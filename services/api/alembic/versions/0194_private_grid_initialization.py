"""Pin independent private training origins and allow geometry-only partial TRAIN photos."""

import sqlalchemy as sa
from alembic import op

revision = "0194_private_grid_initialization"
down_revision = "0193_private_game_grid_models"
branch_labels = depends_on = None

# This predicate is local to the v4 cohort admission function already optimized in 0192.
PARTIAL = """AND header.sampling_policy
     ='full-symbol-content-sampling-v1'
    AND member.frozen->'recording'->'geometryOnlyTraining'='true'::jsonb
    AND member.frozen->'recording'->>'contentSamplingPolicy'
     ='full-symbol-content-sampling-v1'"""
INDEPENDENT = """AND member.frozen->'recording'->'geometryOnlyTraining'='true'::jsonb
    AND ((header.sampling_policy='full-symbol-content-sampling-v1'
          AND member.frozen->'recording'->>'contentSamplingPolicy'=header.sampling_policy)
         OR (header.photo_split->>'weightInitialization'='from_scratch'
          AND member.frozen->'recording'->>'weightInitialization'='from_scratch'
          AND header.photo_split->>'independentGameId'=wanted::text))"""

COHORT = """
CREATE FUNCTION public.guard_grid_independent_cohort() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE d jsonb:=NEW.document; init text:=d->>'weightInitialization'; pin jsonb;
BEGIN
 IF TG_OP='UPDATE' AND (OLD.document->>'weightInitialization' IS DISTINCT FROM init
    OR OLD.document#>>'{photoSplit,independentGameId}' IS DISTINCT FROM
       d#>>'{photoSplit,independentGameId}') THEN
   RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID';
 END IF;
 IF init IS NULL AND d#>>'{photoSplit,independentGameId}' IS NULL
    AND d#>>'{photoSplit,weightInitialization}' IS NULL THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' AND NEW.document=OLD.document THEN RETURN NEW; END IF;
 pin:=public.grid_private_assignment_pin(NEW.game_id);
 IF pin IS NULL OR init IS NULL OR init NOT IN ('from_scratch','assigned_weights')
    OR d->'privateLearning' IS DISTINCT FROM pin OR (init='from_scratch' AND
     (d#>>'{photoSplit,independentGameId}' IS DISTINCT FROM NEW.game_id::text
      OR d#>>'{photoSplit,weightInitialization}' IS DISTINCT FROM init
      OR d->>'mode' IS DISTINCT FROM 'screen+grid'
      OR d->>'policyVersion' IS DISTINCT FROM 'application-grid-corrections-v4'))
    OR (init='assigned_weights' AND d#>>'{photoSplit,independentGameId}' IS NOT NULL) THEN
   RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_independent_cohort BEFORE INSERT OR UPDATE OF document
 ON game_data_v2.grid_training_cohorts FOR EACH ROW EXECUTE FUNCTION
 public.guard_grid_independent_cohort()
"""

JOB = """
CREATE FUNCTION public.guard_grid_weight_initialization() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE p jsonb:=NEW.input_payload; init text; pin jsonb; expected text; frozen jsonb;
BEGIN
 IF TG_OP='UPDATE' AND OLD.game_id IS NOT DISTINCT FROM NEW.game_id AND OLD.input_payload=p THEN
   RETURN NEW;
 END IF;
 IF NEW.job_type::text='grid_correction_learning'
   AND p->>'learning_kind'='grid-correction-learning-v1' THEN
   pin:=p#>'{pins,privateLearning}'; init:=p#>>'{pins,weightInitialization}';
   IF pin IS NOT NULL AND init IS NULL AND TG_OP='INSERT' THEN
     RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_REQUIRED'; END IF;
   IF init IS DISTINCT FROM p#>>'{preview,weightInitialization}' THEN
     RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 ELSIF NEW.job_type::text='grid_training' THEN
   pin:=p->'private_learning'; init:=p->>'weight_initialization';
 ELSE RETURN NEW;
 END IF;
 IF TG_OP='UPDATE' AND (OLD.input_payload->>'weight_initialization' IS DISTINCT FROM
    p->>'weight_initialization' OR OLD.input_payload#>>'{pins,weightInitialization}'
    IS DISTINCT FROM p#>>'{pins,weightInitialization}') THEN
   RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 IF NEW.job_type::text='grid_training' AND pin IS NOT NULL THEN
   SELECT c.document INTO frozen FROM game_data_v2.grid_training_cohorts c
   WHERE c.game_id=NEW.game_id AND c.id=(p->>'cohort_id')::uuid;
   IF init IS DISTINCT FROM frozen->>'weightInitialization' THEN
     RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 END IF;
 IF init IS NULL THEN RETURN NEW; END IF;
 IF pin IS NULL OR pin->>'gameId' IS DISTINCT FROM NEW.game_id::text THEN
   RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 SELECT CASE WHEN v.family_id=f.id AND f.owner_game_id=NEW.game_id
     AND v.manifest_json::jsonb#>>'{provenance,independentGameId}'=NEW.game_id::text
     AND v.manifest_json::jsonb#>>'{provenance,weightInitialization}' IN
         ('from_scratch','assigned_weights')
    THEN 'assigned_weights' ELSE 'from_scratch' END INTO expected
 FROM public.grid_model_versions v JOIN public.grid_model_families f
 ON f.id=(pin->>'targetFamilyId')::uuid WHERE v.id=(pin->>'baseVersionId')::uuid;
 IF init IS DISTINCT FROM expected OR (init='from_scratch' AND
    ((NEW.job_type::text='grid_training' AND (p->>'mode' IS DISTINCT FROM 'screen+grid'
       OR p->>'preset_id' IS DISTINCT FROM 'screen-grid-corrections-v1'
       OR frozen->>'policyVersion' IS DISTINCT FROM 'application-grid-corrections-v4'
       OR frozen#>>'{photoSplit,weightInitialization}' IS DISTINCT FROM init
       OR p->'content_experiment' IS NOT NULL))
      OR (NEW.job_type::text='grid_correction_learning' AND
        (coalesce(p#>>'{command,trainingMode}','screen+grid')<>'screen+grid'
         OR p#>>'{command,contentExperiment}' IS NOT NULL
         OR p#>>'{command,rescueVariant}' IS NOT NULL))
    )) THEN RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_initialization_job BEFORE INSERT OR UPDATE OF input_payload,game_id
 ON public.jobs
FOR EACH ROW EXECUTE FUNCTION public.guard_grid_weight_initialization()
"""

VERSION = """
CREATE FUNCTION public.guard_independent_grid_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE doc jsonb:=NEW.manifest_json::jsonb; owner_id uuid; run jsonb; sealed jsonb; init text;
BEGIN
 SELECT owner_game_id INTO owner_id FROM public.grid_model_families WHERE id=NEW.family_id;
 IF owner_id IS NULL THEN
   IF doc->'provenance' ?| array['independentGameId','weightInitialization'] THEN
     RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
   RETURN NEW;
 END IF;
 SELECT j.input_payload,j.checkpoint_payload#>'{export,descriptor,payload}' INTO run,sealed
 FROM public.jobs j WHERE j.id=(doc#>>'{provenance,runId}')::uuid
 AND j.game_id=owner_id AND j.job_type::text='grid_training';
 init:=run->>'weight_initialization';
 IF init IS NULL AND NOT(doc->'provenance' ?| array['independentGameId','weightInitialization'])
   THEN RETURN NEW; END IF;
 IF init IS NULL OR doc#>>'{provenance,weightInitialization}' IS DISTINCT FROM init
   OR doc#>>'{provenance,independentGameId}' IS DISTINCT FROM owner_id::text
   OR sealed IS DISTINCT FROM doc THEN
   RAISE EXCEPTION 'GRID_PRIVATE_INITIALIZATION_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER grid_independent_version BEFORE INSERT ON public.grid_model_versions
 FOR EACH ROW EXECUTE FUNCTION public.guard_independent_grid_version()
"""


def _partial(*, restore: bool) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("SELECT pg_advisory_xact_lock(9910994)")
    op.execute("SELECT pg_advisory_xact_lock(9921002)")
    sql = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT pg_get_functiondef("
                "'public.recording_photo_cohort_v4(uuid,jsonb,text)'::regprocedure)"
            )
        )
        .scalar_one()
    )
    old, new = (INDEPENDENT, PARTIAL) if restore else (PARTIAL, INDEPENDENT)
    if sql.count(old) != 1:
        raise RuntimeError(
            "The existing cohort function has an unexpected partial-photo predicate."
        )
    op.get_bind().exec_driver_sql(sql.replace(old, new))


def upgrade() -> None:
    _partial(restore=False)
    for statement in (COHORT, JOB, VERSION):
        op.execute(statement)


def downgrade() -> None:
    marked = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM game_data_v2.grid_training_cohorts "
            "WHERE document ? 'weightInitialization') OR EXISTS (SELECT 1 FROM public.jobs "
            "WHERE input_payload ? 'weight_initialization' "
            "OR input_payload->'pins' ? 'weightInitialization')"
        )
    )
    if marked:
        raise RuntimeError("Independent grid learning records require migration 0194.")
    _partial(restore=True)
    op.execute("DROP TRIGGER grid_independent_cohort ON game_data_v2.grid_training_cohorts")
    op.execute("DROP FUNCTION public.guard_grid_independent_cohort()")
    op.execute("DROP TRIGGER grid_independent_version ON public.grid_model_versions")
    op.execute("DROP FUNCTION public.guard_independent_grid_version()")
    op.execute("DROP TRIGGER grid_initialization_job ON public.jobs")
    op.execute("DROP FUNCTION public.guard_grid_weight_initialization()")
