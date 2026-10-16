"""Forward-only own-cohort recording capability installed by Alembic0163."""

INSTALL_SOURCE_RECORDING_V3_SQL = r"""
CREATE FUNCTION public.recording_cohort_page_v3(wanted uuid, cohort uuid, after_source uuid,
    page_limit integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE header jsonb; family uuid; member record; groups uuid[]; gid uuid; view jsonb;
 component uuid[]; items jsonb:='[]'; cursor uuid; reasons jsonb; selected_role text; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF page_limit IS NULL OR page_limit NOT BETWEEN 1 AND 200 THEN
   RAISE EXCEPTION 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT c.document INTO header FROM game_data_v2.grid_training_cohorts c
 WHERE c.game_id=wanted AND c.id=cohort;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 family:=(header->>'familyId')::uuid;
 FOR member IN SELECT m.source_id,m.role FROM game_data_v2.grid_training_cohort_members m
 WHERE m.game_id=wanted AND m.cohort_id=cohort
 AND (after_source IS NULL OR m.source_id>after_source)
 ORDER BY m.source_id LIMIT page_limit LOOP
   SELECT pg_catalog.array_agg(DISTINCT o.group_id ORDER BY o.group_id) INTO groups
   FROM public.recording_occurrences o WHERE o.origin='MAIN' AND o.game_id=wanted
   AND o.source_id=member.source_id AND EXISTS(SELECT 1 FROM
     pg_catalog.jsonb_array_elements(header->'recordings') selected
     WHERE selected->>'groupId'=o.group_id::text);
   IF COALESCE(pg_catalog.jsonb_array_length(header->'recordings'),0)=0 THEN
     items:=items||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
       'sourceId',member.source_id,'groupId',NULL,'role',NULL,'resolutionId',NULL,
       'proofSha256',NULL,'qualification','unresolved','reasonCodes',
       pg_catalog.jsonb_build_array('RECORDING_SELECTION_REQUIRED')));
   ELSIF COALESCE(pg_catalog.cardinality(groups),0)<>1 THEN
     items:=items||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
       'sourceId',member.source_id,'groupId',NULL,'role',member.role,'resolutionId',NULL,
       'proofSha256',NULL,'qualification','unresolved','reasonCodes',
       pg_catalog.jsonb_build_array(CASE WHEN COALESCE(pg_catalog.cardinality(groups),0)=0
         THEN 'RECORDING_MEMBERSHIP_REQUIRED' ELSE 'RECORDING_MEMBERSHIP_AMBIGUOUS' END)));
   ELSE
     gid:=groups[1]; view:=public.recording_group_view_v1(wanted,gid,family);
     SELECT selected->>'role' INTO selected_role FROM
       pg_catalog.jsonb_array_elements(header->'recordings') selected
       WHERE selected->>'groupId'=gid::text;
     component:=public.recording_closure_v1(ARRAY[gid]); reasons:=view->'reasonCodes';
     IF view->>'role' IS DISTINCT FROM selected_role THEN
       reasons:=reasons||pg_catalog.jsonb_build_array('RECORDING_ROLE_CONFLICT'); END IF;
     items:=items||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
       'sourceId',member.source_id,'groupId',gid,'role',CASE WHEN
         pg_catalog.jsonb_array_length(reasons)=0 THEN selected_role ELSE NULL END,
       'resolutionId',view->'resolutionId','proofSha256',public.recording_proof_v1(component),
       'qualification',CASE WHEN pg_catalog.jsonb_array_length(reasons)=0 THEN 'eligible'
         ELSE 'unresolved' END,'reasonCodes',reasons));
   END IF;
   cursor:=member.source_id;
 END LOOP;
 IF pg_catalog.jsonb_array_length(items)<page_limit THEN cursor:=NULL; END IF;
 RETURN pg_catalog.jsonb_build_object('items',items,'nextCursor',cursor);
END $$;

CREATE FUNCTION public.recording_cohort_command_v3(wanted uuid, req jsonb, trusted_actor text)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE k text:=req->>'kind'; key_id uuid:=(req->>'idempotencyKey')::uuid;
 cohort uuid:=(req->>'cohortId')::uuid; header record; previous public.recording_commands;
 member record; pin jsonb; gid uuid; family uuid; component uuid[]; preproof text; view jsonb;
 resolution public.recording_evidence; existing public.recording_evidence;
 use_payload jsonb; result jsonb; use_id uuid; uses jsonb:='[]'; report record; doc jsonb;
 report_id uuid:=(req->>'reportId')::uuid; seen uuid[]:='{}'; minimum record;
 used_members integer:=0; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF k IS NULL OR k NOT IN ('register_cohort_use','validate_cohort_use','bind_existing_report')
 OR (k<>'validate_cohort_use' AND key_id IS NULL)
 OR cohort IS NULL OR trusted_actor IS NULL OR trusted_actor=''
 OR pg_catalog.length(trusted_actor)>64 OR pg_catalog.jsonb_typeof(req)<>'object'
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_object_keys(req) field
   WHERE field NOT IN ('kind','idempotencyKey','cohortId','expectedRevision',
     'manifestSha256','reportId')) THEN
   RAISE EXCEPTION 'RECORDING_COMMAND_INVALID' USING ERRCODE='22023'; END IF;
 IF k<>'validate_cohort_use' THEN
   -- Finalizers already hold these before ownership locks. Read-only current
   -- eligibility does not take locks, replay a stale receipt or write anything.
   PERFORM pg_catalog.pg_advisory_xact_lock(9910994);
   PERFORM pg_catalog.pg_advisory_xact_lock(9921002);
   SELECT * INTO previous FROM public.recording_commands WHERE game_id=wanted AND kind=k
   AND idempotency_key=key_id;
   IF FOUND THEN
     IF previous.command_json IS DISTINCT FROM req THEN RAISE EXCEPTION
       'RECORDING_COMMAND_CONFLICT' USING ERRCODE='23505'; END IF;
     RETURN previous.receipt;
   END IF;
 END IF;
 SELECT c.revision,c.status,c.document,c.manifest_sha256 INTO header
 FROM game_data_v2.grid_training_cohorts c WHERE c.game_id=wanted AND c.id=cohort;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 IF header.revision IS DISTINCT FROM (req->>'expectedRevision')::integer THEN
   RAISE EXCEPTION 'RECORDING_REVISION_CONFLICT' USING ERRCODE='40001'; END IF;
 IF header.manifest_sha256 IS NULL OR header.manifest_sha256!~'^[0-9a-f]{64}$'
 OR header.manifest_sha256 IS DISTINCT FROM req->>'manifestSha256'
 OR (k='register_cohort_use' AND header.status<>'ready_to_freeze')
 OR (k<>'register_cohort_use' AND header.status<>'frozen') THEN
   RAISE EXCEPTION 'RECORDING_COHORT_NOT_READY' USING ERRCODE='22023'; END IF;
 family:=(header.document->>'familyId')::uuid;
 IF family IS NULL OR header.document->>'baseVersionId' IS NULL
 OR header.document->>'policyVersion' IS DISTINCT FROM 'application-grid-cohort-v1'
 OR COALESCE(header.document->>'mode','') NOT IN ('grid-only','screen+grid') OR NOT EXISTS(
   SELECT 1 FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort) THEN
   RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort
   AND pg_catalog.jsonb_typeof(m.frozen->'used') IS DISTINCT FROM 'boolean') THEN
   RAISE EXCEPTION 'RECORDING_COHORT_USED_INVALID' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort AND m.frozen->'used'='true'::jsonb
   AND m.role IS NULL) THEN
   RAISE EXCEPTION 'RECORDING_ROLE_REQUIRED' USING ERRCODE='22023'; END IF;
 -- Excluded members remain immutable metadata. Only true flags can count or
 -- create protection; neither missing roles nor partial control photos count.
 FOR minimum IN SELECT required.role,pg_catalog.count(m.source_id) photos,
   COALESCE(pg_catalog.sum((m.frozen->>'boardEligibleCount')::integer),0) boards,
   pg_catalog.count(m.source_id) FILTER(WHERE m.frozen->'screenEligible'='true'::jsonb) full_photos
   FROM (VALUES('TRAIN'),('VALIDATION'),('REGRESSION')) required(role)
   LEFT JOIN game_data_v2.grid_training_cohort_members m ON m.game_id=wanted
     AND m.cohort_id=cohort AND m.role=required.role AND m.frozen->'used'='true'::jsonb
   GROUP BY required.role LOOP
   IF (minimum.role='TRAIN' AND (minimum.photos<10 OR minimum.boards<30
       OR (header.document->>'mode'='screen+grid' AND minimum.full_photos<10)))
   OR (minimum.role<>'TRAIN' AND (minimum.photos<5 OR minimum.boards<15
       OR minimum.full_photos<5)) THEN RAISE EXCEPTION
     'GRID_COHORT_MINIMUM_NOT_MET' USING ERRCODE='22023'; END IF;
 END LOOP;
 IF report_id IS NOT NULL AND k<>'bind_existing_report' THEN
   RAISE EXCEPTION 'RECORDING_COMMAND_INVALID' USING ERRCODE='22023'; END IF;
 IF k='bind_existing_report' THEN
   SELECT r.id,r.version_id,r.producer,r.report_json,r.report_sha256 INTO report
     FROM public.grid_model_evaluation_reports r WHERE r.id=report_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
   IF pg_catalog.octet_length(report.report_json)>1048576
   OR report.report_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(
     pg_catalog.convert_to(report.report_json,'UTF8')),'hex')
   THEN RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
   doc:=report.report_json::jsonb;
   IF report.producer IS DISTINCT FROM 'server:grid-model-evaluator-v1'
   OR doc->>'producer' IS DISTINCT FROM 'server:grid-model-evaluator-v1'
   OR doc->>'schemaVersion' IS DISTINCT FROM 'grid-model-evaluation-read-v2'
   OR doc->>'policyVersion' IS DISTINCT FROM 'grid-model-per-game-gate-v1' THEN
     RAISE EXCEPTION 'RECORDING_REPORT_PROVENANCE_UNSUPPORTED' USING ERRCODE='22023'; END IF;
   IF pg_catalog.jsonb_typeof(doc->'cohorts') IS DISTINCT FROM 'array' THEN
     RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
   IF pg_catalog.jsonb_array_length(doc->'cohorts') NOT BETWEEN 1 AND 100
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(doc->'cohorts') c
     WHERE pg_catalog.jsonb_typeof(c)<>'object' OR NOT(c ?& ARRAY[
       'gameId','cohortId','manifestSha256'])
       OR (c-ARRAY['gameId','cohortId','manifestSha256'])<>'{}'
       OR COALESCE(c->>'manifestSha256','')!~'^[0-9a-f]{64}$'
       OR COALESCE(c->>'gameId','')!~
         '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR COALESCE(c->>'cohortId','')!~
         '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(doc->'cohorts') c
     GROUP BY c->>'gameId' HAVING pg_catalog.count(*)>1)
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(doc->'cohorts') c
     GROUP BY c->>'cohortId' HAVING pg_catalog.count(*)>1)
   OR EXISTS(SELECT 1 FROM pg_catalog.unnest(ARRAY['versionId','baseVersionId','familyId']) field
     WHERE COALESCE(doc->>field,'')!~
       '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
   OR doc->>'versionId' IS DISTINCT FROM report.version_id::text
   OR doc->>'familyId' IS DISTINCT FROM header.document->>'familyId'
   OR doc->>'baseVersionId' IS DISTINCT FROM header.document->>'baseVersionId'
   OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(doc->'cohorts') c
     WHERE c->>'gameId'=wanted::text AND c->>'cohortId'=cohort::text
       AND c->>'manifestSha256'=header.manifest_sha256) THEN
     RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 END IF;
 FOR member IN SELECT m.source_id,m.role,m.frozen,m.live_source_image_id
 FROM game_data_v2.grid_training_cohort_members m WHERE m.game_id=wanted AND m.cohort_id=cohort
 AND m.frozen->'used'='true'::jsonb
 ORDER BY m.source_id LOOP
   used_members:=used_members+1;
   IF member.role IS NULL THEN RAISE EXCEPTION
     'RECORDING_ROLE_REQUIRED' USING ERRCODE='22023'; END IF;
   IF member.live_source_image_id IS NULL THEN RAISE EXCEPTION
     'SOURCE_REMOVED_NEW_USE_BLOCKED' USING ERRCODE='22023'; END IF;
   IF pg_catalog.jsonb_typeof(member.frozen->'positions') IS DISTINCT FROM 'array' THEN
     RAISE EXCEPTION 'RECORDING_COHORT_USED_INVALID' USING ERRCODE='22023'; END IF;
   IF pg_catalog.jsonb_typeof(member.frozen->'boardEligibleCount') IS DISTINCT FROM 'number'
   OR pg_catalog.jsonb_array_length(member.frozen->'positions')<>9
   OR COALESCE((member.frozen->>'boardEligibleCount')::integer,0) NOT BETWEEN 1 AND 9
   OR (member.frozen->>'boardEligibleCount')::integer<>(SELECT pg_catalog.count(*) FROM
     pg_catalog.jsonb_array_elements(member.frozen->'positions') p
     WHERE pg_catalog.jsonb_typeof(p->'label')='object')
   OR (member.frozen->'screenEligible'='true'::jsonb) IS DISTINCT FROM
     ((member.frozen->>'boardEligibleCount')::integer=9)
   OR ((member.role<>'TRAIN' OR header.document->>'mode'='screen+grid')
     AND member.frozen->'screenEligible' IS DISTINCT FROM 'true'::jsonb)
   OR member.frozen->'recording'->>'qualification' IS DISTINCT FROM 'eligible' THEN
     RAISE EXCEPTION 'RECORDING_COHORT_USED_INVALID' USING ERRCODE='22023'; END IF;
   pin:=member.frozen->'recording'; gid:=(pin->>'groupId')::uuid;
   IF gid IS NULL OR pin->>'role' IS DISTINCT FROM member.role OR NOT EXISTS(
     SELECT 1 FROM public.recording_occurrences o WHERE o.origin='MAIN'
     AND o.game_id=wanted AND o.source_id=member.source_id AND o.group_id=gid)
   OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(header.document->'recordings') r
     WHERE r->>'groupId'=gid::text AND r->>'role'=member.role) THEN RAISE EXCEPTION
     'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
   component:=public.recording_closure_v1(ARRAY[gid]);
   preproof:=public.recording_proof_v1(component);
   view:=public.recording_group_view_v1(wanted,gid,family);
   IF view->>'role' IS DISTINCT FROM member.role
   OR pg_catalog.jsonb_array_length(view->'reasonCodes')<>0
   OR view->>'resolutionId' IS DISTINCT FROM pin->>'resolutionId'
   OR preproof IS DISTINCT FROM pin->>'proofSha256' THEN RAISE EXCEPTION
     'RECORDING_COHORT_PROOF_STALE' USING ERRCODE='40001'; END IF;
   SELECT * INTO resolution FROM public.recording_evidence e
     WHERE e.id=(pin->>'resolutionId')::uuid AND e.kind='resolution';
   IF NOT FOUND OR resolution.dependency_group_ids IS DISTINCT FROM component
   OR resolution.proof_sha256 IS DISTINCT FROM preproof
   OR resolution.payload->>'familyId' IS DISTINCT FROM family::text
   OR resolution.payload->>'baseVersionId' IS DISTINCT FROM header.document->>'baseVersionId'
   OR NOT EXISTS(SELECT 1 FROM public.recording_role_heads h
     WHERE h.group_id=gid AND h.family_id=family AND h.role=member.role) THEN
     RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
   IF gid=ANY(seen) THEN CONTINUE; END IF;
   seen:=pg_catalog.array_append(seen,gid);
   SELECT * INTO existing FROM public.recording_evidence e WHERE e.kind='use'
     AND e.payload->>'gameId'=wanted::text AND e.payload->>'cohortId'=cohort::text
     AND e.payload->>'manifestSha256'=header.manifest_sha256
     AND e.payload->>'resolutionId'=resolution.id::text
     AND e.payload->>'role'=member.role AND e.group_ids=ARRAY[gid]
     AND NOT (e.payload ? 'reportId') ORDER BY e.ordinal LIMIT 1;
   IF k<>'register_cohort_use' AND NOT FOUND THEN RAISE EXCEPTION
     'RECORDING_USE_REQUIRED' USING ERRCODE='22023'; END IF;
   IF k='register_cohort_use' OR k='bind_existing_report' THEN
     use_payload:=pg_catalog.jsonb_build_object('gameId',wanted,'cohortId',cohort,
       'manifestSha256',header.manifest_sha256,'familyId',family,
       'baseVersionId',header.document->>'baseVersionId','resolutionId',resolution.id,
       'role',member.role);
     IF k='bind_existing_report' THEN use_payload:=use_payload||pg_catalog.jsonb_build_object(
       'reportId',report_id,'reportSha256',report.report_sha256); END IF;
     SELECT e.id INTO use_id FROM public.recording_evidence e WHERE e.kind='use'
       AND e.group_ids=ARRAY[gid] AND e.payload=use_payload;
     IF NOT FOUND THEN
       use_id:=pg_catalog.gen_random_uuid();
       INSERT INTO public.recording_evidence(id,kind,group_ids,dependency_group_ids,payload,
         payload_sha256,proof_sha256,actor) VALUES(use_id,'use',ARRAY[gid],component,use_payload,
         public.recording_digest_v1(use_payload),preproof,trusted_actor);
     END IF;
     IF public.recording_proof_v1(component) IS DISTINCT FROM preproof THEN RAISE EXCEPTION
       'RECORDING_PROOF_CHANGED_BY_USE' USING ERRCODE='40001'; END IF;
   ELSE use_id:=existing.id;
   END IF;
   uses:=uses||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('useId',use_id,
     'groupId',gid,'resolutionId',resolution.id,'proofSha256',preproof,'role',member.role));
 END LOOP;
 IF k='validate_cohort_use' THEN
   RETURN pg_catalog.jsonb_build_object('kind',k,'cohortId',cohort,
     'manifestSha256',header.manifest_sha256,'valid',true,'usedMemberCount',used_members,
     'proofSha256',public.recording_digest_v1(uses),'statusCode',200);
 END IF;
 result:=pg_catalog.jsonb_build_object('kind',k,'cohortId',cohort,
   'manifestSha256',header.manifest_sha256,'uses',uses,'reportId',report_id,'statusCode',200);
 INSERT INTO public.recording_commands(game_id,kind,idempotency_key,command_json,
   command_sha256,actor,receipt) VALUES(wanted,k,key_id,req,
   public.recording_digest_v1(req),trusted_actor,result);
 RETURN result;
END $$;
"""

DROP_SOURCE_RECORDING_V3_SQL = """
DROP FUNCTION public.recording_cohort_command_v3(uuid,jsonb,text);
DROP FUNCTION public.recording_cohort_page_v3(uuid,uuid,uuid,integer);
"""
