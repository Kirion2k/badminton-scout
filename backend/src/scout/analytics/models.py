"""Rating models and baselines behind one interface (ADR-0006, ADR-0012). Pure: no I/O.

A model answers `predict(a, b)` (P(a beats b)) from what it has seen so far, and learns from a
batch of results with `observe`. The replay driver (`replay.py`) decides what it may see when.
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Result:
    a: int
    b: int
    a_won: bool


class Model(Protocol):
    def at(self, day: date) -> None:
        """Predictions from now on are for `day`."""
        ...

    def predict(self, a: int, b: int) -> float: ...

    def observe(self, day: date, results: list[Result]) -> None:
        """Apply one batch of results, all played on `day`, as simultaneous."""
        ...


class Constant:
    def at(self, day: date) -> None:
        pass

    def predict(self, a: int, b: int) -> float:
        return 0.5

    def observe(self, day: date, results: list[Result]) -> None:
        pass


@dataclass
class WinRate:
    """Prior win rate with a Beta(prior, prior) smoothing, combined by log5."""

    prior: float = 2.0
    won: dict[int, int] = field(default_factory=dict[int, int])
    played: dict[int, int] = field(default_factory=dict[int, int])

    def at(self, day: date) -> None:
        pass

    def rate(self, p: int) -> float:
        return (self.won.get(p, 0) + self.prior) / (self.played.get(p, 0) + 2 * self.prior)

    def predict(self, a: int, b: int) -> float:
        pa, pb = self.rate(a), self.rate(b)
        return pa * (1 - pb) / (pa * (1 - pb) + pb * (1 - pa))

    def observe(self, day: date, results: list[Result]) -> None:
        for r in results:
            for p, won in ((r.a, r.a_won), (r.b, not r.a_won)):
                self.played[p] = self.played.get(p, 0) + 1
                self.won[p] = self.won.get(p, 0) + int(won)


def elo_expected(ra: float, rb: float) -> float:
    """The standard logistic Elo expectation on the 400-point scale."""
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


@dataclass(frozen=True)
class EloConfig:
    initial: float = 1500.0
    k: float = 32.0
    # a player's first `provisional_n` matches move their rating by `provisional_k` instead
    provisional_k: float | None = None
    provisional_n: int = 0
    # pull towards `initial` by this share per idle year (0 = none); adopted only if validated
    decay_per_year: float = 0.0


@dataclass
class Elo:
    config: EloConfig = field(default_factory=EloConfig)
    rating: dict[int, float] = field(default_factory=dict[int, float])
    played: dict[int, int] = field(default_factory=dict[int, int])
    last: dict[int, date] = field(default_factory=dict[int, date])
    today: date | None = None  # set by `at`; only inactivity decay reads it

    def current(self, p: int, day: date | None = None) -> float:
        r = self.rating.get(p, self.config.initial)
        if day and self.config.decay_per_year and p in self.last:
            idle = (day - self.last[p]).days / 365.25
            r = self.config.initial + (r - self.config.initial) * (
                (1 - self.config.decay_per_year) ** idle
            )
        return r

    def predict(self, a: int, b: int) -> float:
        return elo_expected(self.current(a, self.today), self.current(b, self.today))

    def at(self, day: date) -> None:
        self.today = day

    def _k(self, p: int) -> float:
        c = self.config
        if c.provisional_k is not None and self.played.get(p, 0) < c.provisional_n:
            return c.provisional_k
        return c.k

    def observe(self, day: date, results: list[Result]) -> None:
        # every delta from the ratings before the batch: the batch is simultaneous
        pre = {p: self.current(p, day) for r in results for p in (r.a, r.b)}
        delta: dict[int, float] = {}
        for r in results:
            e = elo_expected(pre[r.a], pre[r.b])
            s = 1.0 if r.a_won else 0.0
            delta[r.a] = delta.get(r.a, 0.0) + self._k(r.a) * (s - e)
            delta[r.b] = delta.get(r.b, 0.0) - self._k(r.b) * (s - e)
        for p, d in delta.items():
            self.rating[p] = pre[p] + d
            self.last[p] = day
        for r in results:
            for p in (r.a, r.b):
                self.played[p] = self.played.get(p, 0) + 1


# Glicko-2 (Glickman, "Example of the Glicko-2 system", 2012). Internal scale: mu, phi.
_SCALE = 173.7178


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _volatility(phi: float, sigma: float, delta: float, v: float, tau: float) -> float:
    """Step 5 of the paper: the Illinois algorithm for the new volatility."""
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        return num / (2.0 * (phi * phi + v + ex) ** 2) - (x - a) / (tau * tau)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau
    fa, fb = f(big_a), f(big_b)
    while abs(big_b - big_a) > 1e-6:
        c = big_a + (big_a - big_b) * fa / (fb - fa)
        fc = f(c)
        if fc * fb <= 0:
            big_a, fa = big_b, fb
        else:
            fa /= 2.0
        big_b, fb = c, fc
    return math.exp(big_a / 2.0)


@dataclass(frozen=True)
class Glicko2Player:
    rating: float = 1500.0
    rd: float = 350.0
    vol: float = 0.06


def glicko2_update(
    player: Glicko2Player, games: list[tuple[Glicko2Player, float]], tau: float
) -> Glicko2Player:
    """One rating period for one player: `games` holds (opponent, score) with score 1, 0 or 0.5.
    No games: only the deviation grows (step 6)."""
    mu, phi = (player.rating - 1500.0) / _SCALE, player.rd / _SCALE
    if not games:
        return Glicko2Player(player.rating, math.sqrt(phi**2 + player.vol**2) * _SCALE, player.vol)
    opp = [((o.rating - 1500.0) / _SCALE, o.rd / _SCALE, s) for o, s in games]
    v = 1.0 / sum(_g(pj) ** 2 * _e(mu, mj, pj) * (1 - _e(mu, mj, pj)) for mj, pj, _ in opp)
    delta = v * sum(_g(pj) * (s - _e(mu, mj, pj)) for mj, pj, s in opp)
    sigma = _volatility(phi, player.vol, delta, v, tau)
    phi_star = math.sqrt(phi * phi + sigma * sigma)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * sum(_g(pj) * (s - _e(mu, mj, pj)) for mj, pj, s in opp)
    return Glicko2Player(mu_new * _SCALE + 1500.0, phi_new * _SCALE, sigma)


@dataclass(frozen=True)
class Glicko2Config:
    tau: float = 0.5
    period_days: int = 30
    initial_rd: float = 350.0
    initial_vol: float = 0.06
    max_rd: float = 350.0


@dataclass
class Glicko2:
    """Results within a rating period are pooled and applied when the period closes, so a
    prediction inside a period sees only earlier periods (no leakage by construction)."""

    config: Glicko2Config = field(default_factory=Glicko2Config)
    state: dict[int, Glicko2Player] = field(default_factory=dict[int, Glicko2Player])
    # the period each player's deviation is current to (inactivity grows it lazily)
    as_of: dict[int, int] = field(default_factory=dict[int, int])
    period: int | None = None
    pending: list[Result] = field(default_factory=list[Result])

    def _index(self, day: date) -> int:
        return day.toordinal() // self.config.period_days

    def player(self, p: int) -> Glicko2Player:
        c = self.config
        s = self.state.get(p) or Glicko2Player(1500.0, c.initial_rd, c.initial_vol)
        idle = (self.period or 0) - self.as_of.get(p, self.period or 0)
        if idle > 0:  # step 6 once per idle period, capped at the starting deviation
            phi2 = (s.rd / _SCALE) ** 2 + idle * s.vol**2
            cap = min(c.initial_rd, c.max_rd)  # a returning player is never less known than new
            s = Glicko2Player(s.rating, min(math.sqrt(phi2) * _SCALE, cap), s.vol)
        return s

    def predict(self, a: int, b: int) -> float:
        pa, pb = self.player(a), self.player(b)
        phi = math.sqrt((pa.rd / _SCALE) ** 2 + (pb.rd / _SCALE) ** 2)
        return 1.0 / (1.0 + math.exp(-_g(phi) * (pa.rating - pb.rating) / _SCALE))

    def at(self, day: date) -> None:
        """Close every period that ended before `day`."""
        idx = self._index(day)
        if self.period is None:
            self.period = idx
        if idx > self.period:
            self._close()
            self.period = idx

    def _close(self) -> None:
        games: dict[int, list[tuple[Glicko2Player, float]]] = {}
        snapshot = {p: self.player(p) for r in self.pending for p in (r.a, r.b)}
        for r in self.pending:
            games.setdefault(r.a, []).append((snapshot[r.b], 1.0 if r.a_won else 0.0))
            games.setdefault(r.b, []).append((snapshot[r.a], 0.0 if r.a_won else 1.0))
        for p, gs in games.items():
            new = glicko2_update(snapshot[p], gs, self.config.tau)
            self.state[p] = Glicko2Player(new.rating, min(new.rd, self.config.max_rd), new.vol)
            # the closing period is accounted for: idle growth counts from the next one
            self.as_of[p] = (self.period or 0) + 1
        self.pending = []

    def observe(self, day: date, results: list[Result]) -> None:
        self.at(day)
        self.pending.extend(results)
