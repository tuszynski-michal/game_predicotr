"""Add immutable photo-only roles and buffers to the existing private registry."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_permissions_v4 import (
    INTERNAL,
    SAFE,
    enforce_recording_permissions,
)
from game_predictor_api.storage.source_recording_sql_v4 import FUNCTION_SQL, TABLE_SQL
from sqlalchemy import text

revision = "0170_grid_correction_photo_roles"
down_revision = "0169_board_search_sequence_logs"
branch_labels = depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    quoted = connection.dialect.identifier_preparer.quote(capability)
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(TABLE_SQL)
    op.execute(FUNCTION_SQL)
    op.execute(f"ALTER TABLE public.recording_photo_uses OWNER TO {quoted}")
    for signature in (*SAFE, *INTERNAL, "public.recording_cohort_command_v3(uuid,jsonb,text)"):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {quoted}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    # Existing app identities are discovered from the old safe entry point, not guessed.
    roles = (
        connection.execute(
            text("""
      SELECT DISTINCT r.rolname FROM pg_proc p
      CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
      WHERE p.oid='public.recording_cohort_command_legacy_v3(uuid,jsonb,text)'::regprocedure
       AND a.privilege_type='EXECUTE' AND NOT r.rolsuper AND r.rolname<>:capability
    """),
            {"capability": capability},
        )
        .scalars()
        .all()
    )
    for role in roles:
        enforce_recording_permissions(connection, role)


def downgrade() -> None:
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT 1 FROM public.recording_photo_uses)")):
        raise RuntimeError("Photo-only use history prevents destructive downgrade.")
    op.execute("DROP FUNCTION public.recording_cohort_command_v3(uuid,jsonb,text)")
    op.execute(
        "ALTER FUNCTION public.recording_cohort_command_legacy_v3(uuid,jsonb,text) "
        "RENAME TO recording_cohort_command_v3"
    )
    op.execute("DROP FUNCTION public.recording_photo_cohort_v1(uuid,jsonb,text)")
    op.execute("DROP FUNCTION public.recording_photo_context_v1(uuid,uuid[])")
    op.execute("DROP TABLE public.recording_photo_uses")
