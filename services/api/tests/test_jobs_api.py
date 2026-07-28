import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.jobs import (
    JobService,
    LayoutImportRulesReference,
)
from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.main import create_app
from test_jobs_domain import MemoryJobRepository


def _client(
    tmp_path: Path,
) -> tuple[
    TestClient,
    UUID,
    JobService,
    MemoryJobRepository,
]:
    game_id = uuid4()
    repository = MemoryJobRepository(game_id)
    import_root = tmp_path / "imports"
    import_root.mkdir()
    service = JobService(
        repository,
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
    )
    client = TestClient(
        create_app(
            ApiSettings.from_environment({"GAME_PREDICTOR_IMPORT_ROOT": str(import_root)}),
            job_service_dependency=lambda: service,
        )
    )
    return client, game_id, service, repository


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


def test_create_list_get_and_cancel_job_contract(tmp_path: Path) -> None:
    client, game_id, _service, _repository = _client(tmp_path)
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
        assert created["attemptCount"] == 0
        assert created["heartbeatAt"] is None
        assert created["leaseExpiresAt"] is None

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


def test_typed_payload_and_duplicate_errors_are_stable(tmp_path: Path) -> None:
    client, game_id, _service, _repository = _client(tmp_path)
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


def test_all_five_job_payloads_are_discriminated_by_job_type(
    tmp_path: Path,
) -> None:
    client, game_id, service, _repository = _client(tmp_path)
    import_source = tmp_path / "imports" / "game-1.csv"
    import_source.write_text(
        'schema_version,sequence_number,cells\n1,1,"[1,2,3]"\n',
        encoding="utf-8",
        newline="\n",
    )
    release_id = uuid4()
    requests = [
        (
            "import",
            game_id,
            {
                "schemaVersion": 1,
                "sourcePath": "game-1.csv",
                "contractVersion": 1,
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
                    "gameId": (None if request_game_id is None else str(request_game_id)),
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


def test_import_job_attests_source_and_is_idempotent_by_content(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    content = b'schema_version,sequence_number,cells\n1,1,"[1,2,3]"\n'
    import_root = tmp_path / "imports"
    (import_root / "first.csv").write_bytes(content)
    (import_root / "renamed.csv").write_bytes(content)
    first_request = {
        "jobType": "import",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "sourcePath": "first.csv",
            "contractVersion": 1,
        },
    }
    with client:
        created = client.post("/api/v1/admin/jobs", json=first_request)
        duplicate = client.post(
            "/api/v1/admin/jobs",
            json={
                **first_request,
                "inputPayload": {
                    **first_request["inputPayload"],
                    "sourcePath": "renamed.csv",
                },
            },
        )

    assert created.status_code == 201
    created_payload = created.json()["inputPayload"]
    assert created_payload == {
        "schemaVersion": 1,
        "importKind": "layout_file",
        "sourcePath": "first.csv",
        "sourceChecksum": hashlib.sha256(content).hexdigest(),
        "sourceSizeBytes": len(content),
        "fileFormat": "csv",
        "contractVersion": 1,
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"
    assert duplicate.json()["details"]["existingJobId"] == created.json()["id"]
    assert len(repository.items) == 1


def test_layout_import_validation_requires_completed_import_and_published_rules(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    import_job = replace(
        JobService(repository).create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={"schema_version": 1, "dataset_version_id": str(uuid4())},
        ),
        job_type=JobType.IMPORT,
        status=JobStatus.COMPLETED,
    )
    repository.items[import_job.id] = import_job
    rules_version_id = uuid4()
    repository.rules[rules_version_id] = LayoutImportRulesReference(
        game_id=game_id,
        status=RulesVersionStatus.PUBLISHED,
    )
    payload = {
        "jobType": "validate",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "validationKind": "layout_import",
            "importJobId": str(import_job.id),
            "rulesVersionId": str(rules_version_id),
        },
    }

    with client:
        created = client.post("/api/v1/admin/jobs", json=payload)
        duplicate = client.post("/api/v1/admin/jobs", json=payload)

    assert created.status_code == 201
    assert created.json()["inputPayload"] == payload["inputPayload"]
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "JOB_INPUT_ALREADY_EXISTS"


def test_import_job_rejects_untrusted_metadata_and_unsafe_path(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    (tmp_path / "imports" / "layouts.csv").write_text(
        'schema_version,sequence_number,cells\n1,1,"[1]"\n',
        encoding="utf-8",
    )
    base_request = {
        "jobType": "import",
        "gameId": str(game_id),
        "inputPayload": {
            "schemaVersion": 1,
            "sourcePath": "layouts.csv",
            "contractVersion": 1,
        },
    }
    with client:
        untrusted = client.post(
            "/api/v1/admin/jobs",
            json={
                **base_request,
                "inputPayload": {
                    **base_request["inputPayload"],
                    "sourceChecksum": "a" * 64,
                },
            },
        )
        unsafe = client.post(
            "/api/v1/admin/jobs",
            json={
                **base_request,
                "inputPayload": {
                    **base_request["inputPayload"],
                    "sourcePath": "../layouts.csv",
                },
            },
        )

    assert untrusted.status_code == 422
    assert untrusted.json()["code"] == "VALIDATION_ERROR"
    assert unsafe.status_code == 422
    assert unsafe.json()["code"] == "INVALID_IMPORT_SOURCE_PATH"
    assert repository.items == {}


def test_import_job_reports_contract_error_without_creating_job(
    tmp_path: Path,
) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    (tmp_path / "imports" / "invalid.csv").write_text(
        "wrong,header\n",
        encoding="utf-8",
    )
    with client:
        response = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "import",
                "gameId": str(game_id),
                "inputPayload": {
                    "schemaVersion": 1,
                    "sourcePath": "invalid.csv",
                    "contractVersion": 1,
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "import_header_invalid"
    assert response.json()["details"]["lineNumber"] == 1
    assert repository.items == {}


def test_import_job_rejects_unknown_game_before_inspecting_source(
    tmp_path: Path,
) -> None:
    client, _game_id, _service, repository = _client(tmp_path)
    with client:
        response = client.post(
            "/api/v1/admin/jobs",
            json={
                "jobType": "import",
                "gameId": str(uuid4()),
                "inputPayload": {
                    "schemaVersion": 1,
                    "sourcePath": "../outside.csv",
                    "contractVersion": 1,
                },
            },
        )

    assert response.status_code == 404
    assert response.json()["code"] == "GAME_NOT_FOUND"
    assert repository.items == {}


def test_failed_job_retry_requeues_the_same_record(tmp_path: Path) -> None:
    client, game_id, _service, repository = _client(tmp_path)
    with client:
        created = _create_validate_job(client, game_id)
        job_id = UUID(cast(str, created["id"]))
        repository.items[job_id] = replace(
            repository.items[job_id],
            status=JobStatus.FAILED,
            error_code="TEST_FAILURE",
            error_message="Controlled failure.",
            finished_at=datetime.now(UTC),
        )

        retried = client.post(f"/api/v1/admin/jobs/{job_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["id"] == str(job_id)
    assert retried.json()["status"] == "created"
    assert retried.json()["error"] is None
