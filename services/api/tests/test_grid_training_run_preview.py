"""TASK-1005: read-only run preview of a frozen geometry cohort."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_training_cohorts import create_grid_training_cohorts_router
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.schemas.grid_training_cohorts import GridTrainingRunPreview
from game_predictor_worker.training_core.gpu_lease import GpuLease, lease_path
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_ONLY_V1,
    SCREEN_GRID_V1,
)


def role(name, boards, photos, full):
    return {
        "role": name,
        "requiredBoards": 30 if name == "TRAIN" else 15,
        "requiredPhotos": 10 if name == "TRAIN" else 5,
        "requiredFullPhotos": 0,
        "eligibleBoards": boards,
        "eligiblePhotos": photos,
        "eligibleFullPhotos": full,
        "materializedBoards": boards,
        "materializedPhotos": photos,
        "materializedFullPhotos": full,
        "missingBoards": 0,
        "missingPhotos": 0,
        "missingFullPhotos": 0,
        "recordingRequired": True,
    }


def header(game, cohort, *, status="frozen", mode="grid-only", train=(30, 10, 0)):
    return {
        "id": str(cohort),
        "gameId": str(game),
        "revision": 4,
        "status": status,
        "mode": mode,
        "familyId": str(uuid4()),
        "baseVersionId": str(uuid4()),
        "previewSha256": "a" * 64,
        "manifestSha256": "b" * 64 if status == "frozen" else None,
        "summary": {
            "roles": [
                role("TRAIN", *train),
                role("VALIDATION", 45, 5, 5),
                role("REGRESSION", 45, 5, 5),
            ],
            "reasonCounts": {},
        },
        "nextCaptureCursor": None,
        "nextMaterializationCursor": None,
        "createdAt": "2026-10-16T00:00:00+00:00",
    }


def service(tmp_path: Path, head, qualification="eligible", reasons=()):
    value = GridTrainingCohortService.__new__(GridTrainingCohortService)
    value.artifact_root = tmp_path
    calls = []

    def get(game, cohort):
        calls.append(("get", game, cohort))
        return head

    def eligibility(game, cohort):
        calls.append(("eligibility", game, cohort))
        return {"qualification": qualification, "reasons": list(reasons)}

    value.get = get  # type: ignore[method-assign]
    value.eligibility = eligibility  # type: ignore[method-assign]
    return value, calls


def test_frozen_qualified_grid_only_cohort_has_cost_and_only_pending_worker_checks(tmp_path):
    game, cohort = uuid4(), uuid4()
    value, calls = service(tmp_path, header(game, cohort))
    preview = GridTrainingRunPreview.model_validate(value.run_preview(game, cohort))
    assert preview.apiBlockers == []
    assert preview.selectedPresetId == "grid-only-v1"
    assert {p.presetId: p.fingerprint for p in preview.presets} == {
        "grid-only-v1": GRID_ONLY_V1.fingerprint,
        "screen-grid-v1": SCREEN_GRID_V1.fingerprint,
    }
    assert preview.cost is not None
    assert (preview.cost.trainItems, preview.cost.plannedTrainSeconds) == (30, 600.0)
    assert preview.cost.withinBudget
    assert preview.pendingWorkerChecks == [
        "GPU_AVAILABLE",
        "RUNTIME_COMPATIBLE",
        "VRAM_SUFFICIENT",
        "GPU_LEASE_FREE",
        "BUDGET_AVAILABLE",
    ]
    assert preview.lease.state == "free" and preview.lease.runKind is None
    assert preview.smoke.maxSteps == 50 and preview.smoke.trainSeconds == 120.0
    assert [name for name, *_ in calls] == ["get", "eligibility"]
    assert not lease_path(tmp_path).exists()  # a GET never creates the lease


def test_unfrozen_unqualified_empty_cohort_lists_every_api_blocker(tmp_path):
    game, cohort = uuid4(), uuid4()
    head = header(game, cohort, status="preview_ready", train=(0, 0, 0))
    value, _ = service(tmp_path, head, "blocked", ["SOURCE_REMOVED_NEW_USE_BLOCKED"])
    preview = value.run_preview(game, cohort)
    assert preview["apiBlockers"] == [
        "GRID_RUN_COHORT_NOT_FROZEN",
        "GRID_RUN_COHORT_NOT_QUALIFIED",
        "GRID_RUN_COHORT_EMPTY",
    ]
    assert preview["cohortReasons"] == ["SOURCE_REMOVED_NEW_USE_BLOCKED"]


def test_screen_cohort_uses_the_screen_preset_and_full_photos(tmp_path):
    game, cohort = uuid4(), uuid4()
    value, _ = service(tmp_path, header(game, cohort, mode="screen+grid", train=(99, 11, 11)))
    preview = value.run_preview(game, cohort)
    assert preview["selectedPresetId"] == "screen-grid-v1"
    assert preview["cost"]["trainItems"] == 11


def test_held_or_unreadable_lease_blocks_without_exposing_its_owner(tmp_path):
    game, cohort = uuid4(), uuid4()
    value, _ = service(tmp_path, header(game, cohort))
    lease = GpuLease(lease_path(tmp_path), probe=lambda pid: "created")
    record = lease.acquire("train", "run-1", pid=41, created="created")
    preview = GridTrainingRunPreview.model_validate(value.run_preview(game, cohort))
    assert preview.apiBlockers == ["GRID_RUN_LEASE_BUSY"]
    assert preview.lease.model_dump() == {"state": "held", "runKind": "train"}
    lease.release(record)
    lease_path(tmp_path).write_text("not json", encoding="utf-8")
    assert value.run_preview(game, cohort)["apiBlockers"] == ["GRID_RUN_LEASE_UNKNOWN"]
    lease_path(tmp_path).unlink()
    record = lease.acquire("train", "run-2", pid=41, created="created")
    stored = json.loads(lease_path(tmp_path).read_text(encoding="utf-8"))
    lease_path(tmp_path).write_text(json.dumps({**stored, "expires_at": None}), encoding="utf-8")
    preview = GridTrainingRunPreview.model_validate(value.run_preview(game, cohort))
    assert preview.apiBlockers == ["GRID_RUN_LEASE_UNKNOWN"]
    assert preview.lease.model_dump() == {"state": "unknown", "runKind": None}


def test_http_route_is_a_get_that_validates_the_closed_response(tmp_path):
    game, cohort = uuid4(), uuid4()
    real, _ = service(tmp_path, header(game, cohort))
    calls = []

    def run_preview(*arguments):
        calls.append(arguments)
        return real.run_preview(*arguments)

    fake = SimpleNamespace(run_preview=run_preview)
    application = FastAPI()
    application.include_router(create_grid_training_cohorts_router(lambda: fake), prefix="/api/v1")
    client = TestClient(application)
    path = f"/api/v1/admin/games/{game}/grid-training-cohorts/{cohort}/run-preview"
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["selectedPresetId"] == "grid-only-v1"
    assert calls == [(game, cohort)]
    assert client.post(path).status_code == 405
    operation = application.openapi()["paths"][
        "/api/v1/admin/games/{game_id}/grid-training-cohorts/{cohort_id}/run-preview"
    ]
    assert set(operation) == {"get"}
    assert operation["get"]["operationId"] == "previewGridTrainingRun"
