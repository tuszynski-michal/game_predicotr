"""Application boundary for the operational image review queue."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_worker.images.board_cell_geometry_activation import (
    ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_COORDINATE_SPACE,
    BOARD_CELL_CORNER_SEMANTICS,
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    ManualBoardCellGeometryPreview,
    ManualBoardCellGeometryPreviewer,
    ManualBoardCellGeometryPreviewError,
)

from game_predictor_api.application.image_review_assets import (
    resolve_operational_source_asset,
)
from game_predictor_api.domain.image_reviews import (
    MAX_IMAGE_REVIEW_PAGE_SIZE,
    ImageDatasetCompleteness,
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
    ImageReviewGridIssueView,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionCell,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ImageSequenceSourceSelection,
    ValidatedImageReviewGeometryCommand,
    ValidatedImageReviewResolution,
    decode_image_review_cursor,
    encode_image_review_cursor,
    validate_image_review_geometry_command,
    validate_image_review_resolution,
)


@dataclass(frozen=True, slots=True)
class OperationalImageReviewPage:
    game_id: UUID
    import_job_id: UUID
    view: ImageReviewView
    grid_issue_view: ImageReviewGridIssueView
    items: tuple[ImageReviewItem, ...]
    counts: ImageReviewCounts
    needs_grid_fix_count: int
    queue_version: int
    previous_cursor: str | None
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CanonicalImageReviewPage:
    game_id: UUID
    items: tuple[ImageReviewItem, ...]
    counts: ImageReviewCounts
    previous_cursor: str | None
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PendingGridReinferencePreview:
    game_id: UUID
    pending_board_count: int
    recalculable_board_count: int
    current_v19_board_count: int
    protected_board_count: int
    pending_source_count: int
    partially_resolved_source_count: int
    fully_resolved_source_count: int
    geometry_version: str
    cropper_version: str
    audit_report_checksum_sha256: str


class OperationalImageReviewRepository(Protocol):
    def require_context(self, *, game_id: UUID, import_job_id: UUID) -> None: ...

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        grid_issue_view: ImageReviewGridIssueView,
        after_key: tuple[int, int, str] | None,
        before_key: tuple[int, int, str] | None,
        expected_queue_version: int | None,
        sequence_number: int | None,
        resume_at_first_pending: bool,
        limit: int,
    ) -> ImageReviewPage: ...

    def queue_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[int, ImageReviewCounts]: ...

    def list_canonical_pending_items(
        self,
        *,
        game_id: UUID,
        after_sequence: int | None,
        limit: int,
    ) -> ImageReviewPage: ...

    def canonical_pending_count(self, game_id: UUID) -> int: ...

    def game_counts(self, game_id: UUID) -> ImageReviewCounts: ...

    def pending_grid_reinference_preview(
        self,
        game_id: UUID,
        *,
        geometry_version: str,
        cropper_version: str,
        audit_report_checksum_sha256: str,
    ) -> PendingGridReinferencePreview: ...

    def get_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        for_update: bool = False,
    ) -> ImageReviewItem | None: ...

    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]: ...

    def expected_layout_count(self, game_id: UUID) -> int | None: ...

    def dataset_completeness(self, game_id: UUID) -> ImageDatasetCompleteness | None: ...

    def sequence_source_selection(
        self,
        game_id: UUID,
        sequence_number: int,
    ) -> ImageSequenceSourceSelection | None: ...

    def append_source_override(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        review_item_id: UUID | None,
        selected_by: str,
    ) -> None: ...

    def save_resolution(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        resolution: ValidatedImageReviewResolution,
        resolved_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewResolutionEvent, bool]: ...

    def list_resolution_events(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> Sequence[ImageReviewResolutionEvent]: ...

    def get_geometry_revision_by_idempotency(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
    ) -> ImageReviewGeometryRevision | None: ...

    def save_geometry_revision(
        self,
        *,
        review_item_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        command: ValidatedImageReviewGeometryCommand,
        artifacts: ImageReviewGeometryArtifacts,
        created_at: datetime,
    ) -> tuple[ImageReviewItem, ImageReviewGeometryRevision, bool]: ...


class OperationalImageReviewService:
    def __init__(
        self,
        repository: OperationalImageReviewRepository,
        *,
        artifact_root: Path | None = None,
        board_cell_geometry_previewer: ManualBoardCellGeometryPreviewer | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = artifact_root
        self._board_cell_geometry_previewer = board_cell_geometry_previewer

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        grid_issue_view: ImageReviewGridIssueView,
        after_cursor: str | None,
        before_cursor: str | None,
        sequence_number: int | None,
        resume_at_first_pending: bool,
        limit: int,
    ) -> OperationalImageReviewPage:
        if (
            not 1 <= limit <= MAX_IMAGE_REVIEW_PAGE_SIZE
            or (after_cursor is not None and before_cursor is not None)
            or (
                resume_at_first_pending
                and (
                    view is not ImageReviewView.ALL
                    or after_cursor is not None
                    or before_cursor is not None
                    or sequence_number is not None
                )
            )
            or (
                sequence_number is not None
                and (
                    isinstance(sequence_number, bool)
                    or sequence_number < 1
                    or after_cursor is not None
                    or before_cursor is not None
                )
            )
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PAGE_INVALID",
                "Use one bounded cursor, one positive sequenceNumber, or "
                "resumeAtFirstPending with view=all.",
            )
        self._repository.require_context(game_id=game_id, import_job_id=import_job_id)
        after = (
            decode_image_review_cursor(
                after_cursor,
                game_id=game_id,
                import_job_id=import_job_id,
                view=view,
                grid_issue_view=grid_issue_view,
            )
            if after_cursor
            else None
        )
        before = (
            decode_image_review_cursor(
                before_cursor,
                game_id=game_id,
                import_job_id=import_job_id,
                view=view,
                grid_issue_view=grid_issue_view,
            )
            if before_cursor
            else None
        )
        page = self._repository.list_items(
            game_id=game_id,
            import_job_id=import_job_id,
            view=view,
            grid_issue_view=grid_issue_view,
            after_key=after.key if after is not None else None,
            before_key=before.key if before is not None else None,
            expected_queue_version=(
                after.queue_version
                if after is not None
                else before.queue_version
                if before is not None
                else None
            ),
            sequence_number=sequence_number,
            resume_at_first_pending=resume_at_first_pending,
            limit=limit,
        )
        if page.queue_version is None or (page.items and page.queue_version < 1):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_QUEUE_PROJECTION_INVALID",
                "The operational review queue did not provide a durable topology version.",
            )
        queue_version = page.queue_version
        return OperationalImageReviewPage(
            game_id=game_id,
            import_job_id=import_job_id,
            view=view,
            grid_issue_view=grid_issue_view,
            items=page.items,
            counts=page.counts,
            needs_grid_fix_count=page.needs_grid_fix_count,
            queue_version=queue_version,
            previous_cursor=(
                encode_image_review_cursor(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    view=view,
                    grid_issue_view=grid_issue_view,
                    key=page.items[0].queue_order_key,
                    queue_version=queue_version,
                )
                if page.items and page.has_previous
                else None
            ),
            next_cursor=(
                encode_image_review_cursor(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    view=view,
                    grid_issue_view=grid_issue_view,
                    key=page.items[-1].queue_order_key,
                    queue_version=queue_version,
                )
                if page.items and page.has_next
                else None
            ),
        )

    def list_canonical_pending_items(
        self,
        *,
        game_id: UUID,
        after_sequence: int | None,
        limit: int,
    ) -> CanonicalImageReviewPage:
        if not 1 <= limit <= MAX_IMAGE_REVIEW_PAGE_SIZE or (
            after_sequence is not None and after_sequence < 1
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_PAGE_INVALID",
                "The canonical review page cursor or limit is invalid.",
            )
        page = self._repository.list_canonical_pending_items(
            game_id=game_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        last_sequence = (
            page.items[-1].queue_sequence_number
            if page.items and page.items[-1].queue_sequence_number is not None
            else None
        )
        first_sequence = (
            page.items[0].queue_sequence_number
            if page.items and page.items[0].queue_sequence_number is not None
            else None
        )
        return CanonicalImageReviewPage(
            game_id=game_id,
            items=page.items,
            counts=page.counts,
            previous_cursor=None if first_sequence is None else str(first_sequence),
            next_cursor=None if last_sequence is None or not page.has_next else str(last_sequence),
        )

    def canonical_pending_count(self, game_id: UUID) -> int:
        return self._repository.canonical_pending_count(game_id)

    def game_counts(self, game_id: UUID) -> ImageReviewCounts:
        return self._repository.game_counts(game_id)

    def pending_grid_reinference_preview(self, game_id: UUID) -> PendingGridReinferencePreview:
        return self._repository.pending_grid_reinference_preview(
            game_id,
            geometry_version=BOARD_CELL_GEOMETRY_VERSION,
            cropper_version=CROPPER_VERSION,
            audit_report_checksum_sha256=ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256,
        )

    def get_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> ImageReviewItem:
        item = self._repository.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        if item is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_ITEM_NOT_FOUND",
                "The operational review item does not exist in this game and job.",
                details={"reviewItemId": str(review_item_id)},
            )
        return item

    def resolve_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_revision: int,
        action: ImageReviewAction,
        sequence_number: int | None,
        geometry_revision: int,
        cells: Sequence[ImageReviewResolutionCell],
        rejection_reason: str | None,
        resolved_by: str,
    ) -> tuple[ImageReviewItem, ImageReviewResolutionEvent, bool]:
        if expected_revision < 0:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_REVISION_INVALID",
                "The expected revision cannot be negative.",
            )
        expected_layout_count = self._repository.expected_layout_count(game_id)
        if (
            expected_layout_count is not None
            and sequence_number is not None
            and sequence_number > expected_layout_count
        ):
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_SEQUENCE_OUT_OF_RANGE",
                "The sequence number exceeds the configured game range.",
                details={"expectedLayoutCount": expected_layout_count},
            )
        item = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        resolution = validate_image_review_resolution(
            item=item,
            action=action,
            sequence_number=sequence_number,
            geometry_revision=geometry_revision,
            cells=cells,
            rejection_reason=rejection_reason,
            resolved_by=resolved_by,
            active_symbol_codes=self._repository.active_symbol_codes(game_id),
        )
        return self._repository.save_resolution(
            review_item_id=review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            resolution=resolution,
            resolved_at=datetime.now(UTC),
        )

    def queue_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[int, ImageReviewCounts]:
        queue_version, counts = self._repository.queue_snapshot(
            game_id=game_id,
            import_job_id=import_job_id,
        )
        if queue_version < 1:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_QUEUE_PROJECTION_INVALID",
                "The operational review queue did not provide a durable topology version.",
            )
        return queue_version, counts

    def dataset_completeness(self, game_id: UUID) -> ImageDatasetCompleteness:
        report = self._repository.dataset_completeness(game_id)
        if report is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_GAME_NOT_FOUND",
                "The selected operational review game does not exist.",
            )
        return report

    def sequence_source_selection(
        self,
        game_id: UUID,
        sequence_number: int,
    ) -> ImageSequenceSourceSelection:
        expected = self._repository.expected_layout_count(game_id)
        if expected is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_GAME_NOT_FOUND",
                "The selected operational review game does not exist.",
            )
        if sequence_number < 1 or sequence_number > expected:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_SEQUENCE_OUT_OF_RANGE",
                "The sequence number is outside the configured game range.",
                details={"expectedLayoutCount": expected},
            )
        selection = self._repository.sequence_source_selection(
            game_id,
            sequence_number,
        )
        if selection is None:
            raise ImageReviewNotFoundError(
                "IMAGE_SEQUENCE_SOURCE_NOT_FOUND",
                "No accepted image source exists for this sequence.",
            )
        return selection

    def select_sequence_source(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        review_item_id: UUID | None,
        selected_by: str,
    ) -> ImageSequenceSourceSelection:
        actor = selected_by.strip()
        if not actor or len(actor) > 200:
            raise ImageReviewConflictError(
                "IMAGE_SEQUENCE_SOURCE_ACTOR_INVALID",
                "selectedBy must identify the local administrator.",
            )
        current = self.sequence_source_selection(game_id, sequence_number)
        if review_item_id is not None and review_item_id not in {
            candidate.review_item_id for candidate in current.candidates
        }:
            raise ImageReviewConflictError(
                "IMAGE_SEQUENCE_SOURCE_CANDIDATE_INVALID",
                "The selected review item is not an accepted source for this sequence.",
            )
        self._repository.append_source_override(
            game_id=game_id,
            sequence_number=sequence_number,
            review_item_id=review_item_id,
            selected_by=actor,
        )
        updated = self._repository.sequence_source_selection(game_id, sequence_number)
        if updated is None:
            raise RuntimeError("Image sequence source selection disappeared after update.")
        return updated

    def list_resolution_events(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> Sequence[ImageReviewResolutionEvent]:
        self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        return self._repository.list_resolution_events(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )

    def preview_geometry(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
    ) -> ManualBoardCellGeometryPreview:
        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by="local-admin-preview",
        )
        item = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        self._require_current_geometry_command(item, command)
        return self._validated_board_cell_geometry_preview(
            item=item,
            command=command,
        )

    def correct_geometry(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        corners: Sequence[ImageReviewGeometryPoint],
        corrected_by: str,
    ) -> tuple[ImageReviewItem, ImageReviewGeometryRevision, bool]:
        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=corrected_by,
        )
        prior = self._repository.get_geometry_revision_by_idempotency(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            if prior.command_sha256 != command.command_sha256:
                raise ImageReviewConflictError(
                    "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The geometry idempotency key already represents another command.",
                )
            return (
                self.get_item(
                    review_item_id,
                    game_id=game_id,
                    import_job_id=import_job_id,
                ),
                prior,
                False,
            )
        item = self.get_item(
            review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
        )
        self._require_current_geometry_command(item, command)
        preview = self._validated_board_cell_geometry_preview(
            item=item,
            command=command,
        )
        previewer, artifact_root = self._require_board_cell_geometry_preview_dependencies()
        try:
            persisted = previewer.persist(
                preview=preview,
                managed_data_root=artifact_root.resolve() / "data",
                revision=item.geometry_revision + 1,
            )
        except ManualBoardCellGeometryPreviewError as error:
            raise ImageReviewConflictError(error.code, str(error)) from error
        artifacts = ImageReviewGeometryArtifacts(
            geometry={
                "cellOutputSize": persisted.cell_output_size,
                "cells": [
                    {
                        "columnIndex": cell.column_index,
                        "cropChecksumSha256": cell.checksum_sha256,
                        "paddedSourceQuad": _quad_dict(cell.padded_source_quad),
                        "rowIndex": cell.row_index,
                        "sourceQuad": _quad_dict(cell.source_quad),
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
                "latticeBoundsQuad": _quad_dict(persisted.lattice_bounds_quad),
                "manualGeometryVersion": persisted.manual_geometry_version,
                "positionIndex": persisted.position_index,
                "reviewItemId": persisted.review_item_id,
                "sequenceNumber": persisted.sequence_number,
                "source": "manual_override",
                "sourceGroup": persisted.source_group,
                "sourceImageChecksumSha256": persisted.source_image_checksum_sha256,
                "sourceImageId": persisted.source_image_id,
                "sourceImageRelativePath": persisted.source_image_relative_path,
                "sourceOrderIndex": persisted.source_order_index,
                **_retained_review_context(
                    item.geometry,
                    image_width=persisted.image_width,
                    image_height=persisted.image_height,
                ),
            },
            board_relative_path=item.board_relative_path,
            board_checksum_sha256=item.board_checksum_sha256,
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
        return self._repository.save_geometry_revision(
            review_item_id=review_item_id,
            game_id=game_id,
            import_job_id=import_job_id,
            idempotency_key=idempotency_key,
            command=command,
            artifacts=artifacts,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _require_current_geometry_command(
        item: ImageReviewItem,
        command: ValidatedImageReviewGeometryCommand,
    ) -> None:
        if item.geometry_revision != command.expected_geometry_revision:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT",
                "The selected geometry revision is no longer current.",
            )
        if item.resolution_revision != command.expected_resolution_revision:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_REVISION_CONFLICT",
                "The operational review item changed after it was loaded.",
            )

    def _validated_board_cell_geometry_preview(
        self,
        *,
        item: ImageReviewItem,
        command: ValidatedImageReviewGeometryCommand,
    ) -> ManualBoardCellGeometryPreview:
        sequence_number = item.queue_sequence_number
        if sequence_number is None and item.geometry.get("sequenceSource") == "filename":
            sequence_number = item.suggested_sequence_number
        if sequence_number is None:
            raise ImageReviewConflictError(
                "BOARD_CELL_GEOMETRY_PREVIEW_SEQUENCE_UNRESOLVED",
                "Board-cell geometry requires an unambiguous sequence number.",
            )
        previewer, artifact_root = self._require_board_cell_geometry_preview_dependencies()
        source = resolve_operational_source_asset(item, artifact_root)
        try:
            return previewer.preview(
                source_path=source.path,
                expected_source_sha256=item.source_checksum_sha256,
                review_item_id=str(item.id),
                source_order_index=item.source_order_index,
                source_image_id=str(item.source_image_id),
                source_image_relative_path=item.source_relative_path,
                source_group=str(item.import_job_id),
                sequence_number=sequence_number,
                position_index=item.position_index,
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
            raise ImageReviewConflictError(error.code, str(error)) from error

    def _require_board_cell_geometry_preview_dependencies(
        self,
    ) -> tuple[ManualBoardCellGeometryPreviewer, Path]:
        if self._board_cell_geometry_previewer is None or self._artifact_root is None:
            raise ImageReviewConflictError(
                "BOARD_CELL_GEOMETRY_PREVIEW_UNAVAILABLE",
                "The v19 board-cell geometry preview is not configured.",
            )
        return self._board_cell_geometry_previewer, self._artifact_root


def _retained_review_context(
    geometry: Mapping[str, object],
    *,
    image_width: int,
    image_height: int,
) -> dict[str, object]:
    retained: dict[str, object] = {}
    display_asset_kind = geometry.get("displayAssetKind")
    if display_asset_kind == "source_context":
        retained["displayAssetKind"] = display_asset_kind
    for key in (
        "attestedRangeEnd",
        "attestedRangeStart",
        "sequenceLabelQuad",
        "sequenceSource",
    ):
        value = geometry.get(key)
        if value is not None:
            retained[key] = value
    bounds = _parse_source_context_bounds(
        geometry.get("sourceContextBounds"),
        image_width=image_width,
        image_height=image_height,
    )
    if bounds is None:
        bounds = _derive_source_context_bounds(
            geometry,
            image_width=image_width,
            image_height=image_height,
        )
    if bounds is not None:
        retained["sourceContextBounds"] = bounds
    return retained


def _parse_source_context_bounds(
    value: object,
    *,
    image_width: int,
    image_height: int,
) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        x = round(float(value["x"]))
        y = round(float(value["y"]))
        width = round(float(value["width"]))
        height = round(float(value["height"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    bounded_x = min(image_width - 1, x)
    bounded_y = min(image_height - 1, y)
    right = min(image_width, bounded_x + width)
    bottom = min(image_height, bounded_y + height)
    return {
        "height": max(1, bottom - bounded_y),
        "width": max(1, right - bounded_x),
        "x": bounded_x,
        "y": bounded_y,
    }


def _derive_source_context_bounds(
    geometry: Mapping[str, object],
    *,
    image_width: int,
    image_height: int,
) -> dict[str, int] | None:
    board = _parse_geometry_points(
        geometry.get("latticeBoundsQuad")
        or geometry.get("sourceQuad")
        or geometry.get("quad")
        or geometry.get("corners")
    )
    if board is None:
        return None
    label = _parse_geometry_points(geometry.get("sequenceLabelQuad"))
    points = board + (label or ())
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    board_width = max(
        1,
        max(point[0] for point in board) - min(point[0] for point in board),
    )
    board_height = max(
        1,
        max(point[1] for point in board) - min(point[1] for point in board),
    )
    horizontal_padding = max(12, round(board_width * 0.1))
    top_padding = max(12, round(board_height * 0.12))
    bottom_padding = max(
        12,
        round(board_height * (0.12 if label is not None else 0.55)),
    )
    x = max(0, int(min(xs) - horizontal_padding))
    y = max(0, int(min(ys) - top_padding))
    right = min(image_width, int(max(xs) + horizontal_padding + 0.999999))
    bottom = min(image_height, int(max(ys) + bottom_padding + 0.999999))
    return {
        "height": max(1, bottom - y),
        "width": max(1, right - x),
        "x": x,
        "y": y,
    }


def _parse_geometry_points(value: object) -> tuple[tuple[float, float], ...] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    parsed: list[tuple[float, float]] = []
    for raw_point in value:
        if not isinstance(raw_point, Mapping):
            return None
        try:
            x = float(raw_point["x"])
            y = float(raw_point["y"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(x) or not math.isfinite(y) or x < 0 or y < 0:
            return None
        parsed.append((x, y))
    return tuple(parsed)


def _quad_dict(
    quad: Sequence[tuple[float, float]],
) -> list[dict[str, float]]:
    return [{"x": float(point[0]), "y": float(point[1])} for point in quad]


__all__ = [
    "OperationalImageReviewPage",
    "OperationalImageReviewRepository",
    "OperationalImageReviewService",
]
