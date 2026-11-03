"""Versioned report-v3 binding; existing cohort/recording decisions stay unchanged."""

from .source_recording_sql_v4 import FUNCTION_SQL as V4_SQL

BIND_SQL = r"""
CREATE FUNCTION public.recording_correction_report_bind_v1(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE header record; report record; doc jsonb; previous public.recording_commands;
 cohort uuid:=(req->>'cohortId')::uuid; key_id uuid:=(req->>'idempotencyKey')::uuid;
 result jsonb; validated jsonb; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind' IS DISTINCT FROM 'bind_existing_report' OR key_id IS NULL
 OR actor IS NULL OR actor='' OR length(actor)>64 OR EXISTS(
 SELECT 1 FROM jsonb_object_keys(req) k WHERE k NOT IN
 ('kind','idempotencyKey','cohortId','expectedRevision','manifestSha256','reportId')) THEN
 RAISE EXCEPTION 'RECORDING_COMMAND_INVALID' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 SELECT * INTO previous FROM public.recording_commands
 WHERE game_id=wanted AND kind='bind_existing_report' AND idempotency_key=key_id;
 IF FOUND THEN
  IF previous.command_json IS DISTINCT FROM req THEN RAISE EXCEPTION
   'RECORDING_COMMAND_CONFLICT' USING ERRCODE='23505'; END IF;
  RETURN previous.receipt;
 END IF;
 -- The same wrapper applies all photo reservations and the original legacy
 -- family/holdout checks. No report can bypass its cohort's existing rules.
 validated:=public.recording_cohort_command_v3(wanted,
   (req-'reportId'-'idempotencyKey')||jsonb_build_object('kind','validate_cohort_use'),actor);
 SELECT c.document,c.manifest_sha256 INTO header FROM game_data_v2.grid_training_cohorts c
 WHERE c.game_id=wanted AND c.id=cohort;
 SELECT r.id,r.version_id,r.producer,r.report_json,r.report_sha256 INTO report
 FROM public.grid_model_evaluation_reports r
 WHERE r.id=(req->>'reportId')::uuid;
 IF NOT FOUND OR report.producer IS DISTINCT FROM 'server:grid-model-evaluator-v1'
 OR octet_length(report.report_json)>1048576 OR report.report_sha256 IS DISTINCT FROM
 encode(sha256(convert_to(report.report_json,'UTF8')),'hex') THEN
 RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 doc:=report.report_json::jsonb;
 -- Assigned comparison is separate evidence. Only this local validation view
 -- supplies the candidate's ancestry; the stored report keeps its real baseline.
 IF doc->>'schemaVersion'='grid-model-assigned-comparison-v1' THEN
  SELECT doc||jsonb_build_object('cohorts',jsonb_build_array(doc->'cohort'),
   'familyId',v.family_id,'baseVersionId',v.base_version_id) INTO doc
   FROM public.grid_model_versions v WHERE v.id=report.version_id;
 END IF;
 IF (coalesce(doc->>'schemaVersion',''),coalesce(doc->>'policyVersion','')) NOT IN
 (('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2'),
 ('grid-model-assigned-comparison-v1','grid-model-assigned-nonregression-v1'))
 OR doc->>'producer' IS DISTINCT FROM report.producer
 OR doc->>'versionId' IS DISTINCT FROM report.version_id::text
 OR doc->>'evidenceLevel' IS DISTINCT FROM 'photo-only'
 OR doc->>'familyId' IS DISTINCT FROM header.document->>'familyId'
 OR jsonb_typeof(doc->'cohorts') IS DISTINCT FROM 'array'
 OR NOT EXISTS(SELECT 1 FROM public.grid_model_versions v WHERE v.id=report.version_id
   AND v.manifest_sha256=doc->>'manifestSha256'
   AND v.base_version_id::text=doc->>'baseVersionId')
 OR (SELECT count(*) FROM jsonb_array_elements(doc->'cohorts') c
   WHERE c->>'gameId'=wanted::text AND c->>'cohortId'=cohort::text
   AND c->>'manifestSha256'=header.manifest_sha256)<>1 THEN
 RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 IF header.document->>'baseVersionId' IS DISTINCT FROM doc->>'baseVersionId'
 AND NOT EXISTS(WITH RECURSIVE chain(id,base_version_id,depth) AS (
  SELECT v.id,v.base_version_id,1 FROM public.grid_model_versions v
  WHERE v.id=(doc->>'baseVersionId')::uuid UNION ALL
  SELECT v.id,v.base_version_id,c.depth+1 FROM chain c
  JOIN public.grid_model_versions v ON v.id=c.base_version_id WHERE c.depth<64)
  SELECT 1 FROM chain WHERE id::text=header.document->>'baseVersionId') THEN
 RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 result:=jsonb_build_object('kind','bind_existing_report','cohortId',cohort,
  'manifestSha256',header.manifest_sha256,'reportId',report.id,
  'reportSha256',report.report_sha256,'evidenceLevel','photo-only',
  'cohortProofSha256',public.recording_digest_v1(validated),'statusCode',200);
 INSERT INTO public.recording_commands(game_id,kind,idempotency_key,command_json,
 command_sha256,actor,receipt) VALUES(wanted,'bind_existing_report',key_id,req,
 public.recording_digest_v1(req),actor,result);
 RETURN result;
END $$;
"""

WRAPPER_SQL = (
    V4_SQL[V4_SQL.index("CREATE FUNCTION public.recording_cohort_command_v3(") :]
    .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    .replace(
        " IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c",
        """ IF req->>'kind'='bind_existing_report' AND EXISTS(
  SELECT 1 FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'schemaVersion' IN
   ('grid-model-evaluation-read-v3','grid-model-assigned-comparison-v1')) THEN
  RETURN public.recording_correction_report_bind_v1(wanted,req,actor);
 END IF;
 IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c""",
        1,
    )
)
