import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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
from game_predictor_api.domain.jobs import JobConflictError
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
    assert job["inputPayload"]["sourceDirectory"] == str(source.resolve())
    assert len(job["inputPayload"]["pipelineFingerprint"]) == 64
    assert replay.status_code == 422
    assert replay.json()["code"] == "IMAGE_FOLDER_SELECTION_INVALID"


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
        clock=lambda: NOW,
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
        restored = client.get(
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}"
        )
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
