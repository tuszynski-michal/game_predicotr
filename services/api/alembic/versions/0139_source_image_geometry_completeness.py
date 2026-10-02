"""Persisted D-484 geometry completeness of a source image (TASK-0807).

``source_images`` (game-owned, partitioned ``LIST (game_id)``) gains the state
the pipeline gate reads before symbol cells and search documents are
materialized:

* ``geometry_completeness_status`` -- ``geometry_complete``,
  ``geometry_incomplete`` or ``geometry_exception``; ``NULL`` means not
  evaluated (before the backfill) or outside the gate (superseded, failed
  import, no source geometry);
* ``geometry_completeness_evaluated_at`` -- set by every evaluation, also when
  the status stays ``NULL`` (the resumable backfill selects rows where it is
  ``NULL``);
* ``geometry_exception_reason`` / ``_by`` / ``_at`` -- the operator exception,
  non-empty exactly when the status is ``geometry_exception``.

The columns are added on the partitioned parent (catalog-only, no rewrite) and
reach every partition, including partitions of games created later (the
lifecycle compares partition columns with the parent; the frozen storage
manifest lists tables, not columns, so it does not change). The CHECKs are
validated immediately: every existing value is ``NULL``. Two partial indexes
serve the image queue (incomplete and exception images) and the backfill
cursor (images not evaluated yet).

Downgrade drops everything again, but refuses
(``SOURCE_IMAGE_GEOMETRY_EXCEPTION_PRESENT``) once an operator exception
exists: it is a human decision with author and reason that a recompute cannot
recreate. Plain statuses are derived data; the backfill restores them.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0139_source_image_geometry_completeness"
down_revision: str | Sequence[str] | None = "0138_rls_policy_function_parallel_safe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_IMAGES = "game_data_v2.source_images"
STATUS_CHECK = "ck_source_images_geometry_completeness_status"
STATUS_CHECK_EXPRESSION = (
    "geometry_completeness_status IS NULL OR geometry_completeness_status IN "
    "('geometry_complete', 'geometry_incomplete', 'geometry_exception')"
)
EVALUATED_CHECK = "ck_source_images_geometry_completeness_evaluated"
EVALUATED_CHECK_EXPRESSION = (
    "geometry_completeness_status IS NULL OR geometry_completeness_evaluated_at IS NOT NULL"
)
EXCEPTION_CHECK = "ck_source_images_geometry_exception"
EXCEPTION_CHECK_EXPRESSION = (
    "(geometry_completeness_status = 'geometry_exception' "
    "AND length(btrim(geometry_exception_reason)) > 0 "
    "AND length(btrim(geometry_exception_by)) > 0 "
    "AND geometry_exception_at IS NOT NULL) OR "
    "(geometry_completeness_status IS DISTINCT FROM 'geometry_exception' "
    "AND geometry_exception_reason IS NULL AND geometry_exception_by IS NULL "
    "AND geometry_exception_at IS NULL)"
)
QUEUE_INDEX = "ix_source_images_geometry_completeness_queue"
BACKFILL_INDEX = "ix_source_images_geometry_completeness_unevaluated"
_CHECKS = (
    (STATUS_CHECK, STATUS_CHECK_EXPRESSION),
    (EVALUATED_CHECK, EVALUATED_CHECK_EXPRESSION),
    (EXCEPTION_CHECK, EXCEPTION_CHECK_EXPRESSION),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {SOURCE_IMAGES} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        f"""ALTER TABLE {SOURCE_IMAGES}
            ADD COLUMN geometry_completeness_status varchar(24),
            ADD COLUMN geometry_completeness_evaluated_at timestamptz,
            ADD COLUMN geometry_exception_reason text,
            ADD COLUMN geometry_exception_by varchar(200),
            ADD COLUMN geometry_exception_at timestamptz"""
    )
    for name, expression in _CHECKS:
        op.execute(
            f"ALTER TABLE {SOURCE_IMAGES} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID"
        )
        op.execute(f"ALTER TABLE {SOURCE_IMAGES} VALIDATE CONSTRAINT {name}")
    op.execute(
        f"""CREATE INDEX {QUEUE_INDEX} ON {SOURCE_IMAGES}
            (game_id, geometry_completeness_status, relative_path, id)
            WHERE geometry_completeness_status IN ('geometry_incomplete', 'geometry_exception')"""
    )
    op.execute(
        f"""CREATE INDEX {BACKFILL_INDEX} ON {SOURCE_IMAGES} (game_id, id)
            WHERE geometry_completeness_evaluated_at IS NULL"""
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {SOURCE_IMAGES} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (
            SELECT 1 FROM {SOURCE_IMAGES}
            WHERE geometry_completeness_status = 'geometry_exception'
        ) THEN
            RAISE EXCEPTION 'SOURCE_IMAGE_GEOMETRY_EXCEPTION_PRESENT: an operator geometry '
                'exception exists; withdraw it before downgrading';
        END IF;
    END $guard$""")
    op.execute(f"DROP INDEX game_data_v2.{BACKFILL_INDEX}")
    op.execute(f"DROP INDEX game_data_v2.{QUEUE_INDEX}")
    for name, _expression in reversed(_CHECKS):
        op.execute(f"ALTER TABLE {SOURCE_IMAGES} DROP CONSTRAINT {name}")
    op.execute(
        f"""ALTER TABLE {SOURCE_IMAGES}
            DROP COLUMN geometry_exception_at,
            DROP COLUMN geometry_exception_by,
            DROP COLUMN geometry_exception_reason,
            DROP COLUMN geometry_completeness_evaluated_at,
            DROP COLUMN geometry_completeness_status"""
    )
