import hashlib

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scout.models import IngestRun, RawRecord, RawRecordRevision, Source
from scout.sources import SOURCES

from .conftest import alembic_config

pytestmark = pytest.mark.db
TABLES = {"source", "ingest_run", "raw_record", "raw_record_revision"}


def sha(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def record_with_revision(session: Session, key: str, payload: str) -> RawRecord:
    run = IngestRun(source_id="synthetic")
    record = RawRecord(source_id="synthetic", source_record_key=key)
    session.add_all([run, record])
    session.flush()
    revision = RawRecordRevision(
        raw_record_id=record.id,
        content_sha256=sha(payload),
        payload={"p": payload},
        first_seen_run_id=run.id,
        last_seen_run_id=run.id,
    )
    session.add(revision)
    session.flush()
    record.current_revision_id = revision.id
    session.flush()
    return record


def test_migrations_round_trip_and_match_models(engine: Engine, test_db_url: str) -> None:
    cfg = alembic_config(test_db_url)
    command.downgrade(cfg, "base")
    assert TABLES.isdisjoint(inspect(engine).get_table_names())
    command.upgrade(cfg, "head")
    assert set(inspect(engine).get_table_names()) >= TABLES
    # raises on table, column, type, default, FK and unique drift. Alembic doesn't compare
    # CHECK constraints, which is why each one has its own test below.
    command.check(cfg)


def test_every_database_source_is_in_the_rights_registry(session: Session) -> None:
    assert set(session.scalars(select(Source.id))) <= set(SOURCES)


def test_correction_is_a_new_revision_of_the_same_record(session: Session) -> None:
    record = record_with_revision(session, "2026-01-01|Open|MS|F|a|b", "21-19 21-18")
    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    corrected = RawRecordRevision(
        raw_record_id=record.id,
        content_sha256=sha("21-19 21-17"),
        payload={"p": "21-19 21-17"},
        first_seen_run_id=run.id,
        last_seen_run_id=run.id,
    )
    session.add(corrected)
    session.flush()
    record.current_revision_id = corrected.id
    session.flush()
    revisions = session.scalars(select(RawRecordRevision).filter_by(raw_record_id=record.id)).all()
    assert len(revisions) == 2
    current = select(RawRecord.current_revision_id).where(RawRecord.id == record.id)
    assert session.scalar(current) == corrected.id


def test_record_key_is_unique_per_source(session: Session) -> None:
    session.add(RawRecord(source_id="synthetic", source_record_key="k"))
    session.flush()
    session.add(RawRecord(source_id="synthetic", source_record_key="k"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_same_content_cannot_be_two_revisions(session: Session) -> None:
    record = record_with_revision(session, "k", "x")
    run_id = session.scalars(select(IngestRun.id)).first()
    session.add(
        RawRecordRevision(
            raw_record_id=record.id,
            content_sha256=sha("x"),
            payload={"p": "x"},
            first_seen_run_id=run_id,
            last_seen_run_id=run_id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_current_revision_must_belong_to_the_record(session: Session) -> None:
    a = record_with_revision(session, "a", "x")
    b = record_with_revision(session, "b", "y")
    a.current_revision_id = b.current_revision_id
    with pytest.raises(IntegrityError):
        session.flush()


def test_revision_hash_must_be_sha256_hex(session: Session) -> None:
    record = record_with_revision(session, "k", "x")
    run_id = session.scalars(select(IngestRun.id)).first()
    session.add(
        RawRecordRevision(
            raw_record_id=record.id,
            content_sha256="not-a-hash",
            payload={},
            first_seen_run_id=run_id,
            last_seen_run_id=run_id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_ingest_run_status_is_constrained(session: Session) -> None:
    session.add(IngestRun(source_id="synthetic", status="done"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_records_need_a_known_source(session: Session) -> None:
    session.add(RawRecord(source_id="bwf_match_data", source_record_key="k"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_every_registry_source_has_a_database_row(session: Session) -> None:
    # the request ledger and ingest runs reference source.id: a missing row fails at runtime
    assert set(SOURCES) <= set(session.scalars(select(Source.id)))
