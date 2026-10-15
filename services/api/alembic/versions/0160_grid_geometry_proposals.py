"""Retain model candidates and human command outcomes without live image FKs."""

import hashlib

from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v13 import ADDED_GAME_TABLES

revision = "0160_grid_geometry_proposals"
down_revision = "0159_grid_reinference"
branch_labels = depends_on = None
V12, V13 = "game-data-v2-manifest-v12", "game-data-v2-manifest-v13"


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
    _guard(V12)
    op.execute("""CREATE TABLE game_data_v2.grid_geometry_proposals (
      game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id),
      id UUID NOT NULL, target_result_id UUID NOT NULL, operation_id UUID NOT NULL,
      target_ordinal BIGINT NOT NULL, import_job_id UUID NOT NULL, review_item_id UUID NOT NULL,
      state VARCHAR(16) NOT NULL CHECK(state IN ('pending','accepted','rejected','stale')),
      revision INTEGER NOT NULL CHECK(revision >= 1),
      document JSONB NOT NULL CHECK(jsonb_typeof(document)='object'), accepted JSONB,
      CHECK((state='accepted') = (accepted IS NOT NULL)),
      PRIMARY KEY(game_id,id), UNIQUE(game_id,target_result_id),
      UNIQUE(game_id,operation_id,target_ordinal),
      FOREIGN KEY(game_id,target_result_id)
        REFERENCES game_data_v2.grid_reinference_targets(game_id,target_result_id)
        ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute("""CREATE TABLE game_data_v2.grid_geometry_proposal_events (
      game_id UUID NOT NULL DEFAULT game_data_v2.current_game_id_v1() REFERENCES public.games(id),
      id UUID NOT NULL, proposal_id UUID, ordinal INTEGER NOT NULL CHECK(ordinal>=1),
      kind VARCHAR(32) NOT NULL CHECK(kind IN
        ('created','accepted','rejected','stale','command_completed',
         'command_rejected')),
      command_kind VARCHAR(16) NOT NULL CHECK(command_kind IN ('create','accept','reject')),
      idempotency_key UUID NOT NULL, command_sha256 VARCHAR(64) NOT NULL
        CHECK(command_sha256 ~ '^[0-9a-f]{64}$'),
      document JSONB NOT NULL CHECK(jsonb_typeof(document)='object'),
      PRIMARY KEY(game_id,id), UNIQUE(game_id,proposal_id,ordinal),
      CHECK(proposal_id IS NOT NULL OR (kind='command_rejected' AND command_kind='create')),
      FOREIGN KEY(game_id,proposal_id)
        REFERENCES game_data_v2.grid_geometry_proposals(game_id,id) ON DELETE RESTRICT
    ) PARTITION BY LIST(game_id)""")
    op.execute(
        "CREATE UNIQUE INDEX uq_geometry_proposal_create_key ON "
        "game_data_v2.grid_geometry_proposal_events(game_id,idempotency_key) "
        "WHERE command_kind='create'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_geometry_proposal_command_key ON "
        "game_data_v2.grid_geometry_proposal_events"
        "(game_id,proposal_id,command_kind,idempotency_key) WHERE command_kind<>'create'"
    )
    op.execute(
        "CREATE INDEX ix_grid_proposal_review ON "
        "game_data_v2.grid_geometry_proposals(game_id,import_job_id,review_item_id,id)"
    )
    op.execute(
        "CREATE INDEX ix_grid_target_review_candidate ON game_data_v2.grid_reinference_targets"
        "(game_id,(snapshot #>> '{review,id}'),(snapshot #>> '{source,import_job_id}')) "
        "WHERE outcome='proposal_ready'"
    )
    for table in ADDED_GAME_TABLES:
        _protect(table)
    op.execute(
        f"INSERT INTO public.game_storage_table_manifest SELECT '{V13}',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        f"WHERE manifest_version='{V12}'"
    )
    for table in ADDED_GAME_TABLES:
        op.execute(
            f"INSERT INTO public.game_storage_table_manifest VALUES('{V13}','{table}','game',TRUE)"
        )
    _move_manifest(V12, V13)


def downgrade() -> None:
    _guard(V13)
    op.execute("SET LOCAL row_security=off")
    for table in ADDED_GAME_TABLES:
        op.execute(f"LOCK TABLE game_data_v2.{table} IN ACCESS EXCLUSIVE MODE")
        op.execute(
            f"DO $history$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.{table}) THEN "
            "RAISE EXCEPTION 'GRID_PROPOSAL_DOWNGRADE_HAS_HISTORY'; END IF; END $history$"
        )
    for table in reversed(ADDED_GAME_TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute("DROP INDEX game_data_v2.ix_grid_target_review_candidate")
    _move_manifest(V13, V12)
    op.execute(f"DELETE FROM public.game_storage_table_manifest WHERE manifest_version='{V13}'")
