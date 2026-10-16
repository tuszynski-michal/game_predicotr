"""Game-owned immutable grid training cohorts and exact recording uses."""

import hashlib

from alembic import op
from game_predictor_api.storage.source_recording_permissions_v3 import (
    SOURCE_RECORDING_V3_FUNCTIONS,
    enforce_recording_permissions,
    grant_recording_capability_dependencies,
    validate_recording_capability,
)
from game_predictor_api.storage.source_recording_sql_v3 import (
    DROP_SOURCE_RECORDING_V3_SQL,
    INSTALL_SOURCE_RECORDING_V3_SQL,
)
from sqlalchemy import text

revision = "0163_grid_training_cohorts"
down_revision = "0162_grid_quality_measurements"
branch_labels = depends_on = None
TABLES = (
    "grid_training_cohorts",
    "grid_training_cohort_members",
    "grid_training_cohort_pages",
    "grid_training_cohort_commands",
    "grid_training_cohort_events",
    "grid_source_identity_commands",
)
# Each trigger carries a logical classification because partition child names
# are hashes. Events supplement projections; neither substitutes current proof.
NOTICE_TABLES = {
    "source_images": "source",
    "image_source_geometry_revisions": "source_revision",
    "recognized_boards": "board",
    "board_render_manifests": "board_evidence",
    "image_board_geometry_revisions": "board_evidence",
    "image_board_geometry_review_events": "board_evidence",
    "image_board_geometry_pending": "board_evidence",
    "image_board_geometry_pending_events": "board_evidence",
    "image_geometry_correction_reverts": "board_evidence",
    "image_review_items": "review",
    "image_review_resolution_events": "review_evidence",
    "image_sequence_canonical": "owner",
    "image_symbol_review_cells": "cell",
    "image_symbol_review_events": "cell_evidence",
}


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


def _protect(table: str, capability: str) -> None:
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
      AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid<>c.relowner
      AND r.rolname<>'{capability}' LOOP
        EXECUTE format('GRANT %s ON game_data_v2.{table} TO %I',
          grant_row.privilege_type,grant_row.rolname);
      END LOOP;
    END $grants$""")


IMMUTABLE_SQL = r"""
CREATE FUNCTION game_data_v2.grid_cohort_immutable_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 -- Dispatch before planning expressions: NEW/OLD have different row shapes.
 -- Boolean short-circuit cannot protect a missing record attribute at planning.
 IF TG_ARGV[0]='member' THEN
  IF TG_OP='INSERT' THEN
   IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
     WHERE c.game_id=NEW.game_id AND c.id=NEW.cohort_id AND c.status='preparing')
     THEN RETURN NEW; END IF;
  ELSIF TG_OP='UPDATE' THEN
   IF NEW.game_id=OLD.game_id AND NEW.cohort_id=OLD.cohort_id
   AND NEW.source_id=OLD.source_id AND NEW.ordinal=OLD.ordinal
   AND (NEW.role IS NOT DISTINCT FROM OLD.role OR (OLD.role IS NULL
     AND OLD.frozen='{}'::jsonb AND NEW.frozen<>'{}'::jsonb))
   AND (NEW.live_source_image_id IS NOT DISTINCT FROM OLD.live_source_image_id
     OR NEW.live_source_image_id IS NULL)
   AND ((NEW.frozen=OLD.frozen AND NEW.board_ids=OLD.board_ids
     AND NEW.review_ids=OLD.review_ids AND NEW.cell_ids=OLD.cell_ids)
     OR (OLD.frozen='{}'::jsonb AND NEW.frozen<>'{}'::jsonb AND EXISTS(
       SELECT 1 FROM game_data_v2.grid_training_cohorts c WHERE c.game_id=OLD.game_id
       AND c.id=OLD.cohort_id AND c.status='preparing'))) THEN RETURN NEW; END IF;
  END IF;
 ELSIF TG_ARGV[0]='page' THEN
  IF TG_OP='INSERT' THEN
   IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
     WHERE c.game_id=NEW.game_id AND c.id=NEW.cohort_id
     AND ((NEW.kind='capture' AND c.status='preparing') OR (NEW.kind='materialization'
       AND c.status IN ('preview_ready','materializing')))) THEN RETURN NEW; END IF;
  END IF;
 ELSIF TG_ARGV[0]='header' THEN
  IF TG_OP='UPDATE' THEN
   IF OLD.status NOT IN ('frozen','failed','canceled') AND NEW.game_id=OLD.game_id
   AND NEW.id=OLD.id AND NEW.document=OLD.document AND NEW.created_by=OLD.created_by
   AND NEW.created_at=OLD.created_at AND NEW.revision=OLD.revision+1
   AND (OLD.manifest_sha256 IS NULL OR (NEW.manifest_sha256=OLD.manifest_sha256
     AND NEW.manifest_path=OLD.manifest_path))
   AND (NEW.status=OLD.status OR NEW.status IN ('failed','canceled')
     OR (OLD.status='preparing' AND NEW.status='preview_ready')
     OR (OLD.status='preview_ready' AND NEW.status='materializing')
     OR (OLD.status='materializing' AND NEW.status='ready_to_freeze')
     OR (OLD.status='ready_to_freeze' AND NEW.status='frozen')) THEN RETURN NEW; END IF;
  END IF;
 END IF;
 RAISE EXCEPTION 'GRID_COHORT_IMMUTABLE_HISTORY' USING ERRCODE='23514';
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_cohort_immutable_v1() FROM PUBLIC;
"""

NOTICE_SQL = r"""
CREATE FUNCTION game_data_v2.grid_cohort_notice_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE before_row jsonb; after_row jsonb; row_value jsonb; gid uuid; sid uuid;
 bid uuid; rid uuid; cid uuid; oldsid uuid; oldbid uuid; oldrid uuid; oldcid uuid;
 classification text:=TG_ARGV[0]; BEGIN
 IF TG_OP<>'INSERT' THEN before_row:=pg_catalog.to_jsonb(OLD); END IF;
 IF TG_OP<>'DELETE' THEN after_row:=pg_catalog.to_jsonb(NEW); END IF;
 row_value:=COALESCE(after_row,before_row); gid:=(row_value->>'game_id')::uuid;
 IF gid IS NULL THEN RAISE EXCEPTION 'GRID_COHORT_NOTICE_GAME_REQUIRED'; END IF;
 IF TG_OP='UPDATE' AND before_row=after_row THEN RETURN NEW; END IF;
 -- Symbol labels and confidence alone do not change geometry evidence.
 IF classification='cell' AND TG_OP='UPDATE'
 AND before_row->'quality_issue' IS NOT DISTINCT FROM after_row->'quality_issue'
 AND before_row->'source_geometry_revision_id' IS NOT DISTINCT FROM
   after_row->'source_geometry_revision_id'
 AND before_row->'approved_source_geometry_revision_id' IS NOT DISTINCT FROM
   after_row->'approved_source_geometry_revision_id'
 AND before_row->'recognized_board_id' IS NOT DISTINCT FROM after_row->'recognized_board_id'
 THEN RETURN NEW; END IF;
 IF classification='cell' AND TG_OP='INSERT'
 AND row_value->>'quality_issue' IS DISTINCT FROM 'grid_issue' THEN RETURN NEW; END IF;
 IF classification='cell_evidence' AND NOT (
   COALESCE(before_row::text,'') LIKE '%grid_issue%'
   OR COALESCE(after_row::text,'') LIKE '%grid_issue%') THEN
   IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
 END IF;
 IF classification='source' THEN sid:=(row_value->>'id')::uuid;
 ELSE sid:=(row_value->>'source_image_id')::uuid; END IF;
 IF classification='board' THEN bid:=(row_value->>'id')::uuid;
 ELSE bid:=COALESCE(row_value->>'recognized_board_id',row_value->>'canonical_board_id')::uuid;
 END IF;
 IF classification='review' THEN rid:=(row_value->>'id')::uuid;
 ELSE rid:=COALESCE(row_value->>'review_item_id',row_value->>'image_review_item_id')::uuid;
 END IF;
 IF classification='cell' THEN cid:=(row_value->>'id')::uuid;
 ELSE cid:=COALESCE(row_value->>'cell_id',row_value->>'symbol_review_cell_id')::uuid; END IF;
 IF before_row IS NOT NULL THEN
   oldsid:=CASE WHEN classification='source' THEN (before_row->>'id')::uuid
     ELSE (before_row->>'source_image_id')::uuid END;
   oldbid:=CASE WHEN classification='board' THEN (before_row->>'id')::uuid
     ELSE COALESCE(before_row->>'recognized_board_id',before_row->>'canonical_board_id')::uuid END;
   oldrid:=CASE WHEN classification='review' THEN (before_row->>'id')::uuid
     ELSE COALESCE(before_row->>'review_item_id',before_row->>'image_review_item_id')::uuid END;
   oldcid:=CASE WHEN classification='cell' THEN (before_row->>'id')::uuid
     ELSE COALESCE(before_row->>'cell_id',before_row->>'symbol_review_cell_id')::uuid END;
 END IF;
 INSERT INTO game_data_v2.grid_training_cohort_events(game_id,id,cohort_id,kind,source_id,
   board_id,review_id,cell_id,document)
 SELECT DISTINCT gid,pg_catalog.gen_random_uuid(),m.cohort_id,'currentness_notice',sid,bid,rid,cid,
   pg_catalog.jsonb_build_object('table',TG_ARGV[1],'operation',TG_OP,
     'classification',classification,'reasonCode',CASE WHEN classification='source'
       AND TG_OP='DELETE' THEN 'SOURCE_REMOVED_NEW_USE_BLOCKED'
       ELSE 'GEOMETRY_EVIDENCE_CHANGED' END)
 FROM game_data_v2.grid_training_cohort_members m WHERE m.game_id=gid AND
 ((sid IS NOT NULL AND m.source_id=sid) OR (bid IS NOT NULL AND m.board_ids @> ARRAY[bid])
 OR (rid IS NOT NULL AND m.review_ids @> ARRAY[rid])
 OR (cid IS NOT NULL AND m.cell_ids @> ARRAY[cid])
 OR (oldsid IS NOT NULL AND m.source_id=oldsid)
 OR (oldbid IS NOT NULL AND m.board_ids @> ARRAY[oldbid])
 OR (oldrid IS NOT NULL AND m.review_ids @> ARRAY[oldrid])
 OR (oldcid IS NOT NULL AND m.cell_ids @> ARRAY[oldcid]));
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_cohort_notice_v1() FROM PUBLIC;
"""


def upgrade() -> None:
    _guard(15)
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    base = (
        "game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1() "
        "REFERENCES public.games(id)"
    )
    cohort_fk = (
        "FOREIGN KEY(game_id,cohort_id) REFERENCES game_data_v2.grid_training_cohorts(game_id,id)"
    )
    document = "document jsonb NOT NULL CHECK(jsonb_typeof(document)='object')"
    sha = "CHECK(command_sha256 ~ '^[0-9a-f]{64}$')"
    op.execute(f"""CREATE TABLE game_data_v2.grid_training_cohorts (
      {base},id uuid NOT NULL,revision integer NOT NULL DEFAULT 1 CHECK(revision>=1),
      status varchar(24) NOT NULL CHECK(status IN ('preparing','preview_ready','materializing',
        'ready_to_freeze','frozen','failed','canceled')),{document},
      manifest_path varchar(1000),manifest_sha256 varchar(64),
      CHECK((manifest_path IS NULL)=(manifest_sha256 IS NULL)),
      CHECK(manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{{64}}$'),
      CHECK(status NOT IN ('ready_to_freeze','frozen') OR manifest_sha256 IS NOT NULL),
      summary jsonb NOT NULL DEFAULT '{{}}' CHECK(jsonb_typeof(summary)='object'),
      created_by varchar(64) NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(game_id,id)) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_training_cohort_members (
      {base},cohort_id uuid NOT NULL,source_id uuid NOT NULL,live_source_image_id uuid,
      ordinal integer NOT NULL CHECK(ordinal>=0),role varchar(16)
        CHECK(role IN ('TRAIN','VALIDATION','REGRESSION')),
      frozen jsonb NOT NULL DEFAULT '{{}}' CHECK(jsonb_typeof(frozen)='object'),
      board_ids uuid[] NOT NULL DEFAULT '{{}}',review_ids uuid[] NOT NULL DEFAULT '{{}}',
      cell_ids uuid[] NOT NULL DEFAULT '{{}}',CHECK(live_source_image_id IS NULL
        OR live_source_image_id=source_id),PRIMARY KEY(game_id,cohort_id,source_id),
      UNIQUE(game_id,cohort_id,ordinal),{cohort_fk},
      FOREIGN KEY(game_id,live_source_image_id) REFERENCES game_data_v2.source_images(game_id,id)
        ON DELETE SET NULL (live_source_image_id)) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_training_cohort_pages (
      {base},cohort_id uuid NOT NULL,kind varchar(16) NOT NULL
        CHECK(kind IN ('capture','materialization')),
      page_index integer NOT NULL CHECK(page_index>=0),
      path varchar(1000) NOT NULL,sha256 varchar(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{{64}}$'),
      {document},PRIMARY KEY(game_id,cohort_id,kind,page_index),{cohort_fk})
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_training_cohort_commands (
      {base},kind varchar(32) NOT NULL,idempotency_key uuid NOT NULL,cohort_id uuid,
      command_sha256 varchar(64) NOT NULL {sha},{document},
      PRIMARY KEY(game_id,kind,idempotency_key),{cohort_fk}) PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_training_cohort_events (
      {base},id uuid NOT NULL,cohort_id uuid NOT NULL,kind varchar(64) NOT NULL,
      source_id uuid,board_id uuid,review_id uuid,cell_id uuid,{document},
      created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(game_id,id),{cohort_fk})
      PARTITION BY LIST(game_id)""")
    op.execute(f"""CREATE TABLE game_data_v2.grid_source_identity_commands (
      {base},idempotency_key uuid NOT NULL,command_sha256 varchar(64) NOT NULL {sha},
      {document},PRIMARY KEY(game_id,idempotency_key)) PARTITION BY LIST(game_id)""")
    for name, columns in (
        ("source", "game_id,source_id"),
        ("live_source", "game_id,live_source_image_id"),
    ):
        op.execute(
            f"CREATE INDEX ix_grid_cohort_{name} ON "
            f"game_data_v2.grid_training_cohort_members({columns})"
        )
    for column in ("board_ids", "review_ids", "cell_ids"):
        op.execute(
            f"CREATE INDEX ix_grid_cohort_{column} ON "
            f"game_data_v2.grid_training_cohort_members USING gin({column})"
        )
    for name, columns in (
        ("event", "game_id,cohort_id,created_at"),
        ("event_source", "game_id,source_id"),
        ("event_board", "game_id,board_id"),
    ):
        op.execute(
            f"CREATE INDEX ix_grid_cohort_{name} ON "
            f"game_data_v2.grid_training_cohort_events({columns})"
        )
    for table in TABLES:
        _protect(table, capability)
    op.execute(IMMUTABLE_SQL)
    for table in TABLES:
        kind = (
            "header"
            if table == TABLES[0]
            else "member"
            if table == TABLES[1]
            else "page"
            if table == TABLES[2]
            else "history"
        )
        operations = (
            "INSERT OR UPDATE OR DELETE" if kind in ("member", "page") else "UPDATE OR DELETE"
        )
        op.execute(
            f"CREATE TRIGGER grid_cohort_immutable BEFORE {operations} "
            f"ON game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
            f"game_data_v2.grid_cohort_immutable_v1('{kind}')"
        )
    op.execute(NOTICE_SQL)
    for table, kind in NOTICE_TABLES.items():
        op.execute(
            f"CREATE TRIGGER grid_cohort_currentness BEFORE INSERT OR UPDATE OR DELETE "
            f"ON game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
            f"game_data_v2.grid_cohort_notice_v1('{kind}','{table}')"
        )
    grant_recording_capability_dependencies(connection)
    op.execute(INSTALL_SOURCE_RECORDING_V3_SQL)
    for signature in SOURCE_RECORDING_V3_FUNCTIONS:
        op.execute(f'ALTER FUNCTION {signature} OWNER TO "{capability}"')
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    roles = connection.execute(
        text("""SELECT DISTINCT r.rolname FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
      JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='game_data_v2'
      AND c.relname='source_images' AND NOT r.rolsuper AND NOT r.rolbypassrls
      AND r.oid<>c.relowner""")
    ).scalars()
    for role in roles:
        if role != capability:
            enforce_recording_permissions(connection, role)
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v16',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v15'"
    )
    for table in TABLES:
        op.execute(
            "INSERT INTO public.game_storage_table_manifest "
            f"VALUES('game-data-v2-manifest-v16','{table}','game',TRUE)"
        )
    _manifest(15, 16)


def downgrade() -> None:
    _guard(16)
    capability = validate_recording_capability(op.get_bind())
    op.execute("SET LOCAL row_security=off")
    for table in TABLES:
        op.execute(f"LOCK TABLE game_data_v2.{table} IN ACCESS EXCLUSIVE MODE")
        op.execute(f"""DO $history$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.{table})
          THEN RAISE EXCEPTION 'GRID_COHORT_DOWNGRADE_HAS_HISTORY'; END IF; END $history$""")
    op.execute("""DO $uses$ BEGIN IF EXISTS(SELECT 1 FROM public.recording_evidence
      WHERE kind='use' AND payload ? 'cohortId') OR EXISTS(SELECT 1 FROM public.recording_commands
      WHERE kind IN ('register_cohort_use','validate_cohort_use','bind_existing_report'))
      THEN RAISE EXCEPTION 'GRID_COHORT_DOWNGRADE_HAS_HISTORY'; END IF; END $uses$""")
    op.execute(DROP_SOURCE_RECORDING_V3_SQL)
    op.execute(
        "REVOKE SELECT (version_id,producer,report_json,report_sha256) "
        f'ON public.grid_model_evaluation_reports FROM "{capability}"'
    )
    for table in NOTICE_TABLES:
        op.execute(f"DROP TRIGGER grid_cohort_currentness ON game_data_v2.{table}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE game_data_v2.{table}")
    op.execute("DROP FUNCTION game_data_v2.grid_cohort_notice_v1()")
    op.execute("DROP FUNCTION game_data_v2.grid_cohort_immutable_v1()")
    _manifest(16, 15)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v16'"
    )
