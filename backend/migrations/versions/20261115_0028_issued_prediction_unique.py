"""one forecast per match (review finding)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-15 03:00:00

Forecasts are immutable, so a duplicate could never be removed and would count twice towards
ADR-0013's 1,000. The same two players (in either order), discipline and day: one forecast.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "create unique index ux_issued_prediction_match on issued_prediction "
        "(discipline, least(player_a, player_b), greatest(player_a, player_b), scheduled_on)"
    )


def downgrade() -> None:
    op.execute("drop index ux_issued_prediction_match")
