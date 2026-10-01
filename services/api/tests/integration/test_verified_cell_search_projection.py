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
from game_predictor_api.application.image_grid_reviews import ImageGridReviewService
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewView
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
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
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
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
    sibling_positions: tuple[int, ...] = (),
) -> UUID:
    """Pending 3x5 boards of one photo whose model predicts `first` everywhere.

    The first board sits in slot 0 with sequence 1; each sibling position `p`
    gets sequence `p + 1`. Returns the review item of slot 0.
    """

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
    first_review_id: UUID | None = None
    for position in (0, *sibling_positions):
        sequence = position + 1
        board = RecognizedBoardModel(
            source_image_id=source.id,
            position_index=position,
            sequence_number_raw=str(sequence),
            sequence_number=sequence,
            sequence_confidence=1.0,
            board_geometry={"source": "verified-cell-test", "quad": IN_FRAME_QUAD},
            board_relative_path=f"crops/verified-cells-{position}.png",
            board_checksum_sha256=f"{sequence:064x}",
            # D-467: the import predictions of every cell.  Since S5 a legacy
            # board's crops come from its manual geometry revision (below).
            geometry_revision=1,
            cells_prediction={
                "cells": [
                    {
                        "rowIndex": index // 5,
                        "columnIndex": index % 5,
                        "symbolCode": "first",
                        "confidence": 0.9,
                        "alternatives": [{"symbolCode": "second", "confidence": 0.1}],
                    }
                    for index in range(15)
                ]
            },
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
            sequence_number=sequence,
            recognized_board_id=board.id,
            status="pending",
            snapshot={"sequenceNumber": sequence},
            resolution_revision=0,
            created_at=created_at,
        )
        session.add(review)
        session.flush()
        session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review.id,
                recognized_board_id=board.id,
                revision=1,
                idempotency_key=uuid4(),
                command_sha256=f"{sequence:064x}",
                corners=[
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 60},
                    {"x": 0, "y": 60},
                ],
                geometry={"source": "verified-cell-test", "quad": IN_FRAME_QUAD},
                asset_mode="legacy_file",
                board_relative_path=f"crops/verified-cells-{position}.png",
                board_checksum_sha256=f"{sequence:064x}",
                cropper_version="verified-cell-cropper",
                crop_artifacts=[
                    {
                        "rowIndex": index // 5,
                        "columnIndex": index % 5,
                        "cropRelativePath": f"crops/verified-cells-{position}-{index}.png",
                        "cropChecksumSha256": f"{1000 * position + 100 + index:064x}",
                    }
                    for index in range(15)
                ],
                corrected_by="fixture",
                created_at=created_at,
            )
        )
        session.flush()
        first_review_id = first_review_id or review.id
    assert first_review_id is not None
    return first_review_id


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


def _seed_pending_board(
    session_factory: sessionmaker[Session],
    now: datetime,
    sibling_positions: tuple[int, ...] = (),
) -> _Seed:
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
            sibling_positions=sibling_positions,
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
            # Every crop changed (R6): verified cells wait for a new check with
            # the human label as a suggestion, the saved geometry resolves both
            # grid reports (R5), and search falls back to the model evidence.
            cells = _cells(session, review_item_id)
            assert [cell.review_state for cell in cells[:4]] == ["pending"] * 4
            assert cells[0].assignment_source == "human"
            assert cells[0].assigned_symbol_id == second_symbol_id
            assert cells[0].approved_crop_checksum_sha256 != cells[0].crop_checksum_sha256
            assert all(cell.quality_issue is None for cell in cells)
            assert _document_codes(session, game_id) == [1] * 15
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

            # A geometry save that keeps every pixel reopens the board and
            # closes it again from the surviving verifications (R2, R6).
            operational = SqlAlchemyOperationalImageReviewRepository(session)
            identical = operational.get_item(
                seed.review_item_id, game_id=seed.game_id, import_job_id=seed.job_id
            )
            assert identical is not None
            operational.save_geometry_revision(
                review_item_id=seed.review_item_id,
                game_id=seed.game_id,
                import_job_id=seed.job_id,
                idempotency_key=uuid4(),
                command=validate_image_review_geometry_command(
                    corners=(
                        ImageReviewGeometryPoint(1, 1),
                        ImageReviewGeometryPoint(91, 1),
                        ImageReviewGeometryPoint(91, 91),
                        ImageReviewGeometryPoint(1, 91),
                    ),
                    expected_geometry_revision=identical.geometry_revision,
                    expected_resolution_revision=identical.resolution_revision,
                    corrected_by="grid-reviewer",
                ),
                artifacts=ImageReviewGeometryArtifacts(
                    geometry={"source": "identical-recrop", "quad": IN_FRAME_QUAD},
                    board_relative_path="corrected/identical-recrop.png",
                    board_checksum_sha256="d" * 64,
                    cropper_version="verified-cell-cropper",
                    cells=tuple(
                        ImageReviewGeometryCellArtifact(
                            row_index=index // 5,
                            column_index=index % 5,
                            crop_relative_path=f"corrected/identical-{index}.png",
                            crop_checksum_sha256=f"{100 + index:064x}",
                        )
                        for index in range(15)
                    ),
                ),
                created_at=now + timedelta(minutes=1),
            )
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            review = session.get(ImageReviewItemModel, seed.review_item_id)
            assert review is not None and review.status == "accepted"
            assert (
                session.get(
                    ImageLayoutStagingRowModel,
                    {"import_job_id": seed.job_id, "recognized_board_id": board_id},
                )
                is not None
            )

            # Scenario 6 (D-462 R6): a corrected geometry changes only cell 0.
            operational = SqlAlchemyOperationalImageReviewRepository(session)
            current = operational.get_item(
                seed.review_item_id, game_id=seed.game_id, import_job_id=seed.job_id
            )
            assert current is not None
            operational.save_geometry_revision(
                review_item_id=seed.review_item_id,
                game_id=seed.game_id,
                import_job_id=seed.job_id,
                idempotency_key=uuid4(),
                command=validate_image_review_geometry_command(
                    corners=(
                        ImageReviewGeometryPoint(1, 1),
                        ImageReviewGeometryPoint(91, 1),
                        ImageReviewGeometryPoint(91, 91),
                        ImageReviewGeometryPoint(1, 91),
                    ),
                    expected_geometry_revision=current.geometry_revision,
                    expected_resolution_revision=current.resolution_revision,
                    corrected_by="grid-reviewer",
                ),
                artifacts=ImageReviewGeometryArtifacts(
                    geometry={"source": "partial-recrop", "quad": IN_FRAME_QUAD},
                    board_relative_path="corrected/partial-recrop.png",
                    board_checksum_sha256="e" * 64,
                    cropper_version="verified-cell-cropper",
                    cells=tuple(
                        ImageReviewGeometryCellArtifact(
                            row_index=index // 5,
                            column_index=index % 5,
                            crop_relative_path=f"corrected/partial-recrop-{index}.png",
                            crop_checksum_sha256=f"{(9000 if index == 0 else 100) + index:064x}",
                        )
                        for index in range(15)
                    ),
                ),
                created_at=now + timedelta(minutes=2),
            )
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            cells = _cells(session, seed.review_item_id)
            assert cells[0].review_state == "pending"
            assert cells[0].assignment_source == "human"
            assert all(cell.review_state == "approved" for cell in cells[1:])
            assert all(
                cell.approved_crop_checksum_sha256 == cell.crop_checksum_sha256
                and cell.approved_geometry_revision == cell.geometry_revision == 3
                for cell in cells[1:]
            )
            review = session.get(ImageReviewItemModel, seed.review_item_id)
            assert review is not None and review.status == "pending"
            assert (
                session.get(
                    ImageLayoutStagingRowModel,
                    {"import_job_id": seed.job_id, "recognized_board_id": board_id},
                )
                is None
            )
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


def test_correction_queue_lists_one_reported_board_per_slot(
    verified_cell_database: URL,
) -> None:
    """D-462 R4: scenarios 3, 4 and 5 on one photo with three slots."""

    command.upgrade(_migration_config(verified_cell_database), "head")
    engine = create_engine(verified_cell_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)

    def correction_page(session: Session) -> tuple[list[tuple[str, int, tuple[int, ...]]], int]:
        page = ImageGridReviewService(SqlAlchemyImageGridReviewRepository(session)).list(
            game_id=seed.game_id,
            view=ImageGridReviewView.CORRECTION,
            import_job_id=seed.job_id,
            source_image_id=None,
            after_cursor=None,
            before_cursor=None,
            limit=10,
        )
        return (
            [
                (item.slot_kind.value, item.position_index, item.reported_cell_indices)
                for item in page.items
            ],
            page.counts.correction,
        )

    def deferred_slot(session: Session, board: RecognizedBoardModel, position: int) -> None:
        source = session.get(SourceImageModel, board.source_image_id)
        assert source is not None
        session.add(
            ImageBoardGeometryPendingModel(
                game_id=seed.game_id,
                import_job_id=seed.job_id,
                source_image_id=board.source_image_id,
                sequence_number=position + 1,
                position_index=position,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                status="pending",
                reason_code="residual_too_high",
                processing_manifest_checksum_sha256=f"{position + 10:064x}",
                processing_manifest_relative_path=f"manifests/slot-{position}.json",
                pipeline_fingerprint_sha256=PIPELINE,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
            )
        )
        session.flush()

    try:
        # Slot 0 and its sibling slot 1 have live boards; slot 2 has none.
        seed = _seed_pending_board(session_factory, now, sibling_positions=(1,))
        with game_storage_scope(seed.game_id), session_factory() as session:
            assert correction_page(session) == ([], 0)
            service = SymbolCellReviewMutationService(
                SqlAlchemySymbolCellReviewMutationRepository(session)
            )
            for cell in _cells(session, seed.review_item_id)[1:5:3]:
                service.mark_grid_issue(
                    game_id=seed.game_id,
                    cell_review_id=cell.id,
                    expected_revision=cell.revision,
                    expected_geometry_revision=cell.geometry_revision,
                    expected_crop_sample_id=cell.crop_sample_id,
                    expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                    actor="symbol-cell-operator",
                )
            session.commit()

        with game_storage_scope(seed.game_id), session_factory() as session:
            # Two reports of one board give one entry naming both cells, and
            # the unreported sibling of the same photo is not routed (4, 5).
            assert correction_page(session) == ([("current_review", 0, (1, 4))], 1)
            board = session.scalar(
                select(RecognizedBoardModel)
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(ImageReviewItemModel.id == seed.review_item_id)
            )
            assert board is not None
            source = session.get(SourceImageModel, board.source_image_id)
            assert source is not None
            rules = RulesVersionModel(
                game_id=seed.game_id,
                version=1,
                rows=3,
                columns=5,
                spin_cost=0,
                status=RulesVersionStatus.DRAFT,
                created_at=now,
                published_at=None,
            )
            session.add(rules)
            session.flush()
            session.add(
                ImageSourceGeometryRevisionModel(
                    game_id=seed.game_id,
                    source_image_id=source.id,
                    topology_rules_version_id=rules.id,
                    revision=0,
                    sequence_range_start=1,
                    sequence_range_end=3,
                    active_board_slots=[0, 1, 2],
                    coordinate_space="exif-normalized-rgb-pixels-v1",
                    source_checksum_sha256=source.checksum_sha256,
                    normalized_pixel_checksum_sha256="b" * 64,
                    oriented_width=1920,
                    oriented_height=1080,
                    normalization_adapter_version="normalization-test-v1",
                    global_initialization={},
                    board_geometries=[{"positionIndex": slot} for slot in range(3)],
                    engine_kind="structured_opencv_v1",
                    engine_version="structured-test-v1",
                    geometry_source="auto",
                    status="needs_review",
                    geometry_checksum_sha256="d" * 64,
                    processing_time_ms=1,
                    warnings=[],
                    created_by="correction-queue-test",
                    created_at=now,
                )
            )
            # Scenario 3: the algorithm rejected slot 2 only.
            deferred_slot(session, board, 2)
            assert correction_page(session) == (
                [("current_review", 0, (1, 4)), ("deferred_geometry", 2, ())],
                2,
            )
            # A stale deferral of the reported board's own slot adds nothing:
            # the live board stays the slot's single entry.
            deferred_slot(session, board, 0)
            assert correction_page(session) == (
                [("current_review", 0, (1, 4)), ("deferred_geometry", 2, ())],
                2,
            )
            session.rollback()
    finally:
        engine.dispose()
