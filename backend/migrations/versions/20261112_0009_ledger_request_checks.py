"""ledger request checks

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 20:16:05.151338
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # autogenerate does not see CHECK constraints: written by hand
    op.create_check_constraint(
        "ck_request_ledger_requests_non_negative", "request_ledger", "requests >= 0"
    )
    op.create_check_constraint(
        "ck_request_event_requests_positive", "request_event", "requests > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_request_event_requests_positive", "request_event", type_="check")
    op.drop_constraint("ck_request_ledger_requests_non_negative", "request_ledger", type_="check")
