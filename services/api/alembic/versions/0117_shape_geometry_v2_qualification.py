"""Add append-only qualification records for shared shape-geometry candidates.

Revision ID: 0117_shape_geometry_v2_qualification
Revises: 0116_game_shape_geometry_configuration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0117_shape_geometry_v2_qualification"
down_revision: str | Sequence[str] | None = "0116_game_shape_geometry_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROFILE_TABLE = "global_geometry_profile_versions"
_RESULT_TABLE = "global_geometry_profile_qualification_results"
_RECEIPT_TABLE = "global_geometry_profile_qualification_receipts"
_IMMUTABLE_FUNCTION = "reject_global_geometry_library_mutation"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.create_table(
        _RESULT_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_active_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qualification_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "outcome IN ('passed', 'rejected', 'not_evaluable')",
            name="ck_global_geometry_profile_qualification_results_outcome",
        ),
        sa.CheckConstraint(
            "qualification_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_global_geometry_profile_qualification_results_checksum",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array'",
            name="ck_global_geometry_profile_qualification_results_reasons",
        ),
        sa.CheckConstraint(
            "report_payload IS NULL OR jsonb_typeof(report_payload) = 'object'",
            name="ck_global_geometry_profile_qualification_results_report",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            [f"public.{_PROFILE_TABLE}.id"],
            name="fk_global_geom_qualification_result_profile",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_active_profile_id"],
            [f"public.{_PROFILE_TABLE}.id"],
            name="fk_global_geom_qualification_result_previous_active",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_index(
        "ix_global_geom_qualification_result_profile_created",
        _RESULT_TABLE,
        ["profile_id", "created_at"],
        schema="public",
    )
    op.create_table(
        _RECEIPT_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_global_geometry_profile_qualification_receipts_command",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            [f"public.{_RESULT_TABLE}.id"],
            name="fk_global_geom_qualification_receipt_result",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_global_geometry_profile_qualification_receipts_idempotency",
        ),
        schema="public",
    )
    for table in (_RESULT_TABLE, _RECEIPT_TABLE):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only "
            f"BEFORE UPDATE OR DELETE ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{_IMMUTABLE_FUNCTION}()"
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM public.{_RESULT_TABLE})
             OR EXISTS (SELECT 1 FROM public.{_RECEIPT_TABLE}) THEN
            RAISE EXCEPTION 'SHAPE_GEOMETRY_QUALIFICATION_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    for table in (_RECEIPT_TABLE, _RESULT_TABLE):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON public.{table}")
    op.drop_table(_RECEIPT_TABLE, schema="public")
    op.drop_index(
        "ix_global_geom_qualification_result_profile_created",
        table_name=_RESULT_TABLE,
        schema="public",
    )
    op.drop_table(_RESULT_TABLE, schema="public")
