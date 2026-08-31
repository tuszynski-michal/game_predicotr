"""SQLAlchemy persistence for browser-staging retention state."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.browser_staging_retention import ManagedOriginalsHandoff
from game_predictor_api.domain.jobs import JobConflictError

from .models import (
    BrowserSelectionRetentionModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImagePipelineTerminalManifestModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)

RETENTION_DELAY = timedelta(hours=24)


class SqlAlchemyBrowserStagingRetentionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record_ready(
        self,
        *,
        upload_id: UUID,
        game_id: UUID | None,
        display_name: str,
        manifest_checksum_sha256: str,
        finalized_at: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            row = session.get(BrowserSelectionRetentionModel, upload_id)
            if row is None:
                session.add(
                    BrowserSelectionRetentionModel(
                        upload_id=upload_id,
                        game_id=game_id,
                        import_job_id=None,
                        display_name=display_name,
                        state="ready",
                        manifest_checksum_sha256=manifest_checksum_sha256,
                        managed_manifest_relative_path=None,
                        managed_manifest_checksum_sha256=None,
                        finalized_at=finalized_at,
                        last_dependency_at=None,
                        eligible_at=None,
                        blocked_reason=None,
                        updated_at=finalized_at,
                    )
                )
                return
            if row.manifest_checksum_sha256 != manifest_checksum_sha256:
                raise JobConflictError(
                    "IMAGE_BROWSER_RETENTION_MANIFEST_CONFLICT",
                    "The persisted browser staging references another manifest.",
                )

    def record_in_use(
        self,
        *,
        upload_id: UUID,
        game_id: UUID | None,
        job_id: UUID,
        used_at: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            row = session.execute(
                select(BrowserSelectionRetentionModel)
                .where(BrowserSelectionRetentionModel.upload_id == upload_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return
            if row.game_id not in {None, game_id}:
                raise JobConflictError(
                    "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                    "The staged folder belongs to a different game.",
                )
            row.game_id = game_id
            row.import_job_id = job_id
            row.state = "in_use"
            row.last_dependency_at = used_at
            row.eligible_at = None
            row.blocked_reason = None
            row.updated_at = used_at

    def record_ingested(self, handoff: ManagedOriginalsHandoff) -> None:
        with self._session_factory.begin() as session:
            row = session.execute(
                select(BrowserSelectionRetentionModel)
                .where(BrowserSelectionRetentionModel.upload_id == handoff.upload_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return
            if row.game_id not in {None, handoff.game_id}:
                raise JobConflictError(
                    "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                    "The managed-original handoff belongs to a different game.",
                )
            row.game_id = handoff.game_id
            row.import_job_id = handoff.import_job_id
            row.state = "ingested"
            row.managed_manifest_relative_path = handoff.manifest_relative_path
            row.managed_manifest_checksum_sha256 = handoff.manifest_checksum_sha256
            row.last_dependency_at = handoff.completed_at
            row.eligible_at = handoff.completed_at + RETENTION_DELAY
            row.blocked_reason = None
            row.updated_at = handoff.completed_at

    def discard_unused(self, *, upload_id: UUID) -> None:
        """Delete an unused staging's empty import/preflight history.

        Browser staging deletion is deliberately conservative.  Once an
        import produced even one recognized board or review item, its audit
        graph is no longer considered staging-only data and this operation is
        blocked.  Empty preflights/import attempts are removed together with
        their unshared execution checkpoints so they cannot remain in Admin
        import selectors after the staging directory disappears.
        """

        try:
            with self._session_factory.begin() as session:
                retention = session.execute(
                    select(BrowserSelectionRetentionModel)
                    .where(BrowserSelectionRetentionModel.upload_id == upload_id)
                    .with_for_update()
                ).scalar_one_or_none()
                jobs = tuple(
                    session.scalars(
                        select(JobModel)
                        .where(
                            JobModel.input_payload["source_selection_id"].as_string()
                            == str(upload_id)
                        )
                        .with_for_update()
                    )
                )
                job_ids = {job.id for job in jobs}
                if retention is not None and retention.import_job_id is not None:
                    job_ids.add(retention.import_job_id)
                if not job_ids:
                    if retention is not None:
                        session.delete(retention)
                    return

                locked_jobs = tuple(
                    session.scalars(
                        select(JobModel).where(JobModel.id.in_(job_ids)).with_for_update()
                    )
                )
                active = [
                    str(job.id)
                    for job in locked_jobs
                    if job.status.value in {"created", "processing"}
                ]
                if active:
                    raise JobConflictError(
                        "IMAGE_BROWSER_SELECTION_DELETE_ACTIVE",
                        "The browser staging still has an active job.",
                        details={"jobIds": active},
                    )

                review_count = int(
                    session.scalar(
                        select(func.count(ImageReviewItemModel.id)).where(
                            ImageReviewItemModel.import_job_id.in_(job_ids)
                        )
                    )
                    or 0
                )
                board_count = int(
                    session.scalar(
                        select(func.count(RecognizedBoardModel.id))
                        .join(
                            SourceImageModel,
                            SourceImageModel.id == RecognizedBoardModel.source_image_id,
                        )
                        .where(SourceImageModel.import_job_id.in_(job_ids))
                    )
                    or 0
                )
                if review_count or board_count:
                    raise JobConflictError(
                        "IMAGE_BROWSER_SELECTION_DELETE_HAS_RESULTS",
                        "The browser staging produced import results and cannot be "
                        "deleted as unused.",
                        details={
                            "recognizedBoardCount": board_count,
                            "reviewItemCount": review_count,
                        },
                    )

                execution_keys = set(
                    session.scalars(
                        select(ImageImportJobFileModel.file_execution_key).where(
                            ImageImportJobFileModel.job_id.in_(job_ids)
                        )
                    )
                )
                session.execute(
                    delete(SourceImageModel).where(SourceImageModel.import_job_id.in_(job_ids))
                )
                session.execute(
                    delete(ImageImportJobFileModel).where(
                        ImageImportJobFileModel.job_id.in_(job_ids)
                    )
                )
                if retention is not None:
                    session.delete(retention)
                    session.flush()

                if execution_keys:
                    shared_keys = set(
                        session.scalars(
                            select(ImageImportJobFileModel.file_execution_key).where(
                                ImageImportJobFileModel.file_execution_key.in_(execution_keys)
                            )
                        )
                    )
                    unshared_keys = execution_keys - shared_keys
                    if unshared_keys:
                        session.execute(
                            delete(ImagePipelineStageResultModel).where(
                                ImagePipelineStageResultModel.file_execution_key.in_(unshared_keys)
                            )
                        )
                        session.execute(
                            delete(ImagePipelineTerminalManifestModel).where(
                                ImagePipelineTerminalManifestModel.file_execution_key.in_(
                                    unshared_keys
                                )
                            )
                        )
                        session.execute(
                            delete(ImageFileExecutionModel).where(
                                ImageFileExecutionModel.file_execution_key.in_(unshared_keys)
                            )
                        )

                session.execute(delete(JobModel).where(JobModel.id.in_(job_ids)))
                session.flush()
        except IntegrityError as error:
            raise JobConflictError(
                "IMAGE_BROWSER_SELECTION_DELETE_HAS_REFERENCES",
                "The browser staging still has protected database references.",
                details={"uploadId": str(upload_id)},
            ) from error


__all__ = ["RETENTION_DELAY", "SqlAlchemyBrowserStagingRetentionRepository"]
