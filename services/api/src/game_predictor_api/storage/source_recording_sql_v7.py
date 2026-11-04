"""New screen correction capability; never replace historical function bodies."""

from .source_recording_sql_v5 import BIND_SQL as V5_BIND
from .source_recording_sql_v6 import PHOTO_SQL as V6_PHOTO


def _replace(sql: str, before: str, after: str) -> str:
    if before not in sql:
        raise ValueError("Historical SQL template changed; review the new capability explicitly.")
    return sql.replace(before, after)


PHOTO_SQL = _replace(
    V6_PHOTO,
    "CREATE OR REPLACE FUNCTION public.recording_photo_cohort_v1(",
    "CREATE FUNCTION public.recording_photo_cohort_v2(",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "header.document->>'policyVersion' NOT IN "
    "('application-grid-corrections-v1','application-grid-corrections-v2')",
    "header.document->>'policyVersion' IS DISTINCT FROM 'application-grid-corrections-v3'",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "header.document->>'mode'<>'grid-only'",
    "header.document->>'mode' IS DISTINCT FROM 'screen+grid'",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "incremental:=header.document->>'policyVersion'='application-grid-corrections-v2';",
    "incremental:=true;",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "  context:=public.recording_photo_context_data_v2(wanted,ARRAY[source.id],",
    """  IF desired IN ('TRAIN','VALIDATION') AND member.frozen->'used'='true'::jsonb
   AND (member.frozen->'screenEligible' IS DISTINCT FROM 'true'::jsonb
    OR member.frozen->>'boardEligibleCount' IS DISTINCT FROM '9') THEN
   RAISE EXCEPTION 'GRID_COHORT_FULL_PHOTO_REQUIRED' USING ERRCODE='22023'; END IF;
  IF desired='REGRESSION' AND member.frozen->'used'='true'::jsonb
   AND member.frozen->'recording'->>'assessmentPolicy'
    IS DISTINCT FROM 'human-labeled-targets-v1' THEN
   RAISE EXCEPTION 'GRID_COHORT_ASSESSMENT_REQUIRED' USING ERRCODE='22023'; END IF;
  context:=public.recording_photo_context_data_v2(wanted,ARRAY[source.id],""",
)

BIND_SQL = _replace(
    V5_BIND, "recording_correction_report_bind_v1(", "recording_correction_report_bind_v2("
)
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v3(", "recording_cohort_command_v4(")
BIND_SQL = _replace(
    BIND_SQL,
    "('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2')",
    "('grid-model-evaluation-read-v4','grid-model-per-game-gate-v3')",
)

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v4(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF NOT EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
  WHERE c.game_id=wanted AND c.id=(req->>'cohortId')::uuid
  AND c.document->>'policyVersion'='application-grid-corrections-v3') THEN
  RETURN public.recording_cohort_command_v3(wanted,req,actor);
 END IF;
 IF req->>'kind'='bind_existing_report' THEN
  RETURN public.recording_correction_report_bind_v2(wanted,req,actor);
 END IF;
 RETURN public.recording_photo_cohort_v2(wanted,req,actor);
END $$;
"""
