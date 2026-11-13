"""Request budgets (ADR-0008): one ledger per source and day, enforced across processes."""

import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Protocol

from sqlalchemy import Engine, text

from scout.sources import SOURCES, SourceRights


class BudgetExhausted(Exception):
    """The source's daily request budget would be exceeded."""


class Budget(Protocol):
    def charge(
        self,
        source_id: str,
        requests: int,
        *,
        purpose: str,
        note: str | None = None,
        happened: bool = False,
        historical: bool = False,
    ) -> None:
        """Reserve `requests`, waiting for the source's pacing slot. Raises BudgetExhausted.
        `happened`: already sent just now (the runtime's hidden ones): always recorded, no wait,
        and they occupy pacing slots. `historical`: sent earlier (backfill, manual records):
        recorded, never refused, and they don't move pacing."""
        ...


class MemoryBudget:
    """In-process budget: tests, and tools with no database."""

    def __init__(
        self,
        sources: Mapping[str, SourceRights] = SOURCES,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        spent: Mapping[str, int] | None = None,
    ) -> None:
        self._sources, self._sleep, self._clock = sources, sleep, clock
        self._lock = threading.Lock()
        self._spent: Counter[str] = Counter(spent or {})
        self._next_slot: dict[str, float] = {}

    def charge(
        self,
        source_id: str,
        requests: int,
        *,
        purpose: str,
        note: str | None = None,
        happened: bool = False,
        historical: bool = False,
    ) -> None:
        if requests < 1:
            raise ValueError("a charge is at least one request")
        rights = self._sources.get(source_id)
        if rights is None:
            return  # require_permitted already refused unknown sources
        happened = happened or historical
        with self._lock:
            cap = rights.daily_budget
            if not happened and cap is not None and self._spent[source_id] + requests > cap:
                raise BudgetExhausted(f"{source_id}: daily budget of {rights.daily_budget} used")
            self._spent[source_id] += requests
            slot = max(self._clock(), self._next_slot.get(source_id, 0.0))
            if not historical:
                self._next_slot[source_id] = slot + requests * rights.min_interval_s
        if not happened and (wait := slot - self._clock()) > 0:
            self._sleep(wait)

    def spent(self, source_id: str) -> int:
        return self._spent[source_id]


_CHARGE = text(
    """
    INSERT INTO request_ledger (source_id, day, requests, last_slot)
    VALUES (
        :source, (now() AT TIME ZONE 'utc')::date, :n,
        -- pacing carries across midnight: start after the source's latest slot, whatever the day
        greatest(now(), coalesce(
            (SELECT max(last_slot) FROM request_ledger WHERE source_id = :source), now()
        )) + make_interval(secs => :gap)
    )
    ON CONFLICT (source_id, day) DO UPDATE
    SET requests = request_ledger.requests + EXCLUDED.requests,
        last_slot = greatest(now(), request_ledger.last_slot) + make_interval(secs => :gap)
    WHERE request_ledger.requests + EXCLUDED.requests <= :cap
    RETURNING greatest(0, extract(epoch FROM last_slot - now()) - :gap) AS wait
    """
)


class LedgerBudget:
    """The shared budget: an atomic upsert caps the day's total and hands out pacing slots, so
    separate processes and concurrent jobs stay within the provider's terms together."""

    def __init__(
        self,
        engine: Engine,
        sources: Mapping[str, SourceRights] = SOURCES,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._engine, self._sources, self._sleep = engine, sources, sleep

    def charge(
        self,
        source_id: str,
        requests: int,
        *,
        purpose: str,
        note: str | None = None,
        happened: bool = False,
        historical: bool = False,
    ) -> None:
        if requests < 1:
            raise ValueError("a charge is at least one request")
        rights = self._sources.get(source_id)
        if rights is None:
            return
        never_refuse = happened or historical or rights.daily_budget is None
        cap = 2**31 - 1 if never_refuse or rights.daily_budget is None else rights.daily_budget
        with self._engine.begin() as conn:
            wait = conn.execute(
                _CHARGE,
                {
                    "source": source_id,
                    "n": requests,
                    "gap": 0 if historical else requests * rights.min_interval_s,
                    "cap": cap,
                },
            ).scalar()
            if wait is None or requests > cap:
                raise BudgetExhausted(f"{source_id}: daily budget of {cap} used")
            conn.execute(
                text(
                    "INSERT INTO request_event (source_id, requests, purpose, note) "
                    "VALUES (:s, :n, :p, :note)"
                ),
                {"s": source_id, "n": requests, "p": purpose, "note": note},
            )
        if not (happened or historical) and wait > 0:
            self._sleep(float(wait))

    def spent(self, source_id: str) -> int:
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    text(
                        "SELECT coalesce(sum(requests), 0) FROM request_ledger "
                        "WHERE source_id = :s AND day = (now() AT TIME ZONE 'utc')::date"
                    ),
                    {"s": source_id},
                ).scalar()
                or 0
            )
