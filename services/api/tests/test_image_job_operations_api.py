from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_jobs import (
    ImageJobFile,
    ImageJobOperations,
    ImageJobOperationsService,
    ImageJobStageCount,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app

NOW = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)
PIPELINE = "a" * 64
FILE_KEY = "b" * 64


class MemoryImageOperationsRepository:
    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        self.retry_calls: list[tuple[str, str, datetime, int]] = []
        self.failed = True

    def get_operations(
        self,
        job_id: UUID,
        *,
        file_limit: int,
    ) -> ImageJobOperations:
        assert job_id == self.job_id
        return self._operations(file_limit)

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        retried_at: datetime,
        file_limit: int,
    ) -> ImageJobOperations:
        assert job_id == self.job_id
        self.retry_calls.append((file_execution_key, expected_stage, retried_at, file_limit))
        self.failed = False
        return self._operations(file_limit)

    def _operations(self, file_limit: int) -> ImageJobOperations:
        file = ImageJobFile(
            file_execution_key=FILE_KEY,
            order_index=0,
            source_relative_path="batch/page-001.jpg",
            status="failed" if self.failed else "processing",
            next_stage="normalization",
            failed_stage="normalization" if self.failed else None,
            error_code="IMAGE_NORMALIZATION_FAILED" if self.failed else None,
            error_message="Normalization failed." if self.failed else None,
            retry_count=0 if self.failed else 1,
            review_required=False,
            updated_at=NOW,
        )
        return ImageJobOperations(
            job_id=self.job_id,
            pipeline_fingerprint=PIPELINE,
            total=1,
            current=1 if self.failed else 0,
            succeeded=0,
            failed=1 if self.failed else 0,
            review=0,
            waiting=0,
            elapsed_seconds=30.0,
            files_per_minute=2.0 if self.failed else 0.0,
            stage_counts=(ImageJobStageCount(stage="normalization", count=1),),
            files=(file,),
            file_limit=file_limit,
            has_more_files=False,
        )


def _client(tmp_path: Path) -> tuple[TestClient, UUID, MemoryImageOperationsRepository]:
    job_id = uuid4()
    repository = MemoryImageOperationsRepository(job_id)
    service = ImageJobOperationsService(repository, clock=lambda: NOW)
    settings = ApiSettings.from_environment({"GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path)})
    client = TestClient(
        create_app(
            settings,
            image_job_service_dependency=lambda: service,
        )
    )
    return client, job_id, repository


def test_image_job_operations_exposes_bounded_stats_and_safe_errors(
    tmp_path: Path,
) -> None:
    client, job_id, _repository = _client(tmp_path)

    with client:
        response = client.get(
            f"/api/v1/admin/image-jobs/{job_id}/operations",
            params={"file_limit": 25},
        )

    assert response.status_code == 200
    assert response.json() == {
        "jobId": str(job_id),
        "pipelineFingerprint": PIPELINE,
        "total": 1,
        "current": 1,
        "succeeded": 0,
        "failed": 1,
        "review": 0,
        "waiting": 0,
        "elapsedSeconds": 30.0,
        "filesPerMinute": 2.0,
        "stageCounts": [{"stage": "normalization", "count": 1}],
        "files": [
            {
                "fileExecutionKey": FILE_KEY,
                "orderIndex": 0,
                "sourceRelativePath": "batch/page-001.jpg",
                "status": "failed",
                "nextStage": "normalization",
                "failedStage": "normalization",
                "error": {
                    "code": "IMAGE_NORMALIZATION_FAILED",
                    "message": "Normalization failed.",
                },
                "retryCount": 0,
                "reviewRequired": False,
                "updatedAt": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "fileLimit": 25,
        "hasMoreFiles": False,
    }


def test_retry_image_file_preserves_identity_and_targets_exact_stage(
    tmp_path: Path,
) -> None:
    client, job_id, repository = _client(tmp_path)

    with client:
        response = client.post(
            f"/api/v1/admin/image-jobs/{job_id}/files/{FILE_KEY}/retry",
            json={"expectedStage": "normalization"},
        )

    assert response.status_code == 200
    assert response.json()["files"][0]["fileExecutionKey"] == FILE_KEY
    assert response.json()["files"][0]["status"] == "processing"
    assert response.json()["files"][0]["retryCount"] == 1
    assert repository.retry_calls == [(FILE_KEY, "normalization", NOW, 100)]
