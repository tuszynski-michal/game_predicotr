"""PostgreSQL persistence for deferred board-cell geometry work.

The manual resolution of a deferred board is persisted by the virtual source
path (``SqlAlchemyVirtualGridGeometryRepository``); this repository only
defers, lists, resolves automatically and reads the correction context
(D-467, TASK-0790).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryCorrectionContext,
    BoardCellPendingOrderKey,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    BoardRejectionReason,
    ImageBoardGeometryPending,
    rejection_command_sha256,
)
from game_predictor_api.domain.jobs import JobConflictError, JobNotFoundError
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageBoardGeometryPendingEventModel,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import (
    acquire_image_sequence_locks,
    acquire_sequence_ownership_lock,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


def _rejection_lock_key(game_id: UUID, idempotency_key: UUID) -> int:
    """Transaction advisory lock key of one slot-rejection request (signed 64-bit)."""

    digest = hashlib.sha256(
        f"pending-slot-rejection:{game_id}:{idempotency_key}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


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
                    review.resolution_revision != manifest.expected_review_resolution_revision
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
        # D-484 (TASK-0807): an open deferred slot keeps the image incomplete.
        recompute_source_image_geometry_completeness(
            self._session, manifest.game_id, manifest.source_image_id
        )
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
                func.sum(
                    case(
                        (ImageBoardGeometryPendingModel.status == "rejected", 1),
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
        recompute_source_image_geometry_completeness(
            self._session, row.game_id, row.source_image_id
        )
        return _to_domain(row)

    def reject(
        self,
        *,
        pending_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        reason: BoardRejectionReason,
        note: str | None,
        rejected_by: str,
        rejected_at: datetime,
    ) -> tuple[ImageBoardGeometryPending, UUID, bool]:
        """Reject an open deferred slot (TASK-0949, W7/W8); returns ``(slot, event id, created)``.

        Locks in the order of the manual resolution (sequence -> source ->
        slot). The position stays a gap for the gate (D-484): the image is
        recomputed in this transaction and remains incomplete, so no other
        board of it gets cells. The command is identified durably by its
        idempotency key (``image_board_geometry_pending_events``): the same key
        with the same command replays the stored rejection without touching
        the slot, even after the rejection was reverted; the same key with
        another command conflicts; a rejected slot refuses any other key.
        """

        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.WRITE)
        command_sha256 = rejection_command_sha256(
            pending_id=pending_id,
            reason=reason,
            note=note,
            expected_geometry_revision=expected_geometry_revision,
        )
        # Requests with one key run one after another: a retry that arrives
        # while the first one commits waits and then reads the stored result.
        self._session.execute(
            select(func.pg_advisory_xact_lock(_rejection_lock_key(game_id, idempotency_key)))
        )
        known = self._session.scalar(
            select(ImageBoardGeometryPendingModel).where(
                ImageBoardGeometryPendingModel.id == pending_id,
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.import_job_id == import_job_id,
            )
        )
        if known is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist in this import.",
            )
        prior = self._session.scalar(
            select(ImageBoardGeometryPendingEventModel).where(
                ImageBoardGeometryPendingEventModel.game_id == game_id,
                ImageBoardGeometryPendingEventModel.idempotency_key == idempotency_key,
            )
        )
        if prior is not None:
            if (
                prior.action != "rejected"
                or prior.pending_geometry_id != pending_id
                or prior.command_sha256 != command_sha256
            ):
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another command.",
                )
            return _to_domain(known), prior.id, False
        acquire_sequence_ownership_lock(self._session, game_id=game_id)
        acquire_image_sequence_locks(
            self._session, game_id=game_id, sequence_numbers={known.sequence_number}
        )
        self._session.execute(
            select(SourceImageModel.id)
            .where(SourceImageModel.id == known.source_image_id)
            .with_for_update()
        )
        row = self._session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(ImageBoardGeometryPendingModel.id == pending_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert row is not None
        if row.status == BoardCellGeometryPendingStatus.REJECTED.value:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_ALREADY_REJECTED",
                "The deferred geometry item is already rejected.",
            )
        if row.status != BoardCellGeometryPendingStatus.PENDING.value:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE",
                "Only an open deferred slot can be rejected; revert its correction first.",
            )
        if row.expected_geometry_revision != expected_geometry_revision:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT",
                "The deferred geometry item changed after it was loaded.",
            )
        occupied = self._session.scalar(
            select(RecognizedBoardModel.id)
            .where(
                RecognizedBoardModel.source_image_id == row.source_image_id,
                RecognizedBoardModel.position_index == row.position_index,
            )
            .with_for_update()
        )
        if occupied is not None:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE",
                "A board already exists at this position; reject that board instead.",
            )
        revision = (
            self._session.scalar(
                select(func.max(ImageBoardGeometryPendingEventModel.rejection_revision)).where(
                    ImageBoardGeometryPendingEventModel.game_id == game_id,
                    ImageBoardGeometryPendingEventModel.pending_geometry_id == pending_id,
                )
            )
            or 0
        ) + 1
        event = ImageBoardGeometryPendingEventModel(
            id=uuid4(),
            game_id=game_id,
            import_job_id=import_job_id,
            pending_geometry_id=pending_id,
            rejection_revision=revision,
            action="rejected",
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
            reason=reason.value,
            note=note,
            actor=rejected_by,
            created_at=rejected_at,
        )
        self._session.add(event)
        row.status = BoardCellGeometryPendingStatus.REJECTED.value
        row.rejection_reason = reason.value
        row.rejection_note = note
        row.rejected_at = rejected_at
        row.rejected_by = rejected_by
        row.updated_at = rejected_at
        self._session.flush()
        recompute_source_image_geometry_completeness(
            self._session,
            game_id,
            row.source_image_id,
            actor=rejected_by,
            now=rejected_at,
        )
        settle_source_status_after_slot_rejection(self._session, game_id, row.source_image_id)
        return _to_domain(row), event.id, True

    def correction_context(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> BoardCellGeometryCorrectionContext | None:
        row = self._session.get(ImageBoardGeometryPendingModel, pending_id)
        if row is None or row.game_id != game_id or row.import_job_id != import_job_id:
            return None
        source = self._session.get(SourceImageModel, row.source_image_id)
        job = self._session.get(JobModel, import_job_id)
        if source is None or job is None or source.import_job_id != import_job_id:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_CONTEXT_INVALID",
                "The deferred geometry source or import no longer matches persistence.",
            )
        association = self._session.get(
            ImageImportJobFileModel,
            {
                "job_id": import_job_id,
                "file_execution_key": source.file_execution_key,
            },
        )
        detection = self._session.get(
            ImagePipelineStageResultModel,
            {
                "file_execution_key": source.file_execution_key,
                "stage": "board_detection",
            },
        )
        if association is None or detection is None:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_CONTEXT_MISSING",
                "The deferred geometry source order or board detection is unavailable.",
            )
        board = _detected_board(detection.result_payload, row.position_index)
        try:
            symbol_model = SymbolModelJobSnapshot.from_payload(
                job.input_payload.get("symbol_model")
            )
        except ValueError as error:
            raise JobConflictError(
                "IMAGE_SYMBOL_MODEL_SNAPSHOT_INVALID",
                "The deferred geometry import has an invalid pinned symbol model.",
            ) from error
        confidence = board.get("confidence")
        raw_geometry = board.get("geometry")
        if (
            isinstance(raw_geometry, Mapping)
            and raw_geometry.get("quad") is None
            and raw_geometry.get("pageBoardQuad") is None
            and raw_geometry.get("structuredDisposition") == "needs_manual_review"
        ):
            revision = self._session.scalar(
                select(ImageSourceGeometryRevisionModel).where(
                    ImageSourceGeometryRevisionModel.game_id == game_id,
                    ImageSourceGeometryRevisionModel.source_image_id == source.id,
                    ImageSourceGeometryRevisionModel.revision == 0,
                    ImageSourceGeometryRevisionModel.source_checksum_sha256
                    == row.source_checksum_sha256,
                )
            )
            if revision is not None:
                raw_geometry = _manual_draft_from_source_revision(
                    revision.board_geometries,
                    position_index=row.position_index,
                    sequence_number=row.sequence_number,
                )
        geometry = _validated_detected_board_geometry(
            raw_geometry,
            source_width=source.width,
            source_height=source.height,
        )
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, int | float)
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
                "The pinned board detection is incomplete for manual correction.",
            )
        return BoardCellGeometryCorrectionContext(
            pending=_to_domain(row),
            source_order_index=association.order_index,
            source_width=source.width,
            source_height=source.height,
            board_geometry=geometry,
            board_confidence=float(confidence),
            symbol_model=symbol_model,
        )


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
        rejection_reason=(
            None if row.rejection_reason is None else BoardRejectionReason(row.rejection_reason)
        ),
        rejection_note=row.rejection_note,
        rejected_at=row.rejected_at,
        rejected_by=row.rejected_by,
    )


def _detected_board(
    payload: object,
    position_index: int,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned board detection payload is invalid.",
        )
    boards = payload.get("boards")
    if not isinstance(boards, list):
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned board detection has no board list.",
        )
    matches = [
        value
        for value in boards
        if isinstance(value, dict) and value.get("positionIndex") == position_index
    ]
    if len(matches) != 1:
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned board position is missing or ambiguous.",
        )
    return matches[0]


def _manual_draft_from_source_revision(
    boards: object,
    *,
    position_index: int,
    sequence_number: int,
) -> dict[str, object]:
    """Recover only the pinned initial proposal, never approve failed geometry."""
    matches = (
        [
            board
            for board in boards
            if isinstance(board, Mapping)
            and board.get("positionIndex") == position_index
            and board.get("sequenceNumber") == sequence_number
        ]
        if isinstance(boards, list)
        else []
    )
    if len(matches) != 1:
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned source revision has no unique draft for this board.",
        )
    return {"quad": matches[0].get("initialQuad"), "source": "manual_review_draft"}


def _validated_detected_board_geometry(
    value: object,
    *,
    source_width: int,
    source_height: int,
) -> dict[str, object]:
    """Accept the pinned draft within the manual edit bounds, not the image.

    A detected board may extend past the image edge (partially visible cells,
    D-436). The draft only seeds manual correction, so it uses the same
    one-width/one-height margin as ``SourceQuad.require_manual_edit_bounds``;
    the save path still validates the corrected geometry on its own.
    """
    if not isinstance(value, Mapping):
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned board geometry is unavailable for manual correction.",
        )
    raw_quad = value.get("quad") or value.get("pageBoardQuad")
    if (
        isinstance(raw_quad, str | bytes)
        or not isinstance(raw_quad, Sequence)
        or len(raw_quad) != 4
    ):
        raise JobConflictError(
            "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
            "The pinned board geometry has no unambiguous four-corner quad.",
        )
    for point in raw_quad:
        if not isinstance(point, Mapping):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
                "The pinned board quad is invalid.",
            )
        x, y = point.get("x"), point.get("y")
        if (
            isinstance(x, bool)
            or not isinstance(x, int | float)
            or isinstance(y, bool)
            or not isinstance(y, int | float)
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
            or not -source_width <= float(x) <= 2 * source_width
            or not -source_height <= float(y) <= 2 * source_height
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
                "The pinned board quad exceeds the manual edit bounds of the source.",
            )
    return dict(value)


_OPEN_WORK_SQL = text(
    """
SELECT EXISTS (
  SELECT 1 FROM image_board_geometry_pending p
  WHERE p.game_id = :game_id AND p.source_image_id = :source_image_id AND p.status = 'pending'
) OR EXISTS (
  SELECT 1 FROM recognized_boards b
  JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
  WHERE b.game_id = :game_id AND b.source_image_id = :source_image_id AND ri.status = 'pending'
)
"""
)
_ACCEPTED_BOARD_SQL = text(
    """
SELECT EXISTS (
  SELECT 1 FROM recognized_boards b
  JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
  WHERE b.game_id = :game_id AND b.source_image_id = :source_image_id
    AND ri.status IN ('accepted', 'corrected')
)
"""
)


def settle_source_status_after_slot_rejection(
    session: Session, game_id: UUID, source_image_id: UUID
) -> None:
    """Source image status once a deferred slot stopped being open work.

    The status follows ``_refresh_source_states`` of the board decisions: an
    image with no open slot or pending board is ``accepted`` when it keeps an
    accepted board, else ``rejected``. A status other than ``waiting_for_review``
    (the image is still being processed) is left alone.
    """

    parameters = {"game_id": game_id, "source_image_id": source_image_id}
    source = session.get(SourceImageModel, source_image_id, populate_existing=True)
    if source is None or source.status != "waiting_for_review":
        return
    if session.execute(_OPEN_WORK_SQL, parameters).scalar():
        return
    has_accepted = session.execute(_ACCEPTED_BOARD_SQL, parameters).scalar()
    source.status = "accepted" if has_accepted else "rejected"
    session.flush()


__all__ = [
    "SqlAlchemyBoardCellGeometryPendingRepository",
    "settle_source_status_after_slot_rejection",
]
