"""The rating dataset rules and backtest harness (ADR-0012), on synthetic rows only."""

import random
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta

import pytest

from scout.analytics.ordering import round_rank
from scout.analytics.replay import Prediction
from scout.ratings import backtest as bt
from scout.ratings.audit import connectivity, name_key
from scout.ratings.dataset import Candidate, Row, classify, content_hash

DAY = date(2020, 1, 6)
SPLITS = bt.Splits(DAY + timedelta(days=99), DAY + timedelta(days=199), None)


def candidate(**over: object) -> Candidate:
    base = Candidate(
        match_id=1, revision_id=1, day=DAY, round="R32", status="completed", winner_side=1,
        discipline="MS", event_name="MS A", category="adult", tournament_id=1,
        side1=(1,), side2=(2,), withheld=False,
    )  # fmt: skip
    return replace(base, **over)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("family", "over", "expected"),
    [
        ("fed", {}, ("fed:MS", "eligible")),
        ("fed", {"category": "junior"}, ("fed:MS:junior", "eligible")),
        ("fed", {"category": "para"}, (None, "para_event")),
        ("fed", {"category": None}, (None, "uncategorised_event")),
        ("bwf", {"category": None}, ("bwf:MS", "eligible")),  # BWF events are all open draws
        ("fed", {"discipline": None}, (None, "unclassified_event")),
        ("fed", {"discipline": "XD"}, (None, "doubles")),
        ("fed", {"status": "walkover"}, (None, "status_walkover")),
        ("fed", {"status": "retired"}, (None, "status_retired")),
        ("fed", {"winner_side": None}, (None, "no_winner")),
        ("fed", {"side1": (1, 3)}, (None, "not_one_player_per_side")),
        ("fed", {"withheld": True}, (None, "withheld_player")),
        ("fed", {"side2": (1,)}, (None, "same_player_both_sides")),
    ],
)
def test_eligibility(
    family: str, over: dict[str, object], expected: tuple[str | None, str]
) -> None:
    assert classify(family, candidate(**over)) == expected


def test_retirements_count_only_in_the_sensitivity_variant() -> None:
    c = candidate(status="retired")
    assert classify("fed", c, include_retired=True) == ("fed:MS", "eligible")


def rows(seed: int = 1, n: int = 600, players: int = 30) -> list[Row]:
    rng = random.Random(seed)
    strength = [rng.gauss(0, 200) for _ in range(players)]
    out: list[Row] = []
    for i in range(n):
        a, b = rng.sample(range(players), 2)
        p = 1 / (1 + 10 ** ((strength[b] - strength[a]) / 400))
        out.append(Row(i, i, "fed:MS", DAY + timedelta(days=i // 3), round_rank("R16"),
                       i // 12, a, b, rng.random() < p))  # fmt: skip
    return out


def test_the_test_split_is_sealed() -> None:
    preds = bt.run("elo", {}, rows(n=900))  # 300 days: reaches the test period
    with pytest.raises(bt.SealedSplit):
        bt.in_split(preds, SPLITS, "test")
    with pytest.raises(bt.SealedSplit):
        bt.evaluate(preds, SPLITS, "test")
    assert bt.in_split(preds, SPLITS, "test", unseal=True)


def test_tuning_never_reads_the_test_split(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, bool]] = []
    real = bt.in_split

    def spy(
        preds: Iterable[Prediction], splits: bt.Splits, split: str, *, unseal: bool = False
    ) -> list[Prediction]:
        asked.append((split, unseal))
        return real(preds, splits, split, unseal=unseal)

    monkeypatch.setattr(bt, "in_split", spy)
    monkeypatch.setitem(bt.GRIDS, "elo", [{"k": 16.0}, {"k": 32.0}])
    trials = bt.tune("elo", rows(), SPLITS)
    assert len(trials) == 4 and trials[0].validation_log_loss <= trials[-1].validation_log_loss
    assert asked and all(split == "validation" and not unseal for split, unseal in asked)


def test_runs_are_reproducible() -> None:
    data = rows()
    a = bt.output_hash(bt.run("glicko2", {"period_days": 7}, data))
    assert a == bt.output_hash(bt.run("glicko2", {"period_days": 7}, list(data)))
    assert content_hash(data) == content_hash(list(reversed(data)))  # order-independent
    assert bt.config_hash("elo", {"k": 32.0}) != bt.config_hash("elo", {"k": 24.0})


def test_pools_never_share_ratings() -> None:
    data = rows()
    other = [replace(r, pool="fed:WS", match_id=r.match_id + 10_000) for r in data]
    together = {p.match_id: p.p for p in bt.run("elo", {}, data + other)}
    alone = {p.match_id: p.p for p in bt.run("elo", {}, data)}
    assert all(together[k] == v for k, v in alone.items())


def test_evaluate_reports_groups_and_intervals() -> None:
    preds = bt.run("elo", {}, rows(n=900))
    out = bt.evaluate(preds, SPLITS, "validation", boot=200)
    allm = out["all"]
    assert allm["predicted"] + sum(allm["abstained"].values()) == allm["matches"]
    assert allm["log_loss"]["lo"] <= allm["log_loss"]["mean"] <= allm["log_loss"]["hi"]
    assert out["established"]["predicted"] + out["provisional"]["predicted"] == allm["predicted"]
    worse = bt.paired(bt.run("constant", {}, rows(n=900)), preds, SPLITS, "validation", boot=200)
    assert worse["mean"] > 0  # the constant forecast is worse than Elo on Elo-like data


@pytest.mark.parametrize("change", ["correction", "insertion", "identity_merge", "removal"])
def test_a_change_touches_only_predictions_from_its_day_on(change: str) -> None:
    """What a rebuild relies on: before `affected_from`, predictions are identical."""
    old = rows()
    new = list(old)
    if change == "correction":  # a historical result fixed
        new[300] = replace(new[300], a_won=not new[300].a_won)
    elif change == "insertion":  # a newly imported older match
        new.append(Row(9999, 9999, "fed:MS", old[200].day, round_rank("R16"), 99, 3, 4, True))
    elif change == "identity_merge":  # player 7 found to be player 8
        new = [replace(r, a=8 if r.a == 7 else r.a, b=8 if r.b == 7 else r.b) for r in new]
        new = [r for r in new if r.a != r.b]
    else:
        del new[250]
    since = bt.affected_from(old, new)
    assert since is not None
    before = {p.match_id: p for p in bt.run("elo", {"k": 24.0}, old) if p.day < since}
    after = {p.match_id: p for p in bt.run("elo", {"k": 24.0}, new) if p.day < since}
    assert before == after
    assert bt.affected_from(old, list(old)) is None


def test_connectivity_finds_separate_federations() -> None:
    a = [Row(i, i, "fed:MS", DAY, None, 1, i % 3, (i + 1) % 3, True) for i in range(6)]
    b = [Row(100 + i, 0, "fed:MS", DAY, None, 2, 10 + i % 2, 11 - i % 2, True) for i in range(2)]
    out = connectivity(a + b, {1: "tournamentsoftware_ba", 2: "tournamentsoftware_bnz"})
    pool = out["fed:MS"]
    assert pool["components"] == 2 and pool["players"] == 5 and pool["cross_home_matches"] == 0
    assert pool["largest"] == [3, 2]
    assert pool["comparable_pair_share"] == pytest.approx((3 * 2 + 2 * 1) / (5 * 4))


def test_names_compare_loosely_without_printing_them() -> None:
    assert name_key("Ondřej KRÁL") == name_key("ondrej kral") == name_key("KRAL, Ondrej")


def test_review_rating_history_is_kept_per_pool() -> None:
    from scout.ratings.store import History

    data = rows()
    junior = [replace(r, pool="fed:MS:junior", match_id=r.match_id + 10_000) for r in data]
    history = History()
    bt.run("elo", {}, data + junior, after_batch=history)
    pools = {pool for pool, _, _ in history.points}
    assert pools == {"fed:MS", "fed:MS:junior"}
    # the same player has two independent series, each counting only its own pool's matches
    p = data[0].a
    adult = max(
        n for (pool, q, _), (*_, n) in history.points.items() if pool == "fed:MS" and q == p
    )
    assert adult == sum(1 for r in data if p in (r.a, r.b))


def test_seed_markers_are_read_from_the_raw_listing() -> None:
    from scout.ratings.audit import _SEED  # pyright: ignore[reportPrivateUsage]

    assert _SEED.search("Ann LEE [3/4]") and _SEED.search("Ann LEE [1]")
    assert not _SEED.search("Ann LEE") and not _SEED.search("Ann [3] LEE")


def test_the_served_ratings_count_components_and_matches_per_pool() -> None:
    from scout.ratings.production import replay_current

    day = DAY + timedelta(days=5)
    pool = [
        Row(1, 1, "bwf:MS", DAY, round_rank("R16"), 1, 1, 2, True),
        Row(2, 2, "bwf:MS", day, round_rank("QF"), 1, 1, 3, False),
        Row(3, 3, "bwf:MS", day, round_rank("QF"), 1, 7, 8, True),  # a separate island
    ]
    preds, current = replay_current({"bwf:MS": pool}, {"period_days": 3}, True, {8}, day)
    got = {c["player_id"]: c for c in current}
    assert {p: got[p]["played"] for p in got} == {1: 2, 2: 1, 3: 1, 7: 1, 8: 1}
    assert got[1]["last_played"] == day and got[2]["last_played"] == DAY
    assert got[1]["component"] == got[2]["component"] == got[3]["component"]
    assert got[7]["component"] == got[8]["component"] != got[1]["component"]
    assert got[8]["identity_flagged"] and not got[1]["identity_flagged"]
    assert len(preds) == 3 and all(p.abstain for p in preds)  # nobody had an earlier day
