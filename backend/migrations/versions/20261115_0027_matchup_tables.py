"""current BWF ratings and immutable issued predictions (ADR-0013)

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-15 01:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A forecast is evidence only if nobody can change it after the fact: no deletes, no edits to
# what was forecast, and the result set once (from NULL) and never again.
GUARD = """
create function issued_prediction_guard() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'issued predictions are never deleted (ADR-0013)';
    end if;
    if (new.issued_at, new.scheduled_on, new.match_ref, new.discipline, new.player_a,
        new.player_b, new.p_a, new.config_hash, new.calibration_hash, new.run_id,
        new.snapshot_id, new.snapshot_hash)
       is distinct from
       (old.issued_at, old.scheduled_on, old.match_ref, old.discipline, old.player_a,
        old.player_b, old.p_a, old.config_hash, old.calibration_hash, old.run_id,
        old.snapshot_id, old.snapshot_hash) then
        raise exception 'an issued prediction cannot be changed (ADR-0013)';
    end if;
    if old.a_won is not null and (new.a_won, new.resolved_at, new.resolved_match_id,
        new.verified_by) is distinct from (old.a_won, old.resolved_at, old.resolved_match_id,
        old.verified_by) then
        raise exception 'a resolved prediction cannot be changed (ADR-0013)';
    end if;
    return new;
end $$;
create trigger issued_prediction_immutable before update or delete on issued_prediction
for each row execute function issued_prediction_guard();
"""


def upgrade() -> None:
    op.create_table(
        "rating_current",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("pool", sa.Text(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Double[float](), nullable=False),
        sa.Column("rd", sa.Double[float](), nullable=True),
        sa.Column("vol", sa.Double[float](), nullable=True),
        sa.Column("played", sa.Integer(), nullable=False),
        sa.Column("last_played", sa.Date(), nullable=False),
        sa.Column("component", sa.Integer(), nullable=False),
        sa.Column("identity_flagged", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["rating_run.id"], ondelete="CASCADE",
                                name=op.f("fk_rating_current_run_id_rating_run")),
        sa.PrimaryKeyConstraint("run_id", "pool", "player_id", name=op.f("pk_rating_current")),
    )  # fmt: skip
    op.create_table(
        "issued_prediction",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("scheduled_on", sa.Date(), nullable=False),
        sa.Column("match_ref", sa.Text(), nullable=False),
        sa.Column("discipline", sa.String(length=2), nullable=False),
        sa.Column("player_a", sa.BigInteger(), nullable=False),
        sa.Column("player_b", sa.BigInteger(), nullable=False),
        sa.Column("p_a", sa.Double[float](), nullable=False),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("calibration_hash", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("a_won", sa.Boolean(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_match_id", sa.BigInteger(), nullable=True),
        sa.Column("verified_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["rating_run.id"],
                                name=op.f("fk_issued_prediction_run_id_rating_run")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["rating_snapshot.id"],
                                name=op.f("fk_issued_prediction_snapshot_id_rating_snapshot")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_issued_prediction")),
    )  # fmt: skip
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("drop trigger issued_prediction_immutable on issued_prediction")
    op.execute("drop function issued_prediction_guard()")
    op.drop_table("issued_prediction")
    op.drop_table("rating_current")
