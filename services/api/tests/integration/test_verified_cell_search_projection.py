"""D-462: verified cells feed board search immediately (PostgreSQL)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
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
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardSearchFastDocumentModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_verified_cell_test"
PIPELINE = "a" * 64
IN_FRAME_QUAD = [
    {"x": 100, "y": 100},
    {"x": 600, "y": 100},
    {"x": 600, "y": 400},
    {"x": 100, "y": 400},
]

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
def verified_cell_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    identifier = f'"{TEST_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield _database_url(TEST_DATABASE_NAME)
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _add_pending_board(
    session: Session,
    *,
    job_id: UUID,
    file_execution_key: str,
    created_at: datetime,
) -> UUID:
    """One pending 3x5 board whose model predicts `first` everywhere."""

    job = session.get(JobModel, job_id)
    assert job is not None and job.game_id is not None
    source = SourceImageModel(
        import_job_id=job_id,
        file_execution_key=file_execution_key,
        relative_path="verified-cells.jpg",
        checksum_sha256="7" * 64,
        width=1920,
        height=1080,
        status="waiting_for_review",
        created_at=created_at,
    )
    session.add(source)
    session.flush()
    board = RecognizedBoardModel(
        source_image_id=source.id,
        position_index=0,
        sequence_number_raw="1",
        sequence_number=1,
        sequence_confidence=1.0,
        board_geometry={"source": "verified-cell-test", "quad": IN_FRAME_QUAD},
        board_relative_path="crops/verified-cells.png",
        board_checksum_sha256=f"{1:064x}",
        cells_prediction={"cells": []},
        board_confidence=1.0,
        pipeline_fingerprint=PIPELINE,
        status="pending_review",
        created_at=created_at,
    )
    session.add(board)
    session.flush()
    review = ImageReviewItemModel(
        game_id=job.game_id,
        import_job_id=job.id,
        sequence_number=1,
        recognized_board_id=board.id,
        status="pending",
        snapshot={"sequenceNumber": 1},
        resolution_revision=0,
        created_at=created_at,
    )
    session.add(review)
    session.flush()
    session.add_all(
        CellObservationModel(
            recognized_board_id=board.id,
            row_index=index // 5,
            column_index=index % 5,
            crop_relative_path=f"crops/verified-cells-{index}.png",
            crop_checksum_sha256=f"{100 + index:064x}",
            cropper_version="verified-cell-cropper",
            prediction={
                "symbolCode": "first",
                "confidence": 0.9,
                "alternatives": [{"symbolCode": "second", "confidence": 0.1}],
            },
            created_at=created_at,
        )
        for index in range(15)
    )
    return review.id


def _document_codes(session: Session, game_id: UUID) -> list[int | None]:
    document = session.scalar(
        select(ImageBoardSearchFastDocumentModel).where(
            ImageBoardSearchFastDocumentModel.game_id == game_id,
            ImageBoardSearchFastDocumentModel.sequence_number == 1,
        )
    )
    assert document is not None
    assert document.status == "pending"
    return list(document.primary_symbol_mobile_codes)


def _cells(session: Session, review_item_id: UUID) -> list[ImageSymbolReviewCellModel]:
    return list(
        session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == review_item_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        )
    )


@dataclass(frozen=True)
class _Seed:
    game_id: UUID
    job_id: UUID
    review_item_id: UUID
    second_symbol_id: UUID


def _seed_pending_board(session_factory: sessionmaker[Session], now: datetime) -> _Seed:
    """A ready game with one pending board whose model predicts `first`."""

    with session_factory() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code="verified-cells",
            name="Verified cells",
            status=GameStatus.ACTIVE,
        )
        for mobile_code, code in ((1, "first"), (2, "second")):
            catalog.create_symbol(
                game.id,
                mobile_code=mobile_code,
                code=code,
                name=code.title(),
                image_path=None,
                is_wildcard=False,
                display_order=mobile_code,
                status=SymbolStatus.ACTIVE,
            )
        second_symbol_id = next(
            symbol.id for symbol in catalog.list_symbols(game.id) if symbol.code == "second"
        )
        job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "pipeline_fingerprint": PIPELINE,
                    "test_source_batch": now.isoformat(),
                },
                created_at=now,
            )
        )
        session.commit()

    execution = SqlAlchemyImageBatchStore(session_factory).register_file(
        job.id,
        source_checksum_sha256="7" * 64,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="verified-cells.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(game.id), session_factory() as session:
        review_item_id = _add_pending_board(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
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
        backfill.backfill_next_batch(game.id, batch_size=20)
        assert backfill.backfill_next_batch(game.id, batch_size=20).report.status == "ready"
        session.commit()
    return _Seed(game.id, job.id, review_item_id, second_symbol_id)


def test_verified_cells_reach_search_while_the_board_stays_pending(
    verified_cell_database: URL,
) -> None:
    command.upgrade(_migration_config(verified_cell_database), "head")
    engine = create_engine(verified_cell_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)

    try:
        seed = _seed_pending_board(session_factory, now)
        game_id, job_id = seed.game_id, seed.job_id
        review_item_id, second_symbol_id = seed.review_item_id, seed.second_symbol_id
        with game_storage_scope(game_id), session_factory() as session:
            assert _document_codes(session, game_id) == [1] * 15
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            cells = _cells(session, review_item_id)
            # Scenario 1: one verified cell, all others still unverified.
            result = service.reassign(
                game_id=game_id,
                cell_review_id=cells[0].id,
                expected_revision=cells[0].revision,
                expected_geometry_revision=cells[0].geometry_revision,
                expected_crop_sample_id=cells[0].crop_sample_id,
                expected_crop_checksum_sha256=cells[0].crop_checksum_sha256,
                target_symbol_id=second_symbol_id,
                actor="symbol-cell-operator",
            )
            assert result.board_status == "pending"
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            assert _document_codes(session, game_id) == [2] + [1] * 14
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            cells = _cells(session, review_item_id)
            # Scenario 2: another cell reports a bad crop; the verified cell stays.
            service.mark_grid_issue(
                game_id=game_id,
                cell_review_id=cells[1].id,
                expected_revision=cells[1].revision,
                expected_geometry_revision=cells[1].geometry_revision,
                expected_crop_sample_id=cells[1].crop_sample_id,
                expected_crop_checksum_sha256=cells[1].crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            assert _document_codes(session, game_id) == [2, None] + [1] * 13
            cells = _cells(session, review_item_id)
            # The durable bulk job applies decisions per board; each board
            # batch refreshes the search document in its own transaction.
            operation, _created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
                game_id=game_id,
                request=SymbolCellReviewBulkRequest(
                    action=SymbolCellReviewAction.REASSIGN,
                    target_symbol_id=second_symbol_id,
                    explicit_targets=tuple(
                        SymbolCellReviewBulkExplicitTarget(
                            cell_review_id=cell.id,
                            expected_revision=cell.revision,
                            expected_geometry_revision=cell.geometry_revision,
                            expected_crop_sample_id=cell.crop_sample_id,
                            expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                        )
                        for cell in cells[2:4]
                    ),
                    filter_selection=None,
                    actor="local-admin",
                ),
                idempotency_key=uuid4(),
            )
            bulk_job = SqlAlchemyJobRepository(session).get_job(operation.job_id)
            assert bulk_job is not None
            session.commit()

        with game_storage_scope(game_id):
            progress = SqlAlchemySymbolCellReviewBulkOperationWorker(
                session_factory
            ).process_next_batch(job=bulk_job, max_boards=1)
        assert progress.operation.applied_count == 2

        with game_storage_scope(game_id), session_factory() as session:
            assert _document_codes(session, game_id) == [2, None, 2, 2] + [1] * 11
            cells = _cells(session, review_item_id)
            # Reporting a verified cell as a bad crop revokes only that cell.
            SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            ).mark_grid_issue(
                game_id=game_id,
                cell_review_id=cells[2].id,
                expected_revision=cells[2].revision,
                expected_geometry_revision=cells[2].geometry_revision,
                expected_crop_sample_id=cells[2].crop_sample_id,
                expected_crop_checksum_sha256=cells[2].crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            assert _document_codes(session, game_id) == [2, None, None, 2] + [1] * 11
            operational = SqlAlchemyOperationalImageReviewRepository(session)
            current = operational.get_item(review_item_id, game_id=game_id, import_job_id=job_id)
            assert current is not None
            geometry_command = validate_image_review_geometry_command(
                corners=(
                    ImageReviewGeometryPoint(1, 1),
                    ImageReviewGeometryPoint(91, 1),
                    ImageReviewGeometryPoint(91, 91),
                    ImageReviewGeometryPoint(1, 91),
                ),
                expected_geometry_revision=current.geometry_revision,
                expected_resolution_revision=current.resolution_revision,
                corrected_by="grid-reviewer",
            )
            operational.save_geometry_revision(
                review_item_id=review_item_id,
                game_id=game_id,
                import_job_id=job_id,
                idempotency_key=uuid4(),
                command=geometry_command,
                artifacts=ImageReviewGeometryArtifacts(
                    geometry={"source": "verified-cell-recrop", "quad": IN_FRAME_QUAD},
                    board_relative_path="corrected/verified-cells.png",
                    board_checksum_sha256="d" * 64,
                    cropper_version="verified-cell-recrop",
                    cells=tuple(
                        ImageReviewGeometryCellArtifact(
                            row_index=index // 5,
                            column_index=index % 5,
                            crop_relative_path=f"corrected/verified-cells-{index}.png",
                            crop_checksum_sha256=f"{7000 + index:064x}",
                        )
                        for index in range(15)
                    ),
                ),
                created_at=now + timedelta(minutes=1),
            )
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            # Every crop changed: the old approval covers other pixels (R10), so
            # cell 0 is no evidence any more; the document follows the cells.
            cells = _cells(session, review_item_id)
            assert cells[0].review_state == "approved"
            assert cells[1].quality_issue == "grid_issue"
            assert cells[2].quality_issue == "grid_issue"
            assert _document_codes(session, game_id) == [1, None, None] + [1] * 12
    finally:
        engine.dispose()


def test_fifteen_verified_cells_close_the_board_without_geometry_approval(
    verified_cell_database: URL,
) -> None:
    """Scenario 7 (D-462): no extra board, grid or photo approval is needed."""

    command.upgrade(_migration_config(verified_cell_database), "head")
    engine = create_engine(verified_cell_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)

    try:
        seed = _seed_pending_board(session_factory, now)
        with game_storage_scope(seed.game_id), session_factory() as session:
            board = session.scalar(
                select(RecognizedBoardModel)
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(ImageReviewItemModel.id == seed.review_item_id)
            )
            assert board is not None
            assert board.approved_geometry_revision is None
            board_id = board.id
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            result = None
            for cell in _cells(session, seed.review_item_id):
                result = service.approve(
                    game_id=seed.game_id,
                    cell_review_id=cell.id,
                    expected_revision=cell.revision,
                    expected_geometry_revision=cell.geometry_revision,
                    expected_crop_sample_id=cell.crop_sample_id,
                    expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                    actor="symbol-cell-operator",
                )
            assert result is not None
            assert result.board_status == "accepted"
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            review = session.get(ImageReviewItemModel, seed.review_item_id)
            assert review is not None and review.status == "accepted"
            canonical = session.get(
                ImageSequenceCanonicalModel,
                {"game_id": seed.game_id, "sequence_number": 1},
            )
            assert canonical is not None
            staging = session.get(
                ImageLayoutStagingRowModel,
                {"import_job_id": seed.job_id, "recognized_board_id": board_id},
            )
            assert staging is not None and staging.cells == [1] * 15
            board = session.get(RecognizedBoardModel, board_id)
            assert board is not None and board.approved_geometry_revision is None
    finally:
        engine.dispose()


def test_an_approval_of_other_pixels_keeps_the_board_open(
    verified_cell_database: URL,
) -> None:
    """R10 (D-462): pixels decide, not the approval's sample id or revision."""

    command.upgrade(_migration_config(verified_cell_database), "head")
    engine = create_engine(verified_cell_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)

    def approve(session: Session, cell: ImageSymbolReviewCellModel) -> str:
        return (
            SymbolCellReviewMutationService(SqlAlchemySymbolCellReviewMutationRepository(session))
            .approve(
                game_id=seed.game_id,
                cell_review_id=cell.id,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                actor="symbol-cell-operator",
            )
            .board_status
        )

    try:
        seed = _seed_pending_board(session_factory, now)
        with game_storage_scope(seed.game_id), session_factory() as session:
            cells = _cells(session, seed.review_item_id)
            for cell in cells[:14]:
                assert approve(session, cell) == "pending"
            # Simulate an approval that was given to other pixels.
            cells[0].approved_crop_checksum_sha256 = "f" * 64
            session.flush()
            assert approve(session, cells[14]) == "pending"
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            cells = _cells(session, seed.review_item_id)
            # Same pixels under another sample identity: still a verification.
            cells[0].approved_crop_checksum_sha256 = cells[0].crop_checksum_sha256
            cells[0].approved_crop_sample_id = "e" * 64
            session.flush()
            assert SymbolCellReviewWriteThroughCoordinator(session).synchronize_board_from_cells(
                game_id=seed.game_id,
                review_item_id=seed.review_item_id,
                actor="symbol-cell-operator",
            )
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            review = session.get(ImageReviewItemModel, seed.review_item_id)
            assert review is not None and review.status == "accepted"
    finally:
        engine.dispose()
