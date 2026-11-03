"""Selection respects persisted reservation ownership and permanent source retirement."""

from datetime import UTC, datetime
from uuid import uuid4

from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import ImageSequenceCanonicalModel, RecognizedBoardModel
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import text
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_source_replacement_postgres import database, pytestmark  # noqa: F401


def test_selection_reservation_precedence_binding_restart_and_restored_history(database):  # noqa: F811
    factory = create_session_factory(database)
    now = datetime.now(UTC)
    batch, entry = uuid4(), uuid4()
    with game_storage_scope(GAME_ID), factory() as session:
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
        session.commit()
        fixtures = (("e", "accepted"), ("f", "corrected"), ("9", "pending"))
        executions = [
            SqlAlchemyImageBatchStore(factory).register_file(
                job.id,
                source_checksum_sha256=sha * 64,
                pipeline_fingerprint=PIPELINE,
                source_relative_path=f"selection-{index}.jpg",
                order_index=index,
                registered_at=now,
            )
            for index, (sha, _status) in enumerate(fixtures)
        ]
        sources, reviews, boards = [], [], []
        for index, (sha, status) in enumerate(fixtures):
            execution = executions[index]
            review, board = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum=sha * 64,
                source_name=f"selection-{index}.jpg",
                position_index=0,
                sequence_number=707,
                status=status,
                created_at=now,
            )
            sources.append(session.get(RecognizedBoardModel, board).source_image_id)
            reviews.append(review)
            boards.append(board)
        canonical = ImageSequenceCanonicalModel(
            game_id=GAME_ID,
            sequence_number=707,
            review_item_id=reviews[0],
            recognized_board_id=boards[0],
            import_job_id=job.id,
            source_image_id=sources[0],
            source_checksum_sha256="e" * 64,
            board_checksum_sha256="e" * 64,
            status="accepted",
            resolution_revision=1,
            geometry_revision=1,
        )
        session.add(canonical)
        session.flush()
        repository = SqlAlchemyOperationalImageReviewRepository(session)
        ordinary = repository.sequence_source_selection(GAME_ID, 707)
        assert ordinary.state == "available"
        assert len(ordinary.candidates) == 2
        assert all(item.selectable for item in ordinary.candidates)
        assert (
            next(item for item in ordinary.candidates if item.selected).review_item_id == reviews[0]
        )
        params = dict(
            game=GAME_ID,
            batch=batch,
            entry=entry,
            old=sources[0],
            new=sources[2],
            review=reviews[2],
        )
        session.execute(
            text("""INSERT INTO source_replacement_batches
          (game_id,id,revision,status,preview_token,document)
          VALUES(:game,:batch,1,'gap_open',repeat('a',64),'{}')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_entries
          (game_id,id,batch_id,source_id,source_sha256,phase,document)
          VALUES(:game,:entry,:batch,:old,repeat('e',64),'gap_open','{}')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_slots
          (game_id,sequence_number,entry_id,batch_id,state,new_source_id,new_sha256,revision,document)
          VALUES(:game,707,:entry,:batch,'reserved',:new,repeat('9',64),1,'{}')"""),
            params,
        )
        gap = repository.sequence_source_selection(GAME_ID, 707)
        assert gap.state == "reserved_gap"
        assert gap.replacement_batch_id == batch and gap.replacement_entry_id == entry
        assert all(not item.selected and not item.selectable for item in gap.candidates)
        assert reviews[2] not in [item.review_item_id for item in gap.candidates]
        session.execute(
            text("""INSERT INTO source_replacement_retired
          (game_id,source_id,entry_id,source_sha256,document)
          VALUES(:game,:old,:entry,repeat('e',64),'{}')"""),
            params,
        )
        session.execute(
            text("""UPDATE source_replacement_slots
          SET state='pending_bound',bound_review_id=:review
          WHERE game_id=:game AND sequence_number=707"""),
            params,
        )
        session.commit()

    with game_storage_scope(GAME_ID), factory() as session:
        repository = SqlAlchemyOperationalImageReviewRepository(session)
        bound = repository.sequence_source_selection(GAME_ID, 707)
        assert bound.state == "pending_bound"
        assert next(item for item in bound.candidates if item.selected).review_item_id == reviews[2]
        assert all(not item.selectable for item in bound.candidates)
        assert (
            next(
                item for item in bound.candidates if item.review_item_id == reviews[0]
            ).source_state
            == "retired"
        )
        # Restoration removes the active slot, never the historical retirement.
        session.execute(
            text("UPDATE source_replacement_entries SET phase='restored' WHERE id=:entry"), params
        )
        session.execute(
            text(
                "DELETE FROM source_replacement_slots WHERE game_id=:game AND sequence_number=707"
            ),
            params,
        )
        session.execute(
            text(
                "UPDATE image_review_items SET status='accepted', resolved_value='{}', "
                "resolved_by='fixture', resolution_revision=1, resolved_at=now() WHERE id=:review"
            ),
            params,
        )
        session.execute(
            text("""UPDATE image_sequence_canonical SET review_item_id=:review,
          recognized_board_id=:board,source_image_id=:new,source_checksum_sha256=repeat('9',64)
          WHERE game_id=:game AND sequence_number=707"""),
            {**params, "board": boards[2]},
        )
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        restored = SqlAlchemyOperationalImageReviewRepository(session).sequence_source_selection(
            GAME_ID, 707
        )
        assert restored.state == "available"
        old = next(item for item in restored.candidates if item.review_item_id == reviews[0])
        assert (old.source_state, old.selectable, old.selected) == ("replaced", False, False)
        new = next(item for item in restored.candidates if item.selected)
        assert new.review_item_id == reviews[2] and new.selectable
