"""Durable worker-side writer for fail-closed v20 board deferrals."""

from __future__ import annotations

from collections.abc import Mapping

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingService,
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingReason,
    BoardCellProcessingManifestV1,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.models import (
    ImageImportJobFileModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobHandlerError

from .pipeline_execution import ImageStageContext


class BoardCellGeometryDeferredWriter:
    """Create one immutable TASK-3 manifest and idempotent pending row."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        manifest_store: ManagedBoardCellProcessingManifestStore,
    ) -> None:
        self._session_factory = session_factory
        self._manifest_store = manifest_store

    def defer(
        self,
        context: ImageStageContext,
        *,
        position_index: int,
        sequence_number: int,
        reason_code: BoardCellGeometryPendingReason,
        processing_snapshot: Mapping[str, object],
    ) -> None:
        with self._session_factory() as session:
            source = session.scalar(
                select(SourceImageModel).where(
                    SourceImageModel.import_job_id == context.job_id,
                    SourceImageModel.file_execution_key == context.file_execution_key,
                )
            )
            job = session.get(JobModel, context.job_id)
            association = session.get(
                ImageImportJobFileModel,
                {
                    "job_id": context.job_id,
                    "file_execution_key": context.file_execution_key,
                },
            )
            if source is None or job is None or job.game_id is None or association is None:
                raise JobHandlerError(
                    "IMAGE_BOARD_CELL_PENDING_CONTEXT_MISSING",
                    "The v20 geometry stage has no durable import source context.",
                )
            board = session.scalar(
                select(RecognizedBoardModel).where(
                    RecognizedBoardModel.source_image_id == source.id,
                    RecognizedBoardModel.position_index == position_index,
                )
            )
            review = (
                None
                if board is None
                else session.scalar(
                    select(ImageReviewItemModel).where(
                        ImageReviewItemModel.recognized_board_id == board.id
                    )
                )
            )
            manifest = BoardCellProcessingManifestV1(
                game_id=job.game_id,
                import_job_id=context.job_id,
                source_image_id=source.id,
                source_checksum_sha256=context.source_checksum_sha256,
                source_relative_path=context.source_relative_path,
                position_index=position_index,
                sequence_number=sequence_number,
                pipeline_fingerprint_sha256=context.pipeline_fingerprint,
                estimator_version=_snapshot_text(processing_snapshot, "estimatorVersion"),
                estimator_fingerprint_sha256=_snapshot_text(
                    processing_snapshot, "estimatorFingerprintSha256"
                ),
                cropper_version=_snapshot_text(processing_snapshot, "cropperVersion"),
                cropper_fingerprint_sha256=_snapshot_text(
                    processing_snapshot, "cropperFingerprintSha256"
                ),
                expected_geometry_revision=0 if board is None else board.geometry_revision,
                expected_review_resolution_revision=(
                    0 if review is None else review.resolution_revision
                ),
            )

        try:
            with self._session_factory() as session, session.begin():
                BoardCellGeometryPendingService(
                    SqlAlchemyBoardCellGeometryPendingRepository(session),
                    self._manifest_store,
                ).defer(manifest=manifest, reason_code=reason_code)
        except JobConflictError as error:
            raise JobHandlerError(error.code, error.message) from error


def _snapshot_text(value: Mapping[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise JobHandlerError(
            "IMAGE_BOARD_CELL_PROCESSING_SNAPSHOT_INVALID",
            "The pinned v20 board-cell processing snapshot is incomplete.",
        )
    return result


__all__ = ["BoardCellGeometryDeferredWriter"]
