import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

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
from game_predictor_api.storage.reviewer_work_assignment_repository import (
    SqlAlchemyReviewerWorkAssignmentRepository,
)
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
HEAD_REVISION = "0065_remove_symbol_bootstrap"
TEST_DATABASE_NAME = "game_predictor_baseline_test"
EXPECTED_TABLES = {
    "alembic_version",
    "cell_observations",
    "cleanup_operations",
    "curated_image_import_batches",
    "curated_image_import_sources",
    "dataset_versions",
    "games",
    "game_grid_profile_activations",
    "game_symbol_model_activations",
    "grid_calibration_profiles",
    "grid_geometry_cohorts",
    "image_board_geometry_revisions",
    "image_board_geometry_pending",
    "image_file_executions",
    "image_import_job_files",
    "image_layout_staging_rows",
    "image_page_geometry_overrides",
    "image_pipeline_stage_results",
    "image_review_items",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_review_resolution_events",
    "image_selection_candidates",
    "image_selection_groups",
    "image_selection_manual_decisions",
    "image_selection_runs",
    "image_sequence_alternatives",
    "image_sequence_canonical",
    "image_sequence_source_override_events",
    "image_symbol_prediction_revisions",
    "image_verified_cohort_exports",
    "verified_training_cohort_items",
    "verified_training_cohorts",
    "jobs",
    "layout_import_normalized_rows",
    "layout_import_rows",
    "layout_payouts",
    "layouts",
    "mobile_release_games",
    "mobile_releases",
    "paylines",
    "payout_rules",
    "recognized_boards",
    "representative_ranking_activations",
    "representative_ranking_cohorts",
    "representative_ranking_iterations",
    "review_batches",
    "review_feedback_exports",
    "review_items",
    "review_resolutions",
    "reviewer_access_audit_events",
    "reviewer_access_sessions",
    "reviewer_work_assignments",
    "remote_manual_selection_audit_events",
    "remote_manual_selection_batches",
    "remote_manual_selection_collections",
    "remote_manual_selection_files",
    "remote_manual_selection_host_actions",
    "remote_manual_selection_operations",
    "remote_manual_selection_sessions",
    "remote_manual_selection_transfers",
    "rules_version_symbols",
    "rules_versions",
    "source_images",
    "symbol_reference_images",
    "symbols",
    "symbol_model_iterations",
    "worker_lane_runtime",
}

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _quoted_identifier(identifier: str) -> str:
    if identifier != TEST_DATABASE_NAME:
        raise ValueError("Only the dedicated baseline test database may be managed.")
    return f'"{identifier}"'


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


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


def test_upgrade_downgrade_upgrade_cycle_on_postgres(isolated_database: URL) -> None:
    config = _migration_config(isolated_database)
    engine = create_engine(isolated_database, pool_pre_ping=True)

    try:
        command.upgrade(config, "head")
        assert _current_revision(engine) == HEAD_REVISION
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES

        engine.dispose()
        command.downgrade(config, "base")
        assert _current_revision(engine) is None
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}

        engine.dispose()
        command.upgrade(config, "head")
        assert _current_revision(engine) == HEAD_REVISION
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_reviewer_work_assignments_enforce_one_active_row_and_keep_history(
    isolated_database: URL,
) -> None:
    config = _migration_config(isolated_database)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database, pool_pre_ping=True)
    game_id = uuid4()
    import_job_id = uuid4()
    access_session_id = uuid4()
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    job_payload = '{"schema_version":1,"import_kind":"image_directory"}'

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO games (id, code, name, status, expected_layout_count) "
                    "VALUES (:id, :code, :name, 'draft', 19809)"
                ),
                {"id": game_id, "code": "assignment-test", "name": "Assignment test"},
            )
            connection.execute(
                text(
                    "INSERT INTO jobs ("
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
                    "payload": job_payload,
                    "input_key": "a" * 64,
                },
            )
            connection.execute(
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
                    "code_salt": b"s" * 16,
                    "code_hash": b"h" * 32,
                    "created_at": now,
                    "expires_at": now + timedelta(hours=1),
                },
            )
        first = create_reviewer_work_assignment(
            game_id=game_id,
            import_job_id=import_job_id,
            assignment_type=ReviewerWorkAssignmentType.LOCAL,
            lease_owner="test-owner",
            lease_expires_at=now + timedelta(seconds=30),
            created_at=now,
        )
        with Session(engine, expire_on_commit=False) as session, session.begin():
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
        with (
            pytest.raises(ReviewerWorkAssignmentConflictError) as conflict,
            Session(engine) as session,
            session.begin(),
        ):
            SqlAlchemyReviewerWorkAssignmentRepository(session).add(second)
        assert conflict.value.code == "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE"

        closed_at = now + timedelta(seconds=2)
        with Session(engine, expire_on_commit=False) as session, session.begin():
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

        with Session(engine, expire_on_commit=False) as session, session.begin():
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


def test_online_assignment_capacity_is_serialized_across_postgres_transactions(
    isolated_database: URL,
) -> None:
    config = _migration_config(isolated_database)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database, pool_pre_ping=True)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    scopes = [(uuid4(), uuid4(), uuid4()) for _index in range(4)]
    job_payload = '{"schema_version":1,"import_kind":"image_directory"}'

    class TrustedScopeRepository(SqlAlchemyReviewerWorkAssignmentRepository):
        def lock_scope(self, _game_id, _import_job_id) -> bool:
            return True

    try:
        with engine.begin() as connection:
            for index, (game_id, import_job_id, access_session_id) in enumerate(scopes):
                connection.execute(
                    text(
                        "INSERT INTO games (id, code, name, status, expected_layout_count) "
                        "VALUES (:id, :code, :name, 'draft', 19809)"
                    ),
                    {
                        "id": game_id,
                        "code": f"capacity-{index}",
                        "name": f"Capacity {index}",
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO jobs ("
                        "id, job_type, game_id, status, input_payload, input_key, "
                        "progress_current, success_count, failure_count, "
                        "review_count, attempt_count"
                        ") VALUES ("
                        ":id, 'import', :game_id, 'waiting_for_review', "
                        "CAST(:payload AS jsonb), :input_key, 0, 0, 0, 0, 0"
                        ")"
                    ),
                    {
                        "id": import_job_id,
                        "game_id": game_id,
                        "payload": job_payload,
                        "input_key": f"{index + 1}" * 64,
                    },
                )
                connection.execute(
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
                        "code_salt": bytes([index + 1]) * 16,
                        "code_hash": bytes([index + 1]) * 32,
                        "created_at": now,
                        "expires_at": now + timedelta(hours=1),
                    },
                )

        barrier = Barrier(len(scopes))

        def open_online(scope) -> str:
            game_id, import_job_id, access_session_id = scope
            barrier.wait(timeout=5)
            try:
                with Session(engine, expire_on_commit=False) as session, session.begin():
                    service = ReviewerWorkAssignmentService(
                        TrustedScopeRepository(session),
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
                    "SELECT COUNT(*) FROM reviewer_work_assignments "
                    "WHERE assignment_type = 'online' AND closed_at IS NULL"
                )
            )
        assert active_online_count == 3
    finally:
        engine.dispose()
