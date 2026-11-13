"""Provider -> validation -> rights -> ingest boundary -> PostgreSQL, on synthetic data."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.ingest.raw import content_hash, record_payload
from scout.models import IngestRun, RawRecord, RawRecordRevision
from scout.sources import SourceNotPermitted

from .test_provider import ROWS, SYNTHETIC, FakeClient, ok, provider

pytestmark = pytest.mark.db


def ingest(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    run = IngestRun(source_id="synthetic")
    session.add(run)
    session.flush()
    result = provider(FakeClient(ok(rows)))[0].fetch("synthetic.matches", {})
    return [
        record_payload(session, run, SYNTHETIC.record_key(item), row)
        for item, row in zip(result.items, result.rows, strict=True)
    ]


def revisions(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(RawRecordRevision)) or 0


def test_first_ingest_creates_records_and_revisions(session: Session) -> None:
    assert ingest(session, ROWS) == ["new", "new"]
    assert revisions(session) == 2


def test_reingesting_identical_data_writes_no_revisions(session: Session) -> None:
    ingest(session, ROWS)
    assert ingest(session, ROWS) == ["unchanged", "unchanged"]
    assert revisions(session) == 2


def test_corrected_result_is_a_revision_of_the_same_record(session: Session) -> None:
    ingest(session, ROWS)
    corrected = [ROWS[0], {**ROWS[1], "winner": 1}]
    assert ingest(session, corrected) == ["unchanged", "revised"]
    assert revisions(session) == 3
    record = session.scalars(select(RawRecord).filter_by(source_record_key="m2")).one()
    current = session.get(RawRecordRevision, record.current_revision_id)
    assert current is not None and current.payload["winner"] == 1


def test_reverting_to_earlier_content_reuses_that_revision(session: Session) -> None:
    ingest(session, ROWS)
    ingest(session, [ROWS[0], {**ROWS[1], "winner": 1}])
    assert ingest(session, ROWS) == ["unchanged", "revised"]
    assert revisions(session) == 3


def test_source_without_store_grant_cannot_be_ingested(session: Session) -> None:
    run = IngestRun(source_id="hacker_news_smoke")  # LOCAL_RESEARCH only
    with pytest.raises(SourceNotPermitted, match="store"):
        record_payload(session, run, "1", {"title": "x"})
    assert session.scalar(select(func.count()).select_from(RawRecord)) == 0


def test_raw_payload_is_the_source_row_including_unknown_fields(session: Session) -> None:
    ingest(session, [{**ROWS[0], "court": 3}])
    revision = session.scalars(select(RawRecordRevision)).one()
    assert revision.payload == {**ROWS[0], "court": 3}  # dates stay JSON, new fields kept


def test_content_hash_ignores_key_order() -> None:
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
