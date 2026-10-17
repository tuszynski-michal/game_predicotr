"""Durable grid command authorization and closed transport contract."""

import copy
from uuid import uuid4

import pytest
from game_predictor_api.application.grid_reinference import command_transition, digest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.schemas.grid_reinference import GridReinferencePrepare
from pydantic import ValidationError


def operation(scope="pilot"):
    return {
        "operationId": str(uuid4()),
        "jobId": str(uuid4()),
        "state": "prepared",
        "phase": "prepare",
        "revision": 0,
        "receipts": {},
        "manifestSha256": "a" * 64,
        "executionScope": scope,
        "scopeSignature": "same-selector-model-policy",
        "modelSnapshot": {"version": "immutable"},
        "runtimePolicy": "grid-reinference-runtime-v1",
        "acceptancePolicy": "v3-engine-acceptance-v1",
        "sourceCount": 100,
    }


def command(document, **extra):
    return {"idempotencyKey": str(uuid4()), "expectedRevision": document["revision"], **extra}


def freeze(document):
    cmd = command(document, manifestSha256=document["manifestSha256"])
    command_transition(document, "freeze", cmd, actor="operator")


def test_freeze_start_lost_reply_keeps_pin_and_receipts():
    document = operation()
    model = copy.deepcopy(document["modelSnapshot"])
    freeze(document)
    cmd = command(document, manifestSha256=document["manifestSha256"])
    receipt = command_transition(document, "start", cmd, actor="operator")
    persisted = copy.deepcopy(document)  # Restart from only committed state.
    assert command_transition(persisted, "start", cmd, actor="operator") == receipt
    assert persisted == document
    assert persisted["modelSnapshot"] == model
    assert persisted["runtimePolicy"] == document["runtimePolicy"]
    assert persisted["acceptancePolicy"] == document["acceptancePolicy"]
    assert persisted["startSha256"] == persisted["freezeSha256"]
    assert persisted["phase"] == "infer"


def test_same_key_changed_body_conflicts_before_revision():
    document = operation()
    cmd = command(document, manifestSha256=document["manifestSha256"])
    command_transition(document, "freeze", cmd, actor="operator")
    with pytest.raises(JobConflictError, match="different content"):
        command_transition(
            document, "freeze", {**cmd, "manifestSha256": "b" * 64}, actor="operator"
        )


@pytest.mark.parametrize("state", ["prepared", "frozen"])
def test_generic_resume_cannot_authorize_start(state):
    document = operation()
    document["state"] = state
    with pytest.raises(JobConflictError) as caught:
        command_transition(
            document, "resume", command(document, expectedPhase="prepare"), actor="operator"
        )
    assert caught.value.code == "GRID_REINFERENCE_START_REQUIRED"


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_interrupted_inference_requires_and_preserves_prior_authorization(state):
    document = operation()
    document.update(state=state, phase="infer")
    cmd = command(document, expectedPhase="infer")
    with pytest.raises(JobConflictError) as caught:
        command_transition(document, "resume", cmd, actor="operator")
    assert caught.value.code == "GRID_REINFERENCE_START_REQUIRED"
    document["startSha256"] = document["manifestSha256"]
    document["processedSources"] = 11
    original = copy.deepcopy(document["modelSnapshot"])
    command_transition(document, "resume", cmd, actor="operator")
    assert document["state"] == "queued"
    assert document["processedSources"] == 11
    assert document["modelSnapshot"] == original


def test_broader_ack_is_compatible_subset_report_and_explicit_confirmation():
    broad, pilot = operation("broader"), operation()
    pilot.update(state="completed", reportSha256="c" * 64, sourceCount=37)
    ack = command(
        broad, pilotOperationId=pilot["operationId"], pilotReportSha256=pilot["reportSha256"]
    )
    command_transition(broad, "pilot-ack", ack, actor="operator", pilot=pilot)
    assert broad["pilotAck"]["actor"] == "operator"
    freeze(broad)
    start = command(broad, manifestSha256=broad["manifestSha256"])
    with pytest.raises(JobConflictError):
        command_transition(broad, "start", start, actor="operator")
    command_transition(broad, "start", {**start, "broadScopeConfirmed": True}, actor="operator")
    assert broad["state"] == "queued"
    assert "qualityPass" not in broad["pilotAck"]


@pytest.mark.parametrize(
    "change",
    [
        {"state": "failed"},
        {"sourceCount": 101},
        {"scopeSignature": "different-model"},
        {"reportSha256": "d" * 64},
    ],
)
def test_invalid_pilot_never_authorizes_broader(change):
    broad, pilot = operation("broader"), operation()
    pilot.update(state="completed", reportSha256="c" * 64)
    ack = command(
        broad, pilotOperationId=pilot["operationId"], pilotReportSha256=pilot["reportSha256"]
    )
    pilot.update(change)
    with pytest.raises(JobConflictError):
        command_transition(broad, "pilot-ack", ack, actor="operator", pilot=pilot)


def test_closed_prepare_defaults_and_scope_validation():
    parsed = GridReinferencePrepare.model_validate({"idempotencyKey": str(uuid4())})
    assert parsed.execution_scope == "pilot"
    assert parsed.selector.categories == ["grid_issue", "deferred"]
    with pytest.raises(ValidationError):
        GridReinferencePrepare.model_validate({"idempotencyKey": str(uuid4()), "clientPass": True})


def test_receipt_namespaces_and_hash_are_order_independent():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    document = operation()
    key = str(uuid4())
    command_transition(
        document,
        "freeze",
        {"idempotencyKey": key, "expectedRevision": 0, "manifestSha256": "a" * 64},
        actor="operator",
    )
    command_transition(
        document,
        "start",
        {"idempotencyKey": key, "expectedRevision": 1, "manifestSha256": "a" * 64},
        actor="operator",
    )
    assert len(document["receipts"]) == 2


def test_http_prepare_closed_defaults_and_typed_start_request():
    from types import SimpleNamespace

    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from game_predictor_api.api.grid_reinference import register_grid_reinference_routes
    from game_predictor_api.schemas.grid_reinference import GridReinferenceResponse

    game, op, job = uuid4(), uuid4(), uuid4()
    calls = []
    response = dict(
        gameId=str(game),
        operationId=str(op),
        jobId=str(job),
        state="prepared",
        phase="prepare",
        revision=0,
        manifestSha256="a" * 64,
        reportSha256=None,
        sourceCount=2,
        targetCount=3,
        processedSources=0,
        outcomes={},
        modelSnapshot={"pin": "fixed"},
        runtimePolicy="grid-reinference-runtime-v1",
        acceptancePolicy="v3-engine-acceptance-v1",
        membershipCapturedAt="capture",
        preparationStartedAt="begin",
        preparationFinishedAt="end",
    )

    class Service:
        def prepare(self, game_id, body, actor):
            calls.append((game_id, body, actor))
            return response

        def execute(self, game_id, operation_id, kind, body, actor):
            calls.append((game_id, operation_id, kind, body, actor))
            return response

    app = FastAPI()
    router = APIRouter(prefix="/api/v1/admin/image-review-items")
    register_grid_reinference_routes(router, lambda: SimpleNamespace(grid_reinference=Service()))
    app.include_router(router)
    with TestClient(app) as client:
        key = str(uuid4())
        result = client.post(
            f"/api/v1/admin/image-review-items/grid-reinference/{game}/prepare",
            json={"idempotencyKey": key},
        )
        assert result.status_code == 200
        GridReinferenceResponse.model_validate(result.json())
        assert calls[0][1]["selector"]["categories"] == ["grid_issue", "deferred"]
        assert calls[0][1]["executionScope"] == "pilot"
        assert calls[0][2] == "local-admin"
        path = f"/api/v1/admin/image-review-items/grid-reinference/{game}/operations/{op}/start"
        assert (
            client.post(path, json={"idempotencyKey": key, "expectedRevision": 0}).status_code
            == 422
        )
        assert (
            client.post(
                path,
                json={"idempotencyKey": key, "expectedRevision": 0, "manifestSha256": "a" * 64},
            ).status_code
            == 200
        )
        assert calls[-1][2] == "start"


def test_admin_confirmation_targets_cover_every_mutation():
    from game_predictor_api.security.local_admin import match_high_impact_operation

    game, operation_id = uuid4(), uuid4()
    prefix = f"/api/v1/admin/image-review-items/grid-reinference/{game}"
    assert (
        match_high_impact_operation("POST", prefix + "/prepare")[1]
        == f"grid-reinference:{game}:prepare"
    )
    for action in ("freeze", "pilot-ack", "start", "resume", "cancel"):
        assert (
            match_high_impact_operation("POST", f"{prefix}/operations/{operation_id}/{action}")[1]
            == f"grid-reinference:{game}:{operation_id}"
        )


def test_canonical_self_is_eligible_foreign_owner_and_human_decisions_are_protected():
    from game_predictor_api.storage.grid_reinference import target_protection

    target = {
        "kind": "automatic",
        "board": {"id": "board", "approved_geometry_revision": None},
        "review": {"id": "review", "status": "pending"},
        "owner": {"recognized_board_id": "board", "review_item_id": "review"},
        "cells": [],
    }
    assert target_protection(target) is None
    foreign = copy.deepcopy(target)
    foreign["owner"]["review_item_id"] = "other-review"
    assert target_protection(foreign) == "foreign_owner"
    target["cells"] = [{"review_state": "pending", "assignment_source": "human"}]
    assert target_protection(target) == "human_cell_decision"


def test_historical_grid_issue_is_not_a_current_report():
    from pathlib import Path
    from types import SimpleNamespace

    from game_predictor_api.storage.grid_reinference import (
        SqlAlchemyGridReinferenceRepository,
        target_protection,
    )

    board = {
        "id": "board",
        "position_index": 0,
        "sequence_number": 5,
        "geometry_revision": 2,
        "source_geometry_revision_id": "current",
        "approved_geometry_revision": None,
    }
    cell = {
        "quality_issue": "grid_issue",
        "review_state": "pending",
        "geometry_revision": 1,
        "source_geometry_revision_id": "old",
        "asset_mode": "virtual_source",
        "assignment_source": "model",
    }
    row = {
        "board": board,
        "review": {"id": "review", "status": "pending"},
        "cells": [cell],
        "owner": None,
    }
    session = SimpleNamespace(
        execute=lambda statement, *_args, **_kwargs: SimpleNamespace(
            mappings=lambda: [] if "DISTINCT ON" in str(statement) else [row]
        )
    )
    repository = SqlAlchemyGridReinferenceRepository(session, Path("."))
    selected = repository.source_targets(uuid4(), uuid4(), {"categories": ["all_automatic"]})
    assert selected[0]["kind"] == "automatic" and target_protection(selected[0]) is None
    cell.update(geometry_revision=2, source_geometry_revision_id="current")
    assert (
        repository.source_targets(uuid4(), uuid4(), {"categories": ["all_automatic"]})[0]["kind"]
        == "grid_issue"
    )


@pytest.mark.parametrize("version,kind", [(2, "grid-reinference-v1"), (3, "pending_grid_only")])
def test_payload_versions_cannot_cross_legacy_and_selected_contract(version, kind):
    from game_predictor_api.domain.jobs import JobError, JobType, create_job

    with pytest.raises(JobError):
        create_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=uuid4(),
            input_payload={"schema_version": version, "inference_kind": kind},
        )


def test_fingerprint_ignores_operational_owner_pending_fields_but_keeps_decisions():
    from game_predictor_api.storage.grid_reinference import target_fence

    snapshot = {
        "board": None,
        "review": None,
        "cells": [],
        "pending": {
            "id": "pending",
            "status": "pending",
            "expected_geometry_revision": 0,
            "updated_at": "old",
            "created_at": "old",
            "attempt_count": 3,
        },
        "owner": {
            "review_item_id": "owner",
            "resolution_revision": 2,
            "updated_at": "old",
            "document_count": 5,
        },
    }
    changed = copy.deepcopy(snapshot)
    changed["pending"].update(updated_at="new", created_at="new", attempt_count=4)
    changed["owner"].update(updated_at="new", document_count=6)
    assert digest(target_fence(snapshot)) == digest(target_fence(changed))
    changed["pending"]["expected_geometry_revision"] = 1
    assert digest(target_fence(snapshot)) != digest(target_fence(changed))


def test_cancel_failed_is_typed_phase_conflict_without_receipt_mutation():
    document = operation()
    document["state"] = "failed"
    original = copy.deepcopy(document)
    with pytest.raises(JobConflictError) as caught:
        command_transition(document, "cancel", command(document), actor="operator")
    assert caught.value.code == "GRID_REINFERENCE_PHASE_CONFLICT"
    assert document == original
