"""DDL for Alembic 0182; no runtime invocation or operator database access."""

import hashlib

from alembic import op
from sqlalchemy import text

TABLES = ("grid_cell_content_revisions", "grid_cell_content_sessions", "grid_cell_content_commands")


def guard(version: int) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $g$ BEGIN
      IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done')
      THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
      IF EXISTS(SELECT 1 FROM public.game_storage_locations WHERE
        manifest_version<>'game-data-v2-manifest-v{version}' OR store_schema<>'game_data_v2')
      THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $g$""")


def manifest(previous: int, current: int) -> None:
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


def protect(table: str) -> None:
    suffix = hashlib.sha256(table.encode("ascii")).hexdigest()[:12]
    op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
    predicate = "game_id=game_data_v2.current_game_id_v1()"
    op.execute(
        f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
        f"USING({predicate}) WITH CHECK({predicate})"
    )
    op.execute(f"""DO $parts$ DECLARE r record; child text; g record; BEGIN
      FOR r IN SELECT game_id FROM public.game_storage_locations ORDER BY game_id LOOP
        child:='gpv2_'||left(replace(r.game_id::text,'-',''),12)||'_{suffix}';
        EXECUTE format('CREATE TABLE game_data_v2.%I '
          'PARTITION OF game_data_v2.{table} FOR VALUES IN (%L)',child,r.game_id);
        EXECUTE format('ALTER TABLE game_data_v2.%I ENABLE ROW LEVEL SECURITY',child);
        EXECUTE format('ALTER TABLE game_data_v2.%I FORCE ROW LEVEL SECURITY',child);
        EXECUTE format('CREATE POLICY game_scope_v1 ON game_data_v2.%I '
          'USING({predicate}) WITH CHECK({predicate})',child);
      END LOOP;
      FOR g IN SELECT DISTINCT a.grantee,a.privilege_type
        FROM information_schema.role_table_grants a
        WHERE a.table_schema='game_data_v2' AND a.table_name='grid_training_cohort_members'
        AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE') LOOP
        EXECUTE format('GRANT %s ON game_data_v2.{table} TO %I',g.privilege_type,g.grantee);
      END LOOP;
    END $parts$""")


IMMUTABILITY = """
CREATE FUNCTION game_data_v2.grid_content_history_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='UPDATE' AND TG_ARGV[0]='reference' THEN
  IF OLD.live_source_image_id IS NOT NULL AND NEW.live_source_image_id IS NULL
   AND to_jsonb(OLD)-'live_source_image_id'=to_jsonb(NEW)-'live_source_image_id'
   THEN RETURN NEW; END IF;
 ELSIF TG_OP='UPDATE' AND TG_ARGV[0]='session' THEN
  IF OLD.phase<>'frozen' AND NEW.game_id=OLD.game_id AND NEW.id=OLD.id
   AND NEW.cohort_id=OLD.cohort_id AND NEW.document=OLD.document
   AND NEW.revision=OLD.revision+1 THEN
   IF NEW.phase=OLD.phase AND NEW.report IS NOT DISTINCT FROM OLD.report
    AND NOT EXISTS(SELECT 1 FROM jsonb_each(OLD.progress->OLD.phase) prior
      WHERE (NEW.progress->OLD.phase->prior.key) IS DISTINCT FROM prior.value)
    AND NEW.progress-OLD.phase=OLD.progress-OLD.phase THEN RETURN NEW;
   ELSIF OLD.phase='pass1' AND NEW.phase='pass2' AND NEW.progress=OLD.progress
    AND NEW.report IS NULL THEN RETURN NEW;
   ELSIF OLD.phase='pass2' AND NEW.phase='frozen' AND NEW.progress=OLD.progress
    AND NEW.report->>'state'='ready' THEN RETURN NEW; END IF;
  END IF;
 END IF;
 RAISE EXCEPTION 'CONTENT_IMMUTABLE_HISTORY' USING ERRCODE='23514';
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_content_history_v1() FROM PUBLIC;
"""


def upgrade() -> None:
    guard(21)
    base = (
        "game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1() "
        "REFERENCES public.games(id) ON DELETE RESTRICT"
    )
    document = "document jsonb NOT NULL CHECK(jsonb_typeof(document)='object')"
    op.execute(f"""CREATE TABLE game_data_v2.grid_cell_content_revisions(
      {base},pixel_sha256 varchar(64) NOT NULL CHECK(pixel_sha256 ~ '^[0-9a-f]{{64}}$'),
      position_index integer NOT NULL CHECK(position_index BETWEEN 0 AND 8),
      revision integer NOT NULL CHECK(revision>=1),source_id uuid NOT NULL,
      live_source_image_id uuid,document_sha256 varchar(64) NOT NULL
      CHECK(document_sha256 ~ '^[0-9a-f]{{64}}$'),{document},oracle jsonb,
      CHECK(live_source_image_id IS NULL OR live_source_image_id=source_id),
      CHECK(document->>'version'='source-cell-content-v1'),
      CHECK(document#>>'{{reference,gameId}}'=game_id::text),
      CHECK(document#>>'{{source,sourceId}}'=source_id::text),
      CHECK(document#>>'{{reference,sourceRepresentativeSha256}}'=pixel_sha256),
      CHECK((document#>>'{{reference,positionIndex}}')::integer=position_index),
      CHECK((document#>>'{{reference,revision}}')::integer=revision),
      CHECK(jsonb_typeof(document#>'{{reference,cells}}')='array'
        AND jsonb_array_length(document#>'{{reference,cells}}')=15),
      PRIMARY KEY(game_id,pixel_sha256,position_index,revision),
      FOREIGN KEY(game_id,live_source_image_id) REFERENCES game_data_v2.source_images(game_id,id)
        ON DELETE SET NULL(live_source_image_id)) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_cell_content_sessions(
      {base},id uuid NOT NULL,cohort_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>=1),
      phase varchar(16) NOT NULL CHECK(phase IN ('pass1','pass2','frozen')),{document},
      progress jsonb NOT NULL CHECK(jsonb_typeof(progress)='object'
        AND jsonb_typeof(progress->'pass1')='object' AND jsonb_typeof(progress->'pass2')='object'),
      report jsonb,CHECK((phase='frozen')=(report IS NOT NULL)),PRIMARY KEY(game_id,id),
      FOREIGN KEY(game_id,cohort_id) REFERENCES game_data_v2.grid_training_cohorts(game_id,id))
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_cell_content_commands(
      {base},idempotency_key uuid NOT NULL,command_sha256 varchar(64) NOT NULL
      CHECK(command_sha256 ~ '^[0-9a-f]{{64}}$'),{document},PRIMARY KEY(game_id,idempotency_key))
      PARTITION BY LIST(game_id)""")
    op.execute(
        "CREATE INDEX ix_content_source ON "
        "game_data_v2.grid_cell_content_revisions(game_id,source_id)"
    )
    op.execute(
        "CREATE INDEX ix_content_live_source ON "
        "game_data_v2.grid_cell_content_revisions(game_id,live_source_image_id)"
    )
    for table in TABLES:
        protect(table)
    op.execute(IMMUTABILITY)
    for table, kind in zip(TABLES, ("reference", "session", "command"), strict=True):
        op.execute(
            f"CREATE TRIGGER content_immutable BEFORE UPDATE OR DELETE ON game_data_v2.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION game_data_v2.grid_content_history_v1('{kind}')"
        )
    manifest(21, 22)


def downgrade() -> None:
    guard(22)
    if any(
        op.get_bind().scalar(text(f"SELECT EXISTS(SELECT 1 FROM game_data_v2.{table})"))
        for table in TABLES
    ):
        raise RuntimeError("Retained content annotations prevent downgrade.")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute("DROP FUNCTION game_data_v2.grid_content_history_v1()")
    manifest(22, 21)
