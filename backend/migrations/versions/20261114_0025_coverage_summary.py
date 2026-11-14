"""coverage summary (materialized view)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-14 23:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Per source: what /v1/coverage counts. The row '*' holds distinct players over all sources.
# Refreshed by scout.summary.refresh after anything that changes matches, events or identities.
VIEW = """
create materialized view coverage_summary as
with games as (
    select t.source_id, t.id as tournament_id, m.played_on, e.redistributable
    from match m
    join event e on e.id = m.event_id
    join tournament t on t.id = e.tournament_id
), counts as (
    select source_id,
           count(*) as stored_matches,
           count(distinct tournament_id) filter (where redistributable) as public_tournaments,
           count(*) filter (where redistributable) as public_matches,
           min(played_on) filter (where redistributable) as first_played,
           max(played_on) filter (where redistributable) as last_played
    from games group by source_id
), players as (
    select coalesce(t.source_id, '*') as source_id, count(distinct pl.player_id) as public_players
    from match m
    join event e on e.id = m.event_id and e.redistributable
    join tournament t on t.id = e.tournament_id
    join match_side ms on ms.match_id = m.id
    join match_side_player msp on msp.match_side_id = ms.id
    join player_link pl on pl.source_player_id = msp.source_player_id
    group by rollup (t.source_id)
)
select coalesce(c.source_id, p.source_id) as source_id,
       coalesce(c.stored_matches, 0) as stored_matches,
       coalesce(c.public_tournaments, 0) as public_tournaments,
       coalesce(c.public_matches, 0) as public_matches,
       c.first_played, c.last_played,
       coalesce(p.public_players, 0) as public_players,
       now() as computed_at
from counts c full join players p on p.source_id = c.source_id
"""


def upgrade() -> None:
    op.execute(VIEW)
    # a unique index lets REFRESH ... CONCURRENTLY keep the view readable while it rebuilds
    op.execute("create unique index ux_coverage_summary_source on coverage_summary (source_id)")


def downgrade() -> None:
    op.execute("drop materialized view coverage_summary")
