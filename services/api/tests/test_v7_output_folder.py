from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.application.image_imports import (
    ImageFolderSelectionService,
    ImageSelectionPurpose,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    _v7_configuration_from_record,
)
from game_predictor_worker.semi_automatic_selection import v7_output_writer
from PIL import Image
from test_v7_selection_delivery_api import delivery_fixture


def test_output_picker_empty_directory_and_cancel(tmp_path, monkeypatch):
    client, _, service, _, _ = delivery_fixture(tmp_path)
    output = tmp_path / "empty-output"
    output.mkdir()
    monkeypatch.setattr(v7_output_writer, "_is_supported_local_ntfs", lambda _: True)
    service._output_picker = lambda: output
    response = client.post("/admin/semi-automatic-image-selections/output-folder")
    assert response.status_code == 200
    assert response.json() == {"status": "selected", "path": str(output)}
    service._output_picker = lambda: None
    assert client.post("/admin/semi-automatic-image-selections/output-folder").json() == {
        "status": "cancelled",
        "path": None,
    }


def test_create_pins_output_and_configuration_survives_deserialization(tmp_path, monkeypatch):
    stream = BytesIO()
    Image.new("RGB", (16, 16)).save(stream, format="JPEG")
    client, repository, service, _, manifest = delivery_fixture(
        tmp_path, source_policy="operator_selected_local_folder", source_content=stream.getvalue()
    )
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(v7_output_writer, "_is_supported_local_ntfs", lambda _: True)
    folders = ImageFolderSelectionService(lambda: manifest.source_root)
    selected = folders.approve(
        manifest.source_root, purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION
    )
    service._folder_selection = folders
    response = client.post(
        "/admin/semi-automatic-image-selections",
        json={
            "mode": "v7_selection",
            "selectionToken": selected.selection_token,
            "firstSequenceNumber": 1,
            "lastSequenceNumber": 18,
            "v7": {"outputBaseDirectory": str(output)},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["run"]
    target = str(output / manifest.source_root.name)
    assert data["outputDirectory"] == data["v7Configuration"]["outputDirectory"] == target
    restored = _v7_configuration_from_record(
        SimpleNamespace(
            v7_configuration=data["v7Configuration"],
            v7_calibration_fingerprint=data["v7Configuration"]["calibrationFingerprint"],
        )
    )
    assert restored.output_directory == target
    assert not (output / manifest.source_root.name).exists()


def test_output_rejects_source_alias_and_unsupported_filesystem(tmp_path, monkeypatch):
    _, _, service, _, _ = delivery_fixture(tmp_path)
    monkeypatch.setattr(v7_output_writer, "_is_supported_local_ntfs", lambda _: False)
    with pytest.raises(Exception, match="NTFS"):
        service._validate_output_base(tmp_path)
    with pytest.raises(Exception, match="absolute"):
        service._validate_output_base(Path("relative"))
