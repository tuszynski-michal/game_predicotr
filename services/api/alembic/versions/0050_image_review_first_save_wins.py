"""Persist superseded operational review outcomes.

Revision ID: 0050_image_review_first_save_wins
Revises: 0049_image_review_queue_projection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_image_review_first_save_wins"
down_revision: str | Sequence[str] | None = "0049_image_review_queue_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_image_review_items_status", "image_review_items", type_="check")
    op.create_check_constraint(
        "ck_image_review_items_status",
        "image_review_items",
        "status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')",
    )
    op.drop_constraint(
        "ck_image_review_queue_items_status",
        "image_review_queue_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_queue_items_status",
        "image_review_queue_items",
        "status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')",
    )
    op.drop_constraint(
        "ck_image_review_resolution_events_action",
        "image_review_resolution_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_resolution_events_action",
        "image_review_resolution_events",
        "action IN ('accepted', 'corrected', 'rejected', 'reopened', 'superseded')",
    )

    op.drop_constraint(
        "ck_image_review_queue_states_nonnegative",
        "image_review_queue_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_review_queue_states_total",
        "image_review_queue_states",
        type_="check",
    )
    op.add_column(
        "image_review_queue_states",
        sa.Column(
            "superseded_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.alter_column(
        "image_review_queue_states",
        "superseded_count",
        server_default=None,
    )
    op.create_check_constraint(
        "ck_image_review_queue_states_nonnegative",
        "image_review_queue_states",
        "queue_version > 0 AND total_count >= 0 "
        "AND pending_count >= 0 AND accepted_count >= 0 "
        "AND corrected_count >= 0 AND rejected_count >= 0 "
        "AND superseded_count >= 0",
    )
    op.create_check_constraint(
        "ck_image_review_queue_states_total",
        "image_review_queue_states",
        "total_count = pending_count + accepted_count + corrected_count "
        "+ rejected_count + superseded_count",
    )
    _replace_queue_functions(include_superseded=True)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM image_review_items WHERE status = 'superseded'
                ) OR EXISTS (
                    SELECT 1 FROM image_review_resolution_events
                    WHERE action = 'superseded'
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade first-save-wins while superseded audit rows exist'
                        USING ERRCODE = '23514';
                END IF;
            END
            $$
            """
        )
    )
    _replace_queue_functions(include_superseded=False)

    op.drop_constraint(
        "ck_image_review_queue_states_nonnegative",
        "image_review_queue_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_image_review_queue_states_total",
        "image_review_queue_states",
        type_="check",
    )
    op.drop_column("image_review_queue_states", "superseded_count")
    op.create_check_constraint(
        "ck_image_review_queue_states_nonnegative",
        "image_review_queue_states",
        "queue_version > 0 AND total_count >= 0 "
        "AND pending_count >= 0 AND accepted_count >= 0 "
        "AND corrected_count >= 0 AND rejected_count >= 0",
    )
    op.create_check_constraint(
        "ck_image_review_queue_states_total",
        "image_review_queue_states",
        "total_count = pending_count + accepted_count + corrected_count + rejected_count",
    )

    op.drop_constraint(
        "ck_image_review_resolution_events_action",
        "image_review_resolution_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_resolution_events_action",
        "image_review_resolution_events",
        "action IN ('accepted', 'corrected', 'rejected', 'reopened')",
    )
    op.drop_constraint(
        "ck_image_review_queue_items_status",
        "image_review_queue_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_review_queue_items_status",
        "image_review_queue_items",
        "status IN ('pending', 'accepted', 'corrected', 'rejected')",
    )
    op.drop_constraint("ck_image_review_items_status", "image_review_items", type_="check")
    op.create_check_constraint(
        "ck_image_review_items_status",
        "image_review_items",
        "status IN ('pending', 'accepted', 'corrected', 'rejected')",
    )


def _replace_queue_functions(*, include_superseded: bool) -> None:
    superseded_column = ", superseded_count" if include_superseded else ""
    superseded_value = (
        ", CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END" if include_superseded else ""
    )
    superseded_insert_update = (
        ", superseded_count = image_review_queue_states.superseded_count "
        "+ CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END"
        if include_superseded
        else ""
    )
    superseded_status_update = (
        ", superseded_count = superseded_count "
        "- CASE WHEN OLD.status = 'superseded' THEN 1 ELSE 0 END "
        "+ CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END"
        if include_superseded
        else ""
    )
    superseded_delete_update = (
        ", superseded_count = superseded_count "
        "- CASE WHEN projected_status = 'superseded' THEN 1 ELSE 0 END"
        if include_superseded
        else ""
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION project_image_review_queue_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                projected_job_id uuid;
                projected_source_order bigint;
                projected_position smallint;
            BEGIN
                SELECT source.import_job_id, association.order_index, board.position_index
                INTO projected_job_id, projected_source_order, projected_position
                FROM recognized_boards AS board
                JOIN source_images AS source ON source.id = board.source_image_id
                JOIN image_import_job_files AS association
                  ON association.job_id = source.import_job_id
                 AND association.file_execution_key = source.file_execution_key
                WHERE board.id = NEW.recognized_board_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot project image review item %: source-order association is missing',
                        NEW.id USING ERRCODE = '23514';
                END IF;

                INSERT INTO image_review_queue_items (
                    review_item_id, import_job_id, source_order_index,
                    position_index, status, created_at
                ) VALUES (
                    NEW.id, projected_job_id, projected_source_order,
                    projected_position, NEW.status, NEW.created_at
                );

                INSERT INTO image_review_queue_states (
                    import_job_id, queue_version, total_count, pending_count,
                    accepted_count, corrected_count, rejected_count{superseded_column},
                    created_at, updated_at
                ) VALUES (
                    projected_job_id, 1, 1,
                    CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                    CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END
                    {superseded_value}, NEW.created_at, now()
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
                        + CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END
                    {superseded_insert_update},
                    updated_at = now();
                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION project_image_review_queue_status()
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
                        NEW.id USING ERRCODE = '23514';
                END IF;
                UPDATE image_review_queue_states
                SET pending_count = pending_count
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
                        + CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END
                    {superseded_status_update},
                    updated_at = now()
                WHERE import_job_id = projected_job_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot update image review queue state for job %: projection is missing',
                        projected_job_id USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION project_image_review_queue_delete()
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
                        OLD.id USING ERRCODE = '23514';
                END IF;
                UPDATE image_review_queue_states
                SET queue_version = queue_version + 1,
                    total_count = total_count - 1,
                    pending_count = pending_count
                        - CASE WHEN projected_status = 'pending' THEN 1 ELSE 0 END,
                    accepted_count = accepted_count
                        - CASE WHEN projected_status = 'accepted' THEN 1 ELSE 0 END,
                    corrected_count = corrected_count
                        - CASE WHEN projected_status = 'corrected' THEN 1 ELSE 0 END,
                    rejected_count = rejected_count
                        - CASE WHEN projected_status = 'rejected' THEN 1 ELSE 0 END
                    {superseded_delete_update},
                    updated_at = now()
                WHERE import_job_id = projected_job_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot update image review queue state for job %: projection is missing',
                        projected_job_id USING ERRCODE = '23514';
                END IF;
                DELETE FROM image_review_queue_states
                WHERE import_job_id = projected_job_id AND total_count = 0;
                RETURN OLD;
            END
            $$
            """
        )
    )
