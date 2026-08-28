import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_storage import (
    DIAGNOSTIC_ERROR_LIMIT,
    ImageArtifactStore,
    ImageDiagnosticFailure,
    ImageDiagnosticSnapshot,
    ImageStorageService,
)
from game_predictor_api.application.storage_gc import StorageGcPreview, StorageGcRun
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.main import create_app

NOW = datetime(2026, 7, 29, 22, 0, tzinfo=UTC)
PIPELINE = "a" * 64
FILE_KEY = "b" * 64


class MemoryDiagnosticRepository:
    def __init__(
        self,
        job_id: UUID,
        *,
        source_relative_path: str = "batch/page-001.jpg",
    ) -> None:
        self.job_id = job_id
        self.source_relative_path = source_relative_path
        self.received_limits: list[int] = []
        self.inventory_job: Job | None = None

    def active_storage_inventory_job(self) -> Job | None:
        return self.inventory_job

    def add_job(self, job: Job) -> Job:
        self.inventory_job = job
        return job

    def diagnostic_snapshot(
        self,
        job_id: UUID,
        *,
        error_limit: int,
    ) -> ImageDiagnosticSnapshot:
        assert job_id == self.job_id
        self.received_limits.append(error_limit)
        failure = ImageDiagnosticFailure(
            file_execution_key=FILE_KEY,
            order_index=0,
            source_relative_path=self.source_relative_path,
            failed_stage="normalization",
            error_code="IMAGE_NORMALIZATION_FAILED",
            error_message="Normalization failed.",
            retry_count=2,
            last_failed_at=NOW,
        )
        failures = () if error_limit < 1 else (failure,)
        return ImageDiagnosticSnapshot(
            job_id=job_id,
            status="waiting_for_review",
            pipeline_fingerprint=PIPELINE,
            source_updated_at=NOW,
            total=4,
            current=3,
            succeeded=1,
            failed=2,
            review=1,
            waiting=1,
            failures=failures,
            error_limit=error_limit,
            truncated=len(failures) < 2,
        )


def _client(
    tmp_path: Path,
    *,
    source_relative_path: str = "batch/page-001.jpg",
) -> tuple[TestClient, UUID, MemoryDiagnosticRepository]:
    job_id = uuid4()
    repository = MemoryDiagnosticRepository(
        job_id,
        source_relative_path=source_relative_path,
    )
    service = ImageStorageService(repository, ImageArtifactStore(tmp_path))
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)})
    client = TestClient(
        create_app(
            settings,
            image_storage_service_dependency=lambda: service,
        )
    )
    return client, job_id, repository


def test_inventory_is_read_only_bounded_to_managed_namespaces(
    tmp_path: Path,
) -> None:
    (tmp_path / "data" / "originals").mkdir(parents=True)
    original = tmp_path / "data" / "originals" / "source.jpg"
    original.write_bytes(b"source")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    client, _job_id, _repository = _client(tmp_path)

    with client:
        response = client.get("/api/v1/admin/image-storage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rootName"] == "data"
    assert payload["automaticDeletion"] is False
    assert payload["totalFileCount"] == 1
    assert payload["totalSizeBytes"] == len(b"source")
    assert [item["name"] for item in payload["namespaces"]] == [
        "staging",
        "originals",
        "working",
        "crops",
        "training",
        "models",
        "exports",
    ]
    originals = payload["namespaces"][1]
    models = payload["namespaces"][5]
    assert originals["retentionPolicy"] == "preserve"
    assert originals["protected"] is True
    assert models["protected"] is True
    assert outside.read_bytes() == b"outside"


def test_inventory_refresh_returns_one_idempotent_durable_job(tmp_path: Path) -> None:
    client, _job_id, repository = _client(tmp_path)

    with client:
        first = client.post("/api/v1/admin/image-storage/inventory-refresh")
        second = client.post("/api/v1/admin/image-storage/inventory-refresh")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["jobType"] == JobType.STORAGE_INVENTORY.value
    assert repository.inventory_job is not None


def test_diagnostic_export_is_immutable_idempotent_and_downloadable(
    tmp_path: Path,
) -> None:
    client, job_id, repository = _client(tmp_path)

    with client:
        first = client.post(f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports")
        second = client.post(f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports")
        listed = client.get(f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports")
        checksum = first.json()["export"]["checksumSha256"]
        downloaded = client.get(
            f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports/{checksum}/download"
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["export"] == second.json()["export"]
    assert listed.status_code == 200
    assert listed.json() == [first.json()["export"]]
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/octet-stream"
    manifest = json.loads(downloaded.content)
    assert manifest["schemaVersion"] == "image-job-diagnostics-v1"
    assert manifest["aggregates"] == {
        "current": 3,
        "failed": 2,
        "review": 1,
        "succeeded": 1,
        "total": 4,
        "waiting": 1,
    }
    assert manifest["exportedErrorCount"] == 1
    assert manifest["truncated"] is True
    assert manifest["errors"][0]["sourceRelativePath"] == "batch/page-001.jpg"
    assert str(tmp_path) not in downloaded.text
    assert repository.received_limits[:2] == [
        DIAGNOSTIC_ERROR_LIMIT,
        DIAGNOSTIC_ERROR_LIMIT,
    ]


def test_diagnostic_export_rejects_unsafe_paths_and_checksum_drift(
    tmp_path: Path,
) -> None:
    unsafe_client, unsafe_job_id, _repository = _client(
        tmp_path / "unsafe",
        source_relative_path="../secret.jpg",
    )
    with unsafe_client:
        unsafe = unsafe_client.post(f"/api/v1/admin/image-jobs/{unsafe_job_id}/diagnostic-exports")
    assert unsafe.status_code == 409
    assert unsafe.json()["code"] == "IMAGE_STORAGE_PATH_UNSAFE"

    client, job_id, _repository = _client(tmp_path / "corrupt")
    with client:
        created = client.post(f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports")
        export = created.json()["export"]
        path = tmp_path / "corrupt" / Path(*export["relativePath"].split("/"))
        path.write_bytes(b"corrupt")
        downloaded = client.get(
            f"/api/v1/admin/image-jobs/{job_id}/diagnostic-exports/"
            f"{export['checksumSha256']}/download"
        )
    assert downloaded.status_code == 409
    assert downloaded.json()["code"] == "IMAGE_DIAGNOSTIC_EXPORT_CHECKSUM_MISMATCH"


def test_inventory_never_follows_a_symbolic_link(tmp_path: Path) -> None:
    originals = tmp_path / "data" / "originals"
    originals.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.jpg").write_bytes(b"secret")
    link = originals / "external"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this Windows environment.")
    client, _job_id, _repository = _client(tmp_path)

    with client:
        response = client.get("/api/v1/admin/image-storage")

    assert response.status_code == 200
    originals_inventory = response.json()["namespaces"][0]
    assert originals_inventory["fileCount"] == 0
    assert originals_inventory["ignoredSymlinkCount"] == 1

    exports_link = tmp_path / "data" / "exports"
    exports_link.symlink_to(outside, target_is_directory=True)
    with client:
        export_response = client.post(f"/api/v1/admin/image-jobs/{_job_id}/diagnostic-exports")
    assert export_response.status_code == 409
    assert export_response.json()["code"] == "IMAGE_STORAGE_PATH_UNSAFE"
    assert sorted(item.name for item in outside.iterdir()) == ["secret.jpg"]


def test_gc_preview_start_and_status_contract_requires_confirmation(tmp_path: Path) -> None:
    preview_id = uuid4()
    job_id = uuid4()
    preview = StorageGcPreview(
        id=preview_id,
        status="previewed",
        mode="manual",
        policy_version="storage-retention-v1",
        retention_hours=24,
        manifest_relative_path=f"data/exports/storage-gc/{preview_id}/manifest.json",
        manifest_checksum_sha256="c" * 64,
        preview_token="d" * 64,
        candidate_count=2,
        candidate_bytes=2048,
        protected_count=1,
        protected_bytes=1024,
        predicted_free_bytes=4096,
        category_counts={"normalization_working_bitmap": {"count": 2, "bytes": 2048}},
        protection_reason_counts={"active_job_dependency": {"count": 1, "bytes": 1024}},
        created_at=NOW,
    )
    run = StorageGcRun(
        id=preview_id,
        job_id=job_id,
        status="created",
        mode="manual",
        candidate_count=2,
        candidate_bytes=2048,
        protected_count=1,
        protected_bytes=1024,
        deleted_count=0,
        deleted_bytes=0,
        conflict_count=0,
        failed_count=0,
        checkpoint_index=0,
        error_code=None,
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
        started_at=None,
        finished_at=None,
    )

    class GcStub:
        def preview(self):  # type: ignore[no-untyped-def]
            return preview

        def start(self, **values):  # type: ignore[no-untyped-def]
            assert values["confirmed"] is True
            assert values["preview_id"] == preview_id
            return run

        def get_run(self, run_id):  # type: ignore[no-untyped-def]
            assert run_id == preview_id
            return run

    job = uuid4()
    repository = MemoryDiagnosticRepository(job)
    service = ImageStorageService(
        repository,
        ImageArtifactStore(tmp_path),
        GcStub(),  # type: ignore[arg-type]
    )
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)})
    client = TestClient(create_app(settings, image_storage_service_dependency=lambda: service))

    with client:
        created_preview = client.post("/api/v1/admin/image-storage/gc-previews")
        started = client.post(
            "/api/v1/admin/image-storage/gc-runs",
            json={
                "previewId": str(preview_id),
                "manifestChecksumSha256": "c" * 64,
                "previewToken": "d" * 64,
                "confirmed": True,
            },
        )
        status_response = client.get(f"/api/v1/admin/image-storage/gc-runs/{preview_id}")

    assert created_preview.status_code == 201
    assert created_preview.json()["candidateBytes"] == 2048
    assert started.status_code == 201
    assert started.json()["jobId"] == str(job_id)
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "created"
