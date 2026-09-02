from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryManualResolutionProjection,
)
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_grid_reviews import ImageGridReviewService
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkOperationStatus,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.unreadable_board_reviews import (
    SaveUnreadableBoardCellCommand,
    UnreadableBoardReviewService,
    UnreadableBoardReviewView,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingReason,
    BoardCellProcessingManifestV1,
)
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewState,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGridIssueView,
    ImageReviewResolutionCell,
    ImageReviewView,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellQualityIssue,
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_job_repository import (
    SqlAlchemyImageJobOperationsRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    SqlAlchemySymbolCellReviewBulkOperationRepository,
    SqlAlchemySymbolCellReviewBulkOperationWorker,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SqlAlchemySymbolCellReviewMutationRepository,
    SqlAlchemySymbolCellReviewQueryRepository,
    SqlAlchemyUnreadableBoardReviewRepository,
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageLayoutStagingRowModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageReviewQueueStateModel,
    ImageReviewResolutionEventModel,
    ImageSequenceAlternativeModel,
    ImageSequenceCanonicalModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewBulkOperationModel,
    ImageSymbolReviewBulkTargetModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.pending_sequence_ownership import (
    create_owned_pending_review_item,
)
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPrediction,
)
from game_predictor_worker.images.orchestration import (
    ImageStageExecutionResult,
    advance_file_checkpoint,
)
from game_predictor_worker.images.orchestration_store import (
    ImageOrchestrationStoreError,
    SqlAlchemyImageBatchStore,
)
from game_predictor_worker.images.pending_grid_reinference import (
    PendingGridReinferenceHandler,
)
from game_predictor_worker.images.pending_symbol_reinference import (
    PendingSymbolReinferenceHandler,
)
from game_predictor_worker.images.pipeline_store import (
    ImagePipelineStoreError,
    SqlAlchemyImagePipelineStore,
)
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import create_engine, delete, func, null, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_image_batch_test"
PIPELINE = "a" * 64
OTHER_PIPELINE = "b" * 64

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return (
        make_url(ApiSettings.from_environment().database_url)
        .set(database=database_name)
        .update_query_dict({"connect_timeout": "3"})
    )


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_image_batch_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _image_job(game_id: UUID, pipeline: str, created_at: datetime) -> Job:
    return create_job(
        JobType.IMPORT,
        game_id=game_id,
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "pipeline_fingerprint": pipeline,
            "test_source_batch": created_at.isoformat(),
        },
        created_at=created_at,
    )


def _add_review_projection_source(
    session: Session,
    *,
    job_id: UUID,
    file_execution_key: str,
    source_checksum: str,
    source_name: str,
    position_index: int,
    sequence_number: int,
    status: str,
    created_at: datetime,
) -> tuple[UUID, UUID]:
    source = SourceImageModel(
        import_job_id=job_id,
        file_execution_key=file_execution_key,
        relative_path=source_name,
        checksum_sha256=source_checksum,
        width=1920,
        height=1080,
        status="waiting_for_review",
        created_at=created_at,
    )
    session.add(source)
    session.flush()
    board = RecognizedBoardModel(
        source_image_id=source.id,
        position_index=position_index,
        sequence_number_raw=str(sequence_number),
        sequence_number=sequence_number,
        sequence_confidence=1.0,
        board_geometry={"source": "projection-test"},
        board_relative_path=f"crops/{source_name}.png",
        board_checksum_sha256=f"{sequence_number:064x}",
        cells_prediction={"cells": []},
        board_confidence=1.0,
        pipeline_fingerprint=PIPELINE,
        status="pending_review" if status == "pending" else status,
        created_at=created_at,
    )
    session.add(board)
    session.flush()
    resolved = status != "pending"
    review_values: dict[str, object] = {}
    if resolved:
        review_values = {
            "resolved_value": {"action": status, "rejectionReason": "test"},
            "resolved_by": "projection-test",
            "resolved_at": created_at,
        }
    review = ImageReviewItemModel(
        recognized_board_id=board.id,
        status=status,
        snapshot={"sequenceNumber": sequence_number},
        resolution_revision=1 if resolved else 0,
        created_at=created_at,
        **review_values,
    )
    session.add(review)
    session.flush()
    session.add_all(
        CellObservationModel(
            recognized_board_id=board.id,
            row_index=index // 5,
            column_index=index % 5,
            crop_relative_path=f"crops/{source_name}-{index}.png",
            crop_checksum_sha256=f"{sequence_number * 100 + index:064x}",
            cropper_version="projection-test-cropper",
            prediction={
                "symbolCode": "test",
                "confidence": 1.0,
                "alternatives": [{"symbolCode": "test", "confidence": 1.0}],
            },
            created_at=created_at,
        )
        for index in range(15)
    )
    return review.id, board.id


def _set_complete_resolution(
    session: Session,
    *,
    review_item_id: UUID,
    board_id: UUID,
    sequence_number: int,
    action: str,
    resolved_at: datetime,
) -> None:
    review = session.get(ImageReviewItemModel, review_item_id)
    board = session.get(RecognizedBoardModel, board_id)
    assert review is not None
    assert board is not None
    review.status = action
    review.resolved_value = {
        "action": action,
        "sequenceNumber": sequence_number,
        "symbolCodes": ["test"] * 15,
    }
    review.resolved_by = "symbol-cell-backfill-test"
    review.resolution_revision = 1
    review.resolved_at = resolved_at
    board.status = action


def test_symbol_cell_backfill_persists_current_base_and_corrected_geometry_crops(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="symbol-cell-backfill",
                name="Symbol cell backfill",
                status=GameStatus.ACTIVE,
            )
            symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="test",
                name="Test",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        base_execution = image_store.register_file(
            job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="base.jpg",
            order_index=0,
            registered_at=now,
        )
        corrected_execution = image_store.register_file(
            job.id,
            source_checksum_sha256="2" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="corrected.jpg",
            order_index=1,
            registered_at=now,
        )
        pending_execution = image_store.register_file(
            job.id,
            source_checksum_sha256="7" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="unknown.jpg",
            order_index=2,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            base_review_id, base_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=base_execution.file_execution_key,
                source_checksum="1" * 64,
                source_name="base.jpg",
                position_index=0,
                sequence_number=1,
                status="pending",
                created_at=now,
            )
            corrected_review_id, corrected_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=corrected_execution.file_execution_key,
                source_checksum="2" * 64,
                source_name="corrected.jpg",
                position_index=0,
                sequence_number=2,
                status="pending",
                created_at=now,
            )
            pending_review_id, _pending_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=pending_execution.file_execution_key,
                source_checksum="7" * 64,
                source_name="unknown.jpg",
                position_index=0,
                sequence_number=3,
                status="pending",
                created_at=now,
            )
            for observation in session.scalars(
                select(CellObservationModel)
                .where(CellObservationModel.recognized_board_id == _pending_board_id)
                .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
            ):
                observation.prediction = {
                    "symbolCode": "?",
                    "confidence": 1.0,
                    "alternatives": [{"symbolCode": "?", "confidence": 1.0}],
                }
            _set_complete_resolution(
                session,
                review_item_id=base_review_id,
                board_id=base_board_id,
                sequence_number=1,
                action="accepted",
                resolved_at=now,
            )
            _set_complete_resolution(
                session,
                review_item_id=corrected_review_id,
                board_id=corrected_board_id,
                sequence_number=2,
                action="corrected",
                resolved_at=now,
            )
            corrected_board = session.get(RecognizedBoardModel, corrected_board_id)
            assert corrected_board is not None
            corrected_board.geometry_revision = 1
            session.add(
                ImageBoardGeometryRevisionModel(
                    review_item_id=corrected_review_id,
                    recognized_board_id=corrected_board_id,
                    revision=1,
                    idempotency_key=uuid4(),
                    command_sha256="3" * 64,
                    corners=[
                        {"x": 0, "y": 0},
                        {"x": 100, "y": 0},
                        {"x": 100, "y": 100},
                        {"x": 0, "y": 100},
                    ],
                    geometry={"source": "manual"},
                    board_relative_path="boards/corrected.png",
                    board_checksum_sha256="4" * 64,
                    cropper_version="corrected-cropper-v1",
                    crop_artifacts=[
                        {
                            "rowIndex": index // 5,
                            "columnIndex": index % 5,
                            "cropRelativePath": f"corrected/cell-{index}.png",
                            "cropChecksumSha256": f"{1000 + index:064x}",
                        }
                        for index in range(15)
                    ],
                    corrected_by="integration-owner",
                    created_at=now,
                )
            )
            for sequence_number, review_item_id, board_id, status, geometry_revision in (
                (1, base_review_id, base_board_id, "accepted", 0),
                (2, corrected_review_id, corrected_board_id, "corrected", 1),
            ):
                board = session.get(RecognizedBoardModel, board_id)
                assert board is not None
                source = session.get(SourceImageModel, board.source_image_id)
                assert source is not None
                session.add(
                    ImageSequenceCanonicalModel(
                        game_id=game.id,
                        sequence_number=sequence_number,
                        review_item_id=review_item_id,
                        recognized_board_id=board_id,
                        import_job_id=job.id,
                        source_image_id=source.id,
                        source_checksum_sha256=source.checksum_sha256,
                        board_checksum_sha256=board.board_checksum_sha256,
                        status=status,
                        resolution_revision=1,
                        geometry_revision=geometry_revision,
                        created_at=now,
                    )
                )
            job_record = session.get(JobModel, job.id)
            assert job_record is not None
            job_record.status = JobStatus.WAITING_FOR_REVIEW
            projection_result = SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(
                game.id
            )
            assert projection_result.candidate_count == 3
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardSearchFastDocumentModel)
                    .where(ImageBoardSearchFastDocumentModel.game_id == game.id)
                )
                == 3
            )
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            repository = SqlAlchemyImageSymbolReviewRepository(session)
            assert repository.start_or_resume_backfill(game.id).status == "rebuilding"
            first_step = repository.backfill_next_batch(game.id, batch_size=1)
            assert first_step.processed_review_item_count == 1
            assert first_step.has_more is True
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            repository = SqlAlchemyImageSymbolReviewRepository(session)
            assert repository.start_or_resume_backfill(game.id).status == "rebuilding"
            second_step = repository.backfill_next_batch(game.id, batch_size=1)
            assert second_step.processed_review_item_count == 1
            third_step = repository.backfill_next_batch(game.id, batch_size=1)
            assert third_step.processed_review_item_count == 1
            final_step = repository.backfill_next_batch(game.id, batch_size=1)
            assert final_step.has_more is False
            assert final_step.report.status == "ready"
            assert final_step.report.cell_count == 45
            session.commit()

        with Session(engine) as session:
            state = session.get(ImageSymbolReviewStateModel, game.id)
            assert state is not None
            assert state.status == "ready"
            assert state.processed_review_item_count == 3
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewCellModel)
                    .where(ImageSymbolReviewCellModel.game_id == game.id)
                )
                == 45
            )
            base_cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == base_review_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            corrected_cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == corrected_review_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            pending_cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == pending_review_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert len(base_cells) == len(corrected_cells) == len(pending_cells) == 15
            assert all(cell.review_state == "approved" for cell in base_cells + corrected_cells)
            assert all(
                cell.assigned_symbol_id == symbol.id for cell in base_cells + corrected_cells
            )
            assert [cell.geometry_revision for cell in corrected_cells] == [1] * 15
            assert [cell.cropper_version for cell in corrected_cells] == [
                "corrected-cropper-v1"
            ] * 15
            assert [cell.crop_relative_path for cell in corrected_cells] == [
                f"corrected/cell-{index}.png" for index in range(15)
            ]
            assert all(cell.review_state == "pending" for cell in pending_cells)
            assert all(cell.assigned_symbol_id is None for cell in pending_cells)
            session.execute(
                delete(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == pending_review_id
                )
            )
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            assert backfill.start_or_resume_backfill(game.id).status == "rebuilding"
            reconciliation = backfill.reconcile_next_batch(game.id, batch_size=10)
            assert reconciliation.processed_review_item_count == 1
            assert reconciliation.report.status == "rebuilding"
            assert backfill.finalize_backfill(game.id).status == "ready"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewCellModel)
                    .where(ImageSymbolReviewCellModel.review_item_id == pending_review_id)
                )
                == 15
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardSearchFastDocumentModel)
                    .where(ImageBoardSearchFastDocumentModel.game_id == game.id)
                )
                == 3
            )
            query_repository = SqlAlchemySymbolCellReviewQueryRepository(session)
            known_filter = SymbolCellReviewListFilter(
                game_id=game.id,
                symbol_id=symbol.id,
                state=SymbolCellReviewFilterState.ALL,
            )
            first_page = query_repository.list_items(
                review_filter=known_filter,
                after_key=None,
                before_key=None,
                limit=16,
            )
            assert [item.sequence_number for item in first_page.items] == [1] * 15 + [2]
            assert first_page.has_previous is False
            assert first_page.has_next is True
            assert query_repository.counts(review_filter=known_filter).all_count == 30
            assert query_repository.counts(review_filter=known_filter).approved_count == 30
            assert query_repository.counts(review_filter=known_filter).pending_count == 0
            second_page = query_repository.list_items(
                review_filter=known_filter,
                after_key=first_page.items[-1].cursor_key,
                before_key=None,
                limit=16,
            )
            assert [item.sequence_number for item in second_page.items] == [2] * 14
            assert {item.cell_review_id for item in first_page.items}.isdisjoint(
                item.cell_review_id for item in second_page.items
            )
            unknown_filter = SymbolCellReviewListFilter(
                game_id=game.id,
                symbol_id=None,
                state=SymbolCellReviewFilterState.PENDING,
            )
            unknown_page = query_repository.list_items(
                review_filter=unknown_filter,
                after_key=None,
                before_key=None,
                limit=20,
            )
            assert len(unknown_page.items) == 15
            assert {item.sequence_number for item in unknown_page.items} == {3}
            assert all(item.assigned_symbol_id is None for item in unknown_page.items)
            session.execute(
                delete(ImageBoardSearchFastDocumentModel).where(
                    ImageBoardSearchFastDocumentModel.game_id == game.id,
                    ImageBoardSearchFastDocumentModel.sequence_number == 2,
                )
            )
            hidden_owner_page = query_repository.list_items(
                review_filter=known_filter,
                after_key=None,
                before_key=None,
                limit=20,
            )
            assert len(hidden_owner_page.items) == 15
            assert {item.sequence_number for item in hidden_owner_page.items} == {1}
    finally:
        engine.dispose()


def test_symbol_cell_write_through_tracks_board_geometry_and_prediction_mutations(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 26, 13, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="symbol-cell-write-through",
                name="Symbol cell write through",
                status=GameStatus.ACTIVE,
            )
            symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="test",
                name="Test",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            catalog.create_symbol(
                game.id,
                mobile_code=2,
                code="other",
                name="Other",
                image_path=None,
                is_wildcard=False,
                display_order=1,
                status=SymbolStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        execution = image_store.register_file(
            job.id,
            source_checksum_sha256="9" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="write-through.jpg",
            order_index=0,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            review_item_id, board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum="9" * 64,
                source_name="write-through.jpg",
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

        with Session(engine, expire_on_commit=False) as session:
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            assert backfill.start_or_resume_backfill(game.id).status == "rebuilding"
            backfill.backfill_next_batch(game.id, batch_size=10)
            finished = backfill.backfill_next_batch(game.id, batch_size=10)
            assert finished.has_more is False
            assert finished.report.status == "ready"
            assert finished.report.catalog_revision == 1
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            grid_service = ImageGridReviewService(SqlAlchemyImageGridReviewRepository(session))
            grid_page = grid_service.list(
                game_id=game.id,
                view=ImageGridReviewView.NEEDS_VALIDATION,
                import_job_id=None,
                after_cursor=None,
                before_cursor=None,
                limit=10,
            )
            assert len(grid_page.items) == 1
            grid_item = grid_page.items[0]
            assert grid_item.review_item_id == review_item_id
            assert grid_item.state is ImageGridReviewState.NEEDS_VALIDATION
            assert grid_page.counts.needs_validation == 1
            with pytest.raises(ImageGridReviewError) as conflict:
                grid_service.approve(
                    game_id=game.id,
                    review_item_id=review_item_id,
                    expected_resolution_revision=grid_item.resolution_revision,
                    expected_geometry_revision=grid_item.geometry_revision,
                    expected_source_checksum_sha256="0" * 64,
                    expected_source_width=grid_item.source_width,
                    expected_source_height=grid_item.source_height,
                    expected_grid_rows=grid_item.topology.rows,
                    expected_grid_columns=grid_item.topology.columns,
                    actor="grid-reviewer",
                )
            assert conflict.value.code == "IMAGE_GRID_REVIEW_SOURCE_DRIFT"
            approval = grid_service.approve(
                game_id=game.id,
                review_item_id=review_item_id,
                expected_resolution_revision=grid_item.resolution_revision,
                expected_geometry_revision=grid_item.geometry_revision,
                expected_source_checksum_sha256=grid_item.source_checksum_sha256,
                expected_source_width=grid_item.source_width,
                expected_source_height=grid_item.source_height,
                expected_grid_rows=grid_item.topology.rows,
                expected_grid_columns=grid_item.topology.columns,
                actor="grid-reviewer",
            )
            assert approval.changed is True
            assert approval.item.state is ImageGridReviewState.APPROVED
            session.rollback()

        with Session(engine, expire_on_commit=False) as session:
            repository = SqlAlchemyOperationalImageReviewRepository(session)
            service = OperationalImageReviewService(repository)
            item = service.get_item(
                review_item_id,
                game_id=game.id,
                import_job_id=job.id,
            )
            resolved, _event, created = service.resolve_item(
                review_item_id,
                game_id=game.id,
                import_job_id=job.id,
                idempotency_key=uuid4(),
                expected_revision=item.resolution_revision,
                action=ImageReviewAction.ACCEPTED,
                sequence_number=1,
                geometry_revision=item.geometry_revision,
                cells=tuple(
                    ImageReviewResolutionCell(
                        cell_index=cell.cell_index,
                        crop_sample_id=cell.crop_sample_id,
                        symbol_code="test",
                    )
                    for cell in item.cells
                ),
                rejection_reason=None,
                resolved_by="write-through-reviewer",
            )
            assert created is True
            assert resolved.status == "accepted"
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert len(cells) == 15
            assert all(cell.review_state == "approved" for cell in cells)
            assert all(cell.assigned_symbol_id == symbol.id for cell in cells)
            assert all(cell.assignment_source == "board_decision" for cell in cells)
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(ImageSymbolReviewEventModel.review_item_id == review_item_id)
                )
                == 15
            )
            state = session.get(ImageSymbolReviewStateModel, game.id)
            assert state is not None
            assert state.catalog_revision == 2

            board = session.get(RecognizedBoardModel, board_id)
            review = session.get(ImageReviewItemModel, review_item_id)
            assert board is not None and review is not None
            session.add(
                ImageSymbolPredictionRevisionModel(
                    game_id=game.id,
                    review_item_id=review_item_id,
                    recognized_board_id=board_id,
                    source_job_id=job.id,
                    model_iteration_id=None,
                    model_version="write-through-test-v2",
                    model_checksum_sha256="a" * 64,
                    crop_manifest_checksum_sha256="b" * 64,
                    predictions=[
                        {
                            "symbolCode": "other",
                            "confidence": 0.9,
                            "alternatives": [{"symbolCode": "other", "confidence": 0.9}],
                        }
                        for _index in range(15)
                    ],
                )
            )
            session.flush()
            assert (
                SymbolCellReviewWriteThroughCoordinator(
                    session
                ).synchronize_after_prediction_refresh(
                    game_id=game.id,
                    review_item_id=review_item_id,
                    actor="system:test-reinference",
                )
                is True
            )
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert all(cell.assigned_symbol_id == symbol.id for cell in cells)
            assert all(cell.review_state == "approved" for cell in cells)
            assert all(cell.prediction_symbol_code == "other" for cell in cells)

            repository = SqlAlchemyOperationalImageReviewRepository(session)
            item = repository.get_item(
                review_item_id,
                game_id=game.id,
                import_job_id=job.id,
            )
            assert item is not None
            command_value = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(1, 1),
                    ImageReviewGeometryPoint(91, 1),
                    ImageReviewGeometryPoint(91, 91),
                    ImageReviewGeometryPoint(1, 91),
                ),
                expected_geometry_revision=item.geometry_revision,
                expected_resolution_revision=item.resolution_revision,
                corrected_by="geometry-reviewer",
            )
            _updated, revision, created = repository.save_geometry_revision(
                review_item_id=review_item_id,
                game_id=game.id,
                import_job_id=job.id,
                idempotency_key=uuid4(),
                command=command_value,
                artifacts=ImageReviewGeometryArtifacts(
                    geometry={"source": "write-through-test"},
                    board_relative_path="corrected/write-through.png",
                    board_checksum_sha256="c" * 64,
                    cropper_version="write-through-cropper-v2",
                    cells=tuple(
                        ImageReviewGeometryCellArtifact(
                            row_index=index // 5,
                            column_index=index % 5,
                            crop_relative_path=f"corrected/write-through-{index}.png",
                            crop_checksum_sha256=f"{5000 + index:064x}",
                        )
                        for index in range(15)
                    ),
                ),
                created_at=now + timedelta(minutes=1),
            )
            assert created is True
            assert revision.revision == 1
            session.commit()

        with Session(engine) as session:
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert len(cells) == 15
            assert all(cell.geometry_revision == 1 for cell in cells)
            assert all(cell.review_state == "approved" for cell in cells)
            assert all(cell.quality_issue is None for cell in cells)
            assert all(cell.assigned_symbol_id == symbol.id for cell in cells)
            assert all(cell.approved_geometry_revision == 0 for cell in cells)
            assert all(
                cell.approved_crop_checksum_sha256 != cell.crop_checksum_sha256 for cell in cells
            )
            assert [cell.crop_relative_path for cell in cells] == [
                f"corrected/write-through-{index}.png" for index in range(15)
            ]
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(
                        ImageSymbolReviewEventModel.review_item_id == review_item_id,
                        ImageSymbolReviewEventModel.action == "geometry_invalidated",
                    )
                )
                == 15
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardGeometryReviewEventModel)
                    .where(
                        ImageBoardGeometryReviewEventModel.review_item_id == review_item_id,
                        ImageBoardGeometryReviewEventModel.action == "geometry_saved",
                    )
                )
                == 1
            )
            state = session.get(ImageSymbolReviewStateModel, game.id)
            assert state is not None
            # Geometry invokes both its cell synchronization and its canonical
            # projection synchronization. The catalog advances once, not twice.
            assert state.catalog_revision == 4
            review = session.get(ImageReviewItemModel, review_item_id)
            board = session.get(RecognizedBoardModel, board_id)
            assert review is not None and board is not None
            assert review.status == "corrected"
            assert board.approved_geometry_revision == 1
            assert board.geometry_approved_by == "geometry-reviewer"
            review.status = "superseded"
            review.resolved_value = {
                "action": "superseded",
                "canonicalReviewItemId": str(review_item_id),
                "sequenceNumber": 1,
            }
            review.resolved_by = "system:test-superseded"
            review.resolved_at = now + timedelta(minutes=2)
            review.resolution_revision += 1
            SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(review_item_id)
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            assert coordinator.synchronize_after_board_resolution(
                game_id=game.id,
                review_item_id=review_item_id,
                actor="system:test-superseded",
            )
            assert coordinator.synchronize_after_projection_change(game_id=game.id)
            session.commit()

        with Session(engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardSearchFastDocumentModel)
                    .where(ImageBoardSearchFastDocumentModel.game_id == game.id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewCellModel)
                    .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                )
                == 15
            )
            state = session.get(ImageSymbolReviewStateModel, game.id)
            assert state is not None
            assert state.catalog_revision == 5
            grid_page = ImageGridReviewService(SqlAlchemyImageGridReviewRepository(session)).list(
                game_id=game.id,
                view=ImageGridReviewView.ALL,
                import_job_id=None,
                after_cursor=None,
                before_cursor=None,
                limit=10,
            )
            assert grid_page.items == ()
            assert grid_page.counts.total == 0
    finally:
        engine.dispose()


def test_symbol_cell_mutations_close_and_reopen_one_board_atomically(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 26, 15, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="symbol-cell-mutations",
                name="Symbol cell mutations",
                status=GameStatus.ACTIVE,
            )
            first_symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="first",
                name="First",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            second_symbol = catalog.create_symbol(
                game.id,
                mobile_code=2,
                code="second",
                name="Second",
                image_path=None,
                is_wildcard=False,
                display_order=1,
                status=SymbolStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        execution = image_store.register_file(
            job.id,
            source_checksum_sha256="8" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="cell-mutations.jpg",
            order_index=0,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            review_item_id, board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum="8" * 64,
                source_name="cell-mutations.jpg",
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

        with Session(engine, expire_on_commit=False) as session:
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            assert backfill.start_or_resume_backfill(game.id).status == "rebuilding"
            first_step = backfill.backfill_next_batch(game.id, batch_size=20)
            assert first_step.has_more is False
            finished = backfill.backfill_next_batch(game.id, batch_size=20)
            assert finished.has_more is False
            assert finished.report.status == "ready"
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            assert SymbolCellReviewWriteThroughCoordinator(session).approve_current_geometry(
                game_id=game.id,
                review_item_id=review_item_id,
                expected_geometry_revision=0,
                actor="grid-reviewer",
                approved_at=now + timedelta(seconds=1),
            )
            assert not SymbolCellReviewWriteThroughCoordinator(session).approve_current_geometry(
                game_id=game.id,
                review_item_id=review_item_id,
                expected_geometry_revision=0,
                actor="grid-reviewer",
                approved_at=now + timedelta(seconds=2),
            )
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert len(cells) == 15
            # Model suggestions may legitimately be `?`.  This fixture gives
            # each pending crop a reviewed candidate so the test exercises the
            # explicit approve action that closes the fifteenth cell.
            for cell in cells:
                cell.assigned_symbol_id = first_symbol.id
            session.flush()
            for cell in cells:
                result = service.approve(
                    game_id=game.id,
                    cell_review_id=cell.id,
                    expected_revision=cell.revision,
                    expected_geometry_revision=cell.geometry_revision,
                    expected_crop_sample_id=cell.crop_sample_id,
                    expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                    actor="symbol-cell-operator",
                )
            assert result.board_status == "corrected"
            assert result.board_resolution_action == "corrected"
            assert result.board_reopened is False
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            review = session.get(ImageReviewItemModel, review_item_id)
            assert review is not None
            assert review.status == "corrected"
            assert review.resolved_value is not None
            assert review.resolved_value["symbolCodes"] == ["first"] * 15
            canonical = session.get(
                ImageSequenceCanonicalModel,
                {"game_id": game.id, "sequence_number": 1},
            )
            completed_job = session.get(JobModel, job.id)
            queue_state = session.get(ImageReviewQueueStateModel, job.id)
            staging = session.get(
                ImageLayoutStagingRowModel,
                {"import_job_id": job.id, "recognized_board_id": board_id},
            )
            assert canonical is not None and canonical.status == "corrected"
            assert staging is not None and staging.cells == [1] * 15
            assert completed_job is not None and completed_job.status is JobStatus.COMPLETED
            assert queue_state is not None and queue_state.pending_count == 0
            cell = session.scalar(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.cell_index == 0,
                )
            )
            assert cell is not None
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            with pytest.raises(SymbolCellReviewError) as stale:
                service.reassign(
                    game_id=game.id,
                    cell_review_id=cell.id,
                    expected_revision=cell.revision,
                    expected_geometry_revision=cell.geometry_revision,
                    expected_crop_sample_id=cell.crop_sample_id,
                    expected_crop_checksum_sha256="f" * 64,
                    target_symbol_id=second_symbol.id,
                    actor="symbol-cell-operator",
                )
            assert stale.value.code == "SYMBOL_CELL_REVIEW_CROP_DRIFT"
            result = service.reassign(
                game_id=game.id,
                cell_review_id=cell.id,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                target_symbol_id=second_symbol.id,
                actor="symbol-cell-operator",
            )
            assert result.board_status == "corrected"
            assert result.board_resolution_action == "corrected"
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            review = session.get(ImageReviewItemModel, review_item_id)
            staging = session.get(
                ImageLayoutStagingRowModel,
                {"import_job_id": job.id, "recognized_board_id": board_id},
            )
            assert review is not None and review.status == "corrected"
            assert review.resolved_value is not None
            assert review.resolved_value["symbolCodes"] == ["second"] + ["first"] * 14
            assert staging is not None and staging.cells == [2] + [1] * 14
            cell = session.scalar(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.cell_index == 1,
                )
            )
            assert cell is not None
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            result = service.mark_unreadable(
                game_id=game.id,
                cell_review_id=cell.id,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            assert result.board_status == "pending"
            assert result.board_resolution_action is None
            assert result.board_reopened is True
            assert result.quality_issue is SymbolCellQualityIssue.UNREADABLE
            session.commit()

        with Session(engine) as session:
            review = session.get(ImageReviewItemModel, review_item_id)
            board = session.get(RecognizedBoardModel, board_id)
            source = session.scalar(
                select(SourceImageModel).where(SourceImageModel.import_job_id == job.id)
            )
            reopened_job = session.get(JobModel, job.id)
            queue_state = session.get(ImageReviewQueueStateModel, job.id)
            assert review is not None and review.status == "pending"
            assert review.resolved_value is None
            assert board is not None and board.status == "pending_review"
            assert source is not None and source.status == "waiting_for_review"
            assert reopened_job is not None and reopened_job.status is JobStatus.WAITING_FOR_REVIEW
            assert queue_state is not None and queue_state.pending_count == 1
            assert (
                session.get(
                    ImageSequenceCanonicalModel,
                    {"game_id": game.id, "sequence_number": 1},
                )
                is None
            )
            assert (
                session.get(
                    ImageLayoutStagingRowModel,
                    {"import_job_id": job.id, "recognized_board_id": board_id},
                )
                is None
            )
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert cells[1].review_state == "pending"
            assert cells[1].quality_issue is None
            assert cells[1].quality_issue == "unreadable"
            assert all(
                cell.review_state == "approved" and cell.quality_issue is None
                for index, cell in enumerate(cells)
                if index != 1
            )
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            grid_result = service.mark_grid_issue(
                game_id=game.id,
                cell_review_id=cells[2].id,
                expected_revision=cells[2].revision,
                expected_geometry_revision=cells[2].geometry_revision,
                expected_crop_sample_id=cells[2].crop_sample_id,
                expected_crop_checksum_sha256=cells[2].crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            assert grid_result.board_reopened is False
            assert grid_result.quality_issue is SymbolCellQualityIssue.GRID_ISSUE
            session.flush()
            query_repository = SqlAlchemySymbolCellReviewQueryRepository(session)
            known_pending = query_repository.list_items(
                review_filter=SymbolCellReviewListFilter(
                    game_id=game.id,
                    symbol_id=first_symbol.id,
                    state=SymbolCellReviewFilterState.PENDING,
                ),
                after_key=None,
                before_key=None,
                limit=20,
            )
            assert known_pending.items == ()
            temporarily_unrecognized = query_repository.list_items(
                review_filter=SymbolCellReviewListFilter(
                    game_id=game.id,
                    symbol_id=None,
                    state=SymbolCellReviewFilterState.PENDING,
                ),
                after_key=None,
                before_key=None,
                limit=20,
            )
            assert [item.cell_index for item in temporarily_unrecognized.items] == [1, 2]
            assert all(item.is_unknown for item in temporarily_unrecognized.items)
            assert all(item.assigned_symbol_id is None for item in temporarily_unrecognized.items)
            all_game_crops = query_repository.list_items(
                review_filter=SymbolCellReviewListFilter(
                    game_id=game.id,
                    symbol_id=None,
                    state=SymbolCellReviewFilterState.ALL,
                    include_all_symbols=True,
                ),
                after_key=None,
                before_key=None,
                limit=20,
            )
            assert [item.cell_index for item in all_game_crops.items] == list(range(15))
            operational_repository = SqlAlchemyOperationalImageReviewRepository(session)
            grid_issue_page = operational_repository.list_items(
                game_id=game.id,
                import_job_id=job.id,
                view=ImageReviewView.ALL,
                grid_issue_view=ImageReviewGridIssueView.NEEDS_GRID_FIX,
                after_key=None,
                before_key=None,
                expected_queue_version=None,
                sequence_number=None,
                resume_at_first_pending=False,
                limit=10,
            )
            assert [item.id for item in grid_issue_page.items] == [review_item_id]
            assert grid_issue_page.needs_grid_fix_count == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(
                        ImageSymbolReviewEventModel.review_item_id == review_item_id,
                        ImageSymbolReviewEventModel.action == "mark_grid_issue",
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(
                        ImageSymbolReviewEventModel.review_item_id == review_item_id,
                        ImageSymbolReviewEventModel.action == "mark_unreadable",
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageReviewResolutionEventModel)
                    .where(
                        ImageReviewResolutionEventModel.review_item_id == review_item_id,
                        ImageReviewResolutionEventModel.action == "reopened",
                    )
                )
                == 1
            )
            current = operational_repository.get_item(
                review_item_id,
                game_id=game.id,
                import_job_id=job.id,
            )
            assert current is not None
            with pytest.raises(ImageGridReviewError) as blocked_approval:
                SymbolCellReviewWriteThroughCoordinator(session).approve_current_geometry(
                    game_id=game.id,
                    review_item_id=review_item_id,
                    expected_geometry_revision=current.geometry_revision,
                    actor="grid-issue-reviewer",
                    approved_at=now + timedelta(seconds=30),
                )
            assert blocked_approval.value.code == "IMAGE_GRID_REVIEW_CORRECTION_REQUIRED"
            geometry_command = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(1, 1),
                    ImageReviewGeometryPoint(91, 1),
                    ImageReviewGeometryPoint(91, 91),
                    ImageReviewGeometryPoint(1, 91),
                ),
                expected_geometry_revision=current.geometry_revision,
                expected_resolution_revision=current.resolution_revision,
                corrected_by="grid-issue-reviewer",
            )
            _updated, _revision, geometry_created = operational_repository.save_geometry_revision(
                review_item_id=review_item_id,
                game_id=game.id,
                import_job_id=job.id,
                idempotency_key=uuid4(),
                command=geometry_command,
                artifacts=ImageReviewGeometryArtifacts(
                    geometry={"source": "grid-issue-filter-test"},
                    board_relative_path="corrected/grid-issue.png",
                    board_checksum_sha256="d" * 64,
                    cropper_version="grid-issue-filter-test",
                    cells=tuple(
                        ImageReviewGeometryCellArtifact(
                            row_index=index // 5,
                            column_index=index % 5,
                            crop_relative_path=f"corrected/grid-issue-{index}.png",
                            crop_checksum_sha256=f"{6000 + index:064x}",
                        )
                        for index in range(15)
                    ),
                ),
                created_at=now + timedelta(minutes=1),
            )
            assert geometry_created is True
            refreshed_cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            assert [
                cell.cell_index for cell in refreshed_cells if cell.review_state == "pending"
            ] == [
                1,
                2,
            ]
            assert all(
                cell.review_state == "approved"
                and cell.approved_geometry_revision == 0
                and cell.geometry_revision == 1
                for cell in refreshed_cells
                if cell.cell_index not in {1, 2}
            )
            recropped = refreshed_cells[1]
            SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            ).reassign(
                game_id=game.id,
                cell_review_id=recropped.id,
                expected_revision=recropped.revision,
                expected_geometry_revision=recropped.geometry_revision,
                expected_crop_sample_id=recropped.crop_sample_id,
                expected_crop_checksum_sha256=recropped.crop_checksum_sha256,
                target_symbol_id=first_symbol.id,
                actor="symbol-cell-operator",
            )
            session.flush()
            assert recropped.review_state == "approved"
            assert recropped.approved_crop_sample_id == recropped.crop_sample_id
            assert recropped.approved_crop_checksum_sha256 == recropped.crop_checksum_sha256
            assert recropped.approved_geometry_revision == recropped.geometry_revision == 1
            cleared_grid_issue_page = operational_repository.list_items(
                game_id=game.id,
                import_job_id=job.id,
                view=ImageReviewView.ALL,
                grid_issue_view=ImageReviewGridIssueView.NEEDS_GRID_FIX,
                after_key=None,
                before_key=None,
                expected_queue_version=None,
                sequence_number=None,
                resume_at_first_pending=False,
                limit=10,
            )
            assert cleared_grid_issue_page.items == ()
            assert cleared_grid_issue_page.needs_grid_fix_count == 0

            # Resolve the remaining recropped cell, then exercise the dedicated
            # whole-board unreadable workflow with logical unknown as the last
            # decision needed to close the board.
            recropped_grid_cell = refreshed_cells[2]
            SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            ).reassign(
                game_id=game.id,
                cell_review_id=recropped_grid_cell.id,
                expected_revision=recropped_grid_cell.revision,
                expected_geometry_revision=recropped_grid_cell.geometry_revision,
                expected_crop_sample_id=recropped_grid_cell.crop_sample_id,
                expected_crop_checksum_sha256=recropped_grid_cell.crop_checksum_sha256,
                target_symbol_id=first_symbol.id,
                actor="symbol-cell-operator",
            )
            session.flush()
            unreadable_result = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            ).mark_unreadable(
                game_id=game.id,
                cell_review_id=recropped.id,
                expected_revision=recropped.revision,
                expected_geometry_revision=recropped.geometry_revision,
                expected_crop_sample_id=recropped.crop_sample_id,
                expected_crop_checksum_sha256=recropped.crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            assert unreadable_result.board_status == "pending"
            session.flush()

            unreadable_service = UnreadableBoardReviewService(
                SqlAlchemyUnreadableBoardReviewRepository(session)
            )
            pending_page = unreadable_service.list(
                game_id=game.id,
                view=UnreadableBoardReviewView.PENDING,
                after_cursor=None,
                limit=10,
            )
            assert [item.review_item_id for item in pending_page.items] == [review_item_id]
            unreadable_detail = unreadable_service.detail(
                game_id=game.id,
                review_item_id=review_item_id,
            )
            assert len(unreadable_detail.cells) == 15
            target = unreadable_detail.cells[1]
            normal_cell = unreadable_detail.cells[0]
            resolved_unknown = unreadable_service.save(
                game_id=game.id,
                review_item_id=review_item_id,
                cells=tuple(
                    SaveUnreadableBoardCellCommand(
                        cell_index=cell.cell_index,
                        expected_revision=cell.revision,
                        expected_geometry_revision=cell.geometry_revision,
                        expected_crop_sample_id=cell.crop_sample_id,
                        expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                        target_symbol_id=(
                            None
                            if cell.cell_index in {target.cell_index, normal_cell.cell_index}
                            else cell.assigned_symbol_id
                        ),
                    )
                    for cell in unreadable_detail.cells
                ),
                actor="unreadable-board-reviewer",
            )
            assert resolved_unknown.board_status == "corrected"
            assert resolved_unknown.changed_cell_count == 2
            session.commit()

        with Session(engine) as session:
            review = session.get(ImageReviewItemModel, review_item_id)
            assert review is not None and review.status == "corrected"
            assert review.resolved_value is not None
            assert review.resolved_value["symbolCodes"][1] is None
            canonical = session.get(
                ImageSequenceCanonicalModel,
                {"game_id": game.id, "sequence_number": 1},
            )
            assert canonical is not None and canonical.review_item_id == review_item_id
            staging = session.get(
                ImageLayoutStagingRowModel,
                {"import_job_id": job.id, "recognized_board_id": board_id},
            )
            assert staging is not None
            assert staging.cells == [0, 0] + [1] * 13
            target = session.scalar(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.cell_index == 1,
                )
            )
            assert target is not None
            assert target.review_state == "approved"
            assert target.assigned_symbol_id is None
            assert target.quality_issue == "unreadable"
            assert target.approved_crop_sample_id == target.crop_sample_id
            assert target.approved_crop_checksum_sha256 == target.crop_checksum_sha256
            normal_cell = session.scalar(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                    ImageSymbolReviewCellModel.cell_index == 0,
                )
            )
            assert normal_cell is not None
            assert normal_cell.review_state == "approved"
            assert normal_cell.assigned_symbol_id is None
            assert normal_cell.quality_issue == "unreadable"
            unreadable_service = UnreadableBoardReviewService(
                SqlAlchemyUnreadableBoardReviewRepository(session)
            )
            assert (
                unreadable_service.list(
                    game_id=game.id,
                    view=UnreadableBoardReviewView.PENDING,
                    after_cursor=None,
                    limit=10,
                ).items
                == ()
            )
            all_page = unreadable_service.list(
                game_id=game.id,
                view=UnreadableBoardReviewView.ALL,
                after_cursor=None,
                limit=10,
            )
            assert [item.review_item_id for item in all_page.items] == [review_item_id]
    finally:
        engine.dispose()


def test_symbol_cell_bulk_operation_is_idempotent_and_resumes_board_batches(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 26, 16, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="symbol-cell-bulk",
                name="Symbol cell bulk",
                status=GameStatus.ACTIVE,
            )
            symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="first",
                name="First",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        first_execution = image_store.register_file(
            job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="symbol-cell-bulk-1.jpg",
            order_index=0,
            registered_at=now,
        )
        second_execution = image_store.register_file(
            job.id,
            source_checksum_sha256="2" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="symbol-cell-bulk-2.jpg",
            order_index=1,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            first_review_item_id, _first_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=first_execution.file_execution_key,
                source_checksum="1" * 64,
                source_name="symbol-cell-bulk-1.jpg",
                position_index=0,
                sequence_number=1,
                status="pending",
                created_at=now,
            )
            second_review_item_id, _second_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=second_execution.file_execution_key,
                source_checksum="2" * 64,
                source_name="symbol-cell-bulk-2.jpg",
                position_index=0,
                sequence_number=2,
                status="pending",
                created_at=now,
            )
            job_record = session.get(JobModel, job.id)
            assert job_record is not None
            job_record.status = JobStatus.WAITING_FOR_REVIEW
            SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game.id)
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            backfill.start_or_resume_backfill(game.id)
            assert backfill.backfill_next_batch(game.id, batch_size=50).has_more is False
            assert backfill.backfill_next_batch(game.id, batch_size=50).report.status == "ready"
            coordinator = SymbolCellReviewWriteThroughCoordinator(session)
            for review_item_id in (first_review_item_id, second_review_item_id):
                assert coordinator.approve_current_geometry(
                    game_id=game.id,
                    review_item_id=review_item_id,
                    expected_geometry_revision=0,
                    actor="grid-reviewer",
                    approved_at=now + timedelta(seconds=1),
                )
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.game_id == game.id)
                .order_by(
                    ImageSymbolReviewCellModel.sequence_number,
                    ImageSymbolReviewCellModel.cell_index,
                )
            ).all()
            assert len(cells) == 30
            for cell in cells:
                cell.assigned_symbol_id = symbol.id
            request = SymbolCellReviewBulkRequest(
                action=SymbolCellReviewAction.APPROVE,
                target_symbol_id=None,
                explicit_targets=tuple(
                    SymbolCellReviewBulkExplicitTarget(
                        cell_review_id=cell.id,
                        expected_revision=cell.revision,
                        expected_geometry_revision=cell.geometry_revision,
                        expected_crop_sample_id=cell.crop_sample_id,
                        expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                    )
                    for cell in cells
                ),
                filter_selection=None,
                actor="local-admin",
            )
            repository = SqlAlchemySymbolCellReviewBulkOperationRepository(session)
            idempotency_key = uuid4()
            operation, created = repository.start(
                game_id=game.id,
                request=request,
                idempotency_key=idempotency_key,
            )
            repeated, repeated_created = repository.start(
                game_id=game.id,
                request=request,
                idempotency_key=idempotency_key,
            )
            assert created is True
            assert repeated_created is False
            assert repeated.id == operation.id
            assert operation.target_count == 30
            with pytest.raises(SymbolCellReviewError) as idempotency_conflict:
                repository.start(
                    game_id=game.id,
                    request=SymbolCellReviewBulkRequest(
                        action=SymbolCellReviewAction.MARK_GRID_ISSUE,
                        target_symbol_id=None,
                        explicit_targets=request.explicit_targets,
                        filter_selection=None,
                        actor="local-admin",
                    ),
                    idempotency_key=idempotency_key,
                )
            assert idempotency_conflict.value.code == "SYMBOL_CELL_REVIEW_BULK_IDEMPOTENCY_CONFLICT"
            bulk_job = SqlAlchemyJobRepository(session).get_job(operation.job_id)
            assert bulk_job is not None
            session.commit()

        first_worker = SqlAlchemySymbolCellReviewBulkOperationWorker(session_factory)
        first_progress = first_worker.process_next_batch(job=bulk_job, max_boards=1)
        assert first_progress.has_pending_targets is True
        assert first_progress.operation.applied_count == 15
        assert first_progress.operation.pending_count == 15

        # A fresh worker instance models recovery after a crash between checkpoints.
        resumed_worker = SqlAlchemySymbolCellReviewBulkOperationWorker(session_factory)
        second_progress = resumed_worker.process_next_batch(job=bulk_job, max_boards=1)
        assert second_progress.has_pending_targets is False
        assert second_progress.operation.status is SymbolCellReviewBulkOperationStatus.COMPLETED

        with Session(engine) as session:
            persisted_operation = session.get(ImageSymbolReviewBulkOperationModel, operation.id)
            assert persisted_operation is not None
            assert persisted_operation.status == SymbolCellReviewBulkOperationStatus.COMPLETED.value
            assert persisted_operation.applied_count == 30
            assert persisted_operation.conflict_count == 0
            assert persisted_operation.failed_count == 0
            targets = session.scalars(
                select(ImageSymbolReviewBulkTargetModel).where(
                    ImageSymbolReviewBulkTargetModel.operation_id == operation.id
                )
            ).all()
            assert len(targets) == 30
            assert {target.status for target in targets} == {"applied"}
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(ImageSymbolReviewEventModel.operation_id == operation.id)
                )
                == 30
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageReviewItemModel)
                    .where(ImageReviewItemModel.status == "corrected")
                )
                == 2
            )
            state = session.get(ImageSymbolReviewStateModel, game.id)
            assert state is not None
            filter_operation, filter_created = SqlAlchemySymbolCellReviewBulkOperationRepository(
                session
            ).start(
                game_id=game.id,
                request=SymbolCellReviewBulkRequest(
                    action=SymbolCellReviewAction.MARK_UNREADABLE,
                    target_symbol_id=None,
                    explicit_targets=None,
                    filter_selection=SymbolCellReviewBulkFilterSelection(
                        symbol_id=symbol.id,
                        state=SymbolCellReviewFilterState.APPROVED,
                        catalog_revision=state.catalog_revision,
                        excluded_cell_review_ids=(targets[0].cell_review_id,),
                    ),
                    actor="local-admin",
                ),
                idempotency_key=uuid4(),
            )
            assert filter_created is True
            assert filter_operation.target_count == 29
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewBulkTargetModel)
                    .where(ImageSymbolReviewBulkTargetModel.operation_id == filter_operation.id)
                )
                == 29
            )
            filter_job = SqlAlchemyJobRepository(session).get_job(filter_operation.job_id)
            assert filter_job is not None
            session.commit()

        # Marking many crops unreadable on an already completed board must reopen that
        # board only after all target cells were updated.  Otherwise removing
        # canonical ownership after the first crop would make the remaining
        # targets conflict with their own bulk operation.
        unreadable_worker = SqlAlchemySymbolCellReviewBulkOperationWorker(session_factory)
        unreadable_progress = unreadable_worker.process_next_batch(job=filter_job, max_boards=1)
        assert unreadable_progress.has_pending_targets is True
        assert unreadable_progress.operation.applied_count == 14
        assert unreadable_progress.operation.pending_count == 15

        with Session(engine) as session:
            first_board = session.scalar(
                select(ImageReviewItemModel)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .where(RecognizedBoardModel.sequence_number == 1)
            )
            assert first_board is not None
            assert first_board.status == "pending"
            first_board_targets = session.scalars(
                select(ImageSymbolReviewBulkTargetModel).where(
                    ImageSymbolReviewBulkTargetModel.operation_id == filter_operation.id,
                    ImageSymbolReviewBulkTargetModel.sequence_number == 1,
                )
            ).all()
            assert len(first_board_targets) == 14
            assert {target.status for target in first_board_targets} == {"applied"}
            first_board_cells = session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == first_board.id
                )
            ).all()
            assert sum(cell.quality_issue == "grid_issue" for cell in first_board_cells) == 0
            assert sum(cell.quality_issue == "unreadable" for cell in first_board_cells) == 14

            # Model a concurrent full-page geometry save before the next
            # board is processed.  Frozen target identity must turn that
            # entire board batch into a controlled conflict, never into a
            # mixture of old and new crop decisions.
            second_board_cell = session.scalar(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.sequence_number == 2)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            )
            assert second_board_cell is not None
            second_board_cell.geometry_revision += 1
            second_board_cell.crop_sample_id = "e" * 64
            second_board_cell.crop_checksum_sha256 = "f" * 64
            session.commit()

        conflict_progress = unreadable_worker.process_next_batch(job=filter_job, max_boards=1)
        assert conflict_progress.has_pending_targets is False
        assert conflict_progress.operation.status is SymbolCellReviewBulkOperationStatus.COMPLETED
        assert conflict_progress.operation.applied_count == 14
        assert conflict_progress.operation.conflict_count == 15

        with Session(engine) as session:
            conflicted_targets = session.scalars(
                select(ImageSymbolReviewBulkTargetModel).where(
                    ImageSymbolReviewBulkTargetModel.operation_id == filter_operation.id,
                    ImageSymbolReviewBulkTargetModel.sequence_number == 2,
                )
            ).all()
            assert len(conflicted_targets) == 15
            assert {target.status for target in conflicted_targets} == {"conflict"}
            assert {target.error_code for target in conflicted_targets} == {
                "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT"
            }
    finally:
        engine.dispose()


def test_symbol_cell_backfill_fails_closed_when_an_active_board_has_no_sequence(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 26, 13, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="symbol-cell-no-sequence",
                name="Symbol cell no sequence",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        execution = image_store.register_file(
            job.id,
            source_checksum_sha256="5" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="missing-sequence.jpg",
            order_index=0,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            source = SourceImageModel(
                import_job_id=job.id,
                file_execution_key=execution.file_execution_key,
                relative_path="missing-sequence.jpg",
                checksum_sha256="5" * 64,
                width=1920,
                height=1080,
                status="waiting_for_review",
                created_at=now,
            )
            session.add(source)
            session.flush()
            board = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=0,
                sequence_number_raw="?",
                sequence_number=None,
                sequence_confidence=0.0,
                board_geometry={"source": "integration"},
                board_relative_path="boards/missing-sequence.png",
                board_checksum_sha256="6" * 64,
                cells_prediction={"cells": []},
                board_confidence=1.0,
                pipeline_fingerprint=PIPELINE,
                status="pending_review",
                created_at=now,
            )
            session.add(board)
            session.flush()
            review = ImageReviewItemModel(
                recognized_board_id=board.id,
                status="pending",
                snapshot={"sequenceNumber": None},
                resolution_revision=0,
                created_at=now,
            )
            session.add(review)
            session.flush()

            report = SqlAlchemyImageSymbolReviewRepository(session).start_or_resume_backfill(
                game.id
            )
            assert report.status == "failed"
            assert report.missing_sequence_count == 1
            assert report.sample_problem_review_item_ids == (review.id,)
            assert report.failure_message is not None
            assert "SYMBOL_CELL_REVIEW_SEQUENCE_MISSING" in report.failure_message
            session.commit()
    finally:
        engine.dispose()


def test_manual_deferred_geometry_materializes_one_complete_review_projection(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    symbol_model = bootstrap_symbol_model_snapshot()

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="manual-deferred-geometry",
                name="Manual deferred geometry",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(
                create_job(
                    JobType.IMPORT,
                    game_id=game.id,
                    input_payload={
                        "import_kind": "image_directory",
                        "pipeline_fingerprint": PIPELINE,
                        "schema_version": 5,
                        "symbol_model": symbol_model.to_payload(),
                    },
                    created_at=now,
                )
            )
            session.commit()

        execution = image_store.register_file(
            job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="originals/seq_64-72.png",
            order_index=7,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session, session.begin():
            source = SourceImageModel(
                import_job_id=job.id,
                file_execution_key=execution.file_execution_key,
                relative_path="originals/seq_64-72.png",
                checksum_sha256="1" * 64,
                width=620,
                height=420,
                status="processing",
                created_at=now,
            )
            session.add(source)
            session.flush()
            session.add(
                ImagePipelineStageResultModel(
                    file_execution_key=execution.file_execution_key,
                    stage="board_detection",
                    adapter_version="integration-board-detection-v1",
                    result_payload={
                        "boards": [
                            {
                                "confidence": 0.73,
                                "geometry": {
                                    "quad": [
                                        {"x": 60.0, "y": 50.0},
                                        {"x": 560.0, "y": 50.0},
                                        {"x": 560.0, "y": 350.0},
                                        {"x": 60.0, "y": 350.0},
                                    ]
                                },
                                "positionIndex": 0,
                            }
                        ]
                    },
                    created_at=now,
                )
            )
            manifest = BoardCellProcessingManifestV1(
                game_id=game.id,
                import_job_id=job.id,
                source_image_id=source.id,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                position_index=0,
                sequence_number=64,
                pipeline_fingerprint_sha256=PIPELINE,
                estimator_version="board-cell-geometry-v20",
                estimator_fingerprint_sha256="2" * 64,
                cropper_version="board-cell-crops-v19",
                cropper_fingerprint_sha256="3" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
            )
            repository = SqlAlchemyBoardCellGeometryPendingRepository(session)
            pending, created = repository.defer(
                manifest=manifest,
                reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
                manifest_relative_path=(
                    f"image-board-cell-processing-v1/{manifest.checksum_sha256}.json"
                ),
            )
            assert created is True
            geometry_command = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(x=60, y=50),
                    ImageReviewGeometryPoint(x=560, y=50),
                    ImageReviewGeometryPoint(x=560, y=350),
                    ImageReviewGeometryPoint(x=60, y=350),
                ),
                expected_geometry_revision=0,
                expected_resolution_revision=0,
                corrected_by="integration-owner",
            )
            artifacts = ImageReviewGeometryArtifacts(
                geometry={
                    "commandChecksumSha256": geometry_command.command_sha256,
                    "cropperVersion": "board-cell-crops-v19",
                    "expectedGeometryRevision": 0,
                    "expectedResolutionRevision": 0,
                    "positionIndex": 0,
                    "sequenceNumber": 64,
                    "source": "manual_override",
                    "sourceGroup": str(job.id),
                    "sourceImageChecksumSha256": source.checksum_sha256,
                    "sourceImageId": str(source.id),
                    "sourceImageRelativePath": source.relative_path,
                },
                board_relative_path=source.relative_path,
                board_checksum_sha256=source.checksum_sha256,
                cropper_version="board-cell-crops-v19",
                cells=tuple(
                    ImageReviewGeometryCellArtifact(
                        row_index=index // 5,
                        column_index=index % 5,
                        crop_relative_path=f"manual/cell-{index}.png",
                        crop_checksum_sha256=f"{index + 100:064x}",
                    )
                    for index in range(15)
                ),
            )
            prediction = ManualBoardCellSymbolPrediction(
                model_iteration_id=None,
                model_manifest_checksum_sha256=symbol_model.manifest_checksum_sha256,
                model_version=symbol_model.model_version,
                temperature_applied=symbol_model.temperature,
                cells=tuple(
                    {
                        "alternatives": [
                            {
                                "confidence": 1.0,
                                "symbolCode": symbol_model.class_codes[0],
                            }
                        ],
                        "columnIndex": index % 5,
                        "confidence": 1.0,
                        "rowIndex": index // 5,
                        "symbolCode": symbol_model.class_codes[0],
                    }
                    for index in range(15)
                ),
            )
            projection = BoardCellGeometryManualResolutionProjection(
                idempotency_key=uuid4(),
                command=geometry_command,
                command_sha256="4" * 64,
                artifacts=artifacts,
                prediction=prediction,
                model_inference_fingerprint=symbol_model.inference_fingerprint,
                board_confidence=0.73,
            )
            result = repository.materialize_manual_resolution(
                pending.id,
                game_id=game.id,
                import_job_id=job.id,
                expected_manifest_checksum_sha256=manifest.checksum_sha256,
                projection=projection,
                created_at=now,
            )
            assert result is not None and result.created is True
            replay = repository.materialize_manual_resolution(
                pending.id,
                game_id=game.id,
                import_job_id=job.id,
                expected_manifest_checksum_sha256=manifest.checksum_sha256,
                projection=projection,
                created_at=now,
            )
            assert replay is not None and replay.created is False
            assert replay.review_item_id == result.review_item_id
            review_item_id = result.review_item_id

            concurrent_manifest = replace(
                manifest,
                position_index=1,
                sequence_number=65,
            )
            concurrent_pending, _ = repository.defer(
                manifest=concurrent_manifest,
                reason_code=BoardCellGeometryPendingReason.RESIDUAL_TOO_HIGH,
                manifest_relative_path=(
                    f"image-board-cell-processing-v1/{concurrent_manifest.checksum_sha256}.json"
                ),
            )
            session.add(
                RecognizedBoardModel(
                    source_image_id=source.id,
                    position_index=1,
                    sequence_number_raw="65",
                    sequence_number=65,
                    sequence_confidence=1.0,
                    board_geometry={"source": "concurrent-human"},
                    board_relative_path=source.relative_path,
                    board_checksum_sha256=source.checksum_sha256,
                    cells_prediction={"cells": []},
                    board_confidence=1.0,
                    pipeline_fingerprint=PIPELINE,
                    geometry_revision=1,
                    status="corrected",
                    created_at=now,
                )
            )
            session.flush()
            human_wins = repository.materialize_manual_resolution(
                concurrent_pending.id,
                game_id=game.id,
                import_job_id=job.id,
                expected_manifest_checksum_sha256=concurrent_manifest.checksum_sha256,
                projection=projection,
                created_at=now,
            )
            assert human_wins is not None
            assert human_wins.created is False
            assert human_wins.pending.status.value == "superseded"

        with Session(engine) as session:
            pending_row = session.get(ImageBoardGeometryPendingModel, pending.id)
            assert pending_row is not None
            assert pending_row.status == "resolved"
            assert pending_row.resolved_geometry_revision == 1
            board = session.get(RecognizedBoardModel, pending_row.recognized_board_id)
            assert board is not None
            assert board.sequence_number == 64
            assert board.board_confidence == 0.73
            assert board.geometry_revision == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(CellObservationModel)
                    .where(CellObservationModel.recognized_board_id == board.id)
                )
                == 15
            )
            review = session.get(ImageReviewItemModel, review_item_id)
            assert review is not None and review.status == "pending"
            revision = session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.review_item_id == review_item_id
                )
            )
            assert revision is not None and revision.revision == 1
            queue_item = session.get(ImageReviewQueueItemModel, review_item_id)
            assert queue_item is not None and queue_item.status == "pending"
            queue_state = session.get(ImageReviewQueueStateModel, job.id)
            assert queue_state is not None
            assert queue_state.total_count == queue_state.pending_count == 1
    finally:
        engine.dispose()


def test_image_review_queue_projection_backfills_and_tracks_durable_state(
    isolated_image_batch_database: URL,
) -> None:
    config = _migration_config(isolated_image_batch_database)
    command.upgrade(config, "0048_image_page_geometry_overrides")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="review-queue-projection",
                name="Review queue projection",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        later_source = image_store.register_file(
            job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="later.jpg",
            order_index=8,
            registered_at=now,
        )
        earlier_source = image_store.register_file(
            job.id,
            source_checksum_sha256="2" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="earlier.jpg",
            order_index=2,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            later_review_id, later_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=later_source.file_execution_key,
                source_checksum="1" * 64,
                source_name="later.jpg",
                position_index=5,
                sequence_number=10,
                status="pending",
                created_at=now,
            )
            earlier_review_id, _earlier_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=earlier_source.file_execution_key,
                source_checksum="2" * 64,
                source_name="earlier.jpg",
                position_index=7,
                sequence_number=1,
                status="rejected",
                created_at=now,
            )
            session.commit()

        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
        session_factory = create_session_factory(engine)

        with Session(engine, expire_on_commit=False) as session:
            projected = session.scalars(
                select(ImageReviewQueueItemModel)
                .where(ImageReviewQueueItemModel.import_job_id == job.id)
                .order_by(
                    ImageReviewQueueItemModel.source_order_index,
                    ImageReviewQueueItemModel.position_index,
                    ImageReviewQueueItemModel.review_item_id,
                )
            ).all()
            assert [item.review_item_id for item in projected] == [
                earlier_review_id,
                later_review_id,
            ]
            assert [
                (item.source_order_index, item.position_index, item.status) for item in projected
            ] == [(2, 7, "rejected"), (8, 5, "pending")]
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert state is not None
            assert state.queue_version == 1
            assert state.total_count == 2
            assert state.pending_count == 1
            assert state.rejected_count == 1

            earlier_review = session.get(
                ImageReviewItemModel,
                earlier_review_id,
                with_for_update=True,
            )
            later_board = session.get(RecognizedBoardModel, later_board_id)
            assert earlier_review is not None
            assert later_board is not None
            earlier_review.status = "corrected"
            earlier_review.resolved_value = {
                "action": "corrected",
                "sequenceNumber": 1,
                "symbolCodes": ["test"] * 15,
            }
            later_board.sequence_number = 1
            session.commit()

        image_store = SqlAlchemyImageBatchStore(session_factory)
        middle_source = image_store.register_file(
            job.id,
            source_checksum_sha256="3" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="middle.jpg",
            order_index=4,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            middle_review_id, _middle_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=middle_source.file_execution_key,
                source_checksum="3" * 64,
                source_name="middle.jpg",
                position_index=0,
                sequence_number=5,
                status="pending",
                created_at=now,
            )
            session.commit()

        with Session(engine) as session:
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert state is not None
            assert state.queue_version == 2
            assert state.total_count == 3
            assert state.pending_count == 2
            assert state.accepted_count == 0
            assert state.corrected_count == 1
            assert state.rejected_count == 0
            projected = session.scalars(
                select(ImageReviewQueueItemModel)
                .where(ImageReviewQueueItemModel.import_job_id == job.id)
                .order_by(ImageReviewQueueItemModel.source_order_index)
            ).all()
            assert [item.review_item_id for item in projected] == [
                earlier_review_id,
                middle_review_id,
                later_review_id,
            ]
            assert projected[-1].source_order_index == 8
            assert projected[-1].position_index == 5

            operational = OperationalImageReviewService(
                SqlAlchemyOperationalImageReviewRepository(session)
            )
            resumed = operational.list_items(
                game_id=game.id,
                import_job_id=job.id,
                view=ImageReviewView.ALL,
                after_cursor=None,
                before_cursor=None,
                sequence_number=None,
                resume_at_first_pending=True,
                limit=1,
            )
            assert resumed.queue_version == 2
            assert resumed.items[0].id == middle_review_id
            assert resumed.items[0].source_order_index == 4
            assert resumed.previous_cursor is not None
            assert resumed.next_cursor is not None
            after_resumed = operational.list_items(
                game_id=game.id,
                import_job_id=job.id,
                view=ImageReviewView.ALL,
                after_cursor=resumed.next_cursor,
                before_cursor=None,
                sequence_number=None,
                resume_at_first_pending=False,
                limit=1,
            )
            assert after_resumed.items[0].id == later_review_id
            assert after_resumed.items[0].suggested_sequence_number == 1
            topology_cursor = resumed.next_cursor

        with Session(engine) as session:
            immutable_item = session.get(ImageReviewQueueItemModel, middle_review_id)
            assert immutable_item is not None
            immutable_item.source_order_index = 100
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            removable_review = session.get(ImageReviewItemModel, middle_review_id)
            assert removable_review is not None
            session.delete(removable_review)
            session.commit()

        with Session(engine) as session:
            assert session.get(ImageReviewQueueItemModel, middle_review_id) is None
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert state is not None
            assert state.queue_version == 3
            assert state.total_count == 2
            assert state.pending_count == 1
            assert state.corrected_count == 1
            operational = OperationalImageReviewService(
                SqlAlchemyOperationalImageReviewRepository(session)
            )
            with pytest.raises(ImageReviewConflictError) as stale:
                operational.list_items(
                    game_id=game.id,
                    import_job_id=job.id,
                    view=ImageReviewView.ALL,
                    after_cursor=topology_cursor,
                    before_cursor=None,
                    sequence_number=None,
                    resume_at_first_pending=False,
                    limit=1,
                )
            assert stale.value.code == "IMAGE_REVIEW_CURSOR_STALE"
    finally:
        engine.dispose()


def test_review_queue_completes_and_reopens_image_import_job(
    isolated_image_batch_database: URL,
) -> None:
    config = _migration_config(isolated_image_batch_database)
    command.upgrade(config, "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 21, 10, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="review-job-lifecycle",
                name="Review job lifecycle",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            record = session.get(JobModel, job.id)
            assert record is not None
            record.status = JobStatus.WAITING_FOR_REVIEW
            record.stage = "image_pipeline:manual_review"
            session.commit()

        first_registered = image_store.register_file(
            job.id,
            source_checksum_sha256="9" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="review-lifecycle-1.jpg",
            order_index=0,
            registered_at=now,
        )
        second_registered = image_store.register_file(
            job.id,
            source_checksum_sha256="7" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="review-lifecycle-2.jpg",
            order_index=1,
            registered_at=now,
        )
        with Session(engine, expire_on_commit=False) as session:
            first_id, _first_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=first_registered.file_execution_key,
                source_checksum="9" * 64,
                source_name="review-lifecycle-1.jpg",
                position_index=0,
                sequence_number=1,
                status="pending",
                created_at=now,
            )
            second_id, _second_board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=second_registered.file_execution_key,
                source_checksum="7" * 64,
                source_name="review-lifecycle-2.jpg",
                position_index=0,
                sequence_number=2,
                status="pending",
                created_at=now,
            )
            session.commit()

        with Session(engine) as session:
            first = session.get(ImageReviewItemModel, first_id)
            assert first is not None
            first.status = "accepted"
            first.resolved_value = {"action": "accepted", "sequenceNumber": 1}
            first.resolved_by = "lifecycle-test"
            first.resolved_at = now
            first.resolution_revision = 1
            session.commit()

        with Session(engine) as session:
            still_waiting = session.get(JobModel, job.id)
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert still_waiting is not None
            assert state is not None
            assert still_waiting.status is JobStatus.WAITING_FOR_REVIEW
            assert still_waiting.finished_at is None
            assert state.pending_count == 1

            second = session.get(ImageReviewItemModel, second_id)
            assert second is not None
            second.status = "corrected"
            second.resolved_value = {"action": "corrected", "sequenceNumber": 2}
            second.resolved_by = "lifecycle-test"
            second.resolved_at = now + timedelta(seconds=1)
            second.resolution_revision = 1
            session.commit()

        with Session(engine) as session:
            completed = session.get(JobModel, job.id)
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert completed is not None
            assert state is not None
            assert completed.status is JobStatus.COMPLETED
            assert completed.finished_at is not None
            assert state.pending_count == 0

            first = session.get(ImageReviewItemModel, first_id)
            assert first is not None
            first.status = "pending"
            first.resolved_value = null()
            first.resolved_by = None
            first.resolved_at = None
            first.resolution_revision = 2
            session.commit()

        with Session(engine) as session:
            reopened = session.get(JobModel, job.id)
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert reopened is not None
            assert state is not None
            assert reopened.status is JobStatus.WAITING_FOR_REVIEW
            assert reopened.finished_at is None
            assert state.pending_count == 1
    finally:
        engine.dispose()


def test_review_job_completion_migration_backfills_resolved_import(
    isolated_image_batch_database: URL,
) -> None:
    config = _migration_config(isolated_image_batch_database)
    command.upgrade(config, "0052_reviewer_assignment_sessions")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 21, 11, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="review-job-backfill",
                name="Review job backfill",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            record = session.get(JobModel, job.id)
            assert record is not None
            record.status = JobStatus.WAITING_FOR_REVIEW
            record.stage = "image_pipeline:manual_review"
            session.commit()

        registered = image_store.register_file(
            job.id,
            source_checksum_sha256="8" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="resolved-before-upgrade.jpg",
            order_index=0,
            registered_at=now,
        )
        with Session(engine) as session:
            _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=registered.file_execution_key,
                source_checksum="8" * 64,
                source_name="resolved-before-upgrade.jpg",
                position_index=0,
                sequence_number=1,
                status="corrected",
                created_at=now,
            )
            session.commit()
            before_upgrade = session.get(JobModel, job.id)
            assert before_upgrade is not None
            assert before_upgrade.status is JobStatus.WAITING_FOR_REVIEW

        engine.dispose()
        command.upgrade(config, "head")
        engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)

        with Session(engine) as session:
            completed = session.get(JobModel, job.id)
            state = session.get(ImageReviewQueueStateModel, job.id)
            assert completed is not None
            assert state is not None
            assert completed.status is JobStatus.COMPLETED
            assert completed.finished_at is not None
            assert state.total_count == 1
            assert state.pending_count == 0
    finally:
        engine.dispose()


def test_parallel_review_decisions_persist_one_canonical_owner_and_supersede_loser(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 20, 14, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="first-save-wins",
                name="First save wins",
                status=GameStatus.ACTIVE,
            )
            CatalogService(SqlAlchemyCatalogRepository(session)).create_symbol(
                game.id,
                mobile_code=1,
                code="test",
                name="Test",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            repository = SqlAlchemyJobRepository(session)
            jobs = (
                repository.add_job(_image_job(game.id, PIPELINE, now)),
                repository.add_job(_image_job(game.id, PIPELINE, now + timedelta(seconds=1))),
            )
            session.commit()

        review_ids: list[UUID] = []
        for index, job in enumerate(jobs, start=1):
            registered = image_store.register_file(
                job.id,
                source_checksum_sha256=f"{index}" * 64,
                pipeline_fingerprint=PIPELINE,
                source_relative_path=f"source-{index}.jpg",
                order_index=0,
                registered_at=now,
            )
            with Session(engine) as session:
                review_id, _board_id = _add_review_projection_source(
                    session,
                    job_id=job.id,
                    file_execution_key=registered.file_execution_key,
                    source_checksum=f"{index}" * 64,
                    source_name=f"source-{index}.jpg",
                    position_index=0,
                    sequence_number=1,
                    status="pending",
                    created_at=now,
                )
                review_ids.append(review_id)
                session.commit()

        ready = Barrier(2)

        def resolve(review_id: UUID, job_id: UUID) -> tuple[UUID, str, str]:
            with Session(engine, expire_on_commit=False) as session:
                service = OperationalImageReviewService(
                    SqlAlchemyOperationalImageReviewRepository(session)
                )
                current = service.get_item(
                    review_id,
                    game_id=game.id,
                    import_job_id=job_id,
                )
                cells = tuple(
                    ImageReviewResolutionCell(
                        cell_index=cell.cell_index,
                        crop_sample_id=cell.crop_sample_id,
                        symbol_code="test",
                    )
                    for cell in current.cells
                )
                ready.wait(timeout=10)
                resolved, event, created = service.resolve_item(
                    review_id,
                    game_id=game.id,
                    import_job_id=job_id,
                    idempotency_key=uuid4(),
                    expected_revision=0,
                    action=ImageReviewAction.ACCEPTED,
                    sequence_number=1,
                    geometry_revision=0,
                    cells=cells,
                    rejection_reason=None,
                    resolved_by=f"reviewer-{job_id}",
                )
                assert created is True
                queue_version, counts = service.queue_snapshot(
                    game_id=game.id,
                    import_job_id=job_id,
                )
                assert queue_version == 1
                assert counts.total == 1
                assert counts.accepted + counts.superseded == 1
                session.commit()
                return resolved.id, resolved.status, event.action

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(
                executor.map(
                    lambda pair: resolve(*pair),
                    zip(review_ids, (jobs[0].id, jobs[1].id), strict=True),
                )
            )

        assert sorted(status for _item_id, status, _action in results) == [
            "accepted",
            "superseded",
        ]
        assert sorted(action for _item_id, _status, action in results) == [
            "accepted",
            "superseded",
        ]

        with Session(engine) as session:
            canonical = session.scalar(
                select(ImageSequenceCanonicalModel).where(
                    ImageSequenceCanonicalModel.game_id == game.id,
                    ImageSequenceCanonicalModel.sequence_number == 1,
                )
            )
            assert canonical is not None
            assert canonical.review_item_id in review_ids
            assert (
                session.scalar(select(func.count()).select_from(ImageSequenceCanonicalModel)) == 1
            )
            losing_id = next(
                review_id for review_id in review_ids if review_id != canonical.review_item_id
            )
            loser = session.get(ImageReviewItemModel, losing_id)
            assert loser is not None
            assert loser.status == "superseded"
            assert loser.resolution_revision == 2
            assert loser.resolved_value is not None
            assert loser.resolved_value["canonicalReviewItemId"] == str(canonical.review_item_id)
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSequenceAlternativeModel)
                    .where(ImageSequenceAlternativeModel.game_id == game.id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageReviewResolutionEventModel)
                    .where(ImageReviewResolutionEventModel.action == "superseded")
                )
                == 2
            )
            assert session.scalar(select(func.count()).select_from(ImageLayoutStagingRowModel)) == 1
            states = session.scalars(
                select(ImageReviewQueueStateModel).where(
                    ImageReviewQueueStateModel.import_job_id.in_((jobs[0].id, jobs[1].id))
                )
            ).all()
            assert len(states) == 2
            assert all(state.queue_version == 1 and state.total_count == 1 for state in states)
            assert sum(state.accepted_count for state in states) == 1
            assert sum(state.superseded_count for state in states) == 1
            assert sum(state.pending_count for state in states) == 0

            operational_repository = SqlAlchemyOperationalImageReviewRepository(session)
            blocked_geometry = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(1, 1),
                    ImageReviewGeometryPoint(91, 1),
                    ImageReviewGeometryPoint(91, 91),
                    ImageReviewGeometryPoint(1, 91),
                ),
                expected_geometry_revision=0,
                expected_resolution_revision=loser.resolution_revision,
                corrected_by="late-reviewer",
            )
            with pytest.raises(ImageReviewConflictError) as protected:
                operational_repository.save_geometry_revision(
                    review_item_id=losing_id,
                    game_id=game.id,
                    import_job_id=next(
                        job.id
                        for job, review_id in zip(jobs, review_ids, strict=True)
                        if review_id == losing_id
                    ),
                    idempotency_key=uuid4(),
                    command=blocked_geometry,
                    artifacts=ImageReviewGeometryArtifacts(
                        geometry={"source": "blocked-test"},
                        board_relative_path="blocked/board.png",
                        board_checksum_sha256="f" * 64,
                        cropper_version="blocked-test",
                        cells=tuple(
                            ImageReviewGeometryCellArtifact(
                                row_index=index // 5,
                                column_index=index % 5,
                                crop_relative_path=f"blocked/cell-{index}.png",
                                crop_checksum_sha256=f"{index + 500:064x}",
                            )
                            for index in range(15)
                        ),
                    ),
                    created_at=now + timedelta(minutes=1),
                )
            assert protected.value.code == "IMAGE_REVIEW_SUPERSEDED"
    finally:
        engine.dispose()


def test_pending_sequence_owner_is_always_the_newest_import(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    now = datetime(2026, 8, 27, 8, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="pending-sequence-owner",
                name="Pending sequence owner",
                status=GameStatus.ACTIVE,
            )
            older_job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, "1" * 64, now))
            newer_job = SqlAlchemyJobRepository(session).add_job(
                _image_job(game.id, "2" * 64, now + timedelta(seconds=1))
            )
            newest_job = SqlAlchemyJobRepository(session).add_job(
                _image_job(game.id, "3" * 64, now + timedelta(seconds=2))
            )
            session.commit()

        executions = {
            job.id: image_store.register_file(
                job.id,
                source_checksum_sha256=checksum * 64,
                pipeline_fingerprint=checksum * 64,
                source_relative_path=f"source-{checksum}.jpg",
                order_index=0,
                registered_at=job.created_at,
            )
            for job, checksum in (
                (older_job, "1"),
                (newer_job, "2"),
                (newest_job, "3"),
            )
        }

        with Session(engine, expire_on_commit=False) as session, session.begin():
            jobs = {
                job_id: session.get(JobModel, job_id)
                for job_id in (older_job.id, newer_job.id, newest_job.id)
            }

            def create_candidate(job: Job, checksum: str) -> ImageReviewItemModel:
                job_record = jobs[job.id]
                assert job_record is not None
                source = SourceImageModel(
                    import_job_id=job.id,
                    file_execution_key=executions[job.id].file_execution_key,
                    relative_path=f"source-{checksum}.jpg",
                    checksum_sha256=checksum * 64,
                    width=1920,
                    height=1080,
                    status="waiting_for_review",
                    created_at=job.created_at,
                )
                session.add(source)
                session.flush()
                board = RecognizedBoardModel(
                    source_image_id=source.id,
                    position_index=0,
                    sequence_number_raw="10",
                    sequence_number=10,
                    sequence_confidence=1.0,
                    board_geometry={"source": "pending-owner-test"},
                    board_relative_path=f"board-{checksum}.png",
                    board_checksum_sha256=checksum * 64,
                    cells_prediction={"cells": []},
                    board_confidence=1.0,
                    pipeline_fingerprint=checksum * 64,
                    status="pending_review",
                    created_at=job.created_at,
                )
                session.add(board)
                session.flush()
                review, _changed = create_owned_pending_review_item(
                    session,
                    board=board,
                    game_id=game.id,
                    import_job=job_record,
                    snapshot={"sequenceNumber": 10},
                    created_at=job.created_at,
                )
                return review

            newer_review = create_candidate(newer_job, "2")
            older_review = create_candidate(older_job, "1")
            newest_review = create_candidate(newest_job, "3")

        with Session(engine) as session:
            reviews = {
                review.id: session.get(ImageReviewItemModel, review.id)
                for review in (older_review, newer_review, newest_review)
            }
            assert reviews[older_review.id].status == "superseded"  # type: ignore[union-attr]
            assert reviews[newer_review.id].status == "superseded"  # type: ignore[union-attr]
            assert reviews[newest_review.id].status == "pending"  # type: ignore[union-attr]
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageReviewItemModel)
                    .where(
                        ImageReviewItemModel.game_id == game.id,
                        ImageReviewItemModel.sequence_number == 10,
                        ImageReviewItemModel.status == "pending",
                    )
                )
                == 1
            )
    finally:
        engine.dispose()


def test_image_batch_store_reuses_execution_and_fences_checkpoint(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    worker_store = SqlAlchemyWorkerJobStore(session_factory)
    now = datetime(2026, 7, 29, 18, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="image-batch-game",
                name="Image batch game",
                status=GameStatus.ACTIVE,
            )
            CatalogService(SqlAlchemyCatalogRepository(session)).create_symbol(
                game.id,
                mobile_code=1,
                code="lemon",
                name="Lemon",
                image_path=None,
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
            repository = SqlAlchemyJobRepository(session)
            first_job = repository.add_job(_image_job(game.id, PIPELINE, now))
            second_job = repository.add_job(
                _image_job(game.id, PIPELINE, now + timedelta(seconds=1))
            )
            changed_job = repository.add_job(
                _image_job(game.id, OTHER_PIPELINE, now + timedelta(seconds=2))
            )
            session.commit()

        first = image_store.register_file(
            first_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="first/page.jpg",
            order_index=0,
            registered_at=now,
        )
        changed = image_store.register_file(
            changed_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=OTHER_PIPELINE,
            source_relative_path="renamed/page.jpg",
            order_index=0,
            registered_at=now,
        )

        assert changed.file_execution_key != first.file_execution_key
        assert (
            image_store.count_job_files(
                first_job.id,
                pipeline_fingerprint=PIPELINE,
            )
            == 1
        )

        claimed = worker_store.claim_next(
            worker_id="image-worker",
            worker_version="worker-v5",
            lease_duration=timedelta(seconds=60),
            claimed_at=now + timedelta(seconds=2),
        )
        assert claimed is not None
        assert claimed.id == first_job.id
        assert claimed.lease_token is not None

        advanced = advance_file_checkpoint(
            first.checkpoint_payload,
            ImageStageExecutionResult.COMPLETED,
        )
        persisted = image_store.save_file_checkpoint(
            first_job.id,
            lease_token=claimed.lease_token,
            expected_checkpoint=first.checkpoint_payload,
            checkpoint_payload=advanced,
            checkpointed_at=now + timedelta(seconds=3),
        )
        assert persisted.checkpoint_payload["completedStages"] == ["discovery"]

        with pytest.raises(ImageOrchestrationStoreError) as stale:
            image_store.save_file_checkpoint(
                first_job.id,
                lease_token=claimed.lease_token,
                expected_checkpoint=first.checkpoint_payload,
                checkpoint_payload=advanced,
                checkpointed_at=now + timedelta(seconds=4),
            )
        assert stale.value.code == "IMAGE_FILE_CHECKPOINT_STALE"

        current = persisted
        while current.checkpoint_payload["nextStage"] is not None:
            advanced = advance_file_checkpoint(
                current.checkpoint_payload,
                ImageStageExecutionResult.COMPLETED,
            )
            current = image_store.save_file_checkpoint(
                first_job.id,
                lease_token=claimed.lease_token,
                expected_checkpoint=current.checkpoint_payload,
                checkpoint_payload=advanced,
                checkpointed_at=now + timedelta(seconds=5),
            )
        assert current.status == "completed"

        reused = image_store.register_file(
            second_job.id,
            source_checksum_sha256="1" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="renamed/page.jpg",
            order_index=0,
            registered_at=now + timedelta(seconds=6),
        )
        assert reused.file_execution_key == first.file_execution_key
        assert reused.status == "processing"
        assert reused.checkpoint_payload["nextStage"] == "discovery"
        assert reused.checkpoint_payload["completedStages"] == []

        with Session(engine, expire_on_commit=False) as session:
            source = SourceImageModel(
                import_job_id=second_job.id,
                file_execution_key=reused.file_execution_key,
                relative_path="renamed/page.jpg",
                checksum_sha256="1" * 64,
                width=100,
                height=100,
                status="waiting_for_review",
                created_at=now,
            )
            session.add(source)
            session.flush()
            board = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=0,
                sequence_number_raw="1",
                sequence_number=1,
                sequence_confidence=0.5,
                board_geometry={"quad": []},
                board_relative_path="crops/board.png",
                board_checksum_sha256="9" * 64,
                cells_prediction={"cells": []},
                board_confidence=0.5,
                pipeline_fingerprint=PIPELINE,
                status="pending_review",
                created_at=now,
            )
            session.add(board)
            session.flush()
            review = ImageReviewItemModel(
                recognized_board_id=board.id,
                status="pending",
                snapshot={"sequenceNumber": 1},
                resolution_revision=0,
                created_at=now,
            )
            session.add(review)
            session.add_all(
                CellObservationModel(
                    recognized_board_id=board.id,
                    row_index=index // 5,
                    column_index=index % 5,
                    crop_relative_path=f"crops/board-{index}.png",
                    crop_checksum_sha256=f"{index + 1:064x}",
                    cropper_version="cropper-v1",
                    prediction={
                        "symbolCode": "lemon",
                        "confidence": 1.0,
                        "alternatives": [{"symbolCode": "lemon", "confidence": 1.0}],
                    },
                    created_at=now,
                )
                for index in range(15)
            )
            session.commit()

        with Session(engine) as session:
            queue_item = session.get(ImageReviewQueueItemModel, review.id)
            queue_state = session.get(ImageReviewQueueStateModel, second_job.id)
            assert queue_item is not None
            assert queue_item.import_job_id == second_job.id
            assert queue_item.source_order_index == 0
            assert queue_item.position_index == 0
            assert queue_item.status == "pending"
            assert queue_state is not None
            assert queue_state.queue_version == 1
            assert queue_state.total_count == 1
            assert queue_state.pending_count == 1

        pipeline_store = SqlAlchemyImagePipelineStore(session_factory)
        idempotency_key = uuid4()
        pipeline_store.resolve_board(
            review.id,
            expected_revision=0,
            action="rejected",
            sequence_number=None,
            symbol_codes=(),
            resolved_by="local-admin",
            resolved_at=now,
            idempotency_key=idempotency_key,
            reason="unreadable",
        )
        pipeline_store.resolve_board(
            review.id,
            expected_revision=0,
            action="rejected",
            sequence_number=None,
            symbol_codes=(),
            resolved_by="local-admin",
            resolved_at=now,
            idempotency_key=idempotency_key,
            reason="unreadable",
        )
        with pytest.raises(ImagePipelineStoreError) as idempotency_conflict:
            pipeline_store.resolve_board(
                review.id,
                expected_revision=0,
                action="rejected",
                sequence_number=None,
                symbol_codes=(),
                resolved_by="local-admin",
                resolved_at=now,
                idempotency_key=idempotency_key,
                reason="another reason",
            )
        assert idempotency_conflict.value.code == "IMAGE_REVIEW_IDEMPOTENCY_CONFLICT"

        with Session(engine, expire_on_commit=False) as session:
            operational_repository = SqlAlchemyOperationalImageReviewRepository(session)
            operational = OperationalImageReviewService(operational_repository)
            current = operational.get_item(
                review.id,
                game_id=game.id,
                import_job_id=second_job.id,
            )
            correction_key = uuid4()
            cells = tuple(
                ImageReviewResolutionCell(
                    cell_index=cell.cell_index,
                    crop_sample_id=cell.crop_sample_id,
                    symbol_code="lemon",
                )
                for cell in current.cells
            )
            corrected, first_event, created = operational.resolve_item(
                review.id,
                game_id=game.id,
                import_job_id=second_job.id,
                idempotency_key=correction_key,
                expected_revision=1,
                action=ImageReviewAction.CORRECTED,
                sequence_number=2,
                geometry_revision=0,
                cells=cells,
                rejection_reason=None,
                resolved_by="local-admin",
            )
            assert created is True
            assert corrected.resolution_revision == 2
            assert first_event.revision == 2
            retried, retry_event, retry_created = operational.resolve_item(
                review.id,
                game_id=game.id,
                import_job_id=second_job.id,
                idempotency_key=correction_key,
                expected_revision=1,
                action=ImageReviewAction.CORRECTED,
                sequence_number=2,
                geometry_revision=0,
                cells=cells,
                rejection_reason=None,
                resolved_by="local-admin",
            )
            assert retry_created is False
            assert retry_event.id == first_event.id
            assert retried.resolution_revision == 2
            corrected_again, _event, created_again = operational.resolve_item(
                review.id,
                game_id=game.id,
                import_job_id=second_job.id,
                idempotency_key=uuid4(),
                expected_revision=2,
                action=ImageReviewAction.CORRECTED,
                sequence_number=3,
                geometry_revision=0,
                cells=cells,
                rejection_reason=None,
                resolved_by="local-admin",
            )
            assert created_again is True
            assert corrected_again.resolution_revision == 3
            geometry_key = uuid4()
            geometry_command = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(1, 1),
                    ImageReviewGeometryPoint(91, 1),
                    ImageReviewGeometryPoint(91, 91),
                    ImageReviewGeometryPoint(1, 91),
                ),
                expected_geometry_revision=0,
                expected_resolution_revision=3,
                corrected_by="local-admin",
            )
            geometry_artifacts = ImageReviewGeometryArtifacts(
                geometry={
                    "source": "manual_review",
                    "sourceQuad": [
                        {"x": 1, "y": 1},
                        {"x": 91, "y": 1},
                        {"x": 91, "y": 91},
                        {"x": 1, "y": 91},
                    ],
                },
                board_relative_path="image-review-geometry/board.png",
                board_checksum_sha256="8" * 64,
                cropper_version="manual-review-geometry-v1",
                cells=tuple(
                    ImageReviewGeometryCellArtifact(
                        row_index=index // 5,
                        column_index=index % 5,
                        crop_relative_path=f"image-review-geometry/cell-{index}.png",
                        crop_checksum_sha256=f"{index + 100:064x}",
                    )
                    for index in range(15)
                ),
            )
            reopened, geometry_revision, geometry_created = (
                operational_repository.save_geometry_revision(
                    review_item_id=review.id,
                    game_id=game.id,
                    import_job_id=second_job.id,
                    idempotency_key=geometry_key,
                    command=geometry_command,
                    artifacts=geometry_artifacts,
                    created_at=now + timedelta(seconds=10),
                )
            )
            assert geometry_created is True
            assert geometry_revision.revision == 1
            assert reopened.status == "pending"
            assert reopened.geometry_revision == 1
            assert reopened.resolution_revision == 4
            assert all(
                current_cell.crop_sample_id != reopened.cells[index].crop_sample_id
                for index, current_cell in enumerate(corrected_again.cells)
            )
            session.commit()

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ImageFileExecutionModel)) == 2
            assert session.scalar(select(func.count()).select_from(ImageImportJobFileModel)) == 3
            assert (
                session.scalar(select(func.count()).select_from(ImageReviewResolutionEventModel))
                == 4
            )
            assert session.scalar(select(func.count()).select_from(ImageLayoutStagingRowModel)) == 0
            assert (
                session.scalar(select(func.count()).select_from(ImageBoardGeometryRevisionModel))
                == 1
            )
            queue_item = session.get(ImageReviewQueueItemModel, review.id)
            queue_state = session.get(ImageReviewQueueStateModel, second_job.id)
            assert queue_item is not None
            assert queue_item.status == "pending"
            assert queue_item.source_order_index == 0
            assert queue_item.position_index == 0
            assert queue_state is not None
            assert queue_state.queue_version == 1
            assert queue_state.total_count == 1
            assert queue_state.pending_count == 1
            assert queue_state.accepted_count == 0
            assert queue_state.corrected_count == 0
            assert queue_state.rejected_count == 0
    finally:
        engine.dispose()


def test_image_job_operations_aggregate_and_retry_failed_stage(
    isolated_image_batch_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    image_store = SqlAlchemyImageBatchStore(session_factory)
    worker_store = SqlAlchemyWorkerJobStore(session_factory)
    now = datetime(2026, 7, 29, 21, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="image-operations-game",
                name="Image operations game",
                status=GameStatus.ACTIVE,
            )
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
            session.commit()

        registered = image_store.register_file(
            job.id,
            source_checksum_sha256="4" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="batch/page-004.jpg",
            order_index=0,
            registered_at=now,
        )
        claimed = worker_store.claim_next(
            worker_id="image-operations-worker",
            worker_version="worker-v7",
            lease_duration=timedelta(seconds=60),
            claimed_at=now + timedelta(seconds=1),
        )
        assert claimed is not None
        assert claimed.lease_token is not None

        failed_at = now + timedelta(seconds=11)
        image_store.fail_file(
            job.id,
            lease_token=claimed.lease_token,
            expected_checkpoint=registered.checkpoint_payload,
            failed_stage="discovery",
            error_code="IMAGE_DISCOVERY_FAILED",
            error_message="Discovery failed.",
            failed_at=failed_at,
        )
        worker_store.fail(
            job.id,
            lease_token=claimed.lease_token,
            error_code="IMAGE_BATCH_FAILED",
            error_message="One file failed.",
            failed_at=failed_at,
        )

        with Session(engine, expire_on_commit=False) as session, session.begin():
            repository = SqlAlchemyImageJobOperationsRepository(session)
            before = repository.get_operations(job.id, file_limit=10)
            assert before.total == 1
            assert before.failed == 1
            assert before.elapsed_seconds == 10
            assert before.files_per_minute == 6
            assert before.stage_counts[0].stage == "discovery"
            assert before.files[0].file_execution_key == registered.file_execution_key

            diagnostic = repository.diagnostic_snapshot(job.id, error_limit=10)
            assert diagnostic.failed == 1
            assert diagnostic.truncated is False
            assert diagnostic.failures[0].file_execution_key == (registered.file_execution_key)
            assert diagnostic.failures[0].source_relative_path == ("batch/page-004.jpg")
            assert diagnostic.failures[0].error_code == "IMAGE_DISCOVERY_FAILED"

            after = repository.retry_file(
                job.id,
                file_execution_key=registered.file_execution_key,
                expected_stage="discovery",
                retried_at=now + timedelta(seconds=12),
                file_limit=10,
            )
            assert after.failed == 0
            assert after.files[0].file_execution_key == registered.file_execution_key
            assert after.files[0].status == "processing"
            assert after.files[0].next_stage == "discovery"
            assert after.files[0].retry_count == 1
            refreshed_job = session.get(JobModel, job.id)
            assert refreshed_job is not None
            assert refreshed_job.status is JobStatus.CREATED
            assert refreshed_job.error_code is None
            assert refreshed_job.finished_at is None
    finally:
        engine.dispose()


def test_pending_reinference_excludes_cancelled_imports(
    isolated_image_batch_database: URL,
    tmp_path: Path,
) -> None:
    command.upgrade(_migration_config(isolated_image_batch_database), "head")
    engine = create_engine(isolated_image_batch_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 8, 20, 22, tzinfo=UTC)

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code="pending-reinference-scope",
                name="Pending reinference scope",
                status=GameStatus.ACTIVE,
            )
            repository = SqlAlchemyJobRepository(session)
            active_job = repository.add_job(_image_job(game.id, PIPELINE, now))
            cancelled_job = repository.add_job(
                _image_job(game.id, PIPELINE, now + timedelta(seconds=1))
            )
            active_record = session.get(JobModel, active_job.id)
            cancelled_record = session.get(JobModel, cancelled_job.id)
            assert active_record is not None
            assert cancelled_record is not None
            active_record.status = JobStatus.WAITING_FOR_REVIEW
            cancelled_record.status = JobStatus.CANCELLED

            for index, job in enumerate((active_job, cancelled_job), start=1):
                file_execution_key = f"{index:064x}"
                session.add(
                    ImageFileExecutionModel(
                        file_execution_key=file_execution_key,
                        source_checksum_sha256=f"{index + 10:064x}",
                        pipeline_fingerprint=PIPELINE,
                        checkpoint_payload={"schemaVersion": 1},
                        status="waiting_for_review",
                        review_required=True,
                        created_at=now,
                    )
                )
                session.flush()
                session.add(
                    ImageImportJobFileModel(
                        job_id=job.id,
                        file_execution_key=file_execution_key,
                        order_index=0,
                        source_relative_path=f"scope-{index}.jpg",
                        workflow_checkpoint_payload={"schemaVersion": 1},
                        workflow_status="waiting_for_review",
                        review_required=True,
                        created_at=now,
                    )
                )
                session.flush()
                _add_review_projection_source(
                    session,
                    job_id=job.id,
                    file_execution_key=file_execution_key,
                    source_checksum=f"{index + 10:064x}",
                    source_name=f"scope-{index}.jpg",
                    position_index=0,
                    sequence_number=index,
                    status="pending",
                    created_at=now,
                )
            session.commit()

        with Session(engine) as session:
            review_repository = SqlAlchemyOperationalImageReviewRepository(session)
            preview = review_repository.pending_grid_reinference_preview(
                game.id,
                geometry_version="board-cell-geometry-v19-test",
                cropper_version="board-cell-crops-v19-test",
                audit_report_checksum_sha256="a" * 64,
            )
            assert review_repository.canonical_pending_count(game.id) == 1
            assert preview.pending_board_count == 1
            assert preview.recalculable_board_count == 1
            assert preview.pending_source_count == 1

        grid_rows = PendingGridReinferenceHandler(session_factory, tmp_path)._pending_v19_rows(
            game.id
        )
        symbol_rows = PendingSymbolReinferenceHandler(
            session_factory,
            tmp_path,
            REPOSITORY_ROOT,
        )._pending_rows(game.id)
        assert [row.import_job_id for row in grid_rows] == [active_job.id]
        assert [row[2].import_job_id for row in symbol_rows] == [active_job.id]
    finally:
        engine.dispose()
