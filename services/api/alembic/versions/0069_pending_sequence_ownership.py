"""Enforce one unresolved review owner per game sequence.

Revision ID: 0069_pending_sequence_ownership
Revises: 0068_image_symbol_review_bulk_operations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069_pending_sequence_ownership"
down_revision: str | Sequence[str] | None = "0068_image_symbol_review_bulk_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _progress("adding denormalized sequence scope")
    op.add_column("image_review_items", sa.Column("game_id", sa.Uuid(), nullable=True))
    op.add_column("image_review_items", sa.Column("import_job_id", sa.Uuid(), nullable=True))
    op.add_column(
        "image_review_items",
        sa.Column("sequence_number", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_image_review_items_game",
        "image_review_items",
        "games",
        ["game_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_image_review_items_import_job",
        "image_review_items",
        "jobs",
        ["import_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE image_review_items
            DISABLE TRIGGER trg_image_review_queue_status
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE image_review_items AS item
            SET game_id = job.game_id,
                import_job_id = job.id,
                sequence_number = board.sequence_number
            FROM recognized_boards AS board
            JOIN source_images AS source ON source.id = board.source_image_id
            JOIN jobs AS job ON job.id = source.import_job_id
            WHERE item.recognized_board_id = board.id
            """
        )
    )
    _progress("backfilled review-item sequence scope")
    op.alter_column("image_review_items", "game_id", nullable=False)
    op.alter_column("image_review_items", "import_job_id", nullable=False)
    op.execute(
        sa.text(
            """
            CREATE FUNCTION populate_image_review_item_sequence_scope()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                SELECT job.game_id, job.id, board.sequence_number
                INTO NEW.game_id, NEW.import_job_id, NEW.sequence_number
                FROM recognized_boards AS board
                JOIN source_images AS source ON source.id = board.source_image_id
                JOIN jobs AS job ON job.id = source.import_job_id
                WHERE board.id = NEW.recognized_board_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'Cannot scope image review item %: board or import is missing',
                        NEW.id USING ERRCODE = '23514';
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
            CREATE TRIGGER trg_image_review_item_sequence_scope
            BEFORE INSERT OR UPDATE OF recognized_board_id
            ON image_review_items
            FOR EACH ROW
            EXECUTE FUNCTION populate_image_review_item_sequence_scope()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION synchronize_image_review_item_sequence_number()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.sequence_number IS DISTINCT FROM OLD.sequence_number THEN
                    UPDATE image_review_items
                    SET sequence_number = NEW.sequence_number
                    WHERE recognized_board_id = NEW.id;
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
            CREATE TRIGGER trg_image_review_item_sequence_number
            AFTER UPDATE OF sequence_number
            ON recognized_boards
            FOR EACH ROW
            EXECUTE FUNCTION synchronize_image_review_item_sequence_number()
            """
        )
    )

    # Canonical accepted/corrected decisions always win. Otherwise the newest
    # import job owns the pending sequence; UUID is a deterministic tie-break.
    op.execute(
        sa.text(
            """
            CREATE TEMPORARY TABLE pending_sequence_repair_targets
            ON COMMIT DROP AS
            WITH ranked AS (
                SELECT
                    item.id,
                    item.recognized_board_id,
                    item.game_id,
                    item.import_job_id,
                    item.sequence_number,
                    canonical.review_item_id AS canonical_review_item_id,
                    first_value(item.id) OVER (
                        PARTITION BY item.game_id, item.sequence_number
                        ORDER BY job.created_at DESC, job.id DESC, item.id ASC
                    ) AS newest_pending_review_item_id,
                    count(*) OVER (
                        PARTITION BY item.game_id, item.sequence_number
                    ) AS pending_count
                FROM image_review_items AS item
                JOIN jobs AS job ON job.id = item.import_job_id
                LEFT JOIN image_sequence_canonical AS canonical
                  ON canonical.game_id = item.game_id
                 AND canonical.sequence_number = item.sequence_number
                WHERE item.status = 'pending'
                  AND item.sequence_number IS NOT NULL
            )
            SELECT *,
                COALESCE(canonical_review_item_id, newest_pending_review_item_id)
                    AS owner_review_item_id,
                CASE
                    WHEN canonical_review_item_id IS NOT NULL
                        THEN 'canonical_sequence_already_resolved'
                    ELSE 'pending_sequence_replaced_by_newer_import'
                END AS repair_reason
            FROM ranked
            WHERE canonical_review_item_id IS NOT NULL
               OR (pending_count > 1 AND id <> newest_pending_review_item_id)
            """
        )
    )
    _progress("created pending-sequence repair snapshot")
    op.execute(
        sa.text(
            """
            DELETE FROM image_layout_staging_rows AS staging
            USING pending_sequence_repair_targets AS target
            WHERE staging.review_item_id = target.id
            """
        )
    )
    _progress("removed obsolete staging rows")
    op.execute(
        sa.text(
            """
            UPDATE recognized_boards AS board
            SET status = 'rejected'
            FROM pending_sequence_repair_targets AS target
            WHERE board.id = target.recognized_board_id
            """
        )
    )
    _progress("marked obsolete recognized boards")
    op.execute(
        sa.text(
            """
            UPDATE image_review_items AS item
            SET status = 'superseded',
                resolved_value = jsonb_build_object(
                    'action', 'superseded',
                    'ownerReviewItemId', target.owner_review_item_id::text,
                    'reason', target.repair_reason,
                    'sequenceNumber', target.sequence_number
                ),
                resolved_by = 'system:pending-sequence-repair',
                resolution_revision = item.resolution_revision + 1,
                resolved_at = now()
            FROM pending_sequence_repair_targets AS target
            WHERE item.id = target.id
            """
        )
    )
    _progress("superseded duplicate pending review items")
    op.execute(
        sa.text(
            """
            ALTER TABLE image_review_items
            ENABLE TRIGGER trg_image_review_queue_status
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE image_review_queue_items AS queue_item
            SET status = item.status
            FROM image_review_items AS item
            WHERE queue_item.review_item_id = item.id
              AND queue_item.status IS DISTINCT FROM item.status
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE image_review_queue_states AS state
            SET total_count = counts.total_count,
                pending_count = counts.pending_count,
                accepted_count = counts.accepted_count,
                corrected_count = counts.corrected_count,
                rejected_count = counts.rejected_count,
                superseded_count = counts.superseded_count,
                updated_at = now()
            FROM (
                SELECT
                    import_job_id,
                    count(*) AS total_count,
                    count(*) FILTER (WHERE status = 'pending') AS pending_count,
                    count(*) FILTER (WHERE status = 'accepted') AS accepted_count,
                    count(*) FILTER (WHERE status = 'corrected') AS corrected_count,
                    count(*) FILTER (WHERE status = 'rejected') AS rejected_count,
                    count(*) FILTER (WHERE status = 'superseded') AS superseded_count
                FROM image_review_queue_items
                GROUP BY import_job_id
            ) AS counts
            WHERE state.import_job_id = counts.import_job_id
            """
        )
    )
    _progress("reconciled operational review queues")
    op.execute(
        sa.text(
            """
            DELETE FROM image_board_search_candidates AS candidate
            USING pending_sequence_repair_targets AS target
            WHERE candidate.review_item_id = target.id
            """
        )
    )
    _progress("removed obsolete board-search candidates")
    _restore_pending_search_documents()
    _progress("reconciled board-search and symbol-review owners")
    op.create_index(
        "uq_image_review_items_pending_game_sequence",
        "image_review_items",
        ["game_id", "sequence_number"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND sequence_number IS NOT NULL"),
    )
    _progress("pending-sequence ownership migration completed")
    op.create_index(
        "ix_image_review_items_import_status",
        "image_review_items",
        ["import_job_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_review_items_import_status", table_name="image_review_items")
    op.drop_index(
        "uq_image_review_items_pending_game_sequence",
        table_name="image_review_items",
    )
    op.execute("DROP TRIGGER trg_image_review_item_sequence_number ON recognized_boards")
    op.execute("DROP FUNCTION synchronize_image_review_item_sequence_number()")
    op.execute("DROP TRIGGER trg_image_review_item_sequence_scope ON image_review_items")
    op.execute("DROP FUNCTION populate_image_review_item_sequence_scope()")
    op.drop_constraint("fk_image_review_items_import_job", "image_review_items", type_="foreignkey")
    op.drop_constraint("fk_image_review_items_game", "image_review_items", type_="foreignkey")
    op.drop_column("image_review_items", "sequence_number")
    op.drop_column("image_review_items", "import_job_id")
    op.drop_column("image_review_items", "game_id")


def _restore_pending_search_documents() -> None:
    selected_pending = """
        SELECT DISTINCT ON (candidate.game_id, candidate.sequence_number)
            candidate.*
        FROM image_board_search_candidates AS candidate
        JOIN jobs AS job ON job.id = candidate.import_job_id
        LEFT JOIN image_sequence_canonical AS canonical
          ON canonical.game_id = candidate.game_id
         AND canonical.sequence_number = candidate.sequence_number
        WHERE candidate.status = 'pending'
          AND canonical.review_item_id IS NULL
        ORDER BY
            candidate.game_id,
            candidate.sequence_number,
            job.created_at DESC,
            job.id DESC,
            candidate.review_item_id ASC
    """
    op.execute(
        sa.text(
            f"""
            INSERT INTO image_board_search_documents (
                game_id, sequence_number, review_item_id, selection_kind,
                recognized_board_id, import_job_id, status, board_checksum_sha256,
                primary_match_tokens, alternative_rank_1_match_tokens,
                alternative_rank_2_match_tokens, alternative_rank_3_match_tokens,
                alternative_rank_4_match_tokens, known_evidence_positions,
                primary_symbol_mobile_codes, alternative_rank_1_mobile_codes,
                alternative_rank_2_mobile_codes, alternative_rank_3_mobile_codes,
                alternative_rank_4_mobile_codes, created_at, updated_at
            )
            SELECT
                selected.game_id, selected.sequence_number, selected.review_item_id,
                'pending', selected.recognized_board_id, selected.import_job_id,
                selected.status, selected.board_checksum_sha256,
                selected.primary_match_tokens, selected.alternative_rank_1_match_tokens,
                selected.alternative_rank_2_match_tokens,
                selected.alternative_rank_3_match_tokens,
                selected.alternative_rank_4_match_tokens,
                selected.known_evidence_positions, selected.primary_symbol_mobile_codes,
                selected.alternative_rank_1_mobile_codes,
                selected.alternative_rank_2_mobile_codes,
                selected.alternative_rank_3_mobile_codes,
                selected.alternative_rank_4_mobile_codes, now(), now()
            FROM ({selected_pending}) AS selected
            ON CONFLICT (game_id, sequence_number) DO UPDATE SET
                review_item_id = EXCLUDED.review_item_id,
                selection_kind = EXCLUDED.selection_kind,
                recognized_board_id = EXCLUDED.recognized_board_id,
                import_job_id = EXCLUDED.import_job_id,
                status = EXCLUDED.status,
                board_checksum_sha256 = EXCLUDED.board_checksum_sha256,
                primary_match_tokens = EXCLUDED.primary_match_tokens,
                alternative_rank_1_match_tokens = EXCLUDED.alternative_rank_1_match_tokens,
                alternative_rank_2_match_tokens = EXCLUDED.alternative_rank_2_match_tokens,
                alternative_rank_3_match_tokens = EXCLUDED.alternative_rank_3_match_tokens,
                alternative_rank_4_match_tokens = EXCLUDED.alternative_rank_4_match_tokens,
                known_evidence_positions = EXCLUDED.known_evidence_positions,
                primary_symbol_mobile_codes = EXCLUDED.primary_symbol_mobile_codes,
                alternative_rank_1_mobile_codes = EXCLUDED.alternative_rank_1_mobile_codes,
                alternative_rank_2_mobile_codes = EXCLUDED.alternative_rank_2_mobile_codes,
                alternative_rank_3_mobile_codes = EXCLUDED.alternative_rank_3_mobile_codes,
                alternative_rank_4_mobile_codes = EXCLUDED.alternative_rank_4_mobile_codes,
                updated_at = now()
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO image_board_search_fast_documents (
                game_id, sequence_number, review_item_id, recognized_board_id,
                import_job_id, status, board_checksum_sha256, known_evidence_positions,
                primary_symbol_mobile_codes, alternative_rank_1_mobile_codes,
                alternative_rank_2_mobile_codes, alternative_rank_3_mobile_codes,
                alternative_rank_4_mobile_codes, created_at, updated_at
            )
            SELECT
                selected.game_id, selected.sequence_number, selected.review_item_id,
                selected.recognized_board_id, selected.import_job_id, selected.status,
                selected.board_checksum_sha256, selected.known_evidence_positions,
                selected.primary_symbol_mobile_codes,
                selected.alternative_rank_1_mobile_codes,
                selected.alternative_rank_2_mobile_codes,
                selected.alternative_rank_3_mobile_codes,
                selected.alternative_rank_4_mobile_codes, now(), now()
            FROM ({selected_pending}) AS selected
            ON CONFLICT (game_id, sequence_number) DO UPDATE SET
                review_item_id = EXCLUDED.review_item_id,
                recognized_board_id = EXCLUDED.recognized_board_id,
                import_job_id = EXCLUDED.import_job_id,
                status = EXCLUDED.status,
                board_checksum_sha256 = EXCLUDED.board_checksum_sha256,
                known_evidence_positions = EXCLUDED.known_evidence_positions,
                primary_symbol_mobile_codes = EXCLUDED.primary_symbol_mobile_codes,
                alternative_rank_1_mobile_codes = EXCLUDED.alternative_rank_1_mobile_codes,
                alternative_rank_2_mobile_codes = EXCLUDED.alternative_rank_2_mobile_codes,
                alternative_rank_3_mobile_codes = EXCLUDED.alternative_rank_3_mobile_codes,
                alternative_rank_4_mobile_codes = EXCLUDED.alternative_rank_4_mobile_codes,
                updated_at = now()
            """
        )
    )


def _progress(message: str) -> None:
    print(f"[0069] {message}", flush=True)
