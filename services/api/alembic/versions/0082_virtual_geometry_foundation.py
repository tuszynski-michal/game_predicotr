"""Persist virtual geometry provenance without activating the v0.10 pipeline.

Revision ID: 0082_virtual_geometry_foundation
Revises: 0081_pipeline_terminal_manifest_v2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0082_virtual_geometry_foundation"
down_revision: str | Sequence[str] | None = "0081_pipeline_terminal_manifest_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"'^[0-9a-f]{64}$'"
_SAFE_PATH = r"length(btrim({column})) > 0 AND {column} !~ '(^/|(^|/)\.\.(/|$)|\\)'"


def _add_not_valid_check(table: str, name: str, expression: str) -> None:
    # NOT VALID avoids an unbounded scan of the multi-million-row legacy
    # tables. PostgreSQL still enforces the constraint for every new or
    # modified row. TASK-0317 owns bounded validation of historical rows.
    op.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expression}) NOT VALID')


def _drop_check(table: str, name: str) -> None:
    op.drop_constraint(name, table, type_="check")


def upgrade() -> None:
    _add_source_coordinate_metadata()
    _create_source_geometry_revisions()
    _create_rollout_states()
    _extend_recognized_boards()
    _extend_cell_observations()
    _extend_board_geometry_revisions()
    _extend_symbol_review_cells()
    _extend_symbol_review_events()
    _extend_verified_training_cells()


def downgrade() -> None:
    # A physical downgrade would discard v0.10-only provenance. Once any
    # virtual record or source geometry exists, the supported rollback is the
    # per-game legacy rollout switch, not destructive schema removal.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM image_source_geometry_revisions LIMIT 1)
             OR EXISTS (
               SELECT 1 FROM image_geometry_rollout_states
               WHERE geometry_mode <> 'legacy' OR cell_asset_mode <> 'legacy_files'
               LIMIT 1
             )
             OR EXISTS (SELECT 1 FROM recognized_boards WHERE asset_mode = 'virtual_source' LIMIT 1)
             OR EXISTS (SELECT 1 FROM cell_observations WHERE asset_mode = 'virtual_source' LIMIT 1)
             OR EXISTS (
               SELECT 1 FROM image_board_geometry_revisions
               WHERE asset_mode = 'virtual_source' LIMIT 1
             )
             OR EXISTS (
               SELECT 1 FROM image_symbol_review_cells
               WHERE asset_mode = 'virtual_source' LIMIT 1
             )
             OR EXISTS (
               SELECT 1 FROM verified_training_cohort_cells
               WHERE asset_mode = 'virtual_source' LIMIT 1
             )
          THEN
            RAISE EXCEPTION '0082 downgrade blocked: virtual geometry provenance exists';
          END IF;
        END $$
        """
    )

    _downgrade_verified_training_cells()
    _downgrade_symbol_review_events()
    _downgrade_symbol_review_cells()
    _downgrade_board_geometry_revisions()
    _downgrade_cell_observations()
    _downgrade_recognized_boards()
    op.drop_index(
        "ix_image_geometry_rollout_states_mode",
        table_name="image_geometry_rollout_states",
    )
    op.drop_table("image_geometry_rollout_states")
    op.drop_index(
        "ix_image_source_geometry_revisions_game_status",
        table_name="image_source_geometry_revisions",
    )
    op.drop_index(
        "ix_image_source_geometry_revisions_source_created",
        table_name="image_source_geometry_revisions",
    )
    op.drop_table("image_source_geometry_revisions")
    _downgrade_source_coordinate_metadata()


def _add_source_coordinate_metadata() -> None:
    for column in (
        sa.Column("raw_width", sa.Integer(), nullable=True),
        sa.Column("raw_height", sa.Integer(), nullable=True),
        sa.Column("oriented_width", sa.Integer(), nullable=True),
        sa.Column("oriented_height", sa.Integer(), nullable=True),
        sa.Column("exif_orientation", sa.SmallInteger(), nullable=True),
        sa.Column("coordinate_space", sa.String(length=64), nullable=True),
        sa.Column("normalization_adapter_version", sa.String(length=150), nullable=True),
        sa.Column("normalized_pixel_checksum_sha256", sa.String(length=64), nullable=True),
    ):
        op.add_column("source_images", column)
    _add_not_valid_check(
        "source_images",
        "ck_source_images_coordinate_metadata",
        "(raw_width IS NULL AND raw_height IS NULL "
        "AND oriented_width IS NULL AND oriented_height IS NULL "
        "AND exif_orientation IS NULL AND coordinate_space IS NULL "
        "AND normalization_adapter_version IS NULL "
        "AND normalized_pixel_checksum_sha256 IS NULL) OR "
        "(raw_width > 0 AND raw_height > 0 "
        "AND oriented_width > 0 AND oriented_height > 0 "
        "AND (exif_orientation IS NULL OR exif_orientation BETWEEN 1 AND 8) "
        "AND coordinate_space = 'exif-normalized-rgb-pixels-v1' "
        "AND length(btrim(normalization_adapter_version)) > 0 "
        f"AND normalized_pixel_checksum_sha256 ~ {_SHA256})",
    )


def _create_source_geometry_revisions() -> None:
    op.create_table(
        "image_source_geometry_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("source_image_id", sa.Uuid(), nullable=False),
        sa.Column("topology_rules_version_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("sequence_range_start", sa.BigInteger(), nullable=False),
        sa.Column("sequence_range_end", sa.BigInteger(), nullable=False),
        sa.Column(
            "active_board_slots",
            postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
        ),
        sa.Column("coordinate_space", sa.String(length=64), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalized_pixel_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("oriented_width", sa.Integer(), nullable=False),
        sa.Column("oriented_height", sa.Integer(), nullable=False),
        sa.Column("normalization_adapter_version", sa.String(length=150), nullable=False),
        sa.Column("global_initialization", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("board_geometries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("engine_kind", sa.String(length=40), nullable=False),
        sa.Column("engine_version", sa.String(length=150), nullable=False),
        sa.Column("geometry_source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("geometry_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "revision >= 0 AND sequence_range_start > 0 "
            "AND sequence_range_end >= sequence_range_start "
            "AND sequence_range_end - sequence_range_start + 1 BETWEEN 1 AND 9",
            name="ck_image_source_geometry_revisions_range",
        ),
        sa.CheckConstraint(
            "active_board_slots = "
            "(ARRAY[0,1,2,3,4,5,6,7,8]::smallint[])[1:"
            "(sequence_range_end - sequence_range_start + 1)::integer]",
            name="ck_image_source_geometry_revisions_slots",
        ),
        sa.CheckConstraint(
            "coordinate_space = 'exif-normalized-rgb-pixels-v1' "
            "AND oriented_width > 0 AND oriented_height > 0 "
            "AND length(btrim(normalization_adapter_version)) > 0",
            name="ck_image_source_geometry_revisions_source",
        ),
        sa.CheckConstraint(
            f"source_checksum_sha256 ~ {_SHA256} "
            f"AND normalized_pixel_checksum_sha256 ~ {_SHA256} "
            f"AND geometry_checksum_sha256 ~ {_SHA256}",
            name="ck_image_source_geometry_revisions_checksums",
        ),
        sa.CheckConstraint(
            "(global_initialization IS NULL OR jsonb_typeof(global_initialization) = 'object') "
            "AND jsonb_typeof(board_geometries) = 'array' "
            "AND jsonb_array_length(board_geometries) = cardinality(active_board_slots) "
            "AND jsonb_typeof(warnings) = 'array'",
            name="ck_image_source_geometry_revisions_payloads",
        ),
        sa.CheckConstraint(
            "engine_kind IN ('legacy_v20', 'structured_opencv_v1', "
            "'manual_v1', 'keypoint_fallback_v1') "
            "AND length(btrim(engine_version)) > 0",
            name="ck_image_source_geometry_revisions_engine",
        ),
        sa.CheckConstraint(
            "geometry_source IN ('auto', 'manual', 'backfill') "
            "AND status IN ('pending', 'accepted', 'needs_review', 'rejected') "
            "AND (processing_time_ms IS NULL OR processing_time_ms >= 0) "
            "AND length(btrim(created_by)) > 0",
            name="ck_image_source_geometry_revisions_state",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_image_id"], ["source_images.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["topology_rules_version_id"],
            ["rules_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_image_id",
            "revision",
            name="uq_image_source_geometry_revisions_source_revision",
        ),
        sa.UniqueConstraint(
            "source_image_id",
            "geometry_checksum_sha256",
            name="uq_image_source_geometry_revisions_source_checksum",
        ),
    )
    op.create_index(
        "ix_image_source_geometry_revisions_source_created",
        "image_source_geometry_revisions",
        ["source_image_id", "created_at"],
    )
    op.create_index(
        "ix_image_source_geometry_revisions_game_status",
        "image_source_geometry_revisions",
        ["game_id", "status", "created_at"],
    )


def _create_rollout_states() -> None:
    op.create_table(
        "image_geometry_rollout_states",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column(
            "geometry_mode",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
        sa.Column(
            "cell_asset_mode",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'legacy_files'"),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "backfill_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'not_started'"),
        ),
        sa.Column("last_source_image_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "geometry_mode IN ('legacy', 'structured_shadow', "
            "'structured_review', 'structured_default')",
            name="ck_image_geometry_rollout_states_geometry_mode",
        ),
        sa.CheckConstraint(
            "cell_asset_mode IN ('legacy_files', 'virtual_shadow', 'virtual_default')",
            name="ck_image_geometry_rollout_states_asset_mode",
        ),
        sa.CheckConstraint(
            "revision >= 0 AND backfill_status IN ('not_started', 'processing', 'ready', 'failed')",
            name="ck_image_geometry_rollout_states_progress",
        ),
        sa.CheckConstraint(
            "length(btrim(updated_by)) > 0 AND "
            "((backfill_status = 'failed' AND failure_code IS NOT NULL "
            "AND failure_message IS NOT NULL) OR "
            "(backfill_status <> 'failed' AND failure_code IS NULL "
            "AND failure_message IS NULL))",
            name="ck_image_geometry_rollout_states_failure",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_source_image_id"], ["source_images.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("game_id"),
    )
    op.create_index(
        "ix_image_geometry_rollout_states_mode",
        "image_geometry_rollout_states",
        ["geometry_mode", "cell_asset_mode"],
    )


def _extend_recognized_boards() -> None:
    op.add_column(
        "recognized_boards",
        sa.Column(
            "asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
    )
    op.add_column("recognized_boards", sa.Column("source_geometry_revision_id", sa.Uuid()))
    op.add_column("recognized_boards", sa.Column("geometry_engine_name", sa.String(80)))
    op.add_column("recognized_boards", sa.Column("geometry_engine_version", sa.String(150)))
    op.add_column("recognized_boards", sa.Column("geometry_checksum_sha256", sa.String(64)))
    op.create_foreign_key(
        "fk_recognized_boards_source_geometry_revision",
        "recognized_boards",
        "image_source_geometry_revisions",
        ["source_geometry_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("recognized_boards", "board_relative_path", nullable=True)
    op.alter_column("recognized_boards", "board_checksum_sha256", nullable=True)
    _drop_check("recognized_boards", "ck_recognized_boards_sha256")
    _drop_check("recognized_boards", "ck_recognized_boards_relative_path")
    _add_not_valid_check(
        "recognized_boards",
        "ck_recognized_boards_pipeline_checksum",
        f"pipeline_fingerprint ~ {_SHA256}",
    )
    _add_not_valid_check(
        "recognized_boards",
        "ck_recognized_boards_asset_provenance",
        "(asset_mode = 'legacy_file' "
        f"AND board_checksum_sha256 ~ {_SHA256} AND "
        + _SAFE_PATH.format(column="board_relative_path")
        + ") OR (asset_mode = 'virtual_source' "
        "AND board_relative_path IS NULL AND board_checksum_sha256 IS NULL "
        "AND source_geometry_revision_id IS NOT NULL "
        "AND length(btrim(geometry_engine_name)) > 0 "
        "AND length(btrim(geometry_engine_version)) > 0 "
        f"AND geometry_checksum_sha256 ~ {_SHA256})",
    )
    op.create_index(
        "ix_recognized_boards_source_geometry_revision",
        "recognized_boards",
        ["source_geometry_revision_id", "position_index"],
    )


def _extend_cell_observations() -> None:
    _add_virtual_cell_columns("cell_observations")
    op.alter_column("cell_observations", "crop_relative_path", nullable=True)
    _drop_check("cell_observations", "ck_cell_observations_relative_path")
    _add_not_valid_check(
        "cell_observations",
        "ck_cell_observations_asset_provenance",
        _cell_asset_provenance_check(),
    )
    op.create_index(
        "ix_cell_observations_logical_cell",
        "cell_observations",
        ["logical_cell_key", "source_geometry_revision_id"],
        postgresql_where=sa.text("logical_cell_key IS NOT NULL"),
    )


def _extend_board_geometry_revisions() -> None:
    table = "image_board_geometry_revisions"
    op.add_column(
        table,
        sa.Column(
            "asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
    )
    op.add_column(table, sa.Column("source_geometry_revision_id", sa.Uuid()))
    op.add_column(table, sa.Column("geometry_checksum_sha256", sa.String(64)))
    op.add_column(table, sa.Column("virtual_render_spec", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column(table, sa.Column("virtual_render_spec_checksum_sha256", sa.String(64)))
    op.create_foreign_key(
        "fk_image_board_geometry_revisions_source_geometry",
        table,
        "image_source_geometry_revisions",
        ["source_geometry_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(table, "board_relative_path", nullable=True)
    op.alter_column(table, "board_checksum_sha256", nullable=True)
    op.alter_column(table, "crop_artifacts", nullable=True)
    _drop_check(table, "ck_image_board_geometry_revisions_sha256")
    _drop_check(table, "ck_image_board_geometry_revisions_crops")
    _drop_check(table, "ck_image_board_geometry_revisions_relative_path")
    _add_not_valid_check(
        table,
        "ck_image_board_geometry_revisions_command_checksum",
        f"command_sha256 ~ {_SHA256}",
    )
    _add_not_valid_check(
        table,
        "ck_image_board_geometry_revisions_asset",
        "(asset_mode = 'legacy_file' "
        f"AND board_checksum_sha256 ~ {_SHA256} AND "
        + _SAFE_PATH.format(column="board_relative_path")
        + " AND jsonb_typeof(crop_artifacts) = 'array' "
        "AND jsonb_array_length(crop_artifacts) = 15) OR "
        "(asset_mode = 'virtual_source' AND board_relative_path IS NULL "
        "AND board_checksum_sha256 IS NULL AND crop_artifacts IS NULL "
        "AND source_geometry_revision_id IS NOT NULL "
        f"AND geometry_checksum_sha256 ~ {_SHA256} "
        "AND jsonb_typeof(virtual_render_spec) = 'object' "
        f"AND virtual_render_spec_checksum_sha256 ~ {_SHA256})",
    )


def _extend_symbol_review_cells() -> None:
    table = "image_symbol_review_cells"
    _add_virtual_cell_columns(table)
    for column in (
        sa.Column("approved_asset_mode", sa.String(length=20), nullable=True),
        sa.Column("approved_source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("approved_render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("approved_rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
    ):
        op.add_column(table, column)
    op.create_foreign_key(
        "fk_image_symbol_review_cells_approved_source_geometry",
        table,
        "image_source_geometry_revisions",
        ["approved_source_geometry_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(table, "crop_relative_path", nullable=True)
    _drop_check(table, "ck_image_symbol_review_cells_relative_path")
    _drop_check(table, "ck_image_symbol_review_cells_approved_crop_identity")
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_cells_asset_provenance",
        _cell_asset_provenance_check(),
    )
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_cells_approved_provenance",
        "(approved_crop_sample_id IS NULL "
        "AND approved_crop_checksum_sha256 IS NULL "
        "AND approved_geometry_revision IS NULL "
        "AND approved_asset_mode IS NULL "
        "AND approved_source_geometry_revision_id IS NULL "
        "AND approved_render_spec_checksum_sha256 IS NULL "
        "AND approved_rendered_pixel_checksum_sha256 IS NULL) OR "
        "(approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_geometry_revision >= 0 "
        "AND (approved_asset_mode IS NULL OR approved_asset_mode = 'legacy_file') "
        "AND approved_source_geometry_revision_id IS NULL "
        "AND approved_render_spec_checksum_sha256 IS NULL "
        "AND approved_rendered_pixel_checksum_sha256 IS NULL) OR "
        "(approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_geometry_revision >= 0 "
        "AND approved_asset_mode = 'virtual_source' "
        "AND approved_source_geometry_revision_id IS NOT NULL "
        "AND approved_render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$')",
    )


def _extend_symbol_review_events() -> None:
    table = "image_symbol_review_events"
    for column in (
        sa.Column("logical_cell_key", sa.String(length=64), nullable=True),
        sa.Column(
            "previous_asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
        sa.Column(
            "asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
        sa.Column("previous_source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("previous_render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("previous_rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("extractor_version", sa.String(length=150), nullable=True),
        sa.Column("previous_approved_asset_mode", sa.String(length=20), nullable=True),
        sa.Column("approved_asset_mode", sa.String(length=20), nullable=True),
        sa.Column("previous_approved_source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("approved_source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column(
            "previous_approved_render_spec_checksum_sha256", sa.String(length=64), nullable=True
        ),
        sa.Column("approved_render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "previous_approved_rendered_pixel_checksum_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column("approved_rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
    ):
        op.add_column(table, column)
    for constraint_name, column_name in (
        (
            "fk_image_symbol_review_events_previous_source_geometry",
            "previous_source_geometry_revision_id",
        ),
        ("fk_image_symbol_review_events_source_geometry", "source_geometry_revision_id"),
        (
            "fk_image_symbol_review_events_previous_approved_source_geometry",
            "previous_approved_source_geometry_revision_id",
        ),
        (
            "fk_image_symbol_review_events_approved_source_geometry",
            "approved_source_geometry_revision_id",
        ),
    ):
        op.create_foreign_key(
            constraint_name,
            table,
            "image_source_geometry_revisions",
            [column_name],
            ["id"],
            ondelete="RESTRICT",
        )
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_events_render_provenance",
        _event_render_provenance_check("previous_") + " AND " + _event_render_provenance_check(""),
    )


def _extend_verified_training_cells() -> None:
    table = "verified_training_cohort_cells"
    for column in (
        sa.Column(
            "asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
        sa.Column("source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("logical_cell_key", sa.String(length=64), nullable=True),
        sa.Column("render_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("extractor_version", sa.String(length=150), nullable=True),
    ):
        op.add_column(table, column)
    op.create_foreign_key(
        "fk_verified_training_cohort_cells_source_geometry",
        table,
        "image_source_geometry_revisions",
        ["source_geometry_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _add_not_valid_check(
        table,
        "ck_verified_training_cohort_cells_asset_provenance",
        "asset_mode = 'legacy_file' OR (asset_mode = 'virtual_source' "
        "AND source_geometry_revision_id IS NOT NULL "
        f"AND logical_cell_key ~ {_SHA256} "
        "AND jsonb_typeof(render_spec) = 'object' "
        f"AND render_spec_checksum_sha256 ~ {_SHA256} "
        f"AND rendered_pixel_checksum_sha256 ~ {_SHA256} "
        "AND length(btrim(extractor_version)) > 0)",
    )


def _add_virtual_cell_columns(table: str) -> None:
    for column in (
        sa.Column(
            "asset_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'legacy_file'"),
        ),
        sa.Column("source_geometry_revision_id", sa.Uuid(), nullable=True),
        sa.Column("logical_cell_key", sa.String(length=64), nullable=True),
        sa.Column("render_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("render_spec_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("rendered_pixel_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("extractor_version", sa.String(length=150), nullable=True),
    ):
        op.add_column(table, column)
    op.create_foreign_key(
        f"fk_{table}_source_geometry_revision",
        table,
        "image_source_geometry_revisions",
        ["source_geometry_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def _cell_asset_provenance_check() -> str:
    return (
        "(asset_mode = 'legacy_file' AND "
        + _SAFE_PATH.format(column="crop_relative_path")
        + ") OR (asset_mode = 'virtual_source' "
        "AND crop_relative_path IS NULL "
        "AND source_geometry_revision_id IS NOT NULL "
        f"AND logical_cell_key ~ {_SHA256} "
        "AND jsonb_typeof(render_spec) = 'object' "
        f"AND render_spec_checksum_sha256 ~ {_SHA256} "
        f"AND rendered_pixel_checksum_sha256 ~ {_SHA256} "
        "AND length(btrim(extractor_version)) > 0)"
    )


def _event_render_provenance_check(prefix: str) -> str:
    asset_mode = f"{prefix}asset_mode"
    source_geometry = f"{prefix}source_geometry_revision_id"
    render_spec_checksum = f"{prefix}render_spec_checksum_sha256"
    pixel_checksum = f"{prefix}rendered_pixel_checksum_sha256"
    return (
        f"({asset_mode} = 'legacy_file') OR ({asset_mode} = 'virtual_source' "
        f"AND {source_geometry} IS NOT NULL "
        f"AND {render_spec_checksum} ~ {_SHA256} "
        f"AND {pixel_checksum} ~ {_SHA256})"
    )


def _downgrade_source_coordinate_metadata() -> None:
    _drop_check("source_images", "ck_source_images_coordinate_metadata")
    for column_name in (
        "normalized_pixel_checksum_sha256",
        "normalization_adapter_version",
        "coordinate_space",
        "exif_orientation",
        "oriented_height",
        "oriented_width",
        "raw_height",
        "raw_width",
    ):
        op.drop_column("source_images", column_name)


def _downgrade_recognized_boards() -> None:
    op.drop_index(
        "ix_recognized_boards_source_geometry_revision",
        table_name="recognized_boards",
    )
    _drop_check("recognized_boards", "ck_recognized_boards_asset_provenance")
    _drop_check("recognized_boards", "ck_recognized_boards_pipeline_checksum")
    op.alter_column("recognized_boards", "board_checksum_sha256", nullable=False)
    op.alter_column("recognized_boards", "board_relative_path", nullable=False)
    op.create_check_constraint(
        "ck_recognized_boards_sha256",
        "recognized_boards",
        f"board_checksum_sha256 ~ {_SHA256} AND pipeline_fingerprint ~ {_SHA256}",
    )
    op.create_check_constraint(
        "ck_recognized_boards_relative_path",
        "recognized_boards",
        _SAFE_PATH.format(column="board_relative_path"),
    )
    op.drop_constraint(
        "fk_recognized_boards_source_geometry_revision",
        "recognized_boards",
        type_="foreignkey",
    )
    for column_name in (
        "geometry_checksum_sha256",
        "geometry_engine_version",
        "geometry_engine_name",
        "source_geometry_revision_id",
        "asset_mode",
    ):
        op.drop_column("recognized_boards", column_name)


def _downgrade_cell_observations() -> None:
    op.drop_index("ix_cell_observations_logical_cell", table_name="cell_observations")
    _drop_check("cell_observations", "ck_cell_observations_asset_provenance")
    op.alter_column("cell_observations", "crop_relative_path", nullable=False)
    op.create_check_constraint(
        "ck_cell_observations_relative_path",
        "cell_observations",
        _SAFE_PATH.format(column="crop_relative_path"),
    )
    _drop_virtual_cell_columns("cell_observations")


def _downgrade_board_geometry_revisions() -> None:
    table = "image_board_geometry_revisions"
    _drop_check(table, "ck_image_board_geometry_revisions_asset")
    _drop_check(table, "ck_image_board_geometry_revisions_command_checksum")
    op.alter_column(table, "crop_artifacts", nullable=False)
    op.alter_column(table, "board_checksum_sha256", nullable=False)
    op.alter_column(table, "board_relative_path", nullable=False)
    op.create_check_constraint(
        "ck_image_board_geometry_revisions_sha256",
        table,
        f"command_sha256 ~ {_SHA256} AND board_checksum_sha256 ~ {_SHA256}",
    )
    op.create_check_constraint(
        "ck_image_board_geometry_revisions_crops",
        table,
        "jsonb_typeof(crop_artifacts) = 'array' AND jsonb_array_length(crop_artifacts) = 15",
    )
    op.create_check_constraint(
        "ck_image_board_geometry_revisions_relative_path",
        table,
        _SAFE_PATH.format(column="board_relative_path"),
    )
    op.drop_constraint(
        "fk_image_board_geometry_revisions_source_geometry",
        table,
        type_="foreignkey",
    )
    for column_name in (
        "virtual_render_spec_checksum_sha256",
        "virtual_render_spec",
        "geometry_checksum_sha256",
        "source_geometry_revision_id",
        "asset_mode",
    ):
        op.drop_column(table, column_name)


def _downgrade_symbol_review_cells() -> None:
    table = "image_symbol_review_cells"
    _drop_check(table, "ck_image_symbol_review_cells_approved_provenance")
    _drop_check(table, "ck_image_symbol_review_cells_asset_provenance")
    op.alter_column(table, "crop_relative_path", nullable=False)
    op.create_check_constraint(
        "ck_image_symbol_review_cells_relative_path",
        table,
        _SAFE_PATH.format(column="crop_relative_path"),
    )
    op.create_check_constraint(
        "ck_image_symbol_review_cells_approved_crop_identity",
        table,
        "(approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL "
        "AND approved_geometry_revision IS NULL) OR "
        "(approved_crop_sample_id IS NOT NULL "
        "AND approved_crop_checksum_sha256 IS NOT NULL "
        "AND approved_geometry_revision IS NOT NULL "
        "AND approved_crop_sample_id ~ '^[0-9a-f]{64}$' "
        "AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' "
        "AND approved_geometry_revision >= 0)",
    )
    op.drop_constraint(
        "fk_image_symbol_review_cells_approved_source_geometry",
        table,
        type_="foreignkey",
    )
    for column_name in (
        "approved_rendered_pixel_checksum_sha256",
        "approved_render_spec_checksum_sha256",
        "approved_source_geometry_revision_id",
        "approved_asset_mode",
    ):
        op.drop_column(table, column_name)
    _drop_virtual_cell_columns(table)


def _downgrade_symbol_review_events() -> None:
    table = "image_symbol_review_events"
    _drop_check(table, "ck_image_symbol_review_events_render_provenance")
    for constraint_name in (
        "fk_image_symbol_review_events_approved_source_geometry",
        "fk_image_symbol_review_events_previous_approved_source_geometry",
        "fk_image_symbol_review_events_source_geometry",
        "fk_image_symbol_review_events_previous_source_geometry",
    ):
        op.drop_constraint(constraint_name, table, type_="foreignkey")
    for column_name in (
        "approved_rendered_pixel_checksum_sha256",
        "previous_approved_rendered_pixel_checksum_sha256",
        "approved_render_spec_checksum_sha256",
        "previous_approved_render_spec_checksum_sha256",
        "approved_source_geometry_revision_id",
        "previous_approved_source_geometry_revision_id",
        "approved_asset_mode",
        "previous_approved_asset_mode",
        "extractor_version",
        "rendered_pixel_checksum_sha256",
        "previous_rendered_pixel_checksum_sha256",
        "render_spec_checksum_sha256",
        "previous_render_spec_checksum_sha256",
        "source_geometry_revision_id",
        "previous_source_geometry_revision_id",
        "asset_mode",
        "previous_asset_mode",
        "logical_cell_key",
    ):
        op.drop_column(table, column_name)


def _downgrade_verified_training_cells() -> None:
    table = "verified_training_cohort_cells"
    _drop_check(table, "ck_verified_training_cohort_cells_asset_provenance")
    op.drop_constraint(
        "fk_verified_training_cohort_cells_source_geometry",
        table,
        type_="foreignkey",
    )
    for column_name in (
        "extractor_version",
        "rendered_pixel_checksum_sha256",
        "render_spec_checksum_sha256",
        "render_spec",
        "logical_cell_key",
        "source_geometry_revision_id",
        "asset_mode",
    ):
        op.drop_column(table, column_name)


def _drop_virtual_cell_columns(table: str) -> None:
    op.drop_constraint(f"fk_{table}_source_geometry_revision", table, type_="foreignkey")
    for column_name in (
        "extractor_version",
        "rendered_pixel_checksum_sha256",
        "render_spec_checksum_sha256",
        "render_spec",
        "logical_cell_key",
        "source_geometry_revision_id",
        "asset_mode",
    ):
        op.drop_column(table, column_name)
