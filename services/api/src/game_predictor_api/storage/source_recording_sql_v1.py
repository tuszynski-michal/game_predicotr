"""Frozen geometry-recording SQL v1, installed by Alembic0161.

Only shared minimal identities participate in global closure. Game source reads
stay under the nonowner capability role and the caller's unchanged game RLS.
"""

TABLE_SQL = """
CREATE TABLE public.recording_groups (
 id uuid PRIMARY KEY, origin text NOT NULL DEFAULT 'MAIN', game_id uuid,
 external_ref_sha256 text, origin_provider_sha256 text,
 CHECK((origin='MAIN' AND game_id IS NOT NULL AND external_ref_sha256 IS NULL
 AND origin_provider_sha256 IS NULL) OR (origin='LAB_DESCRIPTOR' AND game_id IS NULL
 AND external_ref_sha256 IS NOT NULL AND origin_provider_sha256 IS NOT NULL
 AND external_ref_sha256~'^[0-9a-f]{64}$' AND origin_provider_sha256~'^[0-9a-f]{64}$')),
 UNIQUE(origin_provider_sha256,external_ref_sha256),
 revision bigint NOT NULL CHECK(revision>=1),
 manifest_id uuid NOT NULL UNIQUE, manifest_sha256 text NOT NULL
    CHECK(manifest_sha256~'^[0-9a-f]{64}$'),
 expected_sources integer NOT NULL CHECK(expected_sources>0), page_count integer NOT NULL
    CHECK(page_count>0),
 membership_complete boolean NOT NULL DEFAULT false, declared boolean NOT NULL DEFAULT false,
 independent boolean NOT NULL DEFAULT false,
 origin_import_job_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ix_recording_groups_game ON public.recording_groups(game_id,id);
CREATE TABLE public.recording_occurrences (
 id uuid PRIMARY KEY, group_id uuid NOT NULL REFERENCES public.recording_groups(id),
 origin text NOT NULL DEFAULT 'MAIN', game_id uuid, source_id uuid,
 external_ref_sha256 text, origin_provider_sha256 text,
 CHECK((origin='MAIN' AND game_id IS NOT NULL AND source_id IS NOT NULL
 AND external_ref_sha256 IS NULL AND origin_provider_sha256 IS NULL)
 OR (origin='LAB_DESCRIPTOR' AND game_id IS NULL AND source_id IS NULL
 AND external_ref_sha256 IS NOT NULL AND origin_provider_sha256 IS NOT NULL
 AND external_ref_sha256~'^[0-9a-f]{64}$' AND origin_provider_sha256~'^[0-9a-f]{64}$')),
 UNIQUE(group_id,origin_provider_sha256,external_ref_sha256), source_sha256 text NOT NULL,
 pixel_sha256 text NOT NULL, pixel_algorithm text NOT NULL,
 width integer NOT NULL CHECK(width>0), height integer NOT NULL CHECK(height>0),
 attestation jsonb NOT NULL, UNIQUE(group_id,game_id,source_id),
 CHECK(source_sha256~'^[0-9a-f]{64}$' AND pixel_sha256~'^[0-9a-f]{64}$'));
CREATE INDEX ix_recording_occurrences_group ON public.recording_occurrences(group_id);
CREATE INDEX ix_recording_occurrences_byte ON public.recording_occurrences(source_sha256);
CREATE INDEX ix_recording_occurrences_pixel ON public.recording_occurrences(pixel_algorithm,
    pixel_sha256);
CREATE SEQUENCE public.recording_evidence_ordinal_seq;
CREATE TABLE public.recording_evidence (
 id uuid PRIMARY KEY, ordinal bigint NOT NULL UNIQUE DEFAULT
    nextval('public.recording_evidence_ordinal_seq'),
 kind text NOT NULL CHECK(kind IN ('membership','alias','declaration','retraction','resolution',
    'use','holdout','ancestor','invalidation')),
 group_ids uuid[] NOT NULL, dependency_group_ids uuid[] NOT NULL DEFAULT '{}',
 payload jsonb NOT NULL, payload_sha256 text NOT NULL CHECK(payload_sha256~'^[0-9a-f]{64}$'),
 proof_sha256 text, actor varchar(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
ALTER SEQUENCE public.recording_evidence_ordinal_seq OWNED BY public.recording_evidence.ordinal;
CREATE INDEX ix_recording_evidence_groups ON public.recording_evidence USING gin(group_ids);
CREATE INDEX ix_recording_evidence_dependencies ON public.recording_evidence USING
    gin(dependency_group_ids);
CREATE INDEX ix_recording_evidence_report ON public.recording_evidence((payload->>'reportId'))
    WHERE kind='use';
CREATE TABLE public.recording_role_heads (
 family_id uuid NOT NULL REFERENCES public.grid_model_families(id),
 group_id uuid NOT NULL REFERENCES public.recording_groups(id), revision bigint NOT NULL
    CHECK(revision>=1),
 role text NOT NULL CHECK(role IN ('TRAIN','VALIDATION','REGRESSION')),
 event_id uuid NOT NULL REFERENCES public.recording_evidence(id), PRIMARY KEY(family_id,group_id));
CREATE TABLE public.recording_commands (
 id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
 origin text NOT NULL DEFAULT 'MAIN', game_id uuid, external_ref_sha256 text,
 CHECK((origin='MAIN' AND game_id IS NOT NULL AND external_ref_sha256 IS NULL)
 OR (origin='LAB_DESCRIPTOR' AND game_id IS NULL AND external_ref_sha256 IS NOT NULL
 AND external_ref_sha256~'^[0-9a-f]{64}$')),
 kind text NOT NULL, idempotency_key uuid NOT NULL,
 command_json jsonb NOT NULL, command_sha256 text NOT NULL CHECK(command_sha256~'^[0-9a-f]{64}$'),
 actor varchar(64) NOT NULL, receipt jsonb NOT NULL,
 UNIQUE(game_id,kind,idempotency_key), UNIQUE(external_ref_sha256,kind,idempotency_key));
"""

FUNCTION_SQL = r"""
CREATE FUNCTION public.recording_digest_v1(value jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(value::text,'UTF8')),'hex') $$;

CREATE FUNCTION public.recording_immutable_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 RAISE EXCEPTION 'RECORDING_IMMUTABLE_HISTORY' USING ERRCODE='23514'; END $$;

CREATE FUNCTION public.recording_scope_v1(wanted uuid) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF wanted IS DISTINCT FROM game_data_v2.current_game_id_v1() THEN
   RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.games g JOIN public.game_storage_locations l ON l.game_id=g.id
   WHERE g.id=wanted AND g.code<>'7' AND g.shape_geometry_configuration IN
   ('neural_grid_v3','grid_profile_777_v2','grid_profile_mumie_v1') AND l.status='active') THEN
   RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
END $$;

CREATE FUNCTION public.attest_own_source_ids(wanted uuid, ids uuid[]) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE rows jsonb; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF pg_catalog.cardinality(ids) NOT BETWEEN 1 AND 200 OR
    pg_catalog.cardinality(ids)<>(SELECT pg_catalog.count(DISTINCT x) FROM
    pg_catalog.unnest(ids) x) THEN
   RAISE EXCEPTION 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
   'sourceId',s.id,'byteSha256',s.checksum_sha256,'pixelSha256',s.normalized_pixel_checksum_sha256,
   'pixelAlgorithm','rgb-uint8-v1','width',s.oriented_width,'height',s.oriented_height,
   'adapter',s.normalization_adapter_version,'coordinateSpace',s.coordinate_space)
   ORDER BY s.id) INTO rows FROM game_data_v2.source_images s
 WHERE s.game_id=wanted AND s.id=ANY(ids)
 AND s.coordinate_space='exif-normalized-rgb-pixels-v1'
 AND s.normalization_adapter_version='image-normalization-v2-in-memory-source-v1'
 AND s.normalized_pixel_checksum_sha256~'^[0-9a-f]{64}$'
 AND s.checksum_sha256~'^[0-9a-f]{64}$' AND s.oriented_width>0 AND s.oriented_height>0
 AND EXISTS(SELECT 1 FROM game_data_v2.image_source_geometry_revisions r
   WHERE r.game_id=wanted AND r.source_image_id=s.id
   AND r.source_checksum_sha256=s.checksum_sha256
   AND r.normalized_pixel_checksum_sha256=s.normalized_pixel_checksum_sha256
   AND r.normalization_adapter_version=s.normalization_adapter_version
   AND r.oriented_width=s.oriented_width AND r.oriented_height=s.oriented_height);
 IF COALESCE(pg_catalog.jsonb_array_length(rows),0)<>pg_catalog.cardinality(ids) THEN
   RAISE EXCEPTION 'RECORDING_SOURCE_IDENTITY_UNRESOLVED' USING ERRCODE='22023'; END IF;
 RETURN rows;
END $$;

CREATE FUNCTION public.recording_closure_v1(seeds uuid[]) RETURNS uuid[]
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE reached uuid[]:=seeds; expanded uuid[]; depth integer; BEGIN
 FOR depth IN 1..64 LOOP
   SELECT pg_catalog.array_agg(DISTINCT v ORDER BY v) INTO expanded FROM (
     SELECT pg_catalog.unnest(reached) v
     UNION SELECT pg_catalog.unnest(e.group_ids) FROM public.recording_evidence e
       WHERE e.kind='alias' AND e.group_ids && reached
     UNION SELECT b.group_id FROM public.recording_occurrences a
       JOIN public.recording_occurrences b ON b.source_sha256=a.source_sha256
       WHERE a.group_id=ANY(reached)
     UNION SELECT b.group_id FROM public.recording_occurrences a
       JOIN public.recording_occurrences b ON b.pixel_algorithm=a.pixel_algorithm AND
    b.pixel_sha256=a.pixel_sha256
       WHERE a.group_id=ANY(reached)
   ) members;
   IF pg_catalog.cardinality(expanded)>4096 THEN
     RAISE EXCEPTION 'RECORDING_CLOSURE_UNRESOLVED' USING ERRCODE='22023'; END IF;
   IF expanded=reached OR expanded IS NULL THEN RETURN COALESCE(expanded,'{}'); END IF;
   reached:=expanded;
 END LOOP;
 RAISE EXCEPTION 'RECORDING_CLOSURE_UNRESOLVED' USING ERRCODE='22023';
END $$;

CREATE FUNCTION public.recording_proof_v1(groups uuid[]) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT public.recording_digest_v1(pg_catalog.jsonb_build_object(
 'groups',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(g.id,g.revision,
    g.membership_complete,g.declared,g.independent) ORDER BY g.id),'[]') FROM
    public.recording_groups g WHERE g.id=ANY(groups)),
 'sources',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(o.id,o.group_id,
    o.source_sha256,o.pixel_sha256,o.pixel_algorithm) ORDER BY o.id),'[]') FROM
    public.recording_occurrences o WHERE o.group_id=ANY(groups)),
 'roles',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(h.family_id,
    h.group_id,h.role,h.revision) ORDER BY h.family_id,h.group_id),'[]') FROM
    public.recording_role_heads h WHERE h.group_id=ANY(groups)),
 'protection',(SELECT COALESCE(pg_catalog.jsonb_agg(
    pg_catalog.jsonb_build_array(p.gid,p.role) ORDER BY p.gid,p.role),'[]') FROM (
      SELECT h.group_id gid,h.role FROM public.recording_role_heads h
      WHERE h.group_id=ANY(groups)
      UNION SELECT pg_catalog.unnest(e.group_ids),e.payload->>'role'
      FROM public.recording_evidence e WHERE e.kind IN ('holdout','ancestor','use')
      AND e.group_ids && groups AND e.payload ? 'role'
    ) p WHERE p.gid=ANY(groups)))) $$;

CREATE FUNCTION public.recording_group_view_v1(wanted uuid, gid uuid, family uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g public.recording_groups; component uuid[]; reasons text[]:='{}'; declared_role text;
    resolution uuid; BEGIN
 SELECT * INTO g FROM public.recording_groups WHERE id=gid AND game_id=wanted;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 component:=public.recording_closure_v1(ARRAY[gid]);
 SELECT role INTO declared_role FROM public.recording_role_heads
 WHERE (family IS NULL OR family_id=family) AND group_id=gid ORDER BY family_id LIMIT 1;
 IF EXISTS(SELECT 1 FROM public.recording_groups WHERE id=ANY(component) AND NOT
    membership_complete) THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_MEMBERSHIP_INCOMPLETE'); END IF;
 IF EXISTS(SELECT 1 FROM public.recording_groups WHERE id=ANY(component) AND (NOT declared OR
    NOT independent)) THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_DECLARATION_REQUIRED'); END IF;
 IF (SELECT pg_catalog.count(DISTINCT role) FROM public.recording_role_heads WHERE
    group_id=ANY(component) AND (family IS NULL OR family_id=family))>1 THEN
    reasons:=pg_catalog.array_append(reasons,'RECORDING_ROLE_CONFLICT'); END IF;
 IF declared_role IS NULL THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_ROLE_REQUIRED'); END IF;
 IF declared_role='TRAIN' AND (EXISTS(SELECT 1 FROM public.recording_role_heads WHERE
    group_id=ANY(component) AND role IN ('VALIDATION','REGRESSION')) OR EXISTS(SELECT 1 FROM
    public.recording_evidence WHERE kind IN ('holdout','ancestor','use') AND group_ids &&
    component AND payload->>'role' IN ('VALIDATION','REGRESSION','final_test','unseen_game',
    'Reels','Treasure','declared_holdouts'))) THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_PROTECTED'); END IF;
 IF declared_role IN ('VALIDATION','REGRESSION') AND EXISTS(SELECT 1 FROM
    public.recording_evidence WHERE kind='use' AND group_ids && component AND
    payload->>'role'='TRAIN') THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_ROLE_CONFLICT'); END IF;
 SELECT e.id INTO resolution FROM public.recording_evidence e WHERE e.kind='resolution'
 AND e.group_ids=ARRAY[gid] AND e.payload->>'familyId'=family::text
 AND e.proof_sha256=public.recording_proof_v1(component)
 AND NOT EXISTS(SELECT 1 FROM public.recording_evidence i WHERE i.kind='invalidation' AND
    i.payload->>'resolutionId'=e.id::text)
 ORDER BY e.ordinal DESC LIMIT 1;
 IF resolution IS NULL THEN reasons:=pg_catalog.array_append(reasons,
    'RECORDING_RESOLUTION_REQUIRED'); END IF;
 RETURN pg_catalog.jsonb_build_object('id',g.id,'revision',g.revision,'membershipComplete',
    g.membership_complete,
 'expectedSources',g.expected_sources,'registeredSources',(SELECT pg_catalog.count(*) FROM
    public.recording_occurrences WHERE group_id=gid),
 'manifestId',g.manifest_id,'manifestSha256',g.manifest_sha256,'pageCount',g.page_count,
 'createdAt',g.created_at,'importJobId',g.origin_import_job_id,
 'registeredPages',(SELECT pg_catalog.count(*) FROM public.recording_evidence pe
 WHERE pe.kind='membership' AND pe.group_ids=ARRAY[gid] AND pe.payload ? 'pageIndex'),
 'nextPageIndex',(SELECT page FROM pg_catalog.generate_series(0,g.page_count-1) page
 WHERE NOT EXISTS(SELECT 1 FROM public.recording_evidence pe WHERE pe.kind='membership'
 AND pe.group_ids=ARRAY[gid] AND (pe.payload->>'pageIndex')::integer=page)
 ORDER BY page LIMIT 1),
    'declared',g.declared,'independent',g.independent,
 'role',declared_role,'qualification',CASE WHEN pg_catalog.cardinality(reasons)=0 THEN
    'eligible' WHEN 'RECORDING_PROTECTED'=ANY(reasons) OR 'RECORDING_ROLE_CONFLICT'=ANY(reasons)
    THEN 'blocked' ELSE 'unresolved' END,
 'reasonCodes',pg_catalog.to_jsonb(reasons),'resolutionId',resolution);
END $$;

CREATE FUNCTION public.resolve_own_groups(wanted uuid, ids uuid[], family uuid, page_limit
    integer, after_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE views jsonb; cursor uuid; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF page_limit NOT BETWEEN 1 AND 100 OR COALESCE(pg_catalog.cardinality(ids),0)>200 THEN RAISE
    EXCEPTION 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.unnest(ids) v WHERE NOT EXISTS(SELECT 1 FROM
    public.recording_groups g WHERE g.id=v AND g.game_id=wanted)) THEN RAISE EXCEPTION
    'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 SELECT COALESCE(pg_catalog.jsonb_agg(public.recording_group_view_v1(wanted,g.id,family) ORDER
    BY g.id),'[]') INTO views
 FROM (SELECT id FROM public.recording_groups WHERE game_id=wanted AND (after_id IS NULL OR
    id>after_id) AND (COALESCE(pg_catalog.cardinality(ids),0)=0 OR id=ANY(ids)) ORDER BY id
    LIMIT page_limit) g;
 IF pg_catalog.jsonb_array_length(views)=page_limit THEN cursor:=(views->-1->>'id')::uuid; END IF;
 RETURN pg_catalog.jsonb_build_object('items',views,'nextCursor',cursor);
END $$;

CREATE FUNCTION public.recording_invalidate_dependents_v1(change_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE change public.recording_evidence; previous public.recording_evidence; affected uuid[];
    rid uuid; iid uuid; BEGIN
 SELECT * INTO change FROM public.recording_evidence WHERE id=change_id AND kind<>'resolution';
 IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_CHANGE_INVALID' USING ERRCODE='22023'; END IF;
 affected:=public.recording_closure_v1(change.group_ids);
 FOR previous IN SELECT * FROM public.recording_evidence e WHERE e.kind='resolution' AND
    e.dependency_group_ids && affected LOOP
   IF previous.proof_sha256=public.recording_proof_v1(
     public.recording_closure_v1(previous.group_ids)) THEN CONTINUE; END IF;
   IF EXISTS(SELECT 1 FROM public.recording_evidence e WHERE e.kind='invalidation' AND
    e.payload->>'resolutionId'=previous.id::text) THEN CONTINUE; END IF;
   iid:=pg_catalog.gen_random_uuid();
   INSERT INTO public.recording_evidence(id,kind,group_ids,payload,payload_sha256,actor)
   VALUES(iid,'invalidation',previous.group_ids,pg_catalog.jsonb_build_object('resolutionId',
    previous.id,'changeId',change_id),
    public.recording_digest_v1(pg_catalog.jsonb_build_object('resolutionId',previous.id,
    'changeId',change_id)),'server:recording-registry');
   FOR rid IN SELECT DISTINCT (e.payload->>'reportId')::uuid FROM public.recording_evidence e
     WHERE e.kind='use' AND e.payload->>'resolutionId'=previous.id::text AND e.payload ? 'reportId'
   LOOP
     IF NOT EXISTS(SELECT 1 FROM public.grid_model_evaluation_reports WHERE id=rid) THEN RAISE
    EXCEPTION 'RECORDING_BINDING_INVALID' USING ERRCODE='22023'; END IF;
     INSERT INTO public.grid_model_evaluation_invalidations(id,report_id,reason,actor)
     VALUES(pg_catalog.gen_random_uuid(),rid,'RECORDING_DEPENDENCY_CHANGED',
    'server:recording-registry');
   END LOOP;
 END LOOP;
END $$;
"""

COMMAND_SQL = r"""
CREATE FUNCTION public.recording_command(wanted uuid, envelope jsonb, trusted_actor text)
    RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE req jsonb:=envelope->'request'; k text:=req->>'kind'; key_id
    uuid:=(req->>'idempotencyKey')::uuid;
 gid uuid:=(req->>'groupId')::uuid; family uuid:=(req->>'familyId')::uuid;
 g public.recording_groups; previous public.recording_commands; event_id
    uuid:=pg_catalog.gen_random_uuid();
 payload jsonb; result jsonb; view jsonb; reason text; component uuid[]; source_row jsonb;
 ids uuid[]; rows jsonb; pg_count integer; role_value text:=req->>'role';
 provider_row jsonb; protected_row jsonb; inherited_payload jsonb; inherited_id uuid;
BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF trusted_actor IS NULL OR trusted_actor='' OR pg_catalog.length(trusted_actor)>64 OR
 k NOT IN ('prepare','attach','complete','declare','assign_role','retract','alias','freeze') OR
    key_id IS NULL THEN
 RAISE EXCEPTION 'RECORDING_COMMAND_INVALID' USING ERRCODE='22023'; END IF;
 -- Advisory read only: immutable receipt lookup must not retain global locks
 -- across source membership capture or managed-file IO. Mutating path repeats it.
 IF envelope->>'lookup'='true' THEN
   SELECT * INTO previous FROM public.recording_commands WHERE game_id=wanted AND kind=k AND
    idempotency_key=key_id;
   IF NOT FOUND THEN RETURN NULL; END IF;
   IF previous.command_json<>req THEN RAISE EXCEPTION 'RECORDING_COMMAND_CONFLICT' USING
    ERRCODE='23505'; END IF;
   RETURN previous.receipt;
 END IF;
 PERFORM pg_catalog.set_config('lock_timeout','5s',true);
 PERFORM pg_catalog.set_config('statement_timeout','30s',true);
 PERFORM pg_catalog.pg_advisory_xact_lock(9910994);
 PERFORM pg_catalog.pg_advisory_xact_lock(9921002);
 SELECT * INTO previous FROM public.recording_commands WHERE game_id=wanted AND kind=k AND
    idempotency_key=key_id;
 IF FOUND THEN
   IF previous.command_json<>req THEN RAISE EXCEPTION 'RECORDING_COMMAND_CONFLICT' USING
    ERRCODE='23505'; END IF;
   RETURN previous.receipt;
 END IF;
 IF k='prepare' THEN
   gid:=(envelope->'manifest'->>'id')::uuid;
   IF gid IS NULL OR (envelope->'manifest'->>'count')::integer<1 OR
   (envelope->'manifest'->>'sha256')!~'^[0-9a-f]{64}$' THEN RAISE EXCEPTION
    'RECORDING_MANIFEST_INVALID' USING ERRCODE='22023'; END IF;
   INSERT INTO public.recording_groups(id,game_id,revision,manifest_id,manifest_sha256,
    expected_sources,page_count,origin_import_job_id)
   VALUES(gid,wanted,1,gid,envelope->'manifest'->>'sha256',
    (envelope->'manifest'->>'count')::integer,(envelope->'manifest'->>'pages')::integer,
    (req->'selection'->>'importJobId')::uuid);
   payload:=pg_catalog.jsonb_build_object('manifestId',gid,'manifestSha256',
    envelope->'manifest'->>'sha256');
 ELSE
   SELECT * INTO g FROM public.recording_groups WHERE id=gid AND game_id=wanted FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
   IF g.revision<>(req->>'expectedRevision')::bigint THEN RAISE EXCEPTION
    'RECORDING_REVISION_CONFLICT' USING ERRCODE='40001'; END IF;
   component:=public.recording_closure_v1(ARRAY[gid]);
   payload:=pg_catalog.jsonb_build_object('kind',k);
   IF k='attach' THEN
     IF g.membership_complete OR (req->>'manifestId')::uuid<>g.manifest_id OR
       (req->>'pageIndex')::integer<0 OR (req->>'pageIndex')::integer>=g.page_count THEN RAISE
    EXCEPTION 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
     IF EXISTS(SELECT 1 FROM public.recording_evidence e WHERE e.kind='membership' AND
    e.group_ids=ARRAY[gid] AND e.payload->>'pageIndex'=req->>'pageIndex') THEN RAISE EXCEPTION
    'RECORDING_PAGE_CONFLICT' USING ERRCODE='23505'; END IF;
     SELECT pg_catalog.array_agg(v::uuid) INTO ids FROM
    pg_catalog.jsonb_array_elements_text(envelope->'sourceIds') v;
     rows:=public.attest_own_source_ids(wanted,ids);
     IF rows IS DISTINCT FROM envelope->'identities' THEN RAISE EXCEPTION
    'RECORDING_SOURCE_IDENTITY_DRIFT' USING ERRCODE='40001'; END IF;
     FOR source_row IN SELECT value FROM pg_catalog.jsonb_array_elements(rows) LOOP
       IF EXISTS(SELECT 1 FROM public.recording_occurrences o WHERE o.game_id=wanted AND
    o.source_id=(source_row->>'sourceId')::uuid AND (o.source_sha256<>source_row->>'byteSha256'
    OR o.pixel_sha256<>source_row->>'pixelSha256')) THEN RAISE EXCEPTION
    'RECORDING_SOURCE_IDENTITY_DRIFT' USING ERRCODE='40001'; END IF;
       INSERT INTO public.recording_occurrences(id,group_id,game_id,source_id,source_sha256,
    pixel_sha256,pixel_algorithm,width,height,attestation)
       VALUES(pg_catalog.gen_random_uuid(),gid,wanted,(source_row->>'sourceId')::uuid,
    source_row->>'byteSha256',source_row->>'pixelSha256',source_row->>'pixelAlgorithm',
    (source_row->>'width')::integer,(source_row->>'height')::integer,source_row);
     END LOOP;
     payload:=pg_catalog.jsonb_build_object('pageIndex',(req->>'pageIndex')::integer,'sourceIds',
    envelope->'sourceIds');
   ELSIF k='complete' THEN
     SELECT pg_catalog.count(*) INTO pg_count FROM public.recording_evidence e WHERE
    e.kind='membership' AND e.group_ids=ARRAY[gid] AND e.payload ? 'pageIndex';
     IF pg_count<>g.page_count OR (SELECT pg_catalog.count(*) FROM public.recording_occurrences
    WHERE group_id=gid)<>g.expected_sources THEN RAISE EXCEPTION
    'RECORDING_MEMBERSHIP_INCOMPLETE' USING ERRCODE='22023'; END IF;
     UPDATE public.recording_groups SET membership_complete=true WHERE id=gid;
   ELSIF k='declare' THEN
     IF req->>'independenceConfirmed'<>'true' OR NOT g.membership_complete THEN RAISE EXCEPTION
    'RECORDING_DECLARATION_REQUIRED' USING ERRCODE='22023'; END IF;
     UPDATE public.recording_groups SET declared=true,independent=true WHERE id=gid;
   ELSIF k='retract' THEN
     UPDATE public.recording_groups SET declared=false,independent=false WHERE id=gid;
     DELETE FROM public.recording_role_heads WHERE group_id=gid;
   ELSIF k='alias' THEN
     IF NOT EXISTS(SELECT 1 FROM public.recording_groups WHERE id=(req->>'otherGroupId')::uuid
    AND game_id=wanted) THEN RAISE EXCEPTION 'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
   ELSIF k='assign_role' THEN
     IF family IS NULL OR role_value NOT IN ('TRAIN','VALIDATION','REGRESSION') OR NOT
    EXISTS(SELECT 1 FROM public.grid_model_families WHERE id=family) THEN RAISE EXCEPTION
    'RECORDING_ROLE_REQUIRED' USING ERRCODE='22023'; END IF;
     IF role_value='TRAIN' AND EXISTS(SELECT 1 FROM public.recording_evidence e WHERE e.kind IN
    ('holdout','ancestor','use') AND e.group_ids && component AND e.payload->>'role' IN
    ('VALIDATION','REGRESSION','final_test','unseen_game','Reels','Treasure',
    'declared_holdouts')) THEN reason:='RECORDING_PROTECTED'; END IF;
   END IF;
 END IF;
 IF k='freeze' THEN
   IF envelope->'ancestry'->>'complete' IS DISTINCT FROM 'true'
   OR pg_catalog.jsonb_typeof(envelope->'ancestry'->'references') IS DISTINCT FROM 'array'
   OR COALESCE(envelope->'ancestry'->>'lineageSha256','')!~'^[0-9a-f]{64}$' THEN
     reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED';
   ELSIF pg_catalog.jsonb_array_length(envelope->'ancestry'->'references') NOT BETWEEN 1 AND 64
   THEN reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED'; END IF;
   IF reason IS NULL AND envelope->'ancestry'->>'complete'='true' THEN
     IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
       envelope->'ancestry'->'references') p WHERE NOT EXISTS(
       SELECT 1 FROM public.recording_evidence installed WHERE installed.kind='membership'
       AND installed.payload->>'providerSha256'=p->>'providerSha256'
       AND installed.payload->'provider'=p-'providerSha256')) THEN
       reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED'; END IF;
     IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
       envelope->'ancestry'->'references') p,
       pg_catalog.jsonb_array_elements(p->'recordingGroups') member
       WHERE NOT EXISTS(SELECT 1 FROM public.recording_groups pg
       WHERE pg.id=(member->>'groupId')::uuid AND pg.membership_complete AND pg.declared))
     THEN reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED'; END IF;
     IF reason IS NULL THEN
       FOR provider_row IN SELECT value FROM pg_catalog.jsonb_array_elements(
         envelope->'ancestry'->'references') LOOP
         FOR protected_row IN SELECT value FROM pg_catalog.jsonb_array_elements(
           provider_row->'recordingGroups') LOOP
           IF protected_row->>'role' NOT IN ('TRAIN','VALIDATION','REGRESSION','final_test',
             'unseen_game','Reels','Treasure','declared_holdouts') THEN
             RAISE EXCEPTION 'RECORDING_PROVIDER_INVALID' USING ERRCODE='22023'; END IF;
           inherited_payload:=pg_catalog.jsonb_build_object('role',protected_row->>'role',
             'providerSha256',provider_row->>'providerSha256',
             'ancestor',provider_row->'ancestor');
           IF NOT EXISTS(SELECT 1 FROM public.recording_evidence pe
             WHERE pe.kind IN ('ancestor','use')
             AND pe.group_ids=ARRAY[(protected_row->>'groupId')::uuid]
             AND pe.payload_sha256=public.recording_digest_v1(inherited_payload)) THEN
             inherited_id:=pg_catalog.gen_random_uuid();
             INSERT INTO public.recording_evidence(id,kind,group_ids,payload,
               payload_sha256,actor) VALUES(inherited_id,
               CASE WHEN protected_row->>'role'='TRAIN' THEN 'use' ELSE 'ancestor' END,
               ARRAY[(protected_row->>'groupId')::uuid],inherited_payload,
               public.recording_digest_v1(inherited_payload),'server:recording-registry');
             PERFORM public.recording_invalidate_dependents_v1(inherited_id);
           END IF;
         END LOOP;
       END LOOP;
     END IF;
   END IF;
   view:=public.recording_group_view_v1(wanted,gid,family);
   IF reason IS NULL THEN
     SELECT v INTO reason FROM pg_catalog.jsonb_array_elements_text(view->'reasonCodes') v
     WHERE v<>'RECORDING_RESOLUTION_REQUIRED' LIMIT 1;
   END IF;
   IF reason IS NULL AND envelope->'ancestry'->>'complete' IS DISTINCT FROM 'true' THEN
    reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED'; END IF;
   IF reason IS NULL AND (envelope->'ancestry' IS NULL OR NOT (envelope->'ancestry' ?
    'lineageSha256')) THEN reason:='RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED'; END IF;
   IF reason IS NULL THEN
     FOR ids IN SELECT pg_catalog.array_agg(source_id ORDER BY source_id) FROM (
       SELECT source_id,(pg_catalog.row_number() OVER(ORDER BY source_id)-1)/200 AS page
       FROM public.recording_occurrences WHERE group_id=gid AND game_id=wanted) s
       GROUP BY page ORDER BY page LOOP
       rows:=public.attest_own_source_ids(wanted,ids);
       IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(rows) current_source
         JOIN public.recording_occurrences pinned
         ON pinned.group_id=gid AND pinned.source_id=(current_source->>'sourceId')::uuid
         WHERE pinned.attestation<>current_source) THEN
         RAISE EXCEPTION 'RECORDING_SOURCE_IDENTITY_DRIFT' USING ERRCODE='40001'; END IF;
     END LOOP;
     component:=public.recording_closure_v1(ARRAY[gid]);
   END IF;
   IF reason IS NULL THEN
     payload:=pg_catalog.jsonb_build_object('familyId',family,'baseVersionId',
    req->>'baseVersionId','lineageSha256',envelope->'ancestry'->>'lineageSha256',
    'ancestorReferences',envelope->'ancestry'->'references','state','provisional');
     INSERT INTO public.recording_evidence(id,kind,group_ids,dependency_group_ids,payload,
    payload_sha256,proof_sha256,actor)
     VALUES(event_id,'resolution',ARRAY[gid],component,payload,
    public.recording_digest_v1(payload),public.recording_proof_v1(component),trusted_actor);
   END IF;
 ELSE
   IF reason IS NULL THEN
     INSERT INTO public.recording_evidence(id,kind,group_ids,payload,payload_sha256,actor)
     VALUES(event_id,CASE WHEN k='prepare' OR k='attach' OR k='complete' THEN 'membership' WHEN
    k='alias' THEN 'alias' WHEN k='retract' THEN 'retraction' ELSE 'declaration' END,
       CASE WHEN k='alias' THEN ARRAY[gid,(req->>'otherGroupId')::uuid] ELSE ARRAY[gid] END,
    payload,public.recording_digest_v1(payload),trusted_actor);
     IF k='assign_role' THEN
       INSERT INTO public.recording_role_heads(family_id,group_id,revision,role,event_id)
    VALUES(family,gid,1,role_value,event_id)
       ON CONFLICT(family_id,group_id) DO UPDATE SET
    revision=public.recording_role_heads.revision+1,role=EXCLUDED.role,event_id=EXCLUDED.event_id;
     END IF;
     IF k<>'prepare' THEN UPDATE public.recording_groups SET revision=revision+1 WHERE id=gid;
    END IF;
     PERFORM public.recording_invalidate_dependents_v1(event_id);
   END IF;
 END IF;
 view:=public.recording_group_view_v1(wanted,gid,family);
 IF reason IS NULL AND k IN ('attach','alias','assign_role') THEN
   SELECT v INTO reason FROM pg_catalog.jsonb_array_elements_text(view->'reasonCodes') v WHERE v
    IN ('RECORDING_ROLE_CONFLICT','RECORDING_PROTECTED') LIMIT 1;
 END IF;
 result:=pg_catalog.jsonb_build_object('commandKind',k,'idempotencyKey',key_id,'group',view,
 'statusCode',CASE WHEN reason IS NULL THEN 200 ELSE 409 END,'reasonCode',reason,
 'resolutionId',CASE WHEN k='freeze' AND reason IS NULL THEN event_id ELSE NULL END);
 INSERT INTO public.recording_commands(game_id,kind,idempotency_key,command_json,command_sha256,
    actor,receipt)
 VALUES(wanted,k,key_id,req,public.recording_digest_v1(req),trusted_actor,result);
 RETURN result;
END $$;
"""
