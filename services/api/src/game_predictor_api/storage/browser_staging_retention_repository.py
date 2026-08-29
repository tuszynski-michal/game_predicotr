"""SQLAlchemy persistence for browser-staging retention state."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.browser_staging_retention import ManagedOriginalsHandoff
from game_predictor_api.domain.jobs import JobConflictError

from .models import BrowserSelectionRetentionModel

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
        game_id: UUID,
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


__all__ = ["RETENTION_DELAY", "SqlAlchemyBrowserStagingRetentionRepository"]
