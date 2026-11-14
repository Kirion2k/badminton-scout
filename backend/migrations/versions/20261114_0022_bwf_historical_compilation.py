"""source: bwf_historical_compilation (third-party compilation of BWF results, file import)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-14 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = "bwf_historical_compilation"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO source (id, name, homepage, attribution) VALUES (:id, :name, :home, "
            ":attribution) ON CONFLICT (id) DO NOTHING"
        ).bindparams(
            id=SOURCE,
            name="BWF results, historical compilation, 2007 to 2026",
            home="https://github.com/SahilMotyar/bwf-match-data",
            attribution="Results of the Badminton World Federation, compiled by Sahil Motyar "
            "(bwf-match-data)",
        )
    )


def downgrade() -> None:
    # fails while records still reference the source (foreign keys): nothing is orphaned
    op.execute(sa.text("DELETE FROM source WHERE id = :id").bindparams(id=SOURCE))
