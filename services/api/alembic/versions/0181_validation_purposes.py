"""Add a screen correction capability without reinterpreting historical SQL."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_permissions_v8 import (
    INTERNAL,
    SAFE,
    enforce_recording_permissions,
)
from game_predictor_api.storage.source_recording_sql_v8 import (
    BIND_SQL,
    CONTEXT_SQL,
    DIAGNOSTIC_SQL,
    FENCE_SQL,
    LEGACY_CONTEXT_SQL,
    PHOTO_SQL,
    TABLE_SQL,
    WRAPPER_SQL,
)
from sqlalchemy import text

revision = "0181_validation_purposes"
down_revision = "0180_screen_grid_corrections"
branch_labels = depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    owner = connection.dialect.identifier_preparer.quote(capability)
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    for sql in (
        TABLE_SQL,
        LEGACY_CONTEXT_SQL,
        CONTEXT_SQL,
        PHOTO_SQL,
        FENCE_SQL,
        WRAPPER_SQL,
        DIAGNOSTIC_SQL,
        BIND_SQL,
    ):
        op.execute(sql)
    for signature in (*SAFE, *INTERNAL):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {owner}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    roles = (
        connection.execute(
            text("""SELECT DISTINCT r.rolname FROM pg_proc p
      CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
      WHERE p.oid='public.recording_cohort_command_v3(uuid,jsonb,text)'::regprocedure
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
        text("""SELECT EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohorts
       WHERE document->>'policyVersion'='application-grid-corrections-v4')
       OR EXISTS(SELECT 1 FROM public.recording_photo_uses WHERE validation_purpose IS NOT NULL)
       OR EXISTS(SELECT 1 FROM public.recording_evidence WHERE kind='use'
        AND payload->>'purpose'='diagnostic_comparison')""")
    ):
        raise RuntimeError("Purpose history prevents downgrade.")
    op.execute("DROP TRIGGER recording_validation_admission ON public.recording_photo_uses")
    op.execute("DROP TRIGGER recording_legacy_selection_admission ON public.recording_evidence")
    for signature in (*SAFE, *reversed(INTERNAL)):
        op.execute(f"DROP FUNCTION {signature}")

    op.execute("ALTER TABLE public.recording_photo_uses DROP COLUMN validation_purpose")
    for name in (
        "ix_recording_diagnostic_byte",
        "ix_recording_diagnostic_pixel",
        "ix_recording_diagnostic_binding",
    ):
        op.execute(f"DROP INDEX public.{name}")
    from game_predictor_api.storage.source_recording_sql_v6 import CONTEXT_SQL as OLD_CONTEXT

    op.execute(OLD_CONTEXT.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
