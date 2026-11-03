"""Replacement currentness functions and recording-use fence; no data mutation."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_sql_v4 import FUNCTION_SQL as PHOTO_SQL
from game_predictor_api.storage.source_recording_sql_v5 import WRAPPER_SQL

revision = "0175_source_replacement_guards"
down_revision = "0174_source_replacement"
branch_labels = None
depends_on = None


def _replace_once(sql: str, target: str, replacement: str) -> str:
    if sql.count(target) != 1:
        raise RuntimeError("Replacement migration SQL anchor is missing or ambiguous.")
    return sql.replace(target, replacement, 1)


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION public.source_replacement_source_current_v1(g uuid,s uuid,h text)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_retired r
 WHERE r.game_id=g AND (r.source_id=s OR r.source_sha256=h))
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.state='reserved' AND (p.new_source_id=s OR p.new_sha256=h))
$$;
CREATE FUNCTION public.source_replacement_current_v1(g uuid,s uuid,h text,n bigint,i uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT public.source_replacement_source_current_v1(g,s,h)
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s AND p.state='reserved')
 AND (NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s)
 OR EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s AND p.sequence_number=n AND p.bound_review_id=i))
 AND NOT EXISTS(
 SELECT 1 FROM game_data_v2.source_replacement_slots r WHERE r.game_id=g
 AND r.sequence_number=n AND NOT COALESCE(r.state='pending_bound'
 AND r.new_source_id=s AND r.new_sha256=h AND r.bound_review_id=i,false))
$$;
CREATE FUNCTION public.source_replacement_excluded_reviews_v1(g uuid)
RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 WITH affected_sources AS (
 SELECT r.source_id AS id FROM game_data_v2.source_replacement_retired r WHERE r.game_id=g
 UNION SELECT s.id FROM game_data_v2.source_replacement_retired r
 JOIN game_data_v2.source_images s ON s.game_id=r.game_id AND s.checksum_sha256=r.source_sha256
 WHERE r.game_id=g
 UNION SELECT p.new_source_id FROM game_data_v2.source_replacement_slots p WHERE p.game_id=g
 UNION SELECT s.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.source_images s ON s.game_id=p.game_id AND s.checksum_sha256=p.new_sha256
 WHERE p.game_id=g AND p.state='reserved'
 ), affected_reviews AS (
 SELECT i.id FROM affected_sources a JOIN game_data_v2.recognized_boards b
 ON b.game_id=g AND b.source_image_id=a.id
 JOIN game_data_v2.image_review_items i ON i.game_id=g AND i.recognized_board_id=b.id
 UNION SELECT i.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.image_review_items i ON i.game_id=p.game_id
 AND i.sequence_number=p.sequence_number WHERE p.game_id=g
 UNION SELECT i.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.recognized_boards b ON b.game_id=p.game_id
 AND b.sequence_number=p.sequence_number
 JOIN game_data_v2.image_review_items i ON i.game_id=g AND i.recognized_board_id=b.id
 WHERE p.game_id=g AND i.sequence_number IS NULL
 )
 SELECT i.id FROM affected_reviews a JOIN game_data_v2.image_review_items i ON i.id=a.id
 JOIN game_data_v2.recognized_boards b ON b.game_id=i.game_id AND b.id=i.recognized_board_id
 JOIN game_data_v2.source_images s ON s.game_id=b.game_id AND s.id=b.source_image_id
 WHERE i.game_id=g
 AND NOT public.source_replacement_current_v1(g,s.id,s.checksum_sha256,
 COALESCE(i.sequence_number,b.sequence_number),i.id)
$$;
""")
    guard = """
 IF req->>'kind'<>'validate_cohort_use' THEN
  PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 END IF;
 PERFORM pg_advisory_xact_lock_shared(
  ('x'||substr(encode(sha256(convert_to(wanted::text||chr(58)||'sequence-ownership','UTF8')),
   'hex'),1,16))::bit(64)::bigint);
 IF NOT EXISTS(SELECT 1 FROM public.recording_commands replacement_command
 WHERE replacement_command.game_id=wanted AND replacement_command.kind=req->>'kind'
 AND replacement_command.idempotency_key=(req->>'idempotencyKey')::uuid)
 AND EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_members replacement_member
 JOIN game_data_v2.source_images replacement_source ON
replacement_source.game_id=replacement_member.game_id AND
replacement_source.id=replacement_member.source_id
 WHERE replacement_member.game_id=wanted AND replacement_member.cohort_id=(req->>'cohortId')::uuid
 AND NOT
public.source_replacement_source_current_v1(wanted,replacement_source.id,replacement_source.checksum_sha256))
THEN
  IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_members replacement_member
   JOIN game_data_v2.source_images replacement_source ON
replacement_source.game_id=replacement_member.game_id AND
replacement_source.id=replacement_member.source_id
   JOIN game_data_v2.source_replacement_retired replacement_retired ON
replacement_retired.game_id=replacement_source.game_id
    AND (replacement_retired.source_id=replacement_source.id OR
replacement_retired.source_sha256=replacement_source.checksum_sha256)
   WHERE replacement_member.game_id=wanted AND
replacement_member.cohort_id=(req->>'cohortId')::uuid) THEN
   RAISE EXCEPTION 'SOURCE_REPLACEMENT_RETIRED' USING ERRCODE='22023';
  END IF;
  RAISE EXCEPTION 'SOURCE_REPLACEMENT_RESERVED' USING ERRCODE='22023';
 END IF;
"""
    scope = " PERFORM public.recording_scope_v1(wanted);"
    op.execute(_replace_once(WRAPPER_SQL, scope, scope + guard))
    photo = PHOTO_SQL[
        PHOTO_SQL.index("CREATE FUNCTION public.recording_photo_cohort_v1(") : PHOTO_SQL.index(
            "ALTER FUNCTION public.recording_cohort_command_v3"
        )
    ]
    photo = _replace_once(photo, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
    photo = _replace_once(photo, scope, scope + guard)
    photo = _replace_once(
        photo,
        "WHERE s.game_id=wanted AND s.import_job_id IN",
        "WHERE s.game_id=wanted AND public.source_replacement_source_current_v1("
        "wanted,s.id,s.checksum_sha256) AND s.import_job_id IN",
    )
    op.execute(photo)
    connection = op.get_bind()
    owner = connection.dialect.identifier_preparer.quote(validate_recording_capability(connection))
    op.execute(
        "GRANT SELECT(game_id,source_id,source_sha256) "
        f"ON game_data_v2.source_replacement_retired TO {owner}"
    )
    op.execute(
        "GRANT SELECT(game_id,new_source_id,new_sha256,state) "
        f"ON game_data_v2.source_replacement_slots TO {owner}"
    )


def downgrade() -> None:
    op.execute(WRAPPER_SQL)
    photo = PHOTO_SQL[
        PHOTO_SQL.index("CREATE FUNCTION public.recording_photo_cohort_v1(") : PHOTO_SQL.index(
            "ALTER FUNCTION public.recording_cohort_command_v3"
        )
    ]
    op.execute(_replace_once(photo, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    op.execute("""
DROP FUNCTION public.source_replacement_excluded_reviews_v1(uuid);
DROP FUNCTION public.source_replacement_current_v1(uuid,uuid,text,bigint,uuid);
DROP FUNCTION public.source_replacement_source_current_v1(uuid,uuid,text);
""")
