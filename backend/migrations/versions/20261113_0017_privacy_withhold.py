"""player withholding for removal requests

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-13 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("player", sa.Column("withheld_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "privacy_action",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('withhold', 'restore')", name=op.f("ck_privacy_action_action_valid")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["player.id"], name=op.f("fk_privacy_action_player_id_player")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_privacy_action")),
    )
    op.create_index(op.f("ix_privacy_action_player_id"), "privacy_action", ["player_id"])


def downgrade() -> None:
    # dropping the flag would silently publish everyone withheld after a removal request
    if (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM player WHERE withheld_at IS NOT NULL"))
        .scalar()
    ):
        raise RuntimeError("players are withheld: restore them first (scout privacy restore)")
    op.drop_table("privacy_action")
    op.drop_column("player", "withheld_at")
