"""Fake runtime -> provider -> Tournament Software normalization -> PostgreSQL, synthetic data."""

from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.ingest.operations import OPERATIONS, TsMatchRow
from scout.ingest.provider import ApiAnythingProvider
from scout.ingest.tournamentsoftware import ingest_rows
from scout.models import (
    Event,
    Game,
    IdentityDecision,
    IngestIssue,
    IngestRun,
    Match,
    MatchSide,
    MatchSidePlayer,
    PlayerLink,
    RawRecordRevision,
    SourcePlayer,
    Tournament,
)

from .test_provider import FakeClient, ok
from .ts_fixtures import DOUBLES, ONE_GAME_TO_30, WALKOVER, row

pytestmark = pytest.mark.db
DAY = date(2026, 1, 5)
# the real TS operation and model, recorded under the synthetic source so it is labelled test data
TS = {
    "synthetic.ts": replace(
        OPERATIONS["tournamentsoftware_ba.matches_in_day"], source_id="synthetic"
    )
}


def ingest(session: Session, rows: list[dict[str, Any]]) -> Counter[str]:
    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    result = ApiAnythingProvider(FakeClient(ok(rows)), operations=TS, sleep=lambda _: None).fetch(
        "synthetic.ts", {"tournament": "x", "date": "y"}
    )
    items = [i for i in result.items if isinstance(i, TsMatchRow)]
    return ingest_rows(session, run, DAY, items, list(result.rows))


def count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


SAMPLE = [row(), DOUBLES, WALKOVER, ONE_GAME_TO_30]


def test_first_import_creates_domain_rows(session: Session) -> None:
    counts = ingest(session, SAMPLE)
    assert counts["new"] == 4 and counts["normalized"] == 4
    assert (count(session, Tournament), count(session, Event), count(session, Match)) == (1, 3, 4)
    assert count(session, MatchSide) == 8
    assert count(session, MatchSidePlayer) == 2 + 4 + 2 + 2
    assert count(session, Game) == 2 + 3 + 0 + 1
    # 2 singles players + 4 doubles players, each linked once with an audited decision
    assert count(session, SourcePlayer) == count(session, PlayerLink) == 6
    assert count(session, IdentityDecision) == 6
    statuses = Counter(session.scalars(select(Match.status)).all())
    assert statuses == {"completed": 3, "walkover": 1}


def test_reimport_is_idempotent(session: Session) -> None:
    ingest(session, SAMPLE)
    before = [count(session, m) for m in (Match, Game, SourcePlayer, RawRecordRevision)]
    counts = ingest(session, SAMPLE)
    assert counts["unchanged"] == 4 and counts["normalized"] == 0
    assert [count(session, m) for m in (Match, Game, SourcePlayer, RawRecordRevision)] == before


def test_corrected_score_revises_the_same_match(session: Session) -> None:
    ingest(session, SAMPLE)
    counts = ingest(session, [row(points=(21, 15, 21, 19)), DOUBLES, WALKOVER, ONE_GAME_TO_30])
    assert counts["revised"] == 1 and counts["normalized"] == 1
    assert count(session, Match) == 4
    assert count(session, RawRecordRevision) == 5
    scores = session.scalars(select(Game.side2_points).order_by(Game.match_id, Game.number)).all()
    assert 19 in scores and 18 not in scores


def test_same_player_across_matches_is_one_identity(session: Session) -> None:
    ingest(session, [row(), row(round_="Round 2", side2=(("103", "Jo FIXTURE", "QA1003"),))])
    assert count(session, SourcePlayer) == 3  # QA1001 played twice


def test_same_name_different_member_is_not_merged(session: Session) -> None:
    twin = row(draw=8, side1=(("301", "Alex TESTER", "QA9999"),))
    ingest(session, [row(), twin])
    names = session.scalars(select(SourcePlayer).filter_by(display_name="Alex TESTER")).all()
    assert len(names) == 2
    assert len({session.get(PlayerLink, n.id).player_id for n in names}) == 2  # type: ignore[union-attr]


def test_key_collision_stores_neither_and_raises_an_issue(session: Session) -> None:
    # same draw, round and players but different content: two matches the key can't tell apart
    counts = ingest(session, [row(), row(points=(10, 21, 10, 21), winner=2)])
    assert counts["key_collision"] == 2
    assert count(session, Match) == 0
    assert session.scalars(select(IngestIssue.kind)).all() == ["key_collision"]


def test_identical_duplicate_rows_are_stored_once(session: Session) -> None:
    counts = ingest(session, [row(), row()])
    assert (counts["duplicate_rows"], counts["new"], count(session, Match)) == (1, 1, 1)


def test_rejected_row_is_kept_raw_and_reported(session: Session) -> None:
    counts = ingest(session, [row(points=(21, 15, 21)), DOUBLES])
    assert counts["rejected:malformed_score"] == 1 and counts["normalized"] == 1
    assert count(session, Match) == 1
    assert count(session, RawRecordRevision) == 2  # the bad row's evidence is still stored
    issue = session.scalars(select(IngestIssue)).one()
    assert issue.kind == "malformed_score" and issue.raw_record_id is not None


def test_revision_that_turns_invalid_removes_the_derived_match(session: Session) -> None:
    ingest(session, [row()])
    counts = ingest(session, [row(points=(21, 15, 21))])
    assert counts["revised"] == 1 and counts["rejected:malformed_score"] == 1
    assert count(session, Match) == 0 and count(session, Game) == 0


def test_unchanged_rejected_row_does_not_repeat_its_issue(session: Session) -> None:
    ingest(session, [row(points=(21, 15, 21))])
    ingest(session, [row(points=(21, 15, 21))])
    assert count(session, IngestIssue) == 1


def test_match_the_source_stops_listing_is_flagged_not_deleted(session: Session) -> None:
    ingest(session, [row(), DOUBLES])
    # a partner substitution changes the doubles key: the old record is no longer listed
    substituted = row(
        draw=9, event="XD Open",
        side1=(("201", "Kim SAMPLE", "QA2001"), ("299", "Sub STITUTE", "QA2099")),
        side2=(("203", "Pat DUMMY", "QA2003"), ("204", "Chris MOCK", "QA2004")),
        winner=2, points=(19, 21, 21, 17, 15, 21),
    )  # fmt: skip
    counts = ingest(session, [row(), substituted])
    assert counts["missing_from_source"] == 1
    assert count(session, Match) == 3  # nothing deleted: a human decides
    assert session.scalars(select(IngestIssue.kind)).all() == ["missing_from_source"]


def listings(session: Session, rows: list[dict[str, Any]]) -> Counter[str]:
    from scout.ingest.operations import TsTournament
    from scout.ingest.tournamentsoftware import ingest_tournaments

    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    items = [TsTournament.model_validate(r) for r in rows]
    return ingest_tournaments(session, run, items, rows)


def test_tournament_listing_sets_metadata(session: Session) -> None:
    from .ts_fixtures import TOURNAMENT, listing

    assert listings(session, [listing()])["tournaments_new"] == 1
    t = session.scalars(select(Tournament)).one()
    assert (t.source_key, t.name) == (TOURNAMENT, "Synthetic Open 2026")
    assert (t.organiser, t.location) == ("Synthetic Badminton Association", "Testville")
    assert (t.start_date, t.end_date) == (date(2026, 1, 5), date(2026, 1, 6))
    assert t.raw_record_id is not None


def test_single_day_tournament_and_renamed_listing(session: Session) -> None:
    from .ts_fixtures import listing

    listings(session, [listing(dates=("2026-02-01 00:00",))])
    renamed = listing(name="Synthetic Open 2026 (renamed)", dates=("2026-02-01 00:00",))
    counts = listings(session, [renamed])
    assert counts["tournaments_revised"] == 1
    t = session.scalars(select(Tournament)).one()
    assert t.name == "Synthetic Open 2026 (renamed)"
    assert t.start_date == t.end_date == date(2026, 2, 1)


def test_listing_then_matches_share_one_tournament(session: Session) -> None:
    from .ts_fixtures import listing

    listings(session, [listing()])
    ingest(session, [row()])
    assert count(session, Tournament) == 1


def test_renormalize_reapplies_rules_to_unchanged_records(session: Session) -> None:
    from scout.ingest.tournamentsoftware import ingest_rows

    ingest(session, [row()])
    match = session.scalars(select(Match)).one()
    match.status = "not_played"  # stand-in for a row normalized under an older rule
    session.flush()
    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    p = ApiAnythingProvider(FakeClient(ok([row()])), operations=TS, sleep=lambda _: None)
    result = p.fetch("synthetic.ts", {"tournament": "x", "date": "y"})
    items = [i for i in result.items if isinstance(i, TsMatchRow)]
    counts = ingest_rows(session, run, DAY, items, list(result.rows), renormalize=True)
    assert (counts["unchanged"], counts["normalized"]) == (1, 1)
    assert session.scalars(select(Match.status)).one() == "completed"
    assert count(session, Match) == 1


def test_a_changed_identifier_key_stops_ingest(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic import SecretStr

    from scout.config import get_settings
    from scout.ingest.tournamentsoftware import identifier_key

    monkeypatch.setattr(get_settings(), "identifier_key", SecretStr("first"))
    assert identifier_key(session) == "first"
    monkeypatch.setattr(get_settings(), "identifier_key", SecretStr("second"))
    with pytest.raises(RuntimeError, match="differs"):
        identifier_key(session)
