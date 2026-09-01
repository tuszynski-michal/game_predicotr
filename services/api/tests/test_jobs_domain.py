from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.jobs import (
    PAYOUT_ALGORITHM_VERSION,
    BoardTopologyJobReference,
    ImageGeometryRolloutJobReference,
    ImageSelectionJobDeletionReference,
    JobRepository,
    JobService,
    LayoutImportRulesReference,
    ManagedImageSelectionDeletionArtifactStore,
    PayoutDatasetReference,
    PayoutRulesReference,
)
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobExecutionSlot,
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
    requeue_job_with_fresh_progress,
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
        self.image_selection_deletions: dict[UUID, ImageSelectionJobDeletionReference] = {}
        self.topology_rules_version_id = uuid4()
        self.board_topology: tuple[int, int] | None = (3, 5)
        self.image_geometry_rollout: ImageGeometryRolloutJobReference | None = None
        self.source_bound_additions: list[tuple[UUID, UUID]] = []

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def get_or_pin_board_topology(
        self,
        game_id: UUID,
    ) -> BoardTopologyJobReference | None:
        if game_id != self.game_id:
            return None
        if self.board_topology is None:
            return None
        rows, columns = self.board_topology
        return BoardTopologyJobReference(
            rules_version_id=self.topology_rules_version_id,
            rows=rows,
            columns=columns,
        )

    def get_image_geometry_rollout(
        self,
        game_id: UUID,
    ) -> ImageGeometryRolloutJobReference | None:
        if game_id != self.game_id:
            return None
        return self.image_geometry_rollout

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

    def add_source_bound_job(
        self,
        job: Job,
        *,
        source_selection_id: UUID,
    ) -> Job:
        self.source_bound_additions.append((job.id, source_selection_id))
        return self.add_job(job)

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

    def get_image_selection_deletion_reference(
        self,
        job_id: UUID,
    ) -> ImageSelectionJobDeletionReference | None:
        return self.image_selection_deletions.get(job_id)

    def delete_image_selection_run_and_job(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
    ) -> None:
        reference = self.image_selection_deletions.get(job_id)
        if reference is None or reference.run_id != run_id:
            raise AssertionError("unexpected image-selection deletion")
        del self.image_selection_deletions[job_id]
        del self.items[job_id]


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


def test_page_geometry_preflight_input_key_ignores_source_display_name() -> None:
    game_id = uuid4()
    first: dict[str, object] = {
        "schema_version": 2,
        "validation_kind": "page_geometry_preflight",
        "source_selection_id": str(uuid4()),
        "source_directory": "C:/managed/browser-selections/source",
        "source_manifest_sha256": "a" * 64,
        "page_registration_profile": {"anchors": [{}]},
        "page_geometry_overrides": {},
        "canonical_sequence_numbers": [1, 2, 3],
    }
    labeled = {**first, "source_display_name": "1 - 19809"}

    assert job_input_key(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload=first,
    ) == job_input_key(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload=labeled,
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


def test_job_type_requires_its_assigned_execution_lane() -> None:
    selection = create_job(
        JobType.IMAGE_SELECTION,
        game_id=uuid4(),
        input_payload={"schema_version": 1},
    )
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)

    with pytest.raises(JobError) as wrong_lane:
        start_job(
            selection,
            worker_version="worker-v10-general",
            worker_id="general-worker",
            lease_token=uuid4(),
            lease_expires_at=now + timedelta(seconds=60),
            started_at=now,
        )
    assert wrong_lane.value.code == "INVALID_JOB_EXECUTION_SLOT"

    claimed = start_job(
        selection,
        worker_version="worker-v10-image-selection",
        worker_id="selection-worker",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(seconds=60),
        execution_slot=JobExecutionSlot.IMAGE_SELECTION,
        started_at=now,
    )

    storage_gc = create_job(
        JobType.STORAGE_GC,
        game_id=None,
        input_payload={
            "schema_version": 1,
            "storage_gc_run_id": str(uuid4()),
            "policy_version": "storage-retention-v1",
            "manifest_checksum_sha256": "a" * 64,
            "mode": "manual",
        },
    )
    storage_started = start_job(
        storage_gc,
        worker_version="worker-v10-general",
        worker_id="general-worker",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(seconds=60),
        execution_slot=JobExecutionSlot.GENERAL,
        started_at=now,
    )
    assert storage_started.execution_slot == JobExecutionSlot.GENERAL
    assert claimed.execution_slot == int(JobExecutionSlot.IMAGE_SELECTION)


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


def test_fresh_requeue_discards_partial_progress_for_whole_staging_recalculation() -> None:
    progressed, token = _leased_job()
    checkpointed_at = datetime(2026, 7, 27, 12, 1, 15, tzinfo=UTC)
    progressed = update_job_progress(
        progressed,
        lease_token=token,
        stage="page_geometry_registering",
        current=50,
        total=2_201,
        success_count=43,
        failure_count=0,
        review_count=0,
        updated_at=checkpointed_at,
    )
    cancelled = acknowledge_job_cancellation(
        request_job_cancellation(progressed, requested_at=checkpointed_at),
        lease_token=token,
        finished_at=checkpointed_at + timedelta(seconds=1),
    )

    requeued = requeue_job_with_fresh_progress(cancelled)

    assert requeued.status is JobStatus.CREATED
    assert requeued.stage is None
    assert requeued.progress_current == 0
    assert requeued.progress_total is None
    assert requeued.success_count == 0
    assert requeued.failure_count == 0
    assert requeued.review_count == 0
    assert requeued.checkpoint_payload is None


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


def test_page_geometry_preflight_uses_atomic_source_bound_persistence(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)

    job = service.create_page_geometry_preflight_job(
        game_id=game_id,
        selection_id=selection_id,
        source_directory=tmp_path,
        source_display_name="seq import",
        source_manifest_sha256="a" * 64,
    )

    assert repository.source_bound_additions == [(job.id, selection_id)]


def test_service_physically_deletes_cancelled_image_selection_job(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    source_selection_id = uuid4()
    run_id = uuid4()
    job = repository.add_job(
        create_job(
            JobType.IMAGE_SELECTION,
            game_id=game_id,
            input_payload={"schema_version": 1},
        )
    )
    repository.image_selection_deletions[job.id] = ImageSelectionJobDeletionReference(
        run_id=run_id,
        source_selection_id=source_selection_id,
        source_reference_count=1,
        has_curated_import_source=False,
        has_published_output=False,
    )
    artifact_root = tmp_path / "artifacts"
    import_root = tmp_path / "imports"
    manual_directory = artifact_root / "data" / "working" / "is-manual" / run_id.hex[:12]
    source_directory = import_root / "browser-selections" / str(source_selection_id)
    manual_directory.mkdir(parents=True)
    source_directory.mkdir(parents=True)
    (manual_directory / "manual.jpg").write_bytes(b"manual")
    (source_directory / "source.jpg").write_bytes(b"source")
    service = JobService(
        repository,
        deletion_artifact_store=ManagedImageSelectionDeletionArtifactStore(
            artifact_root=artifact_root,
            import_root=import_root,
        ),
    )
    service.cancel_job(job.id)

    deletion = service.delete_cancelled_image_selection_job(job.id)

    assert deletion.managed_run_files_deleted is True
    assert deletion.source_staging_deleted is True
    assert deletion.shared_source_staging_preserved is False
    assert repository.get_job(job.id) is None
    assert not manual_directory.exists()
    assert not source_directory.exists()
    service.finalize_pending_deletions()
    assert not (
        artifact_root / "data" / "trash" / "image-selection-deletions" / str(job.id)
    ).exists()
    assert not (import_root / ".trash" / "image-selection-deletions" / str(job.id)).exists()


def test_service_preserves_shared_source_and_blocks_handoff(tmp_path: Path) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    source_selection_id = uuid4()
    run_id = uuid4()
    job = repository.add_job(
        create_job(
            JobType.IMAGE_SELECTION,
            game_id=game_id,
            input_payload={"schema_version": 1},
        )
    )
    repository.image_selection_deletions[job.id] = ImageSelectionJobDeletionReference(
        run_id=run_id,
        source_selection_id=source_selection_id,
        source_reference_count=2,
        has_curated_import_source=False,
        has_published_output=False,
    )
    source_directory = tmp_path / "imports" / "browser-selections" / str(source_selection_id)
    source_directory.mkdir(parents=True)
    service = JobService(
        repository,
        deletion_artifact_store=ManagedImageSelectionDeletionArtifactStore(
            artifact_root=tmp_path / "artifacts",
            import_root=tmp_path / "imports",
        ),
    )
    service.cancel_job(job.id)

    deletion = service.delete_cancelled_image_selection_job(job.id)

    assert deletion.source_staging_deleted is False
    assert deletion.shared_source_staging_preserved is True
    assert source_directory.exists()

    blocked_job = repository.add_job(
        create_job(
            JobType.IMAGE_SELECTION,
            game_id=game_id,
            input_payload={"schema_version": 1, "marker": "handoff"},
        )
    )
    repository.image_selection_deletions[blocked_job.id] = ImageSelectionJobDeletionReference(
        run_id=uuid4(),
        source_selection_id=uuid4(),
        source_reference_count=1,
        has_curated_import_source=True,
        has_published_output=False,
    )
    service.cancel_job(blocked_job.id)
    with pytest.raises(JobConflictError) as blocked:
        service.delete_cancelled_image_selection_job(blocked_job.id)
    assert blocked.value.code == "IMAGE_SELECTION_JOB_HANDOFF_EXISTS"


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
            algorithm_version=PAYOUT_ALGORITHM_VERSION,
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
        algorithm_version=PAYOUT_ALGORITHM_VERSION,
    )

    assert created.job_type is JobType.PAYOUT
    assert created.input_payload == {
        "schema_version": 1,
        "dataset_version_id": str(dataset_id),
        "rules_version_id": str(rules_id),
        "algorithm_version": PAYOUT_ALGORITHM_VERSION,
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
