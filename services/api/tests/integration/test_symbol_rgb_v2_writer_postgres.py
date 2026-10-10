"""RGB v2 prediction writes on PostgreSQL (TASK-0871, D-520).

Runs only with ``GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`` against its own
``*_test`` database (the fixture of ``test_image_batch_store``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from alembic import command
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewPredictionSource,
)
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewWriteThroughCoordinator,
    extended_symbol_cell_review_filter_clauses,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from game_predictor_worker.symbols import rgb_v2
from game_predictor_worker.symbols.reference_library_writer import (
    BoardPlan,
    RgbTarget,
    TargetCell,
    apply_board,
    predictions_digest,
    revert_board,
    rgb_v2_policy,
)
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from test_image_batch_store import (  # type: ignore[import-not-found]
    PIPELINE,
    _add_review_projection_source,
    _image_job,
    _migration_config,
    isolated_image_batch_database,
)

__all__ = ["isolated_image_batch_database"]
RUN = "e" * 64


def _cells(session: Session, review_item_id: UUID) -> list[ImageSymbolReviewCellModel]:
    return list(
        session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        )
    )


def _source_ids(
    session: Session, game_id: UUID, review_item_id: UUID, source: SymbolCellReviewPredictionSource
) -> set[int]:
    review_filter = SymbolCellReviewListFilter(
        game_id=game_id,
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=True,
        prediction_source=source,
    )
    cell = ImageSymbolReviewCellModel
    return set(
        session.scalars(
            select(cell.cell_index).where(
                cell.review_item_id == review_item_id,
                *extended_symbol_cell_review_filter_clauses(review_filter),
            )
        )
    )


def test_rgb_v2_write_filter_and_revert_on_one_board(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    try:
        with session_factory() as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="rgb-v2-writer", name="RGB v2 writer", status=GameStatus.ACTIVE
            )
            symbols = {
                code: catalog.create_symbol(
                    game.id,
                    mobile_code=index + 1,
                    code=code,
                    name=code,
                    image_path=None,
                    is_wildcard=False,
                    display_order=index,
                    status=SymbolStatus.ACTIVE,
                )
                for index, code in enumerate(("test", "other"))
            }
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()
        execution = SqlAlchemyImageBatchStore(session_factory).register_file(
            job.id,
            source_checksum_sha256="7" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="rgb.jpg",
            order_index=0,
            registered_at=now,
        )
        with game_storage_scope(game.id), session_factory() as session:
            review_item_id, board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum="7" * 64,
                source_name="rgb.jpg",
                position_index=0,
                sequence_number=1,
                status="pending",
                created_at=now,
            )
            job_record = session.get(JobModel, job.id)
            assert job_record is not None

            job_record.status = JobStatus.WAITING_FOR_REVIEW
            SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game.id)
            session.commit()
        with game_storage_scope(game.id), session_factory() as session:
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            backfill.start_or_resume_backfill(game.id)
            while backfill.backfill_next_batch(game.id, batch_size=10).has_more:
                pass
            session.commit()

        # A model revision with positioned entries, as the inference writes it.
        with game_storage_scope(game.id), session_factory() as session:
            model_revision = ImageSymbolPredictionRevisionModel(
                game_id=game.id,
                review_item_id=review_item_id,
                recognized_board_id=board_id,
                source_job_id=job.id,
                model_iteration_id=None,
                model_version="rgb-test-model-v1",
                model_checksum_sha256="a" * 64,
                crop_manifest_checksum_sha256="b" * 64,
                predictions=[
                    {
                        "rowIndex": index // 5,
                        "columnIndex": index % 5,
                        "symbolCode": "test",
                        "confidence": 0.55,
                        "alternatives": [{"symbolCode": "test", "confidence": 0.55}],
                    }
                    for index in range(15)
                ],
            )
            session.add(model_revision)
            session.flush()
            assert SymbolCellReviewWriteThroughCoordinator(
                session
            ).synchronize_after_prediction_refresh(
                game_id=game.id, review_item_id=review_item_id, actor="system:test-inference"
            )
            session.commit()
            model_revision_id = model_revision.id
            digest = predictions_digest(model_revision.predictions)

        with game_storage_scope(game.id), session_factory() as session:
            cells = _cells(session, review_item_id)
            assert all(cell.review_state == "pending" for cell in cells)
            assert all(cell.assignment_source == "model" for cell in cells)
            assert all(cell.prediction_revision_id == model_revision_id for cell in cells)
            by_index = {cell.cell_index: cell for cell in cells}

        def target(index: int, new: str, status: rgb_v2.Status, old_conf: float) -> TargetCell:
            cell = by_index[index]
            return TargetCell(
                cell.id,
                index,
                str(cell.rendered_pixel_checksum_sha256),
                "test",
                new,
                7 if status == "confirmed" else 2,
                7 if status == "confirmed" else 3,
                RgbTarget(
                    status=status,
                    cnn_symbol=new,
                    library_symbol=new if status == "confirmed" else None,
                    old_confidence=old_conf,
                    old_source="model",
                    original_model_confidence=0.55,
                ),
            )

        policy = rgb_v2_policy({"checkpointSha256": "c" * 64, "runChecksumSha256": RUN})
        plan = BoardPlan(
            review_item_id,
            board_id,
            model_revision_id,
            digest,
            (target(3, "other", "tentative", 0.55), target(4, "test", "confirmed", 0.55)),
        )
        guarded = BoardPlan(
            review_item_id,
            board_id,
            model_revision_id,
            digest,
            (target(3, "other", "tentative", 0.75),),
        )

        # A changed confidence since the preview makes the board stale; nothing is written.
        with game_storage_scope(game.id), session_factory() as session, session.begin():
            assert (
                apply_board(
                    session,
                    game_id=game.id,
                    plan=guarded,
                    library_checksum_sha256=RUN,
                    policy=policy,
                )
                == "stale:cell_changed"
            )

        with game_storage_scope(game.id), session_factory() as session, session.begin():
            assert (
                apply_board(
                    session, game_id=game.id, plan=plan, library_checksum_sha256=RUN, policy=policy
                )
                == "applied"
            )
        with game_storage_scope(game.id), session_factory() as session, session.begin():
            assert (
                apply_board(
                    session, game_id=game.id, plan=plan, library_checksum_sha256=RUN, policy=policy
                )
                == "already_applied"
            )

        with game_storage_scope(game.id), session_factory() as session:
            cells = {cell.cell_index: cell for cell in _cells(session, review_item_id)}
            revision = session.get(
                ImageSymbolPredictionRevisionModel, cells[3].prediction_revision_id
            )
            assert revision is not None and revision.model_version == rgb_v2.MODEL_VERSION
            assert (cells[3].prediction_symbol_code, cells[3].prediction_confidence) == (
                "other",
                rgb_v2.TENTATIVE_CONFIDENCE,
            )
            assert cells[3].assigned_symbol_id == symbols["other"].id
            assert (cells[4].prediction_symbol_code, cells[4].prediction_confidence) == (
                "test",
                rgb_v2.CONFIRMED_CONFIDENCE,
            )
            assert all(cell.review_state == "pending" for cell in cells.values())
            assert all(
                (cell.prediction_symbol_code, cell.prediction_confidence) == ("test", 0.55)
                for index, cell in cells.items()
                if index not in (3, 4)
            )
            entry = next(
                e for e in revision.predictions if (e["rowIndex"], e["columnIndex"]) == (0, 3)
            )
            assert entry["rgbV2"]["status"] == "tentative"
            assert entry["rgbV2"]["runChecksumSha256"] == RUN
            assert _source_ids(
                session, game.id, review_item_id, SymbolCellReviewPredictionSource.RGB_V2
            ) == {3, 4}
            assert _source_ids(
                session,
                game.id,
                review_item_id,
                SymbolCellReviewPredictionSource.RGB_V2_TENTATIVE,
            ) == {3}
            assert _source_ids(
                session, game.id, review_item_id, SymbolCellReviewPredictionSource.MODEL
            ) == set(range(15)) - {3, 4}
            assert not _source_ids(
                session,
                game.id,
                review_item_id,
                SymbolCellReviewPredictionSource.REFERENCE_LIBRARY,
            )

        with game_storage_scope(game.id), session_factory() as session, session.begin():
            assert (
                revert_board(
                    session, game_id=game.id, plan=plan, library_checksum_sha256=RUN, policy=policy
                )
                == "reverted"
            )
        with game_storage_scope(game.id), session_factory() as session:
            cells = _cells(session, review_item_id)
            assert all(
                (cell.prediction_symbol_code, cell.prediction_confidence) == ("test", 0.55)
                for cell in cells
            )
            assert not _source_ids(
                session, game.id, review_item_id, SymbolCellReviewPredictionSource.RGB_V2
            )
    finally:
        engine.dispose()
