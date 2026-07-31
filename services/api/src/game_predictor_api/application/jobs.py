"""Application service and repository port for durable jobs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobNotFoundError,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
)
from game_predictor_api.domain.rules import RulesVersionStatus


@dataclass(frozen=True, slots=True)
class LayoutImportRulesReference:
    game_id: UUID
    status: RulesVersionStatus


class JobRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def get_layout_import_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> LayoutImportRulesReference | None: ...

    def add_job(self, job: Job) -> Job: ...

    def get_job(self, job_id: UUID) -> Job | None: ...

    def get_job_for_update(self, job_id: UUID) -> Job | None: ...

    def get_job_by_input_key(self, input_key: str) -> Job | None: ...

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]: ...

    def save_job(self, job: Job) -> Job: ...


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        import_source_inspector: LayoutImportSourceInspector | None = None,
    ) -> None:
        self._repository = repository
        self._import_source_inspector = import_source_inspector

    def create_job(
        self,
        job_type: JobType,
        *,
        game_id: UUID | None,
        input_payload: dict[str, object],
    ) -> Job:
        if job_type is JobType.IMPORT:
            raise JobError(
                "IMPORT_SOURCE_NOT_ATTESTED",
                "Import jobs must be created through the validated source workflow.",
            )
        return self._persist_job(
            job_type,
            game_id=game_id,
            input_payload=input_payload,
        )

    def create_layout_import_job(
        self,
        *,
        game_id: UUID,
        source_path: str,
        contract_version: int,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        if self._import_source_inspector is None:
            raise JobError(
                "IMPORT_ROOT_NOT_CONFIGURED",
                "The import source inspector is not configured.",
            )
        source = self._import_source_inspector.inspect(
            source_path,
            contract_version=contract_version,
        )
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "import_kind": "layout_file",
                "source_path": source.relative_path,
                "source_checksum": source.checksum,
                "source_size_bytes": source.size_bytes,
                "file_format": source.file_format.value,
                "contract_version": source.contract_version,
            },
            game_already_validated=True,
        )

    def create_image_import_job(
        self,
        *,
        game_id: UUID,
        selection_id: UUID,
        source_directory: Path,
        source_display_name: str,
        pipeline_fingerprint: str,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        try:
            resolved = source_directory.resolve(strict=True)
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_NOT_FOUND",
                "The selected image folder does not exist or is unavailable.",
            ) from error
        if not resolved.is_dir():
            raise JobError(
                "IMAGE_FOLDER_NOT_DIRECTORY",
                "The selected image source must be a directory.",
            )
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "import_kind": "image_directory",
                "source_selection_id": str(selection_id),
                "source_directory": str(resolved),
                "source_display_name": source_display_name,
                "pipeline_fingerprint": pipeline_fingerprint,
            },
            game_already_validated=True,
        )

    def create_layout_import_validation_job(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        import_job = self._repository.get_job(import_job_id)
        if import_job is None or import_job.job_type is not JobType.IMPORT:
            raise JobNotFoundError(
                "LAYOUT_IMPORT_JOB_NOT_FOUND",
                "The referenced layout import job does not exist.",
                details={"importJobId": str(import_job_id)},
            )
        if import_job.game_id != game_id:
            raise JobConflictError(
                "LAYOUT_IMPORT_GAME_MISMATCH",
                "The referenced import job belongs to a different game.",
            )
        if import_job.status is not JobStatus.COMPLETED:
            raise JobConflictError(
                "LAYOUT_IMPORT_NOT_COMPLETED",
                "The referenced import job must be completed before validation.",
            )
        rules = self._repository.get_layout_import_rules_reference(rules_version_id)
        if rules is None:
            raise JobNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "The selected rules version does not exist.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        if rules.game_id != game_id:
            raise JobConflictError(
                "LAYOUT_IMPORT_RULES_GAME_MISMATCH",
                "The selected rules version belongs to a different game.",
            )
        if rules.status is not RulesVersionStatus.PUBLISHED:
            raise JobConflictError(
                "RULES_VERSION_NOT_PUBLISHED",
                "The selected rules version must be published.",
            )
        return self._persist_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "validation_kind": "layout_import",
                "import_job_id": str(import_job_id),
                "rules_version_id": str(rules_version_id),
            },
            game_already_validated=True,
        )

    def _persist_job(
        self,
        job_type: JobType,
        *,
        game_id: UUID | None,
        input_payload: dict[str, object],
        game_already_validated: bool = False,
    ) -> Job:
        if (
            game_id is not None
            and not game_already_validated
            and not self._repository.game_exists(game_id)
        ):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        job = create_job(
            job_type,
            game_id=game_id,
            input_payload=input_payload,
        )
        existing = self._repository.get_job_by_input_key(job.input_key)
        if existing is not None:
            raise JobConflictError(
                "JOB_INPUT_ALREADY_EXISTS",
                "A job with the same type and input already exists.",
                details={"existingJobId": str(existing.id)},
            )
        return self._repository.add_job(job)

    def get_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        return job

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]:
        return self._repository.list_jobs(
            status=status,
            job_type=job_type,
            game_id=game_id,
            limit=limit,
        )

    def cancel_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        updated = request_job_cancellation(job)
        if updated is job:
            return job
        return self._repository.save_job(updated)

    def retry_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        return self._repository.save_job(requeue_job(job))
