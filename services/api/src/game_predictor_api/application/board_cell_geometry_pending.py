"""Application contract for deferred board-cell geometry work."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_COORDINATE_SPACE,
    BOARD_CELL_CORNER_SEMANTICS,
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    ManualBoardCellGeometryArtifacts,
    ManualBoardCellGeometryPreview,
    ManualBoardCellGeometryPreviewer,
    ManualBoardCellGeometryPreviewError,
)
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPrediction,
    ManualBoardCellSymbolPredictionError,
    ManualBoardCellSymbolPredictor,
)

from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    ImageBoardGeometryPending,
    board_cell_processing_artifact_relative_path,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ValidatedImageReviewGeometryCommand,
    canonical_image_review_bytes,
    validate_image_review_geometry_command,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError, JobNotFoundError
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

BoardCellPendingOrderKey = tuple[int, int, UUID]


@dataclass(frozen=True, slots=True)
class BoardCellGeometryPendingPage:
    items: tuple[ImageBoardGeometryPending, ...]
    counts: BoardCellGeometryJobCounts
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class BoardCellGeometryCorrectionContext:
    pending: ImageBoardGeometryPending
    source_order_index: int
    source_width: int
    source_height: int
    board_geometry: Mapping[str, object]
    board_confidence: float
    symbol_model: SymbolModelJobSnapshot


@dataclass(frozen=True, slots=True)
class BoardCellGeometryManualResolutionProjection:
    idempotency_key: UUID
    command: ValidatedImageReviewGeometryCommand
    command_sha256: str
    artifacts: ImageReviewGeometryArtifacts
    prediction: ManualBoardCellSymbolPrediction
    model_inference_fingerprint: str
    board_confidence: float


@dataclass(frozen=True, slots=True)
class BoardCellGeometryManualResolution:
    pending: ImageBoardGeometryPending
    review_item_id: UUID | None
    geometry_revision: int | None
    created: bool


class BoardCellGeometryPendingRepository(Protocol):
    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
        manifest_relative_path: str,
    ) -> tuple[ImageBoardGeometryPending, bool]: ...

    def get(self, pending_id: UUID) -> ImageBoardGeometryPending | None: ...

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        after_key: BoardCellPendingOrderKey | None,
        limit: int,
    ) -> Sequence[ImageBoardGeometryPending]: ...

    def counts(self, *, game_id: UUID, import_job_id: UUID) -> BoardCellGeometryJobCounts: ...

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending | None: ...

    def correction_context(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> BoardCellGeometryCorrectionContext | None: ...

    def materialize_manual_resolution(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        expected_manifest_checksum_sha256: str,
        projection: BoardCellGeometryManualResolutionProjection,
        created_at: datetime,
    ) -> BoardCellGeometryManualResolution | None: ...

    def manual_resolution_by_idempotency(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
    ) -> tuple[str, BoardCellGeometryManualResolution] | None: ...


class BoardCellProcessingManifestStore(Protocol):
    def put(self, manifest: BoardCellProcessingManifestV1) -> str: ...


class ManagedBoardCellProcessingManifestStore:
    """Content-addressed storage; no source image bytes are copied."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()

    def put(self, manifest: BoardCellProcessingManifestV1) -> str:
        relative_path = board_cell_processing_artifact_relative_path(manifest.checksum_sha256)
        target = (self._artifact_root / relative_path).resolve()
        if not target.is_relative_to(self._artifact_root):
            raise JobError(
                "IMAGE_BOARD_CELL_MANIFEST_PATH_INVALID",
                "The board-cell processing manifest path is unsafe.",
            )
        payload = manifest.canonical_bytes()
        if target.exists():
            if target.read_bytes() != payload:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_MANIFEST_CONFLICT",
                    "A different artifact already exists for the processing manifest checksum.",
                )
            return relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return relative_path


class BoardCellGeometryPendingService:
    def __init__(
        self,
        repository: BoardCellGeometryPendingRepository,
        manifest_store: BoardCellProcessingManifestStore,
        *,
        artifact_root: Path | None = None,
        previewer: ManualBoardCellGeometryPreviewer | None = None,
        predictor: ManualBoardCellSymbolPredictor | None = None,
    ) -> None:
        self._repository = repository
        self._manifest_store = manifest_store
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()
        self._previewer = previewer
        self._predictor = predictor

    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
    ) -> tuple[ImageBoardGeometryPending, bool]:
        relative_path = self._manifest_store.put(manifest)
        return self._repository.defer(
            manifest=manifest,
            reason_code=reason_code,
            manifest_relative_path=relative_path,
        )

    def get(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> ImageBoardGeometryPending:
        value = self._repository.get(pending_id)
        if value is None or value.game_id != game_id or value.import_job_id != import_job_id:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist in this import.",
            )
        return value

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        cursor: str | None,
        limit: int,
    ) -> BoardCellGeometryPendingPage:
        after_key = None if cursor is None else decode_board_cell_pending_cursor(cursor)
        values = tuple(
            self._repository.list(
                game_id=game_id,
                import_job_id=import_job_id,
                status=status,
                after_key=after_key,
                limit=limit + 1,
            )
        )
        has_more = len(values) > limit
        items = values[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_board_cell_pending_cursor(
                (last.sequence_number, last.position_index, last.id)
            )
        return BoardCellGeometryPendingPage(
            items=items,
            counts=self._repository.counts(game_id=game_id, import_job_id=import_job_id),
            next_cursor=next_cursor,
        )

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending:
        value = self._repository.resolve(
            pending_id=pending_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            resolved_geometry_revision=resolved_geometry_revision,
        )
        if value is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist.",
            )
        return value

    def correction_context(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> BoardCellGeometryCorrectionContext:
        value = self._repository.correction_context(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        if value is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist in this import.",
            )
        return value

    def preview_manual_resolution(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        corrected_by: str = "local-admin-preview",
        allow_resolved: bool = False,
    ) -> ManualBoardCellGeometryPreview:
        context = self.correction_context(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        self._require_pending_command(
            context,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            allow_resolved=allow_resolved,
        )
        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
        )
        previewer, artifact_root = self._manual_dependencies()
        source_path = _managed_source_path(artifact_root, context.pending.source_relative_path)
        try:
            return previewer.preview(
                source_path=source_path,
                expected_source_sha256=context.pending.source_checksum_sha256,
                review_item_id=str(context.pending.id),
                source_order_index=context.source_order_index,
                source_image_id=str(context.pending.source_image_id),
                source_image_relative_path=context.pending.source_relative_path,
                source_group=str(context.pending.import_job_id),
                sequence_number=context.pending.sequence_number,
                position_index=context.pending.position_index,
                lattice_bounds_quad=(
                    (float(command.corners[0].x), float(command.corners[0].y)),
                    (float(command.corners[1].x), float(command.corners[1].y)),
                    (float(command.corners[2].x), float(command.corners[2].y)),
                    (float(command.corners[3].x), float(command.corners[3].y)),
                ),
                corrected_by=command.corrected_by,
                expected_geometry_revision=command.expected_geometry_revision,
                expected_resolution_revision=command.expected_resolution_revision,
                command_checksum_sha256=command.command_sha256,
            )
        except ManualBoardCellGeometryPreviewError as error:
            raise JobConflictError(error.code, str(error)) from error

    def resolve_manual(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        expected_manifest_checksum_sha256: str,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        corrected_by: str,
        resolved_at: datetime,
    ) -> BoardCellGeometryManualResolution:
        context = self.correction_context(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        self._require_pending_command(
            context,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            allow_resolved=True,
        )
        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
        )
        resolution_command_sha256 = _manual_resolution_command_sha256(
            pending_id=pending_id,
            manifest_checksum_sha256=expected_manifest_checksum_sha256,
            geometry_command_sha256=command.command_sha256,
            model_inference_fingerprint=context.symbol_model.inference_fingerprint,
        )
        prior = self._repository.manual_resolution_by_idempotency(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            prior_checksum, resolution = prior
            if prior_checksum != resolution_command_sha256:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another manual correction.",
                )
            return resolution
        if context.pending.status is BoardCellGeometryPendingStatus.RESOLVED:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT",
                "The deferred geometry item was already resolved by another command.",
            )
        preview = self.preview_manual_resolution(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corners=corners,
            corrected_by=corrected_by,
            allow_resolved=True,
        )
        previewer, artifact_root = self._manual_dependencies()
        if self._predictor is None:
            raise JobError(
                "IMAGE_BOARD_CELL_MANUAL_PREDICTION_UNAVAILABLE",
                "Manual deferred geometry symbol inference is not configured.",
            )
        try:
            prediction = self._predictor.predict(preview, context.symbol_model)
            persisted = previewer.persist(
                preview=preview,
                managed_data_root=artifact_root / "data",
                revision=expected_geometry_revision + 1,
                namespace_discriminator=preview.decision_checksum_sha256,
            )
        except (
            ManualBoardCellGeometryPreviewError,
            ManualBoardCellSymbolPredictionError,
        ) as error:
            raise JobConflictError(error.code, str(error)) from error
        geometry = _manual_geometry_payload(context, persisted)
        artifacts = ImageReviewGeometryArtifacts(
            geometry=geometry,
            board_relative_path=context.pending.source_relative_path,
            board_checksum_sha256=context.pending.source_checksum_sha256,
            cropper_version=persisted.cropper_version,
            cells=tuple(
                ImageReviewGeometryCellArtifact(
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    crop_relative_path=cell.relative_path,
                    crop_checksum_sha256=cell.checksum_sha256,
                )
                for cell in persisted.cells
            ),
        )
        value = self._repository.materialize_manual_resolution(
            pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            projection=BoardCellGeometryManualResolutionProjection(
                idempotency_key=idempotency_key,
                command=command,
                command_sha256=resolution_command_sha256,
                artifacts=artifacts,
                prediction=prediction,
                model_inference_fingerprint=context.symbol_model.inference_fingerprint,
                board_confidence=context.board_confidence,
            ),
            created_at=resolved_at,
        )
        if value is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item no longer exists.",
            )
        return value

    @staticmethod
    def _require_pending_command(
        context: BoardCellGeometryCorrectionContext,
        *,
        expected_manifest_checksum_sha256: str,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        allow_resolved: bool = False,
    ) -> None:
        pending = context.pending
        if pending.processing_manifest_checksum_sha256 != expected_manifest_checksum_sha256:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_MANIFEST_CONFLICT",
                "The deferred geometry item was loaded from another processing manifest.",
            )
        if (
            pending.expected_geometry_revision != expected_geometry_revision
            or pending.expected_review_resolution_revision != expected_resolution_revision
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT",
                "The deferred geometry item changed after it was loaded.",
            )
        if pending.status is BoardCellGeometryPendingStatus.SUPERSEDED or (
            pending.status is BoardCellGeometryPendingStatus.RESOLVED and not allow_resolved
        ):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE",
                "The deferred geometry item is no longer editable.",
            )

    def _manual_dependencies(self) -> tuple[ManualBoardCellGeometryPreviewer, Path]:
        if self._previewer is None or self._artifact_root is None:
            raise JobError(
                "IMAGE_BOARD_CELL_MANUAL_PREVIEW_UNAVAILABLE",
                "Manual deferred board-cell geometry preview is not configured.",
            )
        return self._previewer, self._artifact_root


def _managed_source_path(artifact_root: Path, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise JobError(
            "IMAGE_BOARD_CELL_SOURCE_PATH_INVALID",
            "The deferred geometry source path is unsafe.",
        )
    relative = Path(*normalized.split("/"))
    data_root = (artifact_root / "data").resolve()
    candidate = (data_root / relative).resolve()
    if not candidate.is_relative_to(data_root):
        raise JobError(
            "IMAGE_BOARD_CELL_SOURCE_PATH_INVALID",
            "The deferred geometry source path is unsafe.",
        )
    return candidate


def _manual_geometry_payload(
    context: BoardCellGeometryCorrectionContext,
    persisted: ManualBoardCellGeometryArtifacts,
) -> dict[str, object]:
    geometry = dict(context.board_geometry)
    geometry.update(
        {
            "cellOutputSize": persisted.cell_output_size,
            "cells": [
                {
                    "columnIndex": cell.column_index,
                    "cropChecksumSha256": cell.checksum_sha256,
                    "paddedSourceQuad": [
                        {"x": round(x, 4), "y": round(y, 4)} for x, y in cell.padded_source_quad
                    ],
                    "rowIndex": cell.row_index,
                    "sourceQuad": [
                        {"x": round(x, 4), "y": round(y, 4)} for x, y in cell.source_quad
                    ],
                }
                for cell in persisted.cells
            ],
            "commandChecksumSha256": persisted.command_checksum_sha256,
            "coordinateSpace": BOARD_CELL_COORDINATE_SPACE,
            "cornerSemantics": BOARD_CELL_CORNER_SEMANTICS,
            "correctedBy": persisted.corrected_by,
            "cropperFingerprintSha256": persisted.cropper_fingerprint_sha256,
            "cropperVersion": persisted.cropper_version,
            "decisionChecksumSha256": persisted.decision_checksum_sha256,
            "expectedGeometryRevision": persisted.expected_geometry_revision,
            "expectedResolutionRevision": persisted.expected_resolution_revision,
            "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
            "imageHeight": persisted.image_height,
            "imageWidth": persisted.image_width,
            "latticeBoundsQuad": [
                {"x": round(x, 4), "y": round(y, 4)} for x, y in persisted.lattice_bounds_quad
            ],
            "manualGeometryVersion": persisted.manual_geometry_version,
            "positionIndex": persisted.position_index,
            "sequenceNumber": persisted.sequence_number,
            "sequenceSource": "filename",
            "source": "manual_override",
            "sourceGroup": persisted.source_group,
            "sourceImageChecksumSha256": persisted.source_image_checksum_sha256,
            "sourceImageId": persisted.source_image_id,
            "sourceImageRelativePath": persisted.source_image_relative_path,
            "sourceOrderIndex": persisted.source_order_index,
        }
    )
    return geometry


def _manual_resolution_command_sha256(
    *,
    pending_id: UUID,
    manifest_checksum_sha256: str,
    geometry_command_sha256: str,
    model_inference_fingerprint: str,
) -> str:
    return hashlib.sha256(
        canonical_image_review_bytes(
            {
                "geometryCommandSha256": geometry_command_sha256,
                "manifestChecksumSha256": manifest_checksum_sha256,
                "modelInferenceFingerprint": model_inference_fingerprint,
                "pendingId": str(pending_id),
            }
        )
    ).hexdigest()


def encode_board_cell_pending_cursor(key: BoardCellPendingOrderKey) -> str:
    payload = json.dumps([key[0], key[1], str(key[2])], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_board_cell_pending_cursor(value: str) -> BoardCellPendingOrderKey:
    try:
        payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        sequence, position, pending_id = json.loads(payload)
        if not isinstance(sequence, int) or sequence < 1:
            raise ValueError
        if not isinstance(position, int) or not 0 <= position <= 8:
            raise ValueError
        return sequence, position, UUID(pending_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise JobError(
            "IMAGE_BOARD_CELL_PENDING_CURSOR_INVALID",
            "The deferred board-cell geometry cursor is invalid.",
        ) from error


__all__ = [
    "BoardCellGeometryCorrectionContext",
    "BoardCellGeometryManualResolution",
    "BoardCellGeometryManualResolutionProjection",
    "BoardCellGeometryPendingPage",
    "BoardCellGeometryPendingRepository",
    "BoardCellGeometryPendingService",
    "BoardCellProcessingManifestStore",
    "ManagedBoardCellProcessingManifestStore",
    "decode_board_cell_pending_cursor",
    "encode_board_cell_pending_cursor",
]
