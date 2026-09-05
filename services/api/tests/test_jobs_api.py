import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.jobs import (
    PAYOUT_ALGORITHM_VERSION,
    ImageGeometryRolloutJobReference,
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
from game_predictor_api.domain.jobs import Job, JobError, JobStatus, JobType, create_job
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
from game_predictor_worker.images.pipeline_contract import (
    STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
    STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
)
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


def test_image_import_exposes_systemic_geometry_guard_progress() -> None:
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "source_directory": r"C:\photos",
            "pipeline_fingerprint": "a" * 64,
        },
        created_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    job = replace(
        job,
        checkpoint_payload={
            "geometry_systemic_guard": {
                "policyVersion": "image-geometry-systemic-guard-v1",
                "required": True,
                "passed": False,
                "reportChecksumSha256": "b" * 64,
                "reportRelativePath": "data/image-geometry-guards/report.json",
                "sourceCount": 2_200,
                "activeBoardCount": 19_800,
                "sampleSourceCount": 25,
                "sampleBoardCount": 225,
                "pageRegistrationReadyRate": 1.0,
                "finalCellGridReadyRate": 2 / 19_800,
                "invariantViolationCount": 0,
            },
            "geometry_guard_resolution": {
                "passed": True,
                "manifestChecksumSha256": "c" * 64,
                "correctedFullCount": 5,
                "partialCount": 2,
                "rejectedCount": 1,
            },
        },
    )

    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)

    assert response["progress"]["geometrySystemicGuard"] == {
        "policyVersion": "image-geometry-systemic-guard-v1",
        "required": True,
        "passed": False,
        "reportChecksumSha256": "b" * 64,
        "reportRelativePath": "data/image-geometry-guards/report.json",
        "sourceCount": 2_200,
        "activeBoardCount": 19_800,
        "sampleSourceCount": 25,
        "sampleBoardCount": 225,
        "pageRegistrationReadyRate": 1.0,
        "finalCellGridReadyRate": 2 / 19_800,
        "invariantViolationCount": 0,
        "resolutionApplied": True,
        "resolutionManifestChecksumSha256": "c" * 64,
        "correctedFullCount": 5,
        "partialCount": 2,
        "rejectedCount": 1,
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


def test_verified_v19_full_import_is_pinned_to_the_job(tmp_path: Path) -> None:
    _client_value, game_id, service, _repository = _client(tmp_path)
    source = tmp_path / "curated"
    source.mkdir()

    historical = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="historical",
        pipeline_fingerprint="a" * 64,
    )
    pinned = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="v20",
        pipeline_fingerprint="a" * 64,
        use_verified_board_cell_geometry=True,
    )

    assert "board_cell_processing" not in historical.input_payload
    processing = pinned.input_payload["board_cell_processing"]
    assert isinstance(processing, dict)
    assert processing["activationVersion"] == "board-cell-processing-v20-verified-v19-v1"
    assert processing["rolloutMode"] == "default_v19"
    assert processing["gridRows"] == 3
    assert processing["gridColumns"] == 5
    assert processing["topologyRulesVersionId"] == str(_repository.topology_rules_version_id)
    assert "image_geometry_rollout" not in pinned.input_payload
    assert (
        pinned.input_payload["pipeline_fingerprint"]
        != historical.input_payload["pipeline_fingerprint"]
    )
    response = JobResponse.from_domain(pinned).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["boardCellProcessing"] == processing


def test_new_browser_import_pins_systemic_geometry_guard_policy(tmp_path: Path) -> None:
    _client_value, game_id, service, _repository = _client(tmp_path)
    source = tmp_path / "browser"
    source.mkdir()

    job = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="browser",
        pipeline_fingerprint="a" * 64,
        source_manifest_sha256="b" * 64,
        start_mode="rerun_current_models",
        page_geometry_manifest={
            "checksumSha256": "c" * 64,
            "relativePath": "data/page-geometry-manifests/test.json",
            "preflightJobId": str(uuid4()),
        },
        use_verified_board_cell_geometry=True,
    )

    assert job.input_payload["schema_version"] == 7
    assert job.input_payload["geometry_systemic_guard_policy"] == {
        "policyVersion": "image-geometry-systemic-guard-v1",
        "minimumSourceCount": 100,
        "minimumActiveBoardCount": 500,
        "sampleSourceLimit": 25,
        "minimumFinalCellGridReadyRate": 0.98,
        "requireZeroInvariantViolations": True,
    }
    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["geometrySystemicGuardPolicy"] == {
        "policyVersion": "image-geometry-systemic-guard-v1",
        "minimumSourceCount": 100,
        "minimumActiveBoardCount": 500,
        "sampleSourceLimit": 25,
        "minimumFinalCellGridReadyRate": 0.98,
        "requireZeroInvariantViolations": True,
    }


def test_browser_schema_v7_fingerprint_binds_guard_resolution_manifest(
    tmp_path: Path,
) -> None:
    _client_value, game_id, service, repository = _client(tmp_path)
    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_lattice_v3",
        cell_asset_mode="virtual_default",
        revision=9,
    )
    source = tmp_path / "resolved-browser"
    source.mkdir()
    page_manifest = {
        "checksumSha256": "c" * 64,
        "relativePath": "data/page-geometry-manifests/test.json",
        "preflightJobId": str(uuid4()),
    }
    common = {
        "game_id": game_id,
        "source_directory": source,
        "source_display_name": "resolved-browser",
        "pipeline_fingerprint": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "start_mode": "rerun_current_models",
        "page_geometry_manifest": page_manifest,
    }
    without_resolution = service.create_image_import_job(selection_id=uuid4(), **common)
    resolution = {
        "id": str(uuid4()),
        "checksumSha256": "d" * 64,
        "relativePath": "data/image-geometry-guard-resolutions/dd/test.json",
        "guardJobId": str(uuid4()),
        "guardReportChecksumSha256": "e" * 64,
        "sourceManifestChecksumSha256": "b" * 64,
        "pageGeometryManifestChecksumSha256": "c" * 64,
    }
    with_resolution = service.create_image_import_job(
        selection_id=uuid4(),
        geometry_guard_resolution_manifest=resolution,
        **common,
    )

    assert without_resolution.input_payload["schema_version"] == 7
    assert with_resolution.input_payload["geometry_guard_resolution_manifest"] == resolution
    assert (
        with_resolution.input_payload["pipeline_fingerprint"]
        != without_resolution.input_payload["pipeline_fingerprint"]
    )


def test_geometry_guard_report_reconstruction_job_is_pinned_to_source_import(
    tmp_path: Path,
) -> None:
    _client_value, game_id, service, _repository = _client(tmp_path)
    source = tmp_path / "legacy-guard"
    source.mkdir()
    selection_id = uuid4()
    guard_job = service.create_image_import_job(
        game_id=game_id,
        selection_id=selection_id,
        source_directory=source,
        source_display_name="legacy-guard",
        pipeline_fingerprint="a" * 64,
    )

    reconstruction = service.create_geometry_guard_report_reconstruction_job(
        game_id=game_id,
        source_selection_id=selection_id,
        source_guard_job_id=guard_job.id,
        legacy_report_checksum_sha256="b" * 64,
        source_manifest_checksum_sha256="c" * 64,
        page_geometry_manifest_checksum_sha256="d" * 64,
    )

    assert reconstruction.job_type is JobType.VALIDATE
    assert reconstruction.input_payload == {
        "schema_version": 1,
        "validation_kind": "image_geometry_guard_report_reconstruction",
        "source_selection_id": str(selection_id),
        "source_guard_job_id": str(guard_job.id),
        "legacy_report_checksum_sha256": "b" * 64,
        "source_manifest_checksum_sha256": "c" * 64,
        "page_geometry_manifest_checksum_sha256": "d" * 64,
    }
    response = JobResponse.from_domain(reconstruction).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["validationKind"] == (
        "image_geometry_guard_report_reconstruction"
    )


def test_per_game_virtual_geometry_rollout_is_immutably_pinned_to_new_jobs(
    tmp_path: Path,
) -> None:
    _client_value, game_id, service, repository = _client(tmp_path)
    source = tmp_path / "curated"
    source.mkdir()
    historical = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="legacy",
        pipeline_fingerprint="a" * 64,
    )
    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_shadow",
        cell_asset_mode="virtual_shadow",
        revision=7,
    )

    shadow = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="shadow",
        pipeline_fingerprint="a" * 64,
    )

    legacy_rollout = historical.input_payload["image_geometry_rollout"]
    shadow_rollout = shadow.input_payload["image_geometry_rollout"]
    assert isinstance(legacy_rollout, dict)
    assert isinstance(shadow_rollout, dict)
    assert legacy_rollout["geometryMode"] == "legacy"
    assert legacy_rollout["geometryEngineVersion"] == (STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION)
    assert historical.input_payload["source_pipeline_fingerprint"] == "a" * 64
    assert shadow_rollout["geometryMode"] == "structured_shadow"
    assert shadow_rollout["cellAssetMode"] == "virtual_shadow"
    assert shadow_rollout["rolloutRevision"] == 7
    assert shadow_rollout["geometryEngineVersion"] == (STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION)
    assert shadow_rollout["schemaVersion"] == "virtual-geometry-rollout-snapshot-v2"
    candidate_geometry = shadow_rollout["candidateGeometry"]
    assert isinstance(candidate_geometry, dict)
    assert candidate_geometry["config"]["activationAllowed"] is False
    assert candidate_geometry["config"]["maturity"] == "experimental_measurement_only"
    assert candidate_geometry["config"]["configVersion"] == (
        "structured-lattice-candidate-v3-config-v1"
    )
    assert "board_cell_processing" in shadow.input_payload
    assert (
        shadow.input_payload["pipeline_fingerprint"]
        != historical.input_payload["pipeline_fingerprint"]
    )
    response = JobResponse.from_domain(shadow).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["imageGeometryRollout"] == shadow_rollout

    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_lattice_v3",
        cell_asset_mode="virtual_default",
        revision=8,
    )
    active = service.create_image_import_job(
        game_id=game_id,
        selection_id=uuid4(),
        source_directory=source,
        source_display_name="structured-v3",
        pipeline_fingerprint="a" * 64,
    )
    active_rollout = active.input_payload["image_geometry_rollout"]
    assert isinstance(active_rollout, dict)
    assert active_rollout["schemaVersion"] == "virtual-geometry-rollout-snapshot-v3"
    assert active_rollout["geometryMode"] == "structured_lattice_v3"
    assert active_rollout["cellAssetMode"] == "virtual_default"
    activation = active_rollout["activeLatticeGeometry"]
    assert isinstance(activation, dict)
    assert activation["config"]["activationAllowed"] is True
    assert activation["config"]["maturity"] == "accepted_primary"
    assert len(activation["config"]["acceptanceReportChecksumSha256"]) == 64


def test_verified_v20_import_requires_rules_and_supported_topology(tmp_path: Path) -> None:
    _client_value, game_id, service, repository = _client(tmp_path)
    source = tmp_path / "curated"
    source.mkdir()
    common = {
        "game_id": game_id,
        "source_directory": source,
        "source_display_name": "v20",
        "pipeline_fingerprint": "a" * 64,
        "use_verified_board_cell_geometry": True,
    }

    repository.board_topology = None
    with pytest.raises(JobError) as missing:
        service.create_image_import_job(selection_id=uuid4(), **common)
    assert missing.value.code == "GAME_BOARD_TOPOLOGY_REQUIRED"

    repository.board_topology = (2, 4)
    with pytest.raises(JobError) as unsupported:
        service.create_image_import_job(selection_id=uuid4(), **common)
    assert unsupported.value.code == "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"


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
                "algorithmVersion": PAYOUT_ALGORITHM_VERSION,
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
        JobType.SEMI_AUTOMATIC_IMAGE_SELECTION,
        JobType.SYMBOL_TRAINING,
        JobType.IMAGE_SYMBOL_REINFERENCE,
        JobType.IMAGE_GRID_REINFERENCE,
        JobType.IMAGE_SYMBOL_REVIEW_BULK,
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        JobType.STORAGE_GC,
        JobType.STORAGE_INVENTORY,
        JobType.STORAGE_PIPELINE_COMPACTION,
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
                    "algorithmVersion": PAYOUT_ALGORITHM_VERSION,
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


def test_filename_verification_retry_resets_only_technical_job_progress(
    tmp_path: Path,
) -> None:
    _client_instance, _game_id, service, repository = _client(tmp_path)
    job = replace(
        create_job(
            JobType.SEMI_AUTOMATIC_IMAGE_SELECTION,
            game_id=None,
            input_payload={
                "schema_version": 2,
                "selection_kind": "semi_automatic_image_selection",
                "workflow_mode": "filename_verification",
                "run_id": str(uuid4()),
                "source_upload_id": str(uuid4()),
                "source_manifest_checksum_sha256": "a" * 64,
                "source_fingerprint": "b" * 64,
                "source_count": 2_200,
                "first_sequence_number": 1,
                "last_sequence_number": 19_809,
                "direction": "ascending",
                "range_convention": "seq-inclusive-v1",
                "full_range_size": 9,
                "expected_ranges_fingerprint": "c" * 64,
                "recognizer_fingerprint": "d" * 64,
                "grouping_policy_fingerprint": "e" * 64,
            },
        ),
        status=JobStatus.FAILED,
        progress_current=2_200,
        progress_total=2_200,
        success_count=247,
        review_count=1_953,
        error_code="JOB_PROGRESS_REGRESSION",
        error_message="Review count cannot decrease.",
        finished_at=datetime.now(UTC),
    )
    repository.add_job(job)

    retried = service.retry_job(job.id)

    assert retried.id == job.id
    assert retried.status is JobStatus.CREATED
    assert retried.progress_current == 0
    assert retried.progress_total is None
    assert retried.success_count == 0
    assert retried.review_count == 0
    assert retried.error_code is None


def test_historical_filename_verification_retry_resets_technical_job_progress(
    tmp_path: Path,
) -> None:
    _client_instance, _game_id, service, repository = _client(tmp_path)
    job = replace(
        create_job(
            JobType.SEMI_AUTOMATIC_IMAGE_SELECTION,
            game_id=None,
            input_payload={
                "schema_version": 1,
                "selection_kind": "semi_automatic_image_selection",
                "run_id": str(uuid4()),
                "source_upload_id": str(uuid4()),
                "source_manifest_checksum_sha256": "a" * 64,
                "source_fingerprint": "b" * 64,
                "source_count": 2_200,
                "first_sequence_number": 1,
                "last_sequence_number": 19_809,
                "direction": "ascending",
                "range_convention": "seq-inclusive-v1",
                "full_range_size": 9,
                "expected_ranges_fingerprint": "c" * 64,
                "recognizer_fingerprint": RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
                "grouping_policy_fingerprint": "e" * 64,
            },
        ),
        status=JobStatus.FAILED,
        progress_current=2_200,
        progress_total=2_200,
        success_count=0,
        review_count=2_200,
        error_code="JOB_PROGRESS_REGRESSION",
        error_message="Progress counters cannot decrease.",
        finished_at=datetime.now(UTC),
    )
    repository.add_job(job)

    retried = service.retry_job(job.id)

    assert retried.status is JobStatus.CREATED
    assert retried.progress_current == 0
    assert retried.progress_total is None
    assert retried.success_count == 0
    assert retried.review_count == 0
