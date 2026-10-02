"""Application boundary for the operational image review queue."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from game_predictor_worker.images.board_cell_geometry_activation import (
    ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION

from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryPreview,
    VirtualGridGeometryRevision,
    VirtualGridGeometryService,
)
from game_predictor_api.domain.board_import_coverage import BoardImportCoverageView
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_completeness import (
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    GeometryImageCursor,
    GeometryImageState,
    LowQualityThresholds,
)
from game_predictor_api.domain.image_reviews import (
    MAX_IMAGE_REVIEW_PAGE_SIZE,
    ImageDatasetCompleteness,
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewError,
    ImageReviewGeometryPoint,
    ImageReviewGridIssueView,
    ImageReviewItem,
    ImageReviewNotFoundError,
    ImageReviewPage,
    ImageReviewResolutionCell,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ImageSequenceSourceSelection,
    ValidatedImageReviewResolution,
    decode_image_review_cursor,
    encode_image_review_cursor,
    validate_image_review_resolution,
)
from game_predictor_api.storage.board_import_coverage_repository import (
    BoardImportCoverageReport,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometryCompletenessReport,
    GeometrySourceImageAsset,
    IncompleteGeometryImagePage,
    LowQualityBoardsReport,
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
    unsupported_virtual_board_count: int
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

    def pending_symbol_reinference_count(self, game_id: UUID) -> int: ...

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


class BoardImportCoverageRepository(Protocol):
    def board_import_coverage(
        self,
        game_id: UUID,
        *,
        view: str,
        range_from: int | None,
        range_to: int | None,
        after_sequence_number: int | None,
        limit: int,
    ) -> BoardImportCoverageReport | None: ...


class ImageGeometryCompletenessRepository(Protocol):
    def completeness_report(
        self, game_id: UUID, *, import_job_id: UUID | None = None
    ) -> GeometryCompletenessReport | None: ...

    def incomplete_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        image_state: GeometryImageState | None = None,
        after: GeometryImageCursor | None = None,
        limit: int = MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    ) -> IncompleteGeometryImagePage | None: ...

    def low_quality_boards(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        thresholds: LowQualityThresholds,
        limit: int = MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    ) -> LowQualityBoardsReport | None: ...

    def source_image_asset(
        self, game_id: UUID, source_image_id: UUID
    ) -> GeometrySourceImageAsset | None: ...


def _geometry_completeness_game_not_found() -> ImageReviewNotFoundError:
    return ImageReviewNotFoundError(
        "IMAGE_REVIEW_GAME_NOT_FOUND",
        "The selected operational review game does not exist.",
    )


class OperationalImageReviewService:
    def __init__(
        self,
        repository: OperationalImageReviewRepository,
        *,
        virtual_geometry: VirtualGridGeometryService | None = None,
        board_import_coverage_repository: BoardImportCoverageRepository | None = None,
        geometry_completeness_repository: ImageGeometryCompletenessRepository | None = None,
    ) -> None:
        self._repository = repository
        # D-467 S6 (TASK-0796): manual geometry of a current board is always
        # a ``virtual_source`` revision written by the shared virtual path.
        self._virtual_geometry = virtual_geometry
        self._board_import_coverage_repository = board_import_coverage_repository
        self._geometry_completeness_repository = geometry_completeness_repository

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

    def pending_symbol_reinference_count(self, game_id: UUID) -> int:
        """Count the boards the pending-symbol worker will actually revisit."""

        with game_storage_scope(game_id):
            return self._repository.pending_symbol_reinference_count(game_id)

    def game_counts(self, game_id: UUID) -> ImageReviewCounts:
        with game_storage_scope(game_id):
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
        with game_storage_scope(game_id):
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
        allow_unknown_cells: bool = False,
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
            allow_unknown_cells=allow_unknown_cells,
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

    def board_import_coverage(
        self,
        game_id: UUID,
        *,
        view: BoardImportCoverageView,
        range_from: int | None,
        range_to: int | None,
        after_sequence_number: int | None,
        limit: int,
    ) -> BoardImportCoverageReport:
        if self._board_import_coverage_repository is None:
            raise ImageReviewConflictError(
                "BOARD_IMPORT_COVERAGE_UNAVAILABLE",
                "Board import coverage is not configured.",
            )
        if not 1 <= limit <= 100:
            raise ImageReviewError(
                "BOARD_IMPORT_COVERAGE_LIMIT_INVALID",
                "limit must be between 1 and 100.",
            )
        if range_from is not None and range_to is not None and range_from > range_to:
            raise ImageReviewError(
                "BOARD_IMPORT_COVERAGE_RANGE_INVALID",
                "from must be less than or equal to to.",
            )
        report = self._board_import_coverage_repository.board_import_coverage(
            game_id,
            view=view.value,
            range_from=range_from,
            range_to=range_to,
            after_sequence_number=after_sequence_number,
            limit=limit,
        )
        if report is None:
            raise ImageReviewNotFoundError(
                "IMAGE_REVIEW_GAME_NOT_FOUND",
                "The selected operational review game does not exist.",
            )
        return report

    def geometry_completeness(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None,
    ) -> GeometryCompletenessReport:
        repository = self._require_geometry_completeness_repository()
        report = repository.completeness_report(game_id, import_job_id=import_job_id)
        if report is None:
            raise _geometry_completeness_game_not_found()
        return report

    def incomplete_geometry_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None,
        image_state: GeometryImageState | None,
        after: GeometryImageCursor | None,
        limit: int,
    ) -> IncompleteGeometryImagePage:
        repository = self._require_geometry_completeness_repository()
        if not 1 <= limit <= MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_LIMIT_INVALID",
                f"limit must be between 1 and {MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE}.",
            )
        if image_state is GeometryImageState.COMPLETE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_STATE_INVALID",
                "The incomplete image list cannot be filtered by the complete state.",
            )
        page = repository.incomplete_images(
            game_id,
            import_job_id=import_job_id,
            image_state=image_state,
            after=after,
            limit=limit,
        )
        if page is None:
            raise _geometry_completeness_game_not_found()
        return page

    def geometry_low_quality_boards(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None,
        thresholds: LowQualityThresholds,
        limit: int,
    ) -> LowQualityBoardsReport:
        repository = self._require_geometry_completeness_repository()
        if not 1 <= limit <= MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_LIMIT_INVALID",
                f"limit must be between 1 and {MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE}.",
            )
        report = repository.low_quality_boards(
            game_id,
            import_job_id=import_job_id,
            thresholds=thresholds,
            limit=limit,
        )
        if report is None:
            raise _geometry_completeness_game_not_found()
        return report

    def geometry_source_image(
        self,
        game_id: UUID,
        source_image_id: UUID,
    ) -> GeometrySourceImageAsset:
        repository = self._require_geometry_completeness_repository()
        asset = repository.source_image_asset(game_id, source_image_id)
        if asset is None:
            raise _geometry_completeness_game_not_found()
        return asset

    def _require_geometry_completeness_repository(self) -> ImageGeometryCompletenessRepository:
        if self._geometry_completeness_repository is None:
            raise ImageReviewConflictError(
                "IMAGE_GEOMETRY_COMPLETENESS_UNAVAILABLE",
                "Image geometry completeness is not configured.",
            )
        return self._geometry_completeness_repository

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
        geometry_qualification: GeometryQualification | None = None,
    ) -> VirtualGridGeometryPreview:
        """Render the cells a manual geometry would persist (D-467 S6, TASK-0796).

        The operational Reviewer keeps its route and command; the preview is
        the virtual render of :class:`VirtualGridGeometryService`, the same
        one the Admin grid correction shows.
        """

        virtual_geometry = self._require_virtual_geometry()
        with game_storage_scope(game_id):
            self.get_item(review_item_id, game_id=game_id, import_job_id=import_job_id)
            return virtual_geometry.preview_review_item(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                expected_geometry_revision=expected_geometry_revision,
                expected_resolution_revision=expected_resolution_revision,
                corners=corners,
                geometry_qualification=geometry_qualification,
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
        geometry_qualification: GeometryQualification | None = None,
    ) -> tuple[ImageReviewItem, VirtualGridGeometryRevision, bool]:
        """Persist a ``virtual_source`` geometry revision of one current board.

        Delegates to ``VirtualGridGeometryService.save_review_item`` in the
        same session (replay by ``idempotency_key``, revision CAS, render
        manifest, reopened cells), then reloads the review item for the
        unchanged ``OperationalImageReviewGeometryResponse`` shape.
        """

        virtual_geometry = self._require_virtual_geometry()
        with game_storage_scope(game_id):
            self.get_item(review_item_id, game_id=game_id, import_job_id=import_job_id)
            result = virtual_geometry.save_review_item(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                idempotency_key=idempotency_key,
                expected_geometry_revision=expected_geometry_revision,
                expected_resolution_revision=expected_resolution_revision,
                corners=corners,
                geometry_qualification=geometry_qualification,
                actor=corrected_by,
                created_at=datetime.now(UTC),
            )
            item = self.get_item(review_item_id, game_id=game_id, import_job_id=import_job_id)
        return item, result.revision, result.created

    def _require_virtual_geometry(self) -> VirtualGridGeometryService:
        if self._virtual_geometry is None:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_GEOMETRY_UNAVAILABLE",
                "Manual board geometry is not configured.",
            )
        return self._virtual_geometry


__all__ = [
    "OperationalImageReviewPage",
    "OperationalImageReviewRepository",
    "OperationalImageReviewService",
]
