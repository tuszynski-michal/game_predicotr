"""Drop legacy trigger functions in ``public`` that no trigger references (D-467, S1).

The functions belonged to the removed legacy public game store (migration 0125).
The list is frozen; the migration refuses when any listed function is still used
by a trigger or has another dependency, and it never touches functions outside
the list.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0129_drop_orphaned_legacy_trigger_functions"
down_revision = "0128_partial_board_reconciliation_receipts"
branch_labels = None
depends_on = None

ORPHANED_FUNCTIONS: tuple[str, ...] = (
    "guard_image_review_queue_topology",
    "populate_image_review_item_sequence_scope",
    "project_image_review_queue_delete",
    "project_image_review_queue_insert",
    "project_image_review_queue_status",
    "synchronize_image_review_item_sequence_number",
    "synchronize_image_review_job_status",
)


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("LEGACY_TRIGGER_FUNCTION_DROP_REQUIRES_ONLINE_PREFLIGHT")
    connection = op.get_bind()
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '120s'"))
    connection.execute(text("SET LOCAL search_path = pg_catalog, public"))
    rows = connection.execute(
        text(
            """
            SELECT p.proname,
                   pg_get_function_identity_arguments(p.oid) AS arguments,
                   (SELECT count(*) FROM pg_trigger t WHERE t.tgfoid = p.oid) AS triggers,
                   (SELECT count(*) FROM pg_depend d
                     WHERE d.refclassid = 'pg_proc'::regclass AND d.refobjid = p.oid
                       AND d.deptype <> 'i') AS dependents
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = ANY(:names)
              AND p.pronargs = 0 AND p.prorettype = 'pg_catalog.trigger'::regtype
            """
        ),
        {"names": list(ORPHANED_FUNCTIONS)},
    ).all()
    used = [f"{row.proname}({row.arguments})" for row in rows if row.triggers or row.dependents]
    if used:
        raise RuntimeError("LEGACY_TRIGGER_FUNCTION_STILL_REFERENCED: " + ", ".join(sorted(used)))
    for row in rows:
        connection.execute(text(f'DROP FUNCTION public."{row.proname}"({row.arguments}) RESTRICT'))


def downgrade() -> None:
    raise RuntimeError(
        "LEGACY_TRIGGER_FUNCTION_DOWNGRADE_UNSUPPORTED: "
        "the function bodies belonged to the removed legacy public store"
    )
