import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application import image_imports as image_imports_module
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageFolderSelectionService,
    ImageSelectionPurpose,
    WindowsFolderPicker,
)
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.config import ApiSettings
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
from game_predictor_api.main import create_app
from PIL import Image
from test_image_selections import MemoryImageSelectionRepository
from test_jobs_domain import MemoryJobRepository

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


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

    monkeypatch.setattr(image_imports_module.subprocess, "run", fake_run)

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


def test_cancelled_picker_does_not_create_selection(tmp_path: Path) -> None:
    client, _game_id = _client(tmp_path, None)

    with client:
        response = client.post("/api/v1/admin/image-imports/folder-selection")

    assert response.status_code == 200
    assert response.json() == {
        "status": "cancelled",
        "selectionToken": None,
        "path": None,
        "supportedFileCount": 0,
        "expiresAt": None,
        "purpose": None,
        "inputManifestSha256": None,
    }


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


def test_approved_folder_token_creates_one_typed_image_job(tmp_path: Path) -> None:
    source = tmp_path / "photos"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "layout.jpg", "JPEG")
    client, game_id = _client(tmp_path, source)

    with client:
        selection = client.post("/api/v1/admin/image-imports/folder-selection")
        token = selection.json()["selectionToken"]
        created = client.post(
            "/api/v1/admin/image-imports",
            json={"gameId": str(game_id), "selectionToken": token},
        )
        replay = client.post(
            "/api/v1/admin/image-imports",
            json={"gameId": str(game_id), "selectionToken": token},
        )

    assert selection.status_code == 200
    assert selection.json()["path"] == str(source.resolve())
    assert selection.json()["supportedFileCount"] == 1
    assert created.status_code == 201
    job = created.json()["job"]
    assert job["jobType"] == "import"
    assert job["inputPayload"]["importKind"] == "image_directory"
    assert job["inputPayload"]["schemaVersion"] == 2
    assert job["inputPayload"]["sourceDirectory"] == str(source.resolve())
    assert len(job["inputPayload"]["pipelineFingerprint"]) == 64
    assert job["inputPayload"]["symbolModel"]["modelVersion"] == ("bootstrap-symbol-cnn-onnx-v1")
    assert replay.status_code == 422
    assert replay.json()["code"] == "IMAGE_FOLDER_SELECTION_INVALID"


def test_terminal_image_import_can_be_reprocessed_from_managed_originals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photos"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "layout.jpg", "JPEG")
    client, game_id = _client(tmp_path, source)

    with client:
        selection = client.post("/api/v1/admin/image-imports/folder-selection")
        created = client.post(
            "/api/v1/admin/image-imports",
            json={
                "gameId": str(game_id),
                "selectionToken": selection.json()["selectionToken"],
            },
        )
        source_job_id = created.json()["job"]["id"]
        cancelled = client.post(f"/api/v1/admin/jobs/{source_job_id}/cancel")
        reprocessed = client.post(f"/api/v1/admin/image-imports/{source_job_id}/reprocess")

    assert cancelled.status_code == 200
    assert reprocessed.status_code == 201
    payload = reprocessed.json()["job"]["inputPayload"]
    assert payload["schemaVersion"] == 4
    assert payload["managedSourceJobId"] == source_job_id
    assert payload["sourceDisplayName"].endswith("(ponowne przetworzenie)")
    assert len(payload["pipelineFingerprint"]) == 64


def test_empty_folder_is_rejected_before_selection_token(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.mkdir()
    client, _game_id = _client(tmp_path, source)

    with client:
        response = client.post("/api/v1/admin/image-imports/folder-selection")

    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_FOLDER_EMPTY"


def test_browser_native_folder_upload_creates_an_import_token(tmp_path: Path) -> None:
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

        imported = client.post(
            "/api/v1/admin/image-imports",
            json={
                "gameId": str(game_id),
                "selectionToken": selection["selectionToken"],
            },
        )
        assert imported.status_code == 201
        payload = imported.json()["job"]["inputPayload"]
        assert payload["sourceDisplayName"] == "Zdjecia gry"
    assert "browser-selections" in payload["sourceDirectory"]


class _BrowserCanonicalRepository:
    def canonical_numbers(self, _game_id: UUID) -> set[int]:
        return set(range(1, 10))

    def canonical_source_checksums(self, _game_id: UUID) -> dict[int, str]:
        return {}


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
    job_service = JobService(repository)
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

        ready = client.get(
            "/api/v1/admin/image-imports/browser-selections?purpose=layout_import"
        )
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

        geometry_checksum = "d" * 64
        geometry_job = create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 2,
                "validation_kind": "page_geometry_preflight",
                "source_selection_id": upload_id,
                "source_directory": str(tmp_path / "imports" / upload_id),
                "source_manifest_sha256": report["manifestChecksumSha256"],
                "page_registration_profile": {
                    "policy": "verified-page-registration-v1",
                    "anchors": [{}],
                },
                "page_geometry_overrides": {},
                "canonical_sequence_numbers": list(range(1, 10)),
            },
            created_at=NOW,
        )
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
            review_count=0,
            updated_at=NOW + timedelta(seconds=1),
        )
        repository.add_job(
            complete_job(
                geometry_job,
                lease_token=lease_token,
                finished_at=NOW + timedelta(seconds=2),
            )
        )

        start_payload = {
            "gameId": str(game_id),
            "manifestChecksumSha256": report["manifestChecksumSha256"],
            "preflightChecksumSha256": report["preflightChecksumSha256"],
            "geometryPreflightJobId": str(geometry_job.id),
            "geometryManifestChecksumSha256": geometry_checksum,
        }
        started = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json=start_payload,
        )
        replay = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            json=start_payload,
        )

    assert started.status_code == 201
    assert started.json()["created"] is True
    assert replay.status_code == 201, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["job"]["id"] == started.json()["job"]["id"]
    assert replay.json()["job"]["inputPayload"]["sourceManifestSha256"] == report[
        "manifestChecksumSha256"
    ]


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
        wrong_purpose = client.post(
            "/api/v1/admin/image-imports",
            json={"gameId": str(game_id), "selectionToken": selection_token},
        )
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
    assert wrong_purpose.status_code == 422
    assert wrong_purpose.json()["code"] == "IMAGE_FOLDER_SELECTION_PURPOSE_INVALID"
    assert run.status_code == 200
    assert run.json()["created"] is True
    assert run.json()["run"]["job"]["jobType"] == "image_selection"
    assert run.json()["run"]["sourceSelectionId"] == upload_id
