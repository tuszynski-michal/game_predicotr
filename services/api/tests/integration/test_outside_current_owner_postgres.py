"""A partial V2 board without a search document remains actionable after reconnect."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
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
    ImageBoardSearchFastDocumentModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import Engine, delete, func, select, text, update
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_symbol_source_visibility_migration import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


def test_outside_decisions_without_fast_document_persist_across_sessions(database: Engine) -> None:  # noqa: F811
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", database.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(config, "0127_symbol_review_bulk_filter_scope")
    sessions = create_session_factory(database)
    now = datetime.now(UTC)
    with sessions() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code="outside-owner", name="Outside owner", status=GameStatus.ACTIVE
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
    store = SqlAlchemyImageBatchStore(sessions)
    execution = store.register_file(
        job.id,
        source_checksum_sha256="8" * 64,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="outside-test.png",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(game.id), sessions() as session:
        review_id, board_id = _add_review_projection_source(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
            source_checksum="8" * 64,
            source_name="outside-test.png",
            position_index=0,
            sequence_number=62440,
            status="pending",
            created_at=now,
        )
        session.get(JobModel, job.id).status = JobStatus.WAITING_FOR_REVIEW
        session.get(RecognizedBoardModel, board_id).board_geometry = {
            "quad": [
                {"x": 10, "y": 10},
                {"x": 110, "y": 10},
                {"x": 110, "y": 70},
                {"x": 10, "y": 70},
            ]
        }
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game.id)
        session.commit()
    with game_storage_scope(game.id), sessions() as session:
        repository = SqlAlchemyImageSymbolReviewRepository(session)
        repository.start_or_resume_backfill(game.id)
        for _ in range(3):
            report = repository.backfill_next_batch(game.id, batch_size=20)
            if report.report.status == "ready":
                break
        assert report.report.status == "ready"
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == review_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        assert len(cells) == 15
        outside = cells[0]
        outside_id = outside.id
        second_outside_id = cells[1].id
        # Historical ORM None was JSON null, which must be cleared to SQL NULL.
        session.execute(
            update(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.id == outside_id)
            .values(render_spec=text("'null'::jsonb"))
        )
        session.expire_all()
        board = session.get(RecognizedBoardModel, board_id)
        board.completeness_status = "pending_partial"
        board.unavailable_cell_indices = [0, 1]
        board.geometry_qualification = GeometryQualification(
            "pending_partial",
            (0, 1),
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=(0, 1),
        ).to_dict()
        board.board_geometry = {
            "cells": [
                {
                    "rowIndex": index // 5,
                    "columnIndex": index % 5,
                    "sourceQuad": [
                        {"x": x, "y": y}
                        for x, y in (
                            ((-20, 10), (-10, 10), (-10, 20), (-20, 20))
                            if index in (0, 1)
                            else ((10, 10), (20, 10), (20, 20), (10, 20))
                        )
                    ],
                }
                for index in range(15)
            ]
        }
        coordinator = SymbolCellReviewWriteThroughCoordinator(session)
        assert coordinator.synchronize_after_geometry_change(
            game_id=game.id, review_item_id=review_id
        )
        session.flush()
        assert not coordinator.synchronize_for_backfill_reconciliation(
            game_id=game.id, review_item_id=review_id
        )
        session.execute(
            delete(ImageBoardSearchFastDocumentModel).where(
                ImageBoardSearchFastDocumentModel.review_item_id == review_id
            )
        )
        session.flush()
        repository.start_count_rebuild(game.id)
        for _ in range(3):
            if repository.rebuild_count_projection_next_batch(game.id, batch_size=20):
                break
        session.commit()
    with game_storage_scope(game.id), sessions() as session:
        query = SqlAlchemySymbolCellReviewQueryRepository(session)
        review_filter = SymbolCellReviewListFilter(
            game_id=game.id,
            symbol_id=None,
            state=SymbolCellReviewFilterState.ALL,
            outside_only=True,
            uses_current_projection=True,
            storage_generation=2,
        )
        page = query.list_items(
            review_filter=review_filter, after_key=None, before_key=None, limit=10
        )
        assert [item.cell_review_id for item in page.items] == [outside_id, second_outside_id]
        current = session.get(ImageSymbolReviewCellModel, outside_id)
        service = SymbolCellReviewMutationService(
            SqlAlchemySymbolCellReviewMutationRepository(session)
        )
        service.reassign(
            game_id=game.id,
            cell_review_id=outside_id,
            expected_revision=current.revision,
            expected_geometry_revision=current.geometry_revision,
            expected_crop_sample_id=None,
            expected_crop_checksum_sha256=None,
            target_symbol_id=symbol.id,
            actor="test",
        )
        session.commit()
    with game_storage_scope(game.id), sessions() as session:
        current = session.get(ImageSymbolReviewCellModel, outside_id)
        assert current.assigned_symbol_id == symbol.id
        assert (
            current.source_visibility == "outside" and current.approved_crop_checksum_sha256 is None
        )
        assert session.get(RecognizedBoardModel, board_id).completeness_status == "pending_partial"
        service = SymbolCellReviewMutationService(
            SqlAlchemySymbolCellReviewMutationRepository(session)
        )
        service.mark_unreadable(
            game_id=game.id,
            cell_review_id=outside_id,
            expected_revision=current.revision,
            expected_geometry_revision=current.geometry_revision,
            expected_crop_sample_id=None,
            expected_crop_checksum_sha256=None,
            actor="test",
        )
        session.commit()
    with game_storage_scope(game.id), sessions() as session:
        detail = SqlAlchemyUnreadableBoardReviewRepository(session).get_board(
            game_id=game.id, review_item_id=review_id
        )
        assert detail is not None and len(detail.cells) == 15
        current = session.get(ImageSymbolReviewCellModel, outside_id)
        assert current.quality_issue == "unreadable" and current.source_visibility == "outside"
        assert current.crop_sample_id is None and current.approved_crop_checksum_sha256 is None
        assert current.assigned_symbol_id == symbol.id
        state = session.get(ImageSymbolReviewStateModel, game.id)
        operation, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game.id,
            request=SymbolCellReviewBulkRequest(
                action=SymbolCellReviewAction.REASSIGN,
                target_symbol_id=symbol.id,
                explicit_targets=None,
                filter_selection=SymbolCellReviewBulkFilterSelection(
                    symbol_id=None,
                    outside_only=True,
                    state=SymbolCellReviewFilterState.ALL,
                    catalog_revision=state.catalog_revision,
                ),
                actor="test-bulk",
            ),
            idempotency_key=uuid4(),
        )
        assert created and operation.target_count == 1
        bulk_job = SqlAlchemyJobRepository(session).get_job(operation.job_id)
        session.commit()
    for _ in range(2):
        with game_storage_scope(game.id):
            progress = SqlAlchemySymbolCellReviewBulkOperationWorker(sessions).process_next_batch(
                job=bulk_job,
                max_boards=1,
            )
            assert not progress.has_pending_targets
            assert progress.operation.applied_count == 1
            assert progress.operation.failed_count == progress.operation.conflict_count == 0
    with game_storage_scope(game.id), sessions() as session:
        current = session.get(ImageSymbolReviewCellModel, second_outside_id)
        assert current.assigned_symbol_id == symbol.id and current.source_visibility == "outside"
        assert current.approved_crop_checksum_sha256 is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImageSymbolReviewEventModel)
                .where(ImageSymbolReviewEventModel.operation_id == operation.id)
            )
            == 1
        )
