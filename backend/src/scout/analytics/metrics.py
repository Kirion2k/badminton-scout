"""Scoring probabilistic predictions (ADR-0006, ADR-0012). Pure: no I/O."""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

EPS = 1e-12


def log_losses(ps: Sequence[float], ys: Sequence[int]) -> list[float]:
    return [-math.log(max(EPS, p if y else 1.0 - p)) for p, y in zip(ps, ys, strict=True)]


def brier_scores(ps: Sequence[float], ys: Sequence[int]) -> list[float]:
    return [(p - y) ** 2 for p, y in zip(ps, ys, strict=True)]


def hits(ps: Sequence[float], ys: Sequence[int]) -> list[float]:
    """1 for a correct pick, 0 for a wrong one, 0.5 for a 50/50 (no pick)."""
    return [0.5 if p == 0.5 else float((p > 0.5) == bool(y)) for p, y in zip(ps, ys, strict=True)]


@dataclass(frozen=True)
class Bin:
    lo: float
    hi: float
    n: int
    mean_p: float
    observed: float


def reliability(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> list[Bin]:
    """Equal-width bins over [0, 1]; empty bins are left out."""
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(ps, ys, strict=True):
        grouped[min(int(p * bins), bins - 1)].append((p, y))
    return [
        Bin(i / bins, (i + 1) / bins, len(g), sum(p for p, _ in g) / len(g),
            sum(y for _, y in g) / len(g))
        for i, g in enumerate(grouped)
        if g
    ]  # fmt: skip


def ece(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> float:
    """Expected calibration error: the bin-size-weighted gap between forecast and outcome."""
    n = len(ps)
    return (
        sum(b.n / n * abs(b.mean_p - b.observed) for b in reliability(ps, ys, bins)) if n else 0.0
    )


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float


def cluster_bootstrap(
    values: Sequence[float], clusters: Sequence[int], *, n: int = 1000, seed: int = 0
) -> Interval:
    """The mean with a 95% interval, resampling whole clusters (tournaments): matches within a
    tournament are not independent. For a paired comparison pass per-match differences."""
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for v, c in zip(values, clusters, strict=True):
        sums[c] = sums.get(c, 0.0) + v
        counts[c] = counts.get(c, 0) + 1
    ids = sorted(sums)
    if not ids:
        return Interval(math.nan, math.nan, math.nan)
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(n):
        pick = rng.choices(ids, k=len(ids))
        stats.append(sum(sums[c] for c in pick) / sum(counts[c] for c in pick))
    stats.sort()
    return Interval(sum(values) / len(values), stats[int(0.025 * n)], stats[int(0.975 * n) - 1])
