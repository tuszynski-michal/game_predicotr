"""Reserve private grid families with immutable per-game ownership."""

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.grid_private_learning_sql import INSTALL_SQL, REMOVE_SQL

revision = "0193_private_game_grid_models"
down_revision = "0192_grid_cohort_header_cache"
branch_labels = depends_on = None

EVENT_CONSTRAINT = "ck_grid_assignment_event_command"
EVENT_REQUIREMENTS = """
    AND expected_revision IS NOT NULL AND expected_revision>=0 AND revision=expected_revision+1
    AND command_sha256 IS NOT NULL AND command_sha256 ~ '^[0-9a-f]{64}$'
    AND command_json IS NOT NULL AND receipt_json IS NOT NULL AND actor IS NOT NULL
    AND evidence_sha256 IS NOT NULL AND evidence_sha256 ~ '^[0-9a-f]{64}$'
    AND (kind<>'bootstrap' OR expected_revision=0))
"""

# Historical jobs store related games under several immutable payload keys.
JOB_SCOPE_SQL = """
CREATE FUNCTION public.grid_operation_game_ids(primary_game uuid, payload jsonb)
RETURNS SETOF uuid LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
    SELECT primary_game WHERE primary_game IS NOT NULL
    UNION SELECT (value #>> '{}')::uuid
        FROM jsonb_path_query(payload, '$.shared_cohorts[*].game_id') AS pin(value)
    UNION SELECT (value #>> '{}')::uuid
        FROM jsonb_path_query(payload, '$.cohorts[*].game_id') AS pin(value)
    UNION SELECT (value #>> '{}')::uuid
        FROM jsonb_path_query(payload, '$.pins.historicalCohorts[*].gameId') AS pin(value)
    UNION SELECT (value #>> '{}')::uuid
        FROM jsonb_path_query(payload, '$.pins.scope.trainingGameIds[*]') AS pin(value)
    UNION SELECT (value #>> '{}')::uuid
        FROM jsonb_path_query(payload, '$.command.additionalGameIds[*]') AS pin(value)
$$
"""

JOB_GUARD_SQL = """
CREATE FUNCTION public.guard_private_grid_job() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog SET lock_timeout = '5s' AS $$
BEGIN
    IF NEW.job_type::text NOT IN ('grid_training', 'grid_model_evaluation',
        'grid_correction_learning', 'import', 'image_grid_reinference',
        'image_geometry_rollout_backfill')
        OR NEW.status::text NOT IN ('created', 'processing', 'waiting_for_review') THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE'
        AND OLD.status::text IN ('created', 'processing', 'waiting_for_review')
        AND ROW(OLD.game_id, OLD.job_type, OLD.input_payload)
            IS NOT DISTINCT FROM ROW(NEW.game_id, NEW.job_type, NEW.input_payload) THEN
        RETURN NEW;
    END IF;
    PERFORM pg_advisory_xact_lock(9910994);
    IF NEW.job_type::text IN ('grid_training', 'grid_correction_learning')
        AND EXISTS (
            SELECT 1 FROM public.grid_operation_game_ids(NEW.game_id, NEW.input_payload) scope(id)
            WHERE scope.id <> NEW.game_id
        )
        AND EXISTS (
            SELECT 1 FROM public.games game
            JOIN public.grid_operation_game_ids(NEW.game_id, NEW.input_payload) scope(id)
                ON game.id=scope.id
            WHERE game.grid_model_private
        ) THEN
        RAISE EXCEPTION 'GRID_SHARED_PRIVATE_GAME';
    END IF;
    RETURN NEW;
END;
$$
"""

ASSIGNMENT_GUARD_SQL = """
CREATE FUNCTION public.guard_private_grid_assignment() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE
    version_owner uuid;
    training_owner uuid;
BEGIN
    SELECT family.owner_game_id INTO version_owner
    FROM public.grid_model_versions version
    JOIN public.grid_model_families family ON family.id=version.family_id
    WHERE version.id=NEW.version_id;
    IF TG_TABLE_NAME = 'grid_model_default' THEN
        IF version_owner IS NOT NULL THEN RAISE EXCEPTION 'GRID_MODEL_PRIVATE_DEFAULT'; END IF;
        RETURN NEW;
    END IF;
    SELECT owner_game_id INTO training_owner
    FROM public.grid_model_families WHERE id=NEW.training_family_id;
    IF (version_owner IS NOT NULL AND version_owner <> NEW.game_id)
        OR (training_owner IS NOT NULL AND training_owner <> NEW.game_id) THEN
        RAISE EXCEPTION 'GRID_MODEL_PRIVATE_OWNER_MISMATCH';
    END IF;
    IF EXISTS (SELECT 1 FROM public.games WHERE id=NEW.game_id AND grid_model_private)
        AND training_owner IS DISTINCT FROM NEW.game_id THEN
        RAISE EXCEPTION 'GRID_MODEL_PRIVATE_FAMILY_REQUIRED';
    END IF;
    RETURN NEW;
END;
$$
"""

OWNERSHIP_GUARD_SQL = """
CREATE FUNCTION public.guard_private_grid_ownership() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF TG_TABLE_NAME = 'grid_model_families' THEN
        IF NEW.owner_game_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.games WHERE id=NEW.owner_game_id AND grid_model_private
        ) THEN RAISE EXCEPTION 'GRID_MODEL_PRIVATE_GAME_REQUIRED'; END IF;
    ELSIF OLD.grid_model_private AND NOT NEW.grid_model_private THEN
        RAISE EXCEPTION 'GRID_MODEL_PRIVATE_OWNERSHIP_IMMUTABLE';
    ELSIF NEW.grid_model_private AND EXISTS (
        SELECT 1 FROM public.game_grid_model_assignments assignment
        LEFT JOIN public.grid_model_families family ON family.id=assignment.training_family_id
        WHERE assignment.game_id=NEW.id AND family.owner_game_id IS DISTINCT FROM NEW.id
    ) THEN RAISE EXCEPTION 'GRID_MODEL_PRIVATE_FAMILY_REQUIRED';
    END IF;
    RETURN NEW;
END;
$$
"""


def _lock() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("SELECT pg_advisory_xact_lock(9910994)")


def _assignment_event_constraint(*, private: bool) -> None:
    table = "game_grid_model_assignment_events"
    op.drop_constraint(EVENT_CONSTRAINT, table, schema="public")
    kinds = "'activate','rollback','bootstrap'" + (",'private_enable'" if private else "")
    op.create_check_constraint(
        EVENT_CONSTRAINT,
        table,
        f"kind='historical_assignment' OR (kind IN ({kinds}) {EVENT_REQUIREMENTS}",
        schema="public",
    )


def upgrade() -> None:
    _lock()
    op.add_column(
        "games",
        sa.Column("grid_model_private", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="public",
    )
    op.add_column("grid_model_families", sa.Column("owner_game_id", sa.Uuid()), schema="public")
    op.create_unique_constraint(
        "uq_grid_model_family_owner", "grid_model_families", ["owner_game_id"], schema="public"
    )
    _assignment_event_constraint(private=True)
    for statement in (JOB_SCOPE_SQL, JOB_GUARD_SQL, ASSIGNMENT_GUARD_SQL, OWNERSHIP_GUARD_SQL):
        op.execute(statement)
    op.execute("""CREATE TRIGGER grid_private_job_admission
        BEFORE INSERT OR UPDATE OF status, game_id, job_type, input_payload ON public.jobs
        FOR EACH ROW EXECUTE FUNCTION public.guard_private_grid_job()""")
    for table in ("game_grid_model_assignments", "grid_model_default"):
        op.execute(f"""CREATE TRIGGER grid_private_assignment
            BEFORE INSERT OR UPDATE ON public.{table}
            FOR EACH ROW EXECUTE FUNCTION public.guard_private_grid_assignment()""")
    op.execute("""CREATE TRIGGER grid_private_family_owner
        BEFORE INSERT ON public.grid_model_families
        FOR EACH ROW EXECUTE FUNCTION public.guard_private_grid_ownership()""")
    op.execute("""CREATE CONSTRAINT TRIGGER grid_private_game_state
        AFTER UPDATE ON public.games DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW WHEN (OLD.grid_model_private IS DISTINCT FROM NEW.grid_model_private)
        EXECUTE FUNCTION public.guard_private_grid_ownership()""")

    for statement in INSTALL_SQL:
        op.execute(statement)


def downgrade() -> None:
    _lock()
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.games WHERE grid_model_private)
            OR EXISTS (SELECT 1 FROM public.grid_model_families WHERE owner_game_id IS NOT NULL)
        THEN
            RAISE EXCEPTION 'GRID_MODEL_PRIVATE_DOWNGRADE_HAS_HISTORY';
        END IF;
    END $$""")
    op.execute(REMOVE_SQL)
    op.execute("DROP TRIGGER grid_private_game_state ON public.games")
    op.execute("DROP TRIGGER grid_private_family_owner ON public.grid_model_families")
    for table in ("game_grid_model_assignments", "grid_model_default"):
        op.execute(f"DROP TRIGGER grid_private_assignment ON public.{table}")
    op.execute("DROP TRIGGER grid_private_job_admission ON public.jobs")
    op.execute("DROP FUNCTION public.guard_private_grid_ownership()")
    op.execute("DROP FUNCTION public.guard_private_grid_assignment()")
    op.execute("DROP FUNCTION public.guard_private_grid_job()")
    op.execute("DROP FUNCTION public.grid_operation_game_ids(uuid, jsonb)")
    _assignment_event_constraint(private=False)
    op.drop_constraint("uq_grid_model_family_owner", "grid_model_families", schema="public")
    op.drop_column("grid_model_families", "owner_game_id", schema="public")
    op.drop_column("games", "grid_model_private", schema="public")
