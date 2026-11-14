"""The matchup contract (docs/specs/matchups.md): what may and may not carry a probability."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from scout import matchups
from scout.matchups import (
    Calibration,
    Evidence,
    Matchup,
    ModelInfo,
    Rated,
    Served,
    Standing,
    decide,
)


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


D = date(2026, 7, 5)
SERVED = Served(run_id=1, snapshot_id=1, version="abc", data_as_of=D,
                computed_at=datetime(2026, 11, 15, tzinfo=UTC))  # fmt: skip
EVIDENCE = {"log_loss": 0.55, "reliability": [
    {"lo": i / 10, "hi": (i + 1) / 10, "n": 300, "observed": i / 10 + 0.05} for i in range(10)
]}  # fmt: skip


def st(
    pid: int,
    played: int = 40,
    *,
    rating: float = 1600.0,
    comp: int = 0,
    flagged: bool = False,
    bwf: bool = True,
    matches: int | None = None,
) -> Standing:
    rated = Rated(rating, 80.0, played, D, comp, flagged) if bwf else None
    return Standing(pid, played if matches is None else matches, D, rated)  # fmt: skip


@pytest.mark.parametrize(
    ("a", "b", "outcome"),
    [
        (st(1), st(2), "comparison"),  # flags off: never a number
        (st(1), st(2, played=5), "comparison"),
        (st(1), st(2, flagged=True), "identity_uncertain"),
        (st(1), st(2, comp=3), "incompatible_pools"),
        (st(1), st(2, bwf=False, matches=30), "incompatible_pools"),
        (st(1, bwf=False, matches=30), st(2, bwf=False, matches=12), "comparison"),
        (st(1), st(2, bwf=False, matches=0), "insufficient_data"),
    ],
)  # fmt: skip
def test_outcomes_with_the_flags_off(a: Standing, b: Standing, outcome: str) -> None:
    m = decide(a, b, "MS", SERVED)
    assert m.outcome == outcome and m.probability_a is None and m.reasons
    assert m.a and m.b and m.a.rating is None and m.b.rating is None and not m.ratings_shown


def test_flags_on_without_release_evidence_still_gives_no_number() -> None:
    m = decide(st(1), st(2), "MS", SERVED, public_probabilities=True, public_ratings=True)
    assert m.outcome == "comparison" and m.probability_a is None
    assert m.ratings_shown and m.a and m.a.rating == 1600.0  # ratings flag alone shows ratings


def test_a_probability_needs_everything_and_is_symmetric() -> None:
    kw: dict[str, Any] = {"public_probabilities": True, "release_evidence": EVIDENCE}
    ab = decide(st(1, rating=1700), st(2, rating=1550), "MS", SERVED, **kw)
    ba = decide(st(2, rating=1550), st(1, rating=1700), "MS", SERVED, **kw)
    assert ab.outcome == ba.outcome == "probability"
    assert ab.probability_a and ba.probability_a
    assert ab.probability_a + ba.probability_a == pytest.approx(1, abs=2e-4)  # 4-place rounding
    assert ab.probability_a > 0.5 and ab.model and ab.calibration
    lo, hi = ab.calibration.bin_lo, ab.calibration.bin_hi
    assert lo <= ab.probability_a < hi
    # every other condition still blocks it
    assert decide(st(1), st(2, played=5), "MS", SERVED, **kw).outcome == "comparison"
    assert decide(st(1), st(2, comp=1), "MS", SERVED, **kw).outcome == "incompatible_pools"
    assert decide(st(1), st(2, flagged=True), "MS", SERVED, **kw).outcome == "identity_uncertain"
    assert decide(st(1), st(2), "MS", None, **kw).outcome == "incompatible_pools"


def test_unrated_players_never_carry_rating_fields_even_with_flags_on() -> None:
    on: dict[str, Any] = {"public_probabilities": True, "public_ratings": True,
                          "release_evidence": EVIDENCE}  # fmt: skip
    m = decide(st(1, bwf=False, matches=30), st(2, bwf=False, matches=30), "MS", SERVED, **on)
    assert m.outcome == "comparison" and m.a and m.a.pool == "unrated" and m.a.rating is None
    assert m.data_as_of is None


def test_the_shipped_flags_are_off() -> None:
    assert matchups.PUBLIC_PROBABILITIES is False
    assert matchups.PUBLIC_RATINGS is False
    assert matchups.RELEASE_EVIDENCE is None
