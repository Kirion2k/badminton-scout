"""The future `GET /v1/matchups/compare` contract (docs/specs/matchups.md). Not mounted: M8
decided no probability is published yet (docs/research/m8-rating-feasibility.md). The models are
here so the contract is typed and tested before any number can reach a user.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

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
