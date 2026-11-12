"""DDL for Alembic 0186 (TASK-1195, D-605); no runtime invocation.

Membership lookups of the cohort currentness trigger move from array
containment on ``grid_training_cohort_members`` (``@>`` is not LEAKPROOF, so
under FORCE ROW LEVEL SECURITY the GIN indexes are unusable and every evidence
row write scanned all members) to equality on a normalized lookup table. The
lookup table is derived from member rows by a trigger, so it cannot drift from
the arrays; one notice is still written per matching member row, exactly as
``grid_cohort_notice_v1`` did. The schema also admits the ``retired`` cohort
status (frozen <-> retired) used by TASK-1196.
"""

import hashlib

from alembic import op
from sqlalchemy import text

REFS = "grid_training_cohort_member_refs"
# Trigger classifications from 0163 (partition child names are hashes).
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
STATUSES = (
    "preparing",
    "preview_ready",
    "materializing",
    "ready_to_freeze",
    "frozen",
    "failed",
    "canceled",
)


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
    """RLS, partitions of existing games and the member table's grantees."""

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


# Lookup pairs of one member row; NULL identifiers never become pairs.
_MEMBER_PAIRS = """
  SELECT 'source'::text AS ref_kind, {row}.source_id AS ref_id
  UNION SELECT 'board', pg_catalog.unnest({row}.board_ids)
  UNION SELECT 'review', pg_catalog.unnest({row}.review_ids)
  UNION SELECT 'cell', pg_catalog.unnest({row}.cell_ids)
"""

REFS_SQL = f"""
CREATE FUNCTION game_data_v2.grid_cohort_member_refs_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='UPDATE' AND NEW.game_id=OLD.game_id AND NEW.cohort_id=OLD.cohort_id
 AND NEW.source_id=OLD.source_id AND NEW.board_ids=OLD.board_ids
 AND NEW.review_ids=OLD.review_ids AND NEW.cell_ids=OLD.cell_ids THEN RETURN NULL; END IF;
 IF TG_OP<>'INSERT' THEN
  DELETE FROM game_data_v2.{REFS} r WHERE r.game_id=OLD.game_id
   AND r.cohort_id=OLD.cohort_id AND r.member_source_id=OLD.source_id;
 END IF;
 -- A retired cohort keeps no lookup pairs (TASK-1196 restores them explicitly).
 IF TG_OP<>'DELETE' AND NOT EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
   WHERE c.game_id=NEW.game_id AND c.id=NEW.cohort_id AND c.status='retired') THEN
  INSERT INTO game_data_v2.{REFS}(game_id,cohort_id,member_source_id,ref_kind,ref_id)
  SELECT NEW.game_id,NEW.cohort_id,NEW.source_id,p.ref_kind,p.ref_id
  FROM ({_MEMBER_PAIRS.format(row="NEW")}) p WHERE p.ref_id IS NOT NULL;
 END IF;
 RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_cohort_member_refs_v1() FROM PUBLIC;

-- Pairs are written only by the member trigger above or by an explicit cohort
-- retirement command (TASK-1196) that sets game_predictor.cohort_refs_command.
CREATE FUNCTION game_data_v2.grid_cohort_refs_guard_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP<>'UPDATE' AND (pg_catalog.pg_trigger_depth()>1 OR
   pg_catalog.current_setting('game_predictor.cohort_refs_command',true)='on') THEN
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
 END IF;
 RAISE EXCEPTION 'GRID_COHORT_REFS_DERIVED_ONLY' USING ERRCODE='23514';
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_cohort_refs_guard_v1() FROM PUBLIC;
"""

# Four primary-key prefix lookups (game_id, ref_kind, ref_id); only LEAKPROOF
# equality, so the index stays usable under FORCE ROW LEVEL SECURITY.
LOOKUP_SQL = " UNION ALL ".join(
    f"SELECT r.cohort_id,r.member_source_id FROM game_data_v2.{REFS} r "
    f"WHERE r.game_id=gid AND r.ref_kind='{kind}' AND r.ref_id IN ({new},{old})"
    for kind, new, old in (
        ("source", "sid", "oldsid"),
        ("board", "bid", "oldbid"),
        ("review", "rid", "oldrid"),
        ("cell", "cid", "oldcid"),
    )
)

# Identical to grid_cohort_notice_v1 (0163) except the membership lookup:
# equality on the lookup table instead of array containment on member rows.
NOTICE_V2_SQL = f"""
CREATE FUNCTION game_data_v2.grid_cohort_notice_v2() RETURNS trigger
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
 -- One notice per matching member row, as in v1 (members are unique per cohort/source).
 INSERT INTO game_data_v2.grid_training_cohort_events(game_id,id,cohort_id,kind,source_id,
   board_id,review_id,cell_id,document)
 SELECT gid,pg_catalog.gen_random_uuid(),hit.cohort_id,'currentness_notice',sid,bid,rid,cid,
   pg_catalog.jsonb_build_object('table',TG_ARGV[1],'operation',TG_OP,
     'classification',classification,'reasonCode',CASE WHEN classification='source'
       AND TG_OP='DELETE' THEN 'SOURCE_REMOVED_NEW_USE_BLOCKED'
       ELSE 'GEOMETRY_EVIDENCE_CHANGED' END)
 FROM (SELECT DISTINCT u.cohort_id,u.member_source_id FROM ({LOOKUP_SQL}) u) hit;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
REVOKE ALL ON FUNCTION game_data_v2.grid_cohort_notice_v2() FROM PUBLIC;
"""

# grid_cohort_immutable_v1 from 0163 plus one header branch: a frozen cohort may
# become retired and a retired one frozen again; nothing else changes.
_IMMUTABLE_HEAD = r"""
CREATE OR REPLACE FUNCTION game_data_v2.grid_cohort_immutable_v1() RETURNS trigger
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
"""
_IMMUTABLE_RETIRE = r"""
   -- TASK-1196: retirement only toggles frozen <-> retired; history stays intact.
   IF ((OLD.status='frozen' AND NEW.status='retired')
     OR (OLD.status='retired' AND NEW.status='frozen'))
   AND NEW.game_id=OLD.game_id AND NEW.id=OLD.id AND NEW.document=OLD.document
   AND NEW.created_by=OLD.created_by AND NEW.created_at=OLD.created_at
   AND NEW.revision=OLD.revision+1 AND NEW.summary=OLD.summary
   AND NEW.manifest_sha256=OLD.manifest_sha256 AND NEW.manifest_path=OLD.manifest_path
   THEN RETURN NEW; END IF;
"""
_IMMUTABLE_TAIL = r"""
  END IF;
 END IF;
 RAISE EXCEPTION 'GRID_COHORT_IMMUTABLE_HISTORY' USING ERRCODE='23514';
END $$;
"""
_TERMINAL = "OLD.status NOT IN ('frozen','failed','canceled')"
# A retired cohort is terminal for the general branch: only retired -> frozen.
IMMUTABLE_WITH_RETIRE_SQL = (
    _IMMUTABLE_HEAD.replace(_TERMINAL, "OLD.status NOT IN ('frozen','failed','canceled','retired')")
    + _IMMUTABLE_RETIRE
    + _IMMUTABLE_TAIL
)
IMMUTABLE_ORIGINAL_SQL = _IMMUTABLE_HEAD + _IMMUTABLE_TAIL
assert _TERMINAL in _IMMUTABLE_HEAD and "'retired')" in IMMUTABLE_WITH_RETIRE_SQL


def _status_check(statuses: tuple[str, ...]) -> None:
    """Replace the header status CHECK (auto-named in 0163) on parent and partitions."""

    allowed = ",".join(f"''{status}''" for status in statuses)
    op.execute(f"""DO $s$ DECLARE c record; BEGIN
      FOR c IN SELECT conname FROM pg_constraint WHERE contype='c'
        AND conrelid='game_data_v2.grid_training_cohorts'::regclass
        AND pg_get_constraintdef(oid) LIKE '%status%preparing%' LOOP
        EXECUTE format('ALTER TABLE game_data_v2.grid_training_cohorts DROP CONSTRAINT %I',
          c.conname);
      END LOOP;
      EXECUTE 'ALTER TABLE game_data_v2.grid_training_cohorts ADD CONSTRAINT '
        || 'ck_grid_training_cohorts_status CHECK(status IN ({allowed}))';
    END $s$""")


def _notice_triggers(function: str) -> None:
    for table, kind in NOTICE_TABLES.items():
        op.execute(f"DROP TRIGGER grid_cohort_currentness ON game_data_v2.{table}")
        op.execute(
            f"CREATE TRIGGER grid_cohort_currentness BEFORE INSERT OR UPDATE OR DELETE "
            f"ON game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
            f"game_data_v2.{function}('{kind}','{table}')"
        )


BACKFILL_SQL = f"""
INSERT INTO game_data_v2.{REFS}(game_id,cohort_id,member_source_id,ref_kind,ref_id)
SELECT m.game_id,m.cohort_id,m.source_id,p.ref_kind,p.ref_id
FROM game_data_v2.grid_training_cohort_members m
CROSS JOIN LATERAL ({_MEMBER_PAIRS.format(row="m")}) p
WHERE p.ref_id IS NOT NULL
"""

# Every derived pair exists and nothing else does (both directions).
VERIFY_SQL = f"""
DO $v$ BEGIN
  IF EXISTS(
    (SELECT m.game_id,m.cohort_id,m.source_id,p.ref_kind,p.ref_id
     FROM game_data_v2.grid_training_cohort_members m
     CROSS JOIN LATERAL ({_MEMBER_PAIRS.format(row="m")}) p WHERE p.ref_id IS NOT NULL
     EXCEPT SELECT game_id,cohort_id,member_source_id,ref_kind,ref_id
     FROM game_data_v2.{REFS})
    UNION ALL
    (SELECT game_id,cohort_id,member_source_id,ref_kind,ref_id FROM game_data_v2.{REFS}
     EXCEPT SELECT m.game_id,m.cohort_id,m.source_id,p.ref_kind,p.ref_id
     FROM game_data_v2.grid_training_cohort_members m
     CROSS JOIN LATERAL ({_MEMBER_PAIRS.format(row="m")}) p WHERE p.ref_id IS NOT NULL))
  THEN RAISE EXCEPTION 'GRID_COHORT_REFS_BACKFILL_MISMATCH'; END IF;
END $v$
"""


def upgrade() -> None:
    guard(22)
    op.execute(f"""CREATE TABLE game_data_v2.{REFS}(
      game_id uuid NOT NULL DEFAULT game_data_v2.current_game_id_v1()
        REFERENCES public.games(id) ON DELETE RESTRICT,
      cohort_id uuid NOT NULL,member_source_id uuid NOT NULL,
      ref_kind varchar(8) NOT NULL CHECK(ref_kind IN ('source','board','review','cell')),
      ref_id uuid NOT NULL,
      PRIMARY KEY(game_id,ref_kind,ref_id,cohort_id,member_source_id),
      FOREIGN KEY(game_id,cohort_id) REFERENCES game_data_v2.grid_training_cohorts(game_id,id))
      PARTITION BY LIST(game_id)""")
    op.execute(
        f"CREATE INDEX ix_grid_cohort_refs_member ON game_data_v2.{REFS}"
        "(game_id,cohort_id,member_source_id)"
    )
    protect(REFS)
    op.execute(REFS_SQL)
    op.execute(
        f"CREATE TRIGGER grid_cohort_refs_guard BEFORE INSERT OR UPDATE OR DELETE "
        f"ON game_data_v2.{REFS} FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.grid_cohort_refs_guard_v1()"
    )
    op.execute(
        "CREATE TRIGGER grid_cohort_member_refs AFTER INSERT OR UPDATE OR DELETE "
        "ON game_data_v2.grid_training_cohort_members FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.grid_cohort_member_refs_v1()"
    )
    # Backfill as the owner: one statement per pass, bounded explicitly.
    op.execute("SET LOCAL statement_timeout='900s'")
    op.execute("SET LOCAL row_security=off")
    op.execute("SELECT set_config('game_predictor.cohort_refs_command','on',true)")
    op.execute(BACKFILL_SQL)
    op.execute(VERIFY_SQL)
    op.execute("SELECT set_config('game_predictor.cohort_refs_command','',true)")
    op.execute(f"ANALYZE game_data_v2.{REFS}")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(NOTICE_V2_SQL)
    _notice_triggers("grid_cohort_notice_v2")
    _status_check((*STATUSES, "retired"))
    op.execute(IMMUTABLE_WITH_RETIRE_SQL)
    manifest(22, 23)


def downgrade() -> None:
    guard(23)
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts WHERE status='retired')"
        )
    ):
        raise RuntimeError("A retired grid cohort prevents downgrade; restore it first.")
    op.execute(IMMUTABLE_ORIGINAL_SQL)
    _status_check(STATUSES)
    _notice_triggers("grid_cohort_notice_v1")
    op.execute("DROP FUNCTION game_data_v2.grid_cohort_notice_v2()")
    op.execute("DROP TRIGGER grid_cohort_member_refs ON game_data_v2.grid_training_cohort_members")
    op.execute(f"DROP TABLE game_data_v2.{REFS}")
    op.execute("DROP FUNCTION game_data_v2.grid_cohort_member_refs_v1()")
    op.execute("DROP FUNCTION game_data_v2.grid_cohort_refs_guard_v1()")
    manifest(23, 22)
