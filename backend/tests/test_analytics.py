"""Rating models, ordering, replay and metrics on synthetic data only (ADR-0006, ADR-0012)."""

import math
import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from scout.analytics.graph import UnionFind, components
from scout.analytics.metrics import (
    brier_scores,
    cluster_bootstrap,
    ece,
    hits,
    log_losses,
    reliability,
)
from scout.analytics.models import (
    Constant,
    Elo,
    EloConfig,
    Glicko2,
    Glicko2Config,
    Glicko2Player,
    Model,
    Result,
    WinRate,
    elo_expected,
    glicko2_update,
)
from scout.analytics.ordering import batch_key, batches, round_rank
from scout.analytics.replay import Prediction, Scored, replay

DAY = date(2020, 1, 6)


def test_elo_expectation_is_the_standard_logistic() -> None:
    assert elo_expected(1500, 1500) == 0.5
    assert elo_expected(1900, 1500) == pytest.approx(10 / 11)
    assert elo_expected(1600, 1450) + elo_expected(1450, 1600) == pytest.approx(1.0)


def test_elo_update_moves_k_times_the_surprise() -> None:
    elo = Elo(EloConfig(k=32))
    elo.observe(DAY, [Result(1, 2, a_won=True)])
    assert elo.current(1) == pytest.approx(1516) and elo.current(2) == pytest.approx(1484)


def test_a_batch_is_simultaneous() -> None:
    """1 beats 2 and 2 beats 3 on the same day and round: both deltas use the ratings before."""
    elo = Elo(EloConfig(k=32))
    elo.observe(DAY, [Result(1, 2, True), Result(2, 3, True)])
    assert elo.current(1) == pytest.approx(1516)
    assert elo.current(2) == pytest.approx(1500)  # -16 then +16, both from 1500
    assert elo.current(3) == pytest.approx(1484)


def test_provisional_players_move_faster() -> None:
    elo = Elo(EloConfig(k=16, provisional_k=48, provisional_n=1))
    elo.observe(DAY, [Result(1, 2, True)])
    assert elo.current(1) == pytest.approx(1524)  # first match: provisional K
    elo.observe(DAY + timedelta(days=1), [Result(1, 2, True)])
    assert elo.current(1) - 1524 < 8.1  # established K from the second match


def test_inactivity_decay_pulls_towards_the_start() -> None:
    elo = Elo(EloConfig(k=32, decay_per_year=0.5))
    elo.observe(DAY, [Result(1, 2, True)])
    assert elo.current(1, DAY + timedelta(days=round(365.25))) == pytest.approx(1508, abs=0.1)
    assert elo.current(1, DAY) == pytest.approx(1516)


def test_glicko2_matches_glickmans_worked_example() -> None:
    # Glickman (2012), "Example of the Glicko-2 system", tau = 0.5
    me = Glicko2Player(1500, 200, 0.06)
    games = [
        (Glicko2Player(1400, 30, 0.06), 1.0),
        (Glicko2Player(1550, 100, 0.06), 0.0),
        (Glicko2Player(1700, 300, 0.06), 0.0),
    ]
    new = glicko2_update(me, games, tau=0.5)
    assert new.rating == pytest.approx(1464.06, abs=0.01)
    assert new.rd == pytest.approx(151.52, abs=0.01)
    assert new.vol == pytest.approx(0.05999, abs=1e-5)


def test_glicko2_uncertainty_grows_while_inactive_and_is_capped() -> None:
    g = Glicko2(Glicko2Config(period_days=7))
    g.observe(DAY, [Result(1, 2, True)] * 5)
    g.at(DAY + timedelta(days=7))
    after = g.player(1).rd
    g.at(DAY + timedelta(days=7 * 20))
    assert g.player(1).rd > after
    g.at(DAY + timedelta(days=7 * 100_000))
    assert g.player(1).rd == pytest.approx(350)


def test_glicko2_results_in_an_open_period_are_not_yet_seen() -> None:
    g = Glicko2(Glicko2Config(period_days=30))
    g.observe(DAY, [Result(1, 2, True)])
    assert g.predict(1, 2) == 0.5  # the period has not closed
    g.at(DAY + timedelta(days=30))
    assert g.predict(1, 2) > 0.5


def test_win_rate_baseline_is_smoothed_and_symmetric() -> None:
    w = WinRate(prior=2)
    assert w.predict(1, 2) == 0.5
    w.observe(DAY, [Result(1, 2, True)])
    assert w.rate(1) == pytest.approx(3 / 5)
    assert w.predict(1, 2) + w.predict(2, 1) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("label", "rank"),
    [
        (None, None),
        ("", None),
        ("Q", 0),
        ("Q Qual. R16", 160),
        ("Qualification round of 64", 140),
        ("Q QF", 170),
        ("R64", 3140),
        ("Round of 16", 3160),
        ("Ronde van 16", 3160),
        ("QF", 3170),
        ("Kwartfinale", 3170),
        ("Consolation quarter final", 3175),
        ("Verliezersronde kwartfinale", 3175),
        ("SF", 3180),
        ("Semi-finals", 3180),
        ("5th/8th place", 3185),
        ("Final", 3190),
        ("3rd/4th place", 3195),
        ("Group A", 1000),
        ("Round 1", 2010),
        ("R2", 2020),
        ("Ronde 3", 2030),
        ("anything else", None),
    ],
)
def test_round_rank(label: str | None, rank: int | None) -> None:
    assert round_rank(label) == rank


def test_rounds_order_qualification_groups_numbered_then_main_draw() -> None:
    order = ["Q Qual. R16", "Q Final", "Group B", "Round 1", "Round 2", "R64", "QF", "SF", "Final"]
    ranks = [round_rank(x) for x in order]
    assert ranks == sorted(r for r in ranks if r is not None)


def test_unlabelled_matches_wait_for_the_end_of_the_day() -> None:
    items = [("x", None), ("y", round_rank("Final")), ("z", round_rank("R32"))]
    got = list(batches(items, lambda t: batch_key(DAY, t[1])))
    assert [[t[0] for t in b] for b in got] == [["z"], ["y"], ["x"]]
    by_day = list(batches(items, lambda t: batch_key(DAY, t[1], by_round=False)))
    assert len(by_day) == 1


def m(
    i: int, a: int, b: int, a_won: bool = True, day: date = DAY, rnd: str | None = "R32"
) -> Scored:
    return Scored(i, day, round_rank(rnd), cluster=1, a=a, b=b, a_won=a_won)


def test_replay_abstains_without_history_or_a_connection() -> None:
    d2 = DAY + timedelta(days=1)
    preds = replay(
        Elo(),
        [m(1, 1, 2), m(2, 3, 4), m(3, 1, 3, day=d2), m(4, 1, 2, day=d2), m(5, 5, 1, day=d2)],
    )
    reasons = {p.match_id: p.abstain for p in preds}
    assert reasons == {
        1: "insufficient_data",
        2: "insufficient_data",
        3: "incompatible_pools",  # 1 and 3 have played, but never anyone connected
        4: None,
        5: "insufficient_data",  # 5 is new
    }
    assert all((p.p is None) == (p.abstain is not None) for p in preds)


def scored_stream(seed: int, players: int = 40, days: int = 300) -> list[Scored]:
    """Synthetic players with fixed true strengths; outcomes drawn from an Elo-like curve."""
    rng = random.Random(seed)
    strength = {p: rng.gauss(0, 200) for p in range(players)}
    out: list[Scored] = []
    i = 0
    for d in range(days):
        day = DAY + timedelta(days=d)
        pool = rng.sample(range(players), 8)
        for a, b in zip(pool[::2], pool[1::2], strict=True):
            i += 1
            win = rng.random() < elo_expected(strength[a], strength[b])
            out.append(Scored(i, day, round_rank("R16"), cluster=d // 7, a=a, b=b, a_won=win))
    return out


def mean_log_loss(preds: list[Prediction]) -> float:
    scored = [p for p in preds if p.p is not None]
    return sum(log_losses([p.p for p in scored if p.p is not None], [p.y for p in scored])) / len(
        scored
    )


def test_leakage_a_prediction_never_depends_on_its_own_or_a_later_result() -> None:
    stream = scored_stream(1)
    base = {p.match_id: p.p for p in replay(Elo(), stream)}
    target = stream[len(stream) // 2]
    flipped = [replace(s, a_won=not s.a_won) if s is target else s for s in stream]
    after = {p.match_id: p.p for p in replay(Elo(), flipped)}
    same_or_earlier = [s.match_id for s in stream if (s.day, s.rank) <= (target.day, target.rank)]
    assert all(base[i] == after[i] for i in same_or_earlier)  # own match and its batch included
    assert any(base[i] != after[i] for i in base if i not in same_or_earlier)  # it does matter


def test_leakage_every_feature_is_from_before_the_match() -> None:
    """A player's prior count is exactly their matches in strictly earlier batches."""
    stream = scored_stream(2)
    for p in replay(Constant(), stream):
        me = next(s for s in stream if s.match_id == p.match_id)
        key = batch_key(me.day, me.rank)
        for player, prior in ((me.a, p.prior_a), (me.b, p.prior_b)):
            earlier = sum(
                1 for s in stream if player in (s.a, s.b) and batch_key(s.day, s.rank) < key
            )
            assert prior == earlier


@pytest.mark.parametrize(
    "model", [lambda: Elo(), lambda: Glicko2(Glicko2Config(period_days=7)), lambda: WinRate()]
)
def test_skill_comes_from_the_order_of_results(model: "type[Model]") -> None:
    """Real outcomes beat 0.5; shuffling outcomes across matches destroys the skill."""
    stream = scored_stream(3, days=600)
    real = mean_log_loss(replay(model(), stream))
    rng = random.Random(9)
    outcomes = [s.a_won for s in stream]
    rng.shuffle(outcomes)
    shuffled = mean_log_loss(
        replay(model(), [replace(s, a_won=w) for s, w in zip(stream, outcomes, strict=True)])
    )
    assert real < math.log(2) - 0.02
    assert shuffled > math.log(2) - 0.005


def test_replay_is_deterministic() -> None:
    stream = scored_stream(4)
    assert replay(Elo(), stream) == replay(Elo(), list(stream))
    assert replay(Glicko2(), stream) == replay(Glicko2(), stream)


def test_metrics() -> None:
    assert log_losses([0.5], [1]) == [pytest.approx(math.log(2))]
    assert log_losses([1.0], [0])[0] < 30  # clipped, finite
    assert brier_scores([0.8, 0.8], [1, 0]) == [pytest.approx(0.04), pytest.approx(0.64)]
    assert hits([0.7, 0.3, 0.5], [1, 1, 0]) == [1.0, 0.0, 0.5]
    bins = reliability([0.05, 0.15, 0.95, 0.95], [0, 0, 1, 0])
    assert [(b.n, b.observed) for b in bins] == [(1, 0.0), (1, 0.0), (2, 0.5)]
    assert ece([0.5] * 4, [1, 0, 1, 0]) == 0.0
    assert ece([0.9] * 10, [1] * 9 + [0]) == pytest.approx(0.0)
    assert ece([0.9] * 10, [0] * 10) == pytest.approx(0.9)


def test_cluster_bootstrap_is_seeded_and_brackets_the_mean() -> None:
    rng = random.Random(1)
    values = [rng.random() for _ in range(500)]
    clusters = [i // 10 for i in range(500)]
    a = cluster_bootstrap(values, clusters, seed=7)
    assert a == cluster_bootstrap(values, clusters, seed=7)
    assert a.lo < a.mean < a.hi
    one = cluster_bootstrap([1.0, 1.0], [1, 1])
    assert (one.lo, one.hi) == (1.0, 1.0)


def test_union_find_and_components() -> None:
    uf = UnionFind()
    uf.union(1, 2)
    uf.union(3, 4)
    assert uf.connected(1, 2) and not uf.connected(1, 3) and not uf.connected(1, 99)
    uf.union(2, 3)
    assert uf.connected(1, 4)
    assert components([(1, 2), (2, 3), (7, 8)]) == [3, 2]


def test_doubles_models_learn_and_never_see_their_own_result() -> None:
    from scout.analytics.doubles import (
        DoublesScored,
        PairElo,
        TeamElo,
        TrueSkill,
        replay_doubles,
    )

    ts = TrueSkill()
    assert ts.predict((1, 2), (3, 4)) == pytest.approx(0.5)
    ts.observe([((1, 2), (3, 4), True)])
    assert ts.predict((1, 2), (3, 4)) > 0.5
    assert ts.var[1] < (25 / 3) ** 2  # a result makes the estimate more certain
    assert ts.mu[1] == pytest.approx(ts.mu[2]) and ts.mu[3] < 25 < ts.mu[1]

    te = TeamElo(k=32)
    te.observe([((1, 2), (3, 4), True)])
    assert te.rating[1] == te.rating[2] == pytest.approx(1516)
    assert te.predict((1, 3), (2, 4)) == pytest.approx(0.5)  # new pairs, same players

    pe = PairElo(k=32)
    pe.observe([((1, 2), (3, 4), True)])
    assert pe.predict((1, 3), (2, 4)) == 0.5  # a new partnership knows nothing

    rng = random.Random(5)
    stream = [
        DoublesScored(i, DAY + timedelta(days=i // 4), round_rank("R16"), i // 20,
                      (2 * (i % 5), 2 * (i % 5) + 1), (10 + i % 3, 20 + i % 3), rng.random() < 0.6)
        for i in range(400)
    ]  # fmt: skip
    for model in (PairElo, TeamElo, TrueSkill):
        base = {p.match_id: p.p for p in replay_doubles(model(), stream)}
        target = stream[200]
        flipped = [replace(s, a_won=not s.a_won) if s is target else s for s in stream]
        after = {p.match_id: p.p for p in replay_doubles(model(), flipped)}
        assert all(base[s.match_id] == after[s.match_id] for s in stream if s.day <= target.day)


def test_review_unlabelled_match_never_sees_same_day_results() -> None:
    """An unlabelled match may have been the day's first: predicted from the start of the day,
    whatever the labelled matches of that day did (review finding, ADR-0012)."""
    day2 = DAY + timedelta(days=1)
    history = [m(1, 1, 2), m(2, 1, 3), m(3, 2, 3)]
    seen = set[float | None]()
    for semi_won in (True, False):
        today = [m(10, 1, 2, day=day2, rnd=None), m(11, 1, 3, a_won=semi_won, day=day2, rnd="SF")]
        seen.add({x.match_id: x.p for x in replay(Elo(), history + today)}[10])
    assert len(seen) == 1  # the semi-final's result does not leak into it


def test_review_batching_does_not_change_which_matches_are_scored() -> None:
    stream = scored_stream(6)
    by_round = [(p.match_id, p.abstain) for p in replay(Elo(), stream, by_round=True)]
    by_day = [(p.match_id, p.abstain) for p in replay(Elo(), stream, by_round=False)]
    assert sorted(by_round) == sorted(by_day)


def test_review_an_idle_player_is_never_less_known_than_a_new_one() -> None:
    g = Glicko2(Glicko2Config(period_days=7, initial_rd=250.0))
    g.observe(DAY, [Result(1, 2, True)])
    g.at(DAY + timedelta(days=7 * 10_000))
    assert g.player(1).rd <= 250.0 + 1e-9


def test_review_trueskill_compounds_variance_within_a_batch() -> None:
    from scout.analytics.doubles import TrueSkill

    once, twice = TrueSkill(), TrueSkill()
    once.observe([((1, 2), (3, 4), True)])
    twice.observe([((1, 2), (3, 4), True), ((1, 5), (6, 7), True)])
    assert twice.var[1] < once.var[1]
