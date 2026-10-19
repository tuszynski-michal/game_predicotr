"""Bulk enqueue may queue decisions; execution and competing workflows stay exclusive."""

from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType, create_job
from game_predictor_api.storage.job_admission import admit_job
from sqlalchemy import JSON, Column, MetaData, String, Table, Uuid, create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def admission_store():
    engine = create_engine("sqlite://")
    # Admission only reads these columns. Production PostgreSQL locking and
    # full job persistence are covered by the bulk-start integration tests.
    jobs = Table(
        "jobs",
        MetaData(),
        Column("id", Uuid, primary_key=True),
        Column("game_id", Uuid),
        Column("job_type", String),
        Column("status", String),
        Column("input_payload", JSON),
    )
    jobs.create(engine)
    with Session(engine) as session:
        yield session, jobs
    engine.dispose()


def _job(kind, game_id):
    payload = {"schema_version": 1}
    if kind is JobType.IMPORT:
        payload["import_kind"] = "image_directory"
    elif kind is JobType.VALIDATE:
        payload["validation_kind"] = "page_geometry_preflight"
    return create_job(kind, game_id=game_id, input_payload=payload)


def _add(store, job, status):
    session, jobs = store
    session.execute(
        jobs.insert().values(
            id=job.id,
            game_id=job.game_id,
            job_type=job.job_type.value,
            status=status.value,
            input_payload=job.input_payload,
        )
    )


@pytest.mark.parametrize("status", [JobStatus.CREATED, JobStatus.PROCESSING])
def test_bulk_can_queue_behind_bulk_but_cannot_execute_concurrently(admission_store, status):
    session, _ = admission_store
    game_id = uuid4()
    first = _job(JobType.IMAGE_SYMBOL_REVIEW_BULK, game_id)
    second = _job(JobType.IMAGE_SYMBOL_REVIEW_BULK, game_id)
    _add(admission_store, first, status)

    admit_job(session, second)
    if status is JobStatus.PROCESSING:
        with pytest.raises(JobConflictError) as failure:
            admit_job(session, second, worker_execution=True)
        assert failure.value.code == "GAME_JOB_ADMISSION_CONFLICT"
        assert failure.value.details["existingJobId"] == str(first.id)
    else:
        admit_job(session, second, worker_execution=True)


@pytest.mark.parametrize("status", [JobStatus.CREATED, JobStatus.PROCESSING])
@pytest.mark.parametrize("bulk_first", [False, True])
@pytest.mark.parametrize(
    "other_kind",
    [
        JobType.IMPORT,
        JobType.VALIDATE,
        JobType.IMAGE_GRID_REINFERENCE,
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        JobType.SYMBOL_TRAINING,
        JobType.IMAGE_SYMBOL_REINFERENCE,
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
    ],
)
def test_bulk_conflicts_with_other_workflows_in_both_directions(
    admission_store, other_kind, bulk_first, status
):
    session, _ = admission_store
    game_id = uuid4()
    bulk = _job(JobType.IMAGE_SYMBOL_REVIEW_BULK, game_id)
    other = _job(other_kind, game_id)
    existing, incoming = (bulk, other) if bulk_first else (other, bulk)
    _add(admission_store, existing, status)

    with pytest.raises(JobConflictError) as failure:
        admit_job(session, incoming)
    assert failure.value.code == "GAME_JOB_ADMISSION_CONFLICT"
    assert failure.value.details["existingJobId"] == str(existing.id)
    if status is JobStatus.PROCESSING:
        with pytest.raises(JobConflictError):
            admit_job(session, incoming, worker_execution=True)


def test_other_games_and_own_processing_job_do_not_block_execution(admission_store):
    session, _ = admission_store
    own = _job(JobType.IMAGE_SYMBOL_REVIEW_BULK, uuid4())
    _add(admission_store, own, JobStatus.PROCESSING)
    _add(admission_store, _job(JobType.IMAGE_GRID_REINFERENCE, uuid4()), JobStatus.PROCESSING)
    admit_job(session, own, worker_execution=True)


@pytest.mark.parametrize(
    "status",
    [JobStatus.WAITING_FOR_REVIEW, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED],
)
def test_inactive_jobs_do_not_block_bulk_queue_or_execution(admission_store, status):
    session, _ = admission_store
    game_id = uuid4()
    _add(admission_store, _job(JobType.IMAGE_GRID_REINFERENCE, game_id), status)
    incoming = _job(JobType.IMAGE_SYMBOL_REVIEW_BULK, game_id)
    admit_job(session, incoming)
    admit_job(session, incoming, worker_execution=True)
