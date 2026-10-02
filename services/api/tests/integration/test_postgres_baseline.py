"""Migration lifecycle and Reviewer assignment invariants on PostgreSQL.

The expected head comes from ``schema_readiness.EXPECTED_ALEMBIC_HEAD`` and
the expected tables from the ORM metadata and the frozen game-table manifest,
so the baseline does not pin a revision name or a hand-copied table list.

Game-owned tables live only in ``game_data_v2`` (D-448, migration 0125), so
the Reviewer tests provision their games through the partition lifecycle and
bind every data-plane transaction to one game.
"""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from game_predictor_api.application.reviewer_work_assignments import (
    ReviewerWorkAssignmentService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentType,
    close_reviewer_work_assignment,
    create_reviewer_work_assignment,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_data_v2_manifest_v4 import CREATE_TABLES, GAME_TABLES
from game_predictor_api.storage.game_entity_locator import GameEntityLocator
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.models import Base
from game_predictor_api.storage.reviewer_work_assignment_repository import (
    OtherGamesOnlineAssignments,
    SqlAlchemyReviewerWorkAssignmentRepository,
)
from game_predictor_api.storage.schema_readiness import EXPECTED_ALEMBIC_HEAD
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_baseline_test"
# 0123 (e4c49020) is the first migration whose downgrade always refuses
# (GAME_DATA_V2_QUALIFICATION_CONSTRAINTS_DOWNGRADE_UNSUPPORTED); everything
# up to 0122 must still downgrade to an empty database.
LAST_REVISION_REVERSIBLE_TO_BASE = "0122_board_import_coverage_indexes"
# 0136 (D-467, TASK-0793) refuses its downgrade (CELL_RENDER_SPEC_DROP_IRREVERSIBLE);
# the migrations after it must downgrade to it and upgrade again.
LAST_IRREVERSIBLE_REVISION = "0136_drop_cell_render_spec"
# Storage control-plane tables written with raw SQL only (no ORM model).
STORAGE_CONTROL_TABLES = {
    "alembic_version",
    "game_deletion_batches",
    "game_deletion_operations",
    "game_storage_lifecycle_operations",
    "game_storage_locations",
    "game_storage_migrations",
    "game_storage_table_manifest",
    "game_storage_table_progress",
}
# D-448: public keeps catalog/control/shared tables, game_data_v2 holds exactly
# the manifest's game tables.
EXPECTED_PUBLIC_TABLES = (set(Base.metadata.tables) - set(GAME_TABLES)) | STORAGE_CONTROL_TABLES
EXPECTED_GAME_DATA_V2_TABLES = set(GAME_TABLES)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _quoted_identifier(identifier: str) -> str:
    if identifier != TEST_DATABASE_NAME:
        raise ValueError("Only the dedicated baseline test database may be managed.")
    return f'"{identifier}"'


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().owner_database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = _quoted_identifier(TEST_DATABASE_NAME)

    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _assert_head_schema(engine: Engine) -> None:
    assert _current_revision(engine) == EXPECTED_ALEMBIC_HEAD
    schema = inspect(engine)
    assert set(schema.get_table_names()) == EXPECTED_PUBLIC_TABLES
    assert set(schema.get_table_names(schema="game_data_v2")) == EXPECTED_GAME_DATA_V2_TABLES


def test_upgrade_downgrade_upgrade_cycle_on_postgres(isolated_database: URL) -> None:
    config = _migration_config(isolated_database)
    engine = create_engine(isolated_database, pool_pre_ping=True)

    try:
        command.upgrade(config, LAST_REVISION_REVERSIBLE_TO_BASE)
        assert _current_revision(engine) == LAST_REVISION_REVERSIBLE_TO_BASE

        engine.dispose()
        command.downgrade(config, "base")
        assert _current_revision(engine) is None
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        assert inspect(engine).get_table_names(schema="game_data_v2") == []

        engine.dispose()
        command.upgrade(config, "head")
        _assert_head_schema(engine)

        engine.dispose()
        command.downgrade(config, LAST_IRREVERSIBLE_REVISION)
        assert _current_revision(engine) == LAST_IRREVERSIBLE_REVISION
        with pytest.raises(Exception, match="CELL_RENDER_SPEC_DROP_IRREVERSIBLE"):
            command.downgrade(config, "-1")
        engine.dispose()
        assert _current_revision(engine) == LAST_IRREVERSIBLE_REVISION

        command.upgrade(config, "head")
        _assert_head_schema(engine)
    finally:
        engine.dispose()


def _provision_game(engine: Engine, *, game_id: UUID, code: str) -> None:
    """Create a catalog game and its partitions through the partition lifecycle."""

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.games (id, code, name, status, expected_layout_count) "
                "VALUES (:id, :code, :name, 'draft', 19809)"
            ),
            {"id": game_id, "code": code, "name": code},
        )
    with Session(engine) as session, session.begin():
        operation_id = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game_id, kind=GamePartitionLifecycleKind.PROVISION)
            .operation_id
        )
    for _ in range(len(CREATE_TABLES) + 8):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return
    raise AssertionError("provisioning did not reach done")


def _seed_reviewable_import(
    engine: Engine,
    factory: sessionmaker[Session],
    *,
    game_id: UUID,
    import_job_id: UUID,
    access_session_id: UUID,
    input_key: str,
    secret_byte: bytes,
    now: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.jobs ("
                "id, job_type, game_id, status, input_payload, input_key, "
                "progress_current, success_count, failure_count, review_count, attempt_count"
                ") VALUES ("
                ":id, 'import', :game_id, 'waiting_for_review', "
                "CAST(:payload AS jsonb), :input_key, 0, 0, 0, 0, 0"
                ")"
            ),
            {
                "id": import_job_id,
                "game_id": game_id,
                "payload": '{"schema_version":1,"import_kind":"image_directory"}',
                "input_key": input_key,
            },
        )
    with game_storage_scope(game_id), factory.begin() as session:
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        session.execute(
            text(
                "INSERT INTO reviewer_access_sessions ("
                "id, game_id, import_job_id, code_salt, code_hash, failed_attempts, "
                "created_at, expires_at"
                ") VALUES ("
                ":id, :game_id, :import_job_id, :code_salt, :code_hash, 0, "
                ":created_at, :expires_at"
                ")"
            ),
            {
                "id": access_session_id,
                "game_id": game_id,
                "import_job_id": import_job_id,
                "code_salt": secret_byte * 16,
                "code_hash": secret_byte * 32,
                "created_at": now,
                "expires_at": now + timedelta(hours=1),
            },
        )


def test_reviewer_work_assignments_enforce_one_active_row_and_keep_history(
    isolated_database: URL,
) -> None:
    config = _migration_config(isolated_database)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database, pool_pre_ping=True)
    factory = create_session_factory(engine)
    game_id = uuid4()
    import_job_id = uuid4()
    access_session_id = uuid4()
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)

    try:
        _provision_game(engine, game_id=game_id, code="assignment-test")
        _seed_reviewable_import(
            engine,
            factory,
            game_id=game_id,
            import_job_id=import_job_id,
            access_session_id=access_session_id,
            input_key="a" * 64,
            secret_byte=b"s",
            now=now,
        )
        first = create_reviewer_work_assignment(
            game_id=game_id,
            import_job_id=import_job_id,
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="test-owner",
            lease_expires_at=now + timedelta(seconds=30),
            created_at=now,
        )
        with game_storage_scope(game_id), factory.begin() as session:
            repository = SqlAlchemyReviewerWorkAssignmentRepository(session)
            first = repository.add(first)

        second = create_reviewer_work_assignment(
            game_id=game_id,
            import_job_id=import_job_id,
            assignment_type=ReviewerWorkAssignmentType.ONLINE,
            reviewer_access_session_id=access_session_id,
            lease_owner="test-owner-2",
            lease_expires_at=now + timedelta(seconds=31),
            created_at=now + timedelta(seconds=1),
        )
        # The database rejects a second open row for the import. The stable
        # error code of that rejection is asserted (as a known product bug) in
        # test_duplicate_active_assignment_reports_already_active.
        with (
            pytest.raises(ReviewerWorkAssignmentConflictError),
            game_storage_scope(game_id),
            factory.begin() as session,
        ):
            SqlAlchemyReviewerWorkAssignmentRepository(session).add(second)

        closed_at = now + timedelta(seconds=2)
        with game_storage_scope(game_id), factory.begin() as session:
            repository = SqlAlchemyReviewerWorkAssignmentRepository(session)
            persisted = repository.get_for_update(first.id)
            assert persisted is not None
            closed = close_reviewer_work_assignment(
                persisted,
                lease_token=persisted.lease_token,
                reason="owner_stopped",
                actor="test-owner",
                closed_at=closed_at,
            )
            repository.save_active(
                closed,
                expected_lease_token=persisted.lease_token,
            )

        with game_storage_scope(game_id), factory.begin() as session:
            repository = SqlAlchemyReviewerWorkAssignmentRepository(session)
            second = repository.add(second)
            rows = repository.list_for_import(import_job_id)

        assert len(rows) == 2
        assert rows[0].id == first.id
        assert rows[0].closed_at == closed_at
        assert rows[0].close_reason == "owner_stopped"
        assert rows[1].id == second.id
        assert rows[1].reviewer_access_session_id == access_session_id
        assert rows[1].closed_at is None
    finally:
        engine.dispose()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Product bug (TASK-0810): SqlAlchemyReviewerWorkAssignmentRepository.add maps "
        "the unique violation by the public index name "
        "uq_reviewer_work_assignments_active_import, but in game_data_v2 PostgreSQL "
        "reports the partition's generated index name (gpv2_<game>_<hash>_game_id_"
        "import_job_id_idx<N>), so the code is REVIEWER_ASSIGNMENT_PERSISTENCE_CONFLICT."
    ),
)
def test_duplicate_active_assignment_reports_already_active(isolated_database: URL) -> None:
    command.upgrade(_migration_config(isolated_database), "head")
    engine = create_engine(isolated_database, pool_pre_ping=True)
    factory = create_session_factory(engine)
    game_id = uuid4()
    import_job_id = uuid4()
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)

    try:
        _provision_game(engine, game_id=game_id, code="assignment-code-test")
        _seed_reviewable_import(
            engine,
            factory,
            game_id=game_id,
            import_job_id=import_job_id,
            access_session_id=uuid4(),
            input_key="b" * 64,
            secret_byte=b"t",
            now=now,
        )
        assignments = [
            create_reviewer_work_assignment(
                game_id=game_id,
                import_job_id=import_job_id,
                assignment_type=ReviewerWorkAssignmentType.LOCAL,
                lease_owner=f"test-owner-{index}",
                lease_expires_at=now + timedelta(seconds=30 + index),
                created_at=now + timedelta(seconds=index),
            )
            for index in range(2)
        ]
        with game_storage_scope(game_id), factory.begin() as session:
            SqlAlchemyReviewerWorkAssignmentRepository(session).add(assignments[0])
        with (
            pytest.raises(ReviewerWorkAssignmentConflictError) as conflict,
            game_storage_scope(game_id),
            factory.begin() as session,
        ):
            SqlAlchemyReviewerWorkAssignmentRepository(session).add(assignments[1])
        assert conflict.value.code == "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE"
    finally:
        engine.dispose()


def test_online_assignment_capacity_is_serialized_across_postgres_transactions(
    isolated_database: URL,
) -> None:
    config = _migration_config(isolated_database)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database, pool_pre_ping=True)
    factory = create_session_factory(engine)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    scopes = [(uuid4(), uuid4(), uuid4()) for _index in range(4)]

    class TrustedScopeRepository(SqlAlchemyReviewerWorkAssignmentRepository):
        def lock_scope(self, _game_id, _import_job_id) -> bool:
            return True

    try:
        for index, (game_id, import_job_id, access_session_id) in enumerate(scopes):
            _provision_game(engine, game_id=game_id, code=f"capacity-{index}")
            _seed_reviewable_import(
                engine,
                factory,
                game_id=game_id,
                import_job_id=import_job_id,
                access_session_id=access_session_id,
                input_key=f"{index + 1}" * 64,
                secret_byte=bytes([index + 1]),
                now=now,
            )

        # The cap spans every game (TASK-0797): each game's transaction counts
        # the other games' open online rows in their own bound sessions, as
        # create_app wires the repository.
        locator = GameEntityLocator(factory)
        other_games_online = OtherGamesOnlineAssignments(factory, locator)
        barrier = Barrier(len(scopes))

        def open_online(scope) -> str:
            game_id, import_job_id, access_session_id = scope
            barrier.wait(timeout=5)
            try:
                with game_storage_scope(game_id), factory.begin() as session:
                    service = ReviewerWorkAssignmentService(
                        TrustedScopeRepository(
                            session, locator, other_games_online=other_games_online
                        ),
                        now=lambda: now,
                    )
                    service.open(
                        game_id=game_id,
                        import_job_id=import_job_id,
                        assignment_type=ReviewerWorkAssignmentType.ONLINE,
                        reviewer_access_session_id=access_session_id,
                        lease_owner="postgres-capacity-test",
                        lease_expires_at=now + timedelta(minutes=10),
                    )
                return "opened"
            except ReviewerWorkAssignmentConflictError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(open_online, scopes))

        assert outcomes.count("opened") == 3
        assert outcomes.count("REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED") == 1
        with engine.connect() as connection:
            active_online_count = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM game_data_v2.reviewer_work_assignments "
                    "WHERE assignment_type = 'online' AND closed_at IS NULL"
                )
            )
        assert active_online_count == 3
    finally:
        engine.dispose()
