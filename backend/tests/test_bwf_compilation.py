"""The bwf-match-data importer on synthetic rows (invented names and ids). No network."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.ingest import bwf_compilation as comp
from scout.ingest.tournamentsoftware import Rejection
from scout.models import IngestIssue, IngestRun, Match, PlayerLink, SourcePlayer, Tournament

INDEX = comp.Index.load(
    [
        {"id": 7001, "name": "Synthetic Open 2015", "start_date": "2015-03-03 00:00:00",
         "end_date": "2015-03-08 00:00:00", "location": "Testville, Exampleland"},
        {"id": 7002, "name": "Synthetic Open 2016", "start_date": "2016-03-01 00:00:00",
         "end_date": "2016-03-06 00:00:00", "location": "Testville"},
        # the same name twice, years apart: the match date decides
        {"id": 7003, "name": "Synthetic Masters", "start_date": "2014-05-01 00:00:00",
         "end_date": "2014-05-04 00:00:00"},
        {"id": 7004, "name": "Synthetic Masters", "start_date": "2015-05-01 00:00:00",
         "end_date": "2015-05-04 00:00:00"},
    ]
)  # fmt: skip


def row(**kw: str) -> dict[str, Any]:
    base = {
        "date": "2015-03-05", "discipline": "MS", "tournament": "Synthetic Open 2015",
        "tier": "Grand Prix", "round": "R16", "host_location": "Exampleland",
        "team1": "Alex TESTER", "team2": "Sam EXAMPLE", "winner": "1", "score": "21-15 21-18",
        "team1_at_home": "False", "team2_at_home": "False",
    }  # fmt: skip
    return base | kw


@pytest.mark.parametrize(
    ("winner", "score", "status"),
    [
        ("1", "21-15 21-18", "completed"),
        ("2", "21-15 18-21 19-21", "completed"),
        ("1", "29-27 30-29", "completed"),
        ("1", "21-15 11-4", "retired"),  # stopped inside game two
        ("1", "21-15 15-11", "retired"),  # "won" 15-11 but the game never ended
        ("2", "21-15 15-21", "retired"),  # stopped between games
        ("1", "11-5 11-7 11-3", "completed"),  # the 5x11 trial
        ("1", "11-9 5-11 11-8 9-11 15-14", "completed"),
        ("1", "11-5 11-7 6-3", "retired"),
        ("1", "21-15 21-18 21-10", None),  # three won games in best of three: contradicts
    ],
)
def test_status_comes_from_the_scores_never_from_the_winner_alone(
    winner: str, score: str, status: str | None
) -> None:
    games = tuple(tuple(map(int, g.split("-"))) for g in score.split())
    assert comp.status_of(int(winner), games) == status  # type: ignore[arg-type]


def test_tournament_resolves_by_name_and_date_only_when_unique() -> None:
    from datetime import date

    assert INDEX.resolve("Synthetic  masters", date(2015, 5, 2))["id"] == 7004  # type: ignore[index]
    assert INDEX.resolve("Synthetic Masters", date(2016, 5, 2)) is None  # no edition then
    assert INDEX.resolve("Unknown Cup", date(2015, 5, 2)) is None


def test_normalize_doubles_qualification_and_id_suffix() -> None:
    m = comp.normalize(
        row(discipline="XD", round="Q Qual. R32", team1="Alex TESTER / Kim SAMPLE [9001]",
            team2="Sam EXAMPLE / Jo DEMO"),
        7001,
    )  # fmt: skip
    assert not isinstance(m, Rejection)
    assert m.event_name == "XD Qualification" and m.round == "Q Qual. R32"
    assert [p.source_key for p in m.sides[0]] == ["name:Alex TESTER", "bwf:9001"]
    assert m.sides[0][1].display_name == "Kim SAMPLE"  # the suffix is an id, not part of the name
    half = comp.normalize(row(discipline="MD", team1="Alex TESTER"), 7001)
    assert isinstance(half, Rejection) and half.kind == "incomplete_sides"
    assert isinstance(comp.normalize(row(score="21-x"), 7001), Rejection)


def test_the_match_key_ignores_the_score_and_side_order() -> None:
    a = comp.match_key(7001, row())
    assert a == comp.match_key(7001, row(score="21-10 21-10", team1="Sam EXAMPLE",
                                          team2="Alex TESTER", winner="2"))  # fmt: skip
    assert a != comp.match_key(7001, row(round="QF"))


@pytest.mark.db
def test_import_is_idempotent_dedupes_and_quarantines(session: Session) -> None:
    run = IngestRun(source_id=comp.SOURCE)
    session.add(run)
    session.flush()
    rows = [
        row(),
        row(),  # an identical repeat: stored once
        row(round="QF", team2="Jo DEMO", winner="2", score="21-15 18-21 19-21"),
        row(round="SF", team2="Kim SAMPLE", score="21-15 21-18 21-10"),  # irregular
        row(tournament="Unknown Cup"),  # no index entry
        row(round="F", team1="Alex TESTER", team2="Noa SYNTHETIC", score="21-15 21-18"),
        row(round="F", team1="Alex TESTER", team2="Noa SYNTHETIC", score="21-10 21-10"),
    ]
    counts = comp.ingest(session, run, rows, INDEX)
    assert counts["normalized"] == 2 and counts["duplicate_rows"] == 1
    assert counts["quarantined:irregular_score"] == 1
    assert counts["quarantined:unknown_tournament"] == 1
    assert counts["quarantined:key_collision"] == 2  # same key, different scores: neither kept
    assert session.scalar(select(func.count()).select_from(Match)) == 2
    assert (
        session.scalar(select(func.count()).select_from(IngestIssue)) == 3
    )  # collision: once per key
    t = session.scalars(select(Tournament).filter_by(source_id=comp.SOURCE)).one()
    assert t.name == "Synthetic Open 2015" and str(t.start_date) == "2015-03-03"

    run2 = IngestRun(source_id=comp.SOURCE)
    session.add(run2)
    session.flush()
    again = comp.ingest(session, run2, rows, INDEX)
    assert again["normalized"] == 0 and again["unchanged"] == 3
    assert session.scalar(select(func.count()).select_from(Match)) == 2


@pytest.mark.db
def test_players_are_dataset_scoped_and_never_linked_by_name(session: Session) -> None:
    # a federation player with the same name already exists in another source
    other = SourcePlayer(source_id="synthetic", source_key="m:1", display_name="Alex TESTER")
    session.add(other)
    session.flush()
    run = IngestRun(source_id=comp.SOURCE)
    session.add(run)
    session.flush()
    comp.ingest(session, run, [row()], INDEX)
    mine = session.scalars(
        select(SourcePlayer).filter_by(source_id=comp.SOURCE, display_name="Alex TESTER")
    ).one()
    assert mine.source_key == "name:Alex TESTER"
    link = session.get(PlayerLink, mine.id)
    assert link is not None
    sharing = select(func.count()).select_from(PlayerLink).filter_by(player_id=link.player_id)
    assert session.scalar(sharing) == 1  # its own canonical player: no name-based merge
