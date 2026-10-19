"""Start an operation while another operation holds its board lock in PostgreSQL."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkFilterSelection,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    SqlAlchemySymbolCellReviewBulkOperationRepository,
    SqlAlchemySymbolCellReviewBulkOperationWorker,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageSymbolReviewBulkOperationModel,
    ImageSymbolReviewBulkTargetModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    JobModel,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import Engine, create_engine, event, func, select
from test_image_batch_store import (
    PIPELINE,
    _add_review_projection_source,
    _database_url,
    _image_job,
    _migration_config,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


@pytest.fixture
def locking_database() -> Iterator[Engine]:
    name = "game_predictor_task0897_" + uuid4().hex[:12]
    maintenance = create_engine(_database_url("postgres"), isolation_level="AUTOCOMMIT")
    url = _database_url(name)
    engine = create_engine(url, connect_args={"options": "-c statement_timeout=10000"})
    recording_capability_fixture = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        recording_capability_fixture.create_database(connection)
    try:
        recording_capability_fixture.provision()
        command.upgrade(_migration_config(url), "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            recording_capability_fixture.drop_database(connection)
        maintenance.dispose()


def _source(session_factory):
    now = datetime(2026, 10, 7, tzinfo=UTC)
    with session_factory() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            idempotency_key=uuid4(),
            code=uuid4().hex,
            name="Lock regression",
            status=GameStatus.ACTIVE,
        )
        symbol = catalog.create_symbol(
            game.id,
            mobile_code=1,
            code="first",
            name="First",
            image_path=None,
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )
        job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
        session.commit()
    store = SqlAlchemyImageBatchStore(session_factory)
    execution = store.register_file(
        job.id,
        source_checksum_sha256="1" * 64,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="locking.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(game.id), session_factory() as session, session.begin():
        _add_review_projection_source(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
            source_checksum="1" * 64,
            source_name="locking.jpg",
            position_index=0,
            sequence_number=1,
            status="pending",
            created_at=now,
        )
        session.get(JobModel, job.id).status = JobStatus.WAITING_FOR_REVIEW
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game.id)
    with game_storage_scope(game.id), session_factory() as session, session.begin():
        backfill = SqlAlchemyImageSymbolReviewRepository(session)
        backfill.start_or_resume_backfill(game.id)
        assert not backfill.backfill_next_batch(game.id, batch_size=50).has_more
        assert backfill.backfill_next_batch(game.id, batch_size=50).report.status == "ready"
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.game_id == game.id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        assert len(cells) == 15
        for cell in cells:
            cell.assigned_symbol_id = symbol.id
        session.flush()
        backfill.start_count_rebuild(game.id)
        assert not backfill.rebuild_count_projection_next_batch(game.id, batch_size=50)
        assert backfill.rebuild_count_projection_next_batch(game.id, batch_size=50)
        targets = tuple(
            SymbolCellReviewBulkExplicitTarget(
                cell_review_id=cell.id,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
            )
            for cell in cells
        )
        revision = session.get(ImageSymbolReviewStateModel, game.id).catalog_revision
    return game.id, symbol.id, targets, revision


def test_bulk_jobs_queue_then_execute_sequentially_after_reconnect(
    locking_database: Engine,
) -> None:
    """D-566 permits enqueue while the existing worker admission stays exclusive."""
    factory = create_session_factory(locking_database)
    game_id, _symbol, targets, _revision = _source(factory)

    def request(target):
        return SymbolCellReviewBulkRequest(
            action=SymbolCellReviewAction.APPROVE,
            target_symbol_id=None,
            explicit_targets=(target,),
            filter_selection=None,
            actor="admission-regression",
        )

    with game_storage_scope(game_id), factory() as session, session.begin():
        first, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game_id,
            request=request(targets[0]),
            idempotency_key=uuid4(),
        )
        assert created
    with game_storage_scope(game_id), factory() as session, session.begin():
        assert session.get(JobModel, first.job_id).status == JobStatus.CREATED
        second, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game_id,
            request=request(targets[1]),
            idempotency_key=uuid4(),
        )
        assert created and second.id != first.id
    worker_store = SqlAlchemyWorkerJobStore(factory)
    with game_storage_scope(game_id):
        claimed = worker_store.claim_next(
            worker_id="queue-regression",
            worker_version="task1071",
            lease_duration=timedelta(minutes=1),
            claimed_at=datetime.now(UTC),
            allowed_job_types=frozenset({JobType.IMAGE_SYMBOL_REVIEW_BULK}),
        )
        assert claimed is not None and claimed.id == first.job_id
        assert (
            worker_store.claim_next(
                worker_id="second-worker",
                worker_version="task1071",
                lease_duration=timedelta(minutes=1),
                claimed_at=datetime.now(UTC),
                allowed_job_types=frozenset({JobType.IMAGE_SYMBOL_REVIEW_BULK}),
            )
            is None
        )
    with game_storage_scope(game_id), factory() as session, session.begin():
        third, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game_id,
            request=request(targets[2]),
            idempotency_key=uuid4(),
        )
        assert created
    with game_storage_scope(game_id):
        progress = SqlAlchemySymbolCellReviewBulkOperationWorker(factory).process_next_batch(
            job=claimed, max_boards=1
        )
        assert progress.operation.applied_count == 1
        assert not progress.has_pending_targets
        assert claimed.lease_token is not None
        worker_store.complete(
            claimed.id, lease_token=claimed.lease_token, completed_at=datetime.now(UTC)
        )
        next_job = worker_store.claim_next(
            worker_id="queue-regression",
            worker_version="task1071",
            lease_duration=timedelta(minutes=1),
            claimed_at=datetime.now(UTC),
            allowed_job_types=frozenset({JobType.IMAGE_SYMBOL_REVIEW_BULK}),
        )
        assert next_job is not None and next_job.id == second.job_id
    with game_storage_scope(game_id), factory() as session:
        assert session.get(JobModel, third.job_id).status == JobStatus.CREATED


@pytest.mark.parametrize("mode", ["explicit-independent", "explicit-stale", "filter-stale"])
def test_start_while_worker_holds_board_revalidates_without_deadlock(
    locking_database: Engine,
    monkeypatch,
    mode: str,
) -> None:
    session_factory = create_session_factory(locking_database)
    game_id, symbol_id, targets, revision = _source(session_factory)

    def request(explicit=None, filtered=None):
        return SymbolCellReviewBulkRequest(
            action=SymbolCellReviewAction.APPROVE,
            target_symbol_id=None,
            explicit_targets=explicit,
            filter_selection=filtered,
            actor="lock-regression",
        )

    first_request = request(explicit=targets[:1])
    with game_storage_scope(game_id), session_factory() as session, session.begin():
        first, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game_id,
            request=first_request,
            idempotency_key=uuid4(),
        )
        assert created
        first_job = SqlAlchemyJobRepository(session).get_job(first.job_id)
    worker_store = SqlAlchemyWorkerJobStore(session_factory)
    first_job = worker_store.claim_next(
        worker_id="locking-regression",
        worker_version="task1018",
        lease_duration=timedelta(minutes=1),
        claimed_at=datetime.now(UTC),
        allowed_job_types=frozenset({first_job.job_type}),
    )
    assert first_job is not None and first_job.id == first.job_id
    second_request = (
        request(
            filtered=SymbolCellReviewBulkFilterSelection(
                symbol_id=symbol_id,
                state=SymbolCellReviewFilterState.PENDING,
                catalog_revision=revision,
            )
        )
        if mode == "filter-stale"
        else request(explicit=(targets[1 if mode == "explicit-independent" else 0],))
    )
    board_locked = Event()
    targets_inserting = Event()
    original_ready = SqlAlchemySymbolCellReviewMutationRepository._require_ready_state

    def worker_ready(self, *args, **kwargs):
        board_locked.set()
        assert targets_inserting.wait(5), "Second command never reached target insertion"
        return original_ready(self, *args, **kwargs)

    def before_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        if (
            statement.lstrip().startswith("INSERT")
            and "image_symbol_review_bulk_targets" in statement
        ):
            targets_inserting.set()

    monkeypatch.setattr(
        SqlAlchemySymbolCellReviewMutationRepository, "_require_ready_state", worker_ready
    )
    event.listen(locking_database, "before_cursor_execute", before_execute)
    second_key = uuid4()

    def run_worker():
        with game_storage_scope(game_id):
            return SqlAlchemySymbolCellReviewBulkOperationWorker(
                session_factory
            ).process_next_batch(
                job=first_job,
                max_boards=1,
            )

    def run_start():
        with game_storage_scope(game_id), session_factory() as session, session.begin():
            return SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
                game_id=game_id,
                request=second_request,
                idempotency_key=second_key,
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            worker_future = executor.submit(run_worker)
            assert board_locked.wait(5), "Worker never acquired the board"
            start_future = executor.submit(run_start)
            progress = worker_future.result(timeout=15)
            assert progress.operation.applied_count == 1
            assert not progress.has_pending_targets
            assert first_job.lease_token is not None
            completed = worker_store.complete(
                first_job.id, lease_token=first_job.lease_token, completed_at=datetime.now(UTC)
            )
            assert completed.status is JobStatus.COMPLETED
            if mode == "explicit-independent":
                second, created = start_future.result(timeout=15)
                assert created and second.target_count == 1 and second.id != first.id
            else:
                with pytest.raises(SymbolCellReviewError) as conflict:
                    start_future.result(timeout=15)
                assert conflict.value.code == (
                    "SYMBOL_CELL_REVIEW_BULK_FILTER_STALE"
                    if mode == "filter-stale"
                    else "SYMBOL_CELL_REVIEW_BULK_TARGET_STALE"
                )
    finally:
        event.remove(locking_database, "before_cursor_execute", before_execute)
    # Reconnect after both commits: no ghost job/operation/targets after a rejected start.
    with game_storage_scope(game_id), session_factory() as session, session.begin():
        operations = session.scalars(
            select(ImageSymbolReviewBulkOperationModel).where(
                ImageSymbolReviewBulkOperationModel.game_id == game_id
            )
        ).all()
        assert len(operations) == (2 if mode == "explicit-independent" else 1)
        assert session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewBulkTargetModel)
            .where(
                ImageSymbolReviewBulkTargetModel.operation_id.in_(
                    [operation.id for operation in operations]
                )
            )
        ) == len(operations)
        assert session.scalar(
            select(func.count()).select_from(JobModel).where(JobModel.game_id == game_id)
        ) == 1 + len(operations)
        repeated, created = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game_id,
            request=first_request,
            idempotency_key=next(
                operation.idempotency_key for operation in operations if operation.id == first.id
            ),
        )
        assert not created and repeated.id == first.id


def test_simultaneous_retry_creates_only_one_job_after_reconnect(locking_database: Engine) -> None:
    session_factory = create_session_factory(locking_database)
    game_id, _symbol_id, targets, _revision = _source(session_factory)
    request = SymbolCellReviewBulkRequest(
        action=SymbolCellReviewAction.APPROVE,
        target_symbol_id=None,
        explicit_targets=targets[:1],
        filter_selection=None,
        actor="retry-regression",
    )
    key = uuid4()
    barrier = Barrier(2)

    def start():
        with game_storage_scope(game_id), session_factory() as session, session.begin():
            barrier.wait(timeout=5)
            return SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
                game_id=game_id,
                request=request,
                idempotency_key=key,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(start) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(created for _operation, created in results) == [False, True]
    assert results[0][0].id == results[1][0].id
    with game_storage_scope(game_id), session_factory() as session, session.begin():
        repository = SqlAlchemySymbolCellReviewBulkOperationRepository(session)
        replay, created = repository.start(game_id=game_id, request=request, idempotency_key=key)
        assert not created and replay.id == results[0][0].id
        assert (
            session.scalar(
                select(func.count()).select_from(JobModel).where(JobModel.game_id == game_id)
            )
            == 2
        )
        with pytest.raises(SymbolCellReviewError) as conflict:
            repository.start(
                game_id=game_id,
                request=SymbolCellReviewBulkRequest(
                    action=SymbolCellReviewAction.MARK_UNREADABLE,
                    target_symbol_id=None,
                    explicit_targets=targets[:1],
                    filter_selection=None,
                    actor="retry-regression",
                ),
                idempotency_key=key,
            )
        assert conflict.value.code == "SYMBOL_CELL_REVIEW_BULK_IDEMPOTENCY_CONFLICT"
