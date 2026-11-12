"""Disposable PostgreSQL: the default learning scope keeps labelled and cohort imports only."""

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.grid_correction_learning import labelled_import_scope
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def _source(connection, game: UUID, job: UUID) -> UUID:
    source = uuid4()
    connection.execute(
        text("""
        INSERT INTO source_images (id, game_id, import_job_id, file_execution_key,
         relative_path, checksum_sha256, width, height, status)
        VALUES (:id, :game, :job, :key, :path, :sha, 1200, 900, 'waiting_for_review')"""),
        {
            "id": source,
            "game": game,
            "job": job,
            "key": uuid4().hex * 2,
            "path": f"originals/{uuid4().hex}.jpg",
            "sha": uuid4().hex * 2,
        },
    )
    return source


def _board(
    connection, game: UUID, source: UUID, approved_by: str | None, position: int = 0
) -> None:
    connection.execute(
        text("""
        INSERT INTO recognized_boards (id, game_id, source_image_id, position_index,
         sequence_number_raw, sequence_confidence, board_geometry, cells_prediction,
         board_confidence, pipeline_fingerprint, status, geometry_revision,
         approved_geometry_revision, geometry_approved_by, geometry_approved_at,
         source_geometry_revision_id, geometry_engine_name, geometry_engine_version,
         geometry_checksum_sha256)
        VALUES (:id, :game, :source, :position, '1', 1.0, '{}'::jsonb, '{}'::jsonb, 1.0, :sha,
         'pending_review', 2, :approved_revision, :approved_by, :approved_at,
         :revision, 'manual_v1', 'v1', :sha)"""),
        {
            "id": uuid4(),
            "game": game,
            "source": source,
            "position": position,
            "sha": "a" * 64,
            "revision": uuid4(),
            "approved_revision": None if approved_by is None else 2,
            "approved_by": approved_by,
            "approved_at": None if approved_by is None else datetime.now(UTC),
        },
    )


def test_default_scope_keeps_human_labels_and_prior_cohort_imports():
    with application_role_database("t1199", ("scope",)) as db:
        game = next(iter(db.games.values()))
        human, member, automatic, empty = (uuid4() for _ in range(4))
        with db.owner_engine.begin() as connection:
            # Fixture rows only: FK targets and derived-row triggers are out of scope.
            connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
            connection.exec_driver_sql("SET LOCAL search_path = game_data_v2, public")
            _board(connection, game, _source(connection, game, human), "local-admin")
            _board(connection, game, _source(connection, game, human), None)
            connection.execute(
                text("""
                INSERT INTO grid_training_cohort_members (game_id, cohort_id, source_id, ordinal)
                VALUES (:game, :cohort, :source, 0)"""),
                {"game": game, "cohort": uuid4(), "source": _source(connection, game, member)},
            )
            automatic_source = _source(connection, game, automatic)
            _board(connection, game, automatic_source, "system:v3-engine-acceptance-v1")
            _board(connection, game, automatic_source, "worker:grid", 1)
            _board(connection, game, _source(connection, game, empty), None)
            # A stale approval (geometry moved on) is not a current human label.
            connection.execute(
                text("""
                UPDATE recognized_boards SET geometry_revision = 3
                WHERE game_id = :game AND geometry_approved_by = 'worker:grid'"""),
                {"game": game},
            )
        factory = create_session_factory(db.app_engine)
        with game_storage_scope(game), factory() as session:
            scope = labelled_import_scope(session, game)
        assert scope == sorted([str(human), str(member)])
