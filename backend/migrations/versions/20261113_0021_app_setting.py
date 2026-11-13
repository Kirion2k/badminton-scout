"""app settings (identifier key fingerprint)

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-13 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_app_setting")),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
