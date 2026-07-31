from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewResolutionCell,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_job_repository import (
    SqlAlchemyImageJobOperationsRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.orchestration import (
    ImageStageExecutionResult,
    advance_file_checkpoint,
)
from game_predictor_worker.images.orchestration_store import (
    ImageOrchestrationStoreError,
    SqlAlchemyImageBatchStore,
)
from game_predictor_worker.images.pipeline_store import (
    ImagePipelineStoreError,
    SqlAlchemyImagePipelineStore,
)
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
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
        assert reused.status == "waiting_for_review"
        assert reused.checkpoint_payload["nextStage"] == "manual_review"

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
                        "alternatives": [
                            {"symbolCode": "lemon", "confidence": 1.0}
                        ],
                    },
                    created_at=now,
                )
                for index in range(15)
            )
            session.commit()

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
            assert (
                session.scalar(select(func.count()).select_from(ImageLayoutStagingRowModel))
                == 0
            )
            assert (
                session.scalar(
                    select(func.count()).select_from(ImageBoardGeometryRevisionModel)
                )
                == 1
            )
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
