"""Badminton New Zealand portal source

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-13 14:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO source (id, name, homepage, attribution) VALUES ('tournamentsoftware_bnz', "
        "'Badminton New Zealand (Tournament Software)', 'https://bnz.tournamentsoftware.com', "
        "'Badminton New Zealand via Tournament Software') ON CONFLICT (id) DO NOTHING"
    )
    # tournaments found earlier and parked as unauthorised now belong to an importable portal
    op.execute(
        "UPDATE tournament_discovery SET owner_source = 'tournamentsoftware_bnz', status = 'new', "
        "note = NULL WHERE owner_host = 'bnz.tournamentsoftware.com' "
        "AND status = 'unauthorised_host'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tournament_discovery SET owner_source = NULL, status = 'unauthorised_host' "
        "WHERE owner_source = 'tournamentsoftware_bnz'"
    )
    op.execute("DELETE FROM source WHERE id = 'tournamentsoftware_bnz'")
