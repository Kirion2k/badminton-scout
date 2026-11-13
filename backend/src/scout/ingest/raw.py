"""The ingest boundary: store a source payload as a revisioned raw record (ADR-0005)."""

import hashlib
import json
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.models import IngestRun, RawRecord, RawRecordRevision
from scout.sources import Use, require_permitted

Outcome = Literal["new", "revised", "unchanged"]


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_payload(
    session: Session, run: IngestRun, record_key: str, payload: dict[str, Any]
) -> Outcome:
    """Insert or revise one record. Same content again only moves `last_seen_run_id`."""
    require_permitted(run.source_id, Use.STORE)
    digest = content_hash(payload)
    record = session.scalar(
        select(RawRecord).filter_by(source_id=run.source_id, source_record_key=record_key)
    )
    is_new = record is None
    if record is None:
        record = RawRecord(source_id=run.source_id, source_record_key=record_key)
        session.add(record)
        session.flush()

    revision = session.scalar(
        select(RawRecordRevision).filter_by(raw_record_id=record.id, content_sha256=digest)
    )
    if revision is None:
        revision = RawRecordRevision(
            raw_record_id=record.id,
            content_sha256=digest,
            payload=payload,
            first_seen_run_id=run.id,
            last_seen_run_id=run.id,
        )
        session.add(revision)
        session.flush()
    else:
        revision.last_seen_run_id = run.id

    outcome: Outcome = (
        "new" if is_new else "unchanged" if record.current_revision_id == revision.id else "revised"
    )
    record.current_revision_id = revision.id
    session.flush()
    return outcome
