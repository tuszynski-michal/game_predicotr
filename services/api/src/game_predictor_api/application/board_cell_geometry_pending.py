"""Application contract for deferred board-cell geometry work.

D-467 (TASK-0790): a deferred board is resolved manually only through the
virtual source path (``VirtualGridGeometryService.save_pending_slot``), the
same path as the Admin source correction.  The result is one ``virtual_source``
board with a render manifest; no file crops and no cell observations exist.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridCellSymbol,
    VirtualGridCellSymbolSuggestion,
    VirtualGridGeometryPreview,
    VirtualGridGeometryService,
)
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    BoardRejectionReason,
    ImageBoardGeometryPending,
    board_cell_processing_artifact_relative_path,
    normalized_rejection_note,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryPoint,
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
class BoardCellGeometryRejection:
    pending: ImageBoardGeometryPending
    counts: BoardCellGeometryJobCounts
    created: bool
    # The durable event of the rejection (its id is what the revert addresses).
    rejection_id: UUID


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
    ) -> tuple[ImageBoardGeometryPending, UUID, bool]: ...


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
        virtual_geometry: VirtualGridGeometryService | None = None,
    ) -> None:
        self._repository = repository
        self._manifest_store = manifest_store
        self._virtual_geometry = virtual_geometry

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
        geometry_qualification: GeometryQualification | None = None,
        lattice_nodes: SourceLatticeNodes | None = None,
        expected_proposal_checksum_sha256: str | None = None,
    ) -> VirtualGridGeometryPreview:
        """Contact sheet of the virtual cells a resolution would persist."""

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
        )
        validate_image_review_geometry_command(
            corners=corners,
            lattice_nodes=lattice_nodes,
            expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
            geometry_qualification=geometry_qualification,
        )
        return self._require_virtual_geometry().preview_pending_slot(
            game_id=game_id,
            import_job_id=import_job_id,
            pending_geometry_id=pending_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corners=corners,
            lattice_nodes=lattice_nodes,
            expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
            geometry_qualification=geometry_qualification,
            actor=corrected_by,
        )

    def preview_manual_symbols(
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
        geometry_qualification: GeometryQualification | None = None,
        lattice_nodes: SourceLatticeNodes | None = None,
        expected_proposal_checksum_sha256: str | None = None,
    ) -> tuple[VirtualGridCellSymbolSuggestion, ...]:
        """Model symbols of the cells a resolution would persist (D-488)."""

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
        )
        validate_image_review_geometry_command(
            corners=corners,
            lattice_nodes=lattice_nodes,
            expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
            geometry_qualification=geometry_qualification,
        )
        return self._require_virtual_geometry().preview_pending_slot_symbols(
            game_id=game_id,
            import_job_id=import_job_id,
            pending_geometry_id=pending_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corners=corners,
            lattice_nodes=lattice_nodes,
            expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
            geometry_qualification=geometry_qualification,
            actor=corrected_by,
        )

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
        geometry_qualification: GeometryQualification | None = None,
        cell_symbols: Sequence[VirtualGridCellSymbol] = (),
        lattice_nodes: SourceLatticeNodes | None = None,
        expected_proposal_checksum_sha256: str | None = None,
    ) -> BoardCellGeometryManualResolution:
        """Persist the deferred board as one ``virtual_source`` board (D-467).

        A retry with the same idempotency key and command returns the stored
        revision with ``created=False``; the same key with another command is
        an idempotency conflict.
        """

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
        validate_image_review_geometry_command(
            corners=corners,
            lattice_nodes=lattice_nodes,
            expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
            geometry_qualification=geometry_qualification,
        )
        try:
            result = self._require_virtual_geometry().save_pending_slot(
                game_id=game_id,
                import_job_id=import_job_id,
                pending_geometry_id=pending_id,
                idempotency_key=idempotency_key,
                expected_geometry_revision=expected_geometry_revision,
                expected_resolution_revision=expected_resolution_revision,
                corners=corners,
                lattice_nodes=lattice_nodes,
                expected_proposal_checksum_sha256=expected_proposal_checksum_sha256,
                actor=corrected_by,
                created_at=resolved_at,
                geometry_qualification=geometry_qualification,
                cell_symbols=cell_symbols,
            )
        except ImageGridReviewError as error:
            # Keep the deferred-resolution error contract of the Reviewer.
            if error.code == "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT":
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another manual correction.",
                ) from error
            if (
                context.pending.status is BoardCellGeometryPendingStatus.RESOLVED
                and error.code == "IMAGE_GRID_REVIEW_REVISION_CONFLICT"
            ):
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT",
                    "The deferred geometry item was already resolved by another command.",
                ) from error
            raise
        pending = self._repository.get(pending_id)
        if pending is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item no longer exists.",
            )
        if not result.revisions:
            # A board appeared at the position after deferral; it wins.
            return BoardCellGeometryManualResolution(
                pending=pending,
                review_item_id=pending.review_item_id,
                geometry_revision=None,
                created=False,
            )
        revision = result.revisions[0]
        return BoardCellGeometryManualResolution(
            pending=pending,
            review_item_id=revision.review_item_id,
            geometry_revision=revision.revision,
            created=result.created,
        )

    def reject(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        reason: BoardRejectionReason,
        note: str | None,
        rejected_by: str,
        rejected_at: datetime,
    ) -> BoardCellGeometryRejection:
        """Reject an open deferred slot (TASK-0949); the image keeps waiting.

        The slot leaves the correction queue and its counters, is never cut
        and counts as a missing board for the completeness gate (W8). A retry
        of the same command (same key) returns the stored rejection
        (``created=False``) even after it was reverted; another command with
        the same key, or any other key on a rejected slot, conflicts.
        """

        if expected_geometry_revision < 0:
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT",
                "The expected geometry revision cannot be negative.",
            )
        actor = rejected_by.strip()
        if not actor or len(actor) > 200:
            raise JobError(
                "IMAGE_BOARD_CELL_PENDING_REJECTION_INVALID",
                "The rejecting actor must have 1-200 characters.",
            )
        pending, rejection_id, created = self._repository.reject(
            pending_id=pending_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
            expected_geometry_revision=expected_geometry_revision,
            reason=reason,
            note=normalized_rejection_note(reason, note),
            rejected_by=actor,
            rejected_at=rejected_at,
        )
        return BoardCellGeometryRejection(
            pending=pending,
            counts=self._repository.counts(game_id=game_id, import_job_id=import_job_id),
            created=created,
            rejection_id=rejection_id,
        )

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
        if pending.status in {
            BoardCellGeometryPendingStatus.SUPERSEDED,
            BoardCellGeometryPendingStatus.REJECTED,
        } or (pending.status is BoardCellGeometryPendingStatus.RESOLVED and not allow_resolved):
            raise JobConflictError(
                "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE",
                "The deferred geometry item is no longer editable.",
            )

    def _require_virtual_geometry(self) -> VirtualGridGeometryService:
        if self._virtual_geometry is None:
            raise JobError(
                "IMAGE_BOARD_CELL_MANUAL_PREVIEW_UNAVAILABLE",
                "Manual deferred board geometry is not configured.",
            )
        return self._virtual_geometry


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
    "BoardCellGeometryPendingPage",
    "BoardCellGeometryPendingRepository",
    "BoardCellGeometryPendingService",
    "BoardCellGeometryRejection",
    "BoardCellProcessingManifestStore",
    "ManagedBoardCellProcessingManifestStore",
    "decode_board_cell_pending_cursor",
    "encode_board_cell_pending_cursor",
]
