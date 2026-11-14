"""rating_point keyed by pool

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-15 00:00:00

Review finding: one player's history merged two pools (a junior also in the adult pool). The
table is derived and is rebuilt by `scout ratings evaluate`, so existing points are dropped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("delete from rating_point")
    op.add_column("rating_point", sa.Column("pool", sa.Text(), nullable=False))
    op.drop_constraint("pk_rating_point", "rating_point", type_="primary")
    op.create_primary_key("pk_rating_point", "rating_point", ["run_id", "pool", "player_id", "day"])


def downgrade() -> None:
    op.execute("delete from rating_point")
    op.drop_constraint("pk_rating_point", "rating_point", type_="primary")
    op.create_primary_key("pk_rating_point", "rating_point", ["run_id", "player_id", "day"])
    op.drop_column("rating_point", "pool")
