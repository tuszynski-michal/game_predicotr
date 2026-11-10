"""Real board writes, bounded recounts and an unlocked-attestation revision fence."""

import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.verified_training_cohorts import VerifiedTrainingCohortService
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    SqlAlchemySymbolCellReviewBulkOperationRepository,
    SqlAlchemySymbolCellReviewBulkOperationWorker,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
)
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
)
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import event, select, text
from test_symbol_review_bulk_start_locking_postgres import _source, locking_database

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Isolated PostgreSQL only"
)


@pytest.fixture(scope="module")
def database():
    yield from locking_database.__wrapped__()


def _claimed(factory, game, targets):
    request = SymbolCellReviewBulkRequest(
        action=SymbolCellReviewAction.APPROVE,
        target_symbol_id=None,
        explicit_targets=targets,
        filter_selection=None,
        actor="performance-regression",
    )
    with game_storage_scope(game), factory() as session, session.begin():
        operation, _ = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game, request=request, idempotency_key=uuid4()
        )
    with game_storage_scope(game):
        job = SqlAlchemyWorkerJobStore(factory).claim_next(
            worker_id="task1177",
            worker_version="task1177",
            lease_duration=timedelta(minutes=1),
            claimed_at=datetime.now(UTC),
            allowed_job_types=frozenset({JobType.IMAGE_SYMBOL_REVIEW_BULK}),
        )
    assert job is not None and job.id == operation.job_id
    return job


def _complete(factory, job):
    assert job.lease_token is not None
    SqlAlchemyWorkerJobStore(factory).complete(
        job.id, lease_token=job.lease_token, completed_at=datetime.now(UTC)
    )


def test_queued_bulk_blocks_freeze_before_any_attestation_or_artifact_write(database):
    factory = create_session_factory(database)
    game, _, targets, _ = _source(factory)
    request = SymbolCellReviewBulkRequest(
        action=SymbolCellReviewAction.APPROVE,
        target_symbol_id=None,
        explicit_targets=targets[:1],
        filter_selection=None,
        actor="performance-regression",
    )
    with game_storage_scope(game), factory() as session, session.begin():
        operation, _ = SqlAlchemySymbolCellReviewBulkOperationRepository(session).start(
            game_id=game, request=request, idempotency_key=uuid4()
        )
    with game_storage_scope(game), factory() as session:
        cohorts = Mock()
        cohorts.find_by_idempotency.return_value = None
        artifacts, symbols = Mock(), Mock()
        service = VerifiedTrainingCohortService(
            SqlAlchemyOperationalImageReviewRepository(session), cohorts, artifacts, symbols
        )
        with pytest.raises(ImageReviewConflictError) as error:
            service.freeze(
                game_id=game,
                idempotency_key=uuid4(),
                created_by="operator",
                expected_manifest_checksum_sha256="a" * 64,
            )
        assert error.value.code == "VERIFIED_TRAINING_COHORT_HEAVY_JOB_ACTIVE"
        assert not symbols.mock_calls and not artifacts.mock_calls
        cohorts.save.assert_not_called()
        session.get(JobModel, operation.job_id).status = JobStatus.CANCELLED
        session.commit()


@pytest.mark.parametrize("cells_per_board", [1, 15])
def test_real_bulk_recounts_once_per_boundary_and_replay_creates_no_events(
    database, cells_per_board
):
    factory = create_session_factory(database)
    game, _, targets, _ = _source(factory, board_count=3)
    selected = targets[:3] if cells_per_board == 1 else targets
    job = _claimed(factory, game, selected)
    counts = []
    statements = []

    def trace(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)
        if (
            "image_symbol_review_bulk_targets" in statement
            and "GROUP BY" in statement
            and "count(" in statement
        ):
            counts.append(statement)

    event.listen(database, "before_cursor_execute", trace)
    try:
        started = perf_counter()
        with game_storage_scope(game):
            worker = SqlAlchemySymbolCellReviewBulkOperationWorker(factory)
            progress = worker.process_next_batch(job=job, max_boards=3)
        elapsed = perf_counter() - started
    finally:
        event.remove(database, "before_cursor_execute", trace)
    assert progress.operation.applied_count == len(selected)
    assert not progress.has_pending_targets
    assert len(counts) == 2  # Three boards no longer mean three whole-target rescans.
    projection_deletes = [
        statement
        for statement in statements
        if statement.startswith("DELETE FROM") and "image_board_search_fast_documents" in statement
    ]
    assert projection_deletes
    assert all("image_board_search_fast_documents.game_id =" in sql for sql in projection_deletes)
    with game_storage_scope(game), factory() as session:
        before = session.scalars(select(ImageSymbolReviewEventModel.id)).all()
    with game_storage_scope(game):
        replay = worker.process_next_batch(job=job, max_boards=3)
    assert replay.operation.applied_count == len(selected) and not replay.has_pending_targets
    with game_storage_scope(game), factory() as session:
        assert session.scalars(select(ImageSymbolReviewEventModel.id)).all() == before
    _complete(factory, job)
    if "TASK1177_MEASUREMENT_DIR" not in os.environ:
        return
    output_dir = Path(os.environ["TASK1177_MEASUREMENT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"task1177-bulk-measurement-{len(selected)}.json").write_text(
        json.dumps(
            {
                "boards": 3,
                "cells": len(selected),
                "seconds": elapsed,
                "sqlCount": len(statements),
                "wholeTargetRecounts": len(counts),
            },
            indent=2,
        )
    )
    (output_dir / f"task1177-bulk-sql-{len(selected)}.json").write_text(
        json.dumps(Counter(statements).most_common(), indent=2)
    )


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ"])
def test_other_writer_can_commit_during_attestation_and_fence_rejects_its_drift(
    database, tmp_path, isolation
):
    factory = create_session_factory(database)
    game, _, targets, _ = _source(factory)
    job = _claimed(factory, game, targets[:1])
    preparation_factory = create_session_factory(
        database.execution_options(isolation_level=isolation)
    )
    with game_storage_scope(game), preparation_factory() as preparation:
        repo = SqlAlchemySymbolCellTrainingSourceRepository(preparation, tmp_path)
        fence = repo.capture_freeze_fence(game_id=game)
        # A second connection can perform a real review write while the first
        # would be rendering/checksumming its images. No ownership lock is held.
        with game_storage_scope(game):
            progress = SqlAlchemySymbolCellReviewBulkOperationWorker(factory).process_next_batch(
                job=job
            )
        assert progress.operation.applied_count == 1
        _complete(factory, job)
        with pytest.raises(ImageReviewConflictError) as error:
            repo.require_freeze_fence(game_id=game, expected=fence)
        assert error.value.code == "VERIFIED_TRAINING_COHORT_PREVIEW_STALE"
        preparation.rollback()
    with game_storage_scope(game), factory() as fresh:
        repo = SqlAlchemySymbolCellTrainingSourceRepository(fresh, tmp_path)
        fence = repo.capture_freeze_fence(game_id=game)
        repo.require_freeze_fence(game_id=game, expected=fence)


@pytest.mark.parametrize("lock", ["ownership", "game", "catalog"])
def test_busy_fence_is_nonblocking_and_existing_current_owner_filters_stay_equivalent(
    database, tmp_path, lock
):
    factory = create_session_factory(database)
    game, _, _, _ = _source(factory)
    with game_storage_scope(game), factory() as first, factory() as second:
        repo = SqlAlchemySymbolCellTrainingSourceRepository(first, tmp_path)
        fence = repo.capture_freeze_fence(game_id=game)
        if lock == "ownership":
            acquire_sequence_ownership_lock(second, game_id=game)
        elif lock == "game":
            second.scalar(select(GameModel).where(GameModel.id == game).with_for_update())
        else:
            second.scalar(
                select(ImageSymbolReviewStateModel)
                .where(ImageSymbolReviewStateModel.game_id == game)
                .with_for_update()
            )
        with pytest.raises(ImageReviewConflictError) as error:
            repo.require_freeze_fence(game_id=game, expected=fence)
        assert error.value.code == "VERIFIED_TRAINING_COHORT_WRITE_BUSY"
        second.rollback()
        first.rollback()
        assert repo._exclusion_counts(game).grid_issue == 0
        # This simulates a current-quality flag, then removes its owner from
        # the fast-document map. The old per-cell owner fence remains required.
        first.execute(
            text(
                "UPDATE image_symbol_review_cells SET quality_issue='grid_issue' "
                "WHERE game_id=:g AND cell_index=0"
            ),
            {"g": game},
        )
        assert repo._exclusion_counts(game).grid_issue == 1
        first.execute(
            text("DELETE FROM image_board_search_fast_documents WHERE game_id=:g"), {"g": game}
        )
        assert repo._exclusion_counts(game).grid_issue == 0
        first.rollback()
