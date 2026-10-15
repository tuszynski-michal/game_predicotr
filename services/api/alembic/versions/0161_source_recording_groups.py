"""Private shared geometry recording registry; provision capability before upgrade."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_SEQUENCES,
    PRIVATE_TABLES,
    RECORDING_FUNCTIONS,
    enforce_recording_permissions,
    grant_recording_capability_dependencies,
    validate_recording_capability,
)
from game_predictor_api.storage.source_recording_sql_v1 import COMMAND_SQL, FUNCTION_SQL, TABLE_SQL
from sqlalchemy import text

revision = "0161_source_recording_groups"
down_revision = "0160_grid_geometry_proposals"
branch_labels = depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
    IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done') THEN
      RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
    IF EXISTS(SELECT 1 FROM public.game_storage_locations
      WHERE manifest_version<>'game-data-v2-manifest-v13' OR store_schema<>'game_data_v2') THEN
      RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF; END $guard$""")
    runtime_roles = list(
        connection.execute(
            text("""SELECT DISTINCT r.rolname FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
    JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='game_data_v2' AND c.relname='source_images'
    AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid<>c.relowner""")
        ).scalars()
    )
    op.execute(TABLE_SQL)
    op.execute(FUNCTION_SQL)
    op.execute(COMMAND_SQL)
    grant_recording_capability_dependencies(connection)
    for table in ("recording_evidence", "recording_commands", "recording_occurrences"):
        op.execute(
            f"""CREATE TRIGGER recording_immutable BEFORE UPDATE OR DELETE ON
            public.{table} FOR EACH ROW EXECUTE FUNCTION
            public.recording_immutable_v1()"""
        )
    # No cluster-global role DDL here. Only already validated role owns new objects.
    for table in PRIVATE_TABLES:
        op.execute(f'ALTER TABLE {table} OWNER TO "{capability}"')
    for sequence in PRIVATE_SEQUENCES:
        op.execute(f'ALTER SEQUENCE {sequence} OWNER TO "{capability}"')
    for signature in RECORDING_FUNCTIONS:
        op.execute(f'ALTER FUNCTION {signature} OWNER TO "{capability}"')
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    for table in (*PRIVATE_TABLES, *PRIVATE_SEQUENCES):
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    for role in runtime_roles:
        if role != capability:
            enforce_recording_permissions(connection, role)
    op.execute(
        """INSERT INTO public.game_storage_table_manifest SELECT
        'game-data-v2-manifest-v14',table_name,ownership,partitioned FROM
        public.game_storage_table_manifest WHERE
        manifest_version='game-data-v2-manifest-v13'"""
    )
    for table in PRIVATE_TABLES:
        connection.execute(
            text(
                """INSERT INTO public.game_storage_table_manifest
                VALUES('game-data-v2-manifest-v14',:table,'shared',FALSE)"""
            ),
            {"table": table.split(".")[1]},
        )
    op.execute(
        """ALTER TABLE public.game_storage_locations DROP CONSTRAINT
        ck_game_storage_locations_manifest_version_v13"""
    )
    op.execute(
        """UPDATE public.game_storage_locations SET
        manifest_version='game-data-v2-manifest-v14',revision=revision+1,updated_at=now()"""
    )
    op.execute(
        """ALTER TABLE public.game_storage_locations ADD CONSTRAINT
        ck_game_storage_locations_manifest_version_v14
        CHECK(manifest_version='game-data-v2-manifest-v14')"""
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
      IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done') THEN
        RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
      IF EXISTS(SELECT 1 FROM public.game_storage_locations WHERE
        manifest_version<>'game-data-v2-manifest-v14' OR store_schema<>'game_data_v2') THEN
        RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF; END $guard$""")
    # A single row anywhere is retained identity, declaration or command history.
    # Lock every table before checking, so a concurrent writer cannot cross the fence.
    for table in PRIVATE_TABLES:
        op.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
    for table in PRIVATE_TABLES:
        op.execute(f"""DO $history$ BEGIN IF EXISTS(SELECT 1 FROM {table}) THEN
          RAISE EXCEPTION 'RECORDING_DOWNGRADE_REFUSED: retained registry history';
          END IF; END $history$""")
    # Drop triggers with their exact tables first. No CASCADE can take unrelated
    # same-prefix functions/overloads or other schema objects with this registry.
    for table in (
        "public.recording_commands",
        "public.recording_role_heads",
        "public.recording_occurrences",
        "public.recording_evidence",
        "public.recording_groups",
    ):
        op.execute(f"DROP TABLE {table}")
    for signature in reversed(RECORDING_FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    # OWNED BY drops the ordinal sequence with recording_evidence.
    for sequence in PRIVATE_SEQUENCES:
        op.execute(f"DROP SEQUENCE IF EXISTS {sequence}")
    op.execute("""ALTER TABLE public.game_storage_locations DROP CONSTRAINT
      ck_game_storage_locations_manifest_version_v14""")
    op.execute("""UPDATE public.game_storage_locations SET
      manifest_version='game-data-v2-manifest-v13',revision=revision+1,updated_at=now()
      WHERE manifest_version='game-data-v2-manifest-v14'""")
    op.execute("""ALTER TABLE public.game_storage_locations ADD CONSTRAINT
      ck_game_storage_locations_manifest_version_v13
      CHECK(manifest_version='game-data-v2-manifest-v13')""")
    op.execute("""DELETE FROM public.game_storage_table_manifest
      WHERE manifest_version='game-data-v2-manifest-v14'""")
