"""Offline unit and contract tests for the API Anything provider. No server, no network."""

import logging
import threading
import time
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any

import api_anything
import pytest
from pydantic import BaseModel, ConfigDict

from scout.ingest.operations import OPERATIONS, ApprovedOperation, HackerNewsHit
from scout.ingest.provider import (
    MAX_TIER,
    ApiAnythingProvider,
    BudgetExhausted,
    InvalidParameters,
    OperationFailed,
    ResponseInvalid,
    RetryPolicy,
    RuntimeUnavailable,
    UnknownOperation,
)
from scout.sources import SourceNotPermitted, SourceRights, Use


class Match(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    match_id: str
    winner: int
    played_on: date


def _key(item: BaseModel) -> str:
    return getattr(item, "match_id")  # noqa: B009


SYNTHETIC = ApprovedOperation(
    source_id="synthetic",
    site="synthetic-site",
    op="matches",
    model=Match,
    params=frozenset({"player"}),
    record_key=_key,
)
OPS = MappingProxyType(
    {
        "synthetic.matches": SYNTHETIC,
        "unlicensed.matches": ApprovedOperation(
            source_id="bwf_match_data",
            site="x",
            op="y",
            model=Match,
            params=frozenset(),
            record_key=_key,
        ),
    }
)
ROWS = [
    {"match_id": "m1", "winner": 1, "played_on": "2026-01-05"},
    {"match_id": "m2", "winner": 2, "played_on": "2026-01-05"},
]


def ok(data: Any = ROWS, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "class": "ok", "tier": 1, "ms": 5, "data": data, **extra}


def failed(klass: str, retry: str = "no", **extra: Any) -> dict[str, Any]:
    return {"ok": False, "class": klass, "reason": f"{klass} happened", "retry": retry, **extra}


class FakeClient:
    """Answers with queued results (dicts) or raises queued exceptions, recording every call."""

    def __init__(self, *answers: Mapping[str, Any] | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, dict[str, Any], int | None]] = []
        self.pages: list[Mapping[str, Any]] = []  # answers to result(): the rest of a cut answer
        self.result_calls: list[tuple[str, int | None]] = []

    def call(
        self,
        site: str,
        op: str,
        args: Mapping[str, Any] | None = None,
        *,
        max_tier: int | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append((site, op, dict(args or {}), max_tier))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return api_anything.Result[Any](dict(answer))

    def result(self, result_id: str, offset: int | None = None) -> Mapping[str, Any]:
        self.result_calls.append((result_id, offset))
        return api_anything.Result[Any](dict(self.pages.pop(0)))


def provider(client: FakeClient, **kw: Any) -> tuple[ApiAnythingProvider, list[float]]:
    sleeps: list[float] = []
    return ApiAnythingProvider(client, operations=OPS, sleep=sleeps.append, **kw), sleeps


# --- success and mapping --------------------------------------------------------------------


def test_ok_answer_maps_to_validated_models() -> None:
    client = FakeClient(ok())
    result = provider(client)[0].fetch("synthetic.matches", {"player": "A"})
    assert result.items == (
        Match(match_id="m1", winner=1, played_on=date(2026, 1, 5)),
        Match(match_id="m2", winner=2, played_on=date(2026, 1, 5)),
    )
    assert result.rows == tuple(ROWS)
    assert (result.source_id, result.tier, result.attempts) == ("synthetic", 1, 1)
    assert client.calls == [("synthetic-site", "matches", {"player": "A"}, MAX_TIER)]


def test_browser_tiers_are_never_requested() -> None:
    client = FakeClient(ok())
    provider(client)[0].fetch("synthetic.matches", {})
    assert client.calls[0][3] == 1


def test_empty_list_is_a_valid_empty_answer() -> None:
    assert provider(FakeClient(ok([])))[0].fetch("synthetic.matches", {}).items == ()


def test_hn_model_maps_aliases_and_dates() -> None:
    hit = HackerNewsHit.model_validate(
        {
            "objectID": "1",
            "title": "t",
            "url": None,
            "points": 3,
            "num_comments": 0,
            "author": "a",
            "created_at": "2013-02-17T21:23:40Z",
        }
    )
    assert OPERATIONS["hacker_news.search"].record_key(hit) == "1"
    assert hit.created_at.year == 2013


# --- validation -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        None,  # ok with no data
        {"match_id": "m1"},  # object instead of list
        [{"match_id": "m1", "played_on": "2026-01-05"}],  # missing field
        [{"match_id": "m1", "winner": "first", "played_on": "2026-01-05"}],  # wrong type
        ["m1"],  # list of non-objects
    ],
)
def test_malformed_ok_answers_are_rejected(data: Any) -> None:
    with pytest.raises(ResponseInvalid):
        provider(FakeClient(ok(data)))[0].fetch("synthetic.matches", {})


def test_validation_error_does_not_echo_values() -> None:
    with pytest.raises(ResponseInvalid) as e:
        provider(FakeClient(ok([{**ROWS[0], "match_id": "Jane Private", "winner": "x"}])))[0].fetch(
            "synthetic.matches", {}
        )
    assert "Jane Private" not in str(e.value)
    assert "winner" in str(e.value)


def test_new_upstream_fields_are_reported_as_drift(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    rows = [{**ROWS[0], "court": 3}]
    provider(FakeClient(ok(rows)))[0].fetch("synthetic.matches", {})
    assert "['court']" in caplog.text


# --- policy ---------------------------------------------------------------------------------


def test_unknown_operation_is_refused_before_any_call() -> None:
    client = FakeClient(ok())
    with pytest.raises(UnknownOperation):
        provider(client)[0].fetch("bwf.rankings", {})
    assert client.calls == []


def test_source_without_rights_is_refused_before_any_call() -> None:
    client = FakeClient(ok())
    with pytest.raises(SourceNotPermitted):
        provider(client)[0].fetch("unlicensed.matches", {})
    assert client.calls == []


def test_unexpected_parameters_are_refused() -> None:
    client = FakeClient(ok())
    with pytest.raises(InvalidParameters, match="url"):
        provider(client)[0].fetch("synthetic.matches", {"url": "https://example.com"})
    assert client.calls == []


# --- result classes (contract) --------------------------------------------------------------


@pytest.mark.parametrize(
    "klass", ["auth", "blocked", "input", "drift", "refused", "duplicate", "pending"]
)
def test_non_retryable_classes_fail_after_one_call(klass: str) -> None:
    client = FakeClient(failed(klass, retry="safe" if klass == "pending" else "no"))
    p, sleeps = provider(client)
    with pytest.raises(OperationFailed) as e:
        p.fetch("synthetic.matches", {})
    assert e.value.klass == klass
    assert len(client.calls) == 1
    assert sleeps == []


def test_failure_is_detected_even_when_transport_says_ok() -> None:
    # e.g. a 200 response whose body says blocked, or ok=true with a non-ok class
    for answer in (failed("blocked"), {"ok": True, "class": "drift", "data": ROWS}):
        with pytest.raises(OperationFailed):
            provider(FakeClient(answer))[0].fetch("synthetic.matches", {})


def test_rate_limit_waits_retry_after_then_succeeds() -> None:
    client = FakeClient(failed("rate", retry="after_wait", retryAfterMs=2000), ok())
    p, sleeps = provider(client)
    result = p.fetch("synthetic.matches", {})
    assert sleeps == [2.0]
    assert result.attempts == 2


def test_rate_limit_longer_than_cap_fails_without_sleeping() -> None:
    client = FakeClient(failed("rate", retry="after_wait", retryAfterMs=600_000))
    p, sleeps = provider(client)
    with pytest.raises(OperationFailed) as e:
        p.fetch("synthetic.matches", {})
    assert e.value.retry_after == 600.0
    assert sleeps == []


def test_safe_errors_back_off_exponentially_and_stop_at_the_limit() -> None:
    client = FakeClient(failed("error", retry="safe"))
    p, sleeps = provider(client, retry=RetryPolicy(attempts=3, base_delay_s=0.5))
    with pytest.raises(OperationFailed):
        p.fetch("synthetic.matches", {})
    assert len(client.calls) == 3
    assert sleeps == [0.5, 1.0]


def test_error_needing_a_fix_is_not_retried() -> None:
    client = FakeClient(failed("error", retry="after_fix"))
    with pytest.raises(OperationFailed):
        provider(client)[0].fetch("synthetic.matches", {})
    assert len(client.calls) == 1


# --- runtime availability -------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc", [api_anything.ServerUnavailable("down"), api_anything.Timeout("slow")]
)
def test_unreachable_runtime_is_retried_then_reported(exc: Exception) -> None:
    client = FakeClient(exc)
    p, sleeps = provider(client, retry=RetryPolicy(attempts=2, base_delay_s=0.1))
    with pytest.raises(RuntimeUnavailable):
        p.fetch("synthetic.matches", {})
    assert len(client.calls) == 2
    assert sleeps == [0.1]


def test_runtime_recovering_mid_fetch_succeeds() -> None:
    client = FakeClient(api_anything.ServerUnavailable("down"), ok())
    assert provider(client)[0].fetch("synthetic.matches", {}).attempts == 2


@pytest.mark.parametrize("status", [500, 503])
def test_runtime_5xx_is_retried_then_reported(status: int) -> None:
    client = FakeClient(api_anything.HTTPError(status, "internal error"))
    p, sleeps = provider(client, retry=RetryPolicy(attempts=2, base_delay_s=0.1))
    with pytest.raises(RuntimeUnavailable, match=str(status)):
        p.fetch("synthetic.matches", {})
    assert len(client.calls) == 2
    assert sleeps == [0.1]


@pytest.mark.parametrize(
    "exc",
    [
        api_anything.Unauthorized(401, "bad token"),
        api_anything.NotFound(404, "no such job"),
        api_anything.BadRequest(400, "bad body"),
    ],
)
def test_runtime_4xx_fails_without_retry(exc: Exception) -> None:
    client = FakeClient(exc)
    p, sleeps = provider(client)
    with pytest.raises(OperationFailed) as e:
        p.fetch("synthetic.matches", {})
    assert e.value.klass == "http"
    assert len(client.calls) == 1
    assert sleeps == []


def test_retry_policy_needs_at_least_one_attempt() -> None:
    with pytest.raises(ValueError, match="attempts"):
        RetryPolicy(attempts=0)


# --- reliability ----------------------------------------------------------------------------


def test_repeat_calls_are_independent() -> None:
    client = FakeClient(ok())
    p = provider(client)[0]
    assert len({p.fetch("synthetic.matches", {}).items for _ in range(3)}) == 1
    assert len(client.calls) == 3


def test_concurrent_calls_are_bounded() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    class SlowClient(FakeClient):
        def call(self, *a: Any, **kw: Any) -> Mapping[str, Any]:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return api_anything.Result[Any](ok())

    p = ApiAnythingProvider(SlowClient(), operations=OPS, max_concurrent=2)
    threads = [threading.Thread(target=p.fetch, args=("synthetic.matches", {})) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= 2  # never more than the bound, however the threads are scheduled


def test_logs_carry_parameter_names_not_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    provider(FakeClient(ok()))[0].fetch("synthetic.matches", {"player": "Jane Private"})
    assert "Jane Private" not in caplog.text
    assert "['player']" in caplog.text
    assert "class=ok tier=1" in caplog.text


# --- cut answers (found live in M1B: a 73-match day came back as 35 + more) -----------------


def test_cut_answer_is_read_to_the_end_without_site_requests() -> None:
    client = FakeClient(ok(ROWS[:1], more={"resultId": "r1", "offset": 1}))
    client.pages = [{"ok": True, "class": "ok", "data": ROWS[1:]}]
    result = provider(client)[0].fetch("synthetic.matches", {})
    assert [getattr(m, "match_id") for m in result.items] == ["m1", "m2"]  # noqa: B009
    assert result.rows == tuple(ROWS)
    assert client.result_calls == [("r1", 1)]
    assert len(client.calls) == 1  # the rest came from the runtime's kept copy


def test_cut_answer_that_cannot_be_completed_is_refused() -> None:
    client = FakeClient(ok(ROWS[:1], more={"resultId": "r1", "offset": 1}))
    client.pages = [{"ok": False, "class": "error"}]
    with pytest.raises(ResponseInvalid, match="cut answer"):
        provider(client)[0].fetch("synthetic.matches", {})


# --- request budget (ADR-0008) --------------------------------------------------------------


def _budgeted(
    min_interval_s: float, daily_budget: int | None
) -> MappingProxyType[str, SourceRights]:
    return MappingProxyType(
        {"synthetic": SourceRights(frozenset(Use), "test", min_interval_s=min_interval_s,
                                   daily_budget=daily_budget)}
    )  # fmt: skip


def test_requests_are_spaced_by_the_source_interval() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    p = ApiAnythingProvider(
        FakeClient(ok()), operations=OPS, sleep=sleep, clock=lambda: now[0],
        sources=_budgeted(5.0, None),
    )  # fmt: skip
    p.fetch("synthetic.matches", {})
    now[0] += 1.0
    p.fetch("synthetic.matches", {})
    assert sleeps == [4.0]


def test_daily_budget_stops_requests() -> None:
    client = FakeClient(ok())
    p = ApiAnythingProvider(client, operations=OPS, sleep=lambda _: None, sources=_budgeted(0, 2))
    p.fetch("synthetic.matches", {})
    p.fetch("synthetic.matches", {})
    with pytest.raises(BudgetExhausted):
        p.fetch("synthetic.matches", {})
    assert len(client.calls) == 2


def test_failed_calls_charge_the_runtime_hidden_requests() -> None:
    # a non-ok call may make the runtime send ~4 more site requests (re-send, example args, ...)
    client = FakeClient(failed("error", retry="safe"))
    p = ApiAnythingProvider(client, operations=OPS, sleep=lambda _: None, sources=_budgeted(0, 6))
    with pytest.raises(BudgetExhausted):
        p.fetch("synthetic.matches", {})
    assert len(client.calls) == 2  # 1 + 4 hidden, then the retry: 5 + 1 = 6, budget used up
    assert p.requests_made("synthetic") == 10


def test_failed_call_spaces_the_next_request_for_the_hidden_ones() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    client = FakeClient(failed("input"), ok())
    p = ApiAnythingProvider(
        client, operations=OPS, sleep=sleep, clock=lambda: now[0], sources=_budgeted(5.0, None)
    )
    with pytest.raises(OperationFailed):
        p.fetch("synthetic.matches", {})
    p.fetch("synthetic.matches", {})
    assert sleeps == [25.0]  # its own 5 s plus 4 hidden requests' worth


def test_budget_carries_over_from_earlier_runs() -> None:
    client = FakeClient(ok())
    p = ApiAnythingProvider(
        client, operations=OPS, sleep=lambda _: None, sources=_budgeted(0, 3),
        requests_today={"synthetic": 3},
    )  # fmt: skip
    with pytest.raises(BudgetExhausted):
        p.fetch("synthetic.matches", {})
    assert client.calls == []


def test_healed_answer_is_drift_not_data() -> None:
    with pytest.raises(OperationFailed) as e:
        provider(FakeClient(ok(healed=True)))[0].fetch("synthetic.matches", {})
    assert e.value.klass == "drift"


def test_cut_answer_whose_rest_was_not_kept_is_refused() -> None:
    answer = ok(ROWS[:1], truncated="showing 1 of 2; local retention failed")
    with pytest.raises(ResponseInvalid, match="not kept"):
        provider(FakeClient(answer))[0].fetch("synthetic.matches", {})


def test_multi_page_cut_answer_is_read_in_order() -> None:
    rows = [{**ROWS[0], "match_id": f"m{i}"} for i in range(5)]
    client = FakeClient(ok(rows[:2], more={"resultId": "r", "offset": 2}))
    client.pages = [
        {"ok": True, "data": rows[2:4], "more": {"resultId": "r", "offset": 4}},
        {"ok": True, "data": rows[4:]},
    ]
    result = provider(client)[0].fetch("synthetic.matches", {})
    assert [getattr(m, "match_id") for m in result.items] == [f"m{i}" for i in range(5)]  # noqa: B009
    assert client.result_calls == [("r", 2), ("r", 4)]


def test_oversized_item_paging_fails_fast() -> None:
    client = FakeClient(ok(ROWS[:1], more={"resultId": "r", "offset": 0, "format": "json"}))
    with pytest.raises(ResponseInvalid, match="too large"):
        provider(client)[0].fetch("synthetic.matches", {})
    assert client.result_calls == []
