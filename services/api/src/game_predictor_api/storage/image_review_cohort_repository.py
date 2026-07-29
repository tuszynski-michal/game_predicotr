"""SQLAlchemy persistence for immutable verified review cohort exports."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.image_review_cohorts import (
    VerifiedCohortExportRepository,
)
from game_predictor_api.domain.image_review_cohorts import (
    ImageVerifiedCohortExport,
    VerifiedCohortSource,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.models import ImageVerifiedCohortExportModel


class SqlAlchemyVerifiedCohortExportRepository(VerifiedCohortExportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_state(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        input_state_sha256: str,
    ) -> ImageVerifiedCohortExport | None:
        record = self._session.scalar(
            select(ImageVerifiedCohortExportModel).where(
                ImageVerifiedCohortExportModel.game_id == game_id,
                ImageVerifiedCohortExportModel.import_job_id == import_job_id,
                ImageVerifiedCohortExportModel.input_state_sha256 == input_state_sha256,
            )
        )
        return _to_export(record) if record is not None else None

    def next_version(self, *, game_id: UUID, import_job_id: UUID) -> int:
        return (
            self._session.scalar(
                select(func.max(ImageVerifiedCohortExportModel.version)).where(
                    ImageVerifiedCohortExportModel.game_id == game_id,
                    ImageVerifiedCohortExportModel.import_job_id == import_job_id,
                )
            )
            or 0
        ) + 1

    def save(
        self,
        *,
        source: VerifiedCohortSource,
        version: int,
        payload_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> ImageVerifiedCohortExport:
        record = ImageVerifiedCohortExportModel(
            game_id=source.game_id,
            import_job_id=source.import_job_id,
            version=version,
            input_state_sha256=source.input_state_sha256,
            payload_sha256=payload_sha256,
            artifact_relative_path=artifact_relative_path,
            board_count=source.board_count,
            sample_count=source.sample_count,
            pending_item_count=source.pending_item_count,
            rejected_item_count=source.rejected_item_count,
            created_by=created_by,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_EXPORT_RACE",
                "The verified cohort changed or was exported concurrently; retry.",
            ) from error
        self._session.refresh(record)
        return _to_export(record)

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        limit: int,
    ) -> Sequence[ImageVerifiedCohortExport]:
        return tuple(
            _to_export(record)
            for record in self._session.scalars(
                select(ImageVerifiedCohortExportModel)
                .where(
                    ImageVerifiedCohortExportModel.game_id == game_id,
                    ImageVerifiedCohortExportModel.import_job_id == import_job_id,
                )
                .order_by(ImageVerifiedCohortExportModel.version.desc())
                .limit(limit)
            )
        )


def _to_export(record: ImageVerifiedCohortExportModel) -> ImageVerifiedCohortExport:
    return ImageVerifiedCohortExport(
        id=record.id,
        game_id=record.game_id,
        import_job_id=record.import_job_id,
        version=record.version,
        input_state_sha256=record.input_state_sha256,
        payload_sha256=record.payload_sha256,
        artifact_relative_path=record.artifact_relative_path,
        board_count=record.board_count,
        sample_count=record.sample_count,
        pending_item_count=record.pending_item_count,
        rejected_item_count=record.rejected_item_count,
        created_by=record.created_by,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyVerifiedCohortExportRepository"]
