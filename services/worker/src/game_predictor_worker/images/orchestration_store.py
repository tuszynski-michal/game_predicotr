"""PostgreSQL persistence for resumable image-file executions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_api.domain.jobs import JobStatus, require_active_job_lease
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import (
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    JobModel,
)
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobHandlerError

from .orchestration import (
    IMAGE_IMPORT_KIND,
    ImageBatchCandidate,
    ImageBatchStats,
    ImageFileExecution,
    initial_file_checkpoint,
)
from .pipeline_contract import (
    PIPELINE_STAGES,
    canonical_json_bytes,
    file_execution_key,
    validate_checkpoint_transition,
    validate_file_checkpoint,
)


class ImageOrchestrationStoreError(JobHandlerError):
    """Stable persistence error for image batch orchestration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)


class SqlAlchemyImageBatchStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def register_file(
        self,
        job_id: UUID,
        *,
        source_checksum_sha256: str,
        pipeline_fingerprint: str,
        source_relative_path: str,
        order_index: int,
        registered_at: datetime,
    ) -> ImageFileExecution:
        if order_index < 0:
            raise ImageOrchestrationStoreError(
                "IMAGE_BATCH_ORDER_INVALID",
                "Image batch orderIndex must be non-negative.",
            )
        relative_path = _relative_posix_path(source_relative_path)
        checkpoint = initial_file_checkpoint(
            source_checksum_sha256,
            pipeline_fingerprint,
        )
        execution_key = file_execution_key(
            source_checksum_sha256,
            pipeline_fingerprint,
        )
        with self._session_factory() as session:
            try:
                with session.begin():
                    job = _locked_job(session, job_id)
                    _require_image_job(job, pipeline_fingerprint)
                    execution = session.get(
                        ImageFileExecutionModel,
                        execution_key,
                        with_for_update=True,
                    )
                    if execution is None:
                        execution = ImageFileExecutionModel(
                            file_execution_key=execution_key,
                            source_checksum_sha256=source_checksum_sha256,
                            pipeline_fingerprint=pipeline_fingerprint,
                            checkpoint_payload=checkpoint,
                            status="processing",
                            review_required=False,
                            created_at=registered_at,
                            updated_at=registered_at,
                        )
                        session.add(execution)
                        session.flush()
                    else:
                        _require_execution_provenance(
                            execution,
                            source_checksum_sha256,
                            pipeline_fingerprint,
                        )
                    association = session.get(
                        ImageImportJobFileModel,
                        {
                            "job_id": job_id,
                            "file_execution_key": execution_key,
                        },
                        with_for_update=True,
                    )
                    if association is None:
                        workflow_checkpoint = _initial_job_workflow_checkpoint(
                            execution.checkpoint_payload
                        )
                        workflow_status = (
                            "failed"
                            if execution.status == "failed"
                            else cast(str, workflow_checkpoint["status"])
                        )
                        reuse_requires_review = workflow_status == "waiting_for_review"
                        association = ImageImportJobFileModel(
                            job_id=job_id,
                            file_execution_key=execution_key,
                            order_index=order_index,
                            source_relative_path=relative_path,
                            workflow_checkpoint_payload=workflow_checkpoint,
                            workflow_status=workflow_status,
                            review_required=(execution.review_required or reuse_requires_review),
                            failed_stage=(
                                execution.failed_stage if workflow_status == "failed" else None
                            ),
                            error_code=(
                                execution.error_code if workflow_status == "failed" else None
                            ),
                            error_message=(
                                execution.error_message if workflow_status == "failed" else None
                            ),
                            retry_count=execution.retry_count,
                            last_failed_at=(
                                execution.last_failed_at if workflow_status == "failed" else None
                            ),
                            created_at=registered_at,
                            updated_at=registered_at,
                        )
                        session.add(association)
                        session.flush()
                    elif (
                        association.order_index != order_index
                        or association.source_relative_path != relative_path
                    ):
                        raise ImageOrchestrationStoreError(
                            "IMAGE_BATCH_ASSOCIATION_CONFLICT",
                            "The image execution is already linked with different metadata.",
                        )
                    return _execution_from_records(execution, association)
            except IntegrityError as error:
                session.rollback()
                raise ImageOrchestrationStoreError(
                    "IMAGE_BATCH_PERSISTENCE_CONFLICT",
                    "Image batch data conflicts with an existing order or execution.",
                ) from error

    def count_job_files(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> int:
        with self._session_factory() as session:
            value = session.scalar(
                select(func.count())
                .select_from(ImageImportJobFileModel)
                .join(ImageFileExecutionModel)
                .where(
                    ImageImportJobFileModel.job_id == job_id,
                    ImageFileExecutionModel.pipeline_fingerprint == pipeline_fingerprint,
                )
            )
            return int(value or 0)

    def next_processing_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchCandidate | None:
        return self._next_file(
            job_id,
            pipeline_fingerprint=pipeline_fingerprint,
            status="processing",
            after_order_index=-1,
        )

    def next_waiting_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
        after_order_index: int,
    ) -> ImageBatchCandidate | None:
        return self._next_file(
            job_id,
            pipeline_fingerprint=pipeline_fingerprint,
            status="waiting_for_review",
            after_order_index=after_order_index,
        )

    def _next_file(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
        status: str,
        after_order_index: int,
    ) -> ImageBatchCandidate | None:
        with self._session_factory() as session:
            row = session.execute(
                select(ImageImportJobFileModel, ImageFileExecutionModel)
                .join(
                    ImageFileExecutionModel,
                    ImageFileExecutionModel.file_execution_key
                    == ImageImportJobFileModel.file_execution_key,
                )
                .where(
                    ImageImportJobFileModel.job_id == job_id,
                    ImageImportJobFileModel.order_index > after_order_index,
                    ImageFileExecutionModel.pipeline_fingerprint == pipeline_fingerprint,
                    ImageImportJobFileModel.workflow_status == status,
                )
                .order_by(ImageImportJobFileModel.order_index)
                .limit(1)
            ).first()
            if row is None:
                return None
            association, execution = row.tuple()
            return ImageBatchCandidate(
                execution=_execution_from_records(execution, association),
                order_index=association.order_index,
                source_relative_path=association.source_relative_path,
                job_id=job_id,
            )

    def save_file_checkpoint(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        expected_checkpoint: Mapping[str, object],
        checkpoint_payload: Mapping[str, object],
        checkpointed_at: datetime,
    ) -> ImageFileExecution:
        expected = validate_file_checkpoint(expected_checkpoint)
        current = validate_file_checkpoint(checkpoint_payload)
        validate_checkpoint_transition(expected, current)
        execution_key = cast(str, current["fileExecutionKey"])
        with self._session_factory() as session, session.begin():
            job = _locked_job(session, job_id)
            require_active_job_lease(
                job_from_record(job),
                lease_token=lease_token,
                checked_at=checkpointed_at,
            )
            _require_image_job(job, cast(str, current["pipelineFingerprint"]))
            association = session.get(
                ImageImportJobFileModel,
                {
                    "job_id": job_id,
                    "file_execution_key": execution_key,
                },
            )
            if association is None:
                raise ImageOrchestrationStoreError(
                    "IMAGE_BATCH_FILE_NOT_LINKED",
                    "The file execution is not linked to this image import job.",
                )
            execution = session.get(
                ImageFileExecutionModel,
                execution_key,
                with_for_update=True,
            )
            if execution is None:
                raise ImageOrchestrationStoreError(
                    "IMAGE_FILE_EXECUTION_NOT_FOUND",
                    "The image file execution no longer exists.",
                )
            if canonical_json_bytes(
                association.workflow_checkpoint_payload
            ) != canonical_json_bytes(expected):
                raise ImageOrchestrationStoreError(
                    "IMAGE_FILE_CHECKPOINT_STALE",
                    "The image file checkpoint was advanced by another execution.",
                )
            association.workflow_checkpoint_payload = current
            association.workflow_status = cast(str, current["status"])
            association.review_required = (
                association.review_required or association.workflow_status == "waiting_for_review"
            )
            association.failed_stage = None
            association.error_code = None
            association.error_message = None
            association.last_failed_at = None
            association.updated_at = checkpointed_at
            _advance_global_execution_if_current(
                execution,
                expected=expected,
                current=current,
                checkpointed_at=checkpointed_at,
            )
            session.flush()
            return _execution_from_records(execution, association)

    def fail_file(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        expected_checkpoint: Mapping[str, object],
        failed_stage: str,
        error_code: str,
        error_message: str,
        failed_at: datetime,
    ) -> ImageFileExecution:
        expected = validate_file_checkpoint(expected_checkpoint)
        next_stage = expected["nextStage"]
        normalized_code = error_code.strip()
        normalized_message = error_message.strip()
        if (
            failed_stage != next_stage
            or not normalized_code
            or len(normalized_code) > 100
            or not normalized_message
        ):
            raise ImageOrchestrationStoreError(
                "IMAGE_FILE_FAILURE_INVALID",
                "A file failure requires its exact nextStage, code and safe message.",
            )
        execution_key = cast(str, expected["fileExecutionKey"])
        with self._session_factory() as session, session.begin():
            job = _locked_job(session, job_id)
            require_active_job_lease(
                job_from_record(job),
                lease_token=lease_token,
                checked_at=failed_at,
            )
            _require_image_job(job, cast(str, expected["pipelineFingerprint"]))
            association = session.get(
                ImageImportJobFileModel,
                {
                    "job_id": job_id,
                    "file_execution_key": execution_key,
                },
                with_for_update=True,
            )
            execution = session.get(
                ImageFileExecutionModel,
                execution_key,
                with_for_update=True,
            )
            if association is None or execution is None:
                raise ImageOrchestrationStoreError(
                    "IMAGE_BATCH_FILE_NOT_LINKED",
                    "The file execution is not linked to this image import job.",
                )
            if canonical_json_bytes(
                association.workflow_checkpoint_payload
            ) != canonical_json_bytes(expected):
                raise ImageOrchestrationStoreError(
                    "IMAGE_FILE_CHECKPOINT_STALE",
                    "The image file checkpoint was advanced by another execution.",
                )
            _set_job_file_failure(
                association,
                failed_stage=failed_stage,
                error_code=normalized_code,
                error_message=normalized_message,
                failed_at=failed_at,
            )
            if canonical_json_bytes(execution.checkpoint_payload) == canonical_json_bytes(expected):
                _set_global_failure(
                    execution,
                    failed_stage=failed_stage,
                    error_code=normalized_code,
                    error_message=normalized_message,
                    failed_at=failed_at,
                )
            session.flush()
            return _execution_from_records(execution, association)

    def retry_file(
        self,
        job_id: UUID,
        *,
        file_execution_key: str,
        expected_stage: str,
        retried_at: datetime,
    ) -> ImageFileExecution:
        with self._session_factory() as session, session.begin():
            job = _locked_job(session, job_id)
            association = session.get(
                ImageImportJobFileModel,
                {
                    "job_id": job_id,
                    "file_execution_key": file_execution_key,
                },
                with_for_update=True,
            )
            execution = session.get(
                ImageFileExecutionModel,
                file_execution_key,
                with_for_update=True,
            )
            if association is None or execution is None:
                raise ImageOrchestrationStoreError(
                    "IMAGE_BATCH_FILE_NOT_LINKED",
                    "The file execution is not linked to this image import job.",
                )
            _require_image_job(job, execution.pipeline_fingerprint)
            checkpoint = validate_file_checkpoint(association.workflow_checkpoint_payload)
            if association.workflow_status != "failed" or checkpoint["nextStage"] != expected_stage:
                raise ImageOrchestrationStoreError(
                    "IMAGE_FILE_RETRY_STAGE_INVALID",
                    "Retry must target the failed checkpoint nextStage.",
                )
            association.workflow_status = "processing"
            association.failed_stage = None
            association.error_code = None
            association.error_message = None
            association.last_failed_at = None
            association.retry_count += 1
            association.updated_at = retried_at
            if execution.status == "failed" and canonical_json_bytes(
                execution.checkpoint_payload
            ) == canonical_json_bytes(checkpoint):
                execution.status = "processing"
                execution.failed_stage = None
                execution.error_code = None
                execution.error_message = None
                execution.last_failed_at = None
                execution.retry_count += 1
                execution.updated_at = retried_at
            session.flush()
            return _execution_from_records(execution, association)

    def batch_stats(
        self,
        job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> ImageBatchStats:
        with self._session_factory() as session:
            row = session.execute(
                select(
                    func.count(),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ImageImportJobFileModel.workflow_status.in_(
                                        ("waiting_for_review", "completed", "failed")
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (ImageImportJobFileModel.workflow_status == "completed", 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (ImageImportJobFileModel.workflow_status == "failed", 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (ImageImportJobFileModel.review_required.is_(True), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ImageImportJobFileModel.workflow_status == "waiting_for_review",
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                )
                .select_from(ImageImportJobFileModel)
                .join(ImageFileExecutionModel)
                .where(
                    ImageImportJobFileModel.job_id == job_id,
                    ImageFileExecutionModel.pipeline_fingerprint == pipeline_fingerprint,
                )
            ).one()
            return ImageBatchStats(*(int(value) for value in row))


def _locked_job(session: Session, job_id: UUID) -> JobModel:
    job = session.get(JobModel, job_id, with_for_update=True)
    if job is None:
        raise ImageOrchestrationStoreError(
            "IMAGE_BATCH_JOB_NOT_FOUND",
            "The image import job no longer exists.",
        )
    return job


def _require_image_job(job: JobModel, pipeline_fingerprint: str) -> None:
    payload = job.input_payload
    if (
        job.status
        not in {
            JobStatus.CREATED,
            JobStatus.PROCESSING,
            JobStatus.WAITING_FOR_REVIEW,
        }
        or payload.get("import_kind") != IMAGE_IMPORT_KIND
        or payload.get("pipeline_fingerprint") != pipeline_fingerprint
    ):
        raise ImageOrchestrationStoreError(
            "IMAGE_BATCH_JOB_CONTRACT_MISMATCH",
            "The job does not own this image pipeline execution.",
        )


def _require_execution_provenance(
    execution: ImageFileExecutionModel,
    source_checksum_sha256: str,
    pipeline_fingerprint: str,
) -> None:
    if (
        execution.source_checksum_sha256 != source_checksum_sha256
        or execution.pipeline_fingerprint != pipeline_fingerprint
        or execution.file_execution_key
        != file_execution_key(source_checksum_sha256, pipeline_fingerprint)
    ):
        raise ImageOrchestrationStoreError(
            "IMAGE_FILE_EXECUTION_PROVENANCE_CONFLICT",
            "The existing execution has different source or pipeline provenance.",
        )


def _relative_posix_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ImageOrchestrationStoreError(
            "IMAGE_BATCH_PATH_UNSAFE",
            "sourceRelativePath must be a normalized relative POSIX path.",
        )
    return value


def _initial_job_workflow_checkpoint(
    global_checkpoint_payload: Mapping[str, object],
) -> dict[str, object]:
    checkpoint = validate_file_checkpoint(global_checkpoint_payload)
    completed = cast(list[str], checkpoint["completedStages"])
    automated_count = PIPELINE_STAGES.index("manual_review")
    if len(completed) < automated_count:
        return dict(checkpoint)
    return {
        **checkpoint,
        "completedStages": list(PIPELINE_STAGES[:automated_count]),
        "nextStage": "manual_review",
        "status": "waiting_for_review",
    }


def _advance_global_execution_if_current(
    execution: ImageFileExecutionModel,
    *,
    expected: Mapping[str, object],
    current: Mapping[str, object],
    checkpointed_at: datetime,
) -> None:
    global_checkpoint = validate_file_checkpoint(execution.checkpoint_payload)
    if canonical_json_bytes(global_checkpoint) == canonical_json_bytes(expected):
        execution.checkpoint_payload = dict(current)
        execution.status = cast(str, current["status"])
        execution.review_required = (
            execution.review_required or execution.status == "waiting_for_review"
        )
        execution.failed_stage = None
        execution.error_code = None
        execution.error_message = None
        execution.last_failed_at = None
        execution.updated_at = checkpointed_at
        execution.processed_at = checkpointed_at if execution.status == "completed" else None
        return
    global_completed = cast(list[str], global_checkpoint["completedStages"])
    current_completed = cast(list[str], current["completedStages"])
    if global_completed[: len(current_completed)] != current_completed:
        raise ImageOrchestrationStoreError(
            "IMAGE_FILE_GLOBAL_CHECKPOINT_CONFLICT",
            "The shared image execution is not a prefix-compatible result.",
        )


def _set_job_file_failure(
    association: ImageImportJobFileModel,
    *,
    failed_stage: str,
    error_code: str,
    error_message: str,
    failed_at: datetime,
) -> None:
    association.workflow_status = "failed"
    association.failed_stage = failed_stage
    association.error_code = error_code
    association.error_message = error_message
    association.last_failed_at = failed_at
    association.updated_at = failed_at


def _set_global_failure(
    execution: ImageFileExecutionModel,
    *,
    failed_stage: str,
    error_code: str,
    error_message: str,
    failed_at: datetime,
) -> None:
    execution.status = "failed"
    execution.failed_stage = failed_stage
    execution.error_code = error_code
    execution.error_message = error_message
    execution.last_failed_at = failed_at
    execution.updated_at = failed_at
    execution.processed_at = None


def _execution_from_records(
    record: ImageFileExecutionModel,
    association: ImageImportJobFileModel,
) -> ImageFileExecution:
    checkpoint = validate_file_checkpoint(association.workflow_checkpoint_payload)
    return ImageFileExecution(
        file_execution_key=record.file_execution_key,
        source_checksum_sha256=record.source_checksum_sha256,
        pipeline_fingerprint=record.pipeline_fingerprint,
        checkpoint_payload=checkpoint,
        status=association.workflow_status,
        review_required=association.review_required,
        error_code=association.error_code,
        error_message=association.error_message,
        failed_stage=association.failed_stage,
        retry_count=association.retry_count,
        last_failed_at=association.last_failed_at,
    )


__all__ = [
    "ImageOrchestrationStoreError",
    "SqlAlchemyImageBatchStore",
]
