"""The matchup contract (docs/specs/matchups.md): what may and may not carry a probability."""

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from scout.main import create_app
from scout.matchups import Calibration, Evidence, Matchup, ModelInfo


def ev(pid: int, pool: str = "bwf:MS", n: int = 40) -> Evidence:
    return Evidence(
        player_id=pid, pool=pool, rating=1600.0, rating_deviation=60.0, prior_matches=n,
        provisional=n < 10, last_played=date(2026, 6, 1),
    )  # fmt: skip


MODEL = ModelInfo(
    name="glicko2", version="abc", run_id=5, snapshot_id=1, data_as_of=date(2026, 7, 5),
    computed_at=datetime(2026, 11, 14, tzinfo=UTC),
)  # fmt: skip
CAL = Calibration(bin_lo=0.6, bin_hi=0.7, forecasts=555, observed_rate=0.589, test_log_loss=0.548)


def test_a_validated_probability_carries_its_evidence() -> None:
    m = Matchup(outcome="probability", a=ev(1), b=ev(2), probability_a=0.64, calibration=CAL,
                model=MODEL)  # fmt: skip
    assert m.probability_a == 0.64


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"outcome": "comparison", "a": ev(1), "b": ev(2), "probability_a": 0.6,
          "reasons": ["x"]}, "exactly when"),
        ({"outcome": "probability", "a": ev(1), "b": ev(2), "probability_a": 0.6},
         "needs its model"),
        ({"outcome": "insufficient_data", "a": ev(1, n=0), "b": ev(2)}, "says why"),
        ({"outcome": "comparison", "a": ev(1), "b": ev(2, pool="fed:MS"), "reasons": ["x"]},
         "different pools"),
        ({"outcome": "probability", "a": ev(1, n=3), "b": ev(2), "probability_a": 0.6,
          "calibration": CAL, "model": MODEL}, "provisional"),
        ({"outcome": "probability", "a": ev(1), "b": ev(2), "probability_a": 1.4,
          "calibration": CAL, "model": MODEL}, "less than or equal"),
    ],
)  # fmt: skip
def test_unsupported_probabilities_cannot_be_constructed(
    fields: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Matchup(**fields)


def test_outcomes_without_a_probability() -> None:
    for outcome in ("comparison", "insufficient_data", "incompatible_pools", "identity_uncertain"):
        m = Matchup(outcome=outcome, a=ev(1), b=ev(2), reasons=["why"])  # type: ignore[arg-type]
        assert m.probability_a is None
    cross = Matchup(outcome="incompatible_pools", a=ev(1), b=ev(9, pool="fed:MS"),
                    reasons=["No chain of played matches connects these players."])  # fmt: skip
    assert cross.a and cross.b and cross.a.pool != cross.b.pool


@pytest.mark.anyio
async def test_the_matchup_route_is_not_published_yet() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        assert (await api.get("/v1/matchups/compare", params={"a": 1, "b": 2})).status_code == 404
