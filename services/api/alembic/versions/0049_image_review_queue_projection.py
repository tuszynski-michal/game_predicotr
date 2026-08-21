"""Persist the immutable operational image review queue projection.

Revision ID: 0049_image_review_queue_projection
Revises: 0048_image_page_geometry_overrides
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_image_review_queue_projection"
down_revision: str | Sequence[str] | None = "0048_image_page_geometry_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_review_queue_states",
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("queue_version", sa.BigInteger(), nullable=False),
        sa.Column("total_count", sa.BigInteger(), nullable=False),
        sa.Column("pending_count", sa.BigInteger(), nullable=False),
        sa.Column("accepted_count", sa.BigInteger(), nullable=False),
        sa.Column("corrected_count", sa.BigInteger(), nullable=False),
        sa.Column("rejected_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "queue_version > 0 AND total_count >= 0 "
            "AND pending_count >= 0 AND accepted_count >= 0 "
            "AND corrected_count >= 0 AND rejected_count >= 0",
            name="ck_image_review_queue_states_nonnegative",
        ),
        sa.CheckConstraint(
            "total_count = pending_count + accepted_count + corrected_count + rejected_count",
            name="ck_image_review_queue_states_total",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("import_job_id", name="pk_image_review_queue_states"),
    )
    op.create_table(
        "image_review_queue_items",
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_order_index", sa.BigInteger(), nullable=False),
        sa.Column("position_index", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_order_index >= 0 AND position_index BETWEEN 0 AND 8",
            name="ck_image_review_queue_items_position",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected', 'rejected')",
            name="ck_image_review_queue_items_status",
        ),
        sa.ForeignKeyConstraint(
            ["review_item_id"],
            ["image_review_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("review_item_id", name="pk_image_review_queue_items"),
        sa.UniqueConstraint(
            "import_job_id",
            "source_order_index",
            "position_index",
            "review_item_id",
            name="uq_image_review_queue_items_order_key",
        ),
    )
    op.create_index(
        "ix_image_review_queue_items_job_status_order",
        "image_review_queue_items",
        [
            "import_job_id",
            "status",
            "source_order_index",
            "position_index",
            "review_item_id",
        ],
    )

    # Existing operational review items are projected from their immutable
    # source-file association. A missing association would already make the
    # current workbench silently hide an item, so migration fails closed.
    op.execute(
        sa.text(
            """
            INSERT INTO image_review_queue_items (
                review_item_id,
                import_job_id,
                source_order_index,
                position_index,
                status,
                created_at
            )
            SELECT
                review.id,
                source.import_job_id,
                association.order_index,
                board.position_index,
                review.status,
                review.created_at
            FROM image_review_items AS review
            JOIN recognized_boards AS board
              ON board.id = review.recognized_board_id
            JOIN source_images AS source
              ON source.id = board.source_image_id
            JOIN image_import_job_files AS association
              ON association.job_id = source.import_job_id
             AND association.file_execution_key = source.file_execution_key
            ORDER BY
                source.import_job_id,
                association.order_index,
                board.position_index,
                review.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM image_review_items AS review
                    LEFT JOIN image_review_queue_items AS queue_item
                      ON queue_item.review_item_id = review.id
                    WHERE queue_item.review_item_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot project image review queue: '
                        'a review item has no source-order association'
                        USING ERRCODE = '23514';
                END IF;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO image_review_queue_states (
                import_job_id,
                queue_version,
                total_count,
                pending_count,
                accepted_count,
                corrected_count,
                rejected_count,
                created_at,
                updated_at
            )
            SELECT
                import_job_id,
                1,
                count(*),
                count(*) FILTER (WHERE status = 'pending'),
                count(*) FILTER (WHERE status = 'accepted'),
                count(*) FILTER (WHERE status = 'corrected'),
                count(*) FILTER (WHERE status = 'rejected'),
                min(created_at),
                now()
            FROM image_review_queue_items
            GROUP BY import_job_id
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION project_image_review_queue_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                projected_job_id uuid;
                projected_source_order bigint;
                projected_position smallint;
            BEGIN
                SELECT
                    source.import_job_id,
                    association.order_index,
                    board.position_index
                INTO
                    projected_job_id,
                    projected_source_order,
                    projected_position
                FROM recognized_boards AS board
                JOIN source_images AS source
                  ON source.id = board.source_image_id
                JOIN image_import_job_files AS association
                  ON association.job_id = source.import_job_id
                 AND association.file_execution_key = source.file_execution_key
                WHERE board.id = NEW.recognized_board_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot project image review item %: source-order association is missing',
                        NEW.id
                        USING ERRCODE = '23514';
                END IF;

                INSERT INTO image_review_queue_items (
                    review_item_id,
                    import_job_id,
                    source_order_index,
                    position_index,
                    status,
                    created_at
                ) VALUES (
                    NEW.id,
                    projected_job_id,
                    projected_source_order,
                    projected_position,
                    NEW.status,
                    NEW.created_at
                );

                INSERT INTO image_review_queue_states (
                    import_job_id,
                    queue_version,
                    total_count,
                    pending_count,
                    accepted_count,
                    corrected_count,
                    rejected_count,
                    created_at,
                    updated_at
                ) VALUES (
                    projected_job_id,
                    1,
                    1,
                    CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END,
                    NEW.created_at,
                    now()
                )
                ON CONFLICT (import_job_id) DO UPDATE SET
                    queue_version = image_review_queue_states.queue_version + 1,
                    total_count = image_review_queue_states.total_count + 1,
                    pending_count = image_review_queue_states.pending_count
                        + CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                    accepted_count = image_review_queue_states.accepted_count
                        + CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                    corrected_count = image_review_queue_states.corrected_count
                        + CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                    rejected_count = image_review_queue_states.rejected_count
                        + CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END,
                    updated_at = now();

                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION project_image_review_queue_status()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                projected_job_id uuid;
            BEGIN
                IF NEW.status = OLD.status THEN
                    RETURN NEW;
                END IF;

                UPDATE image_review_queue_items
                SET status = NEW.status
                WHERE review_item_id = NEW.id
                RETURNING import_job_id INTO projected_job_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot update image review queue item %: projection is missing',
                        NEW.id
                        USING ERRCODE = '23514';
                END IF;

                UPDATE image_review_queue_states
                SET
                    pending_count = pending_count
                        - CASE WHEN OLD.status = 'pending' THEN 1 ELSE 0 END
                        + CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                    accepted_count = accepted_count
                        - CASE WHEN OLD.status = 'accepted' THEN 1 ELSE 0 END
                        + CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                    corrected_count = corrected_count
                        - CASE WHEN OLD.status = 'corrected' THEN 1 ELSE 0 END
                        + CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                    rejected_count = rejected_count
                        - CASE WHEN OLD.status = 'rejected' THEN 1 ELSE 0 END
                        + CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END,
                    updated_at = now()
                WHERE import_job_id = projected_job_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot update image review queue state for job %: projection is missing',
                        projected_job_id
                        USING ERRCODE = '23514';
                END IF;

                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION project_image_review_queue_delete()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                projected_job_id uuid;
                projected_status varchar(20);
            BEGIN
                DELETE FROM image_review_queue_items
                WHERE review_item_id = OLD.id
                RETURNING import_job_id, status
                INTO projected_job_id, projected_status;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot delete image review queue item %: projection is missing',
                        OLD.id
                        USING ERRCODE = '23514';
                END IF;

                UPDATE image_review_queue_states
                SET
                    queue_version = queue_version + 1,
                    total_count = total_count - 1,
                    pending_count = pending_count
                        - CASE WHEN projected_status = 'pending' THEN 1 ELSE 0 END,
                    accepted_count = accepted_count
                        - CASE WHEN projected_status = 'accepted' THEN 1 ELSE 0 END,
                    corrected_count = corrected_count
                        - CASE WHEN projected_status = 'corrected' THEN 1 ELSE 0 END,
                    rejected_count = rejected_count
                        - CASE WHEN projected_status = 'rejected' THEN 1 ELSE 0 END,
                    updated_at = now()
                WHERE import_job_id = projected_job_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot delete image review queue state for job %: projection is missing',
                        projected_job_id
                        USING ERRCODE = '23514';
                END IF;

                DELETE FROM image_review_queue_states
                WHERE import_job_id = projected_job_id
                  AND total_count = 0;

                RETURN OLD;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION guard_image_review_queue_topology()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.review_item_id IS DISTINCT FROM OLD.review_item_id
                   OR NEW.import_job_id IS DISTINCT FROM OLD.import_job_id
                   OR NEW.source_order_index IS DISTINCT FROM OLD.source_order_index
                   OR NEW.position_index IS DISTINCT FROM OLD.position_index THEN
                    RAISE EXCEPTION
                        'Image review queue topology is immutable for item %',
                        OLD.review_item_id
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_image_review_queue_insert
            AFTER INSERT ON image_review_items
            FOR EACH ROW
            EXECUTE FUNCTION project_image_review_queue_insert()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_image_review_queue_status
            AFTER UPDATE OF status ON image_review_items
            FOR EACH ROW
            WHEN (OLD.status IS DISTINCT FROM NEW.status)
            EXECUTE FUNCTION project_image_review_queue_status()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_image_review_queue_delete
            BEFORE DELETE ON image_review_items
            FOR EACH ROW
            EXECUTE FUNCTION project_image_review_queue_delete()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_image_review_queue_topology_guard
            BEFORE UPDATE OF review_item_id, import_job_id, source_order_index, position_index
            ON image_review_queue_items
            FOR EACH ROW
            EXECUTE FUNCTION guard_image_review_queue_topology()
            """
        )
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_image_review_queue_topology_guard ON image_review_queue_items")
    op.execute("DROP TRIGGER trg_image_review_queue_delete ON image_review_items")
    op.execute("DROP TRIGGER trg_image_review_queue_status ON image_review_items")
    op.execute("DROP TRIGGER trg_image_review_queue_insert ON image_review_items")
    op.execute("DROP FUNCTION guard_image_review_queue_topology()")
    op.execute("DROP FUNCTION project_image_review_queue_delete()")
    op.execute("DROP FUNCTION project_image_review_queue_status()")
    op.execute("DROP FUNCTION project_image_review_queue_insert()")
    op.drop_index(
        "ix_image_review_queue_items_job_status_order",
        table_name="image_review_queue_items",
    )
    op.drop_table("image_review_queue_items")
    op.drop_table("image_review_queue_states")
