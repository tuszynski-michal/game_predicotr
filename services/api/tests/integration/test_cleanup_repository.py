import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _application_role_database import provision_game
from alembic import command
from alembic.config import Config
from game_predictor_api.application.cleanup import CleanupService, ManagedCleanupArtifactStore
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
    CleanupCommand,
    cleanup_preview,
)
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.mobile_releases import MobileReleaseStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import (
    create_cross_game_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CleanupOperationModel,
    DatasetVersionModel,
    GameModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    LayoutModel,
    MobileReleaseGameModel,
    MobileReleaseModel,
    RulesVersionModel,
    SymbolModel,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_cleanup_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().owner_database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_cleanup_database() -> Iterator[URL]:
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


class RecordingArtifacts:
    def __init__(self) -> None:
        self.deleted: tuple[str, ...] = ()

    def delete(self, paths: tuple[str, ...]) -> None:
        self.deleted = paths


def _add_game_source(session: Session, game_id: UUID) -> tuple[GameModel, DatasetVersionModel]:
    # TASK-0797: game data lives in V2 partitions provisioned by the owner
    # lifecycle (no public fallback store since 0125).
    game = session.get(GameModel, game_id)
    assert game is not None
    game.status = GameStatus.ACTIVE
    session.flush()
    symbol = SymbolModel(
        game_id=game.id,
        mobile_code=1,
        code="S1",
        name="Symbol 1",
        image_path=f"symbols/{game.code}/s1.png",
        is_wildcard=False,
        display_order=1,
        status=SymbolStatus.ACTIVE,
    )
    rules = RulesVersionModel(
        game_id=game.id,
        version=1,
        rows=1,
        columns=1,
        spin_cost=10,
        status=RulesVersionStatus.PUBLISHED,
    )
    dataset = DatasetVersionModel(
        game_id=game.id,
        version=1,
        rows=1,
        columns=1,
        signature_cell_width=2,
        expected_layout_count=1,
        layout_count=1,
        status=DatasetVersionStatus.PUBLISHED,
        generation_seed=1,
        generator_version="cleanup-test-v1",
    )
    session.add_all([symbol, rules, dataset])
    session.flush()
    session.add(
        LayoutModel(
            dataset_version_id=dataset.id,
            sequence_number=1,
            signature="01",
            cells=[1],
        )
    )
    return game, dataset


def test_game_reset_preserves_game_jobs_and_other_game(
    isolated_cleanup_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_cleanup_database), "head")
    engine = create_engine(isolated_cleanup_database, pool_pre_ping=True)
    release_factory = create_cross_game_owner_session_factory(engine)
    target_id = provision_game(engine, "target-game")
    other_id = provision_game(engine, "other-game")
    try:
        with release_factory() as session:
            target_game, target_dataset = _add_game_source(session, target_id)
            other_game, _other_dataset = _add_game_source(session, other_id)
            target_rules = session.scalar(
                select(RulesVersionModel).where(RulesVersionModel.game_id == target_game.id)
            )
            assert target_rules is not None
            job = JobModel(
                job_type=JobType.IMPORT,
                game_id=target_game.id,
                status=JobStatus.COMPLETED,
                input_payload={"schemaVersion": 1},
                input_key="1" * 64,
            )
            release = MobileReleaseModel(
                version="cleanup-test",
                status=MobileReleaseStatus.DRAFT,
                algorithm_version="payout-v2",
                snapshot_schema_version=2,
            )
            session.add_all([job, release])
            session.flush()
            session.add(
                MobileReleaseGameModel(
                    mobile_release_id=release.id,
                    game_id=target_game.id,
                    dataset_version_id=target_dataset.id,
                    rules_version_id=target_rules.id,
                    layout_count=1,
                )
            )
            session.commit()

            artifacts = RecordingArtifacts()
            # Production wiring: the game reset runs in a session bound to the
            # game (application role in the PG application-role mode); only the
            # cross-game safety checks read through the owner session.
            with (
                game_storage_scope(target_game.id),
                create_session_factory(engine)() as game_session,
            ):
                service = CleanupService(
                    SqlAlchemyCleanupRepository(game_session, release_factory), artifacts
                )
                preview = service.preview_game_reset(target_game.id)
                result = service.reset_game(
                    target_game.id,
                    CleanupCommand(
                        preview_token=preview.preview_token,
                        confirmation_target=str(target_game.id),
                        confirmed=True,
                    ),
                )
                game_session.commit()

            assert result.kind == "game_layout_data"
            assert session.get(GameModel, target_game.id) is not None
            assert session.get(JobModel, job.id) is not None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(MobileReleaseModel)
                    .where(MobileReleaseModel.id == release.id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(SymbolModel)
                    .where(SymbolModel.game_id == target_game.id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DatasetVersionModel)
                    .where(DatasetVersionModel.game_id == target_game.id)
                )
                == 0
            )
            assert session.get(GameModel, other_game.id) is not None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(SymbolModel)
                    .where(SymbolModel.game_id == other_game.id)
                )
                == 1
            )
            assert session.scalar(select(func.count()).select_from(CleanupOperationModel)) == 1
            assert artifacts.deleted == preview.snapshot.artifact_paths
    finally:
        engine.dispose()


def test_release_delete_preserves_selected_game_and_records_receipt(
    isolated_cleanup_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_cleanup_database), "head")
    engine = create_engine(isolated_cleanup_database, pool_pre_ping=True)
    release_factory = create_cross_game_owner_session_factory(engine)
    game_id = provision_game(engine, "release-game")
    try:
        # Production wiring: release cleanup runs on the cross-game owner session.
        with release_factory() as session:
            game, dataset = _add_game_source(session, game_id)
            rules = session.scalar(
                select(RulesVersionModel).where(RulesVersionModel.game_id == game.id)
            )
            assert rules is not None
            release = MobileReleaseModel(
                version="release-delete-test",
                status=MobileReleaseStatus.READY,
                algorithm_version="payout-v2",
                snapshot_schema_version=2,
                snapshot_path="snapshots/release-delete-test/hash/snapshot.db",
                snapshot_checksum="a" * 64,
                apk_path="android-releases/release-delete-test/app.apk",
                apk_checksum="b" * 64,
            )
            session.add(release)
            session.flush()
            session.add(
                MobileReleaseGameModel(
                    mobile_release_id=release.id,
                    game_id=game.id,
                    dataset_version_id=dataset.id,
                    rules_version_id=rules.id,
                    layout_count=1,
                )
            )
            session.commit()

            artifacts = RecordingArtifacts()
            service = CleanupService(
                SqlAlchemyCleanupRepository(session, release_factory), artifacts
            )
            preview = service.preview_release(release.id)
            service.delete_release(
                release.id,
                CleanupCommand(
                    preview_token=cleanup_preview(preview.snapshot).preview_token,
                    confirmation_target=str(release.id),
                    confirmed=True,
                ),
            )
            session.commit()

            assert (
                session.scalar(
                    select(func.count())
                    .select_from(MobileReleaseModel)
                    .where(MobileReleaseModel.id == release.id)
                )
                == 0
            )
            assert session.get(GameModel, game.id) is not None
            assert artifacts.deleted == (
                "snapshots/release-delete-test",
                "android-releases/release-delete-test",
            )
            assert session.scalar(select(func.count()).select_from(CleanupOperationModel)) == 1
    finally:
        engine.dispose()


def _derive_job(status: JobStatus, game_id: UUID) -> JobModel:
    """A super game derivation job (TASK-0933), queued or running."""

    now = datetime.now(UTC)
    running = status is JobStatus.PROCESSING
    return JobModel(
        job_type=JobType.SUPER_GAME_SERIES_DERIVE,
        game_id=game_id,
        status=status,
        input_payload={"schema_version": 1, "reason": "test", "request_id": str(uuid4())},
        input_key=uuid4().hex * 2,
        execution_slot=1 if running else None,
        lease_owner="cleanup-test" if running else None,
        lease_token=uuid4() if running else None,
        lease_expires_at=now + timedelta(minutes=5) if running else None,
        heartbeat_at=now if running else None,
    )


def test_a_queued_super_game_derive_job_blocks_and_the_reset_queues_a_new_one(
    isolated_cleanup_database: URL,
) -> None:
    """Audit TASK-0933 P0-4: a derivation job blocks cleanup like any other job.

    Once the worker has finished it, the reset runs and its own input-version
    bump queues a fresh derivation of the reset game.
    """

    command.upgrade(_migration_config(isolated_cleanup_database), "head")
    engine = create_engine(isolated_cleanup_database, pool_pre_ping=True)
    release_factory = create_cross_game_owner_session_factory(engine)
    game_id = provision_game(engine, "derive-blocker")
    try:
        with release_factory() as session:
            game = session.get(GameModel, game_id)
            assert game is not None
            game.super_game_kind = "wild_super_spins"
            job = _derive_job(JobStatus.CREATED, game_id)
            session.add(job)
            session.commit()
            job_id = job.id

        def derive_jobs() -> list[UUID]:
            with release_factory() as session:
                return list(
                    session.scalars(
                        select(JobModel.id).where(
                            JobModel.game_id == game_id,
                            JobModel.job_type == JobType.SUPER_GAME_SERIES_DERIVE,
                            JobModel.status == JobStatus.CREATED,
                        )
                    )
                )

        with game_storage_scope(game_id), create_session_factory(engine)() as game_session:
            service = CleanupService(
                SqlAlchemyCleanupRepository(game_session, release_factory), RecordingArtifacts()
            )
            assert "ACTIVE_GAME_JOB" in service.preview_game_reset(game_id).snapshot.blockers
            game_session.rollback()

        # The worker finished the derivation; the reset is no longer blocked.
        with release_factory() as session:
            session.delete(session.get(JobModel, job_id))
            session.commit()
        assert derive_jobs() == []
        with game_storage_scope(game_id), create_session_factory(engine)() as game_session:
            service = CleanupService(
                SqlAlchemyCleanupRepository(game_session, release_factory), RecordingArtifacts()
            )
            preview = service.preview_game_reset(game_id)
            assert "ACTIVE_GAME_JOB" not in preview.snapshot.blockers
            service.reset_game(
                game_id,
                CleanupCommand(
                    preview_token=preview.preview_token,
                    confirmation_target=str(game_id),
                    confirmed=True,
                ),
            )
            game_session.commit()
        queued = derive_jobs()
        assert len(queued) == 1 and queued[0] != job_id
    finally:
        engine.dispose()


def test_source_cleanup_batches_preserve_queue_until_last_source(
    isolated_cleanup_database: URL,
    tmp_path: Path,
) -> None:
    """Two committed cleanups of one import keep the real queue trigger valid."""
    command.upgrade(_migration_config(isolated_cleanup_database), "head")
    engine = create_engine(isolated_cleanup_database, pool_pre_ping=True)
    factory = create_session_factory(engine)
    cross_game_factory = create_cross_game_owner_session_factory(engine)
    game_id = provision_game(engine, "source-cleanup-batches")
    now = datetime.now(UTC)
    try:
        with game_storage_scope(game_id), factory() as session:
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game_id, PIPELINE, now))
            session.commit()
        store = SqlAlchemyImageBatchStore(factory)
        for index in range(2):
            checksum = str(index + 1) * 64
            name = f"batch-{index}.jpg"
            (tmp_path / name).write_bytes(b"managed source")
            execution = store.register_file(
                job.id,
                source_checksum_sha256=checksum,
                pipeline_fingerprint=PIPELINE,
                source_relative_path=name,
                order_index=index,
                registered_at=now,
            )
            with game_storage_scope(game_id), factory() as session:
                _add_review_projection_source(
                    session,
                    job_id=job.id,
                    file_execution_key=execution.file_execution_key,
                    source_checksum=checksum,
                    source_name=name,
                    position_index=0,
                    sequence_number=1 + index * 9,
                    status="pending",
                    created_at=now,
                )
                session.commit()
        with game_storage_scope(game_id), factory() as session:
            record = session.get(JobModel, job.id)
            assert record is not None
            record.status = JobStatus.WAITING_FOR_REVIEW
            ranges = session.execute(
                select(
                    ImageSourceGeometryRevisionModel.sequence_range_start,
                    ImageSourceGeometryRevisionModel.sequence_range_end,
                )
                .where(ImageSourceGeometryRevisionModel.game_id == game_id)
                .order_by(ImageSourceGeometryRevisionModel.sequence_range_start)
            ).all()
            assert len(ranges) == 2
            session.commit()
        for index, (start, end) in enumerate(ranges):
            # A fresh runtime session sees the previous committed batch.
            with game_storage_scope(game_id), factory() as session:
                service = CleanupService(
                    SqlAlchemyCleanupRepository(session, cross_game_factory),
                    ManagedCleanupArtifactStore(tmp_path),
                )
                selection = BoardSourceCleanupSelection(tuple(range(start, end + 1)))
                preview = service.preview_board_sources(game_id, selection)
                assert preview.snapshot.blockers == ()
                service.delete_board_sources(
                    game_id,
                    selection,
                    CleanupCommand(
                        preview.preview_token, preview.snapshot.confirmation_target, True
                    ),
                )
                session.commit()
                service.finalize_committed_artifacts()
            with game_storage_scope(game_id), factory() as session:
                state = session.execute(
                    text(
                        "SELECT total_count,pending_count FROM image_review_queue_states "
                        "WHERE import_job_id=:job"
                    ),
                    {"job": job.id},
                ).one_or_none()
                if index == 0:
                    assert state == (1, 1)
                else:
                    assert state is None
                remaining = session.execute(
                    text("SELECT count(*) FROM image_review_queue_items WHERE import_job_id=:job"),
                    {"job": job.id},
                ).scalar_one()
                assert remaining == 1 - index
    finally:
        engine.dispose()
