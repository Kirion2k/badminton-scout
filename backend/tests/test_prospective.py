"""Prospective forecasts against fixtures (ADR-0013, ADR-0014): issued before the cutoff,
immutable, scored only from a result verified by a second person. All data is synthetic."""

import dataclasses
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from scout import identity
from scout.budget import MemoryBudget
from scout.fixtures import store
from scout.fixtures.providers import (
    CURATED_COLUMNS,
    CuratedCsv,
    FixtureRow,
    Rejected,
    env_credential,
    parse_row,
)
from scout.fixtures.sync import pilot, sync
from scout.ingest.provider import ProviderError
from scout.models import (
    Fixture,
    ForecastEvent,
    IngestRun,
    IssuedPrediction,
    RatingCurrent,
    RatingModel,
    RatingRun,
    RatingSnapshot,
    SourcePlayer,
)
from scout.ratings import prospective
from tests.test_api_v1 import data, player_id  # noqa: F401  # pyright: ignore[reportUnusedImport]

pytestmark = pytest.mark.db
NOW = datetime.now(UTC)
SOON = NOW.date() + timedelta(days=10)
P1, P2, P3 = ("bwf-player:101", "First Synthetic"), ("bwf-player:102", "Second Synthetic"), (
    "bwf-player:103", "Third Synthetic")  # fmt: skip
START = datetime.combine(SOON, datetime.min.time(), ZoneInfo("Asia/Tokyo")) + timedelta(hours=12)
BASE = FixtureRow(
    key="SYN-2026-MS-R16-1", tournament_key="SYN-2026", tournament_name="Synthetic Open",
    discipline="MS", round="R16", scheduled_date=SOON,
    scheduled_start=START,
    timezone="Asia/Tokyo", status="scheduled", players=(P1, P2), winner_side=None, score=None,
    retrieved_at=NOW,
)  # fmt: skip


@dataclasses.dataclass
class Fake:
    """A provider for tests: returns what it is given, or fails like an unavailable one."""

    rows: Sequence[FixtureRow] = ()
    source_id: str = "bwf_curated"
    requests_per_fetch: int = 1
    error: str | None = None

    def fetch(self) -> tuple[list[FixtureRow], list[Rejected]]:
        if self.error:
            raise ProviderError(self.error)
        return list(self.rows), []


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


def put(
    session: Session, *rows: FixtureRow, by: str = "human:op1", issue: bool = True
) -> dict[str, object]:
    return sync(session, Fake(rows), entered_by=by, issue=issue)


def fixture(session: Session, key: str = BASE.key) -> Fixture:
    return session.scalars(select(Fixture).filter_by(source_key=key)).one()


def sp(session: Session, key: str) -> int:
    return session.scalars(
        select(SourcePlayer.id).filter_by(source_id="bwf_curated", source_key=key)
    ).one()


def link(session: Session, key: str, player: int) -> int:
    decision = identity.link_fixture_player(
        session, sp(session, key), player, "BWF profile", "human:op1"
    )
    return decision.id


@pytest.fixture
def ready(session: Session, ids: dict[str, int]) -> Fixture:
    """BASE stored, both players linked by a person, ratings served: eligible for a forecast."""
    served(session, {ids["alex"]: 40, ids["sam"]: 40})
    report = put(session, BASE)
    assert report["issued"] == 0 and report["refused"] == {"unresolved player": 1}
    link(session, P1[0], ids["alex"])
    link(session, P2[0], ids["sam"])
    return fixture(session)


def result(session: Session, status: str = "completed", winner: int | None = 1,
           by: str = "human:op2", **changes: object) -> Fixture:  # fmt: skip
    """A new revision with a result, entered by op1 and verified by `by`."""
    put(session, dataclasses.replace(BASE, status=status, winner_side=winner, **changes))
    f = fixture(session)
    store.verify(session, f.id, by)
    return f


def test_a_forecast_is_issued_once_before_the_start_and_never_changes(
    session: Session, ready: Fixture, ids: dict[str, int]
) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    assert 0.5 < p.p_a < 1 and (p.player_a, p.player_b) == (ids["alex"], ids["sam"])
    assert p.fixture_revision_id == ready.revision_id and p.issued_at < p.cutoff_at
    assert p.cutoff_at == START - timedelta(minutes=30)
    with pytest.raises(prospective.NotEligible, match="already covers"):
        prospective.issue_for_fixture(session, ready.id)
    for change in ({"p_a": 0.99}, {"player_b": ids["kim"]}, {"cutoff_at": NOW}):
        with pytest.raises(DBAPIError, match="never changed"), session.begin_nested():
            session.execute(update(IssuedPrediction).where(IssuedPrediction.id == p.id)
                            .values(**change))  # fmt: skip
    with pytest.raises(DBAPIError, match="never changed or deleted"), session.begin_nested():
        session.delete(p)
        session.flush()
    event = session.scalars(select(ForecastEvent)).first()
    assert event is not None and event.kind == "refused"
    with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
        session.execute(update(ForecastEvent).values(reason="edited"))


def test_no_forecast_after_the_cutoff(session: Session, ready: Fixture) -> None:
    soon = datetime.now(UTC) + timedelta(minutes=20)  # within 30 minutes of the start
    put(session, dataclasses.replace(BASE, scheduled_start=soon, scheduled_date=soon.date()))
    with pytest.raises(prospective.NotEligible, match="past the cutoff"):
        prospective.issue_for_fixture(session, ready.id)


def test_a_date_only_fixture_closes_at_local_midnight_even_far_east(
    session: Session, ready: Fixture
) -> None:
    # Kiritimati is UTC+14: its date can be a day ahead of UTC's, already in play
    assert store.cutoff(None, date(2026, 12, 1), "Pacific/Kiritimati") == datetime(
        2026, 11, 30, 10, tzinfo=UTC)  # fmt: skip
    local_today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()
    put(session, dataclasses.replace(BASE, scheduled_start=None, scheduled_date=local_today,
                                     timezone="Pacific/Kiritimati"), issue=False)  # fmt: skip
    with pytest.raises(prospective.NotEligible, match="past the cutoff"):
        prospective.issue_for_fixture(session, ready.id)
    put(
        session,
        dataclasses.replace(BASE, scheduled_start=None, timezone="Pacific/Kiritimati"),
        issue=False,
    )
    assert prospective.issue_for_fixture(session, ready.id).cutoff_at == datetime.combine(
        SOON, datetime.min.time(), ZoneInfo("Pacific/Kiritimati"))  # fmt: skip


def test_a_result_counts_only_once_verified_by_someone_else(
    session: Session, ready: Fixture
) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    put(session, dataclasses.replace(BASE, status="completed", winner_side=1, score="21-15 21-18"))
    assert prospective.outcome(session, p).kind == "pending"  # entered, not verified
    with pytest.raises(ValueError, match="someone other"):
        store.verify(session, ready.id, "human:op1")  # the person who entered it
    store.verify(session, ready.id, "human:op2")
    assert prospective.outcome(session, p) == prospective.Outcome("scored", "completed", True)
    report = prospective.score(session, boot=50)
    assert report["resolved"] == 1 and report["conditions"]["1_enough_resolved"] is False
    assert report == prospective.score(session, boot=50)  # reproducible from the database
    # a later correction needs verifying again
    put(session, dataclasses.replace(BASE, status="completed", winner_side=1, score="21-15 21-19"))
    assert prospective.outcome(session, p).kind == "pending"


def test_a_start_moved_before_the_forecast_voids_it(session: Session, ready: Fixture) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    early = p.issued_at - timedelta(hours=1)
    result(session, scheduled_start=early, scheduled_date=early.date())
    assert prospective.outcome(session, p) == prospective.Outcome(
        "void", "issued after the corrected start")  # fmt: skip
    assert prospective.reconcile(session) == 1 and prospective.reconcile(session) == 0


def test_a_later_start_or_postponement_keeps_the_forecast(session: Session, ready: Fixture) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    put(session, dataclasses.replace(BASE, status="postponed"))
    assert prospective.outcome(session, p).kind == "pending"
    later = START + timedelta(days=2)
    f = result(session, winner=2, scheduled_start=later, scheduled_date=later.date())
    assert f.scheduled_date == later.date()
    assert prospective.outcome(session, p) == prospective.Outcome("scored", "completed", False)


def test_a_replaced_player_voids_the_forecast(session: Session, ready: Fixture) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    result(session, players=(P1, P3))
    assert prospective.outcome(session, p) == prospective.Outcome(
        "void", "players changed after the forecast")  # fmt: skip


def test_an_undone_identity_link_voids_the_forecast(session: Session, ids: dict[str, int]) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 40})
    put(session, BASE)
    decision = link(session, P1[0], ids["alex"])
    link(session, P2[0], ids["sam"])
    p = prospective.issue_for_fixture(session, fixture(session).id)
    identity.undo(session, decision, "wrong person", "human:op2")
    result(session)
    assert prospective.outcome(session, p).reason == "players changed after the forecast"


@pytest.mark.parametrize("status", ["abandoned", "walkover", "retired", "cancelled"])
def test_irregular_endings_are_void(session: Session, ready: Fixture, status: str) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    result(session, status=status, winner=None if status in ("abandoned", "cancelled") else 1)
    assert prospective.outcome(session, p) == prospective.Outcome("void", status)
    assert prospective.score(session, boot=10)["void"] == {status: 1}


def test_a_changed_verified_result_is_a_reported_conflict(session: Session, ready: Fixture) -> None:
    p = prospective.issue_for_fixture(session, ready.id)
    result(session, winner=1)
    result(session, winner=2, by="human:op3")
    assert prospective.outcome(session, p).kind == "conflict"
    report = prospective.score(session, boot=10)
    assert report["conflict"] == 1 and report["resolved"] == 0


def test_a_fixture_listed_twice_gets_no_forecast(session: Session, ready: Fixture) -> None:
    put(session, dataclasses.replace(BASE, key="SYN-2026-MS-R16-1-again", players=(P2, P1)))
    again = fixture(session, "SYN-2026-MS-R16-1-again")
    assert again.duplicate_of == ready.id
    for f in (ready, again):
        with pytest.raises(prospective.NotEligible, match="listed twice"):
            prospective.issue_for_fixture(session, f.id)


def test_a_same_name_player_is_never_linked_automatically(
    session: Session, ids: dict[str, int]
) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 40})
    # the rated players' exact names, but no person has linked these BWF ids
    named = dataclasses.replace(BASE, players=(("bwf-player:201", "Alex TESTER"),
                                               ("bwf-player:202", "Sam EXAMPLE")))  # fmt: skip
    assert put(session, named)["refused"] == {"unresolved player": 1}
    with pytest.raises(ValueError, match="by a person"):
        identity.link_fixture_player(session, sp(session, "bwf-player:201"), ids["alex"], "x",
                                     "auto:name")  # fmt: skip


def test_ineligible_ratings_or_stale_data_get_no_forecast(
    session: Session, ready: Fixture, ids: dict[str, int]
) -> None:
    put(session, dataclasses.replace(BASE, retrieved_at=NOW - timedelta(hours=25)), issue=False)
    # the newer check stays: an older reading never makes the fixture stale again
    assert fixture(session).retrieved_at == NOW
    stale = dataclasses.replace(BASE, key="old-check", players=(P1, P3),
                                retrieved_at=NOW - timedelta(hours=25))  # fmt: skip
    put(session, stale)
    with pytest.raises(prospective.NotEligible, match="stale fixture data"):
        prospective.issue_for_fixture(session, fixture(session, "old-check").id)
    session.add(IngestRun(source_id="bwf_historical_compilation", status="succeeded",
                          finished_at=datetime.now(UTC) + timedelta(seconds=1)))  # fmt: skip
    session.flush()
    with pytest.raises(prospective.NotEligible, match="stale rating snapshot"):
        prospective.issue_for_fixture(session, ready.id)


def test_a_provisional_player_gets_no_forecast(session: Session, ids: dict[str, int]) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 4})
    put(session, BASE)
    link(session, P1[0], ids["alex"])
    link(session, P2[0], ids["sam"])
    with pytest.raises(prospective.NotEligible, match="fewer than 10"):
        prospective.issue_for_fixture(session, fixture(session).id)


def test_a_provider_outage_is_recorded_and_issues_nothing(session: Session) -> None:
    report = sync(session, Fake(error="timed out"), entered_by="human:op1")
    assert report["failure"] == {"class": "ProviderError", "detail": "timed out"}
    run = session.scalars(select(IngestRun).where(IngestRun.source_id == "bwf_curated")).one()
    assert run.status == "failed" and not session.scalars(select(Fixture)).first()
    # an automated provider spends its source's request budget, or fetches nothing
    spent = MemoryBudget(spent={"bwf": 300}, sleep=lambda _: None)
    assert "failure" in sync(session, Fake([BASE], source_id="bwf"), entered_by="x", budget=spent)
    assert "failure" in sync(session, Fake([BASE], source_id="bwf"), entered_by="x")


def test_only_evidence_sources_are_forecast_and_counted(
    session: Session, ids: dict[str, int]
) -> None:
    served(session, {ids["alex"]: 40, ids["sam"]: 40})
    report = sync(session, Fake([BASE], source_id="synthetic"), entered_by="x")
    assert report["refused"] == {"synthetic is not a fixture source forecasts are issued from": 1}
    assert pilot(session)["fixtures"] == 0


def test_credentials_come_only_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOUT_TEST_PROVIDER_TOKEN", raising=False)
    with pytest.raises(ProviderError, match="not set in the environment"):
        env_credential("SCOUT_TEST_PROVIDER_TOKEN")
    monkeypatch.setenv("SCOUT_TEST_PROVIDER_TOKEN", "synthetic-token")
    assert env_credential("SCOUT_TEST_PROVIDER_TOKEN") == "synthetic-token"


GOOD = {
    "fixture_key": "SYN-1", "tournament_key": "SYN", "tournament_name": "Synthetic Open",
    "discipline": "WS", "round": "QF", "scheduled_date": "2027-03-04", "scheduled_start": "14:30",
    "timezone": "Europe/Paris", "status": "scheduled", "player_a_bwf_id": "11",
    "player_a_name": "A Synthetic", "player_b_bwf_id": "12", "player_b_name": "B Synthetic",
    "winner": "", "score": "", "checked_at": "2027-03-03T09:00:00+00:00",
}  # fmt: skip


def test_curated_rows_are_parsed_strictly(tmp_path: Path) -> None:
    row = parse_row(GOOD)
    assert row.scheduled_start == datetime(2027, 3, 4, 13, 30, tzinfo=UTC)
    assert row.players[0] == ("bwf-player:11", "A Synthetic")
    for change, why in (
        ({"player_a_bwf_id": ""}, "BWF profile id"),  # a name alone never identifies a player
        ({"timezone": "Mars/Base"}, "unknown timezone"),
        ({"status": "completed"}, "needs a winner"),
        ({"winner": "A"}, "has no winner"),
        ({"checked_at": "2027-03-03T09:00:00"}, "UTC offset"),
        ({"discipline": "MD"}, "MS or WS"),
        ({"player_b_bwf_id": "11"}, "both sides"),
    ):
        with pytest.raises(ValueError, match=why):
            parse_row({**GOOD, **change})
    path = tmp_path / "fixtures.csv"
    lines = [",".join(CURATED_COLUMNS), ",".join(GOOD[c] for c in CURATED_COLUMNS),
             ",".join({**GOOD, "discipline": "XD"}[c] for c in CURATED_COLUMNS)]  # fmt: skip
    path.write_text("\n".join(lines) + "\n")
    rows, rejected = CuratedCsv(path).fetch()
    assert len(rows) == 1 and rejected == [Rejected(3, "discipline must be MS or WS")]
    with pytest.raises(ProviderError, match="unreadable"):
        CuratedCsv(tmp_path / "missing.csv").fetch()
    path.write_text("fixture_key\nSYN-1\n")
    with pytest.raises(ProviderError, match="missing columns"):
        CuratedCsv(path).fetch()
