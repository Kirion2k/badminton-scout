"""M0 persistence: sources, ingest runs and revisioned raw records (ADR-0005).

Badminton domain tables (M1B) follow below.
"""

import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # deterministic constraint names so migrations can reference them
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class Source(Base):
    """Descriptive metadata only. Rights live in scout.sources (ADR-0002)."""

    __tablename__ = "source"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class RawRecord(Base):
    """A record's identity in its source. The key never contains mutable fields like scores."""

    __tablename__ = "raw_record"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_key"),
        # the current revision must be one of this record's own revisions
        ForeignKeyConstraint(
            ["current_revision_id", "id"],
            ["raw_record_revision.id", "raw_record_revision.raw_record_id"],
            name="fk_raw_record_current_revision",
            use_alter=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    source_record_key: Mapped[str] = mapped_column(Text)
    current_revision_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RawRecordRevision(Base):
    """One distinct payload of a record. A correction adds a revision, never overwrites one."""

    __tablename__ = "raw_record_revision"
    __table_args__ = (
        UniqueConstraint("raw_record_id", "content_sha256"),
        UniqueConstraint("id", "raw_record_id"),  # target of raw_record's composite FK
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    raw_record_id: Mapped[int] = mapped_column(ForeignKey("raw_record.id"))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_run.id"))
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_run.id"))


# --- Badminton domain (M1B). Identity per ADR-0003, matches per ADR-0005. ---


class IngestIssue(Base):
    """A record that could not be normalized, or that collided with another (ADR-0005)."""

    __tablename__ = "ingest_issue"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingest_run.id"), index=True)
    raw_record_id: Mapped[int | None] = mapped_column(ForeignKey("raw_record.id"))
    kind: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class SourcePlayer(Base):
    """A player as one source identifies them. Never merged or rewritten (ADR-0003)."""

    __tablename__ = "source_player"
    __table_args__ = (UniqueConstraint("source_id", "source_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    source_key: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Player(Base):
    __tablename__ = "player"
    __table_args__ = (
        Index(
            "ix_player_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(Text)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("player.id"))
    # a removal request (ADR-0010 follow-up): no profile, no search, the name masked elsewhere
    withheld_at: Mapped[datetime | None]


class IdentityDecision(Base):
    """Append-only audit of every link, merge and split (ADR-0003)."""

    __tablename__ = "identity_decision"
    __table_args__ = (
        CheckConstraint("action IN ('link', 'merge', 'split', 'reject')", name="action_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    action: Mapped[str] = mapped_column(String(16))
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    reason: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PlayerLink(Base):
    __tablename__ = "player_link"

    source_player_id: Mapped[int] = mapped_column(ForeignKey("source_player.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("player.id"), index=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("identity_decision.id"))


class Tournament(Base):
    __tablename__ = "tournament"
    __table_args__ = (UniqueConstraint("source_id", "source_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    source_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    organiser: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    # the raw tournament-listing record the metadata came from, when we have one
    raw_record_id: Mapped[int | None] = mapped_column(ForeignKey("raw_record.id"))


class Event(Base):
    """One draw of a tournament, e.g. "MS C - Group A"."""

    __tablename__ = "event"
    __table_args__ = (
        UniqueConstraint("tournament_id", "source_key"),
        CheckConstraint("discipline IN ('MS', 'WS', 'MD', 'WD', 'XD')", name="discipline_valid"),
        CheckConstraint("category IN ('adult', 'junior', 'para')", name="category_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournament.id"))
    source_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    discipline: Mapped[str | None] = mapped_column(String(2))  # null when the name doesn't say
    # "adult", "junior" or "para" from the name and the tournament's codes (ingest/event_codes.py);
    # null until classified. Rating pools never mix them (ADR-0012).
    category: Mapped[str | None] = mapped_column(String(8))
    # ADR-0009: false (the default) keeps the event, its matches and players out of the API
    redistributable: Mapped[bool] = mapped_column(server_default="false", index=True)


class Match(Base):
    """Normalized from exactly one source record's current revision (ADR-0005)."""

    __tablename__ = "match"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'walkover', 'retired', 'disqualified', 'winner_only', "
            "'not_played')",
            name="status_valid",
        ),
        CheckConstraint("winner_side IN (1, 2)", name="winner_side_valid"),
        # the revision a match came from must be one of its own record's revisions
        ForeignKeyConstraint(
            ["normalized_from_revision_id", "raw_record_id"],
            ["raw_record_revision.id", "raw_record_revision.raw_record_id"],
            name="fk_match_own_revision",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    raw_record_id: Mapped[int] = mapped_column(ForeignKey("raw_record.id"), unique=True)
    normalized_from_revision_id: Mapped[int] = mapped_column(BigInteger)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    round: Mapped[str | None] = mapped_column(Text)
    played_on: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(16))
    winner_side: Mapped[int | None] = mapped_column(SmallInteger)
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    court: Mapped[str | None] = mapped_column(Text)


class MatchSide(Base):
    __tablename__ = "match_side"
    __table_args__ = (
        UniqueConstraint("match_id", "side"),
        CheckConstraint("side IN (1, 2)", name="side_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))
    side: Mapped[int] = mapped_column(SmallInteger)


class MatchSidePlayer(Base):
    __tablename__ = "match_side_player"

    match_side_id: Mapped[int] = mapped_column(
        ForeignKey("match_side.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    source_player_id: Mapped[int] = mapped_column(ForeignKey("source_player.id"), index=True)


class Game(Base):
    __tablename__ = "game"
    __table_args__ = (
        CheckConstraint("side1_points >= 0 AND side2_points >= 0", name="points_non_negative"),
    )

    match_id: Mapped[int] = mapped_column(
        ForeignKey("match.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    side1_points: Mapped[int] = mapped_column(SmallInteger)
    side2_points: Mapped[int] = mapped_column(SmallInteger)


class IdentityCandidate(Base):
    """A suggested link between two source players, waiting for a human (ADR-0003)."""

    __tablename__ = "identity_candidate"
    __table_args__ = (
        UniqueConstraint("source_player_a_id", "source_player_b_id"),
        CheckConstraint("source_player_a_id < source_player_b_id", name="ordered_pair"),
        CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'deferred')", name="status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_player_a_id: Mapped[int] = mapped_column(ForeignKey("source_player.id"))
    source_player_b_id: Mapped[int] = mapped_column(ForeignKey("source_player.id"))
    rule: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("identity_decision.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)  # why it is deferred (identity_auto)


class RequestLedger(Base):
    """Requests charged to a source per UTC day, shared by every process (ADR-0008 budget)."""

    __tablename__ = "request_ledger"
    __table_args__ = (CheckConstraint("requests >= 0", name="requests_non_negative"),)

    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    requests: Mapped[int] = mapped_column(server_default="0")
    # the latest slot handed out: the next request may go at last_slot + min_interval
    last_slot: Mapped[datetime] = mapped_column(server_default=func.now())


class RequestEvent(Base):
    """Append-only audit of every charge: who spent the budget, and why."""

    __tablename__ = "request_event"
    __table_args__ = (CheckConstraint("requests > 0", name="requests_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    requests: Mapped[int]
    purpose: Mapped[str] = mapped_column(Text)  # ingest, learning, verification, live_test, ...
    note: Mapped[str | None] = mapped_column(Text)


class TournamentDiscovery(Base):
    """Every tournament a source listed: where it is owned, and how far its import got.

    The import queue. Imported data lives in `tournament` under the *owning* source only, so a
    tournament seen on several portals is imported once.
    """

    __tablename__ = "tournament_discovery"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'not_finished', 'unauthorised_host', 'login_required', "
            "'no_matches', 'partial', 'complete', 'failed')",
            name="status_valid",
        ),
    )

    guid: Mapped[str] = mapped_column(Text, primary_key=True)  # lower-case tournament GUID
    discovered_via: Mapped[str] = mapped_column(ForeignKey("source.id"))
    name: Mapped[str | None] = mapped_column(Text)
    organiser: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    owner_host: Mapped[str | None] = mapped_column(Text)  # null until resolved
    owner_source: Mapped[str | None] = mapped_column(ForeignKey("source.id"))  # null: not ours
    status: Mapped[str] = mapped_column(String(24), server_default="new", index=True)
    days_done: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    note: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_attempt_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class SyncRun(Base):
    """One scheduled pass over one provider (`scout sync`): what it did and when the next is due."""

    __tablename__ = "sync_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'incomplete', 'failed', 'skipped')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None]
    discovered: Mapped[bool] = mapped_column(server_default="false")  # ran a listing search
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    note: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime | None]  # from the scheduler (--every); None = not scheduled
    backfilled_to: Mapped[date | None]  # oldest day this pass searched back to (www history)


class PrivacyAction(Base):
    """Audit trail of removal and correction requests acted on (`scout privacy withhold`)."""

    __tablename__ = "privacy_action"
    __table_args__ = (CheckConstraint("action IN ('withhold', 'restore')", name="action_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("player.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(server_default=func.now())


class AppSetting(Base):
    """Small facts the system must remember about itself (e.g. the identifier key fingerprint)."""

    __tablename__ = "app_setting"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# Ratings (ADR-0006, ADR-0012). Derived only: nothing here is a source of truth, and match data
# is never changed by them. A snapshot freezes the eligible matches (with the player ids of the
# time) so any run can be replayed exactly.


class RatingModel(Base):
    __tablename__ = "rating_model"
    __table_args__ = (UniqueConstraint("name", "config_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)  # "elo", "glicko2", "winrate", "constant"
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RatingSnapshot(Base):
    __tablename__ = "rating_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    family: Mapped[str] = mapped_column(Text)  # "bwf" or "fed"
    query_version: Mapped[int] = mapped_column(SmallInteger)
    content_hash: Mapped[str] = mapped_column(Text)
    # eligible matches per pool and exclusions by reason
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RatingSnapshotMatch(Base):
    __tablename__ = "rating_snapshot_match"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("rating_snapshot.id", ondelete="CASCADE"), primary_key=True
    )
    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(BigInteger)
    pool: Mapped[str] = mapped_column(Text)
    day: Mapped[date]
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    cluster: Mapped[int] = mapped_column(BigInteger)  # the tournament
    a: Mapped[int] = mapped_column(BigInteger)  # canonical player ids at snapshot time
    b: Mapped[int] = mapped_column(BigInteger)
    a_won: Mapped[bool]


class RatingRun(Base):
    __tablename__ = "rating_run"
    __table_args__ = (
        CheckConstraint("kind IN ('backtest', 'full', 'incremental')", name="kind_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("rating_model.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("rating_snapshot.id"))
    pool: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    splits: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    code_version: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    output_hash: Mapped[str | None] = mapped_column(Text)
    # an incremental run replays from this day on top of `base_run_id`
    from_day: Mapped[date | None]
    base_run_id: Mapped[int | None] = mapped_column(ForeignKey("rating_run.id"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class RatingPoint(Base):
    """A player's rating after their last batch of a day: retrospective, never a prediction."""

    __tablename__ = "rating_point"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("rating_run.id", ondelete="CASCADE"), primary_key=True
    )
    pool: Mapped[str] = mapped_column(Text, primary_key=True)
    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    rating: Mapped[float]
    rd: Mapped[float | None]
    vol: Mapped[float | None]
    played: Mapped[int]


class MatchPrediction(Base):
    """P(side a wins) from strictly earlier batches (ADR-0006): the only thing ever scored."""

    __tablename__ = "match_prediction"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("rating_run.id", ondelete="CASCADE"), primary_key=True
    )
    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    p: Mapped[float | None]
    y: Mapped[int] = mapped_column(SmallInteger)
    split: Mapped[str] = mapped_column(String(12))
    prior_a: Mapped[int]
    prior_b: Mapped[int]
    abstain: Mapped[str | None] = mapped_column(String(24))
