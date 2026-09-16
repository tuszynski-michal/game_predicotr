"""Add append-only pre-import geometry guard decisions.

Revision ID: 0096_preimport_geometry_guard_decisions
Revises: 0095_structured_lattice_v3_rollout
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0096_preimport_geometry_guard_decisions"
down_revision: str | Sequence[str] | None = "0095_structured_lattice_v3_rollout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recognized_boards",
        sa.Column(
            "completeness_status",
            sa.String(length=24),
            nullable=False,
            server_default="complete",
        ),
    )
    op.add_column(
        "recognized_boards",
        sa.Column(
            "unavailable_cell_indices",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_check_constraint(
        "ck_recognized_boards_completeness",
        "recognized_boards",
        "(completeness_status = 'complete' AND cardinality(unavailable_cell_indices) = 0) "
        "OR (completeness_status = 'pending_partial' "
        "AND cardinality(unavailable_cell_indices) BETWEEN 1 AND 14 "
        "AND unavailable_cell_indices <@ ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[])",
    )

    op.create_table(
        "image_import_geometry_guard_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("browser_selection_id", sa.Uuid(), nullable=False),
        sa.Column("guard_job_id", sa.Uuid(), nullable=False),
        sa.Column("guard_report_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("position_index", sa.SmallInteger(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.String(length=24), nullable=False),
        sa.Column("symbol_grid_quad", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "unavailable_cell_indices",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("decision_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "position_index BETWEEN 0 AND 8 AND sequence_number > 0 AND revision > 0",
            name="ck_image_import_guard_decisions_values",
        ),
        sa.CheckConstraint(
            "guard_report_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "decision_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_import_guard_decisions_checksums",
        ),
        sa.CheckConstraint(
            "length(btrim(source_relative_path)) > 0 "
            "AND source_relative_path !~ '(^/|(^|/)\\.\\.(/|$)|\\\\)' "
            "AND length(btrim(actor)) > 0",
            name="ck_image_import_guard_decisions_text",
        ),
        sa.CheckConstraint(
            "(disposition = 'corrected_full' AND symbol_grid_quad IS NOT NULL "
            "AND jsonb_typeof(symbol_grid_quad) = 'array' "
            "AND jsonb_array_length(symbol_grid_quad) = 4 "
            "AND cardinality(unavailable_cell_indices) = 0) OR "
            "(disposition = 'partial' AND symbol_grid_quad IS NOT NULL "
            "AND jsonb_typeof(symbol_grid_quad) = 'array' "
            "AND jsonb_array_length(symbol_grid_quad) = 4 "
            "AND cardinality(unavailable_cell_indices) BETWEEN 1 AND 14 "
            "AND unavailable_cell_indices <@ "
            "ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[]) OR "
            "(disposition = 'rejected' AND symbol_grid_quad IS NULL "
            "AND cardinality(unavailable_cell_indices) = 0 "
            "AND length(btrim(reason)) > 0)",
            name="ck_image_import_guard_decisions_disposition",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["browser_selection_id"],
            ["browser_selection_retention_states.upload_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["guard_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guard_job_id",
            "source_checksum_sha256",
            "position_index",
            "revision",
            name="uq_image_import_guard_decisions_revision",
        ),
        sa.UniqueConstraint(
            "guard_job_id",
            "decision_checksum_sha256",
            name="uq_image_import_guard_decisions_checksum",
        ),
    )
    op.create_index(
        "ix_image_import_guard_decisions_current",
        "image_import_geometry_guard_decisions",
        ["guard_job_id", "source_checksum_sha256", "position_index", "revision"],
    )

    op.create_table(
        "image_import_geometry_guard_resolution_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("browser_selection_id", sa.Uuid(), nullable=False),
        sa.Column("guard_job_id", sa.Uuid(), nullable=False),
        sa.Column("guard_report_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("page_geometry_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_relative_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision_count", sa.Integer(), nullable=False),
        sa.Column("sealed_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "decision_count > 0 AND length(btrim(sealed_by)) > 0 "
            "AND length(btrim(manifest_relative_path)) > 0 "
            "AND manifest_relative_path !~ '(^/|(^|/)\\.\\.(/|$)|\\\\)'",
            name="ck_image_import_guard_resolution_manifest_values",
        ),
        sa.CheckConstraint(
            "guard_report_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "page_geometry_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_import_guard_resolution_manifest_checksums",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["browser_selection_id"],
            ["browser_selection_retention_states.upload_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["guard_job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guard_job_id",
            "manifest_checksum_sha256",
            name="uq_image_import_guard_resolution_manifest_checksum",
        ),
    )
    op.create_index(
        "ix_image_import_guard_resolution_manifest_guard",
        "image_import_geometry_guard_resolution_manifests",
        ["guard_job_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_import_guard_resolution_manifest_guard",
        table_name="image_import_geometry_guard_resolution_manifests",
    )
    op.drop_table("image_import_geometry_guard_resolution_manifests")
    op.drop_index(
        "ix_image_import_guard_decisions_current",
        table_name="image_import_geometry_guard_decisions",
    )
    op.drop_table("image_import_geometry_guard_decisions")
    op.drop_constraint(
        "ck_recognized_boards_completeness",
        "recognized_boards",
        type_="check",
    )
    op.drop_column("recognized_boards", "unavailable_cell_indices")
    op.drop_column("recognized_boards", "completeness_status")
