"""Fixtures in the database (ADR-0014): revisioned, duplicate-checked, results verified by a
second person, and players resolved only through human identity decisions."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scout.fixtures.providers import FixtureRow
from scout.ingest.raw import record_payload
from scout.ingest.tournamentsoftware import PlayerRef, get_or_create_source_player
from scout.models import (
    Fixture,
    ForecastEvent,
    IngestRun,
    IssuedPrediction,
    Player,
    PlayerLink,
    RatingCurrent,
    RawRecord,
    RawRecordRevision,
)

CUTOFF_BEFORE_START = timedelta(minutes=30)
TERMINAL = frozenset({"completed", "walkover", "retired", "abandoned", "cancelled"})


def cutoff(start: datetime | None, day: date, zone: str) -> datetime:
    """The last moment a forecast may be issued: 30 minutes before a known start, else the start
    of the scheduled day in the fixture's own timezone (a day that has begun may be in play)."""
    if start is not None:
        return start - CUTOFF_BEFORE_START
    return datetime.combine(day, time(0), ZoneInfo(zone))


def fixture_cutoff(f: Fixture) -> datetime:
    return cutoff(f.scheduled_start, f.scheduled_date, f.timezone)


def upsert(session: Session, run: IngestRun, row: FixtureRow, entered_by: str) -> Fixture:
    """Store the provider's current statement of a fixture. A changed statement is a new
    revision, entered by `entered_by`, and needs verifying again."""
    record_payload(session, run, row.key, row.payload())
    record = session.scalars(
        select(RawRecord).filter_by(source_id=run.source_id, source_record_key=row.key)
    ).one()
    a, b = (get_or_create_source_player(session, run.source_id, PlayerRef(k, n))
            for k, n in row.players)  # fmt: skip
    f = session.scalar(select(Fixture).filter_by(source_id=run.source_id, source_key=row.key))
    if f is None or f.revision_id != record.current_revision_id:
        values = {
            "tournament_key": row.tournament_key, "tournament_name": row.tournament_name,
            "discipline": row.discipline, "round": row.round,
            "scheduled_start": row.scheduled_start, "scheduled_date": row.scheduled_date,
            "timezone": row.timezone, "status": row.status, "side_a_player_id": a.id,
            "side_b_player_id": b.id, "winner_side": row.winner_side, "score": row.score,
            "revision_id": record.current_revision_id, "result_entered_by": entered_by,
            # the last verified revision stays recorded, so a changed result is detectable
            "result_verified_by": None, "result_verified_at": None,
        }  # fmt: skip
        if f is None:
            f = Fixture(source_id=run.source_id, source_key=row.key, raw_record_id=record.id,
                        retrieved_at=row.retrieved_at, **values)  # fmt: skip
            session.add(f)
        else:
            for k, v in values.items():
                setattr(f, k, v)
    f.retrieved_at = max(f.retrieved_at, row.retrieved_at)
    session.flush()
    f.duplicate_of = session.scalar(
        select(func.min(Fixture.id)).where(
            Fixture.source_id == f.source_id, Fixture.id < f.id,
            Fixture.discipline == f.discipline, Fixture.scheduled_date == f.scheduled_date,
            or_((Fixture.side_a_player_id == a.id) & (Fixture.side_b_player_id == b.id),
                (Fixture.side_a_player_id == b.id) & (Fixture.side_b_player_id == a.id)),
        )
    )  # fmt: skip
    session.flush()
    return f


def verify(session: Session, fixture_id: int, by: str) -> Fixture:
    """A second person confirms the current revision's result. If an earlier verified result
    differs, the fixture is in conflict: excluded from scoring and reported (ADR-0014)."""
    f = session.get(Fixture, fixture_id, with_for_update=True)
    if f is None:
        raise ValueError(f"no fixture {fixture_id}")
    if f.status not in TERMINAL:
        raise ValueError(f"fixture {fixture_id} is {f.status}: there is no result to verify")
    if not by.strip() or by == f.result_entered_by:
        raise ValueError("a result is verified by someone other than the person who entered it")
    if f.result_verified_by is not None:
        raise ValueError(f"fixture {fixture_id} is already verified")
    earlier = f.result_verified_revision_id
    if earlier is not None and earlier != f.revision_id:
        was = session.get_one(RawRecordRevision, earlier)
        now = session.get_one(RawRecordRevision, f.revision_id)
        result = ("status", "winner_side")
        if [was.payload[k] for k in result] != [now.payload[k] for k in result]:
            prediction = session.scalar(
                select(IssuedPrediction.id).where(IssuedPrediction.fixture_id == f.id)
            )
            session.add(ForecastEvent(
                kind="conflict", fixture_id=f.id, fixture_revision_id=f.revision_id,
                prediction_id=prediction,
                reason=f"verified result changed from {was.payload['status']}/"
                       f"{was.payload['winner_side']} to {f.status}/{f.winner_side}",
            ))  # fmt: skip
    f.result_verified_by, f.result_verified_revision_id = by, f.revision_id
    f.result_verified_at = session.scalar(select(func.now()))
    session.flush()
    return f


def is_verified(f: Fixture) -> bool:
    return f.result_verified_by is not None and f.result_verified_revision_id == f.revision_id


def canonical(session: Session, player_id: int) -> int:
    """The player a (possibly merged) id belongs to now."""
    for _ in range(5):  # merge chains are one hop (ADR-0003); a few more never hurt
        merged = session.scalar(select(Player.merged_into_id).where(Player.id == player_id))
        if merged is None:
            break
        player_id = merged
    return player_id


def player_of(session: Session, source_player_id: int) -> int:
    linked = session.scalar(
        select(PlayerLink.player_id).where(PlayerLink.source_player_id == source_player_id)
    )
    if linked is None:
        raise ValueError(
            f"source player {source_player_id} is not linked"
        )  # never: linked on creation
    return canonical(session, linked)


def resolved(session: Session, source_player_id: int, run_id: int, discipline: str) -> int | None:
    """The rated BWF player a fixture player is, or None. Only a person's identity decision can
    attach a fixture player to a rated record (`scout identity link-fixture-player`)."""
    pid = player_of(session, source_player_id)
    rated = session.get(RatingCurrent, (run_id, f"bwf:{discipline}", pid))
    return pid if rated is not None else None
