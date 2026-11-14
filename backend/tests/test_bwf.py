"""BWF results normalisation on synthetic payloads shaped like vue-tournament-matches.

No network; every name and id is invented."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.ingest import bwf
from scout.ingest.tournamentsoftware import Rejection
from scout.models import Game, IngestIssue, IngestRun, Match, RawRecord, SourcePlayer, Tournament

INDEX = {
    "id": 9001,
    "name": "Synthetic  International Challenge 2026",
    "start_date": "2026-03-03 00:00:00",
    "end_date": "2026-03-08 00:00:00",
    "location": "Testville, Exampleland",
    "category": "BWF International Challenge",
}
DAY = 1772668800  # 2026-03-05 00:00 UTC


def player(pid: int, name: str) -> dict[str, Any]:
    return {"id": pid, "name_display": name, "nationality": "XXX"}


def score(*points: int) -> str:
    return "".join(f"<span>{p}</span>" for p in points)


def match(
    mid: int,
    draw: str,
    a: list[Any],
    b: list[Any],
    g1: tuple[int, ...],
    g2: tuple[int, ...],
    winner: int | None = 1,
    rnd: str = "R16",
) -> dict[str, Any]:
    m: dict[str, Any] = {
        "id": mid,
        "draw_name": draw,
        "round_name": rnd,
        "winner": winner,
        "team1Score": score(*g1),
        "team2Score": score(*g2),
        "start_time": DAY,
    }
    for i, p in enumerate(a, 1):
        m[f"t1p{i}_detail"] = p
    for i, p in enumerate(b, 1):
        m[f"t2p{i}_detail"] = p
    return m


ALEX, SAM = player(101, "Alex TESTER"), player(102, "Sam EXAMPLE")
KIM, JO = player(103, "Kim SAMPLE"), player(104, "Jo DEMO")
SINGLES = match(1, "MS", [ALEX], [SAM], (21, 21), (15, 18))
DOUBLES = match(2, "XD", [ALEX, KIM], [SAM, JO], (21, 19, 21), (17, 21, 16), rnd="QF")
WALKOVER = match(3, "WS", [KIM], [JO], (), (), winner=2)
RETIRED = match(4, "MS - Qualification", [SAM], [ALEX], (21, 11), (18, 4), rnd="Q1")
UNPLAYED = match(5, "WD", [KIM, JO], [ALEX, SAM], (), (), winner=None)


def payload(*by_time: dict[str, Any], by_court: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"results": {"by_time": {"time_group": list(by_time)}, "by_court": by_court or {}}}


def test_flatten_reads_both_groupings_and_dedupes_on_match_id() -> None:
    data = payload(SINGLES, DOUBLES, by_court={"Court 1": {"a": SINGLES, "b": WALKOVER}, "x": 7})
    assert [m["id"] for m in bwf.flatten(data)] == [1, 2, 3]
    assert bwf.flatten({"results": []}) == [] and bwf.flatten({}) == []


@pytest.mark.parametrize(
    ("draw", "expected"),
    [("MS", ("MS", False)), ("XD - Qualification", ("XD", True)), ("md", ("MD", False)),
     ("Team", (None, False)), (None, (None, False)), ("  ", (None, False))],
)  # fmt: skip
def test_discipline(draw: str | None, expected: tuple[str | None, bool]) -> None:
    assert bwf.discipline(draw) == expected


def test_scores_and_statuses_follow_the_laws_of_badminton() -> None:
    assert bwf.games(score(21, 19), score(17, 21)) == ((21, 17), (19, 21))
    assert bwf.games(score(21), score(17, 21)) is None  # malformed, never guessed
    assert bwf.status_of(1, ((21, 15), (21, 18))) == "completed"
    assert (
        bwf.status_of(1, ((29, 27),)) == "completed"
        and bwf.status_of(2, ((29, 30),)) == "completed"
    )
    assert bwf.status_of(1, ((21, 18), (11, 4))) == "retired"  # last game never finished
    assert bwf.status_of(2, ()) == "walkover"
    assert bwf.status_of(None, ((21, 15),)) == "not_played"


def test_normalize_keys_players_by_bwf_id_and_marks_qualification() -> None:
    t = bwf.BwfTournament.model_validate(INDEX)
    m = bwf.normalize(bwf.BwfMatch.model_validate(RETIRED), t)
    assert not isinstance(m, Rejection)
    assert m.status == "retired" and m.round == "Qualification Q1" and m.discipline == "MS"
    assert [r.source_key for r in m.sides[0]] == ["bwf:102"]
    d = bwf.normalize(bwf.BwfMatch.model_validate(DOUBLES), t)
    assert not isinstance(d, Rejection) and len(d.sides[0]) == 2 and len(d.sides[1]) == 2
    half = match(9, "MD", [ALEX], [SAM, JO], (21,), (10,))  # a doubles side with one player
    assert isinstance(bwf.normalize(bwf.BwfMatch.model_validate(half), t), Rejection)


@pytest.mark.db
def test_ingest_stores_with_provenance_and_is_idempotent(session: Session) -> None:
    run = IngestRun(source_id="bwf")
    session.add(run)
    session.flush()
    data = payload(SINGLES, DOUBLES, WALKOVER, RETIRED, UNPLAYED, by_court={"c": {"x": SINGLES}})
    counts = bwf.ingest_tournament(session, run, INDEX, data)
    assert counts["normalized"] == 5 and counts["new"] == 5
    assert counts["status:walkover"] == 1 and counts["status:retired"] == 1
    assert counts["status:not_played"] == 1
    t = session.scalars(select(Tournament).filter_by(source_id="bwf")).one()
    assert t.name == "Synthetic International Challenge 2026" and str(t.start_date) == "2026-03-03"
    singles = session.scalars(
        select(Match).join(RawRecord).where(RawRecord.source_record_key == "match|1")
    ).one()
    assert singles.winner_side == 1 and singles.status == "completed"
    assert [(g.side1_points, g.side2_points) for g in
            session.scalars(select(Game).filter_by(match_id=singles.id).order_by(Game.number))] == [
        (21, 15), (21, 18)]  # fmt: skip

    run2 = IngestRun(source_id="bwf")
    session.add(run2)
    session.flush()
    again = bwf.ingest_tournament(session, run2, INDEX, data)
    assert again["unchanged"] == 5 and again["normalized"] == 0
    assert session.scalar(select(func.count()).select_from(Match)) == 5
    # one BWF id is one source player, however many matches it appears in
    keys = session.scalars(select(SourcePlayer.source_key).filter_by(source_id="bwf")).all()
    assert sorted(keys) == ["bwf:101", "bwf:102", "bwf:103", "bwf:104"]


@pytest.mark.db
def test_a_corrected_score_is_a_new_revision_of_the_same_match(session: Session) -> None:
    run = IngestRun(source_id="bwf")
    session.add(run)
    session.flush()
    bwf.ingest_tournament(session, run, INDEX, payload(SINGLES))
    fixed = match(1, "MS", [ALEX], [SAM], (21, 21), (15, 19))
    run2 = IngestRun(source_id="bwf")
    session.add(run2)
    session.flush()
    counts = bwf.ingest_tournament(session, run2, INDEX, payload(fixed))
    assert counts["revised"] == 1
    assert session.scalar(select(func.count()).select_from(Match)) == 1
    m = session.scalars(select(Match)).one()
    games = session.scalars(select(Game).filter_by(match_id=m.id).order_by(Game.number))
    assert [g.side2_points for g in games] == [15, 19]


@pytest.mark.db
def test_namesakes_with_different_bwf_ids_stay_two_players(session: Session) -> None:
    run = IngestRun(source_id="bwf")
    session.add(run)
    session.flush()
    twin = player(999, "Alex TESTER")
    bwf.ingest_tournament(
        session, run, INDEX, payload(SINGLES, match(6, "MS", [twin], [KIM], (21, 21), (3, 4)))
    )
    names = session.scalars(select(SourcePlayer).filter_by(display_name="Alex TESTER")).all()
    assert len(names) == 2


@pytest.mark.db
def test_unusable_matches_become_issues_not_rows(session: Session) -> None:
    run = IngestRun(source_id="bwf")
    session.add(run)
    session.flush()
    bad = [
        match(7, "Team", [ALEX], [SAM], (21,), (5,)),
        match(8, "MS", [ALEX], [SAM], (21, 21), (5,)),
    ]
    counts = bwf.ingest_tournament(session, run, INDEX, payload(*bad))
    assert counts["rejected:unknown_discipline"] == 1 and counts["rejected:malformed_score"] == 1
    assert session.scalar(select(func.count()).select_from(Match)) == 0
    assert session.scalar(select(func.count()).select_from(IngestIssue)) == 2
