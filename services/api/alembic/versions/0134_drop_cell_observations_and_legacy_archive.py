"""Drop the V1-era cell records and the empty board-search archive (D-467 S5, TASK-0759).

After TASK-0757/0758 every runtime reader takes a virtual board's cells from
``board_render_manifests`` and TASK-0790 stopped every writer from creating
cell observations or ``legacy_file`` boards at geometry revision 0.  This
migration moves the storage registry from manifest v3 to manifest v4 and
drops, in the same transaction, the three game tables that manifest v4 no
longer lists (frozen below, no ORM import): the per-cell import records and
the two never-populated frozen board-search archive tables.  Partitions are
discovered through ``pg_inherits`` and dropped before their parents.

Preflight (each refusal raises an explicit code and changes nothing):

* ``GAME_STORAGE_LIFECYCLE_IN_PROGRESS`` / ``GAME_STORAGE_LOCATION_BUSY`` — a
  partition lifecycle operation is unfinished or a store is migrating/deleting;
* ``GAME_STORAGE_MANIFEST_UNEXPECTED`` — a store is not V2 manifest v3;
* ``GAME_STORAGE_DROP_TABLE_UNEXPECTED`` — a frozen table is missing or is not a
  partitioned table of ``game_data_v2``;
* ``GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT`` — a foreign key outside the dropped
  set references a dropped table or partition;
* ``CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT`` — a ``legacy_file`` board
  at geometry revision 0 exists (its crops live only in the dropped records);
* ``BOARD_RENDER_MANIFEST_MISSING`` — a ``virtual_source`` board with at least
  one available cell has no render manifest of its current revision;
* ``LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY`` — an archive table holds rows.

The manifest backfill keeps its checkpoint in a file, not in the database, so
there is no durable backfill state to check; the missing-manifest preflight
covers an unfinished backfill.  Downgrade refuses: the dropped rows are not
reconstructible (restore the ``pg_dump`` backup into a side database instead).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v4 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision: str = "0134_drop_cell_observations_and_legacy_archive"
down_revision: str | Sequence[str] | None = "0133_virtual_only_import_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "game_data_v2"
# Frozen: exactly the tables manifest v4 removes from manifest v3.
DROPPED_TABLES = (
    "cell_observations",
    "legacy_board_search_archive_documents",
    "legacy_board_search_archive_states",
)
ARCHIVE_TABLES = DROPPED_TABLES[1:]
V3 = "game-data-v2-manifest-v3"
V4 = "game-data-v2-manifest-v4"
_LOCATION_CHECK_V3 = "ck_game_storage_locations_manifest_version_v3"
_LOCATION_CHECK_V4 = "ck_game_storage_locations_manifest_version_v4"
_V3_QUALIFICATION = "manual-geometry-qualification-v3"
_DROPPED_ARRAY = "ARRAY[" + ", ".join(f"'{name}'" for name in DROPPED_TABLES) + "]::text[]"


def _dropped_relations_cte() -> str:
    """Parents of the frozen set plus every partition found in ``pg_inherits``."""

    return f"""WITH RECURSIVE dropped(oid) AS (
            SELECT c.oid FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = '{SCHEMA}' AND c.relname = ANY({_DROPPED_ARRAY})
            UNION
            SELECT i.inhrelid FROM pg_inherits i JOIN dropped d ON i.inhparent = d.oid
        )"""


def _guard_lifecycle_and_registry() -> None:
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations
                   WHERE status <> 'done') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS: resolve every lifecycle operation';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE status NOT IN ('active', 'blocked')) THEN
            RAISE EXCEPTION 'GAME_STORAGE_LOCATION_BUSY: a game store is migrating or deleting';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V3}' OR store_schema <> '{SCHEMA}') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED: every store must be V2 manifest v3';
        END IF;
    END $guard$""")


def _guard_dropped_tables() -> None:
    op.execute(f"""DO $guard$ BEGIN
        IF (SELECT count(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = '{SCHEMA}' AND c.relname = ANY({_DROPPED_ARRAY})
              AND c.relkind = 'p') <> {len(DROPPED_TABLES)} THEN
            RAISE EXCEPTION 'GAME_STORAGE_DROP_TABLE_UNEXPECTED: every dropped table must be '
                'a partitioned table of {SCHEMA}';
        END IF;
        IF EXISTS (
            {_dropped_relations_cte()}
            SELECT 1 FROM pg_constraint con
            WHERE con.contype = 'f'
              AND con.confrelid IN (SELECT oid FROM dropped)
              AND con.conrelid NOT IN (SELECT oid FROM dropped)
        ) THEN
            RAISE EXCEPTION 'GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT: a foreign key outside the '
                'dropped tables references them';
        END IF;
    END $guard$""")


def _guard_board_data() -> None:
    archive_rows = " OR ".join(
        f"EXISTS (SELECT 1 FROM {SCHEMA}.{table})" for table in ARCHIVE_TABLES
    )
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM {SCHEMA}.recognized_boards
                   WHERE asset_mode = 'legacy_file' AND geometry_revision = 0) THEN
            RAISE EXCEPTION 'CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT: a legacy_file '
                'board at geometry revision 0 still reads its crops from cell observations';
        END IF;
        IF EXISTS (
            SELECT 1 FROM {SCHEMA}.recognized_boards b
            WHERE b.asset_mode = 'virtual_source'
              AND 15 - CASE
                    WHEN b.geometry_qualification->>'version' = '{_V3_QUALIFICATION}'
                    THEN COALESCE(
                        jsonb_array_length(b.geometry_qualification->'fullyUnavailableCellIndices'),
                        0)
                    ELSE cardinality(b.unavailable_cell_indices)
                  END > 0
              AND NOT EXISTS (
                  SELECT 1 FROM {SCHEMA}.board_render_manifests m
                  WHERE m.game_id = b.game_id
                    AND m.recognized_board_id = b.id
                    AND m.geometry_revision = b.geometry_revision)
        ) THEN
            RAISE EXCEPTION 'BOARD_RENDER_MANIFEST_MISSING: a virtual board with available cells '
                'has no render manifest of its current geometry revision';
        END IF;
        IF {archive_rows} THEN
            RAISE EXCEPTION 'LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY: the frozen board-search '
                'archive holds rows';
        END IF;
    END $guard$""")


def _drop_tables() -> None:
    op.execute(f"""DO $drop$ DECLARE parent text; partition record; BEGIN
        FOREACH parent IN ARRAY {_DROPPED_ARRAY} LOOP
            FOR partition IN
                SELECT pn.nspname AS schema_name, pc.relname AS table_name
                FROM pg_inherits i
                JOIN pg_class pc ON pc.oid = i.inhrelid
                JOIN pg_namespace pn ON pn.oid = pc.relnamespace
                WHERE i.inhparent = format('%I.%I', '{SCHEMA}', parent)::regclass
                ORDER BY pc.relname
            LOOP
                EXECUTE format('DROP TABLE %I.%I', partition.schema_name, partition.table_name);
            END LOOP;
            EXECUTE format('DROP TABLE %I.%I', '{SCHEMA}', parent);
        END LOOP;
    END $drop$""")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Router writers hold FOR SHARE on their location row until commit; the
    # registry CHECK is replaced below, so take the strongest lock up front.
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    _guard_lifecycle_and_registry()
    _guard_dropped_tables()
    dropped = ", ".join(f"{SCHEMA}.{table}" for table in DROPPED_TABLES)
    op.execute(f"LOCK TABLE {dropped} IN ACCESS EXCLUSIVE MODE")
    # No board or manifest may change between the preflight and the commit.
    op.execute(
        f"LOCK TABLE {SCHEMA}.recognized_boards, {SCHEMA}.board_render_manifests IN SHARE MODE"
    )
    _guard_board_data()

    manifest = sa.table(
        "game_storage_table_manifest",
        sa.column("manifest_version", sa.Text()),
        sa.column("table_name", sa.Text()),
        sa.column("ownership", sa.Text()),
        sa.column("partitioned", sa.Boolean()),
        schema="public",
    )
    op.bulk_insert(
        manifest,
        [
            {
                "manifest_version": V4,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(f"ALTER TABLE public.game_storage_locations DROP CONSTRAINT {_LOCATION_CHECK_V3}")
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V4}', "
        f"revision = revision + 1, updated_at = now() WHERE manifest_version = '{V3}'"
    )
    op.execute(
        f"ALTER TABLE public.game_storage_locations ADD CONSTRAINT {_LOCATION_CHECK_V4} "
        f"CHECK (manifest_version = '{V4}')"
    )
    _drop_tables()


def downgrade() -> None:
    op.execute("""DO $refuse$ BEGIN
        RAISE EXCEPTION 'CELL_OBSERVATIONS_DROP_IRREVERSIBLE: migration 0134 dropped cell '
            'observations and the board-search archive; restore the pg_dump backup into a '
            'side database instead';
    END $refuse$""")
