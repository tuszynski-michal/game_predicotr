"""Isolated PostgreSQL coverage of SqlAlchemyBoardImportCoverageRepository.

Builds minimal-but-constraint-valid rows directly (mirrors the fixture style
of test_resumable_game_deletion.py) rather than replaying the full worker
pipeline, since TASK-0629 only owns the read side (D-437).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from _virtual_board_fixtures import ensure_source_geometry, virtual_board_columns
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
    OperationalImageReviewService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_import_coverage import MissingReason
from game_predictor_api.main import create_app
from game_predictor_api.storage import grid_diagnostics_repository
from game_predictor_api.storage.board_import_coverage_repository import (
    SqlAlchemyBoardImportCoverageRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_data_v2_manifest_v14 import VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task1010_" + uuid4().hex[:12] + "_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    assert name.endswith("_test") and name != url.database
    # Print only the isolated target, never user/password-bearing DSNs.
    print(f"PostgreSQL fixture target: {url.host}:{url.port}/{name}; credentials omitted")
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    recording_capability_fixture = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        recording_capability_fixture.create_database(connection)
    try:
        recording_capability_fixture.provision()
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        with engine.begin() as connection:
            role = "coverage_" + uuid4().hex[:12]
            recording_capability_fixture.create_runtime_role(connection, role)
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
            )
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            recording_capability_fixture.drop_database(connection)
        maintenance.dispose()


# Every scenario routes its game to game_data_v2: the public game store and
# its generation-1 registry rows were removed by migration 0125 (D-448), and
# the router rejects a registry row with generation < 2.
_V2_PARTITIONED_TABLES = (
    "source_images",
    "image_source_geometry_revisions",
    "recognized_boards",
    "image_review_items",
    "image_sequence_canonical",
    "image_import_job_files",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_board_geometry_pending",
)


def _provision_v2_storage_location(session: Session, *, game_id: UUID) -> None:
    """Route a game to game_data_v2 and create its partitions for this test.

    Mirrors the fixtures in test_game_storage_routing_postgres.py: a real
    cutover also runs storage_generation-tracking migration steps this
    fixture skips, but the routing behavior under test only needs the
    registry row, live partitions for the tables this scenario touches, and
    GameStorageRouter.bind() to establish the session's search_path/RLS scope
    before any insert.
    """

    session.execute(
        text(
            "INSERT INTO public.game_storage_locations "
            "(game_id, store_schema, generation, manifest_version, status, revision) "
            "VALUES (:game_id, 'game_data_v2', 2, :version, 'active', 0)"
        ),
        {"game_id": game_id, "version": VERSION},
    )
    for table in _V2_PARTITIONED_TABLES:
        session.execute(
            text(
                f"CREATE TABLE game_data_v2.{table}_g_{game_id.hex} "
                f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game_id}')"
            )
        )
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)


def _import_job(session: Session, *, game_id: UUID, status: str = "processing") -> JobModel:
    job = JobModel(
        game_id=game_id,
        job_type="import",
        status=status,
        input_payload={"import_kind": "image_directory"},
        input_key=uuid4().hex,
        **(
            {
                "execution_slot": 1,
                "lease_owner": "fixture",
                "lease_token": uuid4().hex,
                "lease_expires_at": datetime.now(UTC),
                "heartbeat_at": datetime.now(UTC),
            }
            if status == "processing"
            else {}
        ),
    )
    session.add(job)
    session.flush()
    return job


def _source(
    session: Session, *, job: JobModel, relative_path: str, order_index: int = 0
) -> SourceImageModel:
    checksum = uuid4().hex * 2
    session.add(
        ImageFileExecutionModel(
            file_execution_key=checksum,
            source_checksum_sha256=checksum,
            pipeline_fingerprint="b" * 64,
            checkpoint_payload={},
            status="waiting_for_review",
            review_required=True,
        )
    )
    session.flush()
    # The project_image_review_queue_insert() trigger requires every
    # image_review_items row to resolve a (job, file_execution_key) source
    # order association, or it raises a CheckViolation on insert.
    session.add(
        ImageImportJobFileModel(
            job_id=job.id,
            file_execution_key=checksum,
            order_index=order_index,
            source_relative_path=relative_path,
            workflow_checkpoint_payload={},
            workflow_status="waiting_for_review",
            review_required=True,
        )
    )
    source = SourceImageModel(
        import_job_id=job.id,
        file_execution_key=checksum,
        relative_path=relative_path,
        checksum_sha256=checksum,
        width=100,
        height=100,
        status="waiting_for_review",
    )
    session.add(source)
    session.flush()
    return source


def _add_complete_board(
    session: Session,
    *,
    game_id: UUID,
    job: JobModel,
    source: SourceImageModel,
    position: int,
    sequence_number: int,
    review_status: str = "pending",
) -> ImageReviewItemModel:
    # D-467 S6 (TASK-0796): every board is a virtual render of its source.
    source_geometry = ensure_source_geometry(
        session,
        game_id=game_id,
        source=source,
        sequence_range_start=sequence_number - position,
        created_at=datetime.now(UTC),
    )
    board = RecognizedBoardModel(
        source_image_id=source.id,
        position_index=position,
        sequence_number_raw=str(sequence_number),
        sequence_number=sequence_number,
        sequence_confidence=1,
        board_geometry={},
        **virtual_board_columns(source_geometry),
        cells_prediction={},
        completeness_status="complete",
        board_confidence=1,
        pipeline_fingerprint="b" * 64,
        status="pending_review",
    )
    session.add(board)
    session.flush()
    item = ImageReviewItemModel(
        game_id=game_id,
        import_job_id=job.id,
        recognized_board_id=board.id,
        sequence_number=sequence_number,
        status=review_status,
        snapshot={},
        **(
            {}
            if review_status == "pending"
            else {
                "resolved_value": {"action": review_status},
                "resolved_by": "fixture",
                "resolved_at": datetime.now(UTC),
                "resolution_revision": 1,
            }
        ),
    )
    session.add(item)
    session.flush()
    return item


def _add_partial_board(
    session: Session,
    *,
    game_id: UUID,
    job: JobModel,
    source: SourceImageModel,
    position: int,
    sequence_number: int,
) -> ImageReviewItemModel:
    # D-467 S6 (TASK-0796): every board is a virtual render of its source.
    source_geometry = ensure_source_geometry(
        session,
        game_id=game_id,
        source=source,
        sequence_range_start=sequence_number - position,
        created_at=datetime.now(UTC),
    )
    board = RecognizedBoardModel(
        source_image_id=source.id,
        position_index=position,
        sequence_number_raw=str(sequence_number),
        sequence_number=sequence_number,
        sequence_confidence=1,
        board_geometry={},
        **virtual_board_columns(source_geometry),
        cells_prediction={},
        completeness_status="pending_partial",
        unavailable_cell_indices=[0],
        board_confidence=1,
        pipeline_fingerprint="b" * 64,
        status="pending_review",
    )
    session.add(board)
    session.flush()
    item = ImageReviewItemModel(
        game_id=game_id,
        import_job_id=job.id,
        recognized_board_id=board.id,
        sequence_number=sequence_number,
        status="pending",
        snapshot={},
    )
    session.add(item)
    session.flush()
    return item


def test_pending_complete_board_without_canonical_is_added(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-1", name="Coverage 1", expected_layout_count=20)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        source = _source(session, job=job, relative_path="seq_1-1.jpg")
        _add_complete_board(
            session, game_id=game.id, job=job, source=source, position=0, sequence_number=1
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert report.counts.added == 1
        assert report.counts.missing == 19
        assert all(segment.start > 1 or segment.end < 1 for segment in report.page.segments)


def test_partial_only_board_is_missing_with_reason(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-2", name="Coverage 2", expected_layout_count=10)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        source = _source(session, job=job, relative_path="seq_5-5.jpg")
        _add_partial_board(
            session, game_id=game.id, job=job, source=source, position=0, sequence_number=5
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        matching = [s for s in report.page.segments if s.start <= 5 <= s.end]
        assert len(matching) == 1
        assert matching[0].state == MissingReason.PARTIAL_SOURCE.value
        assert report.missing_by_reason[MissingReason.PARTIAL_SOURCE] == 1


def test_number_without_any_trace_is_no_source(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-3", name="Coverage 3", expected_layout_count=5)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert report.counts.added == 0
        assert report.counts.missing == 5
        assert [(s.start, s.end, s.state) for s in report.page.segments] == [
            (1, 5, MissingReason.NO_SOURCE.value)
        ]


def test_gaps_at_start_middle_and_end(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-4", name="Coverage 4", expected_layout_count=20)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        for order_index, sequence_number in enumerate([*range(3, 8), *range(10, 18)]):
            source = _source(
                session,
                job=job,
                relative_path=f"seq_{sequence_number}.jpg",
                order_index=order_index,
            )
            _add_complete_board(
                session,
                game_id=game.id,
                job=job,
                source=source,
                position=0,
                sequence_number=sequence_number,
            )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert [(s.start, s.end) for s in report.page.segments] == [(1, 2), (8, 9), (18, 20)]


def test_active_import_file_marks_in_progress_not_no_source(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-5", name="Coverage 5", expected_layout_count=20)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="processing")
        checksum = uuid4().hex * 2
        session.add(
            ImageFileExecutionModel(
                file_execution_key=checksum,
                source_checksum_sha256=checksum,
                pipeline_fingerprint="b" * 64,
                checkpoint_payload={},
                status="processing",
                review_required=False,
            )
        )
        session.flush()
        session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=checksum,
                order_index=0,
                source_relative_path="seq_8-12.jpg",
                workflow_checkpoint_payload={},
                workflow_status="processing",
                review_required=False,
            )
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert [(s.start, s.end, s.state) for s in report.page.segments] == [
            (1, 7, MissingReason.NO_SOURCE.value),
            (8, 12, MissingReason.IMPORT_IN_PROGRESS.value),
            (13, 20, MissingReason.NO_SOURCE.value),
        ]
        assert report.notices.active_import_job_count == 1


def test_geometry_pending_resolution_creates_item_and_stays_added(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-6", name="Coverage 6", expected_layout_count=5)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        source = _source(session, job=job, relative_path="seq_2-2.jpg")

        session.add(
            ImageBoardGeometryPendingModel(
                game_id=game.id,
                import_job_id=job.id,
                source_image_id=source.id,
                sequence_number=2,
                position_index=0,
                source_checksum_sha256="d" * 64,
                source_relative_path="seq_2-2.jpg",
                status="resolved",
                reason_code="incomplete_lattice",
                processing_manifest_checksum_sha256="e" * 64,
                processing_manifest_relative_path="manifests/2.json",
                pipeline_fingerprint_sha256="b" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                resolved_geometry_revision=1,
                resolved_at=datetime.now(UTC),
                superseded_at=None,
            )
        )
        _add_complete_board(
            session, game_id=game.id, job=job, source=source, position=0, sequence_number=2
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert not any(segment.start <= 2 <= segment.end for segment in report.page.segments)
        assert report.counts.added == 1


def test_duplicate_supersession_counts_distinct_and_totals_match_expected(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-7", name="Coverage 7", expected_layout_count=6)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job_a = _import_job(session, game_id=game.id, status="completed")
        source_a = _source(session, job=job_a, relative_path="seq_1-6.jpg")
        for sequence_number in range(1, 7):
            _add_complete_board(
                session,
                game_id=game.id,
                job=job_a,
                source=source_a,
                position=sequence_number - 1,
                sequence_number=sequence_number,
                review_status="superseded" if sequence_number == 3 else "pending",
            )
        session.add(
            ImageSequenceCanonicalModel(
                game_id=game.id,
                sequence_number=3,
                review_item_id=(
                    session.query(ImageReviewItemModel.id)
                    .filter(
                        ImageReviewItemModel.game_id == game.id,
                        ImageReviewItemModel.sequence_number == 3,
                    )
                    .order_by(ImageReviewItemModel.created_at.desc())
                    .first()[0]
                ),
                recognized_board_id=(
                    session.query(ImageReviewItemModel.recognized_board_id)
                    .filter(
                        ImageReviewItemModel.game_id == game.id,
                        ImageReviewItemModel.sequence_number == 3,
                    )
                    .first()[0]
                ),
                import_job_id=job_a.id,
                source_image_id=source_a.id,
                source_checksum_sha256="f" * 64,
                board_checksum_sha256="b" * 64,
                status="accepted",
                resolution_revision=1,
                geometry_revision=0,
            )
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert report.counts.added == 6
        assert report.counts.missing == 0
        assert report.counts.added + report.counts.missing == report.counts.expected


def test_numbers_above_expected_are_out_of_range_not_added(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-8", name="Coverage 8", expected_layout_count=3)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        source = _source(session, job=job, relative_path="seq_9-9.jpg")
        item = _add_complete_board(
            session, game_id=game.id, job=job, source=source, position=0, sequence_number=9
        )
        session.add(
            ImageSequenceCanonicalModel(
                game_id=game.id,
                sequence_number=9,
                review_item_id=item.id,
                recognized_board_id=item.recognized_board_id,
                import_job_id=job.id,
                source_image_id=source.id,
                source_checksum_sha256="f" * 64,
                board_checksum_sha256="b" * 64,
                status="accepted",
                resolution_revision=1,
                geometry_revision=0,
            )
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert report.counts.out_of_range == 1
        assert report.counts.added == 0
        assert [(s.start, s.end) for s in report.page.segments] == [(1, 3)]


def test_pending_complete_board_in_a_game_data_v2_routed_game_is_added(
    database: Engine,
) -> None:
    """Regression: board_import_coverage must bind GameStorageRouter itself.

    None of this router's endpoints live under /admin/games/{gameId}/..., so
    the app-wide bind_game_storage_request middleware never fires for them,
    and plain `select(...).where(Model.col == value)` queries never populate
    execute_state.parameters, so the ORM auto-detection fallback in
    database.py never fires either. Without an explicit
    GameStorageRouter().bind() call in the repository itself, every query
    here silently reads the empty public schema instead of game_data_v2 and
    reports a fully game_data_v2-routed game as 100% missing no matter how
    much real, pending, fully-cut data it has.
    """
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="cov-9", name="Coverage 9", expected_layout_count=5)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        job = _import_job(session, game_id=game.id, status="completed")
        source = _source(session, job=job, relative_path="seq_1-1.jpg")
        _add_complete_board(
            session, game_id=game.id, job=job, source=source, position=0, sequence_number=1
        )

    with Session(database) as session:
        repo = SqlAlchemyBoardImportCoverageRepository(session)
        report = repo.board_import_coverage(game.id, view="missing")
        assert report is not None
        assert report.counts.added == 1
        assert report.counts.missing == 4
        assert all(segment.start > 1 or segment.end < 1 for segment in report.page.segments)


def _diagnostics_slot(
    session: Session,
    *,
    game: GameModel,
    job: JobModel,
    source: SourceImageModel,
    rejected: bool,
    position_index: int,
) -> None:
    session.add(
        ImageBoardGeometryPendingModel(
            game_id=game.id,
            import_job_id=job.id,
            source_image_id=source.id,
            sequence_number=2,
            position_index=position_index,
            source_checksum_sha256=source.checksum_sha256,
            source_relative_path=source.relative_path,
            status="rejected" if rejected else "pending",
            reason_code="incomplete_lattice",
            processing_manifest_checksum_sha256="e" * 64,
            processing_manifest_relative_path="manifests/2.json",
            pipeline_fingerprint_sha256="b" * 64,
            expected_geometry_revision=0,
            expected_review_resolution_revision=0,
            rejection_reason="cropped" if rejected else None,
            rejected_at=datetime.now(UTC) if rejected else None,
            rejected_by="fixture" if rejected else None,
        )
    )


def test_rejected_slot_default_get_and_waiting_priority(database: Engine) -> None:
    with Session(database, expire_on_commit=False) as seed, seed.begin():
        game = GameModel(code="cov-rejected-1010", name="Rejected slot", expected_layout_count=3)
        seed.add(game)
        seed.flush()
        _provision_v2_storage_location(seed, game_id=game.id)
        job = _import_job(seed, game_id=game.id, status="completed")
        source = _source(seed, job=job, relative_path="seq_1-3.jpg")
        _add_complete_board(
            seed, game_id=game.id, job=job, source=source, position=0, sequence_number=1
        )
        _diagnostics_slot(seed, game=game, job=job, source=source, rejected=True, position_index=1)

    class NoopOperationalRepository(OperationalImageReviewRepository):
        pass

    settings = ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": database.url.render_as_string(hide_password=False),
            "GAME_PREDICTOR_OWNER_DATABASE_URL": database.url.render_as_string(hide_password=False),
        }
    )
    assert make_url(settings.database_url).database.endswith("_test")
    url = f"/api/v1/admin/image-review-items/board-import-coverage/{game.id}"
    with create_session_factory(database)() as session:
        service = OperationalImageReviewService(
            NoopOperationalRepository(),
            board_import_coverage_repository=SqlAlchemyBoardImportCoverageRepository(session),
        )
        with TestClient(
            create_app(settings, image_review_service_dependency=lambda: service)
        ) as client:
            response = client.get(url)
            assert response.status_code == 200
            body = response.json()
            assert body["diagnostics"] is None
            assert body["counts"]["added"] == 1
            assert body["missingByReason"]["rejected"] == 1
            assert any(
                s["start"] <= 2 <= s["end"] and s["state"] == "rejected" for s in body["segments"]
            )

    with Session(database) as seed, seed.begin():
        GameStorageRouter().bind(seed, game.id, intent=GameStorageIntent.WRITE)
        pending_source = _source(seed, job=job, relative_path="seq_2-2.jpg", order_index=1)
        _diagnostics_slot(
            seed, game=game, job=job, source=pending_source, rejected=False, position_index=0
        )
    with create_session_factory(database)() as session:
        report = SqlAlchemyBoardImportCoverageRepository(session).board_import_coverage(
            game.id, view="missing"
        )
        assert report is not None
        assert report.counts.added == 1
        assert report.missing_by_reason[MissingReason.WAITING_FOR_GEOMETRY] == 1
        assert report.missing_by_reason[MissingReason.REJECTED] == 0


def test_diagnostics_snapshot_rls_union_and_separate_request_session(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    application_role_mode = OwnedRecordingCapability.for_engine(database).runtime_role_receipt
    assert application_role_mode is not None and application_role_mode.created_here
    game_ids = []
    for index in range(2):
        with Session(database, expire_on_commit=False) as seed, seed.begin():
            game = GameModel(
                code=f"cov-snapshot-1010-{index}", name="Snapshot", expected_layout_count=6
            )
            seed.add(game)
            seed.flush()
            _provision_v2_storage_location(seed, game_id=game.id)
            job = _import_job(seed, game_id=game.id, status="completed")
            source = _source(seed, job=job, relative_path="seq_1-6.jpg")
            item = _add_complete_board(
                seed, game_id=game.id, job=job, source=source, position=0, sequence_number=1
            )
            if index == 0:
                seed.add(
                    ImageSequenceCanonicalModel(
                        game_id=game.id,
                        sequence_number=1,
                        review_item_id=item.id,
                        recognized_board_id=item.recognized_board_id,
                        import_job_id=job.id,
                        source_image_id=source.id,
                        source_checksum_sha256=source.checksum_sha256,
                        board_checksum_sha256="b" * 64,
                        status="accepted",
                        resolution_revision=1,
                        geometry_revision=0,
                    )
                )
            else:
                _add_complete_board(
                    seed, game_id=game.id, job=job, source=source, position=1, sequence_number=2
                )
            game_ids.append(game.id)

    original = grid_diagnostics_repository.read_grid_diagnostics
    observed = []

    def snapshot_application_role(connection: Connection) -> None:
        # Production connects as the application role. The fixture logs in as
        # owner for seeding, so enforce the real NOLOGIN test role for every
        # later transaction, including the snapshot's plain Session.
        connection.exec_driver_sql(f'SET LOCAL ROLE "{application_role_mode.role}"')

    @contextmanager
    def application_identity() -> Iterator[None]:
        event.listen(database, "begin", snapshot_application_role)
        try:
            yield
        finally:
            event.remove(database, "begin", snapshot_application_role)

    request_factory = create_session_factory(database)
    with application_identity(), request_factory() as request:
        request_connection = request.connection()
        request_transaction = request.get_transaction()
        assert request.scalar(text("SELECT current_setting('transaction_read_only')")) == "off"

        def inspect_snapshot(snapshot: Session, **kwargs):
            assert type(snapshot) is Session
            assert snapshot is not request
            assert snapshot.connection() is not request_connection
            state = snapshot.execute(
                text("""
                SELECT current_setting('transaction_isolation'),
                  current_setting('transaction_read_only'),
                  current_setting('game_predictor.game_id'),
                  current_setting('statement_timeout'), current_user,
                  (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user)
            """)
            ).one()
            assert state[:4] == ("repeatable read", "on", str(game_ids[0]), "30s")
            assert state[4] == application_role_mode.role
            assert state[5] is False
            # Deliberately omit a same-game predicate: actual RLS must suppress
            # the other game's seeded boards, not just the report's WHERE clause.
            assert (
                snapshot.scalar(
                    text(
                        "SELECT count(*) FROM game_data_v2.recognized_boards WHERE game_id=:foreign"
                    ),
                    {"foreign": game_ids[1]},
                )
                == 0
            )
            observed.append(state)
            return original(snapshot, **kwargs)

        monkeypatch.setattr(grid_diagnostics_repository, "read_grid_diagnostics", inspect_snapshot)
        report = SqlAlchemyBoardImportCoverageRepository(request).board_import_coverage(
            game_ids[0], view="missing", include_diagnostics=True
        )
        assert report is not None and report.diagnostics is not None
        data = report.diagnostics
        assert report.counts.added == 1
        assert (
            data.qualifying_review_sequences
            + data.canonical_sequences
            - data.canonical_review_overlap
            == 1
        )
        assert data.review_rows_by_status == {"pending": 1}
        assert len(observed) == 1
        assert request.get_transaction() is request_transaction
        assert request.scalar(text("SELECT current_setting('transaction_read_only')")) == "off"
        assert (
            request.scalar(text("SELECT current_setting('transaction_isolation')"))
            == "read committed"
        )
        request.execute(
            text("UPDATE public.games SET name='Request remains writable' WHERE id=:id"),
            {"id": game_ids[0]},
        )
        request.rollback()
