"""`Provider.fetch(operation, params) -> FetchResult`: rights check, call, validate (ADR-0007)."""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import api_anything
from pydantic import BaseModel, ValidationError

from scout.budget import Budget, BudgetExhausted, MemoryBudget
from scout.ingest.operations import OPERATIONS, ApprovedOperation
from scout.sources import SOURCES, SourceRights, Use, require_permitted

__all__ = ["BudgetExhausted"]

log = logging.getLogger(__name__)

# Third-party sites are only ever read over plain HTTP. Browser tiers need a separate approval.
MAX_TIER = 1


class ProviderError(Exception):
    pass


class UnknownOperation(ProviderError):
    pass


class InvalidParameters(ProviderError):
    pass


class RuntimeUnavailable(ProviderError):
    """The API Anything server could not be reached or did not answer in time."""


class ResponseInvalid(ProviderError):
    """The call succeeded, but its data doesn't match our model: treat as schema drift."""


class OperationFailed(ProviderError):
    def __init__(self, klass: str, reason: str, *, retry_after: float | None = None) -> None:
        super().__init__(f"{klass}: {reason}")
        self.klass = klass
        self.reason = reason
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResult:
    operation: str
    source_id: str
    items: tuple[BaseModel, ...]
    # the source's own rows, aligned with items: what record_payload stores (ADR-0005 provenance)
    rows: tuple[dict[str, Any], ...]
    tier: int | None
    attempts: int
    elapsed_ms: int
    fetched_at: datetime


class Provider(Protocol):
    def fetch(self, operation: str, params: Mapping[str, Any]) -> FetchResult: ...


class CallClient(Protocol):
    """The part of api_anything.Client we use, so tests can substitute it."""

    def call(
        self,
        site: str,
        op: str,
        args: Mapping[str, Any] | None = None,
        *,
        max_tier: int | None = None,
    ) -> Mapping[str, Any]: ...

    def result(self, result_id: str, offset: int | None = None) -> Mapping[str, Any]: ...


# a kept answer longer than this many pages is refused rather than read forever
MAX_RESULT_PAGES = 50
# A call that is not ok can make the runtime send more site requests we never see: the same
# request again, the op's example args, a rescan, a replay (runtime execute.js, "no results").
# Charge those to the budget as if they happened, and space the next request accordingly.
HIDDEN_REQUESTS_ON_FAILURE = 4


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_s: float = 0.5
    # a server asking us to wait longer than this gets a failure, not a sleeping worker
    max_wait_s: float = 30

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")

    def backoff(self, attempt: int) -> float:
        return self.base_delay_s * 2 ** (attempt - 1)


class ApiAnythingProvider:
    def __init__(
        self,
        client: CallClient,
        *,
        operations: Mapping[str, ApprovedOperation] = OPERATIONS,
        retry: RetryPolicy = RetryPolicy(),  # noqa: B008  # frozen dataclass, safe as default
        max_concurrent: int = 4,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        sources: Mapping[str, SourceRights] = SOURCES,
        requests_today: Mapping[str, int] | None = None,
        budget: Budget | None = None,
        purpose: str = "ingest",
    ) -> None:
        self._client = client
        self._operations = operations
        self._retry = retry
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._sleep = sleep
        # the shared ledger in real use (scout.budget.LedgerBudget); in-memory for tests and tools
        self._budget = budget or MemoryBudget(
            sources, sleep=sleep, clock=clock, spent=requests_today
        )
        self._purpose = purpose
        self._made: dict[str, int] = {}

    def requests_made(self, source_id: str) -> int:
        """Requests this provider charged to a source, hidden runtime requests included."""
        return self._made.get(source_id, 0)

    def fetch(self, operation: str, params: Mapping[str, Any]) -> FetchResult:
        spec = self._operations.get(operation)
        if spec is None:
            raise UnknownOperation(f"{operation!r} is not an approved operation")
        require_permitted(spec.source_id, Use.LOCAL_RESEARCH)
        unexpected = set(params) - spec.params
        if unexpected:
            raise InvalidParameters(f"{operation}: unexpected parameters {sorted(unexpected)}")

        started = time.monotonic()
        answer, attempts = self._call_with_retry(operation, spec, params)
        rows, items = _validate(operation, spec, self._complete_data(operation, answer))
        return FetchResult(
            operation=operation,
            source_id=spec.source_id,
            items=items,
            rows=rows,
            tier=answer.get("tier"),
            attempts=attempts,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            fetched_at=datetime.now(UTC),
        )

    def _call_with_retry(
        self, operation: str, spec: ApprovedOperation, params: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], int]:
        for attempt in range(1, self._retry.attempts + 1):
            last = attempt == self._retry.attempts
            try:
                self._pace(spec.source_id)
                with self._slots:
                    answer = self._client.call(spec.site, spec.op, dict(params), max_tier=MAX_TIER)
            except api_anything.ServerUnavailable as e:
                self._runtime_down(operation, attempt, last, str(e))
                continue
            except api_anything.Timeout as e:
                # the runtime may still be working the call, re-checks included
                self._charge_hidden(spec.source_id)
                self._runtime_down(operation, attempt, last, str(e))
                continue
            except api_anything.HTTPError as e:
                # the runtime rejected the request itself: 5xx is the runtime, the rest is ours
                if e.status < 500:
                    raise OperationFailed("http", f"runtime answered HTTP {e.status}") from None
                self._charge_hidden(spec.source_id)
                self._runtime_down(operation, attempt, last, f"runtime answered HTTP {e.status}")
                continue

            klass = answer.get("class")
            # judge the call by its class, never by the HTTP status it arrived with
            ok = answer.get("ok") is True and klass == "ok"
            if not ok:
                self._charge_hidden(spec.source_id)
            if answer.get("healed"):
                # the runtime rewrote the op to fit a changed page: our reviewed spec is the
                # contract, so a healed answer is drift to re-validate, not data to accept
                raise OperationFailed("drift", "the runtime healed the operation; re-validate it")
            log.info(
                "%s: class=%s tier=%s ms=%s attempt=%d args=%s",
                operation,
                klass,
                answer.get("tier"),
                answer.get("ms"),
                attempt,
                sorted(params),  # names only: values may be personal data
            )
            if ok:
                return answer, attempt
            wait = self._retry_wait(answer, attempt)
            if wait is None or last:
                raise OperationFailed(
                    str(klass),
                    str(answer.get("reason") or "no reason given"),
                    retry_after=_seconds(answer.get("retryAfterMs")),
                )
            self._sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover

    def _complete_data(self, operation: str, answer: Mapping[str, Any]) -> Any:
        """The whole answer: the runtime cuts long answers and keeps the rest (no site request)."""
        data = answer.get("data")
        more = answer.get("more")
        if not more:
            if answer.get("truncated"):  # cut, and the runtime could not keep the rest
                raise ResponseInvalid(f"{operation}: the answer was cut and the rest was not kept")
            return data
        if not isinstance(data, list):
            raise ResponseInvalid(f"{operation}: a cut answer that is not a list")
        rows: list[Any] = list(cast(list[Any], data))
        for _ in range(MAX_RESULT_PAGES):
            if more.get("format"):  # JSON-text paging of one oversized item: not a list page
                raise ResponseInvalid(f"{operation}: an item too large for one response")
            page = self._client.result(str(more["resultId"]), offset=int(more["offset"]))
            if page.get("ok") is not True or not isinstance(page.get("data"), list):
                raise ResponseInvalid(f"{operation}: reading the rest of a cut answer failed")
            rows.extend(cast(list[Any], page["data"]))
            more = page.get("more")
            if not more:
                if page.get("truncated"):
                    raise ResponseInvalid(f"{operation}: the rest of the answer was not kept")
                return rows
        raise ResponseInvalid(f"{operation}: answer longer than {MAX_RESULT_PAGES} pages")

    def _pace(self, source_id: str) -> None:
        """Reserve one request in the source's budget, waiting for its pacing slot (ADR-0008)."""
        self._budget.charge(source_id, 1, purpose=self._purpose)
        self._made[source_id] = self._made.get(source_id, 0) + 1

    def _charge_hidden(self, source_id: str) -> None:
        self._budget.charge(
            source_id, HIDDEN_REQUESTS_ON_FAILURE, purpose=self._purpose,
            note="runtime re-checks after a failed call", happened=True,
        )  # fmt: skip
        self._made[source_id] = self._made.get(source_id, 0) + HIDDEN_REQUESTS_ON_FAILURE

    def _runtime_down(self, operation: str, attempt: int, last: bool, why: str) -> None:
        """Back off before the next attempt, or give up on the last one."""
        log.warning("%s: runtime unavailable (attempt %d): %s", operation, attempt, why)
        if last:
            raise RuntimeUnavailable(why)
        self._sleep(self._retry.backoff(attempt))

    def _retry_wait(self, answer: Mapping[str, Any], attempt: int) -> float | None:
        """Seconds to wait before retrying, or None when this answer must not be retried."""
        if answer.get("class") not in ("rate", "error"):
            # auth, blocked, input, drift, refused, pending: the same call meets the same answer
            return None
        hint = answer.get("retry")
        if hint == "safe":
            return self._retry.backoff(attempt)
        if hint == "after_wait":
            wait = _seconds(answer.get("retryAfterMs")) or self._retry.backoff(attempt)
            return wait if 0 <= wait <= self._retry.max_wait_s else None
        return None


def _seconds(ms: Any) -> float | None:
    return ms / 1000 if isinstance(ms, int | float) else None


def _validate(
    operation: str, spec: ApprovedOperation, data: Any
) -> tuple[tuple[dict[str, Any], ...], tuple[BaseModel, ...]]:
    kind = type(data).__name__
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in cast(list[object], data)):
        raise ResponseInvalid(f"{operation}: expected a list of objects, got {kind}")
    rows = cast(list[dict[str, Any]], data)
    items: list[BaseModel] = []
    for i, row in enumerate(rows):
        try:
            items.append(spec.model.model_validate(row))
        except ValidationError as e:
            # field locations only: input values may be third-party personal data
            where = sorted({".".join(map(str, err["loc"])) for err in e.errors()})
            raise ResponseInvalid(f"{operation}: row {i} invalid at {where}") from None
    expected = {f.alias or name for name, f in spec.model.model_fields.items()}
    if extra := {key for row in rows for key in row} - expected:
        log.warning("%s: answer has fields the model doesn't know: %s", operation, sorted(extra))
    return tuple(rows), tuple(items)
