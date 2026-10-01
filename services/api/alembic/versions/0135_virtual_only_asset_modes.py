"""Boards and review cells allow only the virtual asset modes (D-467 S6, TASK-0791).

After the conversion script ``scripts/convert_legacy_boards_to_virtual.py``
has moved every ``legacy_file`` board of every game to ``virtual_source``,
the ``asset_mode`` CHECK constraints of ``recognized_boards`` and
``image_symbol_review_cells`` lose their ``legacy_file`` branch and the
column defaults become ``virtual_source``.  The historical ``legacy_file``
records of ``image_board_geometry_revisions`` stay as history, so that
table's CHECK is untouched.

Upgrade refuses (``LEGACY_FILE_BOARDS_PRESENT`` / ``LEGACY_FILE_CELLS_PRESENT``)
while a ``legacy_file`` board or cell exists: run the conversion first.  The
statements run on the partitioned parents, so every per-game partition
receives the same constraint names; adding a CHECK validates the existing
rows (a few seconds on the operator database).

Downgrade restores the previous constraint definitions and defaults; it does
not change any row.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0135_virtual_only_asset_modes"
down_revision: str | Sequence[str] | None = "0134_drop_cell_observations_and_legacy_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOARDS = "game_data_v2.recognized_boards"
CELLS = "game_data_v2.image_symbol_review_cells"
BOARD_CHECK = "ck_recognized_boards_asset_provenance"
CELL_PROVENANCE_CHECK = "ck_image_symbol_review_cells_asset_provenance"

_SAFE_PATH = r"'(^/|(^|/)\.\.(/|$)|\\)'"
_SHA256 = "'^[0-9a-f]{64}$'"

_VIRTUAL_BOARD = (
    "(asset_mode = 'virtual_source' AND board_relative_path IS NULL "
    "AND board_checksum_sha256 IS NULL AND source_geometry_revision_id IS NOT NULL "
    "AND length(btrim(geometry_engine_name)) > 0 "
    "AND length(btrim(geometry_engine_version)) > 0 "
    f"AND geometry_checksum_sha256 ~ {_SHA256})"
)
_LEGACY_BOARD = (
    f"(asset_mode = 'legacy_file' AND board_checksum_sha256 ~ {_SHA256} "
    "AND length(btrim(board_relative_path)) > 0 "
    f"AND board_relative_path !~ {_SAFE_PATH})"
)
_VIRTUAL_CELL = (
    "(asset_mode = 'virtual_source' AND crop_relative_path IS NULL "
    "AND source_geometry_revision_id IS NOT NULL "
    f"AND logical_cell_key ~ {_SHA256} AND jsonb_typeof(render_spec) = 'object' "
    f"AND render_spec_checksum_sha256 ~ {_SHA256} "
    f"AND rendered_pixel_checksum_sha256 ~ {_SHA256} "
    "AND length(btrim(extractor_version)) > 0)"
)
_LEGACY_CELL = (
    "(asset_mode = 'legacy_file' AND length(btrim(crop_relative_path)) > 0 "
    f"AND crop_relative_path !~ {_SAFE_PATH})"
)

NEW_BOARD_CHECK = _VIRTUAL_BOARD
OLD_BOARD_CHECK = f"{_LEGACY_BOARD} OR {_VIRTUAL_BOARD}"
NEW_CELL_CHECK = f"asset_mode = 'none' OR {_VIRTUAL_CELL}"
OLD_CELL_CHECK = f"asset_mode = 'none' OR {_LEGACY_CELL} OR {_VIRTUAL_CELL}"


def _swap_check(table: str, name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {BOARDS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"LOCK TABLE {CELLS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM {BOARDS} WHERE asset_mode <> 'virtual_source') THEN
            RAISE EXCEPTION 'LEGACY_FILE_BOARDS_PRESENT: convert every legacy_file board '
                'with scripts/convert_legacy_boards_to_virtual.py before this migration';
        END IF;
        IF EXISTS (SELECT 1 FROM {CELLS} WHERE asset_mode NOT IN ('virtual_source', 'none')) THEN
            RAISE EXCEPTION 'LEGACY_FILE_CELLS_PRESENT: convert every legacy_file board '
                'with scripts/convert_legacy_boards_to_virtual.py before this migration';
        END IF;
    END $guard$""")
    _swap_check(BOARDS, BOARD_CHECK, NEW_BOARD_CHECK)
    _swap_check(CELLS, CELL_PROVENANCE_CHECK, NEW_CELL_CHECK)
    op.execute(f"ALTER TABLE {BOARDS} ALTER COLUMN asset_mode SET DEFAULT 'virtual_source'")
    op.execute(f"ALTER TABLE {CELLS} ALTER COLUMN asset_mode SET DEFAULT 'virtual_source'")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {BOARDS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"LOCK TABLE {CELLS} IN ACCESS EXCLUSIVE MODE")
    _swap_check(BOARDS, BOARD_CHECK, OLD_BOARD_CHECK)
    _swap_check(CELLS, CELL_PROVENANCE_CHECK, OLD_CELL_CHECK)
    op.execute(f"ALTER TABLE {BOARDS} ALTER COLUMN asset_mode SET DEFAULT 'legacy_file'")
    op.execute(f"ALTER TABLE {CELLS} ALTER COLUMN asset_mode SET DEFAULT 'legacy_file'")
