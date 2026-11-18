"""Database admission for a private game, its frozen training data and evaluation."""

PIN_SQL = """
CREATE FUNCTION public.grid_private_assignment_pin(game uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object('gameId',g.id,'assignmentRevision',a.revision,
          'targetFamilyId',f.id,'baseVersionId',v.id,'baseManifestSha256',v.manifest_sha256)
 FROM public.games g
 JOIN public.game_grid_model_assignments a ON a.game_id=g.id
 JOIN public.grid_model_families f ON f.owner_game_id=g.id AND f.id=a.training_family_id
 JOIN public.grid_model_versions v ON v.id=a.version_id
 WHERE g.id=game AND g.grid_model_private
$$
"""

JOB_SQL = """
CREATE FUNCTION public.guard_private_learning_job() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog SET lock_timeout='5s' AS $$
DECLARE
 p jsonb:=NEW.input_payload;
 pin jsonb;
 frozen record;
 candidate record;
BEGIN
 IF NOT (NEW.job_type::text='grid_training'
     OR (NEW.job_type::text='grid_correction_learning'
          AND p->>'learning_kind'='grid-correction-learning-v1')
     OR (NEW.job_type::text='grid_model_evaluation'
          AND p->>'evaluation_kind'<>'grid-assigned-comparison-v1'))
 THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND NEW.input_payload=OLD.input_payload
    AND NEW.game_id IS NOT DISTINCT FROM OLD.game_id AND NEW.job_type=OLD.job_type
    AND NOT (NEW.status::text='completed' AND OLD.status::text<>'completed'
      AND p#>'{pins,privateLearning}' IS NOT NULL)
    AND (OLD.status::text IN ('created','processing','waiting_for_review')
      OR NEW.status::text NOT IN ('created','processing','waiting_for_review'))
 THEN RETURN NEW; END IF;
 PERFORM pg_advisory_xact_lock(9910994);
 pin:=COALESCE(p->'private_learning',p#>'{pins,privateLearning}');
 IF NOT EXISTS(SELECT 1 FROM public.games g WHERE g.id=NEW.game_id AND g.grid_model_private) THEN
    IF pin IS NOT NULL THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED'; END IF;
    RETURN NEW;
 END IF;
 IF pin IS NULL THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_SCOPE_REQUIRED'; END IF;
 IF pin IS DISTINCT FROM public.grid_private_assignment_pin(NEW.game_id) THEN
    RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED';
 END IF;
 IF NEW.job_type::text='grid_correction_learning' THEN
    IF p#>>'{command,learningScope}' IS DISTINCT FROM 'private_game'
     OR p#>>'{preview,baseVersionId}' IS DISTINCT FROM pin->>'baseVersionId'
     OR p#>'{preview,requiredGameIds}' IS DISTINCT FROM jsonb_build_array(NEW.game_id)
     OR coalesce(p#>'{pins,historicalCohorts}','[]')<>'[]'::jsonb
     OR coalesce(p#>'{command,exclusions}','[]')<>'[]'::jsonb
    THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID'; END IF;
    RETURN NEW;
 END IF;
 IF p->>'family_id' IS DISTINCT FROM pin->>'targetFamilyId'
    OR p->>'base_version_id' IS DISTINCT FROM pin->>'baseVersionId'
 THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED'; END IF;
 IF NEW.job_type::text='grid_training' THEN
    IF coalesce(p->'shared_cohorts','[]')<>'[]'::jsonb
       OR p->>'training_kind' IS DISTINCT FROM 'grid-training-run-v1'
    THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID'; END IF;
    SELECT c.document,c.manifest_sha256 INTO frozen FROM game_data_v2.grid_training_cohorts c
      WHERE c.game_id=NEW.game_id AND c.id=(p->>'cohort_id')::uuid AND c.status='frozen';
    IF NOT FOUND OR frozen.document->'privateLearning' IS DISTINCT FROM pin
      OR frozen.document->>'familyId' IS DISTINCT FROM pin->>'targetFamilyId'
      OR frozen.document#>>'{base,versionId}' IS DISTINCT FROM pin->>'baseVersionId'
      OR frozen.document#>>'{base,manifestSha256}' IS DISTINCT FROM pin->>'baseManifestSha256'
      OR frozen.document->>'mode' IS DISTINCT FROM p->>'mode'
      OR frozen.document->>'cropPolicyVersion' IS DISTINCT FROM 'full-cell-v2'
      OR jsonb_typeof(frozen.document->'detectorReadiness') IS DISTINCT FROM 'object'
      OR frozen.document#>>'{photoSplit,sha256}' IS NULL
      OR frozen.manifest_sha256 IS DISTINCT FROM p->>'cohort_manifest_sha256'
    THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID'; END IF;
 ELSE
    SELECT v.manifest_json::jsonb AS manifest,j.input_payload AS run INTO candidate
    FROM public.grid_model_versions v JOIN public.jobs j
       ON j.id=(v.manifest_json::jsonb#>>'{provenance,runId}')::uuid
    WHERE v.id=(p->>'version_id')::uuid AND v.family_id=(pin->>'targetFamilyId')::uuid
      AND j.game_id=NEW.game_id AND j.job_type::text='grid_training';
    IF NOT FOUND OR candidate.run->'private_learning' IS DISTINCT FROM pin
      OR p->>'base_manifest_sha256' IS DISTINCT FROM pin->>'baseManifestSha256'
      OR p->'cohorts' IS DISTINCT FROM jsonb_build_array(jsonb_build_object(
          'game_id',NEW.game_id,'cohort_id',candidate.run->>'cohort_id',
          'manifest_sha256',candidate.run->>'cohort_manifest_sha256'))
      OR p->>'evaluation_kind' IS DISTINCT FROM 'grid-correction-evaluation-v1'
      OR p#>'{scope,trainingGameIds}' IS DISTINCT FROM jsonb_build_array(NEW.game_id)
    THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_private_learning_job BEFORE INSERT OR UPDATE OF status,input_payload,game_id
 ON public.jobs FOR EACH ROW EXECUTE FUNCTION public.guard_private_learning_job()
"""

VERSION_SQL = """
CREATE FUNCTION public.guard_private_trained_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog SET lock_timeout='5s' AS $$
DECLARE owner_id uuid; run jsonb; pin jsonb; doc jsonb:=NEW.manifest_json::jsonb;
BEGIN
 SELECT owner_game_id INTO owner_id FROM public.grid_model_families WHERE id=NEW.family_id;
 IF owner_id IS NULL THEN RETURN NEW; END IF;
 PERFORM pg_advisory_xact_lock(9910994);
 SELECT j.input_payload INTO run FROM public.jobs j
 WHERE j.id=(doc#>>'{provenance,runId}')::uuid AND j.job_type::text='grid_training'
   AND j.game_id=owner_id;
 pin:=public.grid_private_assignment_pin(owner_id);
 IF pin IS NULL OR run->'private_learning' IS DISTINCT FROM pin
    OR NEW.base_version_id::text IS DISTINCT FROM pin->>'baseVersionId'
    OR doc->>'baseVersionId' IS DISTINCT FROM pin->>'baseVersionId'
    OR NEW.family_id::text IS DISTINCT FROM pin->>'targetFamilyId'
    OR doc->>'familyId' IS DISTINCT FROM pin->>'targetFamilyId'
    OR doc->>'cohortId' IS DISTINCT FROM run->>'cohort_id'
 THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_private_learning_version BEFORE INSERT ON public.grid_model_versions
 FOR EACH ROW EXECUTE FUNCTION public.guard_private_trained_version()
"""

# RFC 4122 UUIDv5, using the same report namespace as report_id_for().
REPORT_ID_SQL = """
CREATE FUNCTION public.grid_learning_report_id(job_id uuid) RETURNS uuid
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
 WITH hash(bytes) AS (SELECT substring(public.digest(
   uuid_send('7f891ee1-4f34-5409-9d80-f8b032bf5c04'::uuid)
   ||convert_to('report:'||job_id::text,'UTF8'),'sha1') FROM 1 FOR 16))
 SELECT encode(set_byte(set_byte(bytes,6,(get_byte(bytes,6)&15)|80),
   8,(get_byte(bytes,8)&63)|128),'hex')::uuid FROM hash
$$
"""

REPORT_SQL = """
CREATE FUNCTION public.guard_private_learning_report() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog SET lock_timeout='5s' AS $$
DECLARE owner_id uuid; doc jsonb:=NEW.report_json::jsonb; pin jsonb;
BEGIN
 SELECT f.owner_game_id INTO owner_id FROM public.grid_model_versions v
 JOIN public.grid_model_families f ON f.id=v.family_id WHERE v.id=NEW.version_id;
 IF owner_id IS NULL THEN RETURN NEW; END IF;
 IF doc->>'schemaVersion'='grid-model-assigned-comparison-v1' THEN
   IF doc#>>'{cohort,gameId}' IS DISTINCT FROM owner_id::text THEN
     RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID';
   END IF;
   RETURN NEW;
 END IF;
 PERFORM pg_advisory_xact_lock(9910994);
 pin:=public.grid_private_assignment_pin(owner_id);
 IF pin IS NULL OR doc->>'versionId' IS DISTINCT FROM NEW.version_id::text
 OR doc->>'trainingGameId' IS DISTINCT FROM owner_id::text
 OR doc->>'baseManifestSha256' IS DISTINCT FROM pin->>'baseManifestSha256'
 OR doc->>'baseVersionId' IS DISTINCT FROM pin->>'baseVersionId'
 OR doc->>'familyId' IS DISTINCT FROM pin->>'targetFamilyId'
 OR jsonb_array_length(doc->'cohorts') IS DISTINCT FROM 1
 OR NOT EXISTS(SELECT 1 FROM public.jobs j WHERE j.game_id=owner_id
      AND j.job_type::text='grid_model_evaluation' AND j.input_payload->'private_learning'=pin
      AND j.input_payload->>'version_id'=NEW.version_id::text
      AND public.grid_learning_report_id(j.id)=NEW.id
      AND j.input_payload->'scope'=doc->'scope'
      AND j.input_payload#>>'{cohorts,0,cohort_id}'=doc#>>'{cohorts,0,cohortId}'
      AND j.input_payload#>>'{cohorts,0,manifest_sha256}'=doc#>>'{cohorts,0,manifestSha256}'
      AND doc#>>'{cohorts,0,gameId}'=owner_id::text)
 THEN RAISE EXCEPTION 'GRID_LEARNING_PRIVATE_COHORTS_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_private_learning_report BEFORE INSERT ON public.grid_model_evaluation_reports
 FOR EACH ROW EXECUTE FUNCTION public.guard_private_learning_report()
"""

INSTALL_SQL = (PIN_SQL, JOB_SQL, VERSION_SQL, REPORT_ID_SQL, REPORT_SQL)
REMOVE_SQL = """
DROP TRIGGER grid_private_learning_report ON public.grid_model_evaluation_reports;
DROP TRIGGER grid_private_learning_version ON public.grid_model_versions;
DROP TRIGGER grid_private_learning_job ON public.jobs;
DROP FUNCTION public.guard_private_learning_report();
DROP FUNCTION public.grid_learning_report_id(uuid);
DROP FUNCTION public.guard_private_trained_version();
DROP FUNCTION public.guard_private_learning_job();
DROP FUNCTION public.grid_private_assignment_pin(uuid);
"""
