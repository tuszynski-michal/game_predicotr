"""Correction-learning request contract and local-owner boundary, without worker or DB."""

from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_correction_learning import create_grid_correction_learning_router
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)

GAME, LEARNING, BASE, IMPORT, OTHER = (UUID(int=index) for index in range(1, 6))
PATH = f"/api/v1/admin/games/{GAME}/grid-correction-learning"
HEADERS = {"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"}


def preview_value() -> dict[str, Any]:
    return {
        "trainingMode": "grid-only",
        "detectorReadiness": None,
        "rescueVariant": None,
        "rescueRecipeSha256": None,
        "gameId": str(GAME),
        "baseVersionId": str(BASE),
        "baseManifestSha256": "a" * 64,
        "defaultRevision": 3,
        "importJobIds": [str(IMPORT)],
        "roleCounts": [
            {"role": role, "photos": 10, "boards": 30}
            for role in ("TRAIN", "VALIDATION", "REGRESSION")
        ],
        "dataAvailability": {
            "photos": 50,
            "boards": 150,
            "minimumPhotos": 20,
            "minimumBoards": 60,
            "photoDeficit": 0,
            "boardDeficit": 0,
            "splitStatus": "ready",
        },
        "bufferPhotos": 20,
        "progressCounts": None,
        "priorScopeDocumented": False,
        "priorGameIds": [],
        "historicalCohorts": [],
        "exclusions": [],
        "requiredGameIds": [str(GAME)],
        "presetId": "grid-corrections",
        "presetFingerprint": "b" * 64,
        "cost": {
            "trainItems": 30,
            "stepsPerEpoch": 3,
            "plannedTrainSeconds": 10.0,
            "plannedSteps": 6,
            "epochsPlanned": 2.0,
            "evaluationsPlanned": 2,
            "estimatedRunSeconds": 15.0,
            "withinBudget": True,
        },
        "blockers": [],
        "pendingWorkerChecks": ["GPU_RUNTIME"],
        "canStart": True,
        "evidenceLevel": "photo-only",
        "limitations": ["Session independence is unproven."],
        "previewSha256": "c" * 64,
    }


def view_value() -> dict[str, Any]:
    return {
        "learningId": str(LEARNING),
        "gameId": str(GAME),
        "status": "created",
        "stage": None,
        "baseVersionId": str(BASE),
        "defaultRevision": 3,
        "cohortId": None,
        "trainingRunId": None,
        "candidateVersionId": None,
        "evaluationId": None,
        "reportId": None,
        "verdict": None,
        "previewSha256": "c" * 64,
        "requiredGameIds": [str(GAME)],
        "exclusions": [],
        "cancelRequested": False,
        "errorCode": None,
        "createdAt": "2026-11-02T12:00:00Z",
        "updatedAt": "2026-11-02T12:00:00Z",
    }


def evaluation_value() -> dict[str, Any]:
    return {
        "evaluationId": str(UUID(int=10)),
        "reportId": str(UUID(int=11)),
        "status": "created",
        "stage": None,
        "versionId": str(UUID(int=12)),
        "baseVersionId": str(BASE),
        "trainingGameId": str(GAME),
        "cohorts": [{"gameId": str(GAME), "cohortId": str(UUID(int=13))}],
        "progressCurrent": 0,
        "progressTotal": 2,
        "verdict": None,
        "cancelRequested": False,
        "errorCode": None,
        "createdAt": "now",
        "updatedAt": "now",
        "report": None,
        "currentness": [],
        "assignedBaselineVersionId": None,
        "assignmentRevision": None,
    }


class Service:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.preview_result = preview_value()
        self.view_result = view_value()
        self.has_evaluation = True

    def ready(self, game: UUID, *, recommend_training_mode: bool = False) -> dict[str, Any]:
        self.calls.append(("ready", (game, True) if recommend_training_mode else (game,)))
        if recommend_training_mode:
            return {
                **deepcopy(self.preview_result),
                "trainingRecommendation": {
                    "mode": "grid-only",
                    "reasonCodes": ["GRID_LEARNING_RECOMMENDED_POINTS"],
                },
            }
        return deepcopy(self.preview_result)

    def preview(self, game: UUID, command: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("preview", (game, command)))
        return deepcopy(self.preview_result)

    def start(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        self.calls.append(("start", (game, command, actor)))
        return deepcopy(self.view_result)

    def get(self, game: UUID, learning: UUID) -> dict[str, Any]:
        self.calls.append(("get", (game, learning)))
        if learning != LEARNING:
            raise HTTPException(404, "Unknown learning run.")
        return deepcopy(self.view_result)

    def cancel(self, game: UUID, learning: UUID, actor: str) -> dict[str, Any]:
        self.calls.append(("cancel", (game, learning, actor)))
        return {**self.view_result, "cancelRequested": True}

    def resume(self, game: UUID, learning: UUID, actor: str) -> dict[str, Any]:
        self.calls.append(("resume", (game, learning, actor)))
        return deepcopy(self.view_result)

    def evaluation(self, game: UUID, learning: UUID) -> dict[str, Any]:
        self.calls.append(("evaluation", (game, learning)))
        if not self.has_evaluation:
            raise HTTPException(409, "The learning run has no evaluation yet.")
        return evaluation_value()

    def list(self, game: UUID) -> dict[str, Any]:
        self.calls.append(("list", (game,)))
        return {"items": [deepcopy(self.view_result)]}


def app_for(service: Service, tmp_path: Path, *, security: bool = True) -> FastAPI:
    app = FastAPI()
    if security:
        app.add_middleware(
            LocalAdminSecurityMiddleware,
            admin_origin="http://127.0.0.1:3000",
            reviewer_origin="http://127.0.0.1:3001",
            audit_log=AppendOnlyAdminAuditLog(tmp_path),
        )
    app.include_router(create_grid_correction_learning_router(lambda: service))
    return app


def start_body() -> dict[str, Any]:
    return {"idempotencyKey": str(UUID(int=20)), "previewSha256": "c" * 64}


def test_counted_learning_material_survives_blocked_readiness_http_without_role_mutation(tmp_path):
    service = Service()
    material = {
        "version": "effective-grid-learning-material-v1",
        "weights": {"corrected": 4, "good": 1},
        "roles": {
            "TRAIN": {
                "correctedBoards": 12,
                "goodBoards": 3,
                "unknownBoards": 0,
                "correctedPhotos": 2,
                "goodPhotos": 1,
                "unknownPhotos": 0,
                "photos": 2,
                "boards": 15,
                "photoCategoriesMayOverlap": True,
            }
        },
        "exclusions": [
            {
                "componentKey": "d" * 64,
                "sourceIds": [str(OTHER)],
                "importIds": [str(IMPORT)],
                "photos": 1,
                "labelledPhotos": 1,
                "boards": 9,
                "priorRoles": ["TRAIN", "VALIDATION"],
                "priorPurposes": [],
                "reasonCodes": ["GRID_CORRECTION_PROTECTION_CONFLICT"],
                "orderingMethods": {str(IMPORT): "indivisible-import-v1"},
            }
        ],
        "excludedPhotos": 1,
        "excludedBoards": 9,
        "availablePhotos": 2,
        "availableBoards": 15,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "minimumBasis": "geometry-three-role-lower-bounds",
        "photoDeficit": 18,
        "boardDeficit": 45,
        "deficitsAreLowerBounds": True,
        "historyModified": False,
    }
    service.preview_result.update(
        learningMaterial=deepcopy(material),
        canStart=False,
        blockers=["GRID_CORRECTION_TOO_FEW_DATA"],
    )
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.get(f"{PATH}/ready")
    assert response.status_code == 200
    assert response.json()["learningMaterial"] == material
    assert response.json()["canStart"] is False
    assert service.calls == [("ready", (GAME,))]


def test_infeasible_material_role_shortfalls_roundtrip_from_the_domain_report(tmp_path):
    # T2 attaches exact per-role deficits to an infeasible split; the closed public
    # schema must carry them instead of failing response validation.
    from game_predictor_api.domain.grid_correction_split import CorrectionRoleCount
    from game_predictor_api.domain.grid_learning_material import role_shortfalls

    service = Service()
    shortfalls = role_shortfalls(
        (
            CorrectionRoleCount("TRAIN", 159, 271),
            CorrectionRoleCount("VALIDATION", 4, 4),
            CorrectionRoleCount("REGRESSION", 13, 21),
        )
    )
    material = {
        "version": "effective-grid-learning-material-v1",
        "weights": {"corrected": 4, "good": 1},
        "roles": {},
        "exclusions": [],
        "excludedPhotos": 0,
        "excludedBoards": 0,
        "availablePhotos": 185,
        "availableBoards": 308,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "minimumBasis": "geometry-three-role-lower-bounds",
        "photoDeficit": 0,
        "boardDeficit": 0,
        "deficitsAreLowerBounds": True,
        "historyModified": False,
        "roleShortfalls": shortfalls,
    }
    service.preview_result.update(
        learningMaterial=deepcopy(material),
        canStart=False,
        blockers=["GRID_CORRECTION_SPLIT_INFEASIBLE"],
    )
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.get(f"{PATH}/ready")
    assert response.status_code == 200
    body = response.json()["learningMaterial"]
    assert body == material
    assert body["roleShortfalls"]["roles"]["VALIDATION"]["photoDeficit"] == 1


def test_recommended_ready_is_explicit_read_only_opt_in_and_roundtrips_reason(tmp_path):
    service = Service()
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        recommended = client.get(f"{PATH}/ready", params={"recommendTrainingMode": True})
        legacy = client.get(f"{PATH}/ready")
    assert recommended.status_code == 200
    assert recommended.json()["trainingRecommendation"] == {
        "mode": "grid-only",
        "reasonCodes": ["GRID_LEARNING_RECOMMENDED_POINTS"],
    }
    assert "trainingRecommendation" not in legacy.json()
    assert service.calls == [("ready", (GAME, True)), ("ready", (GAME,))]


def test_explicit_v4_pair_and_component_projection_roundtrip_without_persistence(tmp_path):
    service = Service()
    assignments = {str(IMPORT): "B"}
    service.preview_result.update(
        policyVersion="application-grid-corrections-v4",
        validationAssignments=assignments,
        validationComponents=[
            {
                "componentKey": "d" * 64,
                "sources": [
                    {
                        "sourceId": str(IMPORT),
                        "displayName": "462201-462209.jpg",
                        "rangeStart": 462201,
                        "rangeEnd": 462209,
                        "qualifiedBoards": 9,
                    }
                ],
                "priorRoles": ["VALIDATION"],
                "priorPurposes": [],
                "options": [{"purpose": "B", "allowed": True, "reasonCodes": []}],
            }
        ],
        validationPurposeCounts={
            "A": {"boards": 45, "photos": 5, "fullPhotos": 5},
            "B": {"boards": 9, "photos": 1, "fullPhotos": 1},
        },
    )
    body = {
        "trainingMode": "grid-only",
        "policyVersion": "application-grid-corrections-v4",
        "validationAssignments": assignments,
    }
    body["historicalCohorts"] = [
        {"gameId": str(OTHER), "cohortId": str(BASE), "manifestSha256": "e" * 64}
    ]
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.post(f"{PATH}/preview", json=body, headers=HEADERS)
        assert response.status_code == 200 and response.json() == service.preview_result
        assert service.calls[-1][0] == "preview"
        assert service.calls[-1][1][1]["validationAssignments"] == assignments
        assert service.calls[-1][1][1]["historicalCohorts"] == body["historicalCohorts"]
        assert (
            client.post(
                f"{PATH}/preview",
                json={"trainingMode": "grid-only", "historicalCohorts": body["historicalCohorts"]},
                headers=HEADERS,
            ).status_code
            == 422
        )
        assert not any(name == "start" for name, _ in service.calls)
        for invalid in (
            {"policyVersion": body["policyVersion"]},
            {"validationAssignments": assignments},
            {"policyVersion": body["policyVersion"], "validationAssignments": {}},
            {**body, "validationAssignments": {str(IMPORT): "TRAIN"}},
        ):
            assert client.post(f"{PATH}/preview", json=invalid, headers=HEADERS).status_code == 422
        started = client.post(PATH, json={**body, **start_body()}, headers=HEADERS)
        assert started.status_code == 200
        assert service.calls[-1][1][1]["policyVersion"] == body["policyVersion"]
        assert service.calls[-1][1][1]["trainingMode"] == "grid-only"


def test_screen_mode_variant_and_readiness_roundtrip_without_fallback(tmp_path: Path) -> None:
    service = Service()
    service.preview_result.update(
        trainingMode="screen+grid",
        canStart=False,
        blockers=["SCREEN_FULL_PHOTOS_REQUIRED"],
        detectorReadiness={
            "photos": 134,
            "fullPhotos": 0,
            "partialPhotos": 134,
            "partialExcludedFromDetector": 134,
            "roles": [],
            "reasonCodes": ["SCREEN_FULL_PHOTOS_REQUIRED"],
        },
    )
    selected = [
        {"gameId": str(UUID(int=101)), "cohortId": str(UUID(int=102)), "manifestSha256": "c" * 64}
    ]
    body = {
        "trainingMode": "screen+grid",
        "historicalCohorts": selected,
        "rescueVariant": {"board": {"margin": 0.2}},
    }
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.post(PATH + "/preview", json=body, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["trainingMode"] == "screen+grid"
        assert response.json()["canStart"] is False
        assert response.json()["detectorReadiness"]["fullPhotos"] == 0
        command = service.calls[-1][1][1]
        assert command["historicalCohorts"] == selected
        assert (
            command["trainingMode"] == "screen+grid"
            and command["rescueVariant"]["board"]["margin"] == 0.2
        )
        assert (
            client.post(
                PATH + "/preview", json={**body, "trainingMode": "grid-only"}, headers=HEADERS
            ).status_code
            == 422
        )


def test_assigned_comparison_route_resolves_baseline_only_on_server(tmp_path: Path) -> None:
    from game_predictor_api.api.grid_model_evaluations import create_grid_model_evaluations_router

    class Comparisons(Service):
        def create_assigned_comparison(self, command):
            self.calls.append(("assigned", (command,)))
            return {
                **evaluation_value(),
                "assignedBaselineVersionId": str(BASE),
                "assignmentRevision": 4,
            }

    service = Comparisons()
    app = app_for(service, tmp_path)
    app.include_router(create_grid_model_evaluations_router(lambda: service))
    body = {
        "idempotencyKey": str(LEARNING),
        "versionId": str(OTHER),
        "gameId": str(GAME),
        "cohortId": str(IMPORT),
    }
    path = "/api/v1/admin/grid-model-evaluations/assigned-comparison"
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.post(path, json=body).status_code == 403
        response = client.post(path, json=body, headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["assignedBaselineVersionId"] == str(BASE)
        assert (
            client.post(
                path, json={**body, "baselineVersionId": str(OTHER)}, headers=HEADERS
            ).status_code
            == 422
        )
    assert service.calls == [("assigned", (body,))]


def test_readiness_reload_is_get_only_and_nullable_readiness_roundtrips(tmp_path: Path) -> None:
    service = Service()
    service.preview_result.update(
        baseVersionId=None,
        baseManifestSha256=None,
        defaultRevision=None,
        cost=None,
        dataAvailability=None,
        canStart=False,
        blockers=["NO_DEFAULT"],
    )
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        assert client.get(f"{PATH}/ready").json() == service.preview_result
        assert client.get(f"{PATH}/ready").status_code == 200
    assert service.calls == [("ready", (GAME,)), ("ready", (GAME,))]


@pytest.mark.parametrize(
    "status,photos,boards,photo_deficit,board_deficit",
    [
        ("minima", 7, 21, 13, 39),
        ("infeasible", 40, 120, 0, 0),
    ],
)
def test_blocked_readiness_preserves_server_counts_without_inventing_roles(
    tmp_path, status, photos, boards, photo_deficit, board_deficit
):
    service = Service()
    counts = {
        "photos": photos,
        "boards": boards,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "photoDeficit": photo_deficit,
        "boardDeficit": board_deficit,
        "splitStatus": status,
    }
    service.preview_result.update(
        canStart=False,
        roleCounts=[],
        cost=None,
        dataAvailability=counts,
        blockers=["GRID_CORRECTION_SPLIT_" + status.upper()],
    )
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        for response in (
            client.get(f"{PATH}/ready"),
            client.post(f"{PATH}/preview", json={}, headers=HEADERS),
        ):
            assert response.status_code == 200
            assert response.json()["dataAvailability"] == counts
            assert response.json()["roleCounts"] == []
            assert response.json()["canStart"] is False


def test_full_request_contract_actor_and_read_routes(tmp_path: Path) -> None:
    service = Service()
    command = {
        "importJobIds": [str(IMPORT)],
        "exclusions": [{"gameId": str(OTHER), "reason": "Labels withdrawn", "confirmed": True}],
    }
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        response = client.post(f"{PATH}/preview", json=command, headers=HEADERS)
        assert response.status_code == 200 and response.json() == preview_value()
        assert service.calls[-1] == (
            "preview",
            (
                GAME,
                {
                    **command,
                    "trainingMode": "grid-only",
                    "rescueVariant": None,
                    "historicalCohorts": [],
                },
            ),
        )
        response = client.post(PATH, json=start_body(), headers=HEADERS)
        assert response.status_code == 200 and response.json() == view_value()
        assert service.calls[-1] == (
            "start",
            (
                GAME,
                {
                    **start_body(),
                    "importJobIds": [],
                    "exclusions": [],
                    "trainingMode": "grid-only",
                    "rescueVariant": None,
                    "historicalCohorts": [],
                },
                "local-owner",
            ),
        )
        assert client.get(PATH).json() == {"items": [view_value()]}
        assert client.get(f"{PATH}/{LEARNING}").json() == view_value()
        assert client.get(f"{PATH}/{UUID(int=99)}").status_code == 404
        assert client.get(f"{PATH}/{LEARNING}/evaluation").json() == evaluation_value()
        service.has_evaluation = False
        assert client.get(f"{PATH}/{LEARNING}/evaluation").status_code == 409
        response = client.post(f"{PATH}/{LEARNING}/cancel", headers=HEADERS)
        assert response.status_code == 200 and response.json()["cancelRequested"] is True
        assert service.calls[-1] == ("cancel", (GAME, LEARNING, "local-owner"))
        assert client.post(f"{PATH}/{LEARNING}/resume", headers=HEADERS).json() == view_value()
        assert service.calls[-1] == ("resume", (GAME, LEARNING, "local-owner"))


def test_exclusion_order_is_canonical_for_preview_start_and_evaluation_http(tmp_path):
    from game_predictor_api.api.grid_model_evaluations import create_grid_model_evaluations_router
    from game_predictor_api.domain.grid_model_registry import descriptor_sha256

    class Canonical(Service):
        def preview(self, game, command):
            result = super().preview(game, command)
            result["previewSha256"] = descriptor_sha256(command)
            return result

        def create(self, command):
            self.calls.append(("evaluation", (command,)))
            return evaluation_value()

    service = Canonical()
    app = app_for(service, tmp_path)
    app.include_router(create_grid_model_evaluations_router(lambda: service))
    exclusions = [
        {"gameId": str(UUID(int=i)), "reason": "Unavailable labels", "confirmed": True}
        for i in (10, 11)
    ]
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        hashes = []
        for values in (exclusions, list(reversed(exclusions))):
            response = client.post(f"{PATH}/preview", json={"exclusions": values}, headers=HEADERS)
            assert response.status_code == 200
            hashes.append(response.json()["previewSha256"])
            assert service.calls[-1][1][1]["exclusions"] == exclusions
            assert (
                client.post(
                    PATH, json={**start_body(), "exclusions": values}, headers=HEADERS
                ).status_code
                == 200
            )
            assert service.calls[-1][1][1]["exclusions"] == exclusions
            response = client.post(
                "/api/v1/admin/grid-model-evaluations",
                headers=HEADERS,
                json={
                    "idempotencyKey": str(LEARNING),
                    "versionId": str(BASE),
                    "cohorts": [{"gameId": str(GAME), "cohortId": str(IMPORT)}],
                    "exclusions": values,
                },
            )
            assert response.status_code == 200
            assert service.calls[-1][1][0]["exclusions"] == exclusions
        assert hashes[0] == hashes[1]


@pytest.mark.parametrize(
    "suffix,body",
    [
        ("/preview", {}),
        ("", start_body()),
        (f"/{LEARNING}/cancel", None),
        (f"/{LEARNING}/resume", None),
    ],
)
@pytest.mark.parametrize("security", [True, False])
def test_every_post_rejects_unvalidated_actor_before_service(
    tmp_path: Path, suffix: str, body: Any, security: bool
) -> None:
    service = Service()
    with TestClient(
        app_for(service, tmp_path, security=security), client=("127.0.0.1", 12345)
    ) as client:
        # Headers alone cannot synthesize middleware state when middleware is absent.
        headers = HEADERS if not security else {}
        assert client.post(f"{PATH}{suffix}", json=body, headers=headers).status_code == 403
    assert service.calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"actor": "local-owner"},
        {"importJobIds": [str(IMPORT)] * 2},
        {"importJobIds": [str(UUID(int=index + 100)) for index in range(101)]},
        {"importJobIds": ["invalid"]},
        {"importJobIds": None},
        {"exclusions": [{"gameId": str(OTHER), "reason": " ", "confirmed": True}]},
        {"exclusions": [{"gameId": str(OTHER), "reason": "a" * 501, "confirmed": True}]},
        {"exclusions": [{"gameId": str(OTHER), "reason": "x", "confirmed": "true"}]},
        {"exclusions": [{"gameId": str(OTHER), "reason": "x", "confirmed": True, "extra": 1}]},
        {"exclusions": [{"gameId": str(OTHER), "reason": "x", "confirmed": True}] * 2},
    ],
)
def test_preview_rejects_unknown_ambiguous_or_unbounded_commands(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    service = Service()
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        assert client.post(f"{PATH}/preview", json=change, headers=HEADERS).status_code == 422
    assert service.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"idempotencyKey": str(UUID(int=20))},
        {**start_body(), "previewSha256": "C" * 64},
        {**start_body(), "previewSha256": "c" * 63},
        {**start_body(), "idempotencyKey": "invalid"},
        {**start_body(), "versionId": str(BASE)},
    ],
)
def test_start_requires_exact_idempotency_and_preview_pin(
    tmp_path: Path, body: dict[str, Any]
) -> None:
    service = Service()
    with TestClient(app_for(service, tmp_path), client=("127.0.0.1", 12345)) as client:
        assert client.post(PATH, json=body, headers=HEADERS).status_code == 422
    assert service.calls == []


def test_openapi_has_eight_operations_and_closed_preview_view_schemas(tmp_path: Path) -> None:
    document = app_for(Service(), tmp_path).openapi()
    operations = {
        operation["operationId"]
        for path in document["paths"].values()
        for operation in path.values()
    }
    assert operations == {
        "getGridCorrectionLearningReady",
        "previewGridCorrectionLearning",
        "startGridCorrectionLearning",
        "listGridCorrectionLearning",
        "getGridCorrectionLearning",
        "cancelGridCorrectionLearning",
        "resumeGridCorrectionLearning",
        "getGridCorrectionLearningEvaluation",
    }
    schemas = document["components"]["schemas"]
    for name, expected in [
        ("GridCorrectionLearningPreview", preview_value()),
        ("GridCorrectionLearningView", view_value()),
    ]:
        assert schemas[name]["additionalProperties"] is False
        assert set(schemas[name]["properties"]) == set(expected) | (
            {
                "policyVersion",
                "validationAssignments",
                "validationComponents",
                "validationPurposeCounts",
                "contentExperiment",
                "contentExperimentReadiness",
                "trainingRecommendation",
                "partialTrainingPhotos",
                "learningMaterial",
                "testSample",
            }
            if name == "GridCorrectionLearningPreview"
            else {"contentExperiment", "contentExperimentPlanSha256"}
        )
        assert set(schemas[name]["required"]) == set(expected) - {
            "progressCounts",
            "trainingMode",
            "rescueVariant",
            "rescueRecipeSha256",
            "detectorReadiness",
        }
    assert (
        schemas["GridCorrectionLearningPreviewCommand"]["properties"]["importJobIds"]["maxItems"]
        == 100
    )
    assert (
        schemas["GridCorrectionLearningStartCommand"]["properties"]["previewSha256"]["pattern"]
        == r"^[0-9a-f]{64}$"
    )
