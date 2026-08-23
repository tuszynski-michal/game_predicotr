"""PostgreSQL persistence for deferred board-cell geometry work."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellPendingOrderKey,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    ImageBoardGeometryPending,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


class SqlAlchemyBoardCellGeometryPendingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
        manifest_relative_path: str,
    ) -> tuple[ImageBoardGeometryPending, bool]:
        # The source row serializes competing defer attempts for all nine board
        # positions. The idempotency lookup deliberately happens after the lock.
        source = self._session.scalar(
            select(SourceImageModel)
            .where(SourceImageModel.id == manifest.source_image_id)
            .with_for_update()
        )
        job = self._session.get(JobModel, manifest.import_job_id)
        if (
            source is None
            or job is None
            or source.import_job_id != manifest.import_job_id
            or job.game_id != manifest.game_id
            or source.checksum_sha256 != manifest.source_checksum_sha256
            or source.relative_path != manifest.source_relative_path
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_CONTEXT_INVALID",
                "The processing manifest does not match its import source and game.",
            )
        existing = self._session.scalar(
            select(ImageBoardGeometryPendingModel).where(
                ImageBoardGeometryPendingModel.import_job_id == manifest.import_job_id,
                ImageBoardGeometryPendingModel.source_image_id == manifest.source_image_id,
                ImageBoardGeometryPendingModel.position_index == manifest.position_index,
                ImageBoardGeometryPendingModel.processing_manifest_checksum_sha256
                == manifest.checksum_sha256,
            )
        )
        if existing is not None:
            return _to_domain(existing), False

        current = self._session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(
                ImageBoardGeometryPendingModel.import_job_id == manifest.import_job_id,
                ImageBoardGeometryPendingModel.source_image_id == manifest.source_image_id,
                ImageBoardGeometryPendingModel.position_index == manifest.position_index,
                ImageBoardGeometryPendingModel.status
                == BoardCellGeometryPendingStatus.PENDING.value,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if current is not None:
            current.status = BoardCellGeometryPendingStatus.SUPERSEDED.value
            current.superseded_at = now
            current.updated_at = now

        board = self._session.scalar(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == manifest.source_image_id,
                RecognizedBoardModel.position_index == manifest.position_index,
            )
        )
        review = None
        if board is not None:
            review = self._session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            )
            if board.geometry_revision != manifest.expected_geometry_revision or (
                review is not None
                and (
                    review.resolution_revision
                    != manifest.expected_review_resolution_revision
                    or review.status != "pending"
                )
            ):
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT",
                    "The board or human-review revision changed before geometry was deferred.",
                )

        row = ImageBoardGeometryPendingModel(
            id=uuid4(),
            game_id=manifest.game_id,
            import_job_id=manifest.import_job_id,
            source_image_id=manifest.source_image_id,
            recognized_board_id=None if board is None else board.id,
            review_item_id=None if review is None else review.id,
            sequence_number=manifest.sequence_number,
            position_index=manifest.position_index,
            source_checksum_sha256=manifest.source_checksum_sha256,
            source_relative_path=manifest.source_relative_path,
            status=BoardCellGeometryPendingStatus.PENDING.value,
            reason_code=reason_code.value,
            processing_manifest_checksum_sha256=manifest.checksum_sha256,
            processing_manifest_relative_path=manifest_relative_path,
            pipeline_fingerprint_sha256=manifest.pipeline_fingerprint_sha256,
            expected_geometry_revision=manifest.expected_geometry_revision,
            expected_review_resolution_revision=manifest.expected_review_resolution_revision,
            resolved_geometry_revision=None,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            superseded_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _to_domain(row), True

    def get(self, pending_id: UUID) -> ImageBoardGeometryPending | None:
        row = self._session.get(ImageBoardGeometryPendingModel, pending_id)
        return None if row is None else _to_domain(row)

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        after_key: BoardCellPendingOrderKey | None,
        limit: int,
    ) -> Sequence[ImageBoardGeometryPending]:
        query = select(ImageBoardGeometryPendingModel).where(
            ImageBoardGeometryPendingModel.game_id == game_id,
            ImageBoardGeometryPendingModel.import_job_id == import_job_id,
        )
        if status is not None:
            query = query.where(ImageBoardGeometryPendingModel.status == status.value)
        if after_key is not None:
            sequence, position, pending_id = after_key
            query = query.where(
                or_(
                    ImageBoardGeometryPendingModel.sequence_number > sequence,
                    and_(
                        ImageBoardGeometryPendingModel.sequence_number == sequence,
                        ImageBoardGeometryPendingModel.position_index > position,
                    ),
                    and_(
                        ImageBoardGeometryPendingModel.sequence_number == sequence,
                        ImageBoardGeometryPendingModel.position_index == position,
                        ImageBoardGeometryPendingModel.id > pending_id,
                    ),
                )
            )
        rows = self._session.scalars(
            query.order_by(
                ImageBoardGeometryPendingModel.sequence_number,
                ImageBoardGeometryPendingModel.position_index,
                ImageBoardGeometryPendingModel.id,
            ).limit(limit)
        )
        return tuple(_to_domain(row) for row in rows)

    def counts(self, *, game_id: UUID, import_job_id: UUID) -> BoardCellGeometryJobCounts:
        values = self._session.execute(
            select(
                func.count(),
                func.sum(
                    case(
                        (ImageBoardGeometryPendingModel.status == "pending", 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (ImageBoardGeometryPendingModel.status == "resolved", 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (ImageBoardGeometryPendingModel.status == "superseded", 1),
                        else_=0,
                    )
                ),
            ).where(
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.import_job_id == import_job_id,
            )
        ).one()
        return BoardCellGeometryJobCounts(*(int(value or 0) for value in values))

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending | None:
        row = self._session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(ImageBoardGeometryPendingModel.id == pending_id)
            .with_for_update()
        )
        if row is None:
            return None
        if row.processing_manifest_checksum_sha256 != expected_manifest_checksum_sha256:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_MANIFEST_CONFLICT",
                "The deferred geometry item was loaded from a different processing manifest.",
            )
        if row.status == BoardCellGeometryPendingStatus.RESOLVED.value:
            if row.resolved_geometry_revision != resolved_geometry_revision:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT",
                    "The deferred geometry item already has a different resolution.",
                )
            return _to_domain(row)
        if row.status == BoardCellGeometryPendingStatus.SUPERSEDED.value:
            return _to_domain(row)

        board = (
            self._session.scalar(
                select(RecognizedBoardModel).where(
                    RecognizedBoardModel.source_image_id == row.source_image_id,
                    RecognizedBoardModel.position_index == row.position_index,
                )
            )
            if row.recognized_board_id is None
            else self._session.get(RecognizedBoardModel, row.recognized_board_id)
        )
        review = None
        if board is not None:
            review = self._session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            )
        now = datetime.now(UTC)
        human_changed = (
            board is not None and board.geometry_revision != row.expected_geometry_revision
        ) or (
            review is not None
            and (
                review.resolution_revision != row.expected_review_resolution_revision
                or review.status != "pending"
            )
        )
        if human_changed:
            row.status = BoardCellGeometryPendingStatus.SUPERSEDED.value
            row.superseded_at = now
        else:
            if resolved_geometry_revision <= row.expected_geometry_revision:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_GEOMETRY_REVISION_INVALID",
                    "A resolution must advance the pinned geometry revision.",
                )
            row.status = BoardCellGeometryPendingStatus.RESOLVED.value
            row.resolved_geometry_revision = resolved_geometry_revision
            row.resolved_at = now
        row.updated_at = now
        self._session.flush()
        return _to_domain(row)


def _to_domain(row: ImageBoardGeometryPendingModel) -> ImageBoardGeometryPending:
    return ImageBoardGeometryPending(
        id=row.id,
        game_id=row.game_id,
        import_job_id=row.import_job_id,
        source_image_id=row.source_image_id,
        recognized_board_id=row.recognized_board_id,
        review_item_id=row.review_item_id,
        sequence_number=row.sequence_number,
        position_index=row.position_index,
        source_checksum_sha256=row.source_checksum_sha256,
        source_relative_path=row.source_relative_path,
        status=BoardCellGeometryPendingStatus(row.status),
        reason_code=BoardCellGeometryPendingReason(row.reason_code),
        processing_manifest_checksum_sha256=row.processing_manifest_checksum_sha256,
        processing_manifest_relative_path=row.processing_manifest_relative_path,
        pipeline_fingerprint_sha256=row.pipeline_fingerprint_sha256,
        expected_geometry_revision=row.expected_geometry_revision,
        expected_review_resolution_revision=row.expected_review_resolution_revision,
        resolved_geometry_revision=row.resolved_geometry_revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        superseded_at=row.superseded_at,
    )


__all__ = ["SqlAlchemyBoardCellGeometryPendingRepository"]
