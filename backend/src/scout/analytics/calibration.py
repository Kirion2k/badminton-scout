"""Symmetric probability calibration (ADR-0013). Pure: no I/O.

Every map here works on the log-odds z = logit(p) and is odd in z (no intercept), so
P(A beats B) + P(B beats A) = 1 survives calibration and player order never matters.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

_EPS = 1e-12
T_BOUNDS = (0.25, 4.0)  # ADR-0013


def logit(p: float) -> float:
    p = min(max(p, _EPS), 1 - _EPS)
    return math.log(p / (1 - p))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def with_temperature(p: float, t: float) -> float:
    """sigmoid(logit(p) / t): t > 1 pulls forecasts towards 0.5, t < 1 pushes them out."""
    return sigmoid(logit(p) / t)


def _loss(zs: Sequence[float], ys: Sequence[int], t: float) -> float:
    total = 0.0
    for z, y in zip(zs, ys, strict=True):
        q = sigmoid(z / t)
        total -= math.log(max(_EPS, q if y else 1 - q))
    return total / len(zs)


def fit_temperature(ps: Sequence[float], ys: Sequence[int]) -> float:
    """The temperature minimising mean log loss, by golden-section search on log t within
    T_BOUNDS. Deterministic; log loss is convex in 1/t, so the search finds the optimum."""
    if not ps:
        return 1.0
    zs = [logit(p) for p in ps]
    lo, hi = (math.log(b) for b in T_BOUNDS)
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = _loss(zs, ys, math.exp(a)), _loss(zs, ys, math.exp(b))
    for _ in range(80):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = _loss(zs, ys, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = _loss(zs, ys, math.exp(b))
    return math.exp((lo + hi) / 2)


@dataclass(frozen=True)
class Calibrator:
    """`temperature` for every matchup, or, when `provisional_temperature` is set, that one
    for matchups where either player has fewer than `established_at` prior matches. The
    established test uses both players, so it is symmetric."""

    temperature: float = 1.0
    provisional_temperature: float | None = None
    established_at: int = 10

    def __call__(self, p: float, prior_a: int, prior_b: int) -> float:
        t = self.temperature
        if self.provisional_temperature is not None and min(prior_a, prior_b) < self.established_at:
            t = self.provisional_temperature
        return with_temperature(p, t)
