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
def test_incremental_rebuild_equals_full_rebuild(change: str) -> None:
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
    base = bt.run("elo", {"k": 24.0}, old)
    inc, since = bt.incremental("elo", {"k": 24.0}, base, old, new)
    full = bt.run("elo", {"k": 24.0}, new)
    assert since is not None
    key = {p.match_id: p for p in full}
    assert sorted(p.match_id for p in inc) == sorted(key)
    assert all(p == key[p.match_id] for p in inc)


def test_nothing_changed_reuses_everything() -> None:
    data = rows()
    base = bt.run("elo", {}, data)
    inc, since = bt.incremental("elo", {}, base, data, list(data))
    assert since is None and inc == base


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
