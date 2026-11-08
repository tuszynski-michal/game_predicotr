"""The opt-in uses the existing actor-guarded correction command, never client proofs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_grid_correction_learning_api import HEADERS, PATH, Service, app_for, start_body

VERSION = "full-symbol-content-experiment-v1"


def test_registered_auxiliary_graph_roundtrips_through_existing_http_contract():
    from copy import deepcopy
    from uuid import uuid4

    from fastapi import FastAPI
    from game_predictor_api.api.grid_model_registry import create_grid_model_registry_router
    from game_predictor_api.domain.grid_model_registry import (
        historical_catalogue,
        validate_manifest,
    )

    payload = deepcopy(historical_catalogue()[0])
    payload.update(
        modelVersion="neural-grid-v2",
        bundleFormat="neural-grid-bundle-v2",
        admission="not_evaluated",
        baseVersionId=payload["versionId"],
    )
    payload["files"].append({"name": "content.onnx", "sha256": "f" * 64, "sizeBytes": 123})
    payload["inferenceManifest"].update(
        modelVersion=payload["modelVersion"],
        bundleFormat=payload["bundleFormat"],
        files=payload["files"],
    )
    validate_manifest(payload)
    captured = []

    class Registry:
        def register(self, key, manifest):
            captured.append(manifest)
            return {
                "manifest": manifest,
                "manifestSha256": "a" * 64,
                "available": True,
                "reasonCode": "TRANSPORT_FIXTURE_ONLY",
            }

    app = FastAPI()
    app.include_router(create_grid_model_registry_router(lambda: Registry()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/grid-model-versions",
            json={"idempotencyKey": str(uuid4()), "manifest": payload},
        )
    assert response.status_code == 200, response.text
    assert (
        captured == [payload] and response.json()["manifest"]["files"][-1]["name"] == "content.onnx"
    )


def command() -> dict:
    return {
        "contentExperiment": VERSION,
        "trainingMode": "screen+grid",
        "policyVersion": "application-grid-corrections-v4",
        "validationAssignments": {},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("trainingMode", "grid-only"),
        ("policyVersion", None),
        ("validationAssignments", None),
        ("contentExperiment", "future"),
        ("contentExperimentInputs", {}),
        ("contentExperimentPlanSha256", "a" * 64),
    ],
)
def test_invalid_or_client_supplied_experiment_proof_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    service = Service()
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.post(f"{PATH}/preview", json={**command(), field: value}, headers=HEADERS)
    assert response.status_code == 422
    assert service.calls == []


def test_preview_start_and_retry_retain_exact_experiment_token(tmp_path: Path) -> None:
    service = Service()
    readiness = {
        "state": "blocked",
        "reasonCodes": ["CONTENT_BANK_ANCESTRY_UNRESOLVED"],
        "games": [],
        "inputsSha256": None,
    }
    service.preview_result.update(contentExperiment=VERSION, contentExperimentReadiness=readiness)
    service.view_result.update(contentExperiment=VERSION)
    body = {**command(), **start_body()}
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        preview = client.post(f"{PATH}/preview", json=command(), headers=HEADERS)
        assert preview.status_code == 200
        assert (
            preview.json()["contentExperimentReadiness"]["automaticQualification"]
            == "not_evaluated"
        )
        assert preview.json()["contentExperimentReadiness"]["bankMeasurement"] == "pending_worker"
        for _ in range(2):
            result = client.post(PATH, json=body, headers=HEADERS)
            assert result.status_code == 200
            assert result.json()["contentExperiment"] == VERSION
    assert service.calls[-1][1][1] == service.calls[-2][1][1]
    assert service.calls[-1][1][1]["contentExperiment"] == VERSION


def test_legacy_request_does_not_gain_experiment_defaults(tmp_path: Path) -> None:
    service = Service()
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.post(f"{PATH}/preview", json={}, headers=HEADERS)
    assert response.status_code == 200
    assert "contentExperiment" not in service.calls[-1][1][1]
    assert "contentExperiment" not in response.json()
