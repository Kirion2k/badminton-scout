"""Precomputed coverage counts (the coverage_summary view, migration 0025).

Counting every match and player for /v1/coverage took seconds at 400k matches. The view holds
the counts; anything that changes matches, events or identities refreshes it, and the endpoint
says when the counts were computed.
"""

import logging

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def refresh(db: Session | Connection, *, concurrently: bool = True) -> None:
    """Recount. CONCURRENTLY keeps the view readable meanwhile (needs it populated, it is)."""
    db.execute(
        text(f"refresh materialized view {'concurrently ' if concurrently else ''}coverage_summary")
    )


def refresh_quietly(db: Session) -> None:
    """For the end of a job: a failed recount must never fail the job that changed the data."""
    try:
        refresh(db)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("coverage summary refresh failed; counts stay as they were")
