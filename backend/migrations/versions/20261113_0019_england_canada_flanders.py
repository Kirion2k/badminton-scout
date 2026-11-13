"""sources: Badminton England, Badminton Canada, Badminton Vlaanderen

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-13 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PORTALS = {
    "england": ("be.tournamentsoftware.com", "Badminton England"),
    "canada": ("badmintoncanada.tournamentsoftware.com", "Badminton Canada"),
    "badvla": ("badvla.tournamentsoftware.com", "Badminton Vlaanderen (Belgium)"),
}


def upgrade() -> None:
    for key, (host, federation) in PORTALS.items():
        op.execute(
            sa.text(
                "INSERT INTO source (id, name, homepage, attribution) VALUES (:id, :name, :home, "
                ":attribution) ON CONFLICT (id) DO NOTHING"
            ).bindparams(
                id=f"tournamentsoftware_{key}",
                name=f"{federation} (Tournament Software)",
                home=f"https://{host}",
                attribution=f"{federation} via Tournament Software",
            )
        )


def downgrade() -> None:
    for key in PORTALS:
        op.execute(
            sa.text("DELETE FROM source WHERE id = :id").bindparams(id=f"tournamentsoftware_{key}")
        )
