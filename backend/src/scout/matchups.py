"""Mynton Matchup: `GET /v1/matchups/compare` (docs/specs/matchups.md, ADR-0013).

`decide` turns two players' standings into one of five outcomes. A probability needs every
condition of ADR-0013 at once, including both flags below; until the prospective evaluation has
passed, RELEASE_EVIDENCE is None and no probability can be produced, whatever the flags say.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

# ADR-0013: code constants, so turning one on is a reviewed commit (like
# privacy.PUBLISH_RESTRICTED_EVENTS). Both stay False until the release conditions hold.
PUBLIC_PROBABILITIES = False
PUBLIC_RATINGS = False  # BWF singles rating numbers, labelled as Mynton estimates
# The passed prospective evaluation (docs/research/...): its reliability bins and log loss.
# None until ADR-0013's release conditions are met; a probability is impossible without it.
RELEASE_EVIDENCE: dict[str, Any] | None = None
ESTABLISHED_AT = 10  # prior matches (ADR-0006)

Outcome = Literal[
    "probability",  # validated: P(a beats b), within a validated pool and calibration range
    "comparison",  # both rated in one pool, but no validated probability (e.g. provisional)
    "insufficient_data",  # a player has too few eligible matches
    "incompatible_pools",  # no chain of played matches connects them (other federation, family)
    "identity_uncertain",  # a record may be two people, or one person under two names
]


class Evidence(BaseModel):
    player_id: int
    pool: str  # e.g. "bwf:MS", "fed:WS"
    rating: float | None
    rating_deviation: float | None  # Glicko-2 RD when the model has one
    prior_matches: int  # eligible matches before `as_of`
    provisional: bool  # fewer than 10 prior matches (ADR-0006)
    last_played: date | None


class ModelInfo(BaseModel):
    name: str  # "elo", "glicko2"
    version: str  # rating_model.config_hash
    run_id: int
    snapshot_id: int
    data_as_of: date  # the last match day in the snapshot
    computed_at: datetime


class Calibration(BaseModel):
    """How such forecasts did in the held-out test period: the reliability bin this forecast
    falls in, so the number comes with its track record."""

    bin_lo: float
    bin_hi: float
    forecasts: int
    observed_rate: float
    test_log_loss: float


class Matchup(BaseModel):
    outcome: Outcome
    discipline: Literal["MS", "WS"] = "MS"
    ratings_shown: bool = False  # rating fields are null unless PUBLIC_RATINGS is on
    data_as_of: date | None = None  # the last match day of the BWF ratings, when BWF is involved
    a: Evidence | None
    b: Evidence | None
    probability_a: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    calibration: Calibration | None = None
    head_to_head: tuple[int, int] | None = None  # decided meetings won by a, by b
    model: ModelInfo | None = None
    reasons: list[str] = []  # why no probability, in plain words

    @model_validator(mode="after")
    def _a_probability_only_when_validated(self) -> "Matchup":
        has_p = self.probability_a is not None
        if has_p != (self.outcome == "probability"):
            raise ValueError("probability_a is given exactly when outcome is 'probability'")
        if has_p and (self.calibration is None or self.model is None or not self.a or not self.b):
            raise ValueError("a probability needs its model, evidence and calibration")
        if not has_p and not self.reasons:
            raise ValueError("every outcome without a probability says why")
        if self.a and self.b and self.outcome in ("probability", "comparison"):
            if self.a.pool != self.b.pool:
                raise ValueError("ratings from different pools are never compared")
            if self.outcome == "probability" and (self.a.provisional or self.b.provisional):
                raise ValueError("no probability for a provisional player")
        return self


@dataclass(frozen=True)
class Rated:
    """A player's served BWF singles rating (rating_current)."""

    rating: float
    rd: float | None
    played: int
    last_played: date
    component: int
    identity_flagged: bool


@dataclass(frozen=True)
class Standing:
    player_id: int
    matches: int  # served matches in this discipline, any source
    last_played: date | None
    bwf: Rated | None  # None: no BWF singles rating in this discipline


@dataclass(frozen=True)
class Served:
    """The run the ratings come from, and how a probability would be made."""

    run_id: int
    snapshot_id: int
    version: str  # the configuration hash
    data_as_of: date
    computed_at: datetime
    temperature: float = 1.0


def _evidence(s: Standing, pool: str, show: bool) -> Evidence:
    if s.bwf is None:  # no rating of this player is ever served (federation, junior)
        return Evidence(
            player_id=s.player_id, pool="unrated", rating=None, rating_deviation=None,
            prior_matches=s.matches, provisional=s.matches < ESTABLISHED_AT,
            last_played=s.last_played,
        )  # fmt: skip
    return Evidence(
        player_id=s.player_id, pool=pool,
        rating=round(s.bwf.rating, 1) if show else None,
        rating_deviation=round(s.bwf.rd, 1) if show and s.bwf.rd is not None else None,
        prior_matches=s.bwf.played, provisional=s.bwf.played < ESTABLISHED_AT,
        last_played=s.bwf.last_played,
    )  # fmt: skip


def blocker(a: Rated, b: Rated, discipline: str) -> tuple[Outcome, str] | None:
    """Why two rated players cannot get a probability, or None. Shared by the route and by
    prospective forecasts, so both apply the same rules (ADR-0013)."""
    if a.identity_flagged or b.identity_flagged:
        return ("identity_uncertain", "A player's record may combine two people with the same "
                "name: the BWF results identify players by name only.")  # fmt: skip
    if a.component != b.component:
        return ("incompatible_pools", "No chain of played matches connects these players.")
    if min(a.played, b.played) < ESTABLISHED_AT:
        label = _LABEL.get(discipline, discipline)
        return ("comparison", f"A player has fewer than {ESTABLISHED_AT} BWF {label} matches: "
                "too few for a reliable estimate.")  # fmt: skip
    return None


def probability(a: Rated, b: Rated, served: Served) -> float:
    """P(a beats b): the Glicko-2 expectation with the served calibration. Odd in the players."""
    from scout.analytics.calibration import with_temperature
    from scout.analytics.models import glicko2_expected

    raw = glicko2_expected(a.rating, a.rd or 350.0, b.rating, b.rd or 350.0)
    return with_temperature(raw, served.temperature)


def decide(
    a: Standing,
    b: Standing,
    discipline: Literal["MS", "WS"],
    served: Served | None,
    *,
    head_to_head: tuple[int, int] | None = None,
    public_probabilities: bool | None = None,
    public_ratings: bool | None = None,
    release_evidence: dict[str, Any] | None = None,
) -> Matchup:
    """One of five outcomes, in ADR-0013's order. The keyword overrides exist for tests only;
    the route passes nothing, so the module constants decide."""
    show_p = PUBLIC_PROBABILITIES if public_probabilities is None else public_probabilities
    show_r = PUBLIC_RATINGS if public_ratings is None else public_ratings
    evidence = RELEASE_EVIDENCE if release_evidence is None else release_evidence
    pool = f"bwf:{discipline}"
    shown = show_r and a.bwf is not None and b.bwf is not None and served is not None
    as_of = served.data_as_of if served and (a.bwf or b.bwf) else None
    ea, eb = _evidence(a, pool, shown), _evidence(b, pool, shown)
    label = _LABEL[discipline]

    def out(outcome: Outcome, *reasons: str) -> Matchup:
        return Matchup(outcome=outcome, discipline=discipline, ratings_shown=shown,
                       data_as_of=as_of, a=ea, b=eb, head_to_head=head_to_head,
                       reasons=list(reasons))  # fmt: skip

    missing = [n for n, st in (("A", a), ("B", b)) if st.matches == 0]
    if missing:
        return out("insufficient_data", *(f"Player {n} has no {label} results." for n in missing))
    if a.bwf is None and b.bwf is None:
        return out("comparison", "Mynton has no validated rating for these players' "
                   "competitions: only their results are compared.")  # fmt: skip
    if a.bwf is None or b.bwf is None or served is None:
        return out("incompatible_pools", "One player's results come from BWF tournaments and "
                   "the other's from federation tournaments: no matches connect them.")  # fmt: skip
    if blocked := blocker(a.bwf, b.bwf, discipline):
        return out(*blocked)
    if not show_p or evidence is None:
        return out("comparison", "Mynton does not publish win probabilities yet: the model is "
                   "still being evaluated on new results.")  # fmt: skip
    p = probability(a.bwf, b.bwf, served)
    bins: list[dict[str, Any]] = evidence["reliability"]
    hit = next(x for x in bins if x["lo"] <= p < x["hi"] or (p == 1.0 and x["hi"] == 1.0))
    return Matchup(
        outcome="probability", discipline=discipline, ratings_shown=shown, data_as_of=as_of,
        a=ea, b=eb, head_to_head=head_to_head, probability_a=round(p, 4),
        calibration=Calibration(bin_lo=hit["lo"], bin_hi=hit["hi"], forecasts=hit["n"],
                                observed_rate=hit["observed"], test_log_loss=evidence["log_loss"]),
        model=ModelInfo(name="glicko2", version=served.version, run_id=served.run_id,
                        snapshot_id=served.snapshot_id, data_as_of=served.data_as_of,
                        computed_at=served.computed_at),
    )  # fmt: skip


_LABEL = {"MS": "men's singles", "WS": "women's singles"}
