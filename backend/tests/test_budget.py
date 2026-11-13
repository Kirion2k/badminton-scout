"""The shared request ledger holds the cap and the pacing across separate budgets/processes."""

import threading
from types import MappingProxyType

import pytest
from sqlalchemy import Engine, text

from scout.budget import BudgetExhausted, LedgerBudget, MemoryBudget
from scout.sources import SourceRights, Use

pytestmark = pytest.mark.db


def capped(cap: int, interval: float = 0.0) -> MappingProxyType[str, SourceRights]:
    rights = SourceRights(frozenset(Use), "test", min_interval_s=interval, daily_budget=cap)
    return MappingProxyType({"synthetic": rights})


@pytest.fixture
def clean(engine: Engine) -> Engine:
    with engine.begin() as c:
        c.execute(text("DELETE FROM request_event; DELETE FROM request_ledger"))
    return engine


def test_cap_holds_across_concurrent_processes(clean: Engine) -> None:
    # 8 workers, each its own LedgerBudget (as separate processes would be), 20 tries each
    refused = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal refused
        budget = LedgerBudget(clean, capped(50), sleep=lambda _: None)
        for _ in range(20):
            try:
                budget.charge("synthetic", 1, purpose="test")
            except BudgetExhausted:
                with lock:
                    refused += 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert LedgerBudget(clean, capped(50)).spent("synthetic") == 50
    assert refused == 8 * 20 - 50


def test_pacing_slots_are_shared_between_budgets(clean: Engine) -> None:
    waits: list[float] = []
    a = LedgerBudget(clean, capped(100, interval=5.0), sleep=waits.append)
    b = LedgerBudget(clean, capped(100, interval=5.0), sleep=waits.append)
    a.charge("synthetic", 1, purpose="test")  # slot now
    b.charge("synthetic", 1, purpose="test")  # another process: must wait about one interval
    assert len(waits) == 1 and 4.0 < waits[0] <= 5.0


def test_requests_that_happened_are_recorded_past_the_cap(clean: Engine) -> None:
    budget = LedgerBudget(clean, capped(3), sleep=lambda _: None)
    budget.charge("synthetic", 3, purpose="test")
    budget.charge("synthetic", 4, purpose="test", happened=True)  # hidden runtime requests
    assert budget.spent("synthetic") == 7
    with pytest.raises(BudgetExhausted):
        budget.charge("synthetic", 1, purpose="test")


def test_every_charge_is_audited_with_its_purpose(clean: Engine) -> None:
    budget = LedgerBudget(clean, capped(10), sleep=lambda _: None)
    budget.charge("synthetic", 1, purpose="learning", note="add matchesInDay")
    budget.charge("synthetic", 2, purpose="live_test")
    with clean.connect() as c:
        rows = c.execute(text("SELECT purpose, requests FROM request_event ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [("learning", 1), ("live_test", 2)]


def test_refused_charge_leaves_no_trace(clean: Engine) -> None:
    budget = LedgerBudget(clean, capped(1), sleep=lambda _: None)
    with pytest.raises(BudgetExhausted):
        budget.charge("synthetic", 2, purpose="test")
    assert budget.spent("synthetic") == 0


def test_memory_budget_matches_ledger_semantics() -> None:
    budget = MemoryBudget(capped(2), sleep=lambda _: None)
    budget.charge("synthetic", 2, purpose="t")
    budget.charge("synthetic", 4, purpose="t", happened=True)
    with pytest.raises(BudgetExhausted):
        budget.charge("synthetic", 1, purpose="t")
    assert budget.spent("synthetic") == 6


def test_historical_records_count_but_do_not_delay_new_requests(clean: Engine) -> None:
    waits: list[float] = []
    budget = LedgerBudget(clean, capped(1000, interval=5.0), sleep=waits.append)
    budget.charge("synthetic", 230, purpose="backfill", historical=True)
    budget.charge("synthetic", 1, purpose="test")
    assert budget.spent("synthetic") == 231
    assert waits == []  # 230 past requests must not push the next one 19 minutes out


@pytest.mark.parametrize("n", [0, -200])
def test_charges_below_one_request_are_refused(clean: Engine, n: int) -> None:
    for budget in (LedgerBudget(clean, capped(10)), MemoryBudget(capped(10))):
        with pytest.raises(ValueError, match="at least one"):
            budget.charge("synthetic", n, purpose="test", historical=True)


def test_pacing_carries_across_the_day_boundary(clean: Engine) -> None:
    # yesterday's row holds a slot in the future: today's first charge must wait for it
    with clean.begin() as c:
        c.execute(text(
            "INSERT INTO request_ledger (source_id, day, requests, last_slot) VALUES "
            "('synthetic', (now() AT TIME ZONE 'utc')::date - 1, 1, now() + interval '3 seconds')"
        ))  # fmt: skip
    waits: list[float] = []
    budget = LedgerBudget(clean, capped(10, interval=5.0), sleep=waits.append)
    budget.charge("synthetic", 1, purpose="t")
    assert len(waits) == 1 and 2.0 < waits[0] <= 3.0
