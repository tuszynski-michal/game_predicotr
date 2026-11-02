"""Apply reads are GET-only; mutations require intent and a closed confirmation command."""

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_correction_apply import create_grid_correction_apply_router
from game_predictor_api.schemas.grid_correction_apply import GridCorrectionApplyStartCommand
from pydantic import ValidationError
from test_grid_correction_learning_api import BASE, GAME, HEADERS, LEARNING, OTHER, app_for

PATH = f"/api/v1/admin/games/{GAME}/grid-correction-learning/{LEARNING}/apply"
APPLY = UUID(int=30)


class Service:
    def __init__(self):
        self.calls = []
        self.preview_result = {
            "gameId": str(GAME),
            "learningId": str(LEARNING),
            "versionId": str(OTHER),
            "versionLabel": "candidate",
            "baseVersionId": str(BASE),
            "defaultVersionId": str(BASE),
            "defaultRevision": 4,
            "additionalGameIds": [],
            "requiredGameIds": [str(GAME)],
            "targets": [
                {
                    "gameId": str(GAME),
                    "gameLabel": "A2",
                    "assignmentRevision": 2,
                    "assignedVersionId": str(BASE),
                    "requiresComparison": False,
                }
            ],
            "excludedGameIds": [],
            "limitations": ["Photo only."],
            "evidenceLevel": "photo-only",
            "blockers": [],
            "canApply": True,
            "previewSha256": "a" * 64,
        }
        self.view_result = {
            "applyId": str(APPLY),
            "gameId": str(GAME),
            "learningId": str(LEARNING),
            "versionId": str(OTHER),
            "status": "created",
            "stage": None,
            "errorCode": None,
            "steps": [{"kind": "publish", "gameId": None, "status": "pending"}],
            "createdAt": "now",
            "updatedAt": "now",
        }

    def preview(self, *args):
        self.calls.append(("preview", args))
        return deepcopy(self.preview_result)

    def list(self, *args):
        self.calls.append(("list", args))
        return {"items": [deepcopy(self.view_result)]}

    def get(self, *args):
        self.calls.append(("get", args))
        return deepcopy(self.view_result)

    def start(self, *args):
        self.calls.append(("start", args))
        return deepcopy(self.view_result)

    def resume(self, *args):
        self.calls.append(("resume", args))
        return deepcopy(self.view_result)


def command():
    return {
        "idempotencyKey": str(APPLY),
        "previewSha256": "a" * 64,
        "additionalGameIds": [],
        "confirmLimitedEvidence": True,
    }


def test_read_only_entry_query_and_explicit_mutations(tmp_path):
    service = Service()
    app = app_for(service, tmp_path)
    app.include_router(create_grid_correction_apply_router(lambda: service))
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert (
            client.get(PATH + "/preview", params=[("additionalGameIds", str(OTHER))]).status_code
            == 200
        )
        assert service.calls[-1] == ("preview", (GAME, LEARNING, [OTHER]))
        assert client.get(PATH).status_code == 200
        assert client.get(PATH + f"/{APPLY}").status_code == 200
        assert [call[0] for call in service.calls] == ["preview", "list", "get"]
        assert client.post(PATH, json=command()).status_code == 403
        assert client.post(PATH + f"/{APPLY}/resume").status_code == 403
        assert client.post(PATH, json=command(), headers=HEADERS).status_code == 200
        assert service.calls[-1] == ("start", (GAME, LEARNING, command(), "local-owner"))
        assert client.post(PATH + f"/{APPLY}/resume", headers=HEADERS).status_code == 200
        assert service.calls[-1] == ("resume", (GAME, LEARNING, APPLY, "local-owner"))


@pytest.mark.parametrize(
    "change",
    [
        {"baselineVersionId": str(BASE)},
        {"expectedRevision": 3},
        {"confirmLimitedEvidence": "true"},
        {"confirmLimitedEvidence": 1},
        {"additionalGameIds": [str(OTHER), str(OTHER)]},
    ],
)
def test_client_cannot_supply_evidence_revisions_or_coerce_confirmation(change):
    with pytest.raises(ValidationError):
        GridCorrectionApplyStartCommand.model_validate({**command(), **change})


def test_confirmation_field_is_required():
    body = command()
    del body["confirmLimitedEvidence"]
    with pytest.raises(ValidationError):
        GridCorrectionApplyStartCommand.model_validate(body)


def test_operation_ids_match_generated_client_contract(tmp_path):
    service = Service()
    app = app_for(service, tmp_path)
    app.include_router(create_grid_correction_apply_router(lambda: service))
    operations = {
        operation["operationId"]
        for path, methods in app.openapi()["paths"].items()
        if "/apply" in path
        for operation in methods.values()
    }
    assert operations == {
        "previewGridCorrectionApply",
        "startGridCorrectionApply",
        "listGridCorrectionApply",
        "getGridCorrectionApply",
        "resumeGridCorrectionApply",
    }
