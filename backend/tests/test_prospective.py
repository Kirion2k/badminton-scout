"""Prospective forecasts (ADR-0013): recorded before the match, immutable, scored after."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from scout.models import (
    IssuedPrediction,
    Player,
    RatingCurrent,
    RatingModel,
    RatingRun,
    RatingSnapshot,
    Tournament,
)
from scout.ratings import prospective
from tests.test_api_v1 import data, player_id  # noqa: F401  # pyright: ignore[reportUnusedImport]

pytestmark = pytest.mark.db


def served(session: Session, players: dict[int, int], as_of: str = "2025-12-31") -> int:
    snap = RatingSnapshot(family="bwf", query_version=2, content_hash="h", counts={})
    model = RatingModel(name="glicko2", config={}, config_hash="cfg")
    session.add_all([snap, model])
    session.flush()
    run = RatingRun(model_id=model.id, snapshot_id=snap.id, pool="bwf", kind="full",
                    code_version="test", finished_at=datetime.now(UTC),
                    metrics={"data_as_of": as_of, "calibration_hash": "cal",
                             "calibration": {"temperature": 1.0}})  # fmt: skip
    session.add(run)
    session.flush()
    for i, (pid, played) in enumerate(players.items()):
        session.add(RatingCurrent(run_id=run.id, pool="bwf:MS", player_id=pid,
                                  rating=1650.0 - 100 * i, rd=60.0, vol=0.06, played=played,
                                  last_played=date(2025, 12, 1), component=0))  # fmt: skip
    session.flush()
    return run.id


@pytest.fixture
def ids(data: Session) -> dict[str, int]:  # noqa: F811
    names = {"alex": "Alex TESTER", "sam": "Sam EXAMPLE", "kim": "Kim SAMPLE"}
    return {k: player_id(data, v) for k, v in names.items()}


def test_a_forecast_is_issued_only_for_an_eligible_future_match(
    session: Session, ids: dict[str, int]
) -> None:
    alex, sam = ids["alex"], ids["sam"]
    served(session, {alex: 40, sam: 40})
    with pytest.raises(prospective.NotEligible, match="after the ratings"):
        prospective.issue(session, alex, sam, "MS", date(2025, 12, 31), "too early")
    f = prospective.issue(session, alex, sam, "MS", date(2026, 1, 5), "Synthetic Open R16")
    assert 0.5 < f.p_a < 1 and f.config_hash == "cfg" and f.snapshot_hash == "h"


def test_provisional_or_unrated_players_get_no_forecast(
    session: Session, ids: dict[str, int]
) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 4})
    with pytest.raises(prospective.NotEligible, match="fewer than 10"):
        prospective.issue(session, ids["alex"], ids["sam"], "MS", date(2026, 1, 5), "x")
    with pytest.raises(prospective.NotEligible, match="no bwf:MS rating"):
        prospective.issue(session, ids["alex"], ids["kim"], "MS", date(2026, 1, 5), "x")


def test_an_issued_forecast_cannot_be_changed_or_deleted(
    session: Session, ids: dict[str, int]
) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 40})
    f = prospective.issue(session, ids["alex"], ids["sam"], "MS", date(2026, 1, 5), "x")
    for change in ({"p_a": 0.99}, {"player_b": ids["kim"]}, {"scheduled_on": date(2026, 2, 1)}):
        with pytest.raises(DBAPIError, match="cannot be changed"), session.begin_nested():
            session.execute(update(IssuedPrediction).where(IssuedPrediction.id == f.id)
                            .values(**change))  # fmt: skip
    with pytest.raises(DBAPIError, match="never deleted"), session.begin_nested():
        session.delete(f)
        session.flush()
    session.execute(update(IssuedPrediction).where(IssuedPrediction.id == f.id)
                    .values(a_won=True, verified_by="t"))  # fmt: skip
    with pytest.raises(DBAPIError, match="resolved prediction"), session.begin_nested():
        session.execute(update(IssuedPrediction).where(IssuedPrediction.id == f.id)
                        .values(a_won=False))  # fmt: skip


def test_resolve_and_score_against_verified_bwf_results(
    session: Session, ids: dict[str, int]
) -> None:
    alex, sam = ids["alex"], ids["sam"]
    served(session, {alex: 40, sam: 40})
    meeting = session.execute(
        text("""select m.id, m.played_on, m.winner_side, ms.side from match m
                join event e on e.id = m.event_id and e.discipline = 'MS'
                join match_side ms on ms.match_id = m.id
                join match_side_player msp on msp.match_side_id = ms.id
                join player_link pl on pl.source_player_id = msp.source_player_id
                where pl.player_id = :a and m.status = 'completed' and exists (
                    select 1 from match_side ms2
                    join match_side_player msp2 on msp2.match_side_id = ms2.id
                    join player_link pl2 on pl2.source_player_id = msp2.source_player_id
                    where ms2.match_id = m.id and ms2.side <> ms.side and pl2.player_id = :b)"""),
        {"a": alex, "b": sam},
    ).one()
    match_id, when, winner, alex_side = meeting
    # a forecast for a match in a federation source is never resolved: only BWF results count
    prospective.issue(session, alex, sam, "MS", when, "Synthetic Open")
    assert prospective.resolve(session, "test")["resolved"] == 0
    session.execute(update(Tournament).values(source_id="bwf_historical_compilation"))
    assert prospective.resolve(session, "test") == {"resolved": 1, "no_result_yet": 0,
                                                    "ambiguous": 0}  # fmt: skip
    resolved = session.scalars(select(IssuedPrediction)).one()
    assert resolved.resolved_match_id == match_id and resolved.a_won == (winner == alex_side)
    report = prospective.score(session, boot=50)
    assert report["resolved"] == 1
    assert report["conditions"]["1_enough_resolved"] is False  # one forecast is not evidence
    assert "not met" in report["status"]
    assert session.get(Player, alex) is not None
