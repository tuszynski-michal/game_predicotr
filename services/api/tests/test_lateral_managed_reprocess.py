import json
from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.application.jobs import ImageGeometryRolloutJobReference, JobService
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_worker.images import lateral_partial_contract as contract
from test_managed_reprocess_evidence import (
    _arrange_source_with_evidence,
    _completed_preflight,
    _write_json,
)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "LATERAL_PARTIAL_RELEASED", True)
    repository, source, checksum, old = _arrange_source_with_evidence(tmp_path)
    root = tmp_path / "artifacts"
    manifest = json.loads((root / old["relativePath"]).read_bytes())
    manifest["lateralPartialGeometry"] = contract.LateralPartialGeometrySnapshot().to_payload()
    relative = "data/page-geometry-manifests/lateral.json"
    sha, _ = _write_json(root / relative, manifest)
    preflight = _completed_preflight(
        source.game_id,
        selection_id=UUID(source.input_payload["source_selection_id"]),
        source_manifest_sha256="b" * 64,
        geometry_checksum=sha,
        geometry_relative_path=relative,
    )
    preflight = replace(
        preflight,
        input_payload={
            **preflight.input_payload,
            "lateral_partial_geometry": contract.LateralPartialGeometrySnapshot().to_payload(),
        },
    )
    repository.add_job(preflight)
    descriptor = {
        "checksumSha256": sha,
        "relativePath": relative,
        "preflightJobId": str(preflight.id),
    }
    repository.image_geometry_rollout = ImageGeometryRolloutJobReference(
        geometry_mode="structured_lattice_v3", cell_asset_mode="virtual_default", revision=12
    )
    return repository, source, descriptor, root


def test_new_run_reuses_sources_and_retry_after_restart_is_idempotent(tmp_path, monkeypatch):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    old_payload = json.dumps(source.input_payload, sort_keys=True)
    options = dict(
        pipeline_fingerprint="d" * 64,
        geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        page_geometry_manifest=descriptor,
    )
    first = JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
        source.id, **options
    )
    second = JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
        source.id, **options
    )
    assert first.id == second.id != source.id
    assert first.input_payload["managed_source_job_id"] == str(source.id)
    assert first.input_payload["page_geometry_manifest"] == descriptor
    assert (
        first.input_payload["image_geometry_rollout"]["lateralPartialGeometry"]
        == contract.LateralPartialGeometrySnapshot().to_payload()
    )
    assert json.dumps(source.input_payload, sort_keys=True) == old_payload


def test_old_preflight_requires_explicit_preparation_not_upload(tmp_path, monkeypatch):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    with pytest.raises(JobConflictError) as error:
        JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
            source.id,
            pipeline_fingerprint="d" * 64,
            geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        )
    assert error.value.code == "IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED"


@pytest.mark.parametrize("change", ["missing", "checksum", "scope"])
def test_changed_artifact_never_creates_run(tmp_path, monkeypatch, change):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    count = len(repository.items)
    path = root / descriptor["relativePath"]
    if change == "missing":
        path.unlink()
    elif change == "checksum":
        path.write_text("{}")
    else:
        value = json.loads(path.read_bytes())
        value["sourceSelectionId"] = "wrong"
        descriptor["checksumSha256"], _ = _write_json(path, value)
    with pytest.raises(JobConflictError):
        JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
            source.id,
            pipeline_fingerprint="d" * 64,
            page_geometry_manifest=descriptor,
            geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        )
    assert len(repository.items) == count


@pytest.mark.parametrize("disposition", ["rejected", "manual", "partial"])
def test_guard_decisions_without_board_projection_fail_closed_before_new_run(
    tmp_path, monkeypatch, disposition
):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    # No recognized board exists. A pinned resolution cannot be dropped just
    # because an earlier import never reached projection.
    source.input_payload["geometry_guard_resolution_manifest"] = {
        "checksumSha256": "c" * 64,
        "disposition": disposition,
    }
    count = len(repository.items)
    with pytest.raises(JobConflictError) as error:
        JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
            source.id,
            pipeline_fingerprint="d" * 64,
            page_geometry_manifest=descriptor,
            geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        )
    assert error.value.code == "IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED"
    assert len(repository.items) == count


def test_managed_preflight_can_be_created_without_browser_directory(tmp_path, monkeypatch):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    job = JobService(repository, artifact_root=root).create_page_geometry_preflight_job(
        game_id=source.game_id,
        selection_id=UUID(source.input_payload["source_selection_id"]),
        source_directory=tmp_path / "released-browser-folder",
        source_display_name="v4",
        source_manifest_sha256=source.input_payload["source_manifest_sha256"],
        geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
        managed_source_job_id=source.id,
    )
    assert job.input_payload["managed_source_job_id"] == str(source.id)
    assert len(job.input_payload["managed_source_manifest_checksum_sha256"]) == 64
    assert not (tmp_path / "released-browser-folder").exists()


def test_explicit_new_preflight_does_not_require_an_old_descriptor(tmp_path, monkeypatch):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    source.input_payload.pop("page_geometry_manifest")
    job = JobService(repository, artifact_root=root).create_managed_image_reprocess_job(
        source.id,
        pipeline_fingerprint="d" * 64,
        page_geometry_manifest=descriptor,
        geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
    )
    assert job.input_payload["page_geometry_manifest"] == descriptor


def test_managed_preflight_http_never_touches_browser_files(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.main import create_app

    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    service = JobService(repository, artifact_root=root)
    browser = Mock()
    browser.bind_ready_game.side_effect = AssertionError("Released browser staging accessed")
    client = TestClient(
        create_app(
            ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(root)}),
            job_service_dependency=lambda: service,
            browser_image_selection_service_dependency=lambda: browser,
        )
    )
    selection = source.input_payload["source_selection_id"]
    with client:
        response = client.post(
            f"/api/v1/admin/image-imports/browser-selections/{selection}/geometry-preflight",
            json={
                "gameId": str(source.game_id),
                "geometryEngineVariant": (
                    contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES.value
                ),
                "managedSourceJobId": str(source.id),
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["job"]["inputPayload"]["managedSourceJobId"] == str(source.id)
    browser.bind_ready_game.assert_not_called()


@pytest.mark.parametrize("entrypoint", ["browser", "managed"])
def test_public_import_entrypoints_cannot_drop_guard_history(tmp_path, monkeypatch, entrypoint):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.main import create_app

    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    source.input_payload["geometry_guard_resolution_manifest"] = {"checksumSha256": "c" * 64}
    count = len(repository.items)
    service = JobService(repository, artifact_root=root)
    browser = Mock()
    browser.bind_ready_game.side_effect = AssertionError("Guard must fail before browser access")
    client = TestClient(
        create_app(
            ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(root)}),
            job_service_dependency=lambda: service,
            browser_image_selection_service_dependency=lambda: browser,
        )
    )
    variant = contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES.value
    with client:
        for _ in range(2):
            if entrypoint == "browser":
                response = client.post(
                    "/api/v1/admin/image-imports/browser-selections/"
                    f"{source.input_payload['source_selection_id']}/start",
                    json={
                        "gameId": str(source.game_id),
                        "manifestChecksumSha256": "b" * 64,
                        "preflightChecksumSha256": "c" * 64,
                        "geometryEngineVariant": variant,
                    },
                )
            else:
                response = client.post(
                    f"/api/v1/admin/image-imports/{source.id}/reprocess",
                    params={"geometryEngineVariant": variant},
                    headers={"X-Admin-Target": f"image-import:{source.id}:reprocess"},
                )
            assert response.status_code == 409, response.text
            assert response.json()["code"] == "IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED"
    assert len(repository.items) == count
    browser.bind_ready_game.assert_not_called()


def test_browser_rerun_preserves_lineage_without_cascading_identities(tmp_path, monkeypatch):
    repository, source, descriptor, root = _setup(tmp_path, monkeypatch)
    service = JobService(repository, artifact_root=root)
    options = dict(
        game_id=source.game_id,
        selection_id=UUID(source.input_payload["source_selection_id"]),
        source_directory=tmp_path,
        source_display_name="v4",
        pipeline_fingerprint="d" * 64,
        source_manifest_sha256="b" * 64,
        page_geometry_manifest=descriptor,
        start_mode="rerun_current_models",
        geometry_engine_variant=contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES,
    )
    first = service.create_image_import_job(**options)
    assert first.input_payload["previous_job_id"] == str(source.id)
    with pytest.raises(JobConflictError) as duplicate:
        JobService(repository, artifact_root=root).create_image_import_job(**options)
    assert duplicate.value.code == "JOB_INPUT_ALREADY_EXISTS"
    assert duplicate.value.details["existingJobId"] == str(first.id)
