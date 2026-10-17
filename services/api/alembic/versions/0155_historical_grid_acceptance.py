"""Add durable, game-scoped status-only historical acceptance (TASK-1008).

No source, geometry, crop or human decision is changed by this migration.
Downgrade refuses while any operation history exists.
"""

import hashlib

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v8 import (
    ADDED_GAME_TABLES,
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision = "0155_historical_grid_acceptance"
down_revision = "0154_geometry_correction_revert"
branch_labels = depends_on = None
V7, V8 = "game-data-v2-manifest-v7", "game-data-v2-manifest-v8"
OPERATIONS, TARGETS, RECEIPTS = ADDED_GAME_TABLES


def _guard() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
                IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <>
        'done') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS';
        END IF;
    END $guard$""")


def _protect(table: str) -> None:
    suffix = hashlib.sha256(table.encode("ascii")).hexdigest()[:12]
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} USING(game_id = "
        f"game_data_v2.current_game_id_v1()) WITH CHECK(game_id = "
        f"game_data_v2.current_game_id_v1())"
    )
    op.execute(f"""DO $partitions$ DECLARE location record; child text; BEGIN
        FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
            child := 'gpv2_' || left(replace(location.game_id::text,'-',''),12) || '_{suffix}';
                    EXECUTE format('CREATE TABLE game_data_v2.%I PARTITION OF game_data_v2.{table}
        FOR VALUES IN (%L)',child,location.game_id);
            EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
                    EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I USING(game_id =
        game_data_v2.current_game_id_v1()) WITH CHECK(game_id =
        game_data_v2.current_game_id_v1())',child);
        END LOOP;
    END $partitions$""")


def upgrade() -> None:
    _guard()
    op.execute(f"""DO $guard$ BEGIN
                IF EXISTS (SELECT 1 FROM public.game_storage_locations WHERE manifest_version <>
        '{V7}' OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    op.execute(f"""CREATE TABLE game_data_v2.{OPERATIONS} (
                game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES
        public.games(id) ON DELETE RESTRICT,
        id UUID NOT NULL, idempotency_key UUID NOT NULL, command_sha256 VARCHAR(64) NOT NULL,
        phase VARCHAR(20) NOT NULL, preparation_state VARCHAR(100),
        started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                preview_after_source_id UUID, preview_cursor BIGINT NOT NULL DEFAULT 0, run_cursor
        BIGINT NOT NULL DEFAULT 0,
        revision_count BIGINT NOT NULL DEFAULT 0, eligible_count BIGINT NOT NULL DEFAULT 0,
        accepted_count BIGINT NOT NULL DEFAULT 0, skipped_count BIGINT NOT NULL DEFAULT 0,
        preview_reasons JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        run_reasons JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        confirm_key UUID, confirm_sha256 VARCHAR(64),
        PRIMARY KEY(game_id,id), UNIQUE(game_id,idempotency_key),
                CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$' AND phase IN
        ('previewing','previewed','running','done')),
        CHECK(preview_cursor >= 0 AND run_cursor BETWEEN 0 AND preview_cursor),
        CHECK((confirm_key IS NULL) = (confirm_sha256 IS NULL)),
        CHECK(confirm_sha256 IS NULL OR confirm_sha256 ~ '^[0-9a-f]{{64}}$'),
                CHECK((phase IN ('previewing','previewed') AND confirm_key IS NULL) OR (phase IN
        ('running','done') AND confirm_key IS NOT NULL))
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{TARGETS} (
                game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES
        public.games(id) ON DELETE RESTRICT,
                operation_id UUID NOT NULL, ordinal BIGINT NOT NULL CHECK(ordinal > 0),
        source_image_id UUID NOT NULL,
                revision_id UUID, revision_number INTEGER, previous_status VARCHAR(20),
        fingerprint_sha256 VARCHAR(64) NOT NULL,
        reasons JSONB NOT NULL CHECK(jsonb_typeof(reasons) = 'array'),
        PRIMARY KEY(game_id,operation_id,ordinal), UNIQUE(game_id,operation_id,source_image_id),
                FOREIGN KEY(game_id,operation_id) REFERENCES game_data_v2.{OPERATIONS}(game_id,id)
        ON DELETE RESTRICT,
                CHECK(fingerprint_sha256 ~ '^[0-9a-f]{{64}}$'), CHECK((revision_id IS NULL) =
        (revision_number IS NULL))
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{RECEIPTS} (
                game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES
        public.games(id) ON DELETE RESTRICT,
                operation_id UUID NOT NULL, ordinal BIGINT NOT NULL, idempotency_key UUID NOT
        NULL, command_sha256 VARCHAR(64) NOT NULL,
        source_image_id UUID NOT NULL, revision_id UUID, outcome VARCHAR(20) NOT NULL,
        reasons JSONB NOT NULL CHECK(jsonb_typeof(reasons) = 'array'), actor VARCHAR(200) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(game_id,operation_id,ordinal), UNIQUE(game_id,idempotency_key),
                FOREIGN KEY(game_id,operation_id,ordinal) REFERENCES
        game_data_v2.{TARGETS}(game_id,operation_id,ordinal) ON DELETE RESTRICT,
        CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$' AND length(btrim(actor)) > 0),
                CHECK((outcome = 'accepted' AND revision_id IS NOT NULL AND reasons = '[]'::jsonb)
        OR (outcome = 'skipped' AND jsonb_array_length(reasons) > 0))
    ) PARTITION BY LIST(game_id)""")
    # Dependency order matters when provisioning pre-existing game partitions.
    for table in (OPERATIONS, TARGETS, RECEIPTS):
        _protect(table)
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
                "manifest_version": V8,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        "ck_game_storage_locations_manifest_version_v7"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET "
        f"manifest_version='{V8}',revision=revision+1,updated_at=now() WHERE "
        f"manifest_version='{V7}'"
    )
    op.execute(
        f"ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v8 CHECK(manifest_version='{V8}')"
    )


def downgrade() -> None:
    _guard()
    op.execute("SET LOCAL row_security = off")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.{OPERATIONS}) THEN
            RAISE EXCEPTION 'HISTORICAL_ACCEPTANCE_DOWNGRADE_HAS_HISTORY';
        END IF;
                IF EXISTS (SELECT 1 FROM public.game_storage_locations WHERE manifest_version <>
        '{V8}') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    for table in (RECEIPTS, TARGETS, OPERATIONS):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        "ck_game_storage_locations_manifest_version_v8"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET "
        f"manifest_version='{V7}',revision=revision+1,updated_at=now() WHERE "
        f"manifest_version='{V8}'"
    )
    op.execute(
        f"ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v7 CHECK(manifest_version='{V7}')"
    )
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version='{V8}'")
