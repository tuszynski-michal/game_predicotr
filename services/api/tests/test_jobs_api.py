import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.jobs import (
    ImageSelectionJobDeletionReference,
    JobService,
    LayoutImportRulesReference,
    ManagedImageSelectionDeletionArtifactStore,
    PayoutDatasetReference,
    PayoutRulesReference,
)
from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.main import create_app
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_worker.images.board_cell_geometry_activation import (
    PENDING_BOARD_CELL_RECROP_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from test_jobs_domain import MemoryJobRepository


def _client(
    tmp_path: Path,
) -> tuple[
    TestClient,
    UUID,
    JobService,
    MemoryJobRepository,
]:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    import_root = tmp_path / "imports"
    import_root.mkdir()
    service = JobService(
        repository,
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
        deletion_artifact_store=ManagedImageSelectionDeletionArtifactStore(
            artifact_root=tmp_path / "artifacts",
            import_root=import_root,
        ),
    )
    client = TestClient(
        create_app(
            ApiSettings.from_environment({"GAME_PREDICTOR_IMPORT_ROOT": str(import_root)}),
            job_service_dependency=lambda: service,
        )
    )
    return client, game_id, service, repository


def _create_validate_job(client: TestClient, game_id: UUID) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/jobs",
        json={
            "jobType": "validate",
            "gameId": str(game_id),
            "inputPayload": {
                "schemaVersion": 1,
                "datasetVersionId": str(uuid4()),
            },
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_image_directory_job_payload_is_serialized_for_operations_ui() -> None:
    selection_run_id = uuid4()
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "source_selection_id": str(uuid4()),
            "source_directory": r"C:\photos",
            "source_display_name": "photos",
            "pipeline_fingerprint": "a" * 64,
            "image_selection_run_id": str(selection_run_id),
        },
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
    )

    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)

    assert response["inputPayload"] == {
        "schemaVersion": 1,
        "importKind": "image_directory",
        "sourceSelectionId": job.input_payload["source_selection_id"],
        "sourceDirectory": r"C:\photos",
        "sourceDisplayName": "photos",
        "pipelineFingerprint": "a" * 64,
        "imageSelectionRunId": str(selection_run_id),
    }


def test_pending_grid_reinference_pins_the_accepted_v19_recrop_snapshot(
    tmp_path: Path,
) -> None:
    _client_instance, game_id, service, _repository = _client(tmp_path)

    job = service.create_pending_grid_reinference_job(game_id=game_id)
    payload = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)["inputPayload"]

    assert payload["schemaVersion"] == 2
    assert payload["inferenceKind"] == "pending_grid_only"
    assert payload["cellOutputSize"] == 64
    assert payload["gridProfile"] is None
    assert payload["boardCellRecrop"]["activationVersion"] == (PENDING_BOARD_CELL_RECROP_VERSION)
    assert payload["boardCellRecrop"]["geometryVersion"] == BOARD_CELL_GEOMETRY_VERSION
    assert payload["boardCellRecrop"]["cropperVersion"] == CROPPER_VERSION


def test_historical_pending_grid_reinference_v1_payload_remains_serializable() -> None:
    job = create_job(
        JobType.IMAGE_GRID_REINFERENCE,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "inference_kind": "pending_grid_only",
            "cell_output_size": 64,
            "grid_profile": {
                "profileId": None,
                "profileVersion": "detector-baseline-v1",
                "profileChecksumSha256": "a" * 64,
                "activationId": None,
                "profilePayload": {},
                "pageRegistrationProfile": None,
                "inferenceFingerprint": "b" * 64,
            },
        },
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )

    payload = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)["inputPayload"]

    assert payload["schemaVersion"] == 1
    assert payload["boardCellRecrop"] is None
    assert payload["gridProfile"]["profileVersion"] == "detector-baseline-v1"


def test_image_selection_job_exposes_bounded_operational_progress() -> None:
    job = create_job(
        JobType.IMAGE_SELECTION,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "source_selection_id": str(uuid4()),
            "input_manifest_sha256": "a" * 64,
            "selector_fingerprint": "b" * 64,
            "contract_version": 1,
        },
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
    )
    job = replace(
        job,
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "image_selection",
            "group_count": 12,
            "selected_count": 9,
            "manual_count": 2,
            "range_required_count": 4,
            "skipped_count": 1,
            "error_count": 3,
            "verification_count": 30,
            "upload_duration_seconds": 15.5,
            "processing_duration_seconds": 8.25,
            "diagnostic": {"checksumSha256": "c" * 64},
            "recent_window": {
                "fromProcessed": 64,
                "toProcessed": 96,
                "elapsedSeconds": 12.5,
                "groupsFinalized": 3,
                "verifications": 18,
                "manual": 2,
                "rangeRequired": 1,
            },
            "stage_timing": {
                "counters": {"anchoredOcrAttempts": 8, "fallbackOcrAttempts": 3},
                "stages": {
                    "geometry": {"totalSeconds": 4.5},
                    "ocr": {"totalSeconds": 7.25},
                },
            },
        },
    )

    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)

    assert response["progress"]["imageSelection"] == {
        "groups": 12,
        "selected": 9,
        "manual": 2,
        "rangeRequired": 4,
        "skipped": 1,
        "errors": 3,
        "verifications": 30,
        "uploadDurationSeconds": 15.5,
        "processingDurationSeconds": 8.25,
        "diagnosticChecksumSha256": "c" * 64,
        "recentWindow": {
            "fromProcessed": 64,
            "toProcessed": 96,
            "elapsedSeconds": 12.5,
            "groupsFinalized": 3,
            "verifications": 18,
            "manual": 2,
            "rangeRequired": 1,
        },
        "stageSeconds": {"geometry": 4.5, "ocr": 7.25},
        "telemetryCounters": {
            "anchoredOcrAttempts": 8,
            "fallbackOcrAttempts": 3,
        },
    }


def test_job_exposes_explicit_board_cell_geometry_progress() -> None:
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "source_directory": r"C:\photos",
            "source_display_name": "photos",
            "pipeline_fingerprint": "a" * 64,
        },
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
    )
    job = replace(
        job,
        checkpoint_payload={
            "board_cell_geometry": {
                "status": "waiting_for_geometry",
                "total": 90,
                "processed": 90,
                "succeeded": 86,
                "pending": 3,
                "resolved": 0,
                "superseded": 1,
            }
        },
    )

    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)

    assert response["progress"]["boardCellGeometry"] == {
        "status": "waiting_for_geometry",
        "total": 90,
        "processed": 90,
        "succeeded": 86,
        "pending": 3,
        "resolved": 0,
        "superseded": 1,
    }


def test_curated_image_import_job_preserves_selection_run_provenance(
    tmp_path: Path,
) -> None:
    _client_value, game_id, service, _repository = _client(tmp_path)
    curated_root = tmp_path / "curated"
    curated_root.mkdir()
    selection_id = uuid4()
    selection_run_id = uuid4()

    job = service.create_image_import_job(
        game_id=game_id,
        selection_id=selection_id,
        source_directory=curated_root,
        source_display_name="curated",
        pipeline_fingerprint="a" * 64,
        image_selection_run_id=selection_run_id,
    )

    assert job.input_payload["source_selection_id"] == str(selection_id)
    assert job.input_payload["image_selection_run_id"] == str(selection_run_id)
    assert job.input_payload["schema_version"] == 2
    symbol_model = job.input_payload["symbol_model"]
    assert isinstance(symbol_model, dict)
    assert symbol_model["modelVersion"] == "bootstrap-symbol-cnn-onnx-v1"
    assert len(str(symbol_model["inferenceFingerprint"])) == 64


class _MutableSymbolModelResolver:
    def __init__(self, snapshot: SymbolModelJobSnapshot) -> None:
        self.snapshot = snapshot

    def resolve(self, *, game_id: UUID) -> SymbolModelJobSnapshot:
        del game_id
        return self.snapshot


def _test_symbol_snapshot(iteration_id: UUID, marker: str) -> SymbolModelJobSnapshot:
    return SymbolModelJobSnapshot(
        iteration_id=iteration_id,
        model_version=f"candidate-{marker}",
        manifest_checksum_sha256=marker * 64,
        onnx_checksum_sha256=("a" if marker == "b" else "b") * 64,
        onnx_relative_path=f"models/{marker}/model.onnx",
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=("lemon", "seven"),
        input_size=64,
        temperature=1.0,
    )


def test_model_activation_changes_only_jobs_created_after_the_change(tmp_path: Path) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    source = tmp_path / "photos"
    source.mkdir()
    first_snapshot = _test_symbol_snapshot(uuid4(), "b")
    second_snapshot = _test_symbol_snapshot(uuid4(), "c")
    resolver = _MutableSymbolModelResolver(first_snapshot)
    service = JobService(repository, None, resolver)

    before = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="photos",
        pipeline_fingerprint="d" * 64,
    )
    resolver.snapshot = second_snapshot
    after = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="photos",
        pipeline_fingerprint="d" * 64,
    )

    assert before.input_payload["symbol_model"] == first_snapshot.to_payload()
    assert after.input_payload["symbol_model"] == second_snapshot.to_payload()
    assert (
        before.input_payload["pipeline_fingerprint"] != after.input_payload["pipeline_fingerprint"]
    )
    assert before.input_payload["source_pipeline_fingerprint"] == "d" * 64
    assert after.input_payload["source_pipeline_fingerprint"] == "d" * 64


def test_create_list_get_and_cancel_job_contract(tmp_path: Path) -> None:
    client, game_id, _service, _repository = _client(tmp_path)
    with client:
        created = _create_validate_job(client, game_id)
        job_id = created["id"]

        assert created["jobType"] == "validate"
        assert created["status"] == "created"
        assert created["progress"] == {
            "current": 0,
            "total": None,
            "stage": None,
            "succeeded": 0,
            "failed": 0,
            "review": 0,
        }
        assert created["error"] is None
        assert created["attemptCount"] == 0
        assert created["heartbeatAt"] is None
        assert created["leaseExpiresAt"] is None

        listed = client.get(
            "/api/v1/admin/jobs",
            params={"status": "created", "job_type": "validate"},
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [job_id]

        fetched = client.get(f"/api/v1/admin/jobs/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == job_id

        cancelled = client.post(f"/api/v1/admin/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancelRequestedAt"] is not None
        assert cancelled.json()["finishedAt"] is not None


def test_delete_cancelled_image_selection_job_contract(tmp_path: Path) -> None:
    client, game_id, service, repository = _client(tmp_path)
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
    manual_directory = tmp_path / "artifacts" / "data" / "working" / "is-manual" / run_id.hex[:12]
    manual_directory.mkdir(parents=True)
    service.cancel_job(job.id)

    with client:
        response = client.delete(f"/api/v1/admin/jobs/{job.id}")
        service.finalize_pending_deletions()

    assert response.status_code == 200
    assert response.json() == {
        "jobId": str(job.id),
        "runId": str(run_id),
        "managedRunFilesDeleted": True,
        "sourceStagingDeleted": False,
        "sharedSourceStagingPreserved": False,
    }
    assert repository.get_job(job.id) is None
    assert not manual_directory.exists()


def test_typed_payload_and_duplicate_errors_are_stable(tmp_path: Path) -> None:
    client, game_id, _service, _repository = _client(tmp_path)
    dataset_id = uuid4()
    payload = {
        "jobType": "validate",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "datasetVersionId": str(dataset_id),
        },
    }
    with client:
        assert client.post("/api/v1/admin/jobs", json=payload).status_code == 201
        duplicate = client.post("/api/v1/admin/jobs", json=payload)
        invalid = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "validate",
                "gameId": str(game_id),
                "inputPayload": {
                    "schemaVersion": 2,
                    "datasetVersionId": str(dataset_id),
                },
            },
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_all_five_job_payloads_are_discriminated_by_job_type(
    tmp_path: Path,
) -> None:
    client, game_id, service, _repository = _client(tmp_path)
    import_source = tmp_path / "imports" / "game-1.csv"
    import_source.write_text(
        'schema_version,sequence_number,cells\n1,1,"[1,2,3]"\n',
        encoding="utf-8",
        newline="\n",
    )
    release_id = uuid4()
    payout_dataset_id = uuid4()
    payout_rules_id = uuid4()
    _repository.payout_datasets[payout_dataset_id] = PayoutDatasetReference(
        game_id=game_id,
        status=DatasetVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        expected_layout_count=50,
        layout_count=50,
    )
    _repository.payout_rules[payout_rules_id] = PayoutRulesReference(
        game_id=game_id,
        status=RulesVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
    )
    requests = [
        (
            "import",
            game_id,
            {
                "schemaVersion": 1,
                "sourcePath": "game-1.csv",
                "contractVersion": 1,
            },
        ),
        (
            "payout",
            game_id,
            {
                "schemaVersion": 1,
                "datasetVersionId": str(payout_dataset_id),
                "rulesVersionId": str(payout_rules_id),
                "algorithmVersion": "payout-v2",
            },
        ),
        ("snapshot", None, {"schemaVersion": 1, "mobileReleaseId": str(release_id)}),
        (
            "android_build",
            None,
            {"schemaVersion": 1, "mobileReleaseId": str(uuid4())},
        ),
    ]
    with client:
        _create_validate_job(client, game_id)
        for job_type, request_game_id, input_payload in requests:
            response = client.post(
                "/api/v1/admin/jobs",
                json={
                    "jobType": job_type,
                    "gameId": (None if request_game_id is None else str(request_game_id)),
                    "inputPayload": input_payload,
                },
            )
            assert response.status_code == 201

    jobs: list[Job] = list(
        service.list_jobs(
            status=None,
            job_type=None,
            game_id=None,
            limit=20,
        )
    )
    assert {job.job_type for job in jobs} == set(JobType) - {
        JobType.IMAGE_SELECTION,
        JobType.SYMBOL_TRAINING,
            JobType.IMAGE_SYMBOL_REINFERENCE,
            JobType.IMAGE_GRID_REINFERENCE,
        }
    assert all(job.status is JobStatus.CREATED for job in jobs)


def test_payout_job_rejects_incomplete_dataset_before_queueing(tmp_path: Path) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    dataset_id = uuid4()
    rules_id = uuid4()
    repository.payout_datasets[dataset_id] = PayoutDatasetReference(
        game_id=game_id,
        status=DatasetVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
        expected_layout_count=50,
        layout_count=48,
    )
    repository.payout_rules[rules_id] = PayoutRulesReference(
        game_id=game_id,
        status=RulesVersionStatus.PUBLISHED,
        rows=3,
        columns=5,
    )

    with client:
        response = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "payout",
                "gameId": str(game_id),
                "inputPayload": {
                    "schemaVersion": 1,
                    "datasetVersionId": str(dataset_id),
                    "rulesVersionId": str(rules_id),
                    "algorithmVersion": "payout-v2",
                },
            },
        )

    assert response.status_code == 409
    assert response.json() == {
        "code": "PAYOUT_DATASET_INCOMPLETE",
        "message": "The selected dataset has missing or excess layouts.",
        "details": {"expectedLayoutCount": 50, "layoutCount": 48},
    }
    assert repository.items == {}


def test_import_job_attests_source_and_is_idempotent_by_content(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    content = b'schema_version,sequence_number,cells\n1,1,"[1,2,3]"\n'
    import_root = tmp_path / "imports"
    (import_root / "first.csv").write_bytes(content)
    (import_root / "renamed.csv").write_bytes(content)
    first_request = {
        "jobType": "import",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "sourcePath": "first.csv",
            "contractVersion": 1,
        },
    }
    with client:
        created = client.post("/api/v1/admin/jobs", json=first_request)
        duplicate = client.post(
            "/api/v1/admin/jobs",
            json={
                **first_request,
                "inputPayload": {
                    **first_request["inputPayload"],
                    "sourcePath": "renamed.csv",
                },
            },
        )

    assert created.status_code == 201
    created_payload = created.json()["inputPayload"]
    assert created_payload == {
        "schemaVersion": 1,
        "importKind": "layout_file",
        "sourcePath": "first.csv",
        "sourceChecksum": hashlib.sha256(content).hexdigest(),
        "sourceSizeBytes": len(content),
        "fileFormat": "csv",
        "contractVersion": 1,
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"
    assert duplicate.json()["details"]["existingJobId"] == created.json()["id"]
    assert len(repository.items) == 1


def test_layout_import_validation_requires_completed_import_and_published_rules(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    import_job = replace(
        JobService(repository).create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={"schema_version": 1, "dataset_version_id": str(uuid4())},
        ),
        job_type=JobType.IMPORT,
        status=JobStatus.COMPLETED,
    )
    repository.items[import_job.id] = import_job
    rules_version_id = uuid4()
    repository.rules[rules_version_id] = LayoutImportRulesReference(
        game_id=game_id,
        status=RulesVersionStatus.PUBLISHED,
    )
    payload = {
        "jobType": "validate",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "validationKind": "layout_import",
            "importJobId": str(import_job.id),
            "rulesVersionId": str(rules_version_id),
        },
    }

    with client:
        created = client.post("/api/v1/admin/jobs", json=payload)
        duplicate = client.post("/api/v1/admin/jobs", json=payload)

    assert created.status_code == 201
    assert created.json()["inputPayload"] == payload["inputPayload"]
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"


def test_import_job_rejects_untrusted_metadata_and_unsafe_path(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    (tmp_path / "imports" / "layouts.csv").write_text(
        'schema_version,sequence_number,cells\n1,1,"[1]"\n',
        encoding="utf-8",
    )
    base_request = {
        "jobType": "import",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "sourcePath": "layouts.csv",
            "contractVersion": 1,
        },
    }
    with client:
        untrusted = client.post(
            "/api/v1/admin/jobs",
            json={
                **base_request,
                "inputPayload": {
                    **base_request["inputPayload"],
                    "sourceChecksum": "a" * 64,
                },
            },
        )
        unsafe = client.post(
            "/api/v1/admin/jobs",
            json={
                **base_request,
                "inputPayload": {
                    **base_request["inputPayload"],
                    "sourcePath": "../layouts.csv",
                },
            },
        )

    assert untrusted.status_code == 422
    assert untrusted.json()["code"] == "VALIDATION_ERROR"
    assert unsafe.status_code == 422
    assert unsafe.json()["code"] == "INVALID_IMPORT_SOURCE_PATH"
    assert repository.items == {}


def test_import_job_reports_contract_error_without_creating_job(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    (tmp_path / "imports" / "invalid.csv").write_text(
        "wrong,header\n",
        encoding="utf-8",
    )
    with client:
        response = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "import",
                "gameId": str(game_id),
                "inputPayload": {
                    "schemaVersion": 1,
                    "sourcePath": "invalid.csv",
                    "contractVersion": 1,
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "import_header_invalid"
    assert response.json()["details"]["lineNumber"] == 1
    assert repository.items == {}


def test_import_job_rejects_unknown_game_before_inspecting_source(
    tmp_path: Path,
) -> None:
    client, _game_id, _service, repository = _client(tmp_path)
    with client:
        response = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "import",
                "gameId": str(uuid4()),
                "inputPayload": {
                    "schemaVersion": 1,
                    "sourcePath": "../outside.csv",
                    "contractVersion": 1,
                },
            },
        )

    assert response.status_code == 404
    assert response.json()["code"] == "GAME_NOT_FOUND"
    assert repository.items == {}


def test_failed_job_retry_requeues_the_same_record(tmp_path: Path) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    with client:
        created = _create_validate_job(client, game_id)
        job_id = UUID(cast(str, created["id"]))
        repository.items[job_id] = replace(
            repository.items[job_id],
            status=JobStatus.FAILED,
            error_code="TEST_FAILURE",
            error_message="Controlled failure.",
            finished_at=datetime.now(UTC),
        )

        retried = client.post(f"/api/v1/admin/jobs/{job_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["id"] == str(job_id)
    assert retried.json()["status"] == "created"
    assert retried.json()["error"] is None
