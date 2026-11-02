"""Durable corrections parent and scoped report-v3 registry binding."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_permissions_v5 import (
    SIGNATURE,
    grant_recording_capability_dependencies,
)
from game_predictor_api.storage.source_recording_sql_v4 import FUNCTION_SQL as V4_SQL
from game_predictor_api.storage.source_recording_sql_v5 import BIND_SQL, WRAPPER_SQL
from sqlalchemy import text

revision = "0171_grid_correction_learning"
down_revision = "0170_grid_correction_photo_roles"
branch_labels = depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'grid_correction_learning'")
    connection = op.get_bind()
    owner = connection.dialect.identifier_preparer.quote(validate_recording_capability(connection))
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(BIND_SQL)
    op.execute(WRAPPER_SQL)
    op.execute(f"ALTER FUNCTION {SIGNATURE} OWNER TO {owner}")
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    grant_recording_capability_dependencies(connection)


def downgrade() -> None:
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.jobs "
            "WHERE job_type::text='grid_correction_learning')"
        )
    ):
        raise RuntimeError("Learning workflow history prevents downgrade.")
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.recording_commands "
            "WHERE receipt->>'evidenceLevel'='photo-only' AND kind='bind_existing_report')"
        )
    ):
        raise RuntimeError("Correction report bindings prevent downgrade.")
    wrapper = V4_SQL[V4_SQL.index("CREATE FUNCTION public.recording_cohort_command_v3(") :]
    op.execute(wrapper.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute(f"DROP FUNCTION {SIGNATURE}")
