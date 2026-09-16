from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType, create_job
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.browser_staging_retention_repository import (
    SqlAlchemyBrowserStagingRetentionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RulesVersionModel,
    SourceImageModel,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_browser_staging_retention_test"

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
def isolated_browser_staging_database() -> Iterator[URL]:
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


def _seed_staging(
    session: Session,
    *,
    upload_id: UUID,
    suffix: str,
    geometry_source: str,
    geometry_revision: int,
    now: datetime,
) -> UUID:
    game = GameModel(
        code=f"browser-retention-{suffix}",
        name=f"Browser retention {suffix}",
        status=GameStatus.ACTIVE,
    )
    session.add(game)
    session.flush()
    rules = RulesVersionModel(
        game_id=game.id,
        version=1,
        rows=3,
        columns=3,
        spin_cost=0,
        status=RulesVersionStatus.DRAFT,
        created_at=now,
        published_at=None,
    )
    session.add(rules)
    session.flush()
    job = SqlAlchemyJobRepository(session).add_job(
        create_job(
            JobType.IMPORT,
            game_id=game.id,
            input_payload={
                "schema_version": 1,
                "import_kind": "image_directory",
                "source_selection_id": str(upload_id),
                "pipeline_fingerprint": "c" * 64,
            },
            created_at=now,
        )
    )
    job_record = session.get(JobModel, job.id)
    assert job_record is not None
    job_record.status = JobStatus.CANCELLED
    job_record.finished_at = now

    execution_key = suffix * 64
    source_checksum = suffix * 64
    session.add(
        ImageFileExecutionModel(
            file_execution_key=execution_key,
            source_checksum_sha256=source_checksum,
            pipeline_fingerprint="c" * 64,
            checkpoint_payload={"schemaVersion": 1},
            status="waiting_for_review",
            review_required=True,
            created_at=now,
        )
    )
    session.add(
        ImageImportJobFileModel(
            job_id=job.id,
            file_execution_key=execution_key,
            order_index=0,
            source_relative_path=f"page-{suffix}.jpg",
            workflow_checkpoint_payload={"schemaVersion": 1},
            workflow_status="waiting_for_review",
            review_required=True,
            created_at=now,
        )
    )
    session.add(
        ImagePipelineStageResultModel(
            file_execution_key=execution_key,
            stage="board_cell_geometry",
            adapter_version="browser-retention-test-v1",
            result_payload={},
            created_at=now,
        )
    )
    source = SourceImageModel(
        import_job_id=job.id,
        file_execution_key=execution_key,
        relative_path=f"page-{suffix}.jpg",
        checksum_sha256=source_checksum,
        width=1440,
        height=1920,
        status="waiting_for_review",
        created_at=now,
    )
    session.add(source)
    session.flush()
    session.add(
        ImageSourceGeometryRevisionModel(
            game_id=game.id,
            source_image_id=source.id,
            topology_rules_version_id=rules.id,
            revision=geometry_revision,
            sequence_range_start=1,
            sequence_range_end=9,
            active_board_slots=list(range(9)),
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=source_checksum,
            normalized_pixel_checksum_sha256="b" * 64,
            oriented_width=1440,
            oriented_height=1920,
            normalization_adapter_version="normalization-test-v1",
            global_initialization={},
            board_geometries=[{} for _ in range(9)],
            engine_kind="structured_opencv_v1",
            engine_version="structured-test-v1",
            geometry_source=geometry_source,
            status="needs_review",
            geometry_checksum_sha256="d" * 64,
            topology_fingerprint_sha256=None,
            sequence_attestation_schema_version=None,
            sequence_attestation_checksum_sha256=None,
            processing_time_ms=1,
            warnings=[],
            created_by="browser-retention-test",
            created_at=now,
        )
    )
    for position_index in range(9):
        session.add(
            ImageBoardGeometryPendingModel(
                game_id=game.id,
                import_job_id=job.id,
                source_image_id=source.id,
                recognized_board_id=None,
                review_item_id=None,
                sequence_number=position_index + 1,
                position_index=position_index,
                source_checksum_sha256=source_checksum,
                source_relative_path=f"page-{suffix}.jpg",
                status="pending",
                reason_code="residual_too_high",
                processing_manifest_checksum_sha256="e" * 64,
                processing_manifest_relative_path="manifests/processing.json",
                pipeline_fingerprint_sha256="c" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                resolved_geometry_revision=None,
                created_at=now,
                updated_at=now,
                resolved_at=None,
                superseded_at=None,
            )
        )
    session.add(
        BrowserSelectionRetentionModel(
            upload_id=upload_id,
            game_id=game.id,
            import_job_id=job.id,
            display_name=f"browser-retention-{suffix}",
            state="in_use",
            manifest_checksum_sha256="f" * 64,
            managed_manifest_relative_path=None,
            managed_manifest_checksum_sha256=None,
            finalized_at=now,
            last_dependency_at=now,
            eligible_at=None,
            blocked_reason=None,
            updated_at=now,
        )
    )
    session.flush()
    return job.id


def test_discard_unused_removes_only_automatic_empty_geometry_history(
    isolated_browser_staging_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_browser_staging_database), "head")
    engine = create_engine(isolated_browser_staging_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 2, 8, tzinfo=UTC)
    automatic_upload_id = uuid4()
    manual_upload_id = uuid4()

    try:
        with Session(engine, expire_on_commit=False) as session:
            automatic_job_id = _seed_staging(
                session,
                upload_id=automatic_upload_id,
                suffix="1",
                geometry_source="auto",
                geometry_revision=0,
                now=now,
            )
            manual_job_id = _seed_staging(
                session,
                upload_id=manual_upload_id,
                suffix="2",
                geometry_source="manual",
                geometry_revision=1,
                now=now,
            )
            session.commit()

        repository = SqlAlchemyBrowserStagingRetentionRepository(session_factory)
        repository.discard_unused(upload_id=automatic_upload_id)

        with Session(engine) as session:
            assert session.get(BrowserSelectionRetentionModel, automatic_upload_id) is None
            assert session.get(JobModel, automatic_job_id) is None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardGeometryPendingModel)
                    .where(ImageBoardGeometryPendingModel.import_job_id == automatic_job_id)
                )
                == 0
            )
            assert (
                session.scalar(select(func.count()).select_from(ImageSourceGeometryRevisionModel))
                == 1
            )
            assert session.scalar(select(func.count()).select_from(SourceImageModel)) == 1
            assert session.scalar(select(func.count()).select_from(ImageImportJobFileModel)) == 1
            assert session.scalar(select(func.count()).select_from(ImageFileExecutionModel)) == 1
            assert (
                session.scalar(select(func.count()).select_from(ImagePipelineStageResultModel)) == 1
            )

        with pytest.raises(JobConflictError) as protected_error:
            repository.discard_unused(upload_id=manual_upload_id)
        assert protected_error.value.code == "IMAGE_BROWSER_SELECTION_DELETE_HAS_RESULTS"
        assert protected_error.value.details["protectedSourceGeometryRevisionCount"] == 1

        with Session(engine) as session:
            assert session.get(BrowserSelectionRetentionModel, manual_upload_id) is not None
            assert session.get(JobModel, manual_job_id) is not None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageBoardGeometryPendingModel)
                    .where(ImageBoardGeometryPendingModel.import_job_id == manual_job_id)
                )
                == 9
            )
    finally:
        engine.dispose()
