"""TASK-1047 (D-562): HTTP contract of source crop and original-deletion runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.source_crop_runs import (
    SourceCropRun,
    SourceCropRunKind,
    SourceCropRunService,
    SourceCropScope,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobConflictError, JobNotFoundError
from game_predictor_api.main import create_app
from game_predictor_api.security.local_admin import match_high_impact_operation

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ROOT = "/api/v1/admin/image-storage"
SHA_A = "a" * 64


class MemoryRuns:
    """Mirrors SqlAlchemySourceCropRunRepository's API-side rules."""

    def __init__(self) -> None:
        self.runs: dict[UUID, SourceCropRun] = {}

    def create_planning_run(
        self, *, run_id: UUID, kind: SourceCropRunKind, scope: SourceCropScope
    ) -> SourceCropRun:
        if any(
            run.status in ("planning", "previewed", "created", "processing")
            for run in self.runs.values()
        ):
            raise JobConflictError("SOURCE_CROP_RUN_ACTIVE", "Another source crop run is active.")
        run = SourceCropRun(
            id=run_id,
            kind=kind,
            status="planning",
            scope=scope,
            plan_job_id=uuid4(),
            job_id=None,
            manifest_checksum_sha256=None,
            preview_token=None,
            eligible_count=0,
            excluded_count=0,
            exclusion_counts={},
            candidate_bytes=0,
            estimated_saved_bytes=0,
            processed_count=0,
            succeeded_count=0,
            skipped_count=0,
            failed_count=0,
            saved_bytes=0,
            checkpoint_index=0,
            outcome_counts={},
            created_at=NOW,
            updated_at=NOW,
        )
        self.runs[run_id] = run
        return run

    def preview(self, run_id: UUID) -> SourceCropRun:
        run = replace(
            self.runs[run_id],
            status="previewed",
            manifest_checksum_sha256="c" * 64,
            preview_token="d" * 64,
            eligible_count=3,
            excluded_count=2,
            exclusion_counts={"GRID_ISSUE": 2},
            candidate_bytes=3000,
            estimated_saved_bytes=2000,
        )
        self.runs[run_id] = run
        return run

    def start_run(
        self,
        *,
        run_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_preview_token: str,
    ) -> SourceCropRun:
        run = self.get_run(run_id)
        if (
            run.manifest_checksum_sha256 != expected_manifest_checksum_sha256
            or run.preview_token != expected_preview_token
        ):
            raise JobConflictError("SOURCE_CROP_PREVIEW_STALE", "The preview is stale.")
        if run.job_id is not None:
            return run
        run = replace(run, status="created", job_id=uuid4())
        self.runs[run_id] = run
        return run

    def get_run(self, run_id: UUID) -> SourceCropRun:
        if run_id not in self.runs:
            raise JobNotFoundError(
                "SOURCE_CROP_RUN_NOT_FOUND", "The source crop run does not exist."
            )
        return self.runs[run_id]

    def list_runs(self, *, limit: int) -> Sequence[SourceCropRun]:
        return list(self.runs.values())[:limit]


@pytest.fixture
def repository() -> MemoryRuns:
    return MemoryRuns()


@pytest.fixture
def client(tmp_path: Path, repository: MemoryRuns) -> TestClient:
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)})
    service = SourceCropRunService(repository)
    return TestClient(create_app(settings, source_crop_service_dependency=lambda: service))


def _start_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "manifestChecksumSha256": "c" * 64,
        "previewToken": "d" * 64,
        "confirmed": True,
    }
    body.update(overrides)
    return body


def test_preview_start_get_and_list(client: TestClient, repository: MemoryRuns) -> None:
    with client:
        created = client.post(
            f"{ROOT}/source-crop-previews",
            json={"scope": {"gameId": None, "onlyChecksums": [SHA_A], "limit": 10}},
        )
        assert created.status_code == 201, created.text
        run_id = UUID(created.json()["id"])
        assert created.json()["status"] == "planning"
        assert created.json()["kind"] == "crop"
        assert created.json()["scope"]["onlyChecksums"] == [SHA_A]
        repository.preview(run_id)

        previewed = client.get(f"{ROOT}/source-crop-runs/{run_id}")
        started = client.post(f"{ROOT}/source-crop-previews/{run_id}/start", json=_start_body())
        again = client.post(f"{ROOT}/source-crop-previews/{run_id}/start", json=_start_body())
        listed = client.get(f"{ROOT}/source-crop-runs", params={"limit": 5})

    assert previewed.json()["previewToken"] == "d" * 64
    assert previewed.json()["exclusionCounts"] == {"GRID_ISSUE": 2}
    assert previewed.json()["estimatedSavedBytes"] == 2000
    assert started.status_code == 201
    assert started.json()["status"] == "created" and started.json()["jobId"] is not None
    assert again.json()["jobId"] == started.json()["jobId"]
    assert [run["id"] for run in listed.json()["runs"]] == [str(run_id)]


def test_start_requires_confirmation_and_a_current_preview(
    client: TestClient, repository: MemoryRuns
) -> None:
    with client:
        run_id = UUID(client.post(f"{ROOT}/source-crop-previews", json={}).json()["id"])
        repository.preview(run_id)
        unconfirmed = client.post(
            f"{ROOT}/source-crop-previews/{run_id}/start", json=_start_body(confirmed=False)
        )
        stale = client.post(
            f"{ROOT}/source-crop-previews/{run_id}/start",
            json=_start_body(previewToken="e" * 64),
        )
        unknown = client.get(f"{ROOT}/source-crop-runs/{uuid4()}")

    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["code"] == "SOURCE_CROP_CONFIRMATION_REQUIRED"
    assert stale.status_code == 409 and stale.json()["code"] == "SOURCE_CROP_PREVIEW_STALE"
    assert unknown.status_code == 404 and unknown.json()["code"] == "SOURCE_CROP_RUN_NOT_FOUND"
    assert repository.runs[run_id].job_id is None


def test_only_one_run_is_active(client: TestClient) -> None:
    with client:
        first = client.post(f"{ROOT}/source-crop-previews", json={})
        second = client.post(f"{ROOT}/source-crop-previews", json={"kind": "crop"})

    assert first.status_code == 201
    assert second.status_code == 409 and second.json()["code"] == "SOURCE_CROP_RUN_ACTIVE"


def test_original_deletion_previews_are_refused_until_a_handler_exists(
    client: TestClient, repository: MemoryRuns
) -> None:
    with client:
        refused = client.post(f"{ROOT}/source-crop-previews", json={"kind": "original_deletion"})
    assert refused.status_code == 409
    assert refused.json()["code"] == "SOURCE_CROP_KIND_UNSUPPORTED"
    assert repository.runs == {}


def test_original_deletion_needs_an_irreversibility_acknowledgement(
    client: TestClient, repository: MemoryRuns
) -> None:
    # Created directly: the HTTP preview of this kind waits for its handler.
    run = repository.create_planning_run(
        run_id=uuid4(), kind="original_deletion", scope=SourceCropScope()
    )
    repository.preview(run.id)
    with client:
        refused = client.post(f"{ROOT}/source-crop-previews/{run.id}/start", json=_start_body())
        accepted = client.post(
            f"{ROOT}/source-crop-previews/{run.id}/start",
            json=_start_body(acknowledgeIrreversible=True),
        )

    assert refused.status_code == 409
    assert refused.json()["code"] == "SOURCE_ORIGINAL_DELETION_ACKNOWLEDGEMENT_REQUIRED"
    assert accepted.status_code == 201


@pytest.mark.parametrize(
    "scope",
    [
        {"onlyChecksums": ["A" * 64]},
        {"onlyChecksums": [SHA_A, SHA_A]},
        {"onlyChecksums": []},
        {"limit": 0},
    ],
)
def test_invalid_scopes_are_refused(client: TestClient, scope: dict[str, object]) -> None:
    with client:
        response = client.post(f"{ROOT}/source-crop-previews", json={"scope": scope})
    assert response.status_code in (409, 422)


def test_start_is_a_confirmed_high_impact_operation() -> None:
    preview = uuid4()
    operation, target = match_high_impact_operation(
        "POST", f"{ROOT}/source-crop-previews/{preview}/start"
    )
    assert operation is not None and operation.action == "start-source-crop-run"
    assert target == f"source-crop-preview:{preview}"
    assert match_high_impact_operation("POST", f"{ROOT}/source-crop-previews") == (None, None)


def test_openapi_publishes_the_start_target_headers(client: TestClient) -> None:
    with client:
        schema = client.get("/openapi.json").json()
    operation = schema["paths"][f"{ROOT}/source-crop-previews/{{preview_id}}/start"]["post"]
    headers = {item["name"] for item in operation["parameters"] if item["in"] == "header"}
    assert {"X-Admin-Confirmation", "X-Admin-Target"} <= headers
