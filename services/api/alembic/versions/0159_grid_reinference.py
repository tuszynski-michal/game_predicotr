"""Persist scoped grid reinference state and receipts, without running inference."""

import hashlib

from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v12 import ADDED_GAME_TABLES

revision = "0159_grid_reinference"
down_revision = "0158_new_game_v3_bootstrap"
branch_labels = depends_on = None
V11, V12 = "game-data-v2-manifest-v11", "game-data-v2-manifest-v12"
OPERATIONS, SOURCES, TARGETS = ADDED_GAME_TABLES


def _guard(version: str) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <> 'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations
          WHERE manifest_version <> '{version}' OR store_schema <> 'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")


def _protect(table: str) -> None:
    suffix = hashlib.sha256(table.encode("ascii")).hexdigest()[:12]
    predicate = "game_id = game_data_v2.current_game_id_v1()"
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(f"""DO $partitions$ DECLARE location record; child text; BEGIN
        FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
            child := 'gpv2_' || left(replace(location.game_id::text,'-',''),12) || '_{suffix}';
            EXECUTE format('CREATE TABLE game_data_v2.%I PARTITION OF game_data_v2.{table} '
                'FOR VALUES IN (%L)',child,location.game_id);
            EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
            EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
            EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
                'USING ({predicate}) WITH CHECK ({predicate})',child);
        END LOOP;
    END $partitions$""")
    # Existing application roles receive owner default privileges configured by
    # provision_application_role. Copy parent ACLs too for earlier installations
    # whose grants predate that default-privilege policy. Never create cluster roles.
    op.execute(f"""DO $grants$ DECLARE grant_row record; BEGIN
        FOR grant_row IN
            SELECT DISTINCT r.rolname,a.privilege_type FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN LATERAL aclexplode(c.relacl) a
            JOIN pg_roles r ON r.oid=a.grantee
            WHERE n.nspname='game_data_v2' AND c.relname='source_images'
              AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE')
              AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid <> c.relowner
        LOOP
            EXECUTE format('GRANT %s ON game_data_v2.{table} TO %I',
                grant_row.privilege_type,grant_row.rolname);
        END LOOP;
    END $grants$""")


def _move_manifest(previous: str, current: str) -> None:
    old_number, number = previous.rsplit("v", 1)[1], current.rsplit("v", 1)[1]
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{old_number}"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version='{current}',"
        f"revision=revision+1,updated_at=now() WHERE manifest_version='{previous}'"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{number} "
        f"CHECK(manifest_version='{current}')"
    )


def upgrade() -> None:
    _guard(V11)
    op.execute(f"""CREATE TABLE game_data_v2.{OPERATIONS} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1()
            REFERENCES public.games(id) ON DELETE RESTRICT,
        id UUID NOT NULL, idempotency_key UUID NOT NULL,
        command_sha256 VARCHAR(64) NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$'),
        job_id UUID NOT NULL, document JSONB NOT NULL CHECK(jsonb_typeof(document)='object'),
        PRIMARY KEY(game_id,id), UNIQUE(game_id,idempotency_key), UNIQUE(game_id,job_id),
        FOREIGN KEY(game_id,job_id) REFERENCES public.jobs(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{SOURCES} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1()
            REFERENCES public.games(id) ON DELETE RESTRICT,
        operation_id UUID NOT NULL, ordinal BIGINT NOT NULL CHECK(ordinal > 0),
        source_image_id UUID NOT NULL, live_source_image_id UUID,
        CHECK(live_source_image_id IS NULL OR live_source_image_id = source_image_id),
        document JSONB NOT NULL CHECK(jsonb_typeof(document)='object'),
        checkpoint JSONB CHECK(checkpoint IS NULL OR jsonb_typeof(checkpoint)='object'),
        PRIMARY KEY(game_id,operation_id,ordinal),
        UNIQUE(game_id,operation_id,source_image_id),
        UNIQUE(game_id,operation_id,ordinal,source_image_id),
        FOREIGN KEY(game_id,operation_id) REFERENCES game_data_v2.{OPERATIONS}(game_id,id)
            ON DELETE RESTRICT,
        FOREIGN KEY(game_id,live_source_image_id) REFERENCES game_data_v2.source_images(game_id,id)
            ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.{TARGETS} (
        game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1()
            REFERENCES public.games(id) ON DELETE RESTRICT,
        operation_id UUID NOT NULL, ordinal BIGINT NOT NULL,
        source_ordinal BIGINT NOT NULL CHECK(source_ordinal > 0), source_image_id UUID NOT NULL,
        position_index INTEGER NOT NULL CHECK(position_index BETWEEN 0 AND 8),
        target_result_id UUID NOT NULL,
        snapshot JSONB NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
        fingerprint_sha256 VARCHAR(64) NOT NULL CHECK(fingerprint_sha256 ~ '^[0-9a-f]{{64}}$'),
        outcome VARCHAR(32), result JSONB,
        PRIMARY KEY(game_id,operation_id,ordinal), UNIQUE(game_id,target_result_id),
        UNIQUE(game_id,operation_id,source_image_id,position_index),
        FOREIGN KEY(game_id,operation_id,source_ordinal,source_image_id)
            REFERENCES game_data_v2.{SOURCES}(game_id,operation_id,ordinal,source_image_id)
            ON DELETE RESTRICT,
        CHECK(ordinal = source_ordinal * 10 + position_index + 1),
        CHECK((outcome IS NULL AND result IS NULL) OR (outcome IS NOT NULL
            AND result IS NOT NULL AND jsonb_typeof(result)='object'))
    ) PARTITION BY LIST(game_id)""")
    for table in ADDED_GAME_TABLES:
        _protect(table)
    op.execute(f"""INSERT INTO public.game_storage_table_manifest
        SELECT '{V12}',table_name,ownership,partitioned
        FROM public.game_storage_table_manifest WHERE manifest_version='{V11}'""")
    for table in ADDED_GAME_TABLES:
        op.execute(
            f"INSERT INTO public.game_storage_table_manifest VALUES('{V12}','{table}','game',TRUE)"
        )
    _move_manifest(V11, V12)


def downgrade() -> None:
    _guard(V12)
    op.execute("SET LOCAL row_security=off")
    for table in ADDED_GAME_TABLES:
        # The same transaction holds the guard and DDL locks. Refuse loss of
        # operation history even when no terminal result has yet been written.
        op.execute(f"LOCK TABLE game_data_v2.{table} IN ACCESS EXCLUSIVE MODE")
        op.execute(f"""DO $history$ BEGIN
            IF EXISTS(SELECT 1 FROM game_data_v2.{table}) THEN
                RAISE EXCEPTION 'GRID_REINFERENCE_DOWNGRADE_HAS_HISTORY'; END IF;
        END $history$""")
    for table in reversed(ADDED_GAME_TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    _move_manifest(V12, V11)
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version='{V12}'")
