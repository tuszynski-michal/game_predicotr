"""Add explicit source visibility and asset-free logical review positions."""

import sqlalchemy as sa
from alembic import op

revision = "0126_symbol_cell_source_visibility"
down_revision = "0125_remove_legacy_public_game_store"
branch_labels = None
depends_on = None

# Frozen migration contract: never import current runtime ORM definitions.
_CONSTRAINTS = [
    (
        "image_symbol_review_bulk_targets",
        "ck_image_symbol_review_bulk_targets_checksums",
        "(expected_crop_sample_id IS NULL AND expected_crop_checksum_sha256 IS NULL) OR "
        "(expected_crop_sample_id IS NOT NULL AND expected_crop_checksum_sha256 IS NOT "
        "NULL AND expected_crop_sample_id ~ '^[0-9a-f]{64}$' AND "
        "expected_crop_checksum_sha256 ~ '^[0-9a-f]{64}$')",
    ),
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_asset_provenance",
        "asset_mode = 'none' OR (asset_mode = 'legacy_file' AND "
        "length(btrim(crop_relative_path)) > 0 AND crop_relative_path !~ "
        "'(^/|(^|/)\\.\\.(/|$)|\\\\)') OR (asset_mode = 'virtual_source' AND "
        "crop_relative_path IS NULL AND source_geometry_revision_id IS NOT NULL AND "
        "logical_cell_key ~ '^[0-9a-f]{64}$' AND jsonb_typeof(render_spec) = 'object' AND"
        " render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
        "rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
        "length(btrim(extractor_version)) > 0)",
    ),
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_source_asset",
        "(asset_mode = 'none' AND source_visibility IS NOT DISTINCT FROM 'outside' AND "
        "NOT source_available AND crop_sample_id IS NULL AND crop_checksum_sha256 IS NULL"
        " AND crop_relative_path IS NULL AND render_spec IS NULL AND "
        "render_spec_checksum_sha256 IS NULL AND rendered_pixel_checksum_sha256 IS NULL "
        "AND render_identity_v2_sha256 IS NULL AND logical_cell_key IS NULL AND "
        "logical_cell_key_v2 IS NULL AND extractor_version IS NULL AND "
        "prediction_symbol_code IS NULL AND prediction_confidence IS NULL) OR (asset_mode"
        " <> 'none' AND source_visibility IS DISTINCT FROM 'outside' AND crop_sample_id "
        "IS NOT NULL AND crop_checksum_sha256 IS NOT NULL)",
    ),
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_source_visibility",
        "source_visibility IS NULL OR source_visibility IN ('full', 'partial', 'outside')",
    ),
    (
        "image_symbol_review_events",
        "ck_image_symbol_review_events_render_provenance",
        "(previous_asset_mode IN ('legacy_file', 'none') OR (previous_asset_mode = "
        "'virtual_source' AND previous_source_geometry_revision_id IS NOT NULL AND "
        "previous_render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
        "previous_rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$')) AND (asset_mode IN "
        "('legacy_file', 'none') OR (asset_mode = 'virtual_source' AND "
        "source_geometry_revision_id IS NOT NULL AND render_spec_checksum_sha256 ~ "
        "'^[0-9a-f]{64}$' AND rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$'))",
    ),
]


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    schema = "game_data_v2"
    op.add_column(
        "image_symbol_review_cells",
        sa.Column("source_visibility", sa.String(10), nullable=True),
        schema=schema,
    )
    for table in (
        "image_symbol_review_cells",
        "image_symbol_review_events",
        "image_symbol_review_bulk_targets",
    ):
        prefix = "expected_" if table.endswith("bulk_targets") else ""
        for column in ("crop_sample_id", "crop_checksum_sha256"):
            op.alter_column(table, prefix + column, nullable=True, schema=schema)
    for table, name, expression in _CONSTRAINTS:
        if name not in {
            "ck_image_symbol_review_cells_source_visibility",
            "ck_image_symbol_review_cells_source_asset",
        }:
            op.drop_constraint(name, table, schema=schema, type_="check")
        op.create_check_constraint(
            name, table, expression, schema=schema, postgresql_not_valid=True
        )


def downgrade() -> None:
    raise RuntimeError("SOURCE_VISIBILITY_DOWNGRADE_UNSUPPORTED: outside positions may exist")
