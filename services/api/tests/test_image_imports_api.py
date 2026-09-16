import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import NoReturn
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import (
    _geometry_manifest_descriptor,
    _image_import_preflight_checksum,
    _uses_touching_page_grid,
)
from game_predictor_api.application import controlled_folder_picker as folder_picker_module
from game_predictor_api.application import image_imports as image_imports_module
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    BrowserImageUpload,
    ImageFolderSelectionService,
    ImageSelectionPurpose,
    WindowsFolderPicker,
)
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.jobs import ImageGeometryRolloutJobReference, JobService
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    ImageImportEnginePolicySnapshot,
)
from game_predictor_api.domain.image_sequence_canonical import (
    ImageSequenceCanonicalService,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobError,
    JobType,
    checkpoint_job,
    complete_job,
    create_job,
    start_job,
)
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    bootstrap_symbol_model_snapshot,
    cold_start_unclassified_symbol_snapshot,
)
from game_predictor_api.main import create_app
from game_predictor_worker.images.lateral_partial_contract import (
    GeometryEngineVariant,
    LateralPartialGeometrySnapshot,
)
from game_predictor_worker.images.partial_grid_learning import (
    PartialGridPattern,
    PartialGridTrainingProfile,
)
from game_predictor_worker.images.pipeline_contract import (
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    StructuredGeometryActivationSnapshot,
)
from game_predictor_worker.images.structured_geometry import (
    structured_lattice_active_config_payload,
)
from PIL import Image
from test_image_selections import MemoryImageSelectionRepository
from test_jobs_domain import MemoryJobRepository

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


class RejectingImageWriteCapacityGuard:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def check_image_write(self, input_bytes: int) -> object:
        self.calls.append(input_bytes)
        raise JobConflictError(
            "STORAGE_CAPACITY_INSUFFICIENT",
            "Future managed artifacts would exceed the configured reserve.",
        )


def test_legacy_cold_start_preflight_checksum_keeps_the_golden_bytes() -> None:
    payload: dict[str, object] = {
        "geometryPreflightRequired": True,
        "schemaVersion": 1,
        "symbolModelBlockerCode": "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED",
        "symbolModelReady": False,
        "unclassifiedColdStartAllowed": True,
    }

    checksum = _image_import_preflight_checksum(
        payload=payload,
        geometry_engine_variant=None,
        symbol_model_inference_fingerprint=None,
        symbol_model_snapshot_fingerprint="s" * 64,
    )

    assert checksum == "4bf26fa30ff859f84459da60a54c3696a1e17c9dfd62b7e01d1e4a2ad43d9202"
    assert "symbolModelSnapshotFingerprint" not in payload


def _partial_training_profile(source_count: int) -> PartialGridTrainingProfile:
    return PartialGridTrainingProfile(
        patterns=(
            PartialGridPattern(
                unavailable_cell_indices=(0, 5, 10),
                sample_count=source_count,
                source_count=source_count,
            ),
        ),
        distinct_source_count=source_count,
    )


def test_v4_replay_lookup_keeps_pinned_profile_after_training_changes() -> None:
    game_id = uuid4()
    selection_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)
    policy = ImageImportEnginePolicySnapshot(
        game_id=game_id,
        policy=ImageImportEnginePolicy.STRUCTURED_LATTICE_V3,
        geometry_mode="structured_lattice_v3",
        cell_asset_mode="virtual_default",
        revision=4,
    )
    symbol = bootstrap_symbol_model_snapshot()
    rollout = GeometryPipelineRolloutSnapshot(
        geometry_mode=GeometryRolloutMode.STRUCTURED_LATTICE_V3,
        cell_asset_mode=CellAssetRolloutMode.VIRTUAL_DEFAULT,
        rollout_revision=4,
        geometry_engine_version="structured-opencv-pinned-preflight-v1",
        virtual_renderer_version="virtual-cell-renderer-v1",
        preprocessing_version="symbol-rgb-v1",
        active_lattice_geometry=StructuredGeometryActivationSnapshot.from_config_payload(
            structured_lattice_active_config_payload()
        ),
        lateral_partial_geometry=LateralPartialGeometrySnapshot(
            training_profile=_partial_training_profile(3),
        ),
    ).to_payload()

    def import_job(**overrides: object):
        payload: dict[str, object] = {
            "schema_version": 1,
            "source_selection_id": str(selection_id),
            "source_manifest_sha256": "a" * 64,
            "image_geometry_rollout": rollout,
            "symbol_model": symbol.to_payload(),
            "grid_profile": {"inferenceFingerprint": "g" * 64},
        }
        payload.update(overrides)
        return create_job(JobType.IMPORT, game_id=game_id, input_payload=payload, created_at=NOW)

    exact = repository.add_job(import_job())
    repository.add_job(import_job(source_manifest_sha256="x" * 64))
    repository.add_job(import_job(symbol_model={"inferenceFingerprint": "z" * 64}))
    repository.add_job(
        import_job(
            image_geometry_rollout={
                **rollout,
                "lateralPartialGeometry": {"variant": "structured_lattice_v4_partial_sides"},
            }
        )
    )

    found = service.get_image_import_run_by_source_selection(
        game_id=game_id,
        source_selection_id=selection_id,
        source_manifest_sha256="a" * 64,
        engine_policy=policy,
        symbol_model_inference_fingerprint=symbol.inference_fingerprint,
        symbol_model_snapshot_fingerprint=symbol.inference_fingerprint,
        grid_profile_inference_fingerprint="g" * 64,
        geometry_engine_variant=GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
    )

    assert found is not None
    assert found.id == exact.id


def test_v4_preflight_lookup_rejects_an_arbitrary_lateral_mapping() -> None:
    game_id = uuid4()
    selection_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)
    base = {
        "schema_version": 2,
        "validation_kind": "page_geometry_preflight",
        "source_selection_id": str(selection_id),
        "source_manifest_sha256": "a" * 64,
    }
    exact = repository.add_job(
        create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                **base,
                "lateral_partial_geometry": LateralPartialGeometrySnapshot(
                    training_profile=_partial_training_profile(3),
                    frame_support_review=False,
                ).to_payload(),
            },
            created_at=NOW,
        )
    )
    repository.add_job(
        create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                **base,
                "lateral_partial_geometry": {"variant": "structured_lattice_v4_partial_sides"},
            },
            created_at=NOW,
        )
    )

    found = service.get_page_geometry_preflight_by_source_selection(
        game_id=game_id,
        source_selection_id=selection_id,
        source_manifest_sha256="a" * 64,
        geometry_engine_variant=GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
    )

    assert found is not None
    assert found.id == exact.id


def test_v4_preflight_lookup_keeps_completed_snapshot_after_training_profile_changes() -> None:
    game_id = uuid4()
    selection_id = uuid4()
    repository = MemoryJobRepository(game_id)

    class ChangedTrainingProfileResolver:
        def partial_grid_training_profile(self, *, game_id: UUID) -> dict[str, object]:
            return _partial_training_profile(4).to_payload()

    service = JobService(
        repository,
        page_geometry_override_snapshot_resolver=ChangedTrainingProfileResolver(),
    )
    pinned = LateralPartialGeometrySnapshot(
        training_profile=_partial_training_profile(3),
    )
    completed = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(selection_id),
            "source_manifest_sha256": "a" * 64,
            "lateral_partial_geometry": pinned.to_payload(),
        },
        created_at=NOW,
    )
    lease_token = uuid4()
    completed = start_job(
        completed,
        worker_version="test-worker",
        worker_id="test-worker",
        lease_token=lease_token,
        lease_expires_at=NOW + timedelta(minutes=5),
        started_at=NOW,
    )
    completed = checkpoint_job(
        completed,
        lease_token=lease_token,
        checkpoint_payload={
            "schema_version": 1,
            "complete": True,
            "geometry_manifest_checksum_sha256": "b" * 64,
            "geometry_manifest_relative_path": "data/page-geometry-manifests/test.json",
        },
        stage="page_geometry_manifest_ready",
        current=1,
        total=1,
        success_count=1,
        failure_count=0,
        review_count=0,
        updated_at=NOW + timedelta(seconds=1),
    )
    completed = repository.add_job(
        complete_job(
            completed,
            lease_token=lease_token,
            finished_at=NOW + timedelta(seconds=2),
        )
    )

    found = service.get_page_geometry_preflight_by_source_selection(
        game_id=game_id,
        source_selection_id=selection_id,
        source_manifest_sha256="a" * 64,
        geometry_engine_variant=GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
    )

    assert completed.status.value == "completed"
    assert found is not None
    assert found.id == completed.id


@pytest.mark.skipif(os.name != "nt", reason="Windows-native folder picker")
def test_native_folder_picker_overrides_hidden_parent_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "select-folder.ps1"
    script.write_text("# controlled test helper", encoding="utf-8")
    selected = tmp_path / "photos"
    selected.mkdir()
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        **options: object,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["options"] = options
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "selected", "path": str(selected)}),
            stderr="",
        )

    monkeypatch.setattr(folder_picker_module.subprocess, "run", fake_run)

    result = WindowsFolderPicker(script).choose()

    assert result == selected.resolve()
    options = captured["options"]
    assert isinstance(options, dict)
    startup_info = options["startupinfo"]
    assert isinstance(startup_info, subprocess.STARTUPINFO)
    assert startup_info.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startup_info.wShowWindow == 1


def _client(
    tmp_path: Path,
    picker_path: Path | None,
) -> tuple[TestClient, UUID]:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    job_service = JobService(repository)
    selection_service = ImageFolderSelectionService(
        lambda: picker_path,
        clock=lambda: NOW,
    )
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
        )
    )
    return client, game_id


def test_legacy_folder_import_routes_are_absent(tmp_path: Path) -> None:
    client, game_id = _client(tmp_path, None)

    with client:
        paths = client.get("/openapi.json").json()["paths"]
        old_start = client.post(
            "/api/v1/admin/image-imports",
            json={"gameId": str(game_id), "selectionToken": "approved-token"},
        )

    assert "/api/v1/admin/image-imports" not in paths
    assert "/api/v1/admin/image-imports/preflight" not in paths
    assert "/api/v1/admin/image-imports/folder-selection" not in paths
    assert old_start.status_code == 404


def test_only_one_native_folder_picker_can_be_open() -> None:
    entered = Event()
    release = Event()

    def blocking_picker() -> None:
        entered.set()
        assert release.wait(timeout=2)
        return None

    service = ImageFolderSelectionService(blocking_picker)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_selection = executor.submit(service.select)
        assert entered.wait(timeout=1)

        with pytest.raises(JobConflictError) as error:
            service.select()

        assert error.value.code == "IMAGE_FOLDER_PICKER_ALREADY_OPEN"
        release.set()
        assert first_selection.result(timeout=1) is None


def test_fixed_picker_serializes_image_import_and_remote_host_windows() -> None:
    entered = Event()
    release = Event()
    picker = WindowsFolderPicker(Path("controlled.ps1"))

    def blocking_picker() -> None:
        entered.set()
        assert release.wait(timeout=2)
        return None

    picker._choose_exclusive = blocking_picker  # type: ignore[method-assign]
    image_service = ImageFolderSelectionService(picker)
    remote_service = RemoteManualSelectionHostService(picker)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_selection = executor.submit(image_service.select)
        assert entered.wait(timeout=1)

        with pytest.raises(JobConflictError) as error:
            remote_service.select_base()

        assert error.value.code == "IMAGE_FOLDER_PICKER_ALREADY_OPEN"
        release.set()
        assert first_selection.result(timeout=1) is None


def test_empty_folder_is_rejected_before_selection_token(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.mkdir()
    service = ImageFolderSelectionService(lambda: source, clock=lambda: NOW)

    with pytest.raises(JobError) as raised:
        service.select()

    assert raised.value.code == "IMAGE_FOLDER_EMPTY"


def test_browser_native_folder_upload_finalizes_without_legacy_import(tmp_path: Path) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    job_service = JobService(repository)
    image_bytes: list[bytes] = []
    for color in ((255, 0, 0), (0, 255, 0)):
        stream = BytesIO()
        Image.new("RGB", (32, 24), color).save(stream, "JPEG")
        image_bytes.append(stream.getvalue())
    total_bytes = sum(len(value) for value in image_bytes)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "Zdjecia gry",
                "expectedFileCount": 2,
                "expectedTotalBytes": total_bytes,
            },
        )
        assert created.status_code == 201
        upload_id = created.json()["uploadId"]

        for index, content in enumerate(image_bytes):
            uploaded = client.put(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/{index}",
                content=content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Image-Relative-Path": f"Zdjecia gry/layout-{index + 1}.jpg",
                },
            )
            assert uploaded.status_code == 200
            assert uploaded.json()["uploadedFileCount"] == index + 1

        finalized = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
        )
        assert finalized.status_code == 200
        selection = finalized.json()
        assert selection["status"] == "selected"
        assert selection["supportedFileCount"] == 2

        assert selection["path"] is None
        assert selection["selectionToken"] is not None


class _BrowserCanonicalRepository:
    def canonical_numbers(self, _game_id: UUID) -> set[int]:
        return set(range(1, 10))

    def canonical_source_checksums(self, _game_id: UUID) -> dict[int, str]:
        return {}


class _MutableBrowserCanonicalRepository(_BrowserCanonicalRepository):
    def __init__(self, numbers: set[int]) -> None:
        self.numbers = numbers

    def canonical_numbers(self, _game_id: UUID) -> set[int]:
        return set(self.numbers)


class _UnavailableSymbolModelResolver:
    def resolve(self, *, game_id: UUID) -> NoReturn:
        del game_id
        raise JobConflictError(
            "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED",
            "The bootstrap symbol model does not match this game's active symbol catalog.",
        )


class _ColdStartSymbolModelResolver(_UnavailableSymbolModelResolver):
    def resolve_unclassified_cold_start(self, *, game_id: UUID):
        del game_id
        return cold_start_unclassified_symbol_snapshot(("CYTRYNA", "WISNIA"))


def test_ready_browser_layout_import_preflight_and_start_are_idempotent(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    canonical_service = ImageSequenceCanonicalService(_BrowserCanonicalRepository())
    job_service = JobService(repository, artifact_root=tmp_path / "artifacts")
    image_bytes: list[bytes] = []
    for color in ((255, 0, 0), (0, 255, 0)):
        stream = BytesIO()
        Image.new("RGB", (32, 24), color).save(stream, "JPEG")
        image_bytes.append(stream.getvalue())
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: canonical_service,
            page_geometry_override_service_dependency=lambda: None,
        )
    )
    total_bytes = sum(len(value) for value in image_bytes)

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "1-18",
                "expectedFileCount": 2,
                "expectedTotalBytes": total_bytes,
                "gameId": str(game_id),
            },
        )
        assert created.status_code == 201
        upload_id = created.json()["uploadId"]
        for index, content in enumerate(image_bytes):
            uploaded = client.put(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/{index}",
                content=content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Image-Relative-Path": f"1-18/seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
                },
            )
            assert uploaded.status_code == 200
        finalized = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
        )
        assert finalized.status_code == 200

        ready = client.get("/api/v1/admin/image-imports/browser-selections?purpose=layout_import")
        assert ready.status_code == 200
        assert ready.json()[0]["uploadId"] == upload_id

        preflight = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )
        assert preflight.status_code == 200
        report = preflight.json()
        assert report["sourceFileCount"] == 2
        assert report["newSequenceCount"] == 9
        assert report["reusedSequenceCount"] == 9
        assert report["skippedSourceCount"] == 1
        assert report["firstUnresolvedSequence"] == 10
        assert report["geometryPreflightRequired"] is True
        assert report["symbolModelReady"] is True
        assert report["symbolModelBlockerCode"] is None
        assert len(report["symbolModelInferenceFingerprint"]) == 64
        assert report["geometryPreflightJob"] is None
        assert report["geometryPreflightArtifactReady"] is False
        assert (
            report["geometryPreflightArtifactBlockerCode"]
            == "IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED"
        )
        assert report["existingImportJob"] is None

        jobs_before_v4_report = tuple(
            repository.list_jobs(status=None, job_type=None, game_id=game_id, limit=100)
        )
        v4_report = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={
                "gameId": str(game_id),
                "geometryEngineVariant": "structured_lattice_v4_partial_sides",
            },
        )
        assert v4_report.status_code == 200
        assert v4_report.json()["geometryEngineVariantEnabled"] is True
        assert v4_report.json()["geometryEngineVariantBlockerCode"] is None
        assert v4_report.json()["preflightChecksumSha256"] == report["preflightChecksumSha256"]
        assert (
            tuple(repository.list_jobs(status=None, job_type=None, game_id=game_id, limit=100))
            == jobs_before_v4_report
        )

        missing_geometry = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": report["manifestChecksumSha256"],
                "preflightChecksumSha256": report["preflightChecksumSha256"],
            },
        )
        assert missing_geometry.status_code == 409
        assert missing_geometry.json()["code"] == "IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED"

        geometry_response = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            json={"gameId": str(game_id)},
        )
        assert geometry_response.status_code == 201, geometry_response.text
        geometry_job = repository.get_job(UUID(geometry_response.json()["job"]["id"]))
        assert geometry_job is not None
        geometry_manifest = {
            "gameId": str(game_id),
            "sourceSelectionId": upload_id,
            "sourceManifestChecksumSha256": report["manifestChecksumSha256"],
            "lateralPartialGeometry": geometry_job.input_payload["lateral_partial_geometry"],
            "entries": {},
        }
        manifest_bytes = json.dumps(geometry_manifest, sort_keys=True).encode()
        geometry_checksum = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = (
            tmp_path
            / "artifacts"
            / "data"
            / "page-geometry-manifests"
            / f"{geometry_checksum}.json"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
        lease_token = uuid4()
        geometry_job = start_job(
            geometry_job,
            worker_version="test-worker",
            worker_id="test-worker",
            lease_token=lease_token,
            lease_expires_at=NOW + timedelta(minutes=5),
            started_at=NOW,
        )
        geometry_job = checkpoint_job(
            geometry_job,
            lease_token=lease_token,
            checkpoint_payload={
                "schema_version": 1,
                "complete": True,
                "geometry_manifest_checksum_sha256": geometry_checksum,
                "geometry_manifest_relative_path": (
                    f"data/page-geometry-manifests/{geometry_checksum}.json"
                ),
            },
            stage="page_geometry_manifest_ready",
            current=2,
            total=2,
            success_count=1,
            failure_count=0,
            review_count=1,
            updated_at=NOW + timedelta(seconds=1),
        )
        repository.add_job(
            complete_job(
                geometry_job,
                lease_token=lease_token,
                finished_at=NOW + timedelta(seconds=2),
            )
        )

        replayed_report = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )
        assert replayed_report.status_code == 200
        assert replayed_report.json()["geometryPreflightJob"]["id"] == str(geometry_job.id)
        assert replayed_report.json()["geometryPreflightArtifactReady"] is True
        assert replayed_report.json()["geometryPreflightArtifactBlockerCode"] is None

        start_payload = {
            "gameId": str(game_id),
            "manifestChecksumSha256": report["manifestChecksumSha256"],
            "preflightChecksumSha256": report["preflightChecksumSha256"],
            "geometryPreflightJobId": str(geometry_job.id),
            "geometryManifestChecksumSha256": geometry_checksum,
        }
        invalid_resolution_reference = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                **start_payload,
                "geometryGuardResolutionManifestId": str(uuid4()),
            },
        )
        started = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json=start_payload,
        )
        replay = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json=start_payload,
        )
        rerun_current_models = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                **start_payload,
                "startMode": "rerun_current_models",
            },
        )

    assert started.status_code == 201
    assert started.json()["created"] is True
    assert started.json()["job"]["inputPayload"]["schemaVersion"] == 7
    assert invalid_resolution_reference.status_code == 409
    assert (
        invalid_resolution_reference.json()["code"] == "IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED"
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["job"]["id"] == started.json()["job"]["id"]
    assert (
        replay.json()["job"]["inputPayload"]["sourceManifestSha256"]
        == report["manifestChecksumSha256"]
    )
    import_payload = started.json()["job"]["inputPayload"]
    assert import_payload["imageGeometryRollout"]["geometryMode"] == "structured_lattice_v3"
    assert (
        import_payload["boardCellProcessing"]["activationVersion"]
        == "board-cell-processing-v20-verified-v19-v1"
    )
    assert rerun_current_models.status_code == 201, rerun_current_models.text
    assert rerun_current_models.json()["created"] is False
    assert rerun_current_models.json()["job"]["id"] == started.json()["job"]["id"]


def test_browser_report_and_geometry_preflight_remain_available_without_symbol_model(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    canonical_service = ImageSequenceCanonicalService(_BrowserCanonicalRepository())
    job_service = JobService(
        repository,
        symbol_model_snapshot_resolver=_UnavailableSymbolModelResolver(),
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(stream, "JPEG")
    image_bytes = stream.getvalue()
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: canonical_service,
            page_geometry_override_service_dependency=lambda: None,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "10-18",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(image_bytes),
                "gameId": str(game_id),
            },
        )
        assert created.status_code == 201
        upload_id = created.json()["uploadId"]
        uploaded = client.put(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/0",
            content=image_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "10-18/seq_10-18.jpg",
            },
        )
        assert uploaded.status_code == 200
        assert (
            client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
            ).status_code
            == 200
        )

        preflight = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )
        assert preflight.status_code == 200, preflight.text
        report = preflight.json()
        assert report["symbolModelReady"] is False
        assert report["symbolModelBlockerCode"] == "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED"
        assert report["unclassifiedColdStartAllowed"] is False
        assert report["symbolModelInferenceFingerprint"] is None
        assert len(report["gridProfileInferenceFingerprint"]) == 64

        geometry = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            json={"gameId": str(game_id)},
        )
        assert geometry.status_code == 201, geometry.text

        started = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": report["manifestChecksumSha256"],
                "preflightChecksumSha256": report["preflightChecksumSha256"],
            },
        )

    assert started.status_code == 409
    assert started.json()["code"] == "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED"
    assert not repository.list_jobs(
        status=None,
        job_type=JobType.IMPORT,
        game_id=game_id,
        limit=10,
    )


def test_first_browser_import_can_materialize_unclassified_crops_without_a_model(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    job_service = JobService(
        repository,
        symbol_model_snapshot_resolver=_ColdStartSymbolModelResolver(),
        artifact_root=tmp_path / "artifacts",
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(stream, "JPEG")
    image_bytes = stream.getvalue()
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: ImageSequenceCanonicalService(
                _BrowserCanonicalRepository()
            ),
            page_geometry_override_service_dependency=lambda: None,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "10-18",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(image_bytes),
                "gameId": str(game_id),
            },
        )
        upload_id = created.json()["uploadId"]
        client.put(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/0",
            content=image_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "10-18/seq_10-18.jpg",
            },
        )
        client.post(f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize")
        preflight = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        ).json()
        assert preflight["symbolModelReady"] is False
        assert preflight["unclassifiedColdStartAllowed"] is True
        cold_start = cold_start_unclassified_symbol_snapshot(("CYTRYNA", "WISNIA"))
        assert preflight["symbolModelInferenceFingerprint"] is None
        assert preflight["symbolModelSnapshotFingerprint"] == cold_start.inference_fingerprint

        geometry_response = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            json={"gameId": str(game_id)},
        )
        assert geometry_response.status_code == 201, geometry_response.text
        geometry_job = repository.get_job(UUID(geometry_response.json()["job"]["id"]))
        assert geometry_job is not None
        geometry_manifest = {
            "gameId": str(game_id),
            "sourceSelectionId": upload_id,
            "sourceManifestChecksumSha256": preflight["manifestChecksumSha256"],
            "lateralPartialGeometry": geometry_job.input_payload["lateral_partial_geometry"],
            "entries": {},
        }
        manifest_bytes = json.dumps(geometry_manifest, sort_keys=True).encode()
        geometry_checksum = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = (
            tmp_path
            / "artifacts"
            / "data"
            / "page-geometry-manifests"
            / f"{geometry_checksum}.json"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
        lease_token = uuid4()
        geometry_job = start_job(
            geometry_job,
            worker_version="test-worker",
            worker_id="test-worker",
            lease_token=lease_token,
            lease_expires_at=NOW + timedelta(minutes=5),
            started_at=NOW,
        )
        geometry_job = checkpoint_job(
            geometry_job,
            lease_token=lease_token,
            checkpoint_payload={
                "schema_version": 1,
                "complete": True,
                "geometry_manifest_checksum_sha256": geometry_checksum,
                "geometry_manifest_relative_path": (
                    f"data/page-geometry-manifests/{geometry_checksum}.json"
                ),
            },
            stage="page_geometry_manifest_ready",
            current=1,
            total=1,
            success_count=1,
            failure_count=0,
            review_count=0,
            updated_at=NOW + timedelta(seconds=1),
        )
        geometry_job = complete_job(
            geometry_job,
            lease_token=lease_token,
            finished_at=NOW + timedelta(seconds=2),
        )
        repository.add_job(geometry_job)

        started = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": preflight["manifestChecksumSha256"],
                "preflightChecksumSha256": preflight["preflightChecksumSha256"],
                "geometryPreflightJobId": str(geometry_job.id),
                "geometryManifestChecksumSha256": geometry_checksum,
                "symbolModelSnapshotFingerprint": cold_start.inference_fingerprint,
            },
        )

        assert started.status_code == 201, started.text
        started_job = repository.get_job(UUID(started.json()["job"]["id"]))
        assert started_job is not None
        assert (
            SymbolModelJobSnapshot.from_payload(
                started_job.input_payload["symbol_model"]
            ).inference_fingerprint
            == cold_start.inference_fingerprint
        )
        assert started_job.input_payload["source_selection_id"] == upload_id
        assert (
            started_job.input_payload["source_manifest_sha256"]
            == preflight["manifestChecksumSha256"]
        )
        assert (
            started_job.input_payload["grid_profile"]["inferenceFingerprint"]
            == preflight["gridProfileInferenceFingerprint"]
        )
        current_policy = job_service.current_image_import_engine_policy(game_id=game_id)
        assert current_policy.policy is ImageImportEnginePolicy.VERIFIED_V19
        assert (
            started_job.input_payload["image_geometry_rollout"]["geometryMode"]
            == "structured_lattice_v3"
        )
        repository.add_job(
            create_job(
                JobType.IMPORT,
                game_id=game_id,
                input_payload={
                    **started_job.input_payload,
                    "symbol_model": {
                        "inferenceFingerprint": cold_start.inference_fingerprint,
                    },
                },
                created_at=NOW + timedelta(seconds=3),
            )
        )
        exact_replay = job_service.get_image_import_run_by_source_selection(
            game_id=game_id,
            source_selection_id=UUID(upload_id),
            source_manifest_sha256=preflight["manifestChecksumSha256"],
            engine_policy=current_policy,
            symbol_model_inference_fingerprint=None,
            symbol_model_snapshot_fingerprint=cold_start.inference_fingerprint,
            grid_profile_inference_fingerprint=preflight["gridProfileInferenceFingerprint"],
            geometry_engine_variant=GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        )
        assert exact_replay is not None, started_job.input_payload
        assert exact_replay.id == started_job.id
        replayed = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )

    assert started.status_code == 201, started.text
    snapshot = started.json()["job"]["inputPayload"]["symbolModel"]
    assert snapshot["inferenceMode"] == "unclassified"
    assert snapshot["modelVersion"] == "cold-start-unclassified-v1"
    assert replayed.status_code == 200
    assert replayed.json()["existingImportJob"]["id"] == started.json()["job"]["id"]


def test_structured_shadow_cold_start_bootstraps_required_geometry_preflight(
    tmp_path: Path,
) -> None:
    class RetentionGuard:
        def record_ready(self, **_values: object) -> None:
            return None

        def record_in_use(self, **_values: object) -> None:
            raise AssertionError(
                "A newly created source-bound job must pin retention in its own transaction."
            )

        def record_ingested(self, _handoff: object) -> None:
            return None

        def discard_unused(self, *, upload_id: UUID) -> None:
            del upload_id

    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_shadow",
        cell_asset_mode="virtual_shadow",
        revision=1,
    )
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
        retention=RetentionGuard(),
    )

    canonical_service = ImageSequenceCanonicalService(_BrowserCanonicalRepository())
    job_service = JobService(repository, artifact_root=tmp_path / "artifacts")
    stream = BytesIO()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(stream, "JPEG")
    image_bytes = stream.getvalue()
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: canonical_service,
            page_geometry_override_service_dependency=lambda: None,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "10-18",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(image_bytes),
                "gameId": str(game_id),
            },
        )
        upload_id = created.json()["uploadId"]
        uploaded = client.put(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/0",
            content=image_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "10-18/seq_10-18.jpg",
            },
        )
        assert uploaded.status_code == 200
        assert (
            client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
            ).status_code
            == 200
        )

        preflight = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )
        assert preflight.status_code == 200
        report = preflight.json()
        assert report["imageEnginePolicy"] == "structured_shadow"
        assert report["imageEnginePolicyRevision"] == 1
        assert report["geometryPreflightRequired"] is True

        missing_geometry = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": report["manifestChecksumSha256"],
                "preflightChecksumSha256": report["preflightChecksumSha256"],
                "imageEnginePolicy": "structured_shadow",
                "imageEnginePolicyRevision": 1,
                "boardCellProcessingMode": "structured_shadow",
            },
        )
        geometry = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            json={"gameId": str(game_id)},
        )
        assert geometry.status_code == 201, geometry.text
        geometry_job_id = UUID(geometry.json()["job"]["id"])
        geometry_job = job_service.get_job(geometry_job_id)
        profile = geometry_job.input_payload["page_registration_profile"]
        assert isinstance(profile, dict)
        assert profile["policy"] == "verified-page-registration-v1"
        assert profile["anchors"] == []
        masked_geometry = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            json={
                "gameId": str(game_id),
                "pageRegistrationVariant": "board_area_test",
            },
        )
        assert masked_geometry.status_code == 201, masked_geometry.text
        assert masked_geometry.json()["created"] is True
        masked_job = job_service.get_job(UUID(masked_geometry.json()["job"]["id"]))
        masked_profile = masked_job.input_payload["page_registration_profile"]
        assert isinstance(masked_profile, dict)
        assert (
            masked_job.input_payload["preflight_policy_version"]
            == "page-geometry-preflight-v3-board-area-mask"
        )
        assert masked_profile["policy"] == "verified-page-registration-v2-board-area-mask-v1"
        assert masked_profile["anchorMaskPaddingRatio"] == 0.1
        geometry_manifest = {
            "gameId": str(game_id),
            "sourceSelectionId": upload_id,
            "sourceManifestChecksumSha256": report["manifestChecksumSha256"],
            "lateralPartialGeometry": geometry_job.input_payload["lateral_partial_geometry"],
            "entries": {},
        }
        manifest_bytes = json.dumps(geometry_manifest, sort_keys=True).encode()
        geometry_checksum = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = (
            tmp_path
            / "artifacts"
            / "data"
            / "page-geometry-manifests"
            / f"{geometry_checksum}.json"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
        lease_token = uuid4()
        geometry_job = start_job(
            geometry_job,
            worker_version="test-worker",
            worker_id="test-worker",
            lease_token=lease_token,
            lease_expires_at=NOW + timedelta(minutes=5),
            started_at=NOW,
        )
        geometry_job = checkpoint_job(
            geometry_job,
            lease_token=lease_token,
            checkpoint_payload={
                "schema_version": 1,
                "complete": True,
                "geometry_manifest_checksum_sha256": geometry_checksum,
                "geometry_manifest_relative_path": (
                    f"data/page-geometry-manifests/{geometry_checksum}.json"
                ),
            },
            stage="page_geometry_manifest_ready",
            current=1,
            total=1,
            success_count=0,
            failure_count=0,
            review_count=1,
            updated_at=NOW + timedelta(seconds=1),
        )
        repository.save_job(
            complete_job(
                geometry_job,
                lease_token=lease_token,
                finished_at=NOW + timedelta(seconds=2),
            )
        )
        started = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json={
                "gameId": str(game_id),
                "manifestChecksumSha256": report["manifestChecksumSha256"],
                "preflightChecksumSha256": report["preflightChecksumSha256"],
                "geometryPreflightJobId": str(geometry_job_id),
                "geometryManifestChecksumSha256": geometry_checksum,
                "imageEnginePolicy": "structured_shadow",
                "imageEnginePolicyRevision": 1,
                "boardCellProcessingMode": "structured_shadow",
            },
        )

    assert missing_geometry.status_code == 409
    assert missing_geometry.json()["code"] == "IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED"
    assert started.status_code == 201, started.text
    payload = started.json()["job"]["inputPayload"]
    assert payload["imageGeometryRollout"]["geometryMode"] == "structured_lattice_v3"
    assert payload["pageGeometryManifest"] == {
        "checksumSha256": geometry_checksum,
        "preflightJobId": str(geometry_job_id),
        "relativePath": f"data/page-geometry-manifests/{geometry_checksum}.json",
    }


def test_browser_upload_plan_skips_complete_ranges_before_staging_bytes(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    canonical_service = ImageSequenceCanonicalService(_BrowserCanonicalRepository())
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            job_service_dependency=lambda: JobService(repository),
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: canonical_service,
        )
    )

    with client:
        response = client.post(
            "/api/v1/admin/image-imports/browser-selections/upload-plan",
            json={
                "gameId": str(game_id),
                "files": [
                    {
                        "sourceIndex": 0,
                        "relativePath": "seq_1-9.jpg",
                        "sizeBytes": 100,
                    },
                    {
                        "sourceIndex": 1,
                        "relativePath": "seq_10-18.jpg",
                        "sizeBytes": 200,
                    },
                ],
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["selectedFileCount"] == 2
    assert payload["uploadFileCount"] == 1
    assert payload["uploadTotalBytes"] == 200
    assert payload["skippedCompleteSourceCount"] == 1
    assert payload["skippedCompleteSources"] == [
        {
            "relativePath": "seq_1-9.jpg",
            "sequenceRangeEnd": 9,
            "sequenceRangeStart": 1,
            "sourceIndex": 0,
        }
    ]
    assert payload["filesToUpload"] == [
        {
            "relativePath": "seq_10-18.jpg",
            "sizeBytes": 200,
            "sourceIndex": 1,
            "uploadIndex": 0,
        }
    ]


def test_browser_preflight_rejects_a_stale_range_skipped_before_upload(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=10 * 1024 * 1024,
        clock=lambda: NOW,
    )
    canonical_repository = _MutableBrowserCanonicalRepository(set(range(1, 10)))
    canonical_service = ImageSequenceCanonicalService(canonical_repository)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            job_service_dependency=lambda: JobService(repository),
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
            image_sequence_canonical_service_dependency=lambda: canonical_service,
            page_geometry_override_service_dependency=lambda: None,
        )
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(stream, "JPEG")
    image_bytes = stream.getvalue()

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "10-18",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(image_bytes),
                "gameId": str(game_id),
                "uploadPlanChecksumSha256": "a" * 64,
                "skippedCanonicalRanges": [{"sequenceRangeStart": 1, "sequenceRangeEnd": 9}],
            },
        )
        assert created.status_code == 201, created.text
        upload_id = created.json()["uploadId"]
        uploaded = client.put(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/0",
            content=image_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "seq_10-18.jpg",
            },
        )
        assert uploaded.status_code == 200, uploaded.text
        assert (
            client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
            ).status_code
            == 200
        )
        canonical_repository.numbers.clear()
        preflight = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            json={"gameId": str(game_id)},
        )

    assert preflight.status_code == 409
    assert preflight.json()["code"] == "IMAGE_SEQUENCE_UPLOAD_PLAN_STALE"


def test_geometry_manifest_descriptor_allows_review_listing_without_checksum() -> None:
    game_id = uuid4()
    upload_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)
    checksum = "d" * 64
    job = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(upload_id),
            "source_directory": "C:/staging",
            "source_display_name": "1-9",
            "source_manifest_sha256": "a" * 64,
            "page_registration_profile": {
                "policy": "verified-page-registration-v1",
                "anchors": [{}],
            },
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
        },
        created_at=NOW,
    )
    lease_token = uuid4()
    started = start_job(
        job,
        worker_version="test-worker",
        worker_id="test-worker",
        lease_token=lease_token,
        lease_expires_at=NOW + timedelta(minutes=5),
        started_at=NOW,
    )
    checkpointed = checkpoint_job(
        started,
        lease_token=lease_token,
        checkpoint_payload={
            "schema_version": 1,
            "complete": True,
            "geometry_manifest_checksum_sha256": checksum,
            "geometry_manifest_relative_path": f"data/page-geometry-manifests/{checksum}.json",
        },
        stage="page_geometry_manifest_ready",
        current=1,
        total=1,
        success_count=1,
        failure_count=0,
        review_count=0,
        updated_at=NOW + timedelta(seconds=1),
    )
    repository.add_job(
        complete_job(
            checkpointed,
            lease_token=lease_token,
            finished_at=NOW + timedelta(seconds=2),
        )
    )

    descriptor = _geometry_manifest_descriptor(
        job_service=service,
        game_id=game_id,
        upload_id=upload_id,
        preflight_job_id=job.id,
        expected_checksum=None,
    )

    assert descriptor is not None
    assert descriptor["checksumSha256"] == checksum


@pytest.mark.parametrize("selective_board_review", [False, True])
def test_geometry_review_listing_keeps_manual_overrides_editable_until_batch_submit(
    tmp_path: Path,
    selective_board_review: bool,
) -> None:
    game_id = uuid4()
    upload_id = uuid4()
    repository = MemoryJobRepository(game_id)
    service = JobService(repository)
    old_checksum = "1" * 64
    current_checksum = "2" * 64
    manual_source_checksum = "a" * 64
    unresolved_source_checksum = "b" * 64
    quads = [
        [
            {"x": column * 20, "y": row * 20},
            {"x": column * 20 + 15, "y": row * 20},
            {"x": column * 20 + 15, "y": row * 20 + 15},
            {"x": column * 20, "y": row * 20 + 15},
        ]
        for row in range(3)
        for column in range(3)
    ]
    manifest = {
        "entries": {
            manual_source_checksum: {
                "registrationVersion": "manual-page-geometry-override-v1",
                "sourceRelativePath": "new/seq_1-9.jpg",
                "status": "registered",
            },
            unresolved_source_checksum: {
                "sourceRelativePath": "new/seq_10-14.jpg",
                "status": "review_required",
                "reasonCode": "PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT",
                **(
                    {
                        "lateralRegistrationCandidate": {
                            "version": "lateral-page-registration-candidate-v3"
                        }
                    }
                    if selective_board_review
                    else {}
                ),
                "registrationDiagnostics": {
                    "version": "page-registration-diagnostics-v1",
                    "bestAttempt": {
                        "featureCount": 1000,
                        "reasonCode": "PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT",
                        "meanRedEdgeCoverage": 0.68,
                    },
                    "attempts": [],
                },
            },
        },
        "registeredSourceCount": 1,
        "reviewRequiredSourceCount": 1,
        "skippedHumanResolvedSourceCount": 0,
    }
    content = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_checksum = hashlib.sha256(content).hexdigest()
    relative_path = f"data/page-geometry-manifests/{manifest_checksum}.json"
    manifest_path = tmp_path / "artifacts" / Path(*relative_path.split("/"))
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(content)
    job = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(upload_id),
            "source_directory": "C:/staging",
            "source_display_name": "new",
            "source_manifest_sha256": "c" * 64,
            "page_registration_profile": {"policy": "test", "anchors": []},
            "lateral_partial_geometry": (
                LateralPartialGeometrySnapshot(
                    frame_support_review=True, selective_frame_review=True
                ).to_payload()
                if selective_board_review
                else None
            ),
            "page_geometry_overrides": {
                manual_source_checksum: {"decisionChecksumSha256": old_checksum}
            },
            "canonical_sequence_numbers": [],
        },
        created_at=NOW,
    )
    lease_token = uuid4()
    job = start_job(
        job,
        worker_version="test-worker",
        worker_id="test-worker",
        lease_token=lease_token,
        lease_expires_at=NOW + timedelta(minutes=5),
        started_at=NOW,
    )
    job = checkpoint_job(
        job,
        lease_token=lease_token,
        checkpoint_payload={
            "schema_version": 1,
            "complete": True,
            "geometry_manifest_checksum_sha256": manifest_checksum,
            "geometry_manifest_relative_path": relative_path,
        },
        stage="page_geometry_manifest_ready",
        current=2,
        total=2,
        success_count=1,
        failure_count=0,
        review_count=1,
        updated_at=NOW + timedelta(seconds=1),
    )
    repository.add_job(
        complete_job(job, lease_token=lease_token, finished_at=NOW + timedelta(seconds=2))
    )

    class OverrideSnapshot:
        def snapshot(self, *, game_id: UUID) -> dict[str, object]:
            return {
                manual_source_checksum: {
                    "decisionChecksumSha256": current_checksum,
                    "quads": quads,
                    "revision": 2,
                }
            }

        def partial_grid_training_profile(self, *, game_id: UUID) -> None:
            return None

        def exclusion_snapshot(
            self, *, game_id: UUID, browser_selection_id: UUID
        ) -> dict[str, object]:
            return {}

    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            job_service_dependency=lambda: service,
            page_geometry_override_service_dependency=lambda: OverrideSnapshot(),
        )
    )

    with client:
        response = client.get(
            "/api/v1/admin/image-imports/"
            f"browser-selections/{upload_id}/geometry-preflights/{job.id}/review-sources",
            params={"game_id": str(game_id)},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [source["sequenceRangeStart"] for source in payload["sources"]] == (
        [1] if selective_board_review else [1, 10]
    )
    assert [source["expectedBoardCount"] for source in payload["sources"]] == (
        [9] if selective_board_review else [9, 5]
    )
    assert payload["reviewRequiredSourceCount"] == (0 if selective_board_review else 1)
    manual = payload["sources"][0]
    assert manual["reviewReason"] == "manual_override"
    assert manual["geometryOrigin"] == "manual_override"
    assert manual["existingFinalQuads"] == quads
    assert manual["existingOverrideRevision"] == 2
    assert manual["savedSincePreflight"] is True
    if selective_board_review:
        return
    unresolved = payload["sources"][1]
    assert unresolved["reviewReason"] == "review_required"
    assert unresolved["geometryOrigin"] == "manual_template"
    assert unresolved["rejectionReasonCode"] == ("PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT")
    assert unresolved["registrationDiagnostics"]["bestAttempt"] == {
        "anchorSourceChecksumSha256": None,
        "featureCount": 1000,
        "inlierCount": None,
        "inlierRatio": None,
        "matchCount": None,
        "meanRedEdgeCoverage": 0.68,
        "minimumBoardRedEdgeCoverage": None,
        "p95ReprojectionError": None,
        "reasonCode": "PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT",
        "targetFeatureCount": None,
    }


def test_legacy_touching_page_grid_is_reopened_but_separated_frames_are_not() -> None:
    touching = [
        [
            {"x": column * 20, "y": row * 20},
            {"x": (column + 1) * 20, "y": row * 20},
            {"x": (column + 1) * 20, "y": (row + 1) * 20},
            {"x": column * 20, "y": (row + 1) * 20},
        ]
        for row in range(3)
        for column in range(3)
    ]
    separated = [
        [
            {"x": column * 20, "y": row * 20},
            {"x": column * 20 + 15, "y": row * 20},
            {"x": column * 20 + 15, "y": row * 20 + 15},
            {"x": column * 20, "y": row * 20 + 15},
        ]
        for row in range(3)
        for column in range(3)
    ]

    assert _uses_touching_page_grid({"quads": touching}) is True
    assert _uses_touching_page_grid({"quads": separated}) is False


def test_game_less_ready_staging_is_bound_once(tmp_path: Path) -> None:
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (20, 30, 40)).save(stream, "JPEG")
    content = stream.getvalue()
    upload = service.begin(
        display_name="history",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )
    service.upload_file(
        upload.upload_id,
        0,
        relative_path="history/seq_1-9.jpg",
        content=content,
    )
    service.finalize(upload.upload_id)
    game_id = uuid4()

    bound = service.bind_ready_game(upload.upload_id, game_id)

    assert bound.upload.game_id == game_id
    assert service.get_ready(upload.upload_id).upload.game_id == game_id
    with pytest.raises(JobError) as error:
        service.bind_ready_game(upload.upload_id, uuid4())
    assert error.value.code == "IMAGE_FOLDER_SELECTION_GAME_MISMATCH"


def test_replacement_forks_staging_and_replays_after_restart(tmp_path: Path) -> None:
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    root = tmp_path / "imports"
    service = BrowserImageSelectionService(
        selection_service, root, max_bytes=1024 * 1024, clock=lambda: NOW
    )
    game_id = uuid4()

    def jpeg(color: tuple[int, int, int]) -> bytes:
        stream = BytesIO()
        Image.new("RGB", (32, 24), color).save(stream, "JPEG")
        return stream.getvalue()

    originals = (jpeg((20, 30, 40)), jpeg((50, 60, 70)))
    upload = service.begin(
        display_name="cut",
        expected_file_count=2,
        expected_total_bytes=sum(map(len, originals)),
        game_id=game_id,
    )
    for index, content in enumerate(originals):
        service.upload_file(
            upload.upload_id,
            index,
            relative_path=f"cut/seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
            content=content,
        )
    service.finalize(upload.upload_id)
    old_ready = service.get_ready(upload.upload_id)
    replacement = jpeg((80, 90, 100))
    old_source = old_ready.manifest.files[1]

    revised = service.fork_ready_with_replacement(
        upload.upload_id,
        game_id=game_id,
        source_checksum_sha256=old_source.checksum_sha256,
        source_relative_path=old_source.relative_path,
        content=replacement,
    )

    assert revised.upload.upload_id != upload.upload_id
    assert revised.manifest.checksum_sha256 != old_ready.manifest.checksum_sha256
    assert revised.manifest.files[0].checksum_sha256 == old_ready.manifest.files[0].checksum_sha256
    assert revised.manifest.files[1].checksum_sha256 == hashlib.sha256(replacement).hexdigest()
    assert (
        service.get_ready(upload.upload_id).manifest.checksum_sha256
        == old_ready.manifest.checksum_sha256
    )
    assert revised.upload.replacement_parent_upload_id == upload.upload_id
    assert revised.upload.replacement_parent_manifest_sha256 == old_ready.manifest.checksum_sha256
    with pytest.raises(JobConflictError) as unconfirmed:
        service.require_current_ready(revised.upload.upload_id, game_id)
    assert unconfirmed.value.code == "IMAGE_REPLACEMENT_NOT_CONFIRMED"
    assert [item.upload.upload_id for item in service.list_ready()] == [upload.upload_id]
    with pytest.raises(JobConflictError) as pending:
        service.require_current_ready(upload.upload_id, game_id)
    assert pending.value.code == "IMAGE_REPLACEMENT_PENDING"

    restarted = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        root,
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    replayed = restarted.fork_ready_with_replacement(
        upload.upload_id,
        game_id=game_id,
        source_checksum_sha256=old_source.checksum_sha256,
        source_relative_path=old_source.relative_path,
        content=replacement,
    )
    assert replayed.upload.upload_id == revised.upload.upload_id
    restarted.discard_pending_replacement(
        upload.upload_id, revised.upload.upload_id, game_id=game_id
    )
    assert (
        restarted.require_current_ready(upload.upload_id, game_id).upload.upload_id
        == upload.upload_id
    )
    with pytest.raises(JobConflictError) as discarded:
        restarted.confirm_ready_replacement(
            upload.upload_id,
            revised.upload.upload_id,
            game_id=game_id,
            source_checksum_sha256=old_source.checksum_sha256,
            source_relative_path=old_source.relative_path,
            replacement_checksum_sha256=hashlib.sha256(replacement).hexdigest(),
        )
    assert discarded.value.code == "IMAGE_REPLACEMENT_REVISION_CONFLICT"
    restarted.fork_ready_with_replacement(
        upload.upload_id,
        game_id=game_id,
        source_checksum_sha256=old_source.checksum_sha256,
        source_relative_path=old_source.relative_path,
        content=replacement,
    )
    write_state = restarted._write_upload_state

    def fail_after_child_state(value: BrowserImageUpload) -> None:
        if value.upload_id == upload.upload_id:
            raise OSError("interrupted before parent publication")
        write_state(value)

    restarted._write_upload_state = fail_after_child_state
    with pytest.raises(OSError):
        restarted.confirm_ready_replacement(
            upload.upload_id,
            revised.upload.upload_id,
            game_id=game_id,
            source_checksum_sha256=old_source.checksum_sha256,
            source_relative_path=old_source.relative_path,
            replacement_checksum_sha256=hashlib.sha256(replacement).hexdigest(),
        )
    restarted = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        root,
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    assert revised.upload.upload_id in [item.upload.upload_id for item in restarted.list_ready()]
    published = restarted.confirm_ready_replacement(
        upload.upload_id,
        revised.upload.upload_id,
        game_id=game_id,
        source_checksum_sha256=old_source.checksum_sha256,
        source_relative_path=old_source.relative_path,
        replacement_checksum_sha256=hashlib.sha256(replacement).hexdigest(),
    )
    assert published.upload.upload_id == revised.upload.upload_id
    assert (
        restarted.confirm_ready_replacement(
            upload.upload_id,
            revised.upload.upload_id,
            game_id=game_id,
            source_checksum_sha256=old_source.checksum_sha256,
            source_relative_path=old_source.relative_path,
            replacement_checksum_sha256=hashlib.sha256(replacement).hexdigest(),
        ).upload.upload_id
        == revised.upload.upload_id
    )
    cold = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        root,
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    with pytest.raises(JobConflictError) as superseded:
        cold.require_current_ready(upload.upload_id, game_id)
    assert superseded.value.code == "IMAGE_BROWSER_SELECTION_SUPERSEDED"
    assert [item.upload.upload_id for item in cold.list_ready()] == [revised.upload.upload_id]


@pytest.mark.parametrize("geometry_accepted", [False, True])
def test_page_source_replacement_api_blocks_accepted_geometry(
    tmp_path: Path, geometry_accepted: bool
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service, tmp_path / "imports", max_bytes=1024 * 1024, clock=lambda: NOW
    )

    def jpeg(color: tuple[int, int, int]) -> bytes:
        stream = BytesIO()
        Image.new("RGB", (32, 24), color).save(stream, "JPEG")
        return stream.getvalue()

    old_content = jpeg((20, 30, 40))
    new_content = jpeg((80, 90, 100))
    upload = browser_service.begin(
        display_name="cut",
        expected_file_count=1,
        expected_total_bytes=len(old_content),
        game_id=game_id,
    )
    browser_service.upload_file(
        upload.upload_id, 0, relative_path="cut/seq_1-9.jpg", content=old_content
    )
    browser_service.finalize(upload.upload_id)
    source_checksum = hashlib.sha256(old_content).hexdigest()
    manifest = {
        "entries": {
            source_checksum: {"status": "review_required", "sourceRelativePath": "cut/seq_1-9.jpg"}
        },
        "registeredSourceCount": 0,
        "reviewRequiredSourceCount": 1,
        "skippedHumanResolvedSourceCount": 0,
    }
    encoded = json.dumps(manifest).encode()
    checksum = hashlib.sha256(encoded).hexdigest()
    relative = f"data/page-geometry-manifests/{checksum}.json"
    path = tmp_path / "artifacts" / Path(*relative.split("/"))
    path.parent.mkdir(parents=True)
    path.write_bytes(encoded)
    repository = MemoryJobRepository(game_id)
    job = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(upload.upload_id),
            "source_manifest_sha256": browser_service.get_ready(
                upload.upload_id
            ).manifest.checksum_sha256,
        },
        created_at=NOW,
    )
    lease = uuid4()
    started = start_job(
        job,
        worker_version="test",
        worker_id="test",
        lease_token=lease,
        lease_expires_at=NOW + timedelta(minutes=5),
        started_at=NOW,
    )
    checkpointed = checkpoint_job(
        started,
        lease_token=lease,
        checkpoint_payload={
            "schema_version": 1,
            "complete": True,
            "geometry_manifest_checksum_sha256": checksum,
            "geometry_manifest_relative_path": relative,
        },
        stage="done",
        current=1,
        total=1,
        success_count=0,
        failure_count=0,
        review_count=1,
        updated_at=NOW + timedelta(seconds=1),
    )
    repository.add_job(
        complete_job(checkpointed, lease_token=lease, finished_at=NOW + timedelta(seconds=2))
    )

    class Overrides:
        def snapshot(self, *, game_id: UUID) -> dict[str, object]:
            return {source_checksum: {"revision": 1}} if geometry_accepted else {}

        def exclusion_snapshot(
            self, *, game_id: UUID, browser_selection_id: UUID
        ) -> dict[str, object]:
            return {}

    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: JobService(repository),
            browser_image_selection_service_dependency=lambda: browser_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            page_geometry_override_service_dependency=lambda: Overrides(),
        )
    )
    with client:
        response = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
            f"/geometry-preflights/{job.id}/source-replacement",
            content=new_content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Game-Id": str(game_id),
                "X-Source-Checksum-Sha256": source_checksum,
                "X-Source-Relative-Path": "cut/seq_1-9.jpg",
                "X-Geometry-Manifest-Checksum-Sha256": checksum,
            },
        )
    assert response.status_code == (409 if geometry_accepted else 200), response.text
    if geometry_accepted:
        assert response.json()["code"] == "IMAGE_REPLACEMENT_NOT_ALLOWED"
    else:
        assert response.json()["uploadId"] != str(upload.upload_id)
        replacement_id = response.json()["uploadId"]
        with client:
            pending_replay = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
                f"/geometry-preflights/{job.id}/source-replacement",
                content=new_content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Game-Id": str(game_id),
                    "X-Source-Checksum-Sha256": source_checksum,
                    "X-Source-Relative-Path": "cut/seq_1-9.jpg",
                    "X-Geometry-Manifest-Checksum-Sha256": checksum,
                },
            )
        assert pending_replay.status_code == 200, pending_replay.text
        assert pending_replay.json()["uploadId"] == replacement_id
        with client:
            abandoned = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
                f"/replacement-revisions/{replacement_id}/discard",
                json={"gameId": str(game_id)},
            )
        assert abandoned.status_code == 204, abandoned.text
        with client:
            replay = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
                f"/geometry-preflights/{job.id}/source-replacement",
                content=new_content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Game-Id": str(game_id),
                    "X-Source-Checksum-Sha256": source_checksum,
                    "X-Source-Relative-Path": "cut/seq_1-9.jpg",
                    "X-Geometry-Manifest-Checksum-Sha256": checksum,
                },
            )
        assert replay.status_code == 200, replay.text
        assert replay.json()["uploadId"] == replacement_id
        with client:
            confirmed = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
                f"/replacement-revisions/{replacement_id}/confirm",
                json={
                    "gameId": str(game_id),
                    "sourceChecksumSha256": source_checksum,
                    "sourceRelativePath": "cut/seq_1-9.jpg",
                    "replacementChecksumSha256": hashlib.sha256(new_content).hexdigest(),
                },
            )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["uploadId"] == replacement_id
        with client:
            stale = client.post(
                f"/api/v1/admin/image-imports/browser-selections/{upload.upload_id}"
                f"/geometry-preflights/{job.id}/source-replacement",
                content=new_content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Game-Id": str(game_id),
                    "X-Source-Checksum-Sha256": source_checksum,
                    "X-Source-Relative-Path": "cut/seq_1-9.jpg",
                    "X-Geometry-Manifest-Checksum-Sha256": checksum,
                },
            )
        assert stale.status_code == 409
        assert stale.json()["code"] == "IMAGE_BROWSER_SELECTION_SUPERSEDED"


def test_finalized_browser_staging_persists_ready_and_in_use_lifecycle(
    tmp_path: Path,
) -> None:
    class RetentionSpy:
        def __init__(self) -> None:
            self.ready: dict[str, object] | None = None
            self.in_use: dict[str, object] | None = None

        def record_ready(self, **values: object) -> None:
            self.ready = values

        def record_in_use(self, **values: object) -> None:
            self.in_use = values

        def record_ingested(self, _handoff: object) -> None:
            raise AssertionError("ingestion belongs to the worker")

        def discard_unused(self, *, upload_id: UUID) -> None:
            raise AssertionError(f"unexpected discard of {upload_id}")

    retention = RetentionSpy()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
        retention=retention,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (20, 30, 40)).save(stream, "JPEG")
    content = stream.getvalue()
    game_id = uuid4()
    upload = service.begin(
        display_name="1-9",
        expected_file_count=1,
        expected_total_bytes=len(content),
        game_id=game_id,
    )
    service.upload_file(
        upload.upload_id,
        0,
        relative_path="1-9/seq_1-9.jpg",
        content=content,
    )

    service.finalize(upload.upload_id)
    job_id = uuid4()
    service.mark_in_use(upload.upload_id, game_id=game_id, job_id=job_id)

    assert retention.ready is not None
    assert retention.ready["upload_id"] == upload.upload_id
    assert retention.ready["game_id"] == game_id
    assert retention.ready["finalized_at"] == NOW
    assert retention.in_use == {
        "upload_id": upload.upload_id,
        "game_id": game_id,
        "job_id": job_id,
        "used_at": NOW,
    }


def test_cancelled_browser_staging_discards_unused_history_before_files(
    tmp_path: Path,
) -> None:
    class RetentionSpy:
        def __init__(self) -> None:
            self.discarded: UUID | None = None

        def record_ready(self, **_values: object) -> None:
            return None

        def record_in_use(self, **_values: object) -> None:
            return None

        def record_ingested(self, _handoff: object) -> None:
            return None

        def discard_unused(self, *, upload_id: UUID) -> None:
            self.discarded = upload_id

    retention = RetentionSpy()
    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
        retention=retention,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (20, 30, 40)).save(stream, "JPEG")
    content = stream.getvalue()
    upload = service.begin(
        display_name="unused",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )
    service.upload_file(
        upload.upload_id,
        0,
        relative_path="unused/seq_1-9.jpg",
        content=content,
    )
    service.finalize(upload.upload_id)

    service.cancel(upload.upload_id)

    assert retention.discarded == upload.upload_id
    assert not upload.path.exists()


def test_cancelled_browser_staging_restores_files_when_history_is_protected(
    tmp_path: Path,
) -> None:
    class ProtectedRetention:
        def record_ready(self, **_values: object) -> None:
            return None

        def record_in_use(self, **_values: object) -> None:
            return None

        def record_ingested(self, _handoff: object) -> None:
            return None

        def discard_unused(self, *, upload_id: UUID) -> None:
            raise JobConflictError(
                "IMAGE_BROWSER_SELECTION_DELETE_HAS_RESULTS",
                f"protected {upload_id}",
            )

    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
        retention=ProtectedRetention(),
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (20, 30, 40)).save(stream, "JPEG")
    content = stream.getvalue()
    upload = service.begin(
        display_name="protected",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )
    service.upload_file(
        upload.upload_id,
        0,
        relative_path="protected/seq_1-9.jpg",
        content=content,
    )
    service.finalize(upload.upload_id)

    with pytest.raises(JobConflictError) as error:
        service.cancel(upload.upload_id)

    assert error.value.code == "IMAGE_BROWSER_SELECTION_DELETE_HAS_RESULTS"
    assert upload.path.is_dir()
    assert (upload.path / "00000001.jpg").is_file()


def test_browser_upload_header_is_allowed_by_cors(tmp_path: Path) -> None:
    client, _game_id = _client(tmp_path, None)

    with client:
        response = client.options(
            "/api/v1/admin/image-imports/browser-selections/upload/files/0",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": (
                    "content-type,x-admin-intent,x-image-relative-path"
                ),
            },
        )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].casefold()
    assert "x-image-relative-path" in allowed_headers


def test_page_source_replacement_headers_are_allowed_by_cors(tmp_path: Path) -> None:
    client, _game_id = _client(tmp_path, None)

    with client:
        response = client.options(
            "/api/v1/admin/image-imports/browser-selections/upload/"
            "geometry-preflights/preflight/source-replacement",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "content-type,x-admin-intent,x-admin-confirmation,x-admin-target,"
                    "x-game-id,x-source-checksum-sha256,x-source-relative-path,"
                    "x-geometry-manifest-checksum-sha256"
                ),
            },
        )

    assert response.status_code == 200, response.text
    allowed_headers = response.headers["access-control-allow-headers"].casefold()
    for header in (
        "x-game-id",
        "x-source-checksum-sha256",
        "x-source-relative-path",
        "x-geometry-manifest-checksum-sha256",
    ):
        assert header in allowed_headers


def test_photo_selection_staging_is_resumable_after_service_recreation(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    upload_root = tmp_path / "imports"
    first_service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    image_bytes = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_bytes, "JPEG")
    content = image_bytes.getvalue()
    upload = first_service.begin(
        display_name="Duzy folder",
        expected_file_count=2,
        expected_total_bytes=len(content) * 2,
        purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        game_id=game_id,
    )
    first_service.upload_file(
        upload.upload_id,
        0,
        relative_path="Duzy folder/photo-1.jpg",
        content=content,
    )

    resumed_service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW + timedelta(minutes=20),
    )
    resumed = resumed_service.get(upload.upload_id)
    duplicate_retry = resumed_service.upload_file(
        upload.upload_id,
        0,
        relative_path="Duzy folder/photo-1.jpg",
        content=content,
    )

    assert resumed.uploaded_indexes == {0}
    assert resumed.uploaded_bytes == len(content)
    assert duplicate_retry.uploaded_indexes == {0}


def test_photo_selection_staging_uses_a_compact_append_only_journal(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    upload_root = tmp_path / "imports"
    service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    image_bytes = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_bytes, "JPEG")
    content = image_bytes.getvalue()
    upload = service.begin(
        display_name="Duzy folder",
        expected_file_count=3,
        expected_total_bytes=len(content) * 3,
        purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        game_id=game_id,
    )
    upload_path = upload_root / "browser-selections" / str(upload.upload_id)
    state_path = upload_path / image_imports_module.UPLOAD_STATE_FILE_NAME
    initial_state_bytes = state_path.read_bytes()

    for index in range(3):
        service.upload_file(
            upload.upload_id,
            index,
            relative_path=f"Duzy folder/photo-{index + 1}.jpg",
            content=content,
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    journal_lines = (
        (upload_path / image_imports_module.UPLOAD_JOURNAL_FILE_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    )
    resumed = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW + timedelta(minutes=1),
    ).get(upload.upload_id)

    assert state["schemaVersion"] == 2
    assert "files" not in state
    assert state_path.read_bytes() == initial_state_bytes
    assert len(journal_lines) == 3
    assert resumed.uploaded_indexes == {0, 1, 2}
    assert resumed.uploaded_bytes == len(content) * 3


def test_legacy_browser_upload_state_is_migrated_without_losing_progress(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    upload_root = tmp_path / "imports"
    service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    image_bytes = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_bytes, "JPEG")
    content = image_bytes.getvalue()
    upload = service.begin(
        display_name="Legacy upload",
        expected_file_count=2,
        expected_total_bytes=len(content) * 2,
        purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        game_id=game_id,
    )
    uploaded = service.upload_file(
        upload.upload_id,
        0,
        relative_path="Legacy upload/photo-1.jpg",
        content=content,
    )
    value = uploaded.uploaded_files[0]
    upload_path = upload_root / "browser-selections" / str(upload.upload_id)
    state_path = upload_path / image_imports_module.UPLOAD_STATE_FILE_NAME
    journal_path = upload_path / image_imports_module.UPLOAD_JOURNAL_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "uploadId": str(upload.upload_id),
                "displayName": upload.display_name,
                "purpose": upload.purpose.value,
                "gameId": str(game_id),
                "expectedFileCount": upload.expected_file_count,
                "expectedTotalBytes": upload.expected_total_bytes,
                "createdAt": upload.created_at.isoformat(),
                "files": [
                    {
                        "fileIndex": value.file_index,
                        "relativePath": value.relative_path,
                        "storedFileName": value.stored_file_name,
                        "sizeBytes": value.size_bytes,
                        "checksumSha256": value.checksum_sha256,
                    }
                ],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    journal_path.unlink()

    resumed = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW + timedelta(minutes=1),
    ).get(upload.upload_id)
    migrated_state = json.loads(state_path.read_text(encoding="utf-8"))

    assert resumed.uploaded_indexes == {0}
    assert resumed.uploaded_bytes == len(content)
    assert migrated_state["schemaVersion"] == 2
    assert "files" not in migrated_state
    assert len(journal_path.read_text(encoding="utf-8").splitlines()) == 1


def test_file_upload_response_does_not_repeat_the_resume_index_inventory(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (50, 60, 70)).save(stream, "JPEG")
    content = stream.getvalue()
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: JobService(MemoryJobRepository(game_id)),
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "Zdjecia do selekcji",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(content),
                "purpose": "photo_selection",
                "gameId": str(game_id),
            },
        )
        uploaded = client.put(
            f"/api/v1/admin/image-imports/browser-selections/{created.json()['uploadId']}/files/0",
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "Zdjecia do selekcji/photo.jpg",
            },
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["uploadedFileCount"] == 1
    assert uploaded.json()["uploadedBytes"] == len(content)
    assert "uploadedFileIndexes" not in uploaded.json()


def test_finalized_photo_selection_can_be_reapproved_after_service_recreation(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    upload_root = tmp_path / "imports"
    first_selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    first_service = BrowserImageSelectionService(
        first_selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    image_bytes = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_bytes, "JPEG")
    content = image_bytes.getvalue()
    upload = first_service.begin(
        display_name="Duzy folder",
        expected_file_count=1,
        expected_total_bytes=len(content),
        purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        game_id=game_id,
    )
    first_service.upload_file(
        upload.upload_id,
        0,
        relative_path="Duzy folder/photo-1.jpg",
        content=content,
    )
    first_selected = first_service.finalize(upload.upload_id)

    resumed_selection_service = ImageFolderSelectionService(
        lambda: None,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    resumed_service = BrowserImageSelectionService(
        resumed_selection_service,
        upload_root,
        max_bytes=1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    resumed = resumed_service.get(upload.upload_id)
    repeated_selected = resumed_service.finalize(upload.upload_id)

    assert resumed.uploaded_indexes == {0}
    assert resumed.uploaded_bytes == len(content)
    assert first_selected.selection_id == repeated_selected.selection_id == upload.upload_id
    assert first_selected.input_manifest_sha256 == repeated_selected.input_manifest_sha256


def test_expired_legacy_token_does_not_delete_finalized_browser_staging(
    tmp_path: Path,
) -> None:
    current = NOW
    selection_service = ImageFolderSelectionService(
        lambda: None,
        clock=lambda: current,
    )
    upload_root = tmp_path / "imports"
    service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024 * 1024,
        clock=lambda: current,
    )
    image_bytes = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(image_bytes, "JPEG")
    content = image_bytes.getvalue()
    first = service.begin(
        display_name="Pierwszy staging",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )
    service.upload_file(
        first.upload_id,
        0,
        relative_path="Pierwszy staging/seq_1-9.jpg",
        content=content,
    )
    service.finalize(first.upload_id)
    first_path = first.path

    current = NOW + timedelta(minutes=20)
    second = service.begin(
        display_name="Drugi staging",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )

    assert second.path.is_dir()
    assert first_path.is_dir()
    assert (
        service.get_ready(first.upload_id).manifest.files[0].relative_path.endswith("seq_1-9.jpg")
    )


def test_photo_selection_staging_enforces_separate_file_and_byte_limits(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024,
        photo_selection_max_bytes=2048,
        clock=lambda: NOW,
    )

    accepted = service.begin(
        display_name="Maximum supported folder",
        expected_file_count=100_000,
        expected_total_bytes=1024,
        purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        game_id=game_id,
    )

    with pytest.raises(JobError) as too_many_files:
        service.begin(
            display_name="Too many",
            expected_file_count=100_001,
            expected_total_bytes=1024,
            purpose=ImageSelectionPurpose.PHOTO_SELECTION,
            game_id=game_id,
        )
    with pytest.raises(JobError) as too_many_bytes:
        service.begin(
            display_name="Too large",
            expected_file_count=1,
            expected_total_bytes=2049,
            purpose=ImageSelectionPurpose.PHOTO_SELECTION,
            game_id=game_id,
        )

    assert accepted.expected_file_count == 100_000
    assert too_many_files.value.code == "IMAGE_BROWSER_SELECTION_COUNT_INVALID"
    assert too_many_bytes.value.code == "IMAGE_BROWSER_SELECTION_SIZE_INVALID"
    assert too_many_bytes.value.details == {
        "declaredBytes": 2049,
        "maximumBytes": 2048,
        "purpose": "photo_selection",
    }


def test_semi_automatic_staging_skips_managed_artifact_capacity_estimate(
    tmp_path: Path,
) -> None:
    capacity_guard = RejectingImageWriteCapacityGuard()
    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        tmp_path / "imports",
        max_bytes=2048,
        photo_selection_max_bytes=2048,
        clock=lambda: NOW,
        capacity_guard=capacity_guard,
    )

    upload = service.begin(
        display_name="Semi-automatic source",
        expected_file_count=1,
        expected_total_bytes=1024,
        purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
    )

    assert upload.path.is_dir()
    assert capacity_guard.calls == []


@pytest.mark.parametrize(
    ("purpose", "game_id"),
    [
        (ImageSelectionPurpose.LAYOUT_IMPORT, None),
        (ImageSelectionPurpose.PHOTO_SELECTION, uuid4()),
    ],
)
def test_managed_artifact_capacity_estimate_still_protects_managed_workflows(
    tmp_path: Path,
    purpose: ImageSelectionPurpose,
    game_id: UUID | None,
) -> None:
    capacity_guard = RejectingImageWriteCapacityGuard()
    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        tmp_path / "imports",
        max_bytes=2048,
        photo_selection_max_bytes=2048,
        clock=lambda: NOW,
        capacity_guard=capacity_guard,
    )

    with pytest.raises(JobConflictError) as raised:
        service.begin(
            display_name="Managed workflow source",
            expected_file_count=1,
            expected_total_bytes=1024,
            purpose=purpose,
            game_id=game_id,
        )

    assert raised.value.code == "STORAGE_CAPACITY_INSUFFICIENT"
    assert capacity_guard.calls == [1024]


def test_semi_automatic_staging_keeps_physical_free_space_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None, clock=lambda: NOW),
        tmp_path / "imports",
        max_bytes=2048,
        photo_selection_max_bytes=2048,
        clock=lambda: NOW,
        capacity_guard=RejectingImageWriteCapacityGuard(),
    )
    monkeypatch.setattr(
        image_imports_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            free=image_imports_module.MIN_FREE_SPACE_RESERVE_BYTES,
        ),
    )

    with pytest.raises(JobError) as raised:
        service.begin(
            display_name="Semi-automatic source",
            expected_file_count=1,
            expected_total_bytes=1,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        )

    assert raised.value.code == "IMAGE_BROWSER_SELECTION_DISK_SPACE_INSUFFICIENT"
    assert not any((tmp_path / "imports" / "browser-selections").iterdir())


def test_photo_selection_token_cannot_create_layout_import_and_can_create_run(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    job_service = JobService(MemoryJobRepository(game_id))
    run_service = ImageSelectionService(MemoryImageSelectionRepository(game_id))
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (50, 60, 70)).save(stream, "JPEG")
    content = stream.getvalue()
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {
                    "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                    "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
                }
            ),
            job_service_dependency=lambda: job_service,
            image_selection_service_dependency=lambda: run_service,
            image_folder_selection_service_dependency=lambda: selection_service,
            browser_image_selection_service_dependency=lambda: browser_service,
        )
    )

    with client:
        created = client.post(
            "/api/v1/admin/image-imports/browser-selections",
            json={
                "displayName": "Zdjecia do selekcji",
                "expectedFileCount": 1,
                "expectedTotalBytes": len(content),
                "purpose": "photo_selection",
                "gameId": str(game_id),
            },
        )
        upload_id = created.json()["uploadId"]
        uploaded = client.put(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/0",
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-Relative-Path": "Zdjecia do selekcji/photo.jpg",
            },
        )
        restored = client.get(f"/api/v1/admin/image-imports/browser-selections/{upload_id}")
        finalized = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize"
        )
        selection_token = finalized.json()["selectionToken"]
        run = client.post(
            "/api/v1/admin/image-selections",
            json={
                "gameId": str(game_id),
                "selectionToken": selection_token,
                "contractVersion": 1,
                "firstSequenceNumber": 1,
            },
        )

    assert created.status_code == 201
    assert uploaded.status_code == 200
    assert restored.status_code == 200
    assert restored.json()["uploadedFileIndexes"] == [0]
    assert finalized.status_code == 200
    assert finalized.json()["purpose"] == "photo_selection"
    assert finalized.json()["path"] is None
    assert len(finalized.json()["inputManifestSha256"]) == 64
    assert run.status_code == 200
    assert run.json()["created"] is True
    assert run.json()["run"]["job"]["jobType"] == "image_selection"
    assert run.json()["run"]["sourceSelectionId"] == upload_id
