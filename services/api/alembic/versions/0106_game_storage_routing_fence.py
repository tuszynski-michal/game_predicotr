"""Install transaction-scoped v2 ownership guards and schema-aware triggers."""

from collections.abc import Sequence

from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES

revision: str = "0106_game_storage_routing_fence"
down_revision: str | Sequence[str] | None = "0105_partitioned_game_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        """
        CREATE FUNCTION game_data_v2.current_game_id_v1()
        RETURNS uuid
        LANGUAGE plpgsql
        STABLE
        SET search_path = pg_catalog
        AS $$
        DECLARE raw_game_id text;
        BEGIN
            raw_game_id := current_setting('game_predictor.game_id', true);
            IF raw_game_id IS NULL OR btrim(raw_game_id) = '' THEN
                RAISE EXCEPTION 'GAME_STORAGE_SCOPE_REQUIRED' USING ERRCODE = '42501';
            END IF;
            RETURN raw_game_id::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'GAME_STORAGE_SCOPE_INVALID' USING ERRCODE = '42501';
        END
        $$
        """
    )
    for table in GAME_TABLES:
        op.execute(
            f"ALTER TABLE game_data_v2.{table} ALTER COLUMN game_id "
            "SET DEFAULT game_data_v2.current_game_id_v1()"
        )
        op.execute(f"ALTER TABLE game_data_v2.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE game_data_v2.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY game_scope_v1 ON game_data_v2.{table} "
            "USING (game_id = game_data_v2.current_game_id_v1()) "
            "WITH CHECK (game_id = game_data_v2.current_game_id_v1())"
        )
    _create_review_triggers()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    _drop_review_triggers()
    for table in reversed(GAME_TABLES):
        op.execute(f"DROP POLICY game_scope_v1 ON game_data_v2.{table}")
        op.execute(f"ALTER TABLE game_data_v2.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE game_data_v2.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE game_data_v2.{table} ALTER COLUMN game_id DROP DEFAULT")
    op.execute("DROP FUNCTION game_data_v2.current_game_id_v1()")


def _create_review_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION game_data_v2.populate_image_review_item_sequence_scope_v1()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public, game_data_v2
        AS $$
        DECLARE projected_game_id uuid; projected_job_id uuid; projected_sequence bigint;
        BEGIN
            SELECT board.game_id, job.id, board.sequence_number
            INTO projected_game_id, projected_job_id, projected_sequence
            FROM game_data_v2.recognized_boards AS board
            JOIN game_data_v2.source_images AS source
              ON source.game_id = board.game_id AND source.id = board.source_image_id
            JOIN public.jobs AS job
              ON job.game_id = source.game_id AND job.id = source.import_job_id
            WHERE board.game_id = NEW.game_id AND board.id = NEW.recognized_board_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Cannot scope image review item %: board or import is missing',
                    NEW.id USING ERRCODE = '23514';
            END IF;
            NEW.game_id := projected_game_id;
            NEW.import_job_id := projected_job_id;
            NEW.sequence_number := projected_sequence;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.project_image_review_queue_insert_v1()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public, game_data_v2
        AS $$
        DECLARE projected_source_order bigint; projected_position smallint;
        BEGIN
            SELECT association.order_index, board.position_index
            INTO projected_source_order, projected_position
            FROM game_data_v2.recognized_boards AS board
            JOIN game_data_v2.source_images AS source
              ON source.game_id = board.game_id AND source.id = board.source_image_id
            JOIN game_data_v2.image_import_job_files AS association
              ON association.game_id = source.game_id
             AND association.job_id = source.import_job_id
             AND association.file_execution_key = source.file_execution_key
            WHERE board.game_id = NEW.game_id AND board.id = NEW.recognized_board_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'Cannot project image review item %: source-order association is missing',
                    NEW.id USING ERRCODE = '23514';
            END IF;
            INSERT INTO game_data_v2.image_review_queue_items (
                game_id, review_item_id, import_job_id, source_order_index,
                position_index, status, created_at
            ) VALUES (
                NEW.game_id, NEW.id, NEW.import_job_id, projected_source_order,
                projected_position, NEW.status, NEW.created_at
            );
            INSERT INTO game_data_v2.image_review_queue_states (
                game_id, import_job_id, queue_version, total_count, pending_count,
                accepted_count, corrected_count, rejected_count, superseded_count,
                created_at, updated_at
            ) VALUES (
                NEW.game_id, NEW.import_job_id, 1, 1,
                CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END,
                CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END,
                NEW.created_at, now()
            ) ON CONFLICT (game_id, import_job_id) DO UPDATE SET
                queue_version = game_data_v2.image_review_queue_states.queue_version + 1,
                total_count = game_data_v2.image_review_queue_states.total_count + 1,
                pending_count = game_data_v2.image_review_queue_states.pending_count
                    + CASE WHEN NEW.status = 'pending' THEN 1 ELSE 0 END,
                accepted_count = game_data_v2.image_review_queue_states.accepted_count
                    + CASE WHEN NEW.status = 'accepted' THEN 1 ELSE 0 END,
                corrected_count = game_data_v2.image_review_queue_states.corrected_count
                    + CASE WHEN NEW.status = 'corrected' THEN 1 ELSE 0 END,
                rejected_count = game_data_v2.image_review_queue_states.rejected_count
                    + CASE WHEN NEW.status = 'rejected' THEN 1 ELSE 0 END,
                superseded_count = game_data_v2.image_review_queue_states.superseded_count
                    + CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END,
                updated_at = now();
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.project_image_review_queue_status_v1()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public, game_data_v2
        AS $$
        BEGIN
            IF NEW.status = OLD.status THEN RETURN NEW; END IF;
            UPDATE game_data_v2.image_review_queue_items SET status = NEW.status
            WHERE game_id = NEW.game_id AND review_item_id = NEW.id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Cannot update image review queue item %: projection is missing',
                    NEW.id USING ERRCODE = '23514';
            END IF;
            UPDATE game_data_v2.image_review_queue_states SET
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
                superseded_count = superseded_count
                    - CASE WHEN OLD.status = 'superseded' THEN 1 ELSE 0 END
                    + CASE WHEN NEW.status = 'superseded' THEN 1 ELSE 0 END,
                updated_at = now()
            WHERE game_id = NEW.game_id AND import_job_id = NEW.import_job_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'Cannot update image review queue state for job %: projection is missing',
                    NEW.import_job_id USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.project_image_review_queue_delete_v1()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public, game_data_v2
        AS $$
        DECLARE projected_status varchar(20);
        BEGIN
            DELETE FROM game_data_v2.image_review_queue_items
            WHERE game_id = OLD.game_id AND review_item_id = OLD.id
            RETURNING status INTO projected_status;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Cannot delete image review queue item %: projection is missing',
                    OLD.id USING ERRCODE = '23514';
            END IF;
            UPDATE game_data_v2.image_review_queue_states SET
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
                superseded_count = superseded_count
                    - CASE WHEN projected_status = 'superseded' THEN 1 ELSE 0 END,
                updated_at = now()
            WHERE game_id = OLD.game_id AND import_job_id = OLD.import_job_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'Cannot delete image review queue state for job %: projection is missing',
                    OLD.import_job_id USING ERRCODE = '23514';
            END IF;
            DELETE FROM game_data_v2.image_review_queue_states
            WHERE game_id = OLD.game_id AND import_job_id = OLD.import_job_id
              AND total_count = 0;
            RETURN OLD;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.guard_image_review_queue_topology_v1()
        RETURNS trigger LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.game_id IS DISTINCT FROM OLD.game_id
               OR NEW.review_item_id IS DISTINCT FROM OLD.review_item_id
               OR NEW.import_job_id IS DISTINCT FROM OLD.import_job_id
               OR NEW.source_order_index IS DISTINCT FROM OLD.source_order_index
               OR NEW.position_index IS DISTINCT FROM OLD.position_index THEN
                RAISE EXCEPTION 'Image review queue topology is immutable for item %',
                    OLD.review_item_id USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.synchronize_image_review_job_status_v1()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NEW.total_count > 0 AND NEW.pending_count = 0 THEN
                UPDATE public.jobs SET status = 'completed',
                    updated_at = GREATEST(jobs.updated_at, NEW.updated_at),
                    finished_at = COALESCE(jobs.finished_at, NEW.updated_at),
                    error_code = NULL, error_message = NULL
                WHERE game_id = NEW.game_id AND id = NEW.import_job_id
                  AND job_type = 'import' AND status = 'waiting_for_review';
            ELSIF NEW.pending_count > 0 THEN
                UPDATE public.jobs SET status = 'waiting_for_review',
                    updated_at = GREATEST(jobs.updated_at, NEW.updated_at),
                    finished_at = NULL, error_code = NULL, error_message = NULL
                WHERE game_id = NEW.game_id AND id = NEW.import_job_id
                  AND job_type = 'import' AND status = 'completed';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION game_data_v2.synchronize_image_review_item_sequence_number_v1()
        RETURNS trigger LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.sequence_number IS DISTINCT FROM OLD.sequence_number THEN
                UPDATE game_data_v2.image_review_items
                SET sequence_number = NEW.sequence_number
                WHERE game_id = NEW.game_id AND recognized_board_id = NEW.id;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    trigger_sql = (
        "CREATE TRIGGER trg_v2_image_review_item_sequence_scope BEFORE INSERT OR UPDATE OF "
        "recognized_board_id ON game_data_v2.image_review_items FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.populate_image_review_item_sequence_scope_v1()",
        "CREATE TRIGGER trg_v2_image_review_queue_insert AFTER INSERT ON "
        "game_data_v2.image_review_items FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.project_image_review_queue_insert_v1()",
        "CREATE TRIGGER trg_v2_image_review_queue_status AFTER UPDATE OF status ON "
        "game_data_v2.image_review_items FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM "
        "NEW.status) EXECUTE FUNCTION game_data_v2.project_image_review_queue_status_v1()",
        "CREATE TRIGGER trg_v2_image_review_queue_delete BEFORE DELETE ON "
        "game_data_v2.image_review_items FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.project_image_review_queue_delete_v1()",
        "CREATE TRIGGER trg_v2_image_review_queue_topology_guard BEFORE UPDATE OF "
        "game_id, review_item_id, import_job_id, source_order_index, position_index ON "
        "game_data_v2.image_review_queue_items FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.guard_image_review_queue_topology_v1()",
        "CREATE TRIGGER trg_v2_image_review_job_status AFTER INSERT OR UPDATE OF "
        "total_count, pending_count ON game_data_v2.image_review_queue_states FOR EACH ROW "
        "EXECUTE FUNCTION game_data_v2.synchronize_image_review_job_status_v1()",
        "CREATE TRIGGER trg_v2_image_review_item_sequence_number AFTER UPDATE OF "
        "sequence_number ON game_data_v2.recognized_boards FOR EACH ROW EXECUTE FUNCTION "
        "game_data_v2.synchronize_image_review_item_sequence_number_v1()",
    )
    for statement in trigger_sql:
        op.execute(statement)


def _drop_review_triggers() -> None:
    for table, trigger in (
        ("recognized_boards", "trg_v2_image_review_item_sequence_number"),
        ("image_review_queue_states", "trg_v2_image_review_job_status"),
        ("image_review_queue_items", "trg_v2_image_review_queue_topology_guard"),
        ("image_review_items", "trg_v2_image_review_queue_delete"),
        ("image_review_items", "trg_v2_image_review_queue_status"),
        ("image_review_items", "trg_v2_image_review_queue_insert"),
        ("image_review_items", "trg_v2_image_review_item_sequence_scope"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON game_data_v2.{table}")
    for function in (
        "synchronize_image_review_item_sequence_number_v1",
        "synchronize_image_review_job_status_v1",
        "guard_image_review_queue_topology_v1",
        "project_image_review_queue_delete_v1",
        "project_image_review_queue_status_v1",
        "project_image_review_queue_insert_v1",
        "populate_image_review_item_sequence_scope_v1",
    ):
        op.execute(f"DROP FUNCTION game_data_v2.{function}()")
