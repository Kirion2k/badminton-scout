"""identity candidates: deferred status and a note

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-13 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("identity_candidate", sa.Column("note", sa.Text(), nullable=True))
    op.drop_constraint("status_valid", "identity_candidate", type_="check")
    op.create_check_constraint(
        "status_valid",
        "identity_candidate",
        "status IN ('open', 'accepted', 'rejected', 'deferred')",
    )


def downgrade() -> None:
    op.execute("UPDATE identity_candidate SET status = 'open' WHERE status = 'deferred'")
    op.drop_constraint("status_valid", "identity_candidate", type_="check")
    op.create_check_constraint(
        "status_valid", "identity_candidate", "status IN ('open', 'accepted', 'rejected')"
    )
    op.drop_column("identity_candidate", "note")
