import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.mobile_releases import (
    MobileReleaseService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseConflictError,
    MobileReleaseGameInput,
    MobileReleaseStatus,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.mobile_release_repository import (
    SqlAlchemyMobileReleaseRepository,
)
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    JobModel,
    MobileReleaseGameModel,
    MobileReleaseModel,
    RulesVersionModel,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_mobile_release_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason=("Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests."),
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_mobile_release_database() -> Iterator[URL]:
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


def _add_published_source(
    session: Session,
    *,
    code: str,
    rules_status: RulesVersionStatus = RulesVersionStatus.PUBLISHED,
) -> MobileReleaseGameInput:
    game = GameModel(
        code=code,
        name=code,
        status=GameStatus.ACTIVE,
    )
    session.add(game)
    session.flush()
    rules = RulesVersionModel(
        game_id=game.id,
        version=1,
        rows=3,
        columns=5,
        spin_cost=10,
        status=rules_status,
    )
    dataset = DatasetVersionModel(
        game_id=game.id,
        version=1,
        rows=3,
        columns=5,
        signature_cell_width=2,
        expected_layout_count=1000,
        layout_count=1000,
        status=DatasetVersionStatus.PUBLISHED,
        generation_seed=7,
        generator_version="mock-v1",
    )
    session.add_all([rules, dataset])
    session.flush()
    return MobileReleaseGameInput(
        game_id=game.id,
        dataset_version_id=dataset.id,
        rules_version_id=rules.id,
    )


def test_mobile_release_repository_persists_atomic_immutable_selection(
    isolated_mobile_release_database: URL,
) -> None:
    command.upgrade(
        _migration_config(isolated_mobile_release_database),
        "head",
    )
    engine = create_engine(
        isolated_mobile_release_database,
        pool_pre_ping=True,
    )

    try:
        with Session(engine, expire_on_commit=False) as session:
            game_z = _add_published_source(session, code="game-z")
            game_a = _add_published_source(session, code="game-a")
            invalid = _add_published_source(
                session,
                code="game-invalid",
                rules_status=RulesVersionStatus.DRAFT,
            )
            session.commit()

            service = MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
            release = service.create_mobile_release(
                version="m3.4-repository.1",
                games=(game_z, game_a),
            )
            session.commit()

            assert release.status is MobileReleaseStatus.DRAFT
            assert release.algorithm_version == "payout-v2"
            assert release.snapshot_schema_version == 3
            assert [game.game_code for game in release.games] == [
                "game-a",
                "game-z",
            ]
            assert [game.layout_count for game in release.games] == [
                1000,
                1000,
            ]
            assert service.get_mobile_release(release.id) == release
            assert session.scalar(select(func.count()).select_from(MobileReleaseGameModel)) == 2

            build_job = service.start_mobile_release_build(release.id)
            session.commit()
            persisted_build = session.get(JobModel, build_job.id)
            persisted_release = session.get(MobileReleaseModel, release.id)
            assert persisted_build is not None
            assert persisted_build.job_type.value == "android_build"
            assert persisted_release is not None
            assert persisted_release.status is MobileReleaseStatus.BUILDING
            assert persisted_release.build_job_id == build_job.id

            with pytest.raises(MobileReleaseConflictError) as duplicate_build:
                service.start_mobile_release_build(release.id)
            assert duplicate_build.value.code == "MOBILE_RELEASE_BUILD_ALREADY_STARTED"
            session.rollback()

            latest = service.create_mobile_release(
                version="m3.4-repository.2",
                games=(game_a,),
            )
            session.commit()
            assert [item.id for item in service.list_mobile_releases()] == [
                latest.id,
                release.id,
            ]

            cancelled_job = service.start_mobile_release_build(latest.id)
            session.commit()
            cancelled = JobService(SqlAlchemyJobRepository(session)).cancel_job(cancelled_job.id)
            session.commit()
            assert cancelled.status.value == "cancelled"
            cancelled_release = session.get(MobileReleaseModel, latest.id)
            assert cancelled_release is not None
            assert cancelled_release.status is MobileReleaseStatus.FAILED

            with pytest.raises(MobileReleaseConflictError) as duplicate:
                service.create_mobile_release(
                    version="m3.4-repository.1",
                    games=(game_a,),
                )
            assert duplicate.value.code == "MOBILE_RELEASE_VERSION_ALREADY_EXISTS"
            session.rollback()

            with pytest.raises(MobileReleaseConflictError) as invalid_source:
                service.create_mobile_release(
                    version="m3.4-repository.invalid",
                    games=(invalid,),
                )
            assert invalid_source.value.code == "RELEASE_RULES_NOT_PUBLISHED"
            session.rollback()

            assert session.scalar(select(func.count()).select_from(MobileReleaseModel)) == 2
            assert session.scalar(select(func.count()).select_from(MobileReleaseGameModel)) == 3
            assert session.scalar(select(func.count()).select_from(JobModel)) == 2
    finally:
        engine.dispose()
