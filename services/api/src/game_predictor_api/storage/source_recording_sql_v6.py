"""Incremental photo reservations in the existing private recording capability."""

from .source_recording_sql_v4 import FUNCTION_SQL as V4_SQL
from .source_recording_sql_v5 import WRAPPER_SQL as V5_WRAPPER

TABLE_SQL = r"""
ALTER TABLE public.recording_photo_uses ADD COLUMN reservation_policy text NOT NULL
 DEFAULT 'legacy-v1' CHECK(reservation_policy IN ('legacy-v1','incremental-v2'));
CREATE TABLE public.recording_photo_reservation_releases (
 game_id uuid NOT NULL,cohort_id uuid NOT NULL,source_id uuid NOT NULL,
 released_by_game uuid NOT NULL,released_by_cohort uuid NOT NULL,
 split_sha256 text NOT NULL CHECK(split_sha256~'^[0-9a-f]{64}$'),
 actor text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(game_id,cohort_id,source_id),
 FOREIGN KEY(game_id,cohort_id,source_id)
 REFERENCES public.recording_photo_uses(game_id,cohort_id,source_id));
CREATE TRIGGER recording_photo_release_immutable BEFORE UPDATE OR DELETE
 ON public.recording_photo_reservation_releases FOR EACH ROW
 EXECUTE FUNCTION public.recording_immutable_v1();
"""

CONTEXT_SQL = r"""
CREATE FUNCTION public.recording_photo_context_data_v2(wanted uuid,ids uuid[],preview boolean)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s record; groups uuid[]; next_groups uuid[]; bytes text[]; pixels text[];
 next_bytes text[]; next_pixels text[]; uses jsonb; released jsonb; releases jsonb;
 roles text[]; external_roles text[]; photo_roles text[]; allowed text[];
labels jsonb; alias_labels jsonb; protected boolean;
external_protection boolean; unspecified_protection boolean; result jsonb:='[]';
 iteration integer; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF ids IS NULL OR cardinality(ids)>200 THEN RAISE EXCEPTION
 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 FOR s IN SELECT id,checksum_sha256,normalized_pixel_checksum_sha256
 FROM game_data_v2.source_images WHERE game_id=wanted AND id=ANY(ids) ORDER BY id LOOP
  bytes:=ARRAY[s.checksum_sha256]; pixels:=ARRAY[s.normalized_pixel_checksum_sha256]; groups:='{}';
  -- Close byte/pixel aliases and known session groups transitively, including
  -- registry entries from other games. Never expose their rows to runtime.
  FOR iteration IN 1..64 LOOP
   SELECT public.recording_closure_v1(COALESCE(array_agg(DISTINCT g),'{}')) INTO next_groups
    FROM (
     SELECT o.group_id g FROM public.recording_occurrences o
      WHERE o.source_sha256=ANY(bytes) OR o.pixel_sha256=ANY(pixels) OR o.group_id=ANY(groups)
     UNION SELECT unnest(u.group_ids) FROM public.recording_photo_uses u
      WHERE u.source_sha256=ANY(bytes) OR u.pixel_sha256=ANY(pixels) OR u.group_ids && groups
    ) connected;
   SELECT COALESCE(array_agg(DISTINCT b ORDER BY b) FILTER(WHERE b IS NOT NULL),'{}'),
    COALESCE(array_agg(DISTINCT p ORDER BY p) FILTER(WHERE p IS NOT NULL),'{}')
    INTO next_bytes,next_pixels FROM (
     SELECT unnest(bytes) b,unnest(pixels) p
     UNION SELECT u.source_sha256,u.pixel_sha256 FROM public.recording_photo_uses u
      WHERE u.source_sha256=ANY(bytes) OR u.pixel_sha256=ANY(pixels) OR u.group_ids && next_groups
     UNION SELECT o.source_sha256,o.pixel_sha256 FROM public.recording_occurrences o
      WHERE o.group_id=ANY(next_groups)
    ) identities;
   IF cardinality(next_bytes)>5000 OR cardinality(next_pixels)>5000 THEN
    RAISE EXCEPTION 'GRID_CORRECTION_CONTEXT_LIMIT' USING ERRCODE='22023'; END IF;
   EXIT WHEN next_groups=groups AND next_bytes=bytes AND next_pixels=pixels;
   groups:=next_groups; bytes:=next_bytes; pixels:=next_pixels;
   IF iteration=64 THEN RAISE EXCEPTION 'GRID_CORRECTION_CONTEXT_LIMIT'
    USING ERRCODE='22023'; END IF;
  END LOOP;
  SELECT COALESCE(jsonb_agg(to_jsonb(u)-'created_at'
   ORDER BY u.game_id,u.cohort_id,u.source_id),'[]')
   INTO uses FROM public.recording_photo_uses u WHERE
   (u.source_sha256=ANY(bytes) OR u.pixel_sha256=ANY(pixels) OR u.group_ids && groups)
   AND NOT EXISTS(SELECT 1 FROM public.recording_photo_reservation_releases r
    WHERE (r.game_id,r.cohort_id,r.source_id)=(u.game_id,u.cohort_id,u.source_id));
  SELECT COALESCE(jsonb_agg(to_jsonb(r)-'created_at'
   ORDER BY r.game_id,r.cohort_id,r.source_id),'[]')
   INTO released FROM public.recording_photo_reservation_releases r
   JOIN public.recording_photo_uses u USING(game_id,cohort_id,source_id)
   WHERE u.source_sha256=ANY(bytes) OR u.pixel_sha256=ANY(pixels) OR u.group_ids && groups;
  SELECT COALESCE(array_agg(DISTINCT role ORDER BY role),'{}') INTO external_roles FROM (
   SELECT h.role FROM public.recording_role_heads h WHERE h.group_id=ANY(groups)
   UNION SELECT e.payload->>'role' FROM public.recording_evidence e
    WHERE e.group_ids && groups AND e.kind IN ('holdout','ancestor','use') AND e.payload ? 'role'
  ) known;
  external_protection:=EXISTS(SELECT 1 FROM public.recording_role_heads h
    WHERE h.group_id=ANY(groups))
   OR EXISTS(SELECT 1 FROM public.recording_evidence e WHERE e.group_ids && groups
    AND e.kind IN ('holdout','ancestor','use'));
  unspecified_protection:=EXISTS(SELECT 1 FROM public.recording_evidence e
   WHERE e.group_ids && groups AND e.kind IN ('holdout','ancestor','use')
    AND COALESCE(e.payload->>'role','') NOT IN ('TRAIN','VALIDATION','REGRESSION'));
  protected:=external_protection OR EXISTS(SELECT 1 FROM jsonb_array_elements(uses) u
   WHERE u->'used_in_cohort'='true' OR u->>'role'='BUFFER'
    OR u->>'reservation_policy'<>'legacy-v1');
  releases:=CASE WHEN preview AND NOT protected THEN uses ELSE '[]'::jsonb END;
  SELECT COALESCE(array_agg(DISTINCT u->>'role' ORDER BY u->>'role'),'{}') INTO photo_roles
   FROM jsonb_array_elements(CASE WHEN preview AND NOT protected THEN '[]'::jsonb ELSE uses END) u;
  SELECT COALESCE(array_agg(DISTINCT r ORDER BY r),'{}') INTO roles
   FROM unnest(external_roles||photo_roles) r;
  allowed:=CASE WHEN unspecified_protection THEN '{}'::text[]
   WHEN cardinality(roles)=0 AND NOT external_protection
   THEN ARRAY['TRAIN','VALIDATION','REGRESSION']
   WHEN cardinality(roles)=1 AND roles[1] IN ('TRAIN','VALIDATION','REGRESSION')
    THEN roles ELSE '{}' END;
  SELECT COALESCE(jsonb_agg(DISTINCT p->'label'),'[]') INTO labels
   FROM public.recording_photo_uses u JOIN game_data_v2.grid_training_cohort_members m
    ON (m.game_id,m.cohort_id,m.source_id)=(u.game_id,u.cohort_id,u.source_id)
   CROSS JOIN LATERAL jsonb_array_elements(m.frozen->'positions') p
   WHERE u.game_id=wanted AND u.source_id=s.id AND u.used_in_cohort AND u.role='TRAIN'
    AND jsonb_typeof(p->'label')='object';
  SELECT COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
   'sourcePixelSha256',u.pixel_sha256,'positionIndex',p->'label'->'positionIndex',
   'nodes',p->'label'->'nodes')),'[]') INTO alias_labels
   FROM public.recording_photo_uses u JOIN game_data_v2.grid_training_cohort_members m
    ON (m.game_id,m.cohort_id,m.source_id)=(u.game_id,u.cohort_id,u.source_id)
   CROSS JOIN LATERAL jsonb_array_elements(m.frozen->'positions') p
   WHERE u.game_id=wanted AND u.source_id<>s.id AND u.used_in_cohort AND u.role='TRAIN'
    AND u.pixel_sha256=s.normalized_pixel_checksum_sha256
    AND jsonb_typeof(p->'label')='object'
    AND jsonb_typeof(p->'label'->'nodes')='array';
  result:=result||jsonb_build_array(jsonb_build_object('sourceId',s.id,
   'componentIds',to_jsonb(groups),'aliasComponentIds',
    (SELECT COALESCE(jsonb_agg(token ORDER BY token),'[]') FROM (
     SELECT public.recording_digest_v1(jsonb_build_object(
      'kind','photo-byte-alias-v2','identity',b)) token FROM unnest(bytes) b
     UNION SELECT public.recording_digest_v1(jsonb_build_object(
      'kind','photo-pixel-alias-v2','identity',p)) FROM unnest(pixels) p
    ) aliases),
   'allowedRoles',to_jsonb(allowed),'priorRoles',to_jsonb(roles),
   'photoRoles',to_jsonb(photo_roles),'usedTrainLabels',labels,
   'usedTrainAliasLabels',alias_labels,'releaseUses',releases,
   'proofSha256',public.recording_digest_v1(jsonb_build_object(
    'groups',public.recording_proof_v1(groups),'roles',to_jsonb(roles),
    'unspecifiedProtection',unspecified_protection,
    'uses',uses,'released',released,'byte',s.checksum_sha256,'pixel',s.normalized_pixel_checksum_sha256))));
 END LOOP;
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION public.recording_photo_context_v1(wanted uuid,ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT COALESCE(jsonb_agg(
  v-'releaseUses'-'usedTrainLabels'-'usedTrainAliasLabels'-'aliasComponentIds'),'[]')
 FROM jsonb_array_elements(public.recording_photo_context_data_v2(wanted,ids,false)) v
$$;
CREATE FUNCTION public.recording_photo_context_v2(wanted uuid,ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT COALESCE(jsonb_agg(v-'releaseUses'),'[]')
 FROM jsonb_array_elements(public.recording_photo_context_data_v2(wanted,ids,true)) v
$$;
"""

_photo = V4_SQL[
    V4_SQL.index("CREATE FUNCTION public.recording_photo_cohort_v1(") : V4_SQL.index(
        "ALTER FUNCTION public.recording_cohort_command_v3("
    )
]
PHOTO_SQL = (
    _photo.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    .replace(
        "pending jsonb:='[]'; BEGIN",
        "pending jsonb:='[]'; releases jsonb:='[]'; released_use jsonb; incremental boolean; BEGIN",
    )
    .replace(
        "header.document->>'policyVersion'<>'application-grid-corrections-v1'",
        "header.document->>'policyVersion' NOT IN "
        "('application-grid-corrections-v1','application-grid-corrections-v2')",
    )
    .replace(
        " plan:=header.document->'photoSplit';",
        " incremental:=header.document->>'policyVersion'='application-grid-corrections-v2';\n"
        " plan:=header.document->'photoSplit';",
    )
    .replace("  IF desired IS NULL THEN CONTINUE; END IF;", "")
    .replace(
        "  context:=public.recording_photo_context_v1(wanted,ARRAY[source.id])->0;",
        """
  context:=public.recording_photo_context_data_v2(wanted,ARRAY[source.id],
   incremental AND kind='register_cohort_use')->0;
  IF incremental AND kind='register_cohort_use' THEN
   IF context->>'proofSha256' IS DISTINCT FROM item->>'registryProofSha256' THEN
    RAISE EXCEPTION 'GRID_CORRECTION_REGISTRY_CHANGED' USING ERRCODE='40001'; END IF;
   releases:=releases||(context->'releaseUses');
  END IF;
  IF desired IS NULL THEN CONTINUE; END IF;""",
    )
    .replace(
        "  IF (desired<>'BUFFER'",
        "  IF (kind='register_cohort_use' OR member.frozen->'used'='true'::jsonb"
        " OR desired='BUFFER'\n   OR incremental OR NOT EXISTS(SELECT 1 FROM "
        "public.recording_photo_reservation_releases r WHERE r.game_id=wanted "
        "AND r.cohort_id=cohort AND r.source_id=source.id)) AND ((desired<>'BUFFER'",
    )
    .replace(
        "   THEN RAISE EXCEPTION 'RECORDING_ROLE_CONFLICT'",
        "   ) THEN RAISE EXCEPTION 'RECORDING_ROLE_CONFLICT'",
    )
    .replace(
        "  FOR item IN SELECT p FROM jsonb_array_elements(pending) p LOOP",
        """
  FOR released_use IN SELECT DISTINCT p FROM jsonb_array_elements(releases) p LOOP
   INSERT INTO public.recording_photo_reservation_releases(game_id,cohort_id,source_id,
    released_by_game,released_by_cohort,split_sha256,actor)
   VALUES((released_use->>'game_id')::uuid,(released_use->>'cohort_id')::uuid,
    (released_use->>'source_id')::uuid,wanted,cohort,plan->>'sha256',actor)
   ON CONFLICT DO NOTHING;
  END LOOP;
  FOR item IN SELECT p FROM jsonb_array_elements(pending) p LOOP""",
    )
    .replace("    used_in_cohort)", "    used_in_cohort,reservation_policy)")
    .replace(
        "'desired',desired,'componentIds',context->'componentIds',",
        "'desired',desired,'componentIds',context->'componentIds','aliasComponentIds',context->'aliasComponentIds',",
    )
    .replace(
        "WHERE b->'componentIds' ? g.value)))",
        "WHERE b->'componentIds' ? g.value) OR EXISTS(SELECT 1 FROM "
        "jsonb_array_elements_text(a->'aliasComponentIds') g "
        "WHERE b->'aliasComponentIds' ? g.value)))",
    )
    .replace(
        "    (item->>'usedInCohort')::boolean);",
        "    (item->>'usedInCohort')::boolean,CASE WHEN incremental THEN 'incremental-v2' "
        "ELSE 'legacy-v1' END);",
    )
)
WRAPPER_SQL = V5_WRAPPER.replace(
    "c.document->>'policyVersion'='application-grid-corrections-v1'",
    "c.document->>'policyVersion' IN "
    "('application-grid-corrections-v1','application-grid-corrections-v2')",
)
