"""Add opt-in partial TRAIN and excluded-component fences without changing history."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_permissions_v10 import (
    INTERNAL,
    SAFE,
    enforce_recording_permissions,
)
from game_predictor_api.storage.source_recording_sql_v10 import BIND_SQL, PHOTO_SQL, WRAPPER_SQL
from sqlalchemy import text

revision = "0184_effective_grid_material"
down_revision = "0183_production_cell_evaluation"
branch_labels = depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    owner = connection.dialect.identifier_preparer.quote(capability)
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(PHOTO_SQL)
    op.execute(BIND_SQL)
    op.execute(WRAPPER_SQL)
    for signature in (*SAFE, *INTERNAL):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {owner}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    roles = (
        connection.execute(
            text("""SELECT DISTINCT r.rolname FROM pg_proc p
      CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
      WHERE p.oid='public.recording_cohort_command_v6(uuid,jsonb,text)'::regprocedure
      AND a.privilege_type='EXECUTE' AND NOT r.rolsuper AND r.rolname<>:owner"""),
            {"owner": capability},
        )
        .scalars()
        .all()
    )
    for role in roles:
        enforce_recording_permissions(connection, role)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("SELECT pg_advisory_xact_lock(9910994)")
    op.execute("SELECT pg_advisory_xact_lock(9921002)")
    if op.get_bind().scalar(
        text("""SELECT EXISTS(
      SELECT 1 FROM game_data_v2.grid_training_cohorts
      WHERE document->'photoSplit'->'learningMaterial'->>'version'
       ='effective-grid-learning-material-v1')""")
    ):
        raise RuntimeError("Effective material cohort history prevents downgrade.")
    for signature in (*SAFE, *INTERNAL):
        op.execute(f"DROP FUNCTION {signature}")
