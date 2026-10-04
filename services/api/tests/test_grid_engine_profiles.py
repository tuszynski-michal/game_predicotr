"""TASK-0830: grid engine profile registry, managed model store, install script, endpoint."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_engine_profiles import GridEngineProfileService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    GRID_ENGINE_MANIFEST_FILE_NAME,
    GRID_ENGINE_PROFILES,
    GridEngineModelError,
    GridEngineModelFile,
    GridEngineModelStatus,
    GridEngineModelVersion,
    grid_engine_manifest,
    grid_engine_profile_for,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore

ROOT = Path(__file__).resolve().parents[3]
_SHA = "0123456789abcdef" * 4


def _install_module() -> ModuleType:
    name = "install_grid_engine_models_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = spec_from_file_location(name, ROOT / "scripts" / "install_grid_engine_models.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bundle(version: GridEngineModelVersion, files: dict[str, bytes]) -> dict[str, Any]:
    return {
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "format": "neural-grid-bundle-v1",
        "preset": {"name": version.preset_name, "seed": 1, "version": "neural-grid-preset-v1"},
        "preset_fingerprint": version.preset_fingerprint,
        "provenance": {
            "checkpoint_sha256": version.checkpoint_sha256,
            "run_id": version.run_id,
        },
        "weights_sha256": version.weights_sha256,
    }


def _fake_export(tmp_path: Path) -> tuple[GridEngineModelVersion, Path]:
    """A registry entry of the real Mumie profile shape, but for small synthetic files."""

    install = _install_module()
    base = GRID_ENGINE_PROFILES[1].current
    onnx = {"screen.onnx": b"screen-model", "board.onnx": b"board-model"}
    source = tmp_path / "export"
    source.mkdir()
    for name, data in onnx.items():
        (source / name).write_bytes(data)
    bundle = _bundle(base, onnx)
    bundle_bytes = json.dumps(bundle).encode("utf-8")
    (source / "bundle.json").write_bytes(bundle_bytes)
    (source / "weights.pt").write_bytes(b"not copied")
    preset = install.preset_bytes(bundle)
    contents = {**onnx, "bundle.json": bundle_bytes, "preset.json": preset}
    version = replace(
        base,
        files=tuple(
            GridEngineModelFile(name, hashlib.sha256(data).hexdigest(), len(data))
            for name, data in contents.items()
        ),
    )
    return version, source


def test_registry_maps_both_profiles_to_one_current_version_with_four_pinned_files() -> None:
    assert [profile.configuration for profile in GRID_ENGINE_PROFILES] == [
        GameShapeGeometryConfiguration.GRID_PROFILE_777_V2,
        GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1,
    ]
    assert [profile.label for profile in GRID_ENGINE_PROFILES] == ["777 v2", "Mumie"]
    for profile in GRID_ENGINE_PROFILES:
        current = profile.current
        assert current.profile is profile.configuration
        assert current.model_kind == "neural_grid"
        assert [file.name for file in current.files] == [
            "screen.onnx",
            "board.onnx",
            "bundle.json",
            "preset.json",
        ]
        for value in (
            *(file.sha256 for file in current.files),
            current.preset_fingerprint,
            current.weights_sha256,
            current.checkpoint_sha256,
        ):
            assert len(value) == 64 and int(value, 16) >= 0
        assert current.relative_directory.as_posix() == (
            f"models/grid-engine/{profile.configuration.value}/{current.version}"
        )
    assert grid_engine_profile_for(GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2) is None
    assert grid_engine_profile_for(None) is None
    assert "777" in GRID_ENGINE_PROFILES[0].description
    assert "777 v3" in GRID_ENGINE_PROFILES[0].description


def test_registry_pins_the_v3c_report_models() -> None:
    profile_777 = GRID_ENGINE_PROFILES[0].current
    profile_mumie = GRID_ENGINE_PROFILES[1].current
    assert (profile_777.run_id, profile_777.export_id, profile_777.preset_name) == (
        "43933ac8d7d443c8b9079630a83de2e6",
        "2cd19738367121e6-round3",
        "A",
    )
    assert (profile_mumie.run_id, profile_mumie.export_id) == (
        "5bc981568c3f42bd96f6f9238e57aedc",
        "iteration03-f896da7196431be2",
    )
    manifest = grid_engine_manifest(profile_mumie)
    assert manifest["profile"] == "grid_profile_mumie_v1"
    assert manifest["report"] == "ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md"
    assert manifest["files"] == [
        {"name": file.name, "sha256": file.sha256, "sizeBytes": file.size_bytes}
        for file in profile_mumie.files
    ]


def test_install_copies_verifies_and_writes_the_manifest_then_is_idempotent(
    tmp_path: Path,
) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    artifact_root = tmp_path / "artifacts"

    result = install.install_version(version, source, artifact_root)

    target = artifact_root / "models" / "grid-engine" / "grid_profile_mumie_v1" / "v1"
    assert result.outcome == "installed"
    assert result.directory == target
    assert sorted(path.name for path in target.iterdir()) == [
        "board.onnx",
        "bundle.json",
        "manifest.json",
        "preset.json",
        "screen.onnx",
    ]
    assert json.loads((target / GRID_ENGINE_MANIFEST_FILE_NAME).read_text("utf-8")) == (
        grid_engine_manifest(version)
    )
    store = ManagedGridEngineModelStore(artifact_root)
    assert store.inspect(version).status is GridEngineModelStatus.AVAILABLE
    assert store.require(version) == target
    assert [path.name for path in target.parent.iterdir()] == ["v1"]

    again = install.install_version(version, source, artifact_root)
    assert again.outcome == "already_installed"


def test_install_refuses_a_source_that_differs_from_the_registry(tmp_path: Path) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    (source / "board.onnx").write_bytes(b"board-model-retrained")
    artifact_root = tmp_path / "artifacts"

    with pytest.raises(GridEngineModelError) as error:
        install.install_version(version, source, artifact_root)

    assert error.value.code == "GRID_ENGINE_SOURCE_CHECKSUM_MISMATCH"
    assert not (artifact_root / "models").exists()


def test_install_refuses_a_bundle_of_another_model(tmp_path: Path) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    version = replace(version, run_id="ff03b1d7c489448483f23e73dd03f31d")

    with pytest.raises(GridEngineModelError) as error:
        install.install_version(version, source, tmp_path / "artifacts")

    assert error.value.code == "GRID_ENGINE_SOURCE_IDENTITY_MISMATCH"
    assert error.value.details["field"] == "run_id"


def test_store_detects_a_missing_file_and_a_changed_file_without_fallback(
    tmp_path: Path,
) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    artifact_root = tmp_path / "artifacts"
    store = ManagedGridEngineModelStore(artifact_root)

    nothing = store.inspect(version)
    assert nothing.status is GridEngineModelStatus.MISSING
    assert nothing.reason_code == "GRID_ENGINE_MODEL_MISSING"
    with pytest.raises(GridEngineModelError) as missing_error:
        store.require(version)
    assert missing_error.value.code == "GRID_ENGINE_MODEL_MISSING"

    install.install_version(version, source, artifact_root)
    target = store.directory(version)

    (target / "board.onnx").unlink()
    removed = store.inspect(version)
    assert removed.status is GridEngineModelStatus.MISSING
    assert {state.file.name: state.status for state in removed.files}["board.onnx"] is (
        GridEngineModelStatus.MISSING
    )

    (target / "board.onnx").write_bytes(b"board-modeL")  # same size, other bytes
    changed = store.inspect(version)
    assert changed.status is GridEngineModelStatus.CHECKSUM_MISMATCH
    assert changed.reason_code == "GRID_ENGINE_MODEL_CHECKSUM_MISMATCH"
    with pytest.raises(GridEngineModelError) as changed_error:
        store.require(version)
    assert changed_error.value.code == "GRID_ENGINE_MODEL_CHECKSUM_MISMATCH"
    assert changed_error.value.details["files"] == {
        "screen.onnx": "available",
        "board.onnx": "checksum_mismatch",
        "bundle.json": "available",
        "preset.json": "available",
    }

    # A tampered target is never overwritten by a second install.
    with pytest.raises(GridEngineModelError) as conflict:
        install.install_version(version, source, artifact_root)
    assert conflict.value.code == "GRID_ENGINE_TARGET_CONFLICT"


def test_store_rejects_a_manifest_that_differs_from_the_registry(tmp_path: Path) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    artifact_root = tmp_path / "artifacts"
    install.install_version(version, source, artifact_root)
    store = ManagedGridEngineModelStore(artifact_root)
    manifest_path = store.directory(version) / GRID_ENGINE_MANIFEST_FILE_NAME
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["version"] = "v2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    state = store.inspect(version)

    assert state.status is GridEngineModelStatus.CHECKSUM_MISMATCH
    assert state.manifest_status is GridEngineModelStatus.CHECKSUM_MISMATCH
    assert all(item.status is GridEngineModelStatus.AVAILABLE for item in state.files)


def test_service_reports_every_profile_with_its_current_model(tmp_path: Path) -> None:
    install = _install_module()
    version, source = _fake_export(tmp_path)
    artifact_root = tmp_path / "artifacts"
    install.install_version(version, source, artifact_root)
    profiles = (
        GRID_ENGINE_PROFILES[0],
        replace(GRID_ENGINE_PROFILES[1], versions=(version,)),
    )

    views = GridEngineProfileService(
        ManagedGridEngineModelStore(artifact_root), profiles
    ).list_profiles()

    assert [(view.profile.label, view.model.status) for view in views] == [
        ("777 v2", GridEngineModelStatus.MISSING),
        ("Mumie", GridEngineModelStatus.AVAILABLE),
    ]


def test_endpoint_lists_profiles_and_model_state_read_only(tmp_path: Path) -> None:
    app = create_app(ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)}))

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/grid-engine-profiles")

    assert response.status_code == 200
    body = response.json()
    assert [item["configuration"] for item in body] == [
        "grid_profile_777_v2",
        "grid_profile_mumie_v1",
    ]
    first = body[0]
    assert first["label"] == "777 v2"
    assert first["modelKind"] == "neural_grid"
    assert first["version"] == "v1"
    assert first["runId"] == "43933ac8d7d443c8b9079630a83de2e6"
    assert first["preset"] == "A"
    assert first["managedPath"] == "models/grid-engine/grid_profile_777_v2/v1"
    assert first["status"] == "missing"
    assert first["reasonCode"] == "GRID_ENGINE_MODEL_MISSING"
    assert first["manifestStatus"] == "missing"
    assert [file["name"] for file in first["files"]] == [
        "screen.onnx",
        "board.onnx",
        "bundle.json",
        "preset.json",
    ]
    assert {file["status"] for file in first["files"]} == {"missing"}
    assert first["reportResults"][0]["dataset"].startswith("development 777")
    assert not (tmp_path / "models").exists()


def test_openapi_exposes_the_read_only_profile_operation() -> None:
    schema = create_app(ApiSettings.from_environment({})).openapi()

    path_item = schema["paths"]["/api/v1/admin/grid-engine-profiles"]
    assert set(path_item) == {"get"}
    assert path_item["get"]["operationId"] == "listGridEngineProfiles"
    assert schema["components"]["schemas"]["GridEngineModelStatus"]["enum"] == [
        "available",
        "missing",
        "checksum_mismatch",
    ]
    assert schema["components"]["schemas"]["GameShapeGeometryConfiguration"]["enum"] == [
        "framed_full_page_v2",
        "requires_clarification",
        "grid_profile_777_v2",
        "grid_profile_mumie_v1",
    ]
