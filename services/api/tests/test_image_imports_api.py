from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_imports import ImageFolderSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from PIL import Image
from test_jobs_domain import MemoryJobRepository

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


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
    }


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
