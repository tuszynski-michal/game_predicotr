from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.jobs import JobService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.main import create_app
from test_jobs_domain import MemoryJobRepository


def _client() -> tuple[TestClient, UUID, JobService]:
    game_id = uuid4()
    service = JobService(MemoryJobRepository(game_id))
    client = TestClient(
        create_app(
            ApiSettings.from_environment({}),
            job_service_dependency=lambda: service,
        )
    )
    return client, game_id, service


def _create_validate_job(client: TestClient, game_id: UUID) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/jobs",
        json={
            "jobType": "validate",
            "gameId": str(game_id),
            "inputPayload": {
                "schemaVersion": 1,
                "datasetVersionId": str(uuid4()),
            },
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_create_list_get_and_cancel_job_contract() -> None:
    client, game_id, _service = _client()
    with client:
        created = _create_validate_job(client, game_id)
        job_id = created["id"]

        assert created["jobType"] == "validate"
        assert created["status"] == "created"
        assert created["progress"] == {
            "current": 0,
            "total": None,
            "stage": None,
            "succeeded": 0,
            "failed": 0,
            "review": 0,
        }
        assert created["error"] is None

        listed = client.get(
            "/api/v1/admin/jobs",
            params={"status": "created", "job_type": "validate"},
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [job_id]

        fetched = client.get(f"/api/v1/admin/jobs/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == job_id

        cancelled = client.post(f"/api/v1/admin/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancelRequestedAt"] is not None
        assert cancelled.json()["finishedAt"] is not None


def test_typed_payload_and_duplicate_errors_are_stable() -> None:
    client, game_id, _service = _client()
    dataset_id = uuid4()
    payload = {
        "jobType": "validate",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "datasetVersionId": str(dataset_id),
        },
    }
    with client:
        assert client.post("/api/v1/admin/jobs", json=payload).status_code == 201
        duplicate = client.post("/api/v1/admin/jobs", json=payload)
        invalid = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "validate",
                "gameId": str(game_id),
                "inputPayload": {
                    "schemaVersion": 2,
                    "datasetVersionId": str(dataset_id),
                },
            },
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_all_five_job_payloads_are_discriminated_by_job_type() -> None:
    client, game_id, service = _client()
    release_id = uuid4()
    requests = [
        (
            "import",
            game_id,
            {
                "schemaVersion": 1,
                "sourcePath": "C:/imports/game-1",
                "pipelineVersion": "image-v1",
            },
        ),
        (
            "payout",
            game_id,
            {
                "schemaVersion": 1,
                "datasetVersionId": str(uuid4()),
                "rulesVersionId": str(uuid4()),
                "algorithmVersion": "payout-v2",
            },
        ),
        ("snapshot", None, {"schemaVersion": 1, "mobileReleaseId": str(release_id)}),
        (
            "android_build",
            None,
            {"schemaVersion": 1, "mobileReleaseId": str(uuid4())},
        ),
    ]
    with client:
        _create_validate_job(client, game_id)
        for job_type, request_game_id, input_payload in requests:
            response = client.post(
                "/api/v1/admin/jobs",
                json={
                    "jobType": job_type,
                    "gameId": (
                        None if request_game_id is None else str(request_game_id)
                    ),
                    "inputPayload": input_payload,
                },
            )
            assert response.status_code == 201

    jobs: list[Job] = list(
        service.list_jobs(
            status=None,
            job_type=None,
            game_id=None,
            limit=20,
        )
    )
    assert {job.job_type for job in jobs} == set(JobType)
    assert all(job.status is JobStatus.CREATED for job in jobs)
