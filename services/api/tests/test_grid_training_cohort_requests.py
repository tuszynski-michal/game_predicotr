"""Closed bounded HTTP contract, actor boundary and metadata-only reload."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_training_cohorts import create_grid_training_cohorts_router
from game_predictor_api.schemas.grid_training_cohorts import (
    GridCohortEligibility,
    GridCohortPrepareCommand,
    GridSourceIdentityCompleteCommand,
)
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)
from pydantic import ValidationError


def prepare_body():
    return {
        "idempotencyKey": str(uuid4()),
        "familyId": str(uuid4()),
        "baseVersionId": str(uuid4()),
        "mode": "grid-only",
        "selector": {"sourceIds": [str(uuid4())]},
        "recordings": [{"groupId": str(uuid4()), "role": "TRAIN"}],
    }


def test_metadata_reload_and_actor_before_replay_and_bounded_routes(tmp_path):
    game, cohort = uuid4(), uuid4()
    body = prepare_body()
    calls = []
    header = {
        "id": str(cohort),
        "gameId": str(game),
        "revision": 0,
        "status": "preparing",
        "mode": "grid-only",
        "familyId": body["familyId"],
        "baseVersionId": body["baseVersionId"],
        "previewSha256": None,
        "manifestSha256": None,
        "summary": {"roles": [], "reasonCounts": {}},
        "nextCaptureCursor": 0,
        "nextMaterializationCursor": None,
        "createdAt": "now",
    }

    def prepare(*arguments):
        calls.append(("prepare", arguments))
        return {
            "cohort": header,
            "receipt": {
                "idempotencyKey": body["idempotencyKey"],
                "kind": "prepare",
                "revision": 0,
                "outcome": "prepared",
            },
        }

    def list_cohorts(*arguments):
        calls.append(("GET", arguments))
        return {"items": [header], "nextCursor": None}

    facts = {
        "qualification": "unresolved",
        "reasons": ["LABEL_STALE"],
        "manifestSha256": None,
        "humanLabelWithdrawn": None,
        "liveSourceLinked": None,
        "snapshotBytesAvailable": None,
    }

    def eligibility(*arguments):
        calls.append(("GET", arguments))
        return facts

    service = SimpleNamespace(prepare=prepare, list=list_cohorts, eligibility=eligibility)
    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    app.include_router(create_grid_training_cohorts_router(lambda: service), prefix="/api/v1")
    path = f"/api/v1/admin/games/{game}/grid-training-cohorts"
    headers = {"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"}
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get(path).status_code == client.get(path).status_code == 200
        for withdrawn, linked in ((None, None), (False, True), (True, False)):
            facts.update(humanLabelWithdrawn=withdrawn, liveSourceLinked=linked)
            response = client.get(f"{path}/{cohort}/eligibility")
            assert response.status_code == 200
            assert response.json() == facts
            assert response.json()["snapshotBytesAvailable"] is None
        facts.update(
            qualification="blocked",
            reasons=["SOURCE_REMOVED_NEW_USE_BLOCKED"],
            humanLabelWithdrawn=None,
            liveSourceLinked=False,
        )
        response = client.get(f"{path}/{cohort}/eligibility")
        assert response.status_code == 200 and response.json() == facts
        assert all(kind == "GET" for kind, _ in calls)
        assert client.post(f"{path}/prepare", json=body).status_code == 403
        assert all(kind == "GET" for kind, _ in calls)
        assert client.post(f"{path}/prepare", json=body, headers=headers).status_code == 200
        assert calls[-1][1] == (
            game,
            {**body, "selector": {**body["selector"], "importJobId": None}},
            "local-owner",
        )
        count = len(calls)
        assert (
            client.post(
                f"{path}/prepare", json={**body, "pixelSha256": "a" * 64}, headers=headers
            ).status_code
            == 422
        )
        assert client.get(f"{path}/{cohort}/members?limit=201").status_code == 422
        assert (
            client.post(
                f"{path}/{cohort}/materialize-page",
                json={"idempotencyKey": str(uuid4()), "expectedRevision": 0},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"{path}/{cohort}/freeze",
                json={"idempotencyKey": str(uuid4()), "expectedRevision": 0},
                headers=headers,
            ).status_code
            == 422
        )
        assert len(calls) == count


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["selector"].update(importJobId=str(uuid4())),
        lambda b: b["selector"].update(sourceIds=[str(uuid4())] * 2),
        lambda b: b.update(recordings=b["recordings"] * 2),
        lambda b: b.update(recordings=[{"groupId": str(uuid4()), "role": "final_test"}]),
        lambda b: b.update(actor="spoof"),
        lambda b: b["selector"].update(sourceIds=[str(uuid4()) for _ in range(201)]),
        lambda b: b.update(selector={"importJobIds": [str(uuid4())]}),
        lambda b: b.update(selector={"importJobIds": [str(uuid4())] * 2}),
        lambda b: b.update(selector={"importJobIds": [str(uuid4()) for _ in range(51)]}),
        lambda b: b.update(
            selector={"importJobId": str(uuid4()), "importJobIds": [str(uuid4()), str(uuid4())]}
        ),
    ],
)
def test_closed_prepare_rejects_ambiguous_or_unbounded_inputs(change):
    body = prepare_body()
    change(body)
    with pytest.raises(ValidationError):
        GridCohortPrepareCommand.model_validate(body)


def test_prepare_accepts_several_named_imports_and_keeps_them_exact(tmp_path):
    game = uuid4()
    body = {**prepare_body(), "selector": {"importJobIds": [str(uuid4()), str(uuid4())]}}
    calls = []

    def prepare(*arguments):
        calls.append(arguments)
        raise RuntimeError("stop after the contract")

    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    service = SimpleNamespace(prepare=prepare)
    app.include_router(create_grid_training_cohorts_router(lambda: service), prefix="/api/v1")
    headers = {"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"}
    with TestClient(app, client=("127.0.0.1", 12345), raise_server_exceptions=False) as client:
        client.post(
            f"/api/v1/admin/games/{game}/grid-training-cohorts/prepare", json=body, headers=headers
        )
    assert calls[0][1]["selector"] == {
        "sourceIds": None,
        "importJobId": None,
        "importJobIds": body["selector"]["importJobIds"],
    }


def test_identity_completion_requires_one_to_five_exact_unique_pins():
    facts = {
        "qualification": "unresolved",
        "reasons": [],
        "manifestSha256": None,
        "humanLabelWithdrawn": None,
        "liveSourceLinked": None,
        "snapshotBytesAvailable": None,
    }
    assert GridCohortEligibility.model_validate(facts).model_dump() == facts
    for field in ("humanLabelWithdrawn", "liveSourceLinked", "snapshotBytesAvailable"):
        with pytest.raises(ValidationError):
            GridCohortEligibility.model_validate({k: v for k, v in facts.items() if k != field})
    preview = prepare_body()
    preview["recordings"] = []
    assert GridCohortPrepareCommand.model_validate(preview).recordings == []
    source = {
        "sourceId": str(uuid4()),
        "expectedSourceSha256": "a" * 64,
        "expectedSourceGeometryRevisionId": str(uuid4()),
        "expectedGeometrySha256": "b" * 64,
    }
    key = str(uuid4())
    assert (
        len(
            GridSourceIdentityCompleteCommand.model_validate(
                {"idempotencyKey": key, "sources": [source]}
            ).sources
        )
        == 1
    )
    for sources in (
        [],
        [source] * 2,
        [{**source, "sourceId": str(uuid4())} for _ in range(6)],
        [{**source, "path": "spoof"}],
    ):
        with pytest.raises(ValidationError):
            GridSourceIdentityCompleteCommand.model_validate(
                {"idempotencyKey": key, "sources": sources}
            )
