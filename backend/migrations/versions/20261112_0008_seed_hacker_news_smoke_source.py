"""seed hacker news smoke source

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12 20:10:07.382242
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # every source in scout.sources needs a row: the request ledger references it
    op.execute(
        "INSERT INTO source (id, name, homepage, attribution) VALUES ('hacker_news_smoke', "
        "'Hacker News search (API Anything smoke test)', 'https://hn.algolia.com', "
        "'Hacker News via Algolia search') ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM request_event WHERE source_id = 'hacker_news_smoke'")
    op.execute("DELETE FROM request_ledger WHERE source_id = 'hacker_news_smoke'")
    op.execute("DELETE FROM source WHERE id = 'hacker_news_smoke'")
