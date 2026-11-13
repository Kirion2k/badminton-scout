"""match status: winner_only (a verified winner, no published score)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-13 22:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("status_valid", "match", type_="check")
    op.create_check_constraint(
        "status_valid",
        "match",
        "status IN ('completed', 'walkover', 'retired', 'disqualified', 'winner_only', "
        "'not_played')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM match WHERE status = 'winner_only'")
    op.drop_constraint("status_valid", "match", type_="check")
    op.create_check_constraint(
        "status_valid",
        "match",
        "status IN ('completed', 'walkover', 'retired', 'disqualified', 'not_played')",
    )
