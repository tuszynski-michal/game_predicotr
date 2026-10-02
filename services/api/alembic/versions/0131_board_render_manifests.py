"""Per-board render manifests as a new V2 game table (D-467, TASK-0757).

Adds ``game_data_v2.board_render_manifests`` (list-partitioned by ``game_id``,
RLS ``game_scope_v1``), one partition for every registered game, and moves the
storage registry from manifest v1 to manifest v3.  Manifest v1 is frozen; its
registry rows stay as history.  The table is empty after upgrade; the
backfill script fills it.  Downgrade drops the table: until S5 removes
``cell_observations`` every row is reconstructible from observations and
geometry revisions.
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v3 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision: str = "0131_board_render_manifests"
down_revision: str | Sequence[str] | None = "0130_board_search_share_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "board_render_manifests"
V1 = "game-data-v2-manifest-v1"
V3 = "game-data-v2-manifest-v3"
_LOCATION_CHECK_V1 = "game_storage_locations_manifest_version_check"
_LOCATION_CHECK_V3 = "ck_game_storage_locations_manifest_version_v3"
# Same derivation as game_partition_lifecycle.partition_name, frozen here.
_PARTITION_SUFFIX = hashlib.sha256(TABLE.encode("ascii")).hexdigest()[:12]


def _guard_no_lifecycle_in_progress() -> None:
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations
                   WHERE status <> 'done') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS: resolve every lifecycle operation';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE status NOT IN ('active', 'blocked')) THEN
            RAISE EXCEPTION 'GAME_STORAGE_LOCATION_BUSY: a game store is migrating or deleting';
        END IF;
    END $guard$""")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Router writers hold FOR SHARE on their location row until commit; the
    # registry CHECK is replaced below, so take the strongest lock up front.
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    _guard_no_lifecycle_in_progress()
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V1}' OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED: every store must be V2 manifest v1';
        END IF;
    END $guard$""")

    op.execute(f"""CREATE TABLE game_data_v2.{TABLE} (
        game_id UUID NOT NULL,
        recognized_board_id UUID NOT NULL,
        geometry_revision INTEGER NOT NULL,
        asset_mode VARCHAR(20) DEFAULT 'virtual_source' NOT NULL,
        source_geometry_revision_id UUID NOT NULL,
        extractor_version VARCHAR(150) NOT NULL,
        cells JSONB NOT NULL,
        manifest_checksum_sha256 VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT v2_pk_{TABLE} PRIMARY KEY (game_id, recognized_board_id, geometry_revision),
        CONSTRAINT ck_{TABLE}_revision CHECK (geometry_revision >= 0),
        CONSTRAINT ck_{TABLE}_asset_mode CHECK (asset_mode = 'virtual_source'),
        CONSTRAINT ck_{TABLE}_cells CHECK (jsonb_typeof(cells) = 'object'
            AND jsonb_typeof(cells->'cells') = 'array'
            AND jsonb_array_length(cells->'cells') > 0),
        CONSTRAINT ck_{TABLE}_checksum CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_{TABLE}_extractor CHECK (length(btrim(extractor_version)) > 0)
    ) PARTITION BY LIST (game_id)""")
    op.execute(
        f"CREATE INDEX v2_fkix_{TABLE}_source_geometry ON game_data_v2.{TABLE} "
        "(game_id, source_geometry_revision_id)"
    )
    op.execute(
        f"ALTER TABLE game_data_v2.{TABLE} ADD CONSTRAINT v2_fk_{TABLE}_board "
        "FOREIGN KEY(game_id, recognized_board_id) "
        "REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE CASCADE"
    )
    op.execute(
        f"ALTER TABLE game_data_v2.{TABLE} ADD CONSTRAINT v2_fk_{TABLE}_source_geometry "
        "FOREIGN KEY(game_id, source_geometry_revision_id) "
        "REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) "
        "ON DELETE RESTRICT"
    )
    op.execute(
        f"ALTER TABLE game_data_v2.{TABLE} ADD CONSTRAINT v2_owner_{TABLE} "
        "FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT"
    )
    op.execute(
        f"ALTER TABLE game_data_v2.{TABLE} ALTER COLUMN game_id "
        "SET DEFAULT game_data_v2.current_game_id_v1()"
    )
    op.execute(f"ALTER TABLE game_data_v2.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{TABLE} "
        "USING (game_id = game_data_v2.current_game_id_v1()) "
        "WITH CHECK (game_id = game_data_v2.current_game_id_v1())"
    )
    # One partition per registered game, named like the lifecycle does.
    op.execute(f"""DO $partitions$ DECLARE location record; child text; BEGIN
        FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
            child := 'gpv2_' || left(replace(location.game_id::text, '-', ''), 12)
                || '_{_PARTITION_SUFFIX}';
            EXECUTE format(
                'CREATE TABLE game_data_v2.%I PARTITION OF game_data_v2.{TABLE} '
                'FOR VALUES IN (%L)', child, location.game_id);
            EXECUTE format(
                'ALTER TABLE game_data_v2.%I SET (autovacuum_vacuum_scale_factor = 0.02, '
                'autovacuum_analyze_scale_factor = 0.01)', child);
        END LOOP;
    END $partitions$""")

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
                "manifest_version": V3,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(f"ALTER TABLE public.game_storage_locations DROP CONSTRAINT {_LOCATION_CHECK_V1}")
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V3}', "
        f"revision = revision + 1, updated_at = now() WHERE manifest_version = '{V1}'"
    )
    op.execute(
        f"ALTER TABLE public.game_storage_locations ADD CONSTRAINT {_LOCATION_CHECK_V3} "
        f"CHECK (manifest_version = '{V3}')"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(
        f"LOCK TABLE public.game_storage_locations, game_data_v2.{TABLE} IN ACCESS EXCLUSIVE MODE"
    )
    _guard_no_lifecycle_in_progress()
    op.execute(f"""DO $notice$ DECLARE dropped bigint; BEGIN
        SELECT count(*) INTO dropped FROM game_data_v2.{TABLE};
        RAISE NOTICE 'BOARD_RENDER_MANIFESTS_DROPPED: % reconstructible rows', dropped;
    END $notice$""")
    op.execute(f"ALTER TABLE public.game_storage_locations DROP CONSTRAINT {_LOCATION_CHECK_V3}")
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V1}', "
        f"revision = revision + 1, updated_at = now() WHERE manifest_version = '{V3}'"
    )
    op.execute(
        f"ALTER TABLE public.game_storage_locations ADD CONSTRAINT {_LOCATION_CHECK_V1} "
        f"CHECK (manifest_version = '{V1}')"
    )
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version = '{V3}'")
    # Partitions are dropped with their parent; no CASCADE to other objects.
    op.execute(f"DROP TABLE game_data_v2.{TABLE}")
