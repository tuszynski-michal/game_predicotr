"""Gate v6 binding (D-612): gate v4, v5 and v6 reports, raw or calibrated; history unchanged."""

from .source_recording_sql_v7 import _replace
from .source_recording_sql_v12 import BIND_SQL as V12_BIND

IMPROVEMENT_POLICY_VERSION = "grid-model-per-game-gate-v6"

BIND_SQL = _replace(
    V12_BIND, "recording_correction_report_bind_v7(", "recording_correction_report_bind_v8("
)
# Validation goes through the newest dispatcher, so every cohort keeps its own rules.
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v9(", "recording_cohort_command_v10(")
BIND_SQL = _replace(
    BIND_SQL,
    " ('grid-model-evaluation-read-v3','grid-model-per-game-gate-v5'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v5'))",
    " ('grid-model-evaluation-read-v3','grid-model-per-game-gate-v5'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v5'),\n"
    " ('grid-model-evaluation-read-v3','grid-model-per-game-gate-v6'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v6'))",
)

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v10(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'='bind_existing_report' AND EXISTS(SELECT 1
  FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'policyVersion' IN
   ('grid-model-per-game-gate-v4','grid-model-per-game-gate-v5',
    'grid-model-per-game-gate-v6')) THEN
  RETURN public.recording_correction_report_bind_v8(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v9(wanted,req,actor);
END $$;
"""
