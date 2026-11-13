"""Gate v5 binding (D-609): gate v4 and v5 reports, raw or calibrated; history unchanged."""

from .source_recording_sql_v7 import _replace
from .source_recording_sql_v11 import BIND_SQL as V11_BIND

CELL_CUT_POLICY_VERSION = "grid-model-per-game-gate-v5"

BIND_SQL = _replace(
    V11_BIND, "recording_correction_report_bind_v6(", "recording_correction_report_bind_v7("
)
# Validation goes through the newest dispatcher, so every cohort keeps its own rules.
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v8(", "recording_cohort_command_v9(")
BIND_SQL = _replace(
    BIND_SQL,
    "(('grid-model-evaluation-read-v3','grid-model-per-game-gate-v4'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v4'))",
    "(('grid-model-evaluation-read-v3','grid-model-per-game-gate-v4'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v4'),\n"
    " ('grid-model-evaluation-read-v3','grid-model-per-game-gate-v5'),\n"
    " ('grid-model-evaluation-read-v5','grid-model-per-game-gate-v5'))",
)

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v9(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'='bind_existing_report' AND EXISTS(SELECT 1
  FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'policyVersion' IN
   ('grid-model-per-game-gate-v4','grid-model-per-game-gate-v5')) THEN
  RETURN public.recording_correction_report_bind_v7(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v8(wanted,req,actor);
END $$;
"""
