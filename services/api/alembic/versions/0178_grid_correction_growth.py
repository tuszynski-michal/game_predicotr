"""Append-only release evidence for unused legacy photo reservations."""

from alembic import op
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from game_predictor_api.storage.source_recording_permissions_v6 import (
    INTERNAL,
    SAFE,
    enforce_recording_permissions,
)
from game_predictor_api.storage.source_recording_replacement_sql import (
    REPLACEMENT_V4_SQL as V4_SQL,
)
from game_predictor_api.storage.source_recording_replacement_sql import (
    REPLACEMENT_V5_WRAPPER as V5_WRAPPER,
)
from game_predictor_api.storage.source_recording_sql_v6 import (
    CONTEXT_SQL,
    PHOTO_SQL,
    TABLE_SQL,
    WRAPPER_SQL,
)
from sqlalchemy import text

revision = "0178_grid_correction_growth"
down_revision = "0177_source_replacement_purge"
branch_labels = depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    capability = validate_recording_capability(connection)
    owner = connection.dialect.identifier_preparer.quote(capability)
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(TABLE_SQL)
    op.execute(CONTEXT_SQL)
    op.execute(PHOTO_SQL)
    op.execute(WRAPPER_SQL)
    op.execute(f"ALTER TABLE public.recording_photo_reservation_releases OWNER TO {owner}")
    for signature in (SAFE, INTERNAL):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {owner}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    roles = (
        connection.execute(
            text("""SELECT DISTINCT r.rolname FROM pg_proc p
     CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
     WHERE p.oid='public.recording_photo_context_v1(uuid,uuid[])'::regprocedure
      AND a.privilege_type='EXECUTE' AND NOT r.rolsuper AND r.rolname<>:owner"""),
            {"owner": capability},
        )
        .scalars()
        .all()
    )
    for role in roles:
        enforce_recording_permissions(connection, role)


def downgrade() -> None:
    connection = op.get_bind()
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("SELECT pg_advisory_xact_lock(9910994)")
    op.execute("SELECT pg_advisory_xact_lock(9921002)")
    if connection.scalar(
        text("""SELECT
      EXISTS(SELECT 1 FROM public.recording_photo_reservation_releases) OR
      EXISTS(SELECT 1 FROM public.recording_photo_uses WHERE reservation_policy='incremental-v2')
    """)
    ):
        raise RuntimeError("Incremental reservation history prevents destructive downgrade.")
    # Restore legacy implementations with the 0175 fences retained at revision 0177.
    context_start = V4_SQL.index("CREATE FUNCTION public.recording_photo_context_v1(")
    photo_start = V4_SQL.index("CREATE FUNCTION public.recording_photo_cohort_v1(")
    wrapper_start = V4_SQL.index("ALTER FUNCTION public.recording_cohort_command_v3(")
    op.execute(
        V4_SQL[context_start:photo_start].replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        )
    )
    op.execute(
        V4_SQL[photo_start:wrapper_start].replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        )
    )
    op.execute(V5_WRAPPER)
    op.execute(f"DROP FUNCTION {SAFE}")
    op.execute(f"DROP FUNCTION {INTERNAL}")
    op.execute("DROP TABLE public.recording_photo_reservation_releases")
    op.execute("ALTER TABLE public.recording_photo_uses DROP COLUMN reservation_policy")
