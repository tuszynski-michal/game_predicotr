"""Opt-in policy is carried by the existing HTTP path; old requests stay exact."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_training_cohorts import create_grid_training_cohorts_router
from game_predictor_api.domain.grid_training_cohorts import require_minima, role_summary
from game_predictor_api.schemas.grid_training_cohorts import GridCohortPrepareCommand
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)
from game_predictor_api.storage.grid_correction_split import CORRECTIONS_POLICY, split_mapping
from pydantic import ValidationError


def body():
    return {
        "idempotencyKey": str(uuid4()),
        "mode": "grid-only",
        "familyId": str(uuid4()),
        "baseVersionId": str(uuid4()),
        "selector": {"importJobId": str(uuid4())},
        "recordings": [],
        "policyVersion": CORRECTIONS_POLICY,
    }


def test_correction_request_preserves_explicit_policy_and_scoped_existing_route(tmp_path):
    calls = []

    def prepare(*args):
        calls.append(args)
        raise RuntimeError("request captured")

    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    app.include_router(
        create_grid_training_cohorts_router(lambda: SimpleNamespace(prepare=prepare)),
        prefix="/api/v1",
    )
    game = uuid4()
    with TestClient(app, client=("127.0.0.1", 1000), raise_server_exceptions=False) as client:
        client.post(
            f"/api/v1/admin/games/{game}/grid-training-cohorts/prepare",
            json=body(),
            headers={"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"},
        )
    assert calls[0][0] == game
    assert calls[0][1]["policyVersion"] == CORRECTIONS_POLICY
    assert calls[0][2] == "local-owner"


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "screen+grid"},
        {"recordings": [{"groupId": str(uuid4()), "role": "TRAIN"}]},
        {"selector": {"sourceIds": [str(uuid4())]}},
    ],
)
def test_correction_policy_refuses_partial_import_selection_and_manual_roles(change):
    with pytest.raises(ValidationError):
        GridCohortPrepareCommand.model_validate({**body(), **change})


def test_partial_control_minima_are_versioned_and_buffer_alias_copies_never_count():
    members = [
        {
            "used": True,
            "role": role,
            "boardEligibleCount": 3,
            "screenEligible": False,
            "recording": {
                "qualification": "eligible",
                "groupId": None,
                "photoIdentity": str(index),
            },
        }
        for role, count in (("TRAIN", 10), ("VALIDATION", 5), ("REGRESSION", 5))
        for index in range(count)
    ]
    current = role_summary("grid-only", members, policy=CORRECTIONS_POLICY)
    require_minima(current)
    legacy = role_summary("grid-only", members)
    assert [r["missingFullPhotos"] for r in legacy["roles"]] == [0, 5, 5]
    mapped = split_mapping(
        {
            "sha256": "a" * 64,
            "sources": [
                {
                    "eligibleBoards": 0,
                    "sourceId": "buffer",
                    "sourceSha256": "b" * 64,
                    "role": None,
                    "buffer": True,
                    "representative": True,
                },
                {
                    "eligibleBoards": 3,
                    "sourceId": "alias",
                    "sourceSha256": "c" * 64,
                    "role": "TRAIN",
                    "buffer": False,
                    "representative": False,
                },
            ],
        }
    )
    assert all(m["qualification"] == "blocked" for m in mapped.values())
    assert mapped["buffer"]["reasonCodes"] == ["GRID_CORRECTION_BUFFER"]
    assert mapped["alias"]["reasonCodes"] == ["GRID_CORRECTION_EXACT_ALIAS"]


def test_shared_candidate_rejects_correction_policy_before_creating_plan(tmp_path, monkeypatch):
    from game_predictor_api.application.shared_grid_model_candidate import (
        SharedGridCandidateService,
    )
    from game_predictor_api.domain.grid_training_cohorts import GridCohortError

    service = SharedGridCandidateService(None, tmp_path)
    monkeypatch.setattr(
        service,
        "_cohort",
        lambda *args: (
            {"policyVersion": CORRECTIONS_POLICY, "status": "frozen"},
            {"qualification": "eligible"},
            {},
        ),
    )
    with pytest.raises(GridCohortError) as error:
        service.prepare(uuid4(), uuid4(), [(uuid4(), uuid4())])
    assert error.value.code == "GRID_RUN_POLICY_UNSUPPORTED"
