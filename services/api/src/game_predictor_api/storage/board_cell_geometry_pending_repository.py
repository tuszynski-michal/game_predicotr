"""PostgreSQL persistence for deferred board-cell geometry work."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryCorrectionContext,
    BoardCellGeometryManualResolution,
    BoardCellGeometryManualResolutionProjection,
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
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.pending_sequence_ownership import (
    create_owned_pending_review_item,
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
        geometry = _validated_detected_board_geometry(
            board.get("geometry"),
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

    def materialize_manual_resolution(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        expected_manifest_checksum_sha256: str,
        projection: BoardCellGeometryManualResolutionProjection,
        created_at: datetime,
    ) -> BoardCellGeometryManualResolution | None:
        row = self._session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(
                ImageBoardGeometryPendingModel.id == pending_id,
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.import_job_id == import_job_id,
            )
            .with_for_update()
        )
        if row is None:
            return None
        if row.processing_manifest_checksum_sha256 != expected_manifest_checksum_sha256:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_MANIFEST_CONFLICT",
                "The deferred geometry item was loaded from another processing manifest.",
            )
        prior = (
            self._session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.review_item_id == row.review_item_id,
                    ImageBoardGeometryRevisionModel.idempotency_key == projection.idempotency_key,
                )
            )
            if row.review_item_id is not None
            else None
        )
        if prior is not None:
            if prior.command_sha256 != projection.command_sha256:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another manual correction.",
                )
            return BoardCellGeometryManualResolution(
                pending=_to_domain(row),
                review_item_id=prior.review_item_id,
                geometry_revision=prior.revision,
                created=False,
            )
        if row.status == BoardCellGeometryPendingStatus.RESOLVED.value:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT",
                "The deferred geometry item was already resolved by another command.",
            )
        if row.status == BoardCellGeometryPendingStatus.SUPERSEDED.value:
            return BoardCellGeometryManualResolution(
                pending=_to_domain(row),
                review_item_id=row.review_item_id,
                geometry_revision=None,
                created=False,
            )
        source = self._session.get(SourceImageModel, row.source_image_id, with_for_update=True)
        job = self._session.get(JobModel, import_job_id)
        if (
            source is None
            or job is None
            or job.game_id != game_id
            or source.import_job_id != import_job_id
            or source.checksum_sha256 != row.source_checksum_sha256
            or source.relative_path != row.source_relative_path
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_CONTEXT_INVALID",
                "The deferred geometry source changed before manual resolution.",
            )
        existing_board = self._session.scalar(
            select(RecognizedBoardModel)
            .where(
                RecognizedBoardModel.source_image_id == row.source_image_id,
                RecognizedBoardModel.position_index == row.position_index,
            )
            .with_for_update()
        )
        if existing_board is not None:
            row.status = BoardCellGeometryPendingStatus.SUPERSEDED.value
            row.superseded_at = created_at
            row.updated_at = created_at
            self._session.flush()
            return BoardCellGeometryManualResolution(
                pending=_to_domain(row),
                review_item_id=row.review_item_id,
                geometry_revision=None,
                created=False,
            )
        try:
            current_model = SymbolModelJobSnapshot.from_payload(
                job.input_payload.get("symbol_model")
            )
        except ValueError as error:
            raise JobConflictError(
                "IMAGE_SYMBOL_MODEL_SNAPSHOT_INVALID",
                "The deferred geometry import has an invalid pinned symbol model.",
            ) from error
        if current_model.inference_fingerprint != projection.model_inference_fingerprint:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_MODEL_CONFLICT",
                "The pinned symbol model changed before manual resolution.",
            )
        artifacts = projection.artifacts
        expected_order = [(r, c) for r in range(3) for c in range(5)]
        if (
            len(artifacts.cells) != 15
            or [(cell.row_index, cell.column_index) for cell in artifacts.cells] != expected_order
            or len(projection.prediction.cells) != 15
            or [
                (prediction.get("rowIndex"), prediction.get("columnIndex"))
                for prediction in projection.prediction.cells
            ]
            != expected_order
            or not _manual_projection_matches(
                row,
                source,
                current_model,
                projection,
            )
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_PROJECTION_INVALID",
                "Manual resolution requires exactly 15 row-major crops and predictions.",
            )
        prediction_payload = {
            "cells": list(projection.prediction.cells),
            "modelIterationId": projection.prediction.model_iteration_id,
            "modelManifestChecksumSha256": (projection.prediction.model_manifest_checksum_sha256),
            "modelVersion": projection.prediction.model_version,
            "temperatureApplied": projection.prediction.temperature_applied,
        }
        board = RecognizedBoardModel(
            source_image_id=source.id,
            position_index=row.position_index,
            sequence_number_raw=str(row.sequence_number),
            sequence_number=row.sequence_number,
            sequence_confidence=1.0,
            board_geometry=dict(artifacts.geometry),
            board_relative_path=artifacts.board_relative_path,
            board_checksum_sha256=artifacts.board_checksum_sha256,
            cells_prediction=prediction_payload,
            board_confidence=projection.board_confidence,
            pipeline_fingerprint=row.pipeline_fingerprint_sha256,
            geometry_revision=row.expected_geometry_revision + 1,
            status="pending_review",
            created_at=created_at,
        )
        self._session.add(board)
        self._session.flush()
        for artifact, prediction in zip(
            artifacts.cells,
            projection.prediction.cells,
            strict=True,
        ):
            self._session.add(
                CellObservationModel(
                    recognized_board_id=board.id,
                    row_index=artifact.row_index,
                    column_index=artifact.column_index,
                    crop_relative_path=artifact.crop_relative_path,
                    crop_checksum_sha256=artifact.crop_checksum_sha256,
                    cropper_version=artifacts.cropper_version,
                    prediction=dict(prediction),
                    created_at=created_at,
                )
            )
        review, ownership_changes = create_owned_pending_review_item(
            self._session,
            board=board,
            game_id=game_id,
            import_job=job,
            snapshot={
                "boardChecksumSha256": artifacts.board_checksum_sha256,
                "boardRelativePath": artifacts.board_relative_path,
                "cells": list(projection.prediction.cells),
                "geometry": dict(artifacts.geometry),
                "pipelineFingerprint": row.pipeline_fingerprint_sha256,
                "positionIndex": row.position_index,
                "sequence": {
                    "confidence": 1.0,
                    "normalizedNumber": row.sequence_number,
                    "positionIndex": row.position_index,
                    "rawText": str(row.sequence_number),
                    "reviewReasons": [],
                    "sequenceSource": "filename",
                },
                "sourceChecksumSha256": source.checksum_sha256,
                "sourceRelativePath": source.relative_path,
            },
            created_at=created_at,
            resolution_revision=row.expected_review_resolution_revision,
        )
        revision = board.geometry_revision
        self._session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review.id,
                recognized_board_id=board.id,
                revision=revision,
                idempotency_key=projection.idempotency_key,
                command_sha256=projection.command_sha256,
                corners=[{"x": point.x, "y": point.y} for point in projection.command.corners],
                geometry=dict(artifacts.geometry),
                board_relative_path=artifacts.board_relative_path,
                board_checksum_sha256=artifacts.board_checksum_sha256,
                cropper_version=artifacts.cropper_version,
                crop_artifacts=[
                    {
                        "columnIndex": cell.column_index,
                        "cropChecksumSha256": cell.crop_checksum_sha256,
                        "cropRelativePath": cell.crop_relative_path,
                        "rowIndex": cell.row_index,
                    }
                    for cell in artifacts.cells
                ],
                corrected_by=projection.command.corrected_by,
                created_at=created_at,
            )
        )
        row.recognized_board_id = board.id
        row.review_item_id = review.id
        row.status = BoardCellGeometryPendingStatus.RESOLVED.value
        row.resolved_geometry_revision = revision
        row.resolved_at = created_at
        row.updated_at = created_at
        source.status = "waiting_for_review" if review.status == "pending" else "completed"
        source.processed_at = created_at
        self._session.flush()
        SqlAlchemyBoardSearchProjectionRepository(self._session).sync_review_items(
            ownership_changes
        )
        coordinator = SymbolCellReviewWriteThroughCoordinator(self._session)
        for changed_review_item_id in ownership_changes:
            coordinator.synchronize_after_geometry_change(
                game_id=game_id,
                review_item_id=changed_review_item_id,
                actor=projection.command.corrected_by,
            )
        coordinator.synchronize_after_projection_change(game_id=game_id)
        return BoardCellGeometryManualResolution(
            pending=_to_domain(row),
            review_item_id=review.id,
            geometry_revision=revision,
            created=True,
        )

    def manual_resolution_by_idempotency(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
    ) -> tuple[str, BoardCellGeometryManualResolution] | None:
        row = self._session.get(ImageBoardGeometryPendingModel, pending_id)
        if (
            row is None
            or row.game_id != game_id
            or row.import_job_id != import_job_id
            or row.review_item_id is None
        ):
            return None
        revision = self._session.scalar(
            select(ImageBoardGeometryRevisionModel).where(
                ImageBoardGeometryRevisionModel.review_item_id == row.review_item_id,
                ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
            )
        )
        if revision is None:
            return None
        return (
            revision.command_sha256,
            BoardCellGeometryManualResolution(
                pending=_to_domain(row),
                review_item_id=revision.review_item_id,
                geometry_revision=revision.revision,
                created=False,
            ),
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


def _validated_detected_board_geometry(
    value: object,
    *,
    source_width: int,
    source_height: int,
) -> dict[str, object]:
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
            or not 0 <= float(x) <= source_width
            or not 0 <= float(y) <= source_height
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID",
                "The pinned board quad is outside the immutable source bounds.",
            )
    return dict(value)


def _manual_projection_matches(
    row: ImageBoardGeometryPendingModel,
    source: SourceImageModel,
    model: SymbolModelJobSnapshot,
    projection: BoardCellGeometryManualResolutionProjection,
) -> bool:
    artifacts = projection.artifacts
    geometry = artifacts.geometry
    prediction = projection.prediction
    expected_iteration = None if model.iteration_id is None else str(model.iteration_id)
    if (
        projection.command.expected_geometry_revision != row.expected_geometry_revision
        or projection.command.expected_resolution_revision
        != row.expected_review_resolution_revision
        or artifacts.board_relative_path != source.relative_path
        or artifacts.board_checksum_sha256 != source.checksum_sha256
        or geometry.get("source") != "manual_override"
        or geometry.get("sourceImageId") != str(source.id)
        or geometry.get("sourceImageChecksumSha256") != source.checksum_sha256
        or geometry.get("sourceImageRelativePath") != source.relative_path
        or geometry.get("sourceGroup") != str(row.import_job_id)
        or geometry.get("sequenceNumber") != row.sequence_number
        or geometry.get("positionIndex") != row.position_index
        or geometry.get("expectedGeometryRevision") != row.expected_geometry_revision
        or geometry.get("expectedResolutionRevision") != row.expected_review_resolution_revision
        or geometry.get("commandChecksumSha256") != projection.command.command_sha256
        or geometry.get("cropperVersion") != artifacts.cropper_version
        or prediction.model_iteration_id != expected_iteration
        or prediction.model_manifest_checksum_sha256 != model.manifest_checksum_sha256
        or prediction.model_version != model.model_version
        or not math.isfinite(projection.board_confidence)
        or not 0 <= projection.board_confidence <= 1
    ):
        return False
    return all(
        _is_safe_relative_path(cell.crop_relative_path) and _is_sha256(cell.crop_checksum_sha256)
        for cell in artifacts.cells
    )


def _is_safe_relative_path(value: str) -> bool:
    relative = PurePosixPath(value)
    return (
        bool(value)
        and not relative.is_absolute()
        and ".." not in relative.parts
        and "\\" not in value
    )


def _is_sha256(value: str) -> bool:
    if len(value) != 64 or value != value.lower():
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


__all__ = ["SqlAlchemyBoardCellGeometryPendingRepository"]
