"""SQLAlchemy repository for image-job operations and selective retry."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.application.image_jobs import (
    ImageJobFile,
    ImageJobOperations,
    ImageJobOperationsRepository,
    ImageJobStageCount,
)
from game_predictor_api.application.image_storage import (
    ImageDiagnosticFailure,
    ImageDiagnosticRepository,
    ImageDiagnosticSnapshot,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobNotFoundError,
    JobStatus,
    JobType,
    requeue_job,
)
from game_predictor_api.storage.job_repository import (
    apply_job_to_record,
    job_from_record,
)
from game_predictor_api.storage.models import (
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    JobModel,
)


class SqlAlchemyImageJobOperationsRepository(
    ImageJobOperationsRepository,
    ImageDiagnosticRepository,
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_operations(
        self,
        job_id: UUID,
        *,
        file_limit: int,
    ) -> ImageJobOperations:
        job = self._image_job(job_id)
        return self._operations(job, file_limit=file_limit)

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        retried_at: datetime,
        file_limit: int,
    ) -> ImageJobOperations:
        job = self._image_job(job_id, for_update=True)
        if job.status not in {
            JobStatus.CREATED,
            JobStatus.WAITING_FOR_REVIEW,
            JobStatus.FAILED,
        }:
            raise JobConflictError(
                "IMAGE_FILE_RETRY_JOB_ACTIVE",
                "An image file cannot be retried while its job is active or terminal.",
            )
        association = self._session.get(
            ImageImportJobFileModel,
            {
                "job_id": job_id,
                "file_execution_key": file_execution_key,
            },
            with_for_update=True,
        )
        execution = self._session.get(
            ImageFileExecutionModel,
            file_execution_key,
            with_for_update=True,
        )
        if association is None or execution is None:
            raise JobNotFoundError(
                "IMAGE_JOB_FILE_NOT_FOUND",
                "The image file is not linked to this job.",
                details={
                    "jobId": str(job_id),
                    "fileExecutionKey": file_execution_key,
                },
            )
        checkpoint = cast(
            Mapping[str, object],
            association.workflow_checkpoint_payload,
        )
        next_stage = checkpoint.get("nextStage")
        if (
            association.workflow_status != "failed"
            or association.failed_stage != expected_stage
            or next_stage != expected_stage
        ):
            raise JobConflictError(
                "IMAGE_FILE_RETRY_STAGE_INVALID",
                "Retry must target the failed checkpoint nextStage.",
                details={
                    "expectedStage": expected_stage,
                    "nextStage": next_stage,
                },
            )
        association.workflow_status = "processing"
        association.failed_stage = None
        association.error_code = None
        association.error_message = None
        association.last_failed_at = None
        association.retry_count += 1
        association.updated_at = retried_at
        if (
            execution.status == "failed"
            and execution.checkpoint_payload == association.workflow_checkpoint_payload
        ):
            execution.status = "processing"
            execution.failed_stage = None
            execution.error_code = None
            execution.error_message = None
            execution.last_failed_at = None
            execution.retry_count += 1
            execution.updated_at = retried_at
        if job.status in {JobStatus.WAITING_FOR_REVIEW, JobStatus.FAILED}:
            apply_job_to_record(
                job,
                requeue_job(job_from_record(job), updated_at=retried_at),
            )
        self._session.flush()
        return self._operations(job, file_limit=file_limit)

    def diagnostic_snapshot(
        self,
        job_id: UUID,
        *,
        error_limit: int,
    ) -> ImageDiagnosticSnapshot:
        job = self._image_job(job_id)
        total, current, succeeded, failed, review, waiting = self._stats(job.id)
        records = self._session.scalars(
            select(ImageImportJobFileModel)
            .where(
                ImageImportJobFileModel.job_id == job.id,
                ImageImportJobFileModel.workflow_status == "failed",
            )
            .order_by(ImageImportJobFileModel.order_index)
            .limit(error_limit)
        ).all()
        failures = tuple(
            ImageDiagnosticFailure(
                file_execution_key=record.file_execution_key,
                order_index=record.order_index,
                source_relative_path=record.source_relative_path,
                failed_stage=cast(str, record.failed_stage),
                error_code=cast(str, record.error_code),
                error_message=cast(str, record.error_message),
                retry_count=record.retry_count,
                last_failed_at=cast(datetime, record.last_failed_at),
            )
            for record in records
        )
        return ImageDiagnosticSnapshot(
            job_id=job.id,
            status=job.status.value,
            pipeline_fingerprint=cast(str, job.input_payload["pipeline_fingerprint"]),
            source_updated_at=job.updated_at,
            total=total,
            current=current,
            succeeded=succeeded,
            failed=failed,
            review=review,
            waiting=waiting,
            failures=failures,
            error_limit=error_limit,
            truncated=failed > len(failures),
        )

    def _image_job(
        self,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> JobModel:
        if for_update:
            job = self._session.scalar(
                select(JobModel).where(JobModel.id == job_id).with_for_update()
            )
        else:
            job = self._session.get(JobModel, job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        if (
            job.job_type is not JobType.IMPORT
            or job.input_payload.get("import_kind") != "image_directory"
            or not isinstance(job.input_payload.get("pipeline_fingerprint"), str)
        ):
            raise JobConflictError(
                "IMAGE_JOB_KIND_INVALID",
                "Image operations require an image_directory import job.",
            )
        return job

    def _operations(
        self,
        job: JobModel,
        *,
        file_limit: int,
    ) -> ImageJobOperations:
        total, current, succeeded, failed, review, waiting = self._stats(job.id)
        stage_expression = case(
            (
                ImageImportJobFileModel.workflow_status == "completed",
                "completed",
            ),
            (
                ImageImportJobFileModel.workflow_status == "failed",
                ImageImportJobFileModel.failed_stage,
            ),
            else_=ImageImportJobFileModel.workflow_checkpoint_payload["nextStage"].as_string(),
        )
        grouped = self._session.execute(
            select(stage_expression, func.count())
            .where(ImageImportJobFileModel.job_id == job.id)
            .group_by(stage_expression)
            .order_by(stage_expression)
        ).all()
        stage_counts = tuple(
            ImageJobStageCount(
                stage="not_started" if stage is None else str(stage),
                count=int(count),
            )
            for stage, count in grouped
        )
        records = self._session.scalars(
            select(ImageImportJobFileModel)
            .where(ImageImportJobFileModel.job_id == job.id)
            .order_by(ImageImportJobFileModel.order_index)
            .limit(file_limit)
        ).all()
        files = tuple(_file_from_record(record) for record in records)
        elapsed_seconds = _elapsed_seconds(job)
        files_per_minute = (
            None
            if elapsed_seconds is None or elapsed_seconds <= 0
            else current * 60.0 / elapsed_seconds
        )
        return ImageJobOperations(
            job_id=job.id,
            pipeline_fingerprint=cast(str, job.input_payload["pipeline_fingerprint"]),
            total=total,
            current=current,
            succeeded=succeeded,
            failed=failed,
            review=review,
            waiting=waiting,
            elapsed_seconds=elapsed_seconds,
            files_per_minute=files_per_minute,
            stage_counts=stage_counts,
            files=files,
            file_limit=file_limit,
            has_more_files=total > len(files),
        )

    def _stats(self, job_id: UUID) -> tuple[int, int, int, int, int, int]:
        stats = self._session.execute(
            select(
                func.count(),
                _status_sum(("waiting_for_review", "completed", "failed")),
                _status_sum(("completed",)),
                _status_sum(("failed",)),
                func.coalesce(
                    func.sum(
                        case(
                            (ImageImportJobFileModel.review_required.is_(True), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                _status_sum(("waiting_for_review",)),
            ).where(ImageImportJobFileModel.job_id == job_id)
        ).one()
        return cast(
            tuple[int, int, int, int, int, int],
            tuple(int(value) for value in stats),
        )


def _status_sum(statuses: tuple[str, ...]) -> ColumnElement[int]:
    return cast(
        ColumnElement[int],
        func.coalesce(
            func.sum(
                case(
                    (ImageImportJobFileModel.workflow_status.in_(statuses), 1),
                    else_=0,
                )
            ),
            0,
        ),
    )


def _file_from_record(record: ImageImportJobFileModel) -> ImageJobFile:
    checkpoint = cast(Mapping[str, object], record.workflow_checkpoint_payload)
    raw_next_stage = checkpoint.get("nextStage")
    return ImageJobFile(
        file_execution_key=record.file_execution_key,
        order_index=record.order_index,
        source_relative_path=record.source_relative_path,
        status=record.workflow_status,
        next_stage=raw_next_stage if isinstance(raw_next_stage, str) else None,
        failed_stage=record.failed_stage,
        error_code=record.error_code,
        error_message=record.error_message,
        retry_count=record.retry_count,
        review_required=record.review_required,
        updated_at=record.updated_at,
    )


def _elapsed_seconds(job: JobModel) -> float | None:
    if job.started_at is None:
        return None
    endpoint = job.finished_at or job.updated_at
    return max(0.0, (endpoint - job.started_at).total_seconds())


__all__ = ["SqlAlchemyImageJobOperationsRepository"]
