"""Persisting runs: the model and configuration, the predictions, and rating history."""

import subprocess
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from scout.analytics.models import Elo, Glicko2, Model, WinRate
from scout.analytics.replay import Prediction, Scored
from scout.models import MatchPrediction, RatingModel, RatingPoint, RatingRun
from scout.ratings.backtest import Splits, config_hash, output_hash


def code_version() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (the developer's own git)
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class History:
    """Each player's rating after their last batch of a day (retrospective, never scored)."""

    def __init__(self) -> None:
        self.points: dict[tuple[int, date], tuple[float, float | None, float | None, int]] = {}
        self.played: dict[int, int] = {}

    def __call__(self, model: Model, day: date, batch: list[Scored]) -> None:
        for m in batch:
            for p in (m.a, m.b):
                self.played[p] = self.played.get(p, 0) + 1
        for p in {q for m in batch for q in (m.a, m.b)}:
            if isinstance(model, Elo):
                value: tuple[float, float | None, float | None] = (model.current(p), None, None)
            elif isinstance(model, Glicko2):
                g = model.player(p)  # results of an open period are not applied yet
                value = (g.rating, g.rd, g.vol)
            elif isinstance(model, WinRate):
                value = (model.rate(p), None, None)
            else:
                continue
            self.points[(p, day)] = (value[0], value[1], value[2], self.played[p])


def save_run(
    session: Session,
    *,
    name: str,
    config: dict[str, Any],
    snapshot_id: int,
    pool: str,
    kind: str,
    splits: Splits,
    preds: Sequence[Prediction],
    metrics: dict[str, Any],
    history: History | None = None,
    from_day: date | None = None,
    base_run_id: int | None = None,
) -> int:
    h = config_hash(name, config)
    model = session.scalar(select(RatingModel).filter_by(name=name, config_hash=h))
    if model is None:
        model = RatingModel(name=name, config=config, config_hash=h)
        session.add(model)
        session.flush()
    run = RatingRun(
        model_id=model.id, snapshot_id=snapshot_id, pool=pool, kind=kind,
        splits={"train_end": str(splits.train_end), "validation_end": str(splits.validation_end),
                "test_end": str(splits.test_end) if splits.test_end else None},
        code_version=code_version(), metrics=metrics, output_hash=output_hash(preds),
        from_day=from_day, base_run_id=base_run_id,
    )  # fmt: skip
    session.add(run)
    session.flush()
    if preds:
        session.execute(
            insert(MatchPrediction),
            [
                {"run_id": run.id, "match_id": p.match_id, "p": p.p, "y": p.y,
                 "split": splits.of(p.day), "prior_a": p.prior_a, "prior_b": p.prior_b,
                 "abstain": p.abstain}
                for p in preds
            ],
        )  # fmt: skip
    if history and history.points:
        session.execute(
            insert(RatingPoint),
            [
                {"run_id": run.id, "player_id": p, "day": d, "rating": r, "rd": rd, "vol": vol,
                 "played": n}
                for (p, d), (r, rd, vol, n) in history.points.items()
            ],
        )  # fmt: skip
    run.finished_at = datetime.now(UTC)
    return run.id
