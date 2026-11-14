"""Doubles models for offline research only (ADR-0012; never published). Pure: no I/O.

Three ways to rate a pair:
- PairElo: the partnership is the competitor; a new partnership starts from scratch.
- TeamElo: each player has a rating; a team is the mean of its two; both move by the same delta.
- TrueSkill: each player has a mean and an uncertainty; a team's performance is the sum
  (Herbrich, Minka and Graepel 2006, two teams, no draws).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from scout.analytics.graph import UnionFind
from scout.analytics.models import elo_expected
from scout.analytics.ordering import batch_key, batches

Team = tuple[int, int]  # player ids, sorted


@dataclass(frozen=True, slots=True)
class DoublesScored:
    match_id: int
    day: date
    rank: int | None
    cluster: int
    a: Team
    b: Team
    a_won: bool


@dataclass(frozen=True, slots=True)
class DoublesPrediction:
    match_id: int
    day: date
    cluster: int
    p: float | None
    y: int
    prior_a: int  # fewest prior matches of any player on side a
    prior_b: int
    pair_prior: int  # prior matches of the less experienced partnership
    abstain: str | None


class Constant:
    def predict(self, a: Team, b: Team) -> float:
        return 0.5

    def observe(self, results: list[tuple[Team, Team, bool]]) -> None:
        pass


@dataclass
class PairElo:
    k: float = 32.0
    rating: dict[Team, float] = field(default_factory=dict[Team, float])

    def predict(self, a: Team, b: Team) -> float:
        return elo_expected(self.rating.get(a, 1500.0), self.rating.get(b, 1500.0))

    def observe(self, results: list[tuple[Team, Team, bool]]) -> None:
        pre = {t: self.rating.get(t, 1500.0) for a, b, _ in results for t in (a, b)}
        for a, b, a_won in results:
            d = self.k * ((1.0 if a_won else 0.0) - elo_expected(pre[a], pre[b]))
            self.rating[a] = self.rating.get(a, pre[a]) + d
            self.rating[b] = self.rating.get(b, pre[b]) - d


@dataclass
class TeamElo:
    k: float = 32.0
    rating: dict[int, float] = field(default_factory=dict[int, float])

    def team(self, t: Team) -> float:
        return sum(self.rating.get(p, 1500.0) for p in t) / 2

    def predict(self, a: Team, b: Team) -> float:
        return elo_expected(self.team(a), self.team(b))

    def observe(self, results: list[tuple[Team, Team, bool]]) -> None:
        pre = {t: self.team(t) for a, b, _ in results for t in (a, b)}
        delta: dict[int, float] = {}
        for a, b, a_won in results:
            d = self.k * ((1.0 if a_won else 0.0) - elo_expected(pre[a], pre[b]))
            for p in a:
                delta[p] = delta.get(p, 0.0) + d
            for p in b:
                delta[p] = delta.get(p, 0.0) - d
        for p, d in delta.items():
            self.rating[p] = self.rating.get(p, 1500.0) + d


def _pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class TrueSkill:
    mu0: float = 25.0
    sigma0: float = 25.0 / 3
    beta: float = 25.0 / 6
    tau: float = 25.0 / 300  # added uncertainty per match played (dynamics)
    mu: dict[int, float] = field(default_factory=dict[int, float])
    var: dict[int, float] = field(default_factory=dict[int, float])

    def _get(self, p: int) -> tuple[float, float]:
        return self.mu.get(p, self.mu0), self.var.get(p, self.sigma0**2)

    def predict(self, a: Team, b: Team) -> float:
        ma = sum(self._get(p)[0] for p in a)
        mb = sum(self._get(p)[0] for p in b)
        v = sum(self._get(p)[1] for p in (*a, *b)) + 4 * self.beta**2
        return _cdf((ma - mb) / math.sqrt(v))

    def observe(self, results: list[tuple[Team, Team, bool]]) -> None:
        pre = {p: self._get(p) for a, b, _ in results for p in (*a, *b)}
        new_mu = dict[int, float]()
        new_var = dict[int, float]()
        for a, b, a_won in results:
            win, lose = (a, b) if a_won else (b, a)
            var = {p: pre[p][1] + self.tau**2 for p in (*win, *lose)}
            c2 = sum(var.values()) + 4 * self.beta**2
            c = math.sqrt(c2)
            t = (sum(pre[p][0] for p in win) - sum(pre[p][0] for p in lose)) / c
            v = _pdf(t) / max(_cdf(t), 1e-12)
            w = v * (v + t)
            for p, sign in [(p, 1.0) for p in win] + [(p, -1.0) for p in lose]:
                new_mu[p] = new_mu.get(p, pre[p][0]) + sign * var[p] / c * v
                new_var[p] = var[p] * max(1 - var[p] / c2 * w, 1e-6)
        self.mu.update(new_mu)
        self.var.update(new_var)


def replay_doubles(
    model: Constant | PairElo | TeamElo | TrueSkill,
    matches: Iterable[DoublesScored],
    *,
    by_round: bool = True,
) -> list[DoublesPrediction]:
    """As `replay.replay`: predictions from the state before each batch; abstain when a player
    has no prior match or the two sides are not connected through earlier matches."""
    played: dict[int, int] = {}
    pairs: dict[Team, int] = {}
    graph = UnionFind()
    out: list[DoublesPrediction] = []

    def key(m: DoublesScored) -> tuple[date, float]:
        return batch_key(m.day, m.rank, by_round=by_round)

    for batch in batches(matches, key):
        for m in batch:
            na = min(played.get(p, 0) for p in m.a)
            nb = min(played.get(p, 0) for p in m.b)
            reason = None
            if na == 0 or nb == 0:
                reason = "insufficient_data"
            elif not graph.connected(m.a[0], m.b[0]):
                reason = "incompatible_pools"
            p = None if reason else model.predict(m.a, m.b)
            pair = min(pairs.get(m.a, 0), pairs.get(m.b, 0))
            out.append(
                DoublesPrediction(
                    m.match_id, m.day, m.cluster, p, int(m.a_won), na, nb, pair, reason
                )
            )
        model.observe([(m.a, m.b, m.a_won) for m in batch])
        for m in batch:
            for p in (*m.a, *m.b):
                played[p] = played.get(p, 0) + 1
                graph.union(m.a[0], p)
            graph.union(m.a[0], m.b[0])
            for t in (m.a, m.b):
                pairs[t] = pairs.get(t, 0) + 1
    return out
