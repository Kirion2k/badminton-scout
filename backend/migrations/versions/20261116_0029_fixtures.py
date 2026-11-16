"""fixtures, forecasts issued against them, and the forecast audit trail (ADR-0014)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-16 01:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = "bwf_curated"
STATUSES = ("scheduled", "postponed", "live", "completed", "walkover", "retired", "abandoned",
            "cancelled")  # fmt: skip

# Outcomes now come from the fixture, so a forecast row never changes at all.
GUARD = """
create or replace function issued_prediction_guard() returns trigger language plpgsql as $$
begin
    raise exception 'an issued prediction is never changed or deleted (ADR-0014)';
end $$;
create trigger issued_prediction_immutable before update or delete on issued_prediction
for each row execute function issued_prediction_guard();
create function forecast_event_guard() returns trigger language plpgsql as $$
begin
    raise exception 'forecast events are append-only (ADR-0014)';
end $$;
create trigger forecast_event_append_only before update or delete on forecast_event
for each row execute function forecast_event_guard();
"""

# 0027's guard, restored on downgrade (a copy: migrations never import each other)
M81_GUARD = """
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
    op.execute(
        sa.text(
            "INSERT INTO source (id, name, homepage, attribution) VALUES (:id, :name, :home, "
            ":attribution) ON CONFLICT (id) DO NOTHING"
        ).bindparams(
            id=SOURCE,
            name="BWF fixtures and results, entered by hand",
            home="https://bwfbadminton.com",
            attribution="Fixtures and results of the Badminton World Federation, entered by hand "
            "from bwfbadminton.com",
        )
    )
    op.create_table(
        "fixture",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("tournament_key", sa.Text(), nullable=False),
        sa.Column("tournament_name", sa.Text(), nullable=False),
        sa.Column("discipline", sa.String(length=2), nullable=False),
        sa.Column("round", sa.Text(), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("side_a_player_id", sa.BigInteger(), nullable=False),
        sa.Column("side_b_player_id", sa.BigInteger(), nullable=False),
        sa.Column("winner_side", sa.SmallInteger(), nullable=True),
        sa.Column("score", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("raw_record_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_id", sa.BigInteger(), nullable=False),
        sa.Column("result_entered_by", sa.Text(), nullable=True),
        sa.Column("result_verified_by", sa.Text(), nullable=True),
        sa.Column("result_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_verified_revision_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("discipline IN ('MS', 'WS')", name=op.f("ck_fixture_discipline_valid")),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f("ck_fixture_status_valid")),
        sa.CheckConstraint("winner_side IN (1, 2)", name=op.f("ck_fixture_winner_valid")),
        sa.CheckConstraint("side_a_player_id <> side_b_player_id", name=op.f("ck_fixture_two_players")),
        sa.CheckConstraint("result_verified_by <> result_entered_by", name=op.f("ck_fixture_four_eyes")),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], name=op.f("fk_fixture_source_id_source")),
        sa.ForeignKeyConstraint(["side_a_player_id"], ["source_player.id"], name=op.f("fk_fixture_side_a_player_id_source_player")),
        sa.ForeignKeyConstraint(["side_b_player_id"], ["source_player.id"], name=op.f("fk_fixture_side_b_player_id_source_player")),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_record.id"], name=op.f("fk_fixture_raw_record_id_raw_record")),
        sa.ForeignKeyConstraint(["revision_id"], ["raw_record_revision.id"], name=op.f("fk_fixture_revision_id_raw_record_revision")),
        sa.ForeignKeyConstraint(["result_verified_revision_id"], ["raw_record_revision.id"], name=op.f("fk_fixture_result_verified_revision_id_raw_record_revision")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixture")),
        sa.UniqueConstraint("source_id", "source_key", name=op.f("uq_fixture_source_id_source_key")),
    )  # fmt: skip
    op.execute("drop trigger issued_prediction_immutable on issued_prediction")
    op.execute("drop function issued_prediction_guard()")
    for column in ("a_won", "resolved_at", "resolved_match_id", "verified_by"):
        op.drop_column("issued_prediction", column)
    # not null without defaults: fails if any M8.1 forecast exists, rather than inventing a fixture
    op.add_column("issued_prediction", sa.Column("fixture_id", sa.BigInteger(), nullable=False))
    op.add_column(
        "issued_prediction", sa.Column("fixture_revision_id", sa.BigInteger(), nullable=False)
    )
    op.add_column(
        "issued_prediction", sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False)
    )
    op.create_foreign_key(
        op.f("fk_issued_prediction_fixture_id_fixture"),
        "issued_prediction",
        "fixture",
        ["fixture_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_issued_prediction_fixture_revision_id_raw_record_revision"),
        "issued_prediction",
        "raw_record_revision",
        ["fixture_revision_id"],
        ["id"],
    )
    op.create_unique_constraint(op.f("uq_issued_prediction_fixture_id"), "issued_prediction",
                                ["fixture_id"])  # fmt: skip
    op.create_table(
        "forecast_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_revision_id", sa.BigInteger(), nullable=False),
        sa.Column("prediction_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("kind IN ('void', 'conflict', 'refused')", name=op.f("ck_forecast_event_kind_valid")),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixture.id"], name=op.f("fk_forecast_event_fixture_id_fixture")),
        sa.ForeignKeyConstraint(["fixture_revision_id"], ["raw_record_revision.id"], name=op.f("fk_forecast_event_fixture_revision_id_raw_record_revision")),
        sa.ForeignKeyConstraint(["prediction_id"], ["issued_prediction.id"], name=op.f("fk_forecast_event_prediction_id_issued_prediction")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecast_event")),
    )  # fmt: skip
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("drop trigger forecast_event_append_only on forecast_event")
    op.execute("drop function forecast_event_guard()")
    op.drop_table("forecast_event")
    op.execute("drop trigger issued_prediction_immutable on issued_prediction")
    op.execute("drop function issued_prediction_guard()")
    # fails if fixture-based forecasts exist: they cannot be expressed in the old shape
    op.drop_constraint(op.f("uq_issued_prediction_fixture_id"), "issued_prediction")
    for column in ("cutoff_at", "fixture_revision_id", "fixture_id"):
        op.drop_column("issued_prediction", column)
    op.add_column("issued_prediction", sa.Column("a_won", sa.Boolean(), nullable=True))
    op.add_column(
        "issued_prediction", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "issued_prediction", sa.Column("resolved_match_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("issued_prediction", sa.Column("verified_by", sa.Text(), nullable=True))
    op.drop_table("fixture")
    # fails while records still reference the source (as 0022): the whole downgrade rolls back
    op.execute(sa.text("DELETE FROM source WHERE id = :id").bindparams(id=SOURCE))
    op.execute(M81_GUARD)
