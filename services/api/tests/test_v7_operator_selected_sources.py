"""Normal operator sources are per-run bindings, independent of calibration game."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.semi_automatic_image_selections import (
    create_semi_automatic_image_selections_router,
)
from game_predictor_api.application.image_imports import ImageFolderSelectionService
from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.v7_pilot_acceptance import (
    receipt_matches_gate,
    validate_pilot_acceptance,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7DeliveryConflict,
    V7PilotSnapshot,
    payload_fingerprint,
)
from game_predictor_api.storage.models import (
    SemiAutomaticV7ActivationGateModel,
    V7PilotAcceptanceModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from PIL import Image
from sqlalchemy.orm import Session
from test_v7_pilot_acceptance import acceptance
from test_v7_selection_delivery_api import V7MemoryRepository


def operator_receipt(tmp_path):
    receipt, gate = acceptance(tmp_path)
    receipt.update(
        version="v7-reviewed-pilot-acceptance-v2",
        sourcePolicy="operator_selected_local_folder",
        scope="real_pilot",
        fixtureRoot=None,
        sourceGameRef=None,
        sourceBindings=[],
    )
    return receipt, replace(
        gate,
        source_policy="operator_selected_local_folder",
        source_game_ref=None,
        source_bindings=(),
        receipt_fingerprint=payload_fingerprint(receipt),
        acceptance_receipt=receipt,
    )


def source_folder(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "no-truth-in-filename.jpg")
    return root


def test_receipt_and_reload_bind_new_roots_without_assigning_game_777(tmp_path):
    receipt, gate = operator_receipt(tmp_path)
    validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")
    assert receipt_matches_gate(
        receipt, payload_fingerprint(receipt), gate, "game_predictor_v7_pilot"
    )
    first = source_folder(tmp_path, "Blazing")
    second = source_folder(tmp_path, "another-game")
    snapshot = gate.snapshot_for(first, "a" * 64)
    restored = V7PilotSnapshot.from_payload(snapshot.as_payload())
    gate.require_snapshot(restored, first, "a" * 64)
    assert (
        snapshot.source_game_ref is None
        and snapshot.source_policy == "operator_selected_local_folder"
    )
    assert restored == snapshot
    assert gate.snapshot_for(second, "a" * 64).binding_fingerprint != snapshot.binding_fingerprint
    for root, fingerprint in ((second, "a" * 64), (first, "b" * 64)):
        with pytest.raises(V7DeliveryConflict) as error:
            gate.require_snapshot(restored, root, fingerprint)
        assert error.value.code == "V7_PILOT_GENERATION_CHANGED"
    for changes in (
        {"generation": 2},
        {"geometry_family_id": "other"},
        {"observer_fingerprint": "0" * 64},
    ):
        with pytest.raises(V7DeliveryConflict):
            replace(gate, **changes).require_snapshot(restored, first, "a" * 64)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "technical_fixture"},
        {"sourceGameRef": "777"},
        {"sourceBindings": [{}]},
        {"sourcePolicy": "exact_sources"},
        {"automaticAllowed": True},
    ],
)
def test_operator_receipt_rejects_fake_game_fixture_or_weakened_policy(tmp_path, changes):
    receipt, gate = operator_receipt(tmp_path)
    receipt.update(changes)
    with pytest.raises(ValueError):
        validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")
    assert not receipt_matches_gate(
        receipt, payload_fingerprint(receipt), gate, "game_predictor_v7_pilot"
    )


def test_v1_still_rejects_other_roots_and_serializes_without_new_field(tmp_path):
    receipt, gate = acceptance(tmp_path)
    validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")
    root = Path(receipt["sourceBindings"][0]["sourceRoot"])
    snapshot = gate.snapshot_for(root, "a" * 64)
    assert "sourcePolicy" not in snapshot.as_payload()
    assert V7PilotSnapshot.from_payload(snapshot.as_payload()) == snapshot
    with pytest.raises(V7DeliveryConflict) as error:
        gate.require_source_root(source_folder(tmp_path, "new-game"))
    assert error.value.code == "V7_SOURCE_BINDING_MISMATCH"


@pytest.mark.parametrize("corruption", [None, "policy", "game", "generation", "receipt"])
def test_sql_provider_reconstructs_only_verified_operator_policy(tmp_path, corruption):
    payload, identity = operator_receipt(tmp_path)
    row = SemiAutomaticV7ActivationGateModel(
        singleton=True,
        pilot_status="active",
        pilot_generation=1,
        pilot_mode="semi_automatic",
        pilot_geometry_family_id=identity.geometry_family_id,
        pilot_source_game_ref=None,
        pilot_source_policy="operator_selected_local_folder",
        pilot_source_bindings=[],
        pilot_profile_fingerprint=identity.profile_fingerprint,
        pilot_observer_fingerprint=identity.observer_fingerprint,
        pilot_ocr_model_fingerprint=identity.ocr_model_fingerprint,
        pilot_acceptance_receipt_fingerprint=identity.receipt_fingerprint,
        pilot_accepted_by=payload["actor"],
        pilot_accepted_at=datetime.fromisoformat(str(payload["acceptedAt"])),
    )
    receipt = V7PilotAcceptanceModel(
        operation_id=uuid4(),
        request_fingerprint="0" * 64,
        receipt_fingerprint=identity.receipt_fingerprint,
        receipt=payload,
        expected_generation=0,
        resulting_generation=1,
    )
    if corruption == "policy":
        row.pilot_source_policy = "exact_sources"
    elif corruption == "game":
        row.pilot_source_game_ref = "777"
    elif corruption == "generation":
        row.pilot_generation = 2
    values = iter([row, None if corruption == "receipt" else receipt, "game_predictor_v7_pilot"])
    session = SimpleNamespace(scalar=lambda _query: next(values))
    gate = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, session)).get_v7_pilot_gate()
    assert gate.enabled is (corruption is None)
    if corruption is None:
        assert (
            gate.source_policy == "operator_selected_local_folder" and gate.source_game_ref is None
        )


def request_fixture(tmp_path):
    receipt, gate = operator_receipt(tmp_path)
    root = source_folder(tmp_path, "Blazing")
    now = [datetime.now(UTC)]
    folders = ImageFolderSelectionService(lambda: root, clock=lambda: now[0])
    repository = V7MemoryRepository(gate)

    def validate(current):
        assert current.enabled and receipt_matches_gate(
            receipt, payload_fingerprint(receipt), current, "game_predictor_v7_pilot"
        )

    service = SemiAutomaticImageSelectionService(
        repository,
        object(),
        enabled=True,
        artifact_root=tmp_path / "artifacts",
        folder_selection=folders,
        v7_artifacts=SimpleNamespace(validate=validate),
    )
    app = FastAPI()

    @app.exception_handler(JobError)
    def failure(_request, error):
        return JSONResponse(
            status_code=409, content={"error": {"code": error.code, "message": error.message}}
        )

    app.include_router(create_semi_automatic_image_selections_router(lambda: service))
    return TestClient(app), service, repository, now, root


def test_http_start_accepts_native_token_for_new_game_and_returns_typed_snapshot(tmp_path):
    client, service, repository, _now, root = request_fixture(tmp_path)
    selected = service.select_local_source()
    response = client.post(
        "/admin/semi-automatic-image-selections",
        json={
            "selectionToken": selected.selection_token,
            "mode": "v7_selection",
            "firstSequenceNumber": 1,
            "lastSequenceNumber": 18,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    body = response.json()["run"]
    snapshot = body["v7Configuration"]["pilot"]
    assert snapshot["sourceGameRef"] is None
    assert snapshot["sourcePolicy"] == "operator_selected_local_folder"
    assert body["v7Configuration"]["mode"] == "semi_automatic"
    assert len(repository.runs) == 1 and not repository.operations
    run = next(iter(repository.runs.values()))
    assert run.job.input_payload["source_kind"] == "local_folder"
    assert not root.with_name(root.name + " cut").exists()
    capabilities = client.get("/admin/semi-automatic-image-selections/capabilities").json()
    assert capabilities["v7"]["sourcePolicy"] == "operator_selected_local_folder"
    assert capabilities["v7"]["automaticStartEnabled"] is False
    assert str(root) not in str(capabilities)


@pytest.mark.parametrize("kind", ["missing", "upload", "expired", "automatic"])
def test_operator_policy_preserves_token_local_only_and_automatic_guards(tmp_path, kind):
    client, service, repository, now, _root = request_fixture(tmp_path)
    selected = service.select_local_source()
    body = {
        "selectionToken": selected.selection_token,
        "mode": "v7_selection",
        "firstSequenceNumber": 1,
        "lastSequenceNumber": 18,
    }
    if kind == "missing":
        body.pop("selectionToken")
    elif kind == "upload":
        body["uploadId"] = "11111111-1111-4111-8111-111111111111"
    elif kind == "expired":
        now[0] += timedelta(days=1)
    else:
        body["v7"] = {"mode": "automatic"}
    response = client.post("/admin/semi-automatic-image-selections", json=body)
    assert response.status_code in (409, 422), response.text
    assert not repository.runs and not repository.operations
    assert not (tmp_path / "artifacts").exists()


def test_changed_source_inventory_after_start_blocks_restored_snapshot(tmp_path):
    _receipt, gate = operator_receipt(tmp_path)
    root = source_folder(tmp_path, "Blazing")
    before = build_local_source_manifest(root, selection_id=uuid4(), display_name=root.name)
    snapshot = V7PilotSnapshot.from_payload(
        gate.snapshot_for(root, before.source_fingerprint).as_payload()
    )
    Image.new("RGB", (8, 8), "black").save(root / "no-truth-in-filename.jpg")
    after = build_local_source_manifest(root, selection_id=uuid4(), display_name=root.name)
    with pytest.raises(V7DeliveryConflict):
        gate.require_snapshot(snapshot, root, after.source_fingerprint)
