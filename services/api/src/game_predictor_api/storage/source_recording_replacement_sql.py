"""Preserve the exact 0175 replacement fence when newer registry SQL is installed."""

from .source_recording_sql_v4 import FUNCTION_SQL as V4_SQL
from .source_recording_sql_v5 import WRAPPER_SQL as V5_WRAPPER

GUARD_SQL = r"""
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


def _replace_once(sql: str, target: str, replacement: str) -> str:
    if sql.count(target) != 1:
        raise RuntimeError("Replacement registry SQL anchor is missing or ambiguous.")
    return sql.replace(target, replacement, 1)


def replacement_guarded_sql(sql: str) -> str:
    scope = " PERFORM public.recording_scope_v1(wanted);"
    return _replace_once(sql, scope, scope + GUARD_SQL)


def replacement_guarded_photo_sql(sql: str) -> str:
    return _replace_once(
        replacement_guarded_sql(sql),
        "WHERE s.game_id=wanted AND s.import_job_id IN",
        "WHERE s.game_id=wanted AND public.source_replacement_source_current_v1("
        "wanted,s.id,s.checksum_sha256) AND s.import_job_id IN",
    )


_photo_start = V4_SQL.index("CREATE FUNCTION public.recording_photo_cohort_v1(")
_photo_end = V4_SQL.index("ALTER FUNCTION public.recording_cohort_command_v3")
REPLACEMENT_V4_SQL = (
    V4_SQL[:_photo_start]
    + replacement_guarded_photo_sql(V4_SQL[_photo_start:_photo_end])
    + V4_SQL[_photo_end:]
)
REPLACEMENT_V5_WRAPPER = replacement_guarded_sql(V5_WRAPPER)
