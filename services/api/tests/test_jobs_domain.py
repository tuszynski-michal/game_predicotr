from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.jobs import (
    JobRepository,
    JobService,
    LayoutImportRulesReference,
    PayoutDatasetReference,
    PayoutRulesReference,
)
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobStatus,
    JobType,
    acknowledge_job_cancellation,
    checkpoint_job,
    complete_job,
    create_job,
    fail_job,
    job_input_key,
    recover_expired_job,
    renew_job_lease,
    request_job_cancellation,
    requeue_job,
    start_job,
    update_job_progress,
    wait_for_review,
)
from game_predictor_api.domain.rules import RulesVersionStatus


class MemoryJobRepository(JobRepository):
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, Job] = {}
        self.rules: dict[UUID, LayoutImportRulesReference] = {}
        self.payout_datasets: dict[UUID, PayoutDatasetReference] = {}
        self.payout_rules: dict[UUID, PayoutRulesReference] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def get_layout_import_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> LayoutImportRulesReference | None:
        return self.rules.get(rules_version_id)

    def get_payout_dataset_reference(
        self,
        dataset_version_id: UUID,
    ) -> PayoutDatasetReference | None:
        return self.payout_datasets.get(dataset_version_id)

    def get_payout_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> PayoutRulesReference | None:
        return self.payout_rules.get(rules_version_id)

    def add_job(self, job: Job) -> Job:
        self.items[job.id] = job
        return job

    def get_job(self, job_id: UUID) -> Job | None:
        return self.items.get(job_id)

    def get_job_for_update(self, job_id: UUID) -> Job | None:
        return self.get_job(job_id)

    def get_job_by_input_key(self, input_key: str) -> Job | None:
        return next(
            (item for item in self.items.values() if item.input_key == input_key),
            None,
        )

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> list[Job]:
        return [
            item
            for item in reversed(tuple(self.items.values()))
            if (status is None or item.status is status)
            and (job_type is None or item.job_type is job_type)
            and (game_id is None or item.game_id == game_id)
        ][:limit]

    def save_job(self, job: Job) -> Job:
        self.items[job.id] = job
        return job


def _job() -> Job:
    return create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={"schema_version": 1, "dataset_version_id": str(uuid4())},
        created_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
    )


def _leased_job(
    job: Job | None = None,
    *,
    started_at: datetime | None = None,
) -> tuple[Job, UUID]:
    now = started_at or datetime(2026, 7, 27, 12, 1, tzinfo=UTC)
    token = uuid4()
    return (
        start_job(
            job or _job(),
            worker_version="worker-v1",
            worker_id="worker-a",
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=60),
            started_at=now,
        ),
        token,
    )


def test_input_key_is_canonical_and_includes_type_and_game() -> None:
    game_id = uuid4()
    first = {"schema_version": 1, "alpha": "a", "nested": {"b": 2, "a": 1}}
    second = {"nested": {"a": 1, "b": 2}, "alpha": "a", "schema_version": 1}

    assert job_input_key(JobType.IMPORT, game_id=game_id, input_payload=first) == (
        job_input_key(JobType.IMPORT, game_id=game_id, input_payload=second)
    )
    assert job_input_key(JobType.IMPORT, game_id=game_id, input_payload=first) != (
        job_input_key(JobType.VALIDATE, game_id=game_id, input_payload=first)
    )


def test_layout_import_input_key_uses_attested_content_not_file_name() -> None:
    game_id = uuid4()
    first: dict[str, object] = {
        "schema_version": 1,
        "import_kind": "layout_file",
        "source_path": "first/layouts.csv",
        "source_checksum": "a" * 64,
        "source_size_bytes": 100,
        "file_format": "csv",
        "contract_version": 1,
    }
    renamed = {
        **first,
        "source_path": "renamed/layouts.csv",
    }
    changed = {
        **first,
        "source_checksum": "b" * 64,
    }

    assert job_input_key(
        JobType.IMPORT,
        game_id=game_id,
        input_payload=first,
    ) == job_input_key(
        JobType.IMPORT,
        game_id=game_id,
        input_payload=renamed,
    )
    assert job_input_key(
        JobType.IMPORT,
        game_id=game_id,
        input_payload=first,
    ) != job_input_key(
        JobType.IMPORT,
        game_id=game_id,
        input_payload=changed,
    )


def test_processing_progress_review_resume_and_completion_lifecycle() -> None:
    original = _job()
    started, token = _leased_job(original)
    progressed = update_job_progress(
        started,
        lease_token=token,
        stage="validating",
        current=20,
        total=100,
        success_count=18,
        failure_count=1,
        review_count=1,
        updated_at=datetime(2026, 7, 27, 12, 1, 10, tzinfo=UTC),
    )
    waiting = wait_for_review(
        progressed,
        lease_token=token,
        updated_at=datetime(2026, 7, 27, 12, 1, 20, tzinfo=UTC),
    )

    assert waiting.status is JobStatus.WAITING_FOR_REVIEW
    assert waiting.stage == "validating"
    with pytest.raises(JobConflictError) as error:
        complete_job(waiting, lease_token=token)
    assert error.value.code == "INVALID_JOB_STATUS_TRANSITION"


def test_invalid_transition_and_progress_regression_are_rejected() -> None:
    original = _job()
    with pytest.raises(JobConflictError) as error:
        complete_job(original, lease_token=uuid4())
    assert error.value.code == "INVALID_JOB_STATUS_TRANSITION"

    started, token = _leased_job(original)
    progressed = update_job_progress(
        started,
        lease_token=token,
        stage="scanning",
        current=5,
        total=10,
        success_count=5,
        failure_count=0,
        review_count=0,
        updated_at=datetime(2026, 7, 27, 12, 1, 10, tzinfo=UTC),
    )
    with pytest.raises(JobError) as progress_error:
        update_job_progress(
            progressed,
            lease_token=token,
            stage="scanning",
            current=4,
            total=10,
            success_count=4,
            failure_count=0,
            review_count=0,
            updated_at=datetime(2026, 7, 27, 12, 1, 20, tzinfo=UTC),
        )
    assert progress_error.value.code == "JOB_PROGRESS_REGRESSION"


def test_cancellation_is_immediate_before_start_and_deferred_during_processing() -> None:
    now = datetime(2026, 7, 27, 13, tzinfo=UTC)
    unstarted = request_job_cancellation(_job(), requested_at=now)
    assert unstarted.status is JobStatus.CANCELLED
    assert unstarted.finished_at == now

    processing, token = _leased_job(started_at=datetime(2026, 7, 27, 12, 59, 30, tzinfo=UTC))
    requested = request_job_cancellation(processing, requested_at=now)
    assert requested.status is JobStatus.PROCESSING
    assert requested.cancel_requested_at == now

    acknowledged = acknowledge_job_cancellation(
        requested,
        lease_token=token,
        finished_at=now + timedelta(seconds=1),
    )
    assert acknowledged.status is JobStatus.CANCELLED


def test_cancelled_job_can_be_requeued_from_its_durable_progress() -> None:
    cancelled_at = datetime(2026, 7, 27, 12, 1, 30, tzinfo=UTC)
    progressed, token = _leased_job()
    progressed = update_job_progress(
        progressed,
        lease_token=token,
        stage="image_selection:scanning",
        current=2_016,
        total=32_079,
        success_count=2_015,
        failure_count=0,
        review_count=1,
        updated_at=cancelled_at - timedelta(seconds=1),
    )
    requested = request_job_cancellation(progressed, requested_at=cancelled_at)
    cancelled = acknowledge_job_cancellation(
        requested,
        lease_token=token,
        finished_at=cancelled_at + timedelta(seconds=1),
    )

    requeued = requeue_job(cancelled, updated_at=cancelled_at + timedelta(seconds=2))

    assert requeued.status is JobStatus.CREATED
    assert requeued.progress_current == 2_016
    assert requeued.progress_total == 32_079
    assert requeued.finished_at is None
    assert requeued.cancel_requested_at is None
    assert requeued.lease_token is None


def test_completed_and_failed_jobs_are_terminal_for_cancel() -> None:
    processing, completed_token = _leased_job()
    completed = complete_job(
        processing,
        lease_token=completed_token,
        finished_at=datetime(2026, 7, 27, 12, 1, 30, tzinfo=UTC),
    )
    failing, failing_token = _leased_job()
    failed = fail_job(
        failing,
        lease_token=failing_token,
        error_code="VALIDATION_FAILED",
        error_message="Dataset is invalid.",
        finished_at=datetime(2026, 7, 27, 12, 1, 30, tzinfo=UTC),
    )

    for terminal in (completed, failed):
        with pytest.raises(JobConflictError) as error:
            request_job_cancellation(terminal)
        assert error.value.code == "JOB_NOT_CANCELLABLE"


def test_service_rejects_duplicate_input_and_cancels_persisted_job() -> None:
    game_id = uuid4()
    service = JobService(MemoryJobRepository(game_id))
    payload: dict[str, object] = {
        "schema_version": 1,
        "dataset_version_id": str(uuid4()),
    }
    created = service.create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload=payload,
    )

    with pytest.raises(JobConflictError) as error:
        service.create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload=payload,
        )
    assert error.value.code == "JOB_INPUT_ALREADY_EXISTS"
    assert service.cancel_job(created.id).status is JobStatus.CANCELLED


def test_service_rejects_import_without_server_source_attestation() -> None:
    service = JobService(MemoryJobRepository(uuid4()))

    with pytest.raises(JobError) as captured:
        service.create_job(
            JobType.IMPORT,
            game_id=uuid4(),
            input_payload={"schema_version": 1},
        )

    assert captured.value.code == "IMPORT_SOURCE_NOT_ATTESTED"


def test_payout_job_requires_complete_published_matching_sources() -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)
    dataset_id = uuid4()
    rules_id = uuid4()
    repository.payout_datasets[dataset_id] = PayoutDatasetReference(
        game_id=game_id,
        status=DatasetVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        expected_layout_count=50,
        layout_count=49,
    )
    repository.payout_rules[rules_id] = PayoutRulesReference(
        game_id=game_id,
        status=RulesVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
    )

    with pytest.raises(JobConflictError) as incomplete:
        service.create_payout_job(
            game_id=game_id,
            dataset_version_id=dataset_id,
            rules_version_id=rules_id,
            algorithm_version="payout-v2",
        )
    assert incomplete.value.code == "PAYOUT_DATASET_INCOMPLETE"

    repository.payout_datasets[dataset_id] = PayoutDatasetReference(
        game_id=game_id,
        status=DatasetVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        expected_layout_count=50,
        layout_count=50,
    )
    created = service.create_payout_job(
        game_id=game_id,
        dataset_version_id=dataset_id,
        rules_version_id=rules_id,
        algorithm_version="payout-v2",
    )

    assert created.job_type is JobType.PAYOUT
    assert created.input_payload == {
        "schema_version": 1,
        "dataset_version_id": str(dataset_id),
        "rules_version_id": str(rules_id),
        "algorithm_version": "payout-v2",
    }


def test_lease_token_heartbeat_checkpoint_and_expiry_are_fenced() -> None:
    started_at = datetime(2026, 7, 27, 14, tzinfo=UTC)
    processing, token = _leased_job(started_at=started_at)

    renewed = renew_job_lease(
        processing,
        lease_token=token,
        heartbeat_at=started_at + timedelta(seconds=20),
        lease_expires_at=started_at + timedelta(seconds=80),
    )
    checkpointed = checkpoint_job(
        renewed,
        lease_token=token,
        checkpoint_payload={"schema_version": 1, "after_sequence_number": 100},
        stage="validating",
        current=100,
        total=1000,
        success_count=98,
        failure_count=1,
        review_count=1,
        updated_at=started_at + timedelta(seconds=30),
    )

    assert checkpointed.checkpoint_payload == {
        "schema_version": 1,
        "after_sequence_number": 100,
    }
    assert checkpointed.heartbeat_at == started_at + timedelta(seconds=20)
    with pytest.raises(JobConflictError) as wrong_token:
        renew_job_lease(
            checkpointed,
            lease_token=uuid4(),
            heartbeat_at=started_at + timedelta(seconds=40),
            lease_expires_at=started_at + timedelta(seconds=100),
        )
    assert wrong_token.value.code == "JOB_LEASE_LOST"
    with pytest.raises(JobConflictError) as expired:
        renew_job_lease(
            checkpointed,
            lease_token=token,
            heartbeat_at=started_at + timedelta(seconds=81),
            lease_expires_at=started_at + timedelta(seconds=120),
        )
    assert expired.value.code == "JOB_LEASE_LOST"


def test_expired_lease_requeues_same_job_and_preserves_checkpoint() -> None:
    started_at = datetime(2026, 7, 27, 15, tzinfo=UTC)
    processing, token = _leased_job(started_at=started_at)
    checkpointed = checkpoint_job(
        processing,
        lease_token=token,
        checkpoint_payload={"schema_version": 1, "cursor": 25},
        stage="writing",
        current=25,
        total=100,
        success_count=25,
        failure_count=0,
        review_count=0,
        updated_at=started_at + timedelta(seconds=20),
    )
    recovered = recover_expired_job(
        checkpointed,
        recovered_at=started_at + timedelta(seconds=61),
    )
    resumed, _new_token = _leased_job(
        recovered,
        started_at=started_at + timedelta(seconds=62),
    )

    assert recovered.id == processing.id
    assert recovered.status is JobStatus.CREATED
    assert recovered.checkpoint_payload == {"schema_version": 1, "cursor": 25}
    assert recovered.execution_slot is None
    assert resumed.attempt_count == 2
    assert resumed.progress_current == 25
