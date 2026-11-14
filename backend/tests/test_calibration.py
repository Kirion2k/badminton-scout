"""Symmetric calibration and its development-only fitting (ADR-0013). Synthetic data only."""

import math
import random
from datetime import date

import pytest

from scout.analytics.calibration import (
    Calibrator,
    fit_temperature,
    logit,
    sigmoid,
    with_temperature,
)
from scout.ratings import calibrate as cal

FORECASTS = [0.03, 0.2, 0.5, 0.61, 0.97]


@pytest.mark.parametrize("t", [0.5, 1.0, 1.3, 3.0])
def test_a_temperature_keeps_both_orders_summing_to_one(t: float) -> None:
    for p in FORECASTS:
        assert with_temperature(p, t) + with_temperature(1 - p, t) == pytest.approx(1, abs=1e-12)


def test_temperature_one_is_the_identity_and_half_stays_half() -> None:
    assert all(with_temperature(p, 1.0) == pytest.approx(p) for p in FORECASTS)
    assert with_temperature(0.5, 2.7) == 0.5
    assert with_temperature(0.8, 2.0) < 0.8 and with_temperature(0.8, 0.5) > 0.8


def test_the_experience_calibrator_is_symmetric_in_the_players() -> None:
    c = Calibrator(1.1, 1.6, 10)
    for p in FORECASTS:
        for na, nb in ((3, 40), (40, 3), (40, 40), (3, 3)):
            assert c(p, na, nb) + c(1 - p, nb, na) == pytest.approx(1, abs=1e-12)


def test_the_fit_recovers_a_known_temperature() -> None:
    """Forecasts made over-confident by a factor of 1.5 on the log-odds scale."""
    rng = random.Random(3)
    ps: list[float] = []
    ys: list[int] = []
    for _ in range(20_000):
        z = rng.gauss(0, 1.5)
        ys.append(int(rng.random() < sigmoid(z)))
        ps.append(sigmoid(1.5 * z))
    assert fit_temperature(ps, ys) == pytest.approx(1.5, abs=0.06)
    assert logit(sigmoid(2.0)) == pytest.approx(2.0)


def forecast(day: date, p: float = 0.7, y: int = 1, n: int = 20) -> cal.Forecast:
    return cal.Forecast(1, day, "bwf:MS", 1, p, y, n, n)


def test_the_fitter_refuses_the_previously_examined_period() -> None:
    with pytest.raises(cal.ExaminedPeriod):
        cal.fit("temperature", [forecast(date(2024, 6, 1)), forecast(date(2025, 1, 2))])
    kept = cal.development([forecast(date(2010, 1, 1)), forecast(date(2016, 1, 1)),
                            forecast(date(2025, 3, 1))])  # fmt: skip
    assert [f.day.year for f in kept] == [2016]


def test_folds_never_fit_on_their_own_or_later_years(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, int]] = []
    real = cal.fit

    def spy(kind: str, fs: list[cal.Forecast]) -> Calibrator:
        if fs:
            seen.append((min(f.day.year for f in fs), max(f.day.year for f in fs)))
        return real(kind, fs)

    monkeypatch.setattr(cal, "fit", spy)
    rng = random.Random(1)
    dev = [forecast(date(y, 3, 1 + i % 27), rng.random(), rng.random() < 0.5, i % 30)
           for y in range(2012, 2025) for i in range(60)]  # fmt: skip
    result = cal.folds(dev)
    assert set(result["temperature"]["years"]) == {str(y) for y in cal.FOLD_YEARS}
    for fold, (_, last) in zip(
        [y for y in cal.FOLD_YEARS for _ in cal.CANDIDATES[1:]], seen, strict=False
    ):
        assert last < fold
    assert cal.select(result) in cal.CANDIDATES
    assert math.isfinite(result["temperature"]["mean_fold_log_loss"])
