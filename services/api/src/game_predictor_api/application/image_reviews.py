"""Application boundary for the operational image review queue."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.manual_geometry_recrop import (
    ManualGeometryPreview,
    ManualGeometryRecropper,
)
from game_predictor_worker.images.rectification import BoardCropError

from game_predictor_api.application.image_review_assets import (
    resolve_operational_source_asset,
)
from game_predictor_api.domain.image_reviews import (
    MAX_IMAGE_REVIEW_PAGE_SIZE,
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewGeometryArtifacts,
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionCell,
    ImageReviewResolutionEvent,
    ImageReviewView,
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
    items: tuple[ImageReviewItem, ...]
    counts: ImageReviewCounts
    previous_cursor: str | None
    next_cursor: str | None


class OperationalImageReviewRepository(Protocol):
    def require_context(self, *, game_id: UUID, import_job_id: UUID) -> None: ...

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        after_key: tuple[int, int, int, str] | None,
        before_key: tuple[int, int, int, str] | None,
        sequence_number: int | None,
        limit: int,
    ) -> ImageReviewPage: ...

    def get_item(
        self,
        review_item_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
        for_update: bool = False,
    ) -> ImageReviewItem | None: ...

    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]: ...

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
        geometry_recropper: ManualGeometryRecropper | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = artifact_root
        self._geometry_recropper = geometry_recropper

    def list_items(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        view: ImageReviewView,
        after_cursor: str | None,
        before_cursor: str | None,
        sequence_number: int | None,
        limit: int,
    ) -> OperationalImageReviewPage:
        if (
            not 1 <= limit <= MAX_IMAGE_REVIEW_PAGE_SIZE
            or (after_cursor is not None and before_cursor is not None)
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
                "Use one bounded cursor or one positive sequenceNumber.",
            )
        self._repository.require_context(game_id=game_id, import_job_id=import_job_id)
        after_key = (
            decode_image_review_cursor(
                after_cursor,
                game_id=game_id,
                import_job_id=import_job_id,
                view=view,
            )
            if after_cursor
            else None
        )
        before_key = (
            decode_image_review_cursor(
                before_cursor,
                game_id=game_id,
                import_job_id=import_job_id,
                view=view,
            )
            if before_cursor
            else None
        )
        page = self._repository.list_items(
            game_id=game_id,
            import_job_id=import_job_id,
            view=view,
            after_key=after_key,
            before_key=before_key,
            sequence_number=sequence_number,
            limit=limit,
        )
        return OperationalImageReviewPage(
            game_id=game_id,
            import_job_id=import_job_id,
            view=view,
            items=page.items,
            counts=page.counts,
            previous_cursor=(
                encode_image_review_cursor(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    view=view,
                    key=page.items[0].cursor_key,
                )
                if page.items and page.has_previous
                else None
            ),
            next_cursor=(
                encode_image_review_cursor(
                    game_id=game_id,
                    import_job_id=import_job_id,
                    view=view,
                    key=page.items[-1].cursor_key,
                )
                if page.items and page.has_next
                else None
            ),
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
    ) -> ManualGeometryPreview:
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
        recropper, artifact_root = self._require_geometry_dependencies()
        source = resolve_operational_source_asset(item, artifact_root)
        try:
            return recropper.preview(
                source_path=source.path,
                expected_source_sha256=item.source_checksum_sha256,
                corners=(
                    Point(command.corners[0].x, command.corners[0].y),
                    Point(command.corners[1].x, command.corners[1].y),
                    Point(command.corners[2].x, command.corners[2].y),
                    Point(command.corners[3].x, command.corners[3].y),
                ),
            )
        except BoardCropError as error:
            raise ImageReviewConflictError(error.code, str(error)) from error

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
        recropper, artifact_root = self._require_geometry_dependencies()
        source = resolve_operational_source_asset(item, artifact_root)
        try:
            preview = recropper.preview(
                source_path=source.path,
                expected_source_sha256=item.source_checksum_sha256,
                corners=(
                    Point(command.corners[0].x, command.corners[0].y),
                    Point(command.corners[1].x, command.corners[1].y),
                    Point(command.corners[2].x, command.corners[2].y),
                    Point(command.corners[3].x, command.corners[3].y),
                ),
            )
            persisted = recropper.persist(
                preview=preview,
                managed_data_root=artifact_root.resolve() / "data",
                review_item_id=str(review_item_id),
                revision=item.geometry_revision + 1,
            )
        except BoardCropError as error:
            raise ImageReviewConflictError(error.code, str(error)) from error
        artifacts = ImageReviewGeometryArtifacts(
            geometry={
                "cropperVersion": persisted.cropper_version,
                "imageHeight": persisted.image_height,
                "imageWidth": persisted.image_width,
                "source": "manual_review",
                "sourceQuad": [{"x": point.x, "y": point.y} for point in persisted.source_quad],
                "transformMatrix": [list(row) for row in persisted.transform_matrix],
            },
            board_relative_path=persisted.board_relative_path,
            board_checksum_sha256=persisted.board_checksum_sha256,
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

    def _require_geometry_dependencies(
        self,
    ) -> tuple[ManualGeometryRecropper, Path]:
        if self._geometry_recropper is None or self._artifact_root is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_UNAVAILABLE",
                "Manual geometry correction is not configured.",
            )
        return self._geometry_recropper, self._artifact_root


__all__ = [
    "OperationalImageReviewPage",
    "OperationalImageReviewRepository",
    "OperationalImageReviewService",
]
