import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.cleanup import CleanupService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.cleanup import CleanupCommand, cleanup_preview
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.mobile_releases import MobileReleaseStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.models import (
    CleanupOperationModel,
    DatasetVersionModel,
    GameModel,
    JobModel,
    LayoutModel,
    MobileReleaseGameModel,
    MobileReleaseModel,
    RulesVersionModel,
    SymbolModel,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_cleanup_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


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


def _add_game_source(session: Session, code: str) -> tuple[GameModel, DatasetVersionModel]:
    game = GameModel(code=code, name=code, status=GameStatus.ACTIVE)
    session.add(game)
    session.flush()
    symbol = SymbolModel(
        game_id=game.id,
        mobile_code=1,
        code="S1",
        name="Symbol 1",
        image_path=f"symbols/{code}/s1.png",
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
    try:
        with Session(engine, expire_on_commit=False) as session:
            target_game, target_dataset = _add_game_source(session, "target-game")
            other_game, _other_dataset = _add_game_source(session, "other-game")
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
            service = CleanupService(SqlAlchemyCleanupRepository(session), artifacts)
            preview = service.preview_game_reset(target_game.id)
            result = service.reset_game(
                target_game.id,
                CleanupCommand(
                    preview_token=preview.preview_token,
                    confirmation_target=str(target_game.id),
                    confirmed=True,
                ),
            )
            session.commit()

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
    try:
        with Session(engine, expire_on_commit=False) as session:
            game, dataset = _add_game_source(session, "release-game")
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
            service = CleanupService(SqlAlchemyCleanupRepository(session), artifacts)
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
