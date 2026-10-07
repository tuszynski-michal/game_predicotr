"""Optional technical picker keeps normal shared token issuance and native default."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.controlled_folder_picker import WindowsFolderPicker
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from PIL import Image


@pytest.mark.parametrize("injected", [False, True])
def test_source_picker_issues_authentic_shared_token_without_consuming_v7_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injected: bool
) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    Image.new("RGB", (8, 8), "white").save(source / "one.jpg")
    native: list[bool] = []
    custom: list[bool] = []

    def choose_native(self: WindowsFolderPicker) -> Path:
        native.append(True)
        return source

    def choose_fixture() -> Path:
        custom.append(True)
        return source

    def reject_gate(*args: object, **kwargs: object) -> None:
        raise AssertionError("Shared token issuance must not read the V7-only gate.")

    monkeypatch.setattr(WindowsFolderPicker, "choose", choose_native)
    monkeypatch.setattr(
        SqlAlchemySemiAutomaticSelectionRepository, "get_v7_pilot_gate", reject_gate
    )
    settings = ApiSettings(
        host="127.0.0.1",
        port=8020,
        admin_origin="http://127.0.0.1:3020",
        artifact_root=tmp_path / "artifacts",
        import_root=tmp_path / "imports",
        v7_label_geometry_runtime_root=tmp_path / "runtime",
        v7_label_geometry_read_only=True,
        semi_automatic_image_selection_enabled=True,
    )
    app = create_app(
        settings,
        local_source_picker=choose_fixture if injected else None,
        job_service_dependency=lambda: object(),
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/admin/semi-automatic-image-selections/source-folder")
    assert response.status_code == 200
    assert response.json()["selectionToken"]
    assert custom == ([True] if injected else [])
    assert native == ([] if injected else [True])
    assert not (tmp_path / "runtime").exists()
