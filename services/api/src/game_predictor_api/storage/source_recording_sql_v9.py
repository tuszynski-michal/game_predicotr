"""Strict production-content report binding; v1–v5 dispatch stays historical."""

from .source_recording_sql_v7 import _replace
from .source_recording_sql_v8 import BIND_SQL as PREVIOUS_BIND

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v6(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'='bind_existing_report' AND EXISTS(SELECT 1
  FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'schemaVersion'='grid-model-evaluation-read-v6') THEN
  RETURN public.recording_correction_report_bind_v4(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v5(wanted,req,actor);
END $$;
"""

BIND_SQL = _replace(
    PREVIOUS_BIND, "recording_correction_report_bind_v3(", "recording_correction_report_bind_v4("
)
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v5(", "recording_cohort_command_v6(")
# Replace the whole pair set: independently extending either allowlist permits
# a new report to be recorded under an obsolete gate.
BIND_SQL = _replace(
    BIND_SQL,
    "(('grid-model-evaluation-read-v5','grid-model-per-game-gate-v2'),"
    "('grid-model-evaluation-read-v5','grid-model-per-game-gate-v3'),\n"
    " ('grid-model-assigned-comparison-v1','grid-model-assigned-nonregression-v1'))",
    "(('grid-model-evaluation-read-v6','production-cell-per-game-gate-v1'))\n"
    " OR doc->>'ruleVersion' IS DISTINCT FROM 'production-cell-content-evaluation-v1'",
)
