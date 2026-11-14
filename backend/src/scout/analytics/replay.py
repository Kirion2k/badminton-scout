"""Chronological replay: the only place a model sees results (ADR-0006, ADR-0012). Pure.

Every match in a batch is predicted from the state before the batch, then the batch is applied.
A prediction is made only when both players have played before and are connected through earlier
matches; otherwise the match is an abstention with its reason, and still updates the model.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from scout.analytics.graph import UnionFind
from scout.analytics.models import Model, Result
from scout.analytics.ordering import batch_key, batches


@dataclass(frozen=True, slots=True)
class Scored:
    """An eligible singles match, in replay order."""

    match_id: int
    day: date
    rank: int | None  # ordering.round_rank of its round label
    cluster: int  # the tournament: bootstrap resamples whole tournaments
    a: int
    b: int
    a_won: bool


@dataclass(frozen=True, slots=True)
class Prediction:
    match_id: int
    day: date
    cluster: int
    p: float | None  # P(a beats b); None when abstained
    y: int  # 1 when a won
    prior_a: int  # eligible matches each player had before this one
    prior_b: int
    abstain: str | None  # "insufficient_data" or "incompatible_pools"


def replay(
    model: Model,
    matches: Iterable[Scored],
    *,
    by_round: bool = True,
    after_batch: Callable[[date, list[Scored]], None] | None = None,
) -> list[Prediction]:
    played: dict[int, int] = {}
    graph = UnionFind()
    out: list[Prediction] = []

    def key(m: Scored) -> tuple[date, float]:
        return batch_key(m.day, m.rank, by_round=by_round)

    for batch in batches(matches, key):
        day = batch[0].day
        model.at(day)
        for m in batch:
            na, nb = played.get(m.a, 0), played.get(m.b, 0)
            reason = None
            if na == 0 or nb == 0:
                reason = "insufficient_data"
            elif not graph.connected(m.a, m.b):
                reason = "incompatible_pools"
            p = None if reason else model.predict(m.a, m.b)
            out.append(Prediction(m.match_id, day, m.cluster, p, int(m.a_won), na, nb, reason))
        model.observe(day, [Result(m.a, m.b, m.a_won) for m in batch])
        for m in batch:
            graph.union(m.a, m.b)
            played[m.a] = played.get(m.a, 0) + 1
            played[m.b] = played.get(m.b, 0) + 1
        if after_batch:
            after_batch(day, batch)
    return out
