"""Chronological replay: the only place a model sees results (ADR-0006, ADR-0012). Pure.

Day by day:
1. Abstentions are decided from the start of the day: a player with no match on an earlier day,
   or two players not connected through earlier days' matches, get no prediction. This does not
   depend on round batching, so every model and batching option is scored on the same matches.
2. A match without a round label is predicted from the start-of-day state (it may have been the
   day's first match) and applied after the day's labelled matches.
3. Labelled matches go round by round: each round is predicted from the state before it, then
   applied as one simultaneous batch.
Every match updates the model, abstained or not.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from itertools import groupby

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
    prior_a: int  # eligible matches each player had on earlier days
    prior_b: int
    abstain: str | None  # "insufficient_data" or "incompatible_pools"


def day_plan[T](
    matches: Iterable[T],
    day_of: Callable[[T], date],
    rank_of: Callable[[T], int | None],
    *,
    by_round: bool,
) -> Iterable[tuple[date, list[T], list[list[T]]]]:
    """(day, matches predicted from the start of the day, labelled rounds in order). With day
    batching every match is predicted from the start of the day."""
    ordered = sorted(matches, key=lambda m: day_of(m))  # stable: input order within a day
    for day, group in groupby(ordered, key=day_of):
        todays = list(group)
        if not by_round:
            yield day, todays, []
            continue
        early = [m for m in todays if rank_of(m) is None]
        labelled = [m for m in todays if rank_of(m) is not None]
        rounds = list(batches(labelled, lambda m, d=day: batch_key(d, rank_of(m))))
        yield day, early, rounds


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
    for day, early, rounds in day_plan(
        matches, lambda m: m.day, lambda m: m.rank, by_round=by_round
    ):
        model.at(day)
        todays = early + [m for r in rounds for m in r]
        reason: dict[int, str | None] = {}
        for m in todays:  # from the start of the day: independent of batching
            if played.get(m.a, 0) == 0 or played.get(m.b, 0) == 0:
                reason[m.match_id] = "insufficient_data"
            elif not graph.connected(m.a, m.b):
                reason[m.match_id] = "incompatible_pools"
            else:
                reason[m.match_id] = None

        # unlabelled matches are predicted first and applied last; each round in between
        steps = [("predict", early)]
        steps += [(action, r) for r in rounds for action in ("predict", "apply")]
        steps.append(("apply", early))
        for action, batch in steps:
            if action == "predict":
                for m in batch:
                    why = reason[m.match_id]
                    p = None if why else model.predict(m.a, m.b)
                    na, nb = played.get(m.a, 0), played.get(m.b, 0)
                    out.append(Prediction(m.match_id, day, m.cluster, p, int(m.a_won), na, nb, why))
            elif batch:
                model.observe(day, [Result(m.a, m.b, m.a_won) for m in batch])
                if after_batch:
                    after_batch(day, batch)
        for m in todays:
            graph.union(m.a, m.b)
            played[m.a] = played.get(m.a, 0) + 1
            played[m.b] = played.get(m.b, 0) + 1
    return out
