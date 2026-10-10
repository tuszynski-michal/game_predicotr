from contextlib import nullcontext
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageFolderSelectionService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.browser_staging_retention_repository import (
    SqlAlchemyBrowserStagingRetentionRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRouter,
    GameStorageRoutingError,
)
from PIL import Image


def _browser_service_dependency(service: BrowserImageSelectionService):
    return lambda: service


def test_deleted_game_staging_does_not_hide_ready_folders_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deleted_game, active_game = uuid4(), uuid4()
    session = Mock()
    session.get.return_value = SimpleNamespace(game_id=active_game, board_import_status="ready")
    retention = SqlAlchemyBrowserStagingRetentionRepository(lambda: nullcontext(session))

    def bind(_router, _session, game_id, *, intent):
        if game_id == deleted_game:
            raise GameStorageRoutingError(
                "GAME_NOT_FOUND", "Game does not exist.", details={"gameId": str(game_id)}
            )
        assert game_id == active_game

    monkeypatch.setattr(GameStorageRouter, "bind", bind)
    now = datetime(2026, 10, 6, tzinfo=UTC)
    selection = ImageFolderSelectionService(lambda: None, clock=lambda: now)
    service = BrowserImageSelectionService(
        selection, tmp_path, max_bytes=1024 * 1024, clock=lambda: now
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (20, 30, 40)).save(stream, "JPEG")
    content = stream.getvalue()
    uploads = []
    for game_id in (deleted_game, active_game):
        upload = service.begin(
            display_name="cut",
            game_id=game_id,
            expected_file_count=1,
            expected_total_bytes=len(content),
        )
        service.upload_file(upload.upload_id, 0, relative_path="cut/seq_1-9.jpg", content=content)
        service.finalize(upload.upload_id)
        uploads.append(upload)

    for _restart in range(2):
        restarted = BrowserImageSelectionService(
            ImageFolderSelectionService(lambda: None, clock=lambda: now),
            tmp_path,
            max_bytes=1024 * 1024,
            clock=lambda: now,
            retention=retention,
        )
        app = create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            browser_image_selection_service_dependency=_browser_service_dependency(restarted),
        )
        response = TestClient(app).get("/api/v1/admin/image-imports/browser-selections")
        assert response.status_code == 200
        items = {item["uploadId"]: item for item in response.json()}
        assert items[str(uploads[0].upload_id)]["boardImportStatus"] is None
        assert items[str(uploads[0].upload_id)]["gameId"] == str(deleted_game)
        assert items[str(uploads[1].upload_id)]["boardImportStatus"] == "ready"
        for upload in uploads:
            assert (upload.path / "_upload_state.json").is_file()
            assert len(restarted.get_ready(upload.upload_id).manifest.files) == 1


@pytest.mark.parametrize("code", ["GAME_STORAGE_LOCATION_MISSING", "GAME_STORAGE_LOCATION_INVALID"])
def test_other_storage_routing_errors_remain_failures(monkeypatch: pytest.MonkeyPatch, code: str):
    error = GameStorageRoutingError(code, "Unavailable storage.", details={})
    monkeypatch.setattr(GameStorageRouter, "bind", Mock(side_effect=error))
    session = Mock()
    retention = SqlAlchemyBrowserStagingRetentionRepository(lambda: nullcontext(session))
    with pytest.raises(GameStorageRoutingError) as raised:
        retention.board_import_status(upload_id=uuid4(), game_id=uuid4())
    assert raised.value is error
    session.get.assert_not_called()


def test_unexpected_storage_error_is_not_treated_as_deleted_game(monkeypatch: pytest.MonkeyPatch):
    error = RuntimeError("database unavailable")
    monkeypatch.setattr(GameStorageRouter, "bind", Mock(side_effect=error))
    retention = SqlAlchemyBrowserStagingRetentionRepository(lambda: nullcontext(Mock()))
    with pytest.raises(RuntimeError) as raised:
        retention.board_import_status(upload_id=uuid4(), game_id=uuid4())
    assert raised.value is error
