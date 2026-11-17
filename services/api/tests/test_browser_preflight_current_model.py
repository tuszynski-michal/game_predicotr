"""New browser preparation follows assignment; immutable work keeps its model."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.image_imports import (
    BrowserImageUpload,
    BrowserReadySelection,
    ImageSelectionPurpose,
)
from game_predictor_api.domain.grid_model_registry import historical_catalogue
from game_predictor_api.domain.image_sequence_canonical import (
    BrowserSequenceManifest,
    BrowserSequenceSource,
)
from game_predictor_api.domain.jobs import JobConflictError, JobStatus
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    proposal_checksum_sha256,
)
from test_managed_reprocess_evidence import NOW, _terminal_import, _write_managed_manifest
from test_neural_page_geometry_api import _frozen_mumie_preflight, _neural_jobs, binding


def current_snapshot(game_id):
    descriptor = deepcopy(
        next(row for row in historical_catalogue() if row["familyCode"] == "grid_profile_mumie_v1")
    )
    descriptor["versionId"] = str(uuid4())
    return NeuralGridSnapshot.from_catalogue(
        game_id=str(game_id),
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=descriptor,
    ).to_payload()


def service(tmp_path, monkeypatch, repository, current):
    jobs = _neural_jobs(tmp_path, monkeypatch, repository, "grid_profile_mumie_v1")
    jobs._grid_profile_snapshot_resolver.resolve_neural_grid_proposal = lambda **_: current
    return jobs


def test_browser_preflight_pins_current_model_and_replays_after_service_restart(
    tmp_path, monkeypatch
):
    game, selection, old, repository, descriptor, frozen = _frozen_mumie_preflight(tmp_path)
    current = current_snapshot(game)
    sources = BrowserSequenceManifest(
        (BrowserSequenceSource(0, "seq_101-105.jpg", "source.jpg", 1, "a" * 64, (101, 105)),),
        (),
        "b" * 64,
    )
    ready = BrowserReadySelection(
        BrowserImageUpload(
            upload_id=selection,
            path=tmp_path,
            display_name="staging",
            purpose=ImageSelectionPurpose.LAYOUT_IMPORT,
            game_id=game,
            expected_file_count=1,
            expected_total_bytes=1,
            created_at=NOW,
            uploaded_indexes={0},
            uploaded_files={},
        ),
        sources,
        NOW,
        None,
    )
    browser = SimpleNamespace(
        require_current_ready=lambda *_: ready, mark_in_use=lambda *_, **__: None
    )
    services = [service(tmp_path, monkeypatch, repository, current)]
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            browser_selection_service_dependency=lambda: browser,
            job_service_dependency=lambda: services[0],
            iterative_import_service_dependency=lambda: None,
            page_geometry_override_service_dependency=lambda: None,
            image_sequence_canonical_service_dependency=lambda: None,
            image_import_geometry_guard_service_dependency=lambda: None,
            artifact_root=tmp_path,
        )
    )
    endpoint = f"/admin/image-imports/browser-selections/{selection}/geometry-preflight"
    with TestClient(app) as client:
        response = client.post(endpoint, json={"gameId": str(game)})
        assert response.status_code == 201, response.text
        first = response.json()
        assert first["created"] is True
        payload = first["job"]["inputPayload"]
        assert payload["neuralGridProposal"] == current
        assert payload.get("basePageGeometryManifest") is None
        assert first["job"]["id"] != str(old.id)
        services[0] = service(tmp_path, monkeypatch, repository, current)
        replay = client.post(endpoint, json={"gameId": str(game)})
        assert replay.status_code == 201, replay.text
        assert replay.json()["created"] is False
        assert replay.json()["job"]["id"] == first["job"]["id"]
        assert len(repository.items) == 2
        # Prove the previous version has a valid, reusable completed artifact
        # before asking for another version. Its entries must not cross models.
        first_job = repository.items[UUID(first["job"]["id"])]
        completed_manifest = json.loads((tmp_path / descriptor["relativePath"]).read_text())
        completed_manifest["version"] = first_job.input_payload["preflight_policy_version"]
        completed_manifest["neuralGridProposal"] = current
        completed_manifest["pageRegistrationProfile"] = first_job.input_payload[
            "page_registration_profile"
        ]
        completed_manifest["entries"]["a" * 64]["neuralProposal"]["engineSnapshot"] = current
        completed_proposal = completed_manifest["entries"]["a" * 64]["neuralProposal"]
        completed_proposal["proposalChecksumSha256"] = proposal_checksum_sha256(completed_proposal)
        raw = json.dumps(completed_manifest).encode()
        relative = "data/page-geometry-manifests/current-completed.json"
        (tmp_path / relative).write_bytes(raw)
        completed = replace(
            first_job,
            status=JobStatus.COMPLETED,
            checkpoint_payload={
                "complete": True,
                "geometry_manifest_checksum_sha256": hashlib.sha256(raw).hexdigest(),
                "geometry_manifest_relative_path": relative,
            },
        )
        repository.items[completed.id] = completed
        assert (
            services[0]._select_page_geometry_base_manifest(
                [completed],
                input_payload=completed.input_payload,
            )
            is not None
        )
        # Activating another version creates a separate request, never a second
        # response to the old request or a rewrite of an old frozen manifest.
        next_current = current_snapshot(game)
        services[0] = service(tmp_path, monkeypatch, repository, next_current)
        changed = client.post(endpoint, json={"gameId": str(game)})
        assert changed.status_code == 201, changed.text
        assert changed.json()["created"] is True
        assert changed.json()["job"]["inputPayload"]["neuralGridProposal"] == next_current
        assert changed.json()["job"]["inputPayload"].get("basePageGeometryManifest") is None
    assert repository.items[old.id].input_payload["neural_grid_proposal"] == frozen
    assert (
        services[0]._neural_import_snapshot(
            game_id=game,
            selection_id=selection,
            source_manifest_sha256="b" * 64,
            descriptor=descriptor,
        )
        == frozen
    )


@pytest.mark.parametrize("refresh", [False, True])
def test_saved_detection_binding_retains_its_exact_frozen_proposal(tmp_path, monkeypatch, refresh):
    game, selection, old, repository, descriptor, frozen = _frozen_mumie_preflight(tmp_path)
    manifest = json.loads((tmp_path / descriptor["relativePath"]).read_text())
    source = manifest["entries"]["a" * 64]["neuralProposal"]
    overrides = {"a" * 64: {"neuralProposalBinding": binding(source)}}
    before = deepcopy(overrides)
    jobs = service(tmp_path, monkeypatch, repository, current_snapshot(game))
    selected = jobs._neural_preflight_snapshot(
        game_id=game,
        selection_id=selection,
        source_manifest_sha256="b" * 64,
        candidates=[old],
        overrides=overrides,
        use_current_model=refresh,
    )
    assert selected == frozen
    assert overrides == before


def test_legacy_service_call_still_preserves_completed_model(tmp_path, monkeypatch):
    game, selection, old, repository, _, frozen = _frozen_mumie_preflight(tmp_path)
    jobs = service(tmp_path, monkeypatch, repository, current_snapshot(game))
    assert (
        jobs._neural_preflight_snapshot(
            game_id=game,
            selection_id=selection,
            source_manifest_sha256="b" * 64,
            candidates=[old],
            overrides={},
        )
        == frozen
    )


def test_current_model_failure_does_not_fall_back_to_an_old_staging_model(tmp_path, monkeypatch):
    game, selection, old, repository, _, _ = _frozen_mumie_preflight(tmp_path)
    jobs = service(tmp_path, monkeypatch, repository, current_snapshot(game))

    def missing(**_):
        raise JobConflictError("GRID_MODEL_ASSIGNMENT_REQUIRED", "Assign a model.")

    jobs._grid_profile_snapshot_resolver.resolve_neural_grid_proposal = missing
    with pytest.raises(JobConflictError) as caught:
        jobs._neural_preflight_snapshot(
            game_id=game,
            selection_id=selection,
            source_manifest_sha256="b" * 64,
            candidates=[old],
            overrides={},
            use_current_model=True,
        )
    assert caught.value.code == "GRID_MODEL_ASSIGNMENT_REQUIRED"


@pytest.mark.parametrize("kind", ["foreign_binding", "manual_quads"])
def test_other_bindings_and_manual_quads_do_not_prevent_current_model(tmp_path, monkeypatch, kind):
    game, selection, old, repository, descriptor, _ = _frozen_mumie_preflight(tmp_path)
    current = current_snapshot(game)
    if kind == "foreign_binding":
        manifest = json.loads((tmp_path / descriptor["relativePath"]).read_text())
        saved = binding(manifest["entries"]["a" * 64]["neuralProposal"])
        saved["sourceSelectionId"] = str(uuid4())
        overrides = {"a" * 64: {"neuralProposalBinding": saved}}
    else:
        overrides = {"a" * 64: {"quads": [[{"x": 1, "y": 2}]], "revision": 3}}
    before = deepcopy(overrides)
    jobs = service(tmp_path, monkeypatch, repository, current)
    selected = jobs._neural_preflight_snapshot(
        game_id=game,
        selection_id=selection,
        source_manifest_sha256="b" * 64,
        candidates=[old],
        overrides=overrides,
        use_current_model=True,
    )
    assert selected == current
    assert overrides == before


def test_missing_frozen_proposal_for_saved_binding_still_fails_closed(tmp_path, monkeypatch):
    game, selection, _, repository, descriptor, _ = _frozen_mumie_preflight(tmp_path)
    manifest = json.loads((tmp_path / descriptor["relativePath"]).read_text())
    overrides = {
        "a" * 64: {
            "neuralProposalBinding": binding(manifest["entries"]["a" * 64]["neuralProposal"])
        }
    }
    jobs = service(tmp_path, monkeypatch, repository, current_snapshot(game))
    with pytest.raises(JobConflictError) as caught:
        jobs._neural_preflight_snapshot(
            game_id=game,
            selection_id=selection,
            source_manifest_sha256="b" * 64,
            candidates=[],
            overrides=overrides,
            use_current_model=True,
        )
    assert caught.value.code == "NEURAL_SOURCE_PROPOSAL_UNAVAILABLE"


@pytest.mark.parametrize("correction", ["manual_quads", "source_exclusion"])
def test_managed_preflight_retains_original_model_after_assignment_changes(
    tmp_path,
    monkeypatch,
    correction,
):
    game, selection, _, repository, descriptor, frozen = _frozen_mumie_preflight(tmp_path)
    source = _terminal_import(
        game,
        selection_id=selection,
        source_manifest_sha256="b" * 64,
        page_descriptor=descriptor,
    )
    source = replace(
        source,
        status=JobStatus.COMPLETED,
        input_payload={
            **source.input_payload,
            "neural_grid_proposal": frozen,
        },
    )
    repository.add_job(source)
    _write_managed_manifest(tmp_path, source, source_checksum="a" * 64)
    jobs = service(tmp_path, monkeypatch, repository, current_snapshot(game))
    overrides = (
        {
            "a" * 64: {
                "quads": [
                    [
                        {"x": 10, "y": 10},
                        {"x": 30, "y": 10},
                        {"x": 30, "y": 40},
                        {"x": 10, "y": 40},
                    ]
                ],
                "revision": 1,
            }
        }
        if correction == "manual_quads"
        else {}
    )
    exclusions = (
        {"a" * 64: {"reason": "outside_selected_range"}} if correction == "source_exclusion" else {}
    )
    jobs._page_geometry_override_snapshot_resolver = SimpleNamespace(
        snapshot=lambda **_: overrides,
        exclusion_snapshot=lambda **_: exclusions,
    )
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            browser_selection_service_dependency=lambda: None,
            job_service_dependency=lambda: jobs,
            iterative_import_service_dependency=lambda: None,
            page_geometry_override_service_dependency=lambda: None,
            image_sequence_canonical_service_dependency=lambda: None,
            image_import_geometry_guard_service_dependency=lambda: None,
            artifact_root=tmp_path,
        )
    )
    with TestClient(app) as client:
        response = client.post(
            f"/admin/image-imports/browser-selections/{selection}/geometry-preflight",
            json={"gameId": str(game), "managedSourceJobId": str(source.id)},
        )
    assert response.status_code == 201, response.text
    job = repository.items[UUID(response.json()["job"]["id"])]
    assert job.input_payload["neural_grid_proposal"] == frozen
    assert job.input_payload["managed_source_job_id"] == str(source.id)
    assert job.input_payload["page_geometry_overrides"] == overrides
    assert job.input_payload["source_exclusions"] == exclusions
