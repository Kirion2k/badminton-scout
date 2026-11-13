"""strip seeding markers from names

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12 21:01:44.839232
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # display names are derived: the raw revisions keep the seeded original as received
    op.execute(
        r"UPDATE source_player SET display_name = "
        r"regexp_replace(display_name, '\s*\[[0-9]+(/[0-9]+)?\]$', '') "
        r"WHERE display_name ~ '\[[0-9]+(/[0-9]+)?\]$'"
    )
    op.execute(
        r"UPDATE player SET display_name = "
        r"regexp_replace(display_name, '\s*\[[0-9]+(/[0-9]+)?\]$', '') "
        r"WHERE display_name ~ '\[[0-9]+(/[0-9]+)?\]$'"
    )


def downgrade() -> None:
    pass  # not reversible from here; re-run ingestion with --renormalize to restore originals
