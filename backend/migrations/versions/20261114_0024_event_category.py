"""event category

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-14 20:33:27.312600
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("event", sa.Column("category", sa.String(length=8), nullable=True))
    op.create_check_constraint("category_valid", "event", "category IN ('adult', 'junior', 'para')")


def downgrade() -> None:
    op.drop_constraint("category_valid", "event", type_="check")
    op.drop_column("event", "category")
