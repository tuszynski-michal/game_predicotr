"""Photo-only uses extend the private recording registry without inventing recordings."""

TABLE_SQL = r"""
CREATE TABLE public.recording_photo_uses (
 game_id uuid NOT NULL, cohort_id uuid NOT NULL, source_id uuid NOT NULL,
 family_id uuid NOT NULL REFERENCES public.grid_model_families(id),
 import_id uuid NOT NULL, source_sha256 text NOT NULL, pixel_sha256 text NOT NULL,
 role text NOT NULL CHECK(role IN ('TRAIN','VALIDATION','REGRESSION','BUFFER')),
 group_ids uuid[] NOT NULL, range_start bigint, range_end bigint,
 used_in_cohort boolean NOT NULL,
 split_sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(game_id,cohort_id,source_id),
 CHECK(source_sha256~'^[0-9a-f]{64}$' AND pixel_sha256~'^[0-9a-f]{64}$'
 AND split_sha256~'^[0-9a-f]{64}$'));
CREATE INDEX ix_recording_photo_byte ON public.recording_photo_uses(source_sha256);
CREATE INDEX ix_recording_photo_pixel ON public.recording_photo_uses(pixel_sha256);
CREATE INDEX ix_recording_photo_groups ON public.recording_photo_uses USING gin(group_ids);
CREATE TRIGGER recording_photo_immutable BEFORE UPDATE OR DELETE
 ON public.recording_photo_uses FOR EACH ROW EXECUTE FUNCTION public.recording_immutable_v1();
"""

FUNCTION_SQL = r"""
CREATE FUNCTION public.recording_photo_context_v1(wanted uuid, ids uuid[]) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s record; groups uuid[]; roles text[]; photo_roles text[]; allowed text[];
 result jsonb:='[]'; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF ids IS NULL OR cardinality(ids)>200 THEN RAISE EXCEPTION
 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 FOR s IN SELECT id,checksum_sha256,normalized_pixel_checksum_sha256
 FROM game_data_v2.source_images WHERE game_id=wanted AND id=ANY(ids) ORDER BY id LOOP
  SELECT array_agg(DISTINCT o.group_id ORDER BY o.group_id) INTO groups
  FROM public.recording_occurrences o WHERE o.source_sha256=s.checksum_sha256
   OR o.pixel_sha256=s.normalized_pixel_checksum_sha256
   OR (o.game_id=wanted AND o.source_id=s.id);
  groups:=public.recording_closure_v1(COALESCE(groups,'{}'));
  SELECT array_agg(DISTINCT u.role ORDER BY u.role) INTO photo_roles
   FROM public.recording_photo_uses u WHERE u.source_sha256=s.checksum_sha256
    OR u.pixel_sha256=s.normalized_pixel_checksum_sha256 OR u.group_ids && groups
    OR EXISTS(SELECT 1 FROM public.recording_occurrences o WHERE o.group_id=ANY(groups)
     AND (o.source_sha256=u.source_sha256 OR o.pixel_sha256=u.pixel_sha256));
  photo_roles:=COALESCE(photo_roles,'{}');
  SELECT array_agg(DISTINCT role ORDER BY role) INTO roles FROM (
   SELECT h.role FROM public.recording_role_heads h WHERE h.group_id=ANY(groups)
   UNION SELECT e.payload->>'role' FROM public.recording_evidence e
    WHERE e.group_ids && groups AND e.kind IN ('holdout','ancestor','use')
     AND e.payload ? 'role'
   UNION SELECT unnest(photo_roles)
  ) known;
  roles:=COALESCE(roles,'{}');
  allowed:=CASE WHEN cardinality(roles)=0 THEN ARRAY['TRAIN','VALIDATION','REGRESSION']
   WHEN cardinality(roles)=1 AND roles[1] IN ('TRAIN','VALIDATION','REGRESSION')
    THEN roles ELSE '{}' END;
  result:=result||jsonb_build_array(jsonb_build_object('sourceId',s.id,
   'componentIds',to_jsonb(groups),'allowedRoles',to_jsonb(allowed),
   'priorRoles',to_jsonb(roles),'photoRoles',to_jsonb(photo_roles),'proofSha256',public.recording_digest_v1(
    jsonb_build_object('groups',public.recording_proof_v1(groups),'roles',to_jsonb(roles),
     'byte',s.checksum_sha256,'pixel',s.normalized_pixel_checksum_sha256))));
 END LOOP;
 RETURN result;
END $$;

CREATE FUNCTION public.recording_photo_cohort_v1(wanted uuid, req jsonb, actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE header record; plan jsonb; item jsonb; source record; member record;
 context jsonb; desired text; cohort uuid:=(req->>'cohortId')::uuid;
 kind text:=req->>'kind'; minimum record; expected integer; pending jsonb:='[]'; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF kind NOT IN ('register_cohort_use','validate_cohort_use') OR actor IS NULL
 OR actor='' OR length(actor)>64 THEN RAISE EXCEPTION
 'RECORDING_COMMAND_INVALID' USING ERRCODE='22023'; END IF;
 IF kind='register_cohort_use' THEN
  PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 END IF;
 SELECT c.revision,c.status,c.document,c.manifest_sha256 INTO header
 FROM game_data_v2.grid_training_cohorts c
 WHERE c.game_id=wanted AND c.id=cohort;
 IF NOT FOUND OR header.document->>'policyVersion'<>'application-grid-corrections-v1'
 OR header.document->>'mode'<>'grid-only' OR header.manifest_sha256 IS NULL
 OR header.manifest_sha256 IS DISTINCT FROM req->>'manifestSha256'
 OR header.revision IS DISTINCT FROM (req->>'expectedRevision')::integer
 OR (kind='register_cohort_use' AND header.status<>'ready_to_freeze')
 OR (kind='validate_cohort_use' AND header.status<>'frozen') THEN
  RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 plan:=header.document->'photoSplit';
 IF jsonb_typeof(plan->'sources')<>'array' OR jsonb_array_length(plan->'sources')=0
 OR jsonb_array_length(plan->'sources')>5000 THEN RAISE EXCEPTION
 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 expected:=jsonb_array_length(plan->'sources');
 IF expected<>(SELECT count(*) FROM game_data_v2.source_images s
  WHERE s.game_id=wanted AND s.import_job_id IN (SELECT (p->>'importId')::uuid
   FROM jsonb_array_elements(plan->'sources') p)) THEN RAISE EXCEPTION
 'GRID_CORRECTION_POPULATION_CHANGED' USING ERRCODE='40001'; END IF;
 FOR item IN SELECT p FROM jsonb_array_elements(plan->'sources') p LOOP
  SELECT s.* INTO source FROM game_data_v2.source_images s
   WHERE s.game_id=wanted AND s.id=(item->>'sourceId')::uuid;
  IF NOT FOUND OR source.import_job_id IS DISTINCT FROM (item->>'importId')::uuid
   OR source.checksum_sha256 IS DISTINCT FROM item->>'sourceSha256'
   OR source.normalized_pixel_checksum_sha256 IS DISTINCT FROM item->>'pixelSha256' THEN
   RAISE EXCEPTION 'GRID_CORRECTION_POPULATION_CHANGED' USING ERRCODE='40001'; END IF;
  SELECT m.live_source_image_id,m.role,m.frozen INTO member
   FROM game_data_v2.grid_training_cohort_members m
   WHERE m.game_id=wanted AND m.cohort_id=cohort AND m.source_id=source.id;
  IF NOT FOUND OR member.live_source_image_id IS NULL THEN RAISE EXCEPTION
   'SOURCE_REMOVED_NEW_USE_BLOCKED' USING ERRCODE='22023'; END IF;
  desired:=CASE WHEN item->'buffer'='true'::jsonb THEN 'BUFFER'
   ELSE item->>'role' END;
  IF desired IS NULL THEN CONTINUE; END IF;
  IF desired<>'BUFFER' AND member.frozen->'used'='true'::jsonb
   AND (jsonb_typeof(member.frozen->'positions') IS DISTINCT FROM 'array'
   OR jsonb_array_length(member.frozen->'positions')<>9
   OR COALESCE((member.frozen->>'boardEligibleCount')::integer,0) NOT BETWEEN 1 AND 9
   OR (member.frozen->>'boardEligibleCount')::integer<>(SELECT count(*) FROM
    jsonb_array_elements(member.frozen->'positions') p WHERE jsonb_typeof(p->'label')='object')
   OR member.frozen->'recording'->>'qualification' IS DISTINCT FROM 'eligible'
   OR member.frozen->'recording'->>'evidenceLevel' IS DISTINCT FROM 'photo-only') THEN
   RAISE EXCEPTION 'RECORDING_COHORT_USED_INVALID' USING ERRCODE='22023'; END IF;
  context:=public.recording_photo_context_v1(wanted,ARRAY[source.id])->0;
  IF (desired<>'BUFFER' AND (member.role IS DISTINCT FROM desired OR
    NOT (context->'allowedRoles' ? desired))) OR (desired='BUFFER' AND
    jsonb_array_length(context->'priorRoles')>0 AND context->'priorRoles'<>'["BUFFER"]')
   THEN RAISE EXCEPTION 'RECORDING_ROLE_CONFLICT' USING ERRCODE='22023'; END IF;
  IF kind='register_cohort_use' THEN
   IF context->>'proofSha256' IS DISTINCT FROM item->>'registryProofSha256' THEN
    RAISE EXCEPTION 'GRID_CORRECTION_REGISTRY_CHANGED' USING ERRCODE='40001'; END IF;
   pending:=pending||jsonb_build_array(item||jsonb_build_object(
    'desired',desired,'componentIds',context->'componentIds',
    'usedInCohort',COALESCE(member.frozen->'used','false'::jsonb)));
  ELSIF NOT EXISTS(SELECT 1 FROM public.recording_photo_uses u
   WHERE u.game_id=wanted AND u.cohort_id=cohort AND u.source_id=source.id
    AND u.role=desired AND u.split_sha256=plan->>'sha256') THEN
   RAISE EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
 END LOOP;
 FOR minimum IN SELECT r.role,count(m.source_id) photos,
  COALESCE(sum((m.frozen->>'boardEligibleCount')::integer),0) boards
  FROM (VALUES('TRAIN'),('VALIDATION'),('REGRESSION')) r(role)
  LEFT JOIN game_data_v2.grid_training_cohort_members m ON m.game_id=wanted
   AND m.cohort_id=cohort AND m.role=r.role AND m.frozen->'used'='true'::jsonb
  GROUP BY r.role LOOP
  IF minimum.photos<(CASE WHEN minimum.role='TRAIN' THEN 10 ELSE 5 END) OR
   minimum.boards<(CASE WHEN minimum.role='TRAIN' THEN 30 ELSE 15 END) THEN
   RAISE EXCEPTION 'GRID_COHORT_MINIMUM_NOT_MET' USING ERRCODE='22023'; END IF;
 END LOOP;
 -- Check every frozen plan role before adding any use. Otherwise a sibling in
 -- the same session would observe this transaction's first insertion as drift.
 IF kind='register_cohort_use' THEN
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(pending) a,
   jsonb_array_elements(pending) b WHERE a->>'sourceId'<b->>'sourceId'
   AND a->>'desired'<>b->>'desired' AND (a->>'sourceSha256'=b->>'sourceSha256'
    OR a->>'pixelSha256'=b->>'pixelSha256' OR EXISTS(SELECT 1 FROM
     jsonb_array_elements_text(a->'componentIds') g WHERE b->'componentIds' ? g.value))) THEN
   RAISE EXCEPTION 'RECORDING_ROLE_CONFLICT' USING ERRCODE='22023'; END IF;
  FOR item IN SELECT p FROM jsonb_array_elements(pending) p LOOP
   INSERT INTO public.recording_photo_uses(game_id,cohort_id,source_id,family_id,
    import_id,source_sha256,pixel_sha256,role,group_ids,range_start,range_end,split_sha256,
    used_in_cohort)
   VALUES(wanted,cohort,(item->>'sourceId')::uuid,(header.document->>'familyId')::uuid,
    (item->>'importId')::uuid,item->>'sourceSha256',item->>'pixelSha256',item->>'desired',
    ARRAY(SELECT value::uuid FROM jsonb_array_elements_text(item->'componentIds')),
    (item->>'rangeStart')::bigint,(item->>'rangeEnd')::bigint,plan->>'sha256',
    (item->>'usedInCohort')::boolean);
  END LOOP;
 END IF;
 RETURN jsonb_build_object('kind',kind,'cohortId',cohort,'evidenceLevel','photo-only',
  'splitSha256',plan->>'sha256');
END $$;

ALTER FUNCTION public.recording_cohort_command_v3(uuid,jsonb,text)
 RENAME TO recording_cohort_command_legacy_v3;
CREATE FUNCTION public.recording_cohort_command_v3(wanted uuid, req jsonb, actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE m record; context jsonb; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF req->>'kind'<>'validate_cohort_use' THEN
  PERFORM pg_advisory_xact_lock(9910994); PERFORM pg_advisory_xact_lock(9921002);
 END IF;
 IF EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts c
  WHERE c.game_id=wanted AND c.id=(req->>'cohortId')::uuid
  AND c.document->>'policyVersion'='application-grid-corrections-v1') THEN
  RETURN public.recording_photo_cohort_v1(wanted,req,actor);
 END IF;
 FOR m IN SELECT source_id,role FROM game_data_v2.grid_training_cohort_members
  WHERE game_id=wanted AND cohort_id=(req->>'cohortId')::uuid
  AND frozen->'used'='true'::jsonb LOOP
  context:=public.recording_photo_context_v1(wanted,ARRAY[m.source_id])->0;
  -- Only the additive photo reservations constrain legacy. Existing recording
  -- heads/holdouts/ancestry retain the family-aware legacy decision below.
  IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(context->'photoRoles') r
   WHERE r.value IS DISTINCT FROM m.role) THEN RAISE EXCEPTION
   'RECORDING_ROLE_CONFLICT' USING ERRCODE='22023'; END IF;
 END LOOP;
 RETURN public.recording_cohort_command_legacy_v3(wanted,req,actor);
END $$;
"""
