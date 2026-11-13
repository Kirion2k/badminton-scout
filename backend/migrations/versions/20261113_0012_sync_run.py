"""scheduled sync runs

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-13 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "counts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'incomplete', 'failed', 'skipped')",
            name=op.f("ck_sync_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["source.id"], name=op.f("fk_sync_run_source_id_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_run")),
    )
    op.create_index(op.f("ix_sync_run_source_id"), "sync_run", ["source_id"])
    op.create_index(op.f("ix_sync_run_started_at"), "sync_run", ["started_at"])


def downgrade() -> None:
    op.drop_table("sync_run")
