"""Review cells no longer carry the duplicated render specification (D-467 S7, TASK-0793).

Since TASK-0792 every reader takes a cell's render specification from
``board_render_manifests`` (``storage/cell_render_specs.py``), verified
against ``image_symbol_review_cells.render_spec_checksum_sha256``.  The cell
column ``render_spec`` (about 19 GB of TOAST in game 777) is therefore
dropped; the checksum, the logical keys and the pixel checksum stay.

Upgrade, in one transaction on the partitioned parent (every per-game
partition follows):

1. ``lock_timeout`` 5 s, ``statement_timeout`` 120 s, ``ACCESS EXCLUSIVE``
   lock of the cell parent and a ``SHARE`` lock of the manifest parent (no
   manifest can disappear during the preflight);
2. preflight: every ``virtual_source`` cell has a board render manifest for
   its ``(game, board, geometry revision)`` -- otherwise
   ``CELL_RENDER_MANIFEST_MISSING`` and nothing changes (an anti-join on the
   manifest primary key; no JSONB is expanded);
3. both CHECK constraints that mention the column are replaced by versions
   without it: ``ck_image_symbol_review_cells_asset_provenance`` is added
   ``NOT VALID`` like in ``0135`` (validated afterwards by the runbook, a
   SHARE UPDATE EXCLUSIVE scan) and ``ck_image_symbol_review_cells_source_asset``
   stays ``NOT VALID`` as it has been since ``0126``;
4. ``DROP COLUMN render_spec`` (catalog-only; the space is reclaimed by the
   partition rewrite in ``DATABASE_MAINTENANCE.md``).

Downgrade refuses (``CELL_RENDER_SPEC_DROP_IRREVERSIBLE``): the specification
still exists in the manifests, but restoring the column is a backfill of
7.5 M rows, not a schema downgrade.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0136_drop_cell_render_spec"
down_revision: str | Sequence[str] | None = "0135_virtual_only_asset_modes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CELLS = "game_data_v2.image_symbol_review_cells"
MANIFESTS = "game_data_v2.board_render_manifests"
PROVENANCE_CHECK = "ck_image_symbol_review_cells_asset_provenance"
SOURCE_ASSET_CHECK = "ck_image_symbol_review_cells_source_asset"

_SHA256 = "'^[0-9a-f]{64}$'"

# ``0135`` minus ``jsonb_typeof(render_spec) = 'object'``.
NEW_PROVENANCE_CHECK = (
    "asset_mode = 'none' OR (asset_mode = 'virtual_source' AND crop_relative_path IS NULL "
    "AND source_geometry_revision_id IS NOT NULL "
    f"AND logical_cell_key ~ {_SHA256} "
    f"AND render_spec_checksum_sha256 ~ {_SHA256} "
    f"AND rendered_pixel_checksum_sha256 ~ {_SHA256} "
    "AND length(btrim(extractor_version)) > 0)"
)
# ``0126`` minus ``render_spec IS NULL``.
NEW_SOURCE_ASSET_CHECK = (
    "(asset_mode = 'none' AND source_visibility IS NOT DISTINCT FROM 'outside' "
    "AND NOT source_available AND crop_sample_id IS NULL AND crop_checksum_sha256 IS NULL "
    "AND crop_relative_path IS NULL "
    "AND render_spec_checksum_sha256 IS NULL AND rendered_pixel_checksum_sha256 IS NULL "
    "AND render_identity_v2_sha256 IS NULL AND logical_cell_key IS NULL "
    "AND logical_cell_key_v2 IS NULL AND extractor_version IS NULL "
    "AND prediction_symbol_code IS NULL AND prediction_confidence IS NULL) OR "
    "(asset_mode <> 'none' AND source_visibility IS DISTINCT FROM 'outside' "
    "AND crop_sample_id IS NOT NULL AND crop_checksum_sha256 IS NOT NULL)"
)


def _swap_check_not_valid(name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {CELLS} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {CELLS} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {CELLS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"LOCK TABLE {MANIFESTS} IN SHARE MODE")
    op.execute(f"""DO $guard$
    DECLARE missing bigint;
    BEGIN
        SELECT count(*) INTO missing
        FROM {CELLS} c
        WHERE c.asset_mode = 'virtual_source'
          AND NOT EXISTS (
            SELECT 1 FROM {MANIFESTS} m
            WHERE m.game_id = c.game_id
              AND m.recognized_board_id = c.recognized_board_id
              AND m.geometry_revision = c.geometry_revision
          );
        IF missing > 0 THEN
            RAISE EXCEPTION 'CELL_RENDER_MANIFEST_MISSING: % virtual review cells have no '
                'board render manifest for their geometry revision; the render '
                'specification would be lost', missing;
        END IF;
    END $guard$""")
    # A CHECK that mentions the column would block (or be dropped by) DROP
    # COLUMN, so both are replaced first, as in 0135.
    _swap_check_not_valid(PROVENANCE_CHECK, NEW_PROVENANCE_CHECK)
    _swap_check_not_valid(SOURCE_ASSET_CHECK, NEW_SOURCE_ASSET_CHECK)
    op.execute(f"ALTER TABLE {CELLS} DROP COLUMN render_spec")


def downgrade() -> None:
    raise RuntimeError(
        "CELL_RENDER_SPEC_DROP_IRREVERSIBLE: the per-cell render specification was dropped; "
        "it exists only in board_render_manifests and restoring the column is a backfill"
    )
