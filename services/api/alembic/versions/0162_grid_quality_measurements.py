"""Retained descriptive measurement evidence and exact own-source membership."""

import hashlib

from alembic import op
from game_predictor_api.storage.source_recording_permissions_v2 import (
    SOURCE_RECORDING_V2_FUNCTION,
    enforce_recording_permissions,
    validate_recording_capability,
)
from game_predictor_api.storage.source_recording_sql_v2 import (
    DROP_SOURCE_RECORDING_V2_SQL,
    INSTALL_SOURCE_RECORDING_V2_SQL,
)
from sqlalchemy import text

revision = "0162_grid_quality_measurements"
down_revision = "0161_source_recording_groups"
branch_labels = depends_on = None
TABLES = (
    "grid_quality_measurements",
    "grid_quality_measurement_members",
    "grid_quality_measurement_judgments",
    "grid_quality_measurement_commands",
    "grid_geometry_approval_commands",
)


def _guard(version: int) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
      IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
      IF EXISTS(SELECT 1 FROM public.game_storage_locations WHERE
        manifest_version<>'game-data-v2-manifest-v{version}' OR store_schema<>'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")


def _manifest(previous: int, current: int) -> None:
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{previous}"
    )
    op.execute(
        "UPDATE public.game_storage_locations SET "
        f"manifest_version='game-data-v2-manifest-v{current}',revision=revision+1,updated_at=now()"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{current} "
        f"CHECK(manifest_version='game-data-v2-manifest-v{current}')"
    )


def _protect(table: str) -> None:
    suffix = hashlib.sha256(table.encode()).hexdigest()[:12]
    predicate = "game_id=game_data_v2.current_game_id_v1()"
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(f"""DO $children$ DECLARE location record; child text; BEGIN
      FOR location IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
        child := 'gpv2_' || left(replace(location.game_id::text,'-',''),12) || '_{suffix}';
        EXECUTE format('CREATE TABLE game_data_v2.%I PARTITION OF game_data_v2.{table} '
          'FOR VALUES IN (%L)',child,location.game_id);
        EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
        EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
        EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
          'USING ({predicate}) WITH CHECK ({predicate})',child);
      END LOOP;
    END $children$""")
    op.execute(f"""DO $grants$ DECLARE grant_row record; BEGIN
      FOR grant_row IN SELECT DISTINCT r.rolname,a.privilege_type FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
      JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='game_data_v2'
        AND c.relname='source_images'
      AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE')
      AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid<>c.relowner LOOP
        EXECUTE format('GRANT %s ON game_data_v2.{table} TO %I',
          grant_row.privilege_type,grant_row.rolname);
      END LOOP;
    END $grants$""")


def upgrade() -> None:
    _guard(14)
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    base = (
        "game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1() "
        "REFERENCES public.games(id)"
    )
    op.execute(f"""CREATE TABLE game_data_v2.grid_quality_measurements (
      {base}, id uuid NOT NULL, manifest_path varchar(1000) NOT NULL,
      manifest_sha256 varchar(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{{64}}$'),
      document jsonb NOT NULL CHECK(jsonb_typeof(document)='object'),
      PRIMARY KEY(game_id,id)) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_quality_measurement_members (
      {base}, measurement_id uuid NOT NULL, source_id uuid NOT NULL,
      sample_kind varchar(8) NOT NULL CHECK(sample_kind IN ('random','hard')),
      live_source_image_id uuid, revision integer NOT NULL CHECK(revision>=0),
      frozen jsonb NOT NULL CHECK(jsonb_typeof(frozen)='object'),
      current jsonb NOT NULL CHECK(jsonb_typeof(current)='object'),
      CHECK(live_source_image_id IS NULL OR live_source_image_id=source_id),
      PRIMARY KEY(game_id,measurement_id,source_id,sample_kind),
      FOREIGN KEY(game_id,measurement_id) REFERENCES
        game_data_v2.grid_quality_measurements(game_id,id),
      FOREIGN KEY(game_id,live_source_image_id) REFERENCES game_data_v2.source_images(game_id,id))
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_quality_measurement_judgments (
      {base}, measurement_id uuid NOT NULL, source_id uuid NOT NULL,
      sample_kind varchar(8) NOT NULL, revision integer NOT NULL CHECK(revision>=1),
      document jsonb NOT NULL CHECK(jsonb_typeof(document)='object'),
      PRIMARY KEY(game_id,measurement_id,source_id,sample_kind,revision),
      FOREIGN KEY(game_id,measurement_id,source_id,sample_kind) REFERENCES
        game_data_v2.grid_quality_measurement_members(game_id,measurement_id,source_id,sample_kind))
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_quality_measurement_commands (
      {base}, idempotency_key uuid NOT NULL, measurement_id uuid NOT NULL,
      kind varchar(16) NOT NULL CHECK(kind IN ('capture','assess')),
      command_sha256 varchar(64) NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$'),
      document jsonb NOT NULL CHECK(jsonb_typeof(document)='object'),
      PRIMARY KEY(game_id,idempotency_key),
      FOREIGN KEY(game_id,measurement_id) REFERENCES
        game_data_v2.grid_quality_measurements(game_id,id))
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_geometry_approval_commands (
      {base}, idempotency_key uuid NOT NULL, review_item_id uuid NOT NULL,
      import_job_id uuid NOT NULL,
      command_sha256 varchar(64) NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$'),
      document jsonb NOT NULL CHECK(jsonb_typeof(document)='object'),
      PRIMARY KEY(game_id,idempotency_key)) PARTITION BY LIST(game_id)""")
    op.execute(
        "CREATE INDEX ix_quality_member_live_source ON "
        "game_data_v2.grid_quality_measurement_members(game_id,live_source_image_id)"
    )
    for table in TABLES:
        _protect(table)
    # A partition trigger sees its physical child name. Pass the exact member
    # classification explicitly rather than relying on the child hash name.
    op.execute("""CREATE FUNCTION game_data_v2.grid_quality_immutable_v1()
      RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
      IF TG_ARGV[0]='member' AND TG_OP='UPDATE' THEN
        IF NEW.game_id=OLD.game_id AND NEW.measurement_id=OLD.measurement_id
          AND NEW.source_id=OLD.source_id AND NEW.sample_kind=OLD.sample_kind
          AND NEW.frozen=OLD.frozen
          AND (NEW.live_source_image_id IS NOT DISTINCT FROM OLD.live_source_image_id
            OR NEW.live_source_image_id IS NULL) THEN RETURN NEW; END IF;
      END IF;
      RAISE EXCEPTION 'GRID_QUALITY_IMMUTABLE_HISTORY'; END $$""")
    op.execute("REVOKE ALL ON FUNCTION game_data_v2.grid_quality_immutable_v1() FROM PUBLIC")
    for table in TABLES:
        kind = "member" if table == "grid_quality_measurement_members" else "immutable"
        op.execute(
            f"CREATE TRIGGER grid_quality_immutable BEFORE UPDATE OR DELETE "
            f"ON game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
            f"game_data_v2.grid_quality_immutable_v1('{kind}')"
        )
    op.execute(
        "CREATE INDEX ix_recording_occurrences_game_source "
        "ON public.recording_occurrences(game_id,source_id) WHERE origin='MAIN'"
    )
    op.execute(INSTALL_SOURCE_RECORDING_V2_SQL)
    op.execute(f'ALTER FUNCTION {SOURCE_RECORDING_V2_FUNCTION} OWNER TO "{capability}"')
    op.execute(f"REVOKE ALL ON FUNCTION {SOURCE_RECORDING_V2_FUNCTION} FROM PUBLIC")
    roles = connection.execute(
        text("""SELECT DISTINCT r.rolname FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
      JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='game_data_v2'
        AND c.relname='source_images'
      AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid<>c.relowner""")
    ).scalars()
    for role in roles:
        if role != capability:
            enforce_recording_permissions(connection, role)
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v15',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v14'"
    )
    for table in TABLES:
        op.execute(
            "INSERT INTO public.game_storage_table_manifest "
            f"VALUES('game-data-v2-manifest-v15','{table}','game',TRUE)"
        )
    _manifest(14, 15)


def downgrade() -> None:
    _guard(15)
    op.execute("SET LOCAL row_security=off")
    for table in TABLES:
        op.execute(f"LOCK TABLE game_data_v2.{table} IN ACCESS EXCLUSIVE MODE")
        op.execute(f"""DO $history$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.{table})
          THEN RAISE EXCEPTION 'GRID_QUALITY_DOWNGRADE_HAS_HISTORY'; END IF; END $history$""")
    op.execute(DROP_SOURCE_RECORDING_V2_SQL)
    op.execute("DROP INDEX public.ix_recording_occurrences_game_source")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute("DROP FUNCTION game_data_v2.grid_quality_immutable_v1()")
    _manifest(15, 14)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v15'"
    )
