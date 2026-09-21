"""Add public, descriptor-only storage for global shape-geometry v2 profiles.

Revision ID: 0115_shape_geometry_v2_global_library
Revises: 0114_v7_semi_automatic_activation_gate
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0115_shape_geometry_v2_global_library"
down_revision: str | Sequence[str] | None = "0114_v7_semi_automatic_activation_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROFILE_TABLE = "global_geometry_profile_versions"
_EVIDENCE_TABLE = "global_geometry_evidence_samples"
_RECEIPT_TABLE = "global_geometry_profile_write_receipts"
_IMMUTABLE_FUNCTION = "reject_global_geometry_library_mutation"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.create_table(
        _PROFILE_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "profile_number",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("geometry_family", sa.String(length=64), nullable=False),
        sa.Column("page_board_rows", sa.SmallInteger(), nullable=False),
        sa.Column("page_board_columns", sa.SmallInteger(), nullable=False),
        sa.Column("board_cell_rows", sa.SmallInteger(), nullable=False),
        sa.Column("board_cell_columns", sa.SmallInteger(), nullable=False),
        sa.Column("normalized_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("frame_appearance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'active', 'rejected', 'retired')",
            name="ck_global_geometry_profile_versions_status",
        ),
        sa.CheckConstraint(
            "page_board_rows = 3 AND page_board_columns = 3 "
            "AND board_cell_rows = 3 AND board_cell_columns = 5",
            name="ck_global_geometry_profile_versions_topology",
        ),
        sa.CheckConstraint(
            "profile_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_global_geometry_profile_versions_checksum",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(normalized_template) = 'object' "
            "AND jsonb_typeof(frame_appearance) = 'object' "
            "AND jsonb_typeof(evidence_summary) = 'object'",
            name="ck_global_geometry_profile_versions_json",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_number", name="uq_global_geometry_profile_versions_number"),
        sa.UniqueConstraint(
            "geometry_family",
            "profile_checksum_sha256",
            name="uq_global_geometry_profile_versions_checksum",
        ),
        schema="public",
    )
    op.create_index(
        "uq_global_geometry_profile_versions_active_scope",
        _PROFILE_TABLE,
        [
            "geometry_family",
            "page_board_rows",
            "page_board_columns",
            "board_cell_rows",
            "board_cell_columns",
        ],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_global_geometry_profile_versions_family_number",
        _PROFILE_TABLE,
        ["geometry_family", "profile_number"],
        schema="public",
    )
    op.create_table(
        _EVIDENCE_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_number", sa.Integer(), nullable=False),
        sa.Column("source_game_ref", sa.String(length=64), nullable=False),
        sa.Column("evidence_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "evidence_number > 0 AND source_game_ref ~ '^[a-z0-9][a-z0-9_-]{1,63}$'",
            name="ck_global_geometry_evidence_samples_values",
        ),
        sa.CheckConstraint(
            "evidence_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_global_geometry_evidence_samples_checksum",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_payload) = 'object'",
            name="ck_global_geometry_evidence_samples_json",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            [f"public.{_PROFILE_TABLE}.id"],
            name="fk_global_geometry_evidence_samples_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "evidence_number",
            name="uq_global_geometry_evidence_samples_number",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "evidence_checksum_sha256",
            name="uq_global_geometry_evidence_samples_checksum",
        ),
        schema="public",
    )
    op.create_index(
        "ix_global_geometry_evidence_samples_profile_number",
        _EVIDENCE_TABLE,
        ["profile_id", "evidence_number"],
        schema="public",
    )
    op.create_table(
        _RECEIPT_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_global_geometry_profile_write_receipts_command",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            [f"public.{_PROFILE_TABLE}.id"],
            name="fk_global_geometry_profile_write_receipts_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_global_geometry_profile_write_receipts_idempotency",
        ),
        schema="public",
    )
    op.execute(
        f"""
        CREATE FUNCTION public.{_IMMUTABLE_FUNCTION}()
        RETURNS trigger AS $$
        BEGIN
          IF TG_TABLE_NAME = '{_PROFILE_TABLE}'
             AND TG_OP = 'UPDATE'
             AND OLD.status = 'candidate'
             AND NEW.status IN ('active', 'rejected')
             AND NEW.id IS NOT DISTINCT FROM OLD.id
             AND NEW.profile_number IS NOT DISTINCT FROM OLD.profile_number
             AND NEW.geometry_family IS NOT DISTINCT FROM OLD.geometry_family
             AND NEW.page_board_rows IS NOT DISTINCT FROM OLD.page_board_rows
             AND NEW.page_board_columns IS NOT DISTINCT FROM OLD.page_board_columns
             AND NEW.board_cell_rows IS NOT DISTINCT FROM OLD.board_cell_rows
             AND NEW.board_cell_columns IS NOT DISTINCT FROM OLD.board_cell_columns
             AND NEW.normalized_template IS NOT DISTINCT FROM OLD.normalized_template
             AND NEW.frame_appearance IS NOT DISTINCT FROM OLD.frame_appearance
             AND NEW.evidence_summary IS NOT DISTINCT FROM OLD.evidence_summary
             AND NEW.profile_checksum_sha256 IS NOT DISTINCT FROM OLD.profile_checksum_sha256
             AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at THEN
            RETURN NEW;
          END IF;
          IF TG_TABLE_NAME = '{_PROFILE_TABLE}'
             AND TG_OP = 'UPDATE'
             AND OLD.status = 'active'
             AND NEW.status = 'retired'
             AND NEW.id IS NOT DISTINCT FROM OLD.id
             AND NEW.profile_number IS NOT DISTINCT FROM OLD.profile_number
             AND NEW.geometry_family IS NOT DISTINCT FROM OLD.geometry_family
             AND NEW.page_board_rows IS NOT DISTINCT FROM OLD.page_board_rows
             AND NEW.page_board_columns IS NOT DISTINCT FROM OLD.page_board_columns
             AND NEW.board_cell_rows IS NOT DISTINCT FROM OLD.board_cell_rows
             AND NEW.board_cell_columns IS NOT DISTINCT FROM OLD.board_cell_columns
             AND NEW.normalized_template IS NOT DISTINCT FROM OLD.normalized_template
             AND NEW.frame_appearance IS NOT DISTINCT FROM OLD.frame_appearance
             AND NEW.evidence_summary IS NOT DISTINCT FROM OLD.evidence_summary
             AND NEW.profile_checksum_sha256 IS NOT DISTINCT FROM OLD.profile_checksum_sha256
             AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'GLOBAL_GEOMETRY_LIBRARY_APPEND_ONLY';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in (_PROFILE_TABLE, _EVIDENCE_TABLE, _RECEIPT_TABLE):
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
          IF EXISTS (SELECT 1 FROM public.{_PROFILE_TABLE})
             OR EXISTS (SELECT 1 FROM public.{_EVIDENCE_TABLE})
             OR EXISTS (SELECT 1 FROM public.{_RECEIPT_TABLE}) THEN
            RAISE EXCEPTION 'SHAPE_GEOMETRY_GLOBAL_LIBRARY_DOWNGRADE_HAS_DATA';
          END IF;
        END $$;
        """
    )
    for table in (_RECEIPT_TABLE, _EVIDENCE_TABLE, _PROFILE_TABLE):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON public.{table}")
    op.execute(f"DROP FUNCTION public.{_IMMUTABLE_FUNCTION}()")
    op.drop_table(_RECEIPT_TABLE, schema="public")
    op.drop_table(_EVIDENCE_TABLE, schema="public")
    op.drop_table(_PROFILE_TABLE, schema="public")
