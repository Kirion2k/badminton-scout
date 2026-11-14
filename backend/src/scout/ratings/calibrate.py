"""Fitting and comparing BWF singles calibrators on development data only (ADR-0013)."""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

from scout.analytics import metrics
from scout.analytics.calibration import Calibrator, fit_temperature

DEV_START = date(2012, 1, 1)  # 2007-2011: warm-up, most ratings immature
DEV_END = date(2024, 12, 31)  # 2025 on was read twice in M8: never fitted on (ADR-0013)
FOLD_YEARS = range(2016, 2025)
ESTABLISHED_AT = 10


class ExaminedPeriod(Exception):
    """A fit was asked to read data from the previously examined period."""


@dataclass(frozen=True, slots=True)
class Forecast:
    match_id: int
    day: date
    pool: str
    cluster: int
    p: float
    y: int
    prior_a: int
    prior_b: int


def load(engine: Engine, run_id: int) -> list[Forecast]:
    """A stored run's made predictions, with the day, pool and tournament of each match."""
    q = text(
        """select mp.match_id, sm.day, sm.pool, sm.cluster, mp.p, mp.y, mp.prior_a, mp.prior_b
           from match_prediction mp
           join rating_run r on r.id = mp.run_id
           join rating_snapshot_match sm on sm.snapshot_id = r.snapshot_id
                                        and sm.match_id = mp.match_id
           where mp.run_id = :run and mp.p is not null
           order by sm.day, mp.match_id"""
    )
    with engine.connect() as c:
        return [Forecast(*row) for row in c.execute(q, {"run": run_id})]


def development(forecasts: Sequence[Forecast]) -> list[Forecast]:
    return [f for f in forecasts if DEV_START <= f.day <= DEV_END]


def _guard(fs: Sequence[Forecast]) -> None:
    if any(f.day > DEV_END for f in fs):
        raise ExaminedPeriod("calibration is fitted on 2012-2024 only (ADR-0013)")


def fit(kind: str, fs: Sequence[Forecast]) -> Calibrator:
    """Fit one candidate. Refuses any forecast after the development period."""
    _guard(fs)
    if kind == "uncalibrated":
        return Calibrator()
    if kind == "temperature":
        return Calibrator(fit_temperature([f.p for f in fs], [f.y for f in fs]))
    if kind == "experience":
        est = [f for f in fs if min(f.prior_a, f.prior_b) >= ESTABLISHED_AT]
        prov = [f for f in fs if min(f.prior_a, f.prior_b) < ESTABLISHED_AT]
        return Calibrator(
            fit_temperature([f.p for f in est], [f.y for f in est]),
            fit_temperature([f.p for f in prov], [f.y for f in prov]),
            ESTABLISHED_AT,
        )
    raise ValueError(kind)


CANDIDATES = ("uncalibrated", "temperature", "experience")


def calibrated(c: Calibrator, fs: Sequence[Forecast]) -> list[float]:
    return [c(f.p, f.prior_a, f.prior_b) for f in fs]


def summary(c: Calibrator, fs: Sequence[Forecast]) -> dict[str, Any]:
    if not fs:
        return {"n": 0}
    ps, ys, cl = calibrated(c, fs), [f.y for f in fs], [f.cluster for f in fs]
    ll = metrics.cluster_bootstrap(metrics.log_losses(ps, ys), cl)
    return {
        "n": len(fs),
        "log_loss": asdict(ll),
        "brier": sum(metrics.brier_scores(ps, ys)) / len(ps),
        "ece": metrics.ece(ps, ys),
        "reliability": [asdict(b) for b in metrics.reliability(ps, ys)],
    }


def groups(fs: Sequence[Forecast]) -> dict[str, list[Forecast]]:
    out: defaultdict[str, list[Forecast]] = defaultdict(list)
    for f in fs:
        out["all"].append(f)
        out[f.pool].append(f)
        out["established" if min(f.prior_a, f.prior_b) >= ESTABLISHED_AT else "provisional"].append(
            f
        )
    return dict(out)


def folds(dev: Sequence[Forecast]) -> dict[str, Any]:
    """Rolling origin: for each fold year, fit on the development years before it and score
    that year. Returns per-candidate fold losses and fitted parameters, plus the paired
    per-match log-loss differences used by the selection rule."""
    out: dict[str, Any] = {k: {"years": {}} for k in CANDIDATES}
    paired: dict[str, list[tuple[int, float]]] = {"experience-temperature": [],
                                                  "temperature-uncalibrated": []}  # fmt: skip
    for year in FOLD_YEARS:
        train = [f for f in dev if f.day.year < year]
        held = [f for f in dev if f.day.year == year]
        losses: dict[str, list[float]] = {}
        for kind in CANDIDATES:
            c = fit(kind, train)
            losses[kind] = metrics.log_losses(calibrated(c, held), [f.y for f in held])
            out[kind]["years"][str(year)] = {
                "n": len(held), "log_loss": sum(losses[kind]) / len(held), **asdict(c),
            }  # fmt: skip
        for i, f in enumerate(held):
            paired["experience-temperature"].append(
                (f.cluster, losses["experience"][i] - losses["temperature"][i])
            )
            paired["temperature-uncalibrated"].append(
                (f.cluster, losses["temperature"][i] - losses["uncalibrated"][i])
            )
    for kind in CANDIDATES:
        ys = out[kind]["years"].values()
        out[kind]["mean_fold_log_loss"] = sum(v["log_loss"] * v["n"] for v in ys) / sum(
            v["n"] for v in ys
        )
    out["paired"] = {
        k: asdict(metrics.cluster_bootstrap([d for _, d in v], [c for c, _ in v]))
        for k, v in paired.items()
    }
    return out


def select(fold_result: dict[str, Any]) -> str:
    """ADR-0013's rule: temperature, unless the experience variant's improvement interval is
    entirely below 0; uncalibrated only if temperature does not improve on it."""
    p = fold_result["paired"]
    if p["temperature-uncalibrated"]["hi"] >= 0:
        return "uncalibrated"
    return "experience" if p["experience-temperature"]["hi"] < 0 else "temperature"


def calibration_hash(c: Calibrator) -> str:
    return hashlib.sha256(json.dumps(asdict(c), sort_keys=True).encode()).hexdigest()[:16]
