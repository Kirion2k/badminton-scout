"""federation portal sources (Scotland, Germany, Austria, Brazil)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-13 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# a copy, not an import: a migration must not change when the registry does
PORTALS = {
    "scotland": ("badmintonscotland.tournamentsoftware.com", "Badminton Scotland"),
    "dbv": ("dbv.turnier.de", "Deutscher Badminton-Verband (Germany)"),
    "obv": ("obv.tournamentsoftware.com", "Österreichischer Badmintonverband (Austria)"),
    "cbbd": ("cbbd.tournamentsoftware.com", "Confederação Brasileira de Badminton (Brazil)"),
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
