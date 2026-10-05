"""Add isolated, opt-in grid comparison history and frozen storage manifest v5.

No images or production geometry are rewritten. Existing game stores receive
an empty protected partition. Downgrade refuses while comparison rows exist.
0141 belongs to another working tree; integration must resolve the heads
before this prepared migration is deployed.
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v5 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    ownership,
)

revision: str = "0142_grid_geometry_shadow_results"
down_revision: str | Sequence[str] | None = "0140_grid_engine_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "image_geometry_shadow_results"
V4 = "game-data-v2-manifest-v4"
V5 = "game-data-v2-manifest-v5"
_PARTITION_SUFFIX = hashlib.sha256(TABLE.encode("ascii")).hexdigest()[:12]


def _guard() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations
                   WHERE status <> 'done') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE status NOT IN ('active','blocked')) THEN
            RAISE EXCEPTION 'GAME_STORAGE_LOCATION_BUSY';
        END IF;
    END $guard$""")


def upgrade() -> None:
    _guard()
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V4}' OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    op.execute(f"""CREATE TABLE game_data_v2.{TABLE} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1(),
        id UUID NOT NULL, job_id UUID NOT NULL, source_image_id UUID NOT NULL,
        source_checksum_sha256 VARCHAR(64) NOT NULL,
        source_geometry_revision_id UUID NOT NULL,
        source_geometry_revision INTEGER NOT NULL,
        source_geometry_checksum_sha256 VARCHAR(64) NOT NULL,
        source_width INTEGER NOT NULL, source_height INTEGER NOT NULL,
        model_profile VARCHAR(100) NOT NULL, model_version VARCHAR(100) NOT NULL,
        model_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
        source_binding JSONB NOT NULL, model_binding JSONB NOT NULL,
        binding_checksum_sha256 VARCHAR(64) NOT NULL,
        status VARCHAR(24) NOT NULL, reasons JSONB NOT NULL, output JSONB NOT NULL,
        output_checksum_sha256 VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT v2_pk_grid_shadow PRIMARY KEY (game_id,id),
        CONSTRAINT uq_grid_shadow_job_source UNIQUE (game_id,job_id,source_image_id),
        CONSTRAINT ck_grid_shadow_status CHECK (status IN ('needs_review','failed','unsupported')),
        CONSTRAINT ck_grid_shadow_source CHECK (source_geometry_revision >= 0
            AND source_width > 0 AND source_height > 0),
        CONSTRAINT ck_grid_shadow_checksums CHECK (
            output_checksum_sha256 ~ '^[0-9a-f]{{64}}$'
            AND source_checksum_sha256 ~ '^[0-9a-f]{{64}}$'
            AND source_geometry_checksum_sha256 ~ '^[0-9a-f]{{64}}$'
            AND binding_checksum_sha256 ~ '^[0-9a-f]{{64}}$'
            AND model_manifest_checksum_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_grid_shadow_payloads CHECK (jsonb_typeof(output) = 'object'
            AND jsonb_typeof(source_binding) = 'object' AND jsonb_typeof(model_binding) = 'object'
            AND jsonb_typeof(reasons) = 'array'),
        CONSTRAINT v2_owner_grid_shadow FOREIGN KEY(game_id)
            REFERENCES public.games(id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_grid_shadow_job FOREIGN KEY(game_id,job_id)
            REFERENCES public.jobs(game_id,id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_grid_shadow_source FOREIGN KEY(game_id,source_image_id)
            REFERENCES game_data_v2.source_images(game_id,id) ON DELETE RESTRICT,
        CONSTRAINT v2_fk_grid_shadow_source_geometry
            FOREIGN KEY(game_id,source_geometry_revision_id)
            REFERENCES game_data_v2.image_source_geometry_revisions(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(
        f"CREATE INDEX ix_grid_shadow_game_created ON game_data_v2.{TABLE} (game_id,created_at,id)"
    )
    op.execute(f"ALTER TABLE game_data_v2.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{TABLE} "
        "USING(game_id = game_data_v2.current_game_id_v1()) "
        "WITH CHECK(game_id = game_data_v2.current_game_id_v1())"
    )
    op.execute(f"""DO $partitions$ DECLARE location record; child text; BEGIN
        FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
            child := 'gpv2_' || left(replace(location.game_id::text,'-',''),12)
                || '_{_PARTITION_SUFFIX}';
            EXECUTE format('CREATE TABLE game_data_v2.%I '
                'PARTITION OF game_data_v2.{TABLE} FOR VALUES IN (%L)',child,location.game_id);
            EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
            EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
                'USING(game_id = game_data_v2.current_game_id_v1()) '
                'WITH CHECK(game_id = game_data_v2.current_game_id_v1())',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I SET '
                '(autovacuum_vacuum_scale_factor = 0.02, '
                'autovacuum_analyze_scale_factor = 0.01)',child);
        END LOOP;
    END $partitions$""")
    op.execute("""CREATE UNIQUE INDEX uq_jobs_grid_shadow_request ON public.jobs
        (game_id,(input_payload->>'request_id'))
        WHERE job_type = 'validate'
            AND input_payload->>'validation_kind' = 'grid_geometry_shadow_v3'""")
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
                "manifest_version": V5,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v4"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V5}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V4}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v5 "
        f"CHECK(manifest_version = '{V5}')"
    )


def downgrade() -> None:
    _guard()
    # FORCE RLS must never make a non-empty table look empty. A role without
    # BYPASSRLS fails here rather than silently deleting hidden history.
    op.execute("SET LOCAL row_security = off")
    op.execute(f"LOCK TABLE game_data_v2.{TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.{TABLE}) THEN
            RAISE EXCEPTION 'GRID_SHADOW_DOWNGRADE_NOT_EMPTY';
        END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
                   WHERE manifest_version <> '{V5}') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED';
        END IF;
    END $guard$""")
    op.execute("DROP INDEX public.uq_jobs_grid_shadow_request")
    op.execute(f"DROP TABLE game_data_v2.{TABLE}")
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v5"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version = '{V4}',"
        f"revision = revision + 1,updated_at = now() WHERE manifest_version = '{V5}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations "
        f"ADD CONSTRAINT ck_game_storage_locations_manifest_version_v4 "
        f"CHECK(manifest_version = '{V4}')"
    )
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version = '{V5}'")
