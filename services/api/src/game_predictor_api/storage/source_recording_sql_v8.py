"""Purpose-aware capability using the existing immutable recording ledger."""

from .source_recording_sql_v5 import BIND_SQL as V5_BIND
from .source_recording_sql_v6 import CONTEXT_SQL as V6_CONTEXT
from .source_recording_sql_v7 import PHOTO_SQL as V7_PHOTO
from .source_recording_sql_v7 import _replace

TABLE_SQL = r"""
ALTER TABLE public.recording_photo_uses ADD COLUMN validation_purpose text
 CHECK(validation_purpose IS NULL OR (role='VALIDATION' AND validation_purpose IN ('A','B')));
CREATE INDEX ix_recording_photo_purpose ON public.recording_photo_uses(validation_purpose)
 WHERE validation_purpose IS NOT NULL;
CREATE INDEX ix_recording_diagnostic_byte ON public.recording_evidence((payload->>'sourceSha256'))
 WHERE kind='use' AND payload->>'purpose'='diagnostic_comparison';
CREATE INDEX ix_recording_diagnostic_pixel ON public.recording_evidence((payload->>'pixelSha256'))
 WHERE kind='use' AND payload->>'purpose'='diagnostic_comparison';
CREATE UNIQUE INDEX ix_recording_diagnostic_binding ON public.recording_evidence
 ((payload->>'deduplicationKey'),(payload->>'recordSha256'))
 WHERE kind='use' AND payload->>'purpose'='diagnostic_comparison';
"""

# Freeze the original SQL JSON projection, including NULLs and its key spelling.
# v7 calls this same v2 context; neither historical cohort body is reinterpreted.
_USE_COLUMNS = (
    "game_id",
    "cohort_id",
    "source_id",
    "family_id",
    "import_id",
    "source_sha256",
    "pixel_sha256",
    "role",
    "group_ids",
    "range_start",
    "range_end",
    "used_in_cohort",
    "split_sha256",
    "reservation_policy",
)
_RELEASE_COLUMNS = (
    "game_id",
    "cohort_id",
    "source_id",
    "released_by_game",
    "released_by_cohort",
    "split_sha256",
    "actor",
)


def _projection(alias: str, columns: tuple[str, ...]) -> str:
    return "jsonb_build_object(" + ",".join(f"'{key}',{alias}.{key}" for key in columns) + ")"


LEGACY_CONTEXT_SQL = _replace(V6_CONTEXT, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
LEGACY_CONTEXT_SQL = _replace(
    LEGACY_CONTEXT_SQL, "to_jsonb(u)-'created_at'", _projection("u", _USE_COLUMNS)
)
LEGACY_CONTEXT_SQL = _replace(
    LEGACY_CONTEXT_SQL, "to_jsonb(r)-'created_at'", _projection("r", _RELEASE_COLUMNS)
)

CONTEXT_SQL = V6_CONTEXT[
    : V6_CONTEXT.index("CREATE OR REPLACE FUNCTION public.recording_photo_context_v1")
]
CONTEXT_SQL = _replace(
    CONTEXT_SQL, "recording_photo_context_data_v2(", "recording_photo_context_data_v3("
)
CONTEXT_SQL = _replace(
    CONTEXT_SQL,
    " iteration integer; BEGIN",
    " purposes text[]; exposed boolean; diagnostic jsonb; iteration integer; BEGIN",
)
CONTEXT_SQL = (
    _replace(CONTEXT_SQL, "   ) identities;", "   ) identities;")
    if "   ) identities;" in CONTEXT_SQL
    else CONTEXT_SQL
)
CONTEXT_SQL = _replace(
    CONTEXT_SQL,
    "  result:=result||jsonb_build_array",
    r"""
  SELECT COALESCE(array_agg(DISTINCT u->>'validation_purpose' ORDER BY u->>'validation_purpose')
   FILTER(WHERE u->>'validation_purpose' IS NOT NULL),'{}') INTO purposes
   FROM jsonb_array_elements(uses) u WHERE u->>'role'='VALIDATION';
  exposed:=EXISTS(SELECT 1 FROM jsonb_array_elements(uses) u WHERE u->>'role'='VALIDATION'
    AND COALESCE(u->>'validation_purpose','A')='A')
   OR EXISTS(SELECT 1 FROM public.recording_evidence e WHERE e.group_ids && groups
    AND e.kind IN ('use','ancestor','holdout') AND e.payload->>'role'='VALIDATION'
    AND COALESCE(e.payload->>'validationPurpose','A')='A')
   OR EXISTS(SELECT 1 FROM public.recording_role_heads h WHERE h.group_id=ANY(groups)
    AND h.role='VALIDATION');
  SELECT COALESCE(jsonb_agg(jsonb_build_object('id',e.id,'sha256',e.payload_sha256)
   ORDER BY e.id),'[]') INTO diagnostic FROM public.recording_evidence e
   WHERE e.kind='use' AND e.payload->>'purpose'='diagnostic_comparison'
   AND (e.payload->>'sourceSha256'=ANY(bytes) OR e.payload->>'pixelSha256'=ANY(pixels)
    OR e.group_ids && groups OR e.dependency_group_ids && groups);
  result:=result||jsonb_build_array""",
)
CONTEXT_SQL = _replace(
    CONTEXT_SQL,
    "'photoRoles',to_jsonb(photo_roles),'usedTrainLabels',labels,",
    "'photoRoles',to_jsonb(photo_roles),'validationPurposes',to_jsonb(purposes),\n"
    "   'selectionExposed',exposed,'diagnosticExposed',jsonb_array_length(diagnostic)>0,"
    "'usedTrainLabels',labels,",
)
CONTEXT_SQL = _replace(
    CONTEXT_SQL,
    "'uses',uses,'released',released,",
    "'uses',uses,'released',released,'diagnostics',diagnostic,'selectionExposed',exposed,",
)
CONTEXT_SQL = CONTEXT_SQL.replace(
    "e.kind IN ('holdout','ancestor','use')",
    "e.kind IN ('holdout','ancestor','use') "
    "AND COALESCE(e.payload->>'purpose','')<>'diagnostic_comparison'",
)
CONTEXT_SQL += r"""
CREATE FUNCTION public.recording_photo_context_v3(wanted uuid,ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT COALESCE(jsonb_agg(v-'releaseUses'),'[]')
 FROM jsonb_array_elements(public.recording_photo_context_data_v3(wanted,ids,true)) v
$$;
"""

PHOTO_SQL = _replace(V7_PHOTO, "recording_photo_cohort_v2(", "recording_photo_cohort_v3(")
PHOTO_SQL = _replace(
    PHOTO_SQL, "'application-grid-corrections-v3'", "'application-grid-corrections-v4'"
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "header.document->>'mode' IS DISTINCT FROM 'screen+grid'",
    "header.document->>'mode' NOT IN ('grid-only','screen+grid')",
)
PHOTO_SQL = _replace(
    PHOTO_SQL, "recording_photo_context_data_v2(", "recording_photo_context_data_v3("
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "IF desired IN ('TRAIN','VALIDATION') AND",
    "IF header.document->>'mode'='screen+grid' AND (desired='TRAIN' OR\n"
    "   (desired='VALIDATION' AND item->>'validationPurpose'='A')) AND",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "IF desired='REGRESSION' AND",
    "IF (desired='REGRESSION' OR (desired='VALIDATION' AND item->>'validationPurpose'='B')) AND",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "    used_in_cohort,reservation_policy)",
    "    used_in_cohort,reservation_policy,validation_purpose)",
)
PHOTO_SQL = _replace(
    PHOTO_SQL, "ELSE 'legacy-v1' END);", "ELSE 'legacy-v1' END,item->>'validationPurpose');"
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "AND a->>'desired'<>b->>'desired'",
    "AND (a->>'desired',COALESCE(a->>'validationPurpose',''))\n"
    "    IS DISTINCT FROM (b->>'desired',COALESCE(b->>'validationPurpose',''))",
)
PHOTO_SQL = _replace(
    PHOTO_SQL,
    "  IF desired IS NULL THEN CONTINUE; END IF;",
    r"""
  IF desired='VALIDATION' AND (item->>'validationPurpose' NOT IN ('A','B')
   OR item->>'validationPurpose' IS NULL) THEN RAISE EXCEPTION
   'GRID_VALIDATION_PURPOSE_REQUIRED' USING ERRCODE='22023'; END IF;
  IF desired='VALIDATION' AND item->>'validationPurpose'='B'
   AND context->'selectionExposed'='true'::jsonb THEN RAISE EXCEPTION
   'GRID_VALIDATION_SELECTION_EXPOSED' USING ERRCODE='22023'; END IF;
  IF (desired='REGRESSION' OR (desired='VALIDATION' AND item->>'validationPurpose'='B'))
   AND context->'diagnosticExposed'='true'::jsonb THEN RAISE EXCEPTION
   'GRID_VALIDATION_DIAGNOSTIC_EXPOSED' USING ERRCODE='22023'; END IF;
  IF desired IS NULL THEN CONTINUE; END IF;""",
)

# The trigger is an admission fence, not a rewrite of legacy JSON/functions.
# Replaying an existing receipt does not INSERT and retains its exact old result.
FENCE_SQL = r"""
CREATE FUNCTION public.recording_validation_fence_v1() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE context jsonb; BEGIN
 PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 context:=public.recording_photo_context_data_v3(NEW.game_id,ARRAY[NEW.source_id],false)->0;
 IF NEW.role='VALIDATION' AND (
  ((context->'validationPurposes' ? 'B') AND COALESCE(NEW.validation_purpose,'A')<>'B')
  OR (NEW.validation_purpose='B' AND context->'selectionExposed'='true'::jsonb)) THEN
  RAISE EXCEPTION 'GRID_VALIDATION_PURPOSE_CONFLICT' USING ERRCODE='22023'; END IF;
 IF (NEW.role='REGRESSION' OR NEW.validation_purpose='B')
  AND context->'diagnosticExposed'='true'::jsonb THEN
  RAISE EXCEPTION 'GRID_VALIDATION_DIAGNOSTIC_EXPOSED' USING ERRCODE='22023'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recording_validation_admission BEFORE INSERT ON public.recording_photo_uses
 FOR EACH ROW EXECUTE FUNCTION public.recording_validation_fence_v1();

CREATE FUNCTION public.recording_training_scope_v1(wanted uuid,cohort uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE member record; context jsonb; proof jsonb:='[]'; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 FOR member IN SELECT m.source_id,m.role,m.frozen FROM game_data_v2.grid_training_cohort_members m
  WHERE m.game_id=wanted AND m.cohort_id=cohort AND m.frozen->'used'='true'::jsonb
   AND m.role IN ('TRAIN','VALIDATION') ORDER BY m.source_id LOOP
  IF member.role='VALIDATION' AND member.frozen->'recording'->>'validationPurpose'='B'
   AND EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c WHERE c.game_id=wanted
    AND c.id=cohort AND c.document->>'policyVersion'='application-grid-corrections-v4')
   THEN CONTINUE; END IF;
  context:=public.recording_photo_context_data_v3(wanted,ARRAY[member.source_id],false)->0;
  IF context->'validationPurposes' ? 'B' THEN RAISE EXCEPTION
   'GRID_VALIDATION_B_SELECTION_FORBIDDEN' USING ERRCODE='22023'; END IF;
  proof:=proof||jsonb_build_array(jsonb_build_object('sourceId',member.source_id,
   'proofSha256',context->>'proofSha256'));
 END LOOP;
 RETURN jsonb_build_object('cohortId',cohort,'proofSha256',public.recording_digest_v1(proof));
END $$;
CREATE FUNCTION public.recording_legacy_selection_fence_v1() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NEW.kind='use' AND NEW.payload->>'role' IN ('TRAIN','VALIDATION')
  AND NOT NEW.payload ? 'reportId' AND NEW.payload ? 'cohortId' THEN
  PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
  PERFORM public.recording_training_scope_v1((NEW.payload->>'gameId')::uuid,
    (NEW.payload->>'cohortId')::uuid);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recording_legacy_selection_admission BEFORE INSERT ON public.recording_evidence
 FOR EACH ROW EXECUTE FUNCTION public.recording_legacy_selection_fence_v1();
"""

WRAPPER_SQL = r"""
CREATE FUNCTION public.recording_cohort_command_v5(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'='bind_existing_report' AND EXISTS(SELECT 1
  FROM public.grid_model_evaluation_reports r WHERE r.id=(req->>'reportId')::uuid
  AND r.report_json::jsonb->>'schemaVersion'='grid-model-evaluation-read-v5') THEN
  RETURN public.recording_correction_report_bind_v3(wanted,req,actor);
 END IF;
 IF req->>'kind'='register_cohort_use' THEN
  PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
  -- A historical receipt stays byte-identical. New use must pass today's fence.
  IF NOT EXISTS(SELECT 1 FROM public.recording_commands WHERE game_id=wanted
   AND kind=req->>'kind' AND idempotency_key=(req->>'idempotencyKey')::uuid) THEN
   PERFORM public.recording_training_scope_v1(wanted,(req->>'cohortId')::uuid);
  END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
  WHERE c.game_id=wanted AND c.id=(req->>'cohortId')::uuid
   AND c.document->>'policyVersion'='application-grid-corrections-v4')
  AND req->>'kind' IN ('register_cohort_use','validate_cohort_use') THEN
  RETURN public.recording_photo_cohort_v3(wanted,req,actor);
 END IF;
 RETURN public.recording_cohort_command_v4(wanted,req,actor);
END $$;
"""

BIND_SQL = _replace(
    V5_BIND, "recording_correction_report_bind_v1(", "recording_correction_report_bind_v3("
)
BIND_SQL = _replace(BIND_SQL, "recording_cohort_command_v3(", "recording_cohort_command_v5(")
BIND_SQL = _replace(
    BIND_SQL,
    "('grid-model-evaluation-read-v3','grid-model-per-game-gate-v2'),",
    "('grid-model-evaluation-read-v5','grid-model-per-game-gate-v2'),('grid-model-evaluation-read-v5','grid-model-per-game-gate-v3'),",
)

DIAGNOSTIC_SQL = r"""
CREATE FUNCTION public.recording_diagnostic_use_v1(wanted uuid,req jsonb,actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE old public.recording_commands; doc jsonb; source record; groups uuid[];
 key_id uuid:=(req->>'idempotencyKey')::uuid; payload jsonb; receipt jsonb; context jsonb;
 event_id uuid;
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF actor IS NULL OR actor='' OR length(actor)>64 OR key_id IS NULL
 OR jsonb_typeof(req) IS DISTINCT FROM 'object'
 OR NOT req ?& ARRAY['schemaVersion','idempotencyKey','recordJson','recordSha256',
   'presetJson','deduplicationKey'] OR (SELECT count(*) FROM jsonb_object_keys(req))<>6
 OR jsonb_typeof(req->'recordJson') IS DISTINCT FROM 'string'
 OR jsonb_typeof(req->'presetJson') IS DISTINCT FROM 'string'
 OR COALESCE(req->>'recordSha256','') !~ '^[0-9a-f]{64}$'
 OR COALESCE(req->>'deduplicationKey','') !~ '^[0-9a-f]{64}$'
 OR req->>'schemaVersion' IS DISTINCT FROM 'diagnostic-registration-v1'
 OR octet_length(req->>'recordJson')>262144 OR req->>'recordSha256' IS DISTINCT FROM
 encode(sha256(convert_to(req->>'recordJson','UTF8')),'hex')
 OR req->>'deduplicationKey' !~ '^[0-9a-f]{64}$' THEN
 RAISE EXCEPTION 'GRID_DIAGNOSTIC_RECORD_INVALID' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 SELECT * INTO old FROM public.recording_commands WHERE game_id=wanted
  AND kind='diagnostic_registration' AND idempotency_key=key_id;
 IF FOUND THEN
  IF old.command_json IS DISTINCT FROM req THEN RAISE EXCEPTION
   'RECORDING_COMMAND_CONFLICT' USING ERRCODE='23505'; END IF;
  RETURN old.receipt;
 END IF;
 doc:=(req->>'recordJson')::jsonb;
 IF doc->>'schema_version' IS DISTINCT FROM 'full-board-input-diagnostic-v1'
 OR jsonb_typeof(doc->'archived_preset') IS DISTINCT FROM 'object'
 OR (req->>'presetJson')::jsonb IS DISTINCT FROM doc->'archived_preset'
 OR doc->'model'->>'preset_sha256' IS DISTINCT FROM
 encode(sha256(convert_to(req->>'presetJson','UTF8')),'hex')
 OR doc->'archived_preset'->'screen' IS DISTINCT FROM doc->'screen_preset'
 OR doc->'archived_preset'->'board' IS DISTINCT FROM doc->'board_preset'
 OR doc->'archived_preset'->>'preprocessing_version'
 IS DISTINCT FROM doc->'model'->>'preprocessing_version'
 OR doc->'model'->>'preprocessing_version' IS DISTINCT FROM 'neural-grid-screen768-board320x192-v1'
 OR doc->'diagnostic_use'->>'purpose' IS DISTINCT FROM 'diagnostic_comparison' THEN
 RAISE EXCEPTION 'GRID_DIAGNOSTIC_RECORD_INVALID' USING ERRCODE='22023'; END IF;
 SELECT s.id,s.checksum_sha256,s.normalized_pixel_checksum_sha256 INTO source
 FROM game_data_v2.source_images s WHERE s.game_id=wanted
  AND s.id=(doc->'source'->>'source_id')::uuid;
 IF NOT FOUND OR source.checksum_sha256 IS DISTINCT FROM doc->'source'->>'source_sha256'
 OR source.normalized_pixel_checksum_sha256
 IS DISTINCT FROM doc->'source'->>'normalized_pixel_sha256'
 THEN RAISE EXCEPTION 'GRID_DIAGNOSTIC_SOURCE_CHANGED' USING ERRCODE='22023'; END IF;
 IF doc->'diagnostic_use'->>'source_id' IS DISTINCT FROM source.id::text
 OR doc->'diagnostic_use'->>'source_sha256' IS DISTINCT FROM source.checksum_sha256
 OR doc->'diagnostic_use'->>'normalized_pixel_sha256'
 IS DISTINCT FROM source.normalized_pixel_checksum_sha256 THEN
 RAISE EXCEPTION 'GRID_DIAGNOSTIC_RECORD_INVALID' USING ERRCODE='22023'; END IF;
 context:=public.recording_photo_context_data_v3(wanted,ARRAY[source.id],false)->0;
 SELECT COALESCE(array_agg(value::uuid),'{}') INTO groups
 FROM jsonb_array_elements_text(context->'componentIds');
 payload:=jsonb_build_object('schemaVersion','diagnostic-registration-v1','gameId',wanted,
  'sourceId',source.id,'sourceSha256',source.checksum_sha256,
  'pixelSha256',source.normalized_pixel_checksum_sha256,'purpose','diagnostic_comparison',
  'recordSha256',req->>'recordSha256','deduplicationKey',req->>'deduplicationKey',
  'sequenceNumber',doc->'sequence_number','positionIndex',doc->'position_index',
  'modelVersionId',doc->'model'->>'version_id','presetSha256',doc->'model'->>'preset_sha256');
 INSERT INTO public.recording_evidence
 (id,kind,group_ids,dependency_group_ids,payload,payload_sha256,actor)
 VALUES(gen_random_uuid(),'use',groups,groups,payload,public.recording_digest_v1(payload),actor)
 ON CONFLICT DO NOTHING RETURNING id INTO event_id;
 IF event_id IS NOT NULL THEN
  PERFORM public.recording_invalidate_dependents_v1(event_id);
  -- Existing report bindings/currentness are the authority. A late discovery
  -- invalidates affected controls without rewriting their historic roles.
  INSERT INTO public.grid_model_evaluation_invalidations(id,report_id,reason,actor)
  SELECT gen_random_uuid(),affected.report_id,'GRID_DIAGNOSTIC_CONTROL_EXPOSED',actor
  FROM (SELECT DISTINCT (e.payload->>'reportId')::uuid report_id
   FROM public.recording_photo_uses u JOIN public.recording_evidence e
    ON e.kind='use' AND e.payload->>'gameId'=u.game_id::text
    AND e.payload->>'cohortId'=u.cohort_id::text AND e.payload ? 'reportId'
   WHERE u.used_in_cohort AND (u.role='REGRESSION' OR u.validation_purpose='B')
    AND (u.group_ids && groups OR context->'aliasComponentIds' ?
     public.recording_digest_v1(jsonb_build_object('kind','photo-byte-alias-v2',
      'identity',u.source_sha256)) OR context->'aliasComponentIds' ?
     public.recording_digest_v1(jsonb_build_object('kind','photo-pixel-alias-v2',
      'identity',u.pixel_sha256)))) affected;
 END IF;
 receipt:=jsonb_build_object('status','registered','recordSha256',req->>'recordSha256',
  'deduplicationKey',req->>'deduplicationKey','sourceId',source.id,'groupIds',groups);
 INSERT INTO public.recording_commands
 (game_id,kind,idempotency_key,command_json,command_sha256,actor,receipt)
 VALUES(wanted,'diagnostic_registration',key_id,req,public.recording_digest_v1(req),actor,receipt);
 RETURN receipt;
END $$;
"""
