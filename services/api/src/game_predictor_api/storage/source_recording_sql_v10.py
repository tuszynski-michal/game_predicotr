"""Additive new-use material capability; existing cohort functions stay immutable."""

from .source_recording_sql_v5 import BIND_SQL as ORIGINAL_BIND
from .source_recording_sql_v7 import _replace
from .source_recording_sql_v8 import PHOTO_SQL as PREVIOUS_PHOTO

PHOTO_SQL = _replace(PREVIOUS_PHOTO, "recording_photo_cohort_v3(", "recording_photo_cohort_v4(")
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "   AND (member.frozen->'screenEligible' IS DISTINCT FROM 'true'::jsonb",
    "   AND NOT (desired='TRAIN' AND item->'geometryOnlyTraining'='true'::jsonb\n"
    "    AND header.document->'photoSplit'->'contentSampling'->>'policy'\n"
    "     ='full-symbol-content-sampling-v1'\n"
    "    AND member.frozen->'recording'->'geometryOnlyTraining'='true'::jsonb\n"
    "    AND member.frozen->'recording'->>'contentSamplingPolicy'\n"
    "     ='full-symbol-content-sampling-v1') IS TRUE\n"
    "   AND (member.frozen->'screenEligible' IS DISTINCT FROM 'true'::jsonb",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "   releases:=releases||(context->'releaseUses');",
    "   IF item->'newUseExcluded' IS DISTINCT FROM 'true'::jsonb THEN\n"
    "    releases:=releases||(context->'releaseUses'); END IF;",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "   incremental AND kind='register_cohort_use')->0;",
    "   incremental AND (kind='register_cohort_use'\n"
    "    OR COALESCE(item->'newUseExcluded'='true'::jsonb,false)))->0;",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "  IF desired IS NULL THEN CONTINUE; END IF;",
    """  IF item->'newUseExcluded'='true'::jsonb AND (desired IS NOT NULL
   OR member.frozen->'used' IS DISTINCT FROM 'false'::jsonb
   OR context->>'proofSha256' IS DISTINCT FROM item->>'registryProofSha256') THEN
   RAISE EXCEPTION 'GRID_CORRECTION_REGISTRY_CHANGED' USING ERRCODE='40001'; END IF;
  IF desired IS NULL THEN CONTINUE; END IF;""",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    " FOR minimum IN SELECT r.role,count(m.source_id) photos,",
    """ IF header.document->>'mode'='screen+grid' THEN
  IF (SELECT count(*) FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort AND m.role='TRAIN'
   AND m.frozen->'used'='true'::jsonb AND m.frozen->'screenEligible'='true'::jsonb
   AND m.frozen->>'boardEligibleCount'='9')<10
   OR (SELECT count(*) FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort AND m.role='VALIDATION'
   AND m.frozen->'recording'->>'validationPurpose'='A'
   AND m.frozen->'used'='true'::jsonb AND m.frozen->'screenEligible'='true'::jsonb
   AND m.frozen->>'boardEligibleCount'='9')<5 THEN
   RAISE EXCEPTION 'GRID_COHORT_FULL_PHOTO_REQUIRED' USING ERRCODE='22023'; END IF;
 END IF;
 FOR minimum IN SELECT r.role,count(m.source_id) photos,""",
)

BIND_SQL = _replace(
    ORIGINAL_BIND, "recording_correction_report_bind_v1(", "recording_correction_report_bind_v5("
)
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v3(", "recording_cohort_command_v7(")
BIND_SQL = _replace(
    BIND_SQL,
    "('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2'),",
    "('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2'),"
    "('grid-model-evaluation-read-v5','grid-model-per-game-gate-v2'),"
    "('grid-model-evaluation-read-v5','grid-model-per-game-gate-v3'),"
    "('grid-model-evaluation-read-v6','production-cell-per-game-gate-v1'),",
)
BIND_SQL = _replace(
    BIND_SQL,
    " OR doc->>'producer' IS DISTINCT FROM report.producer",
    " OR (doc->>'schemaVersion'='grid-model-evaluation-read-v6' AND "
    "doc->>'ruleVersion' IS DISTINCT FROM 'production-cell-content-evaluation-v1')"
    " OR doc->>'producer' IS DISTINCT FROM report.producer",
)

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v7(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind' IN ('register_cohort_use','validate_cohort_use','bind_existing_report') AND EXISTS(
  SELECT 1 FROM game_data_v2.grid_training_cohorts c WHERE c.game_id=wanted
  AND c.id=(req->>'cohortId')::uuid
  AND c.document->>'policyVersion'='application-grid-corrections-v4'
  AND c.document->'photoSplit'->'learningMaterial'->>'version'
   ='effective-grid-learning-material-v1') THEN
   IF req->>'kind'='bind_existing_report' THEN
    RETURN public.recording_correction_report_bind_v5(wanted,req,actor);
   END IF;
  IF req->>'kind'='register_cohort_use' THEN
   PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
   IF NOT EXISTS(SELECT 1 FROM public.recording_commands WHERE game_id=wanted
    AND kind=req->>'kind' AND idempotency_key=(req->>'idempotencyKey')::uuid) THEN
    PERFORM public.recording_training_scope_v1(wanted,(req->>'cohortId')::uuid);
   END IF;
  END IF;
  RETURN public.recording_photo_cohort_v4(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v6(wanted,req,actor);
END $$;
"""
