"""Backtests on a frozen snapshot (ADR-0006, ADR-0012).

Splits only decide which predictions are scored: ratings run continuously from the first match.
The test split is sealed: scoring it needs `unseal=True`, which tuning never passes.
"""

import functools
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from scout.analytics import metrics
from scout.analytics.models import Constant, Elo, EloConfig, Glicko2, Glicko2Config, Model, WinRate
from scout.analytics.replay import Prediction, Scored, replay
from scout.ratings.dataset import Row

PROVISIONAL_BELOW = 10  # ADR-0006: fewer prior matches than this is "provisional"


@dataclass(frozen=True)
class Splits:
    train_end: date
    validation_end: date
    test_end: date | None  # None: to the end of the data

    def of(self, day: date) -> str:
        if day <= self.train_end:
            return "train"
        if day <= self.validation_end:
            return "validation"
        return "test" if self.test_end is None or day <= self.test_end else "after"


# Pre-registered in ADR-0012 (committed e48537f before any evaluation).
SPLITS = {
    "bwf": Splits(date(2021, 12, 31), date(2024, 12, 31), date(2026, 7, 5)),
    "fed": Splits(date(2025, 6, 30), date(2025, 12, 31), None),
}


class SealedSplit(Exception):
    """The test split was asked for without unsealing it."""


def make_model(name: str, config: dict[str, Any]) -> Model:
    if name == "constant":
        return Constant()
    if name == "winrate":
        return WinRate(**config)
    if name == "elo":
        return Elo(EloConfig(**config))
    if name == "glicko2":
        return Glicko2(Glicko2Config(**config))
    raise ValueError(f"unknown model {name!r}")


def config_hash(name: str, config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps([name, config], sort_keys=True).encode()).hexdigest()[:16]


def scored(rows: Iterable[Row]) -> list[Scored]:
    return [Scored(r.match_id, r.day, r.rank, r.cluster, r.a, r.b, r.a_won) for r in rows]


def run(
    name: str,
    config: dict[str, Any],
    rows: Sequence[Row],
    *,
    by_round: bool = True,
    after_batch: Callable[[Model, date, list[Scored]], None] | None = None,
) -> list[Prediction]:
    """Replay each pool separately (pools never share ratings) and return every prediction."""
    by_pool: defaultdict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_pool[r.pool].append(r)
    out: list[Prediction] = []
    for pool in sorted(by_pool):
        model = make_model(name, config)
        hook: Callable[[date, list[Scored]], None] | None = None
        if after_batch:
            hook = functools.partial(after_batch, model)
        out.extend(replay(model, scored(by_pool[pool]), by_round=by_round, after_batch=hook))
    return out


def output_hash(preds: Iterable[Prediction]) -> str:
    h = hashlib.sha256()
    for p in sorted(preds, key=lambda p: p.match_id):
        h.update(f"{p.match_id}|{'-' if p.p is None else f'{p.p:.12f}'}|{p.abstain}\n".encode())
    return h.hexdigest()


def in_split(
    preds: Iterable[Prediction], splits: Splits, split: str, *, unseal: bool = False
) -> list[Prediction]:
    if split == "test" and not unseal:
        raise SealedSplit("the test split is read once, for the selected configurations")
    return [p for p in preds if splits.of(p.day) == split]


def _summary(preds: Sequence[Prediction], seed: int, boot: int) -> dict[str, Any]:
    made = [p for p in preds if p.p is not None]
    out: dict[str, Any] = {
        "matches": len(preds),
        "predicted": len(made),
        "coverage": len(made) / len(preds) if preds else math.nan,
        "abstained": {
            r: sum(1 for p in preds if p.abstain == r)
            for r in ("insufficient_data", "incompatible_pools")
        },
    }
    if not made:
        return out
    ps = [p.p for p in made if p.p is not None]
    ys = [p.y for p in made]
    clusters = [p.cluster for p in made]
    for key, values in (
        ("log_loss", metrics.log_losses(ps, ys)),
        ("brier", metrics.brier_scores(ps, ys)),
        ("accuracy", metrics.hits(ps, ys)),
    ):
        ci = metrics.cluster_bootstrap(values, clusters, n=boot, seed=seed)
        out[key] = {"mean": ci.mean, "lo": ci.lo, "hi": ci.hi}
    out["ece"] = metrics.ece(ps, ys)
    out["reliability"] = [
        {"lo": b.lo, "hi": b.hi, "n": b.n, "mean_p": b.mean_p, "observed": b.observed}
        for b in metrics.reliability(ps, ys)
    ]
    return out


def evaluate(
    preds: Sequence[Prediction],
    splits: Splits,
    split: str,
    *,
    unseal: bool = False,
    seed: int = 0,
    boot: int = 1000,
    pools: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Metrics for one split: overall, provisional vs established, by year and by pool."""
    chosen = in_split(preds, splits, split, unseal=unseal)
    out = {"all": _summary(chosen, seed, boot)}
    established = [p for p in chosen if min(p.prior_a, p.prior_b) >= PROVISIONAL_BELOW]
    provisional = [p for p in chosen if min(p.prior_a, p.prior_b) < PROVISIONAL_BELOW]
    out["established"] = _summary(established, seed, boot)
    out["provisional"] = _summary(provisional, seed, boot)
    years: defaultdict[int, list[Prediction]] = defaultdict(list)
    for p in chosen:
        years[p.day.year].append(p)
    out["by_year"] = {str(y): _summary(ps, seed, boot) for y, ps in sorted(years.items())}
    if pools:
        by_pool: defaultdict[str, list[Prediction]] = defaultdict(list)
        for p in chosen:
            by_pool[pools[p.match_id]].append(p)
        out["by_pool"] = {k: _summary(v, seed, boot) for k, v in sorted(by_pool.items())}
    return out


def paired(
    a: Sequence[Prediction],
    b: Sequence[Prediction],
    splits: Splits,
    split: str,
    *,
    unseal: bool = False,
    seed: int = 0,
    boot: int = 1000,
) -> dict[str, float]:
    """Log loss of a minus log loss of b on the matches both predicted, with a cluster-bootstrap
    95% interval. Below zero, with the whole interval below zero, means a is better."""
    pb = {p.match_id: p for p in in_split(b, splits, split, unseal=unseal) if p.p is not None}
    diffs: list[float] = []
    clusters: list[int] = []
    for p in in_split(a, splits, split, unseal=unseal):
        q = pb.get(p.match_id)
        if p.p is None or q is None or q.p is None:
            continue
        (la,) = metrics.log_losses([p.p], [p.y])
        (lb,) = metrics.log_losses([q.p], [q.y])
        diffs.append(la - lb)
        clusters.append(p.cluster)
    ci = metrics.cluster_bootstrap(diffs, clusters, n=boot, seed=seed)
    return {"n": len(diffs), "mean": ci.mean, "lo": ci.lo, "hi": ci.hi}


def validation_log_loss(preds: Sequence[Prediction], splits: Splits) -> float:
    """The tuning objective. Reads the validation split only."""
    made = [p for p in in_split(preds, splits, "validation") if p.p is not None]
    ps = [p.p for p in made if p.p is not None]
    return sum(metrics.log_losses(ps, [p.y for p in made])) / len(made) if made else math.inf


# Tuning grids (ADR-0012): small on purpose. Each is scored on validation only. Widened once
# (2026-11-14) after the first BWF pass put the Elo optimum at the grid's edge (K 48, 2x), and
# again for the federations (win-rate prior 1, provisional 3x). BWF was selected on the second
# grid (docs/research/m8-bwf-selected.json); a 1-day Glicko-2 period is the floor, not an edge.
# provisional K as a multiple of K, and for how many matches
_PROVISIONAL = ((1.5, 10), (2, 10), (2, 20), (3, 20), (4, 20), (3, 40))
GRIDS: dict[str, list[dict[str, Any]]] = {
    "winrate": [{"prior": a} for a in (0.25, 0.5, 1.0, 2.0, 5.0, 10.0)],
    "elo": [
        {"k": k, "provisional_k": pk, "provisional_n": pn, "decay_per_year": d}
        for k in (16.0, 24.0, 32.0, 40.0, 48.0, 64.0, 80.0)
        for pk, pn in [(None, 0), *((k * x, n) for x, n in _PROVISIONAL)]
        for d in (0.0, 0.1, 0.25)
    ],
    "glicko2": [
        {"tau": t, "period_days": pd, "initial_rd": rd}
        for t in (0.3, 0.5, 0.8, 1.2)
        for pd in (1, 3, 7, 14, 30, 60)
        for rd in (250.0, 350.0)
    ],
}


@dataclass(frozen=True)
class Trial:
    name: str
    config: dict[str, Any]
    by_round: bool
    validation_log_loss: float


def tune(name: str, rows: Sequence[Row], splits: Splits) -> list[Trial]:
    """Every grid configuration, with round and day batching, best first."""
    trials: list[Trial] = []
    for config in GRIDS[name]:
        for by_round in (True, False):
            preds = run(name, config, rows, by_round=by_round)
            trials.append(Trial(name, config, by_round, validation_log_loss(preds, splits)))
    return sorted(trials, key=lambda t: t.validation_log_loss)


def affected_from(old: Sequence[Row], new: Sequence[Row]) -> date | None:
    """The earliest day whose eligible matches differ between two snapshots: an added, removed
    or corrected match, or a changed player id (a merge or split). None when nothing changed."""
    before = {r.match_id: r for r in old}
    after = {r.match_id: r for r in new}
    days = [r.day for k, r in before.items() if after.get(k) != r]
    days += [r.day for k, r in after.items() if before.get(k) != r]
    return min(days, default=None)


def incremental(
    name: str,
    config: dict[str, Any],
    base: Sequence[Prediction],
    old: Sequence[Row],
    new: Sequence[Row],
    *,
    by_round: bool = True,
) -> tuple[list[Prediction], date | None]:
    """Predictions for `new`, keeping `base` (made on `old`) before the earliest affected day.
    Ratings are path-dependent, so everything from that day on is recomputed. The state at that
    day is re-derived by replaying the unchanged earlier matches: at this scale (a full BWF replay
    takes seconds) a stored checkpoint is not worth its complexity. Tests check the result is
    identical to a full rebuild."""
    since = affected_from(old, new)
    if since is None:
        return list(base), None
    fresh = [p for p in run(name, config, new, by_round=by_round) if p.day >= since]
    kept = [p for p in base if p.day < since]
    return sorted(kept + fresh, key=lambda p: (p.day, p.match_id)), since
