"""Noise-tolerant gate v4 binding (D-604); historical binds keep their gates."""

from .source_recording_sql_v5 import BIND_SQL as ORIGINAL_BIND
from .source_recording_sql_v7 import _replace

TOLERANT_POLICY_VERSION = "grid-model-per-game-gate-v4"

BIND_SQL = _replace(
    ORIGINAL_BIND, "recording_correction_report_bind_v1(", "recording_correction_report_bind_v6("
)
# Validation goes through the newest dispatcher, so every cohort keeps its own rules.
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v3(", "recording_cohort_command_v8(")
# Replace the whole pair set: this bind records only gate v4 reports, raw or calibrated.
BIND_SQL = _replace(
    BIND_SQL,
    "(('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2'),\n"
    " ('grid-model-assigned-comparison-v1','grid-model-assigned-nonregression-v1'))",
    "(('grid-model-evaluation-read-v3','grid-model-per-game-gate-v4'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v4'))",
)

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v8(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'='bind_existing_report' AND EXISTS(SELECT 1
  FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'policyVersion'='grid-model-per-game-gate-v4') THEN
  RETURN public.recording_correction_report_bind_v6(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v7(wanted,req,actor);
END $$;
"""
