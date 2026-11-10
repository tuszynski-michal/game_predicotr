"""Persisted readability jobs must not be decoded as Android builds."""

from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.schemas.jobs import JobResponse
from pydantic import ValidationError
from test_jobs_api import _client


@pytest.mark.parametrize(
    ("action", "status"),
    [("prepare", JobStatus.FAILED), ("fit", JobStatus.PROCESSING), ("scan", JobStatus.COMPLETED)],
)
def test_mixed_jobs_and_details_preserve_readability_payload_progress_and_error(
    tmp_path, action, status
):
    client, game, _, repository = _client(tmp_path)
    identifier, release = uuid4(), uuid4()
    job = replace(
        create_job(
            JobType.SYMBOL_READABILITY,
            game_id=game,
            input_payload={
                "schema_version": 1,
                "workflow": "symbol_readability",
                "action": action,
                "identifier": str(identifier),
            },
        ),
        status=status,
        progress_current=7,
        progress_total=15,
        success_count=3,
        failure_count=2,
        review_count=2,
        stage="symbol_readability_" + action,
        error_code="JOB_EXECUTION_FAILED" if status is JobStatus.FAILED else None,
        error_message="OperationalError" if status is JobStatus.FAILED else None,
    )
    repository.add_job(job)
    android = repository.add_job(
        create_job(
            JobType.ANDROID_BUILD,
            game_id=game,
            input_payload={"schema_version": 1, "mobile_release_id": str(release)},
        )
    )
    with client:
        listing = client.get("/api/v1/admin/jobs", params={"game_id": str(game), "limit": 10})
        detail = client.get(f"/api/v1/admin/jobs/{job.id}")
        android_detail = client.get(f"/api/v1/admin/jobs/{android.id}")
    assert listing.status_code == detail.status_code == android_detail.status_code == 200
    by_id = {row["id"]: row for row in listing.json()}
    value = detail.json()
    assert by_id[str(job.id)] == value
    assert len(by_id) == 2
    assert value["jobType"] == "symbol_readability"
    assert value["status"] == status.value
    assert value["inputPayload"] == {
        "schemaVersion": 1,
        "workflow": "symbol_readability",
        "action": action,
        "identifier": str(identifier),
    }
    assert value["progress"]["current"] == 7
    assert value["progress"]["total"] == 15
    assert value["progress"]["stage"] == "symbol_readability_" + action
    assert value["progress"]["succeeded"] == 3
    assert value["progress"]["failed"] == 2
    assert value["progress"]["review"] == 2
    assert value["error"] == (
        {"code": "JOB_EXECUTION_FAILED", "message": "OperationalError"}
        if status is JobStatus.FAILED
        else None
    )
    assert android_detail.json()["inputPayload"] == {
        "schemaVersion": 1,
        "mobileReleaseId": str(release),
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"workflow": "android_build"},
        {"action": "delete"},
        {"identifier": "not-a-uuid"},
        {"unexpected": True},
    ],
)
def test_readability_response_keeps_strict_validation(change):
    job = create_job(
        JobType.SYMBOL_READABILITY,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "workflow": "symbol_readability",
            "action": "prepare",
            "identifier": str(uuid4()),
        },
    )
    with pytest.raises(ValidationError):
        JobResponse.from_domain(replace(job, input_payload={**job.input_payload, **change}))


def test_generic_job_creation_does_not_enqueue_readability(tmp_path):
    client, game, _, repository = _client(tmp_path)
    with client:
        result = client.post(
            "/api/v1/admin/jobs",
            json={
                "gameId": str(game),
                "jobType": "symbol_readability",
                "inputPayload": {
                    "schemaVersion": 1,
                    "workflow": "symbol_readability",
                    "action": "prepare",
                    "identifier": str(uuid4()),
                },
            },
        )
    assert result.status_code == 422
    assert not repository.items
