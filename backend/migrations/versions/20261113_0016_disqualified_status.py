"""match status: disqualified

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-13 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("status_valid", "match", type_="check")
    op.create_check_constraint(
        "status_valid",
        "match",
        "status IN ('completed', 'walkover', 'retired', 'disqualified', 'not_played')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM match WHERE status = 'disqualified'")
    op.drop_constraint("status_valid", "match", type_="check")
    op.create_check_constraint(
        "status_valid", "match", "status IN ('completed', 'walkover', 'retired', 'not_played')"
    )
