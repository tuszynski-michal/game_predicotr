"""OpenAPI schemas for the operational image review queue."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.application.image_reviews import (
    CanonicalImageReviewPage,
    OperationalImageReviewPage,
    PendingGridReinferencePreview,
)
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryRevision
from game_predictor_api.domain.board_import_coverage import BoardImportCoverageView
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    MAX_IMAGE_REVIEW_ALTERNATIVES,
    ImageDatasetCompleteness,
    ImageReviewAction,
    ImageReviewCounts,
    ImageReviewGridIssueView,
    ImageReviewItem,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ImageSequenceSourceSelection,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.geometry_qualification import (
    GeometryQualificationPayload,
    ManualSourceGeometryPoint,
)
from game_predictor_api.schemas.source_lattice_geometry import (
    SourceLatticeNodesPayload,
    lattice_nodes_payload,
)
from game_predictor_api.storage.board_import_coverage_repository import (
    BoardImportCoverageReport,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class OperationalImageReviewAlternativeResponse(ApiModel):
    symbol_code: str = Field(min_length=1, max_length=64)
    confidence: Probability


class OperationalImageReviewCellResponse(ApiModel):
    cell_index: int = Field(ge=0, lt=IMAGE_REVIEW_CELL_COUNT)
    row_index: int = Field(ge=0, lt=3)
    column_index: int = Field(ge=0, lt=5)
    crop_sample_id: Sha256
    crop_checksum_sha256: Sha256
    predicted_symbol_code: str = Field(min_length=1, max_length=64)
    current_symbol_code: str = Field(min_length=1, max_length=64)
    confidence: Probability
    alternatives: tuple[OperationalImageReviewAlternativeResponse, ...] = Field(
        min_length=1,
        max_length=MAX_IMAGE_REVIEW_ALTERNATIVES,
    )


class OperationalImageReviewItemResponse(ApiModel):
    lattice_nodes: SourceLatticeNodesPayload | None = None
    expected_proposal_checksum_sha256: Sha256 | None = None
    id: UUID
    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID
    status: str
    source_order_index: int = Field(ge=0)
    position_index: int = Field(ge=0, le=8)
    sequence_number: int | None = Field(default=None, ge=1)
    suggested_sequence_number: int | None = Field(default=None, ge=1)
    source_checksum_sha256: Sha256
    board_checksum_sha256: Sha256
    geometry_revision: int = Field(ge=0)
    geometry: dict[str, object]
    geometry_qualification: GeometryQualificationPayload | None = Field(
        default=None,
        description="Persisted manual qualification of the current board geometry (TASK-0798)",
    )
    source_width: int | None = Field(
        default=None, gt=0, description="Oriented width of the source the corners refer to"
    )
    source_height: int | None = Field(
        default=None, gt=0, description="Oriented height of the source the corners refer to"
    )
    pipeline_fingerprint: Sha256
    cells: tuple[OperationalImageReviewCellResponse, ...] = Field(
        min_length=0,
        max_length=IMAGE_REVIEW_CELL_COUNT,
    )
    resolved_value: dict[str, object] | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_revision: int = Field(ge=0)
    created_at: datetime


def _client_qualification(
    raw: object,
) -> GeometryQualificationPayload | None:
    if raw is None:
        return None
    return GeometryQualificationPayload.model_validate(
        GeometryQualification.from_dict(raw).to_client_dict()
    )


class OperationalImageReviewCountsResponse(ApiModel):
    pending: int = Field(ge=0)
    accepted: int = Field(ge=0)
    corrected: int = Field(ge=0)
    rejected: int = Field(ge=0)
    superseded: int = Field(ge=0)
    completed: int = Field(ge=0)
    total: int = Field(ge=0)


class OperationalImageReviewPageResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID
    view: ImageReviewView
    grid_issue_view: ImageReviewGridIssueView
    items: tuple[OperationalImageReviewItemResponse, ...]
    counts: OperationalImageReviewCountsResponse
    needs_grid_fix_count: int = Field(ge=0)
    queue_version: int = Field(ge=0)
    previous_cursor: str | None
    next_cursor: str | None


class CanonicalImageReviewPageResponse(ApiModel):
    game_id: UUID
    items: tuple[OperationalImageReviewItemResponse, ...]
    counts: OperationalImageReviewCountsResponse
    previous_cursor: str | None
    next_cursor: str | None


class PendingSymbolReinferencePreviewResponse(ApiModel):
    game_id: UUID
    pending_count: int = Field(ge=0)
    protected_resolved_count: int = Field(ge=0)
    requires_explicit_activation: bool = True


class PendingGridReinferencePreviewResponse(ApiModel):
    game_id: UUID
    pending_board_count: int = Field(ge=0)
    recalculable_board_count: int = Field(ge=0)
    current_v19_board_count: int = Field(ge=0)
    protected_board_count: int = Field(ge=0)
    unsupported_virtual_board_count: int = Field(ge=0)
    pending_source_count: int = Field(ge=0)
    partially_resolved_source_count: int = Field(ge=0)
    fully_resolved_source_count: int = Field(ge=0)
    geometry_version: str
    cropper_version: str
    audit_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requires_explicit_activation: bool = True


class ImageDatasetCompletenessResponse(ApiModel):
    game_id: UUID
    expected_layout_count: int = Field(ge=1)
    accepted_board_count: int = Field(ge=0)
    unique_sequence_count: int = Field(ge=0)
    missing_sequence_count: int = Field(ge=0)
    duplicate_sequence_count: int = Field(ge=0)
    out_of_range_sequence_count: int = Field(ge=0)
    missing_sequence_numbers: tuple[int, ...] = Field(max_length=100)
    missing_sequence_numbers_truncated: bool
    manual_override_count: int = Field(ge=0)
    completion_percentage: float = Field(ge=0, le=100)


class BoardImportCoverageCountsResponse(ApiModel):
    expected: int = Field(ge=1)
    added: int = Field(ge=0)
    missing: int = Field(ge=0)
    approved: int = Field(ge=0)
    out_of_range: int = Field(ge=0)


class BoardImportCoverageNoticesResponse(ApiModel):
    unnumbered_cut_board_count: int = Field(ge=0)
    failed_sources_without_range_count: int = Field(ge=0)
    active_import_job_count: int = Field(ge=0)
    active_sources_without_range_count: int = Field(ge=0)


class BoardImportCoverageRangeResponse(ApiModel):
    # "from" is a Python keyword; construct this model with `**{"from": ..., "to": ...}`.
    from_: int = Field(ge=1, alias="from")
    to: int = Field(ge=1)


class BoardImportCoverageRangeCountsResponse(ApiModel):
    added: int = Field(ge=0)
    missing: int = Field(ge=0)


class BoardImportCoverageSegmentResponse(ApiModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    count: int = Field(ge=1)
    state: str = Field(min_length=1)
    error_code: str | None = None
    geometry_reason_code: str | None = None
    import_job_id: UUID | None = None


class BoardImportCoverageResponse(ApiModel):
    game_id: UUID
    expected_layout_count: int = Field(ge=1)
    counts: BoardImportCoverageCountsResponse
    missing_by_reason: dict[str, int]
    notices: BoardImportCoverageNoticesResponse
    view: BoardImportCoverageView
    range: BoardImportCoverageRangeResponse | None
    range_counts: BoardImportCoverageRangeCountsResponse | None
    segments: tuple[BoardImportCoverageSegmentResponse, ...] = Field(max_length=100)
    next_after_sequence_number: int | None
    computed_at: datetime


class ImageSequenceSourceCandidateResponse(ApiModel):
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=1)
    source_checksum_sha256: Sha256
    source_relative_path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    board_confidence: Probability
    sequence_confidence: Probability
    geometry_revision: int = Field(ge=0)
    automatic_rank: int = Field(ge=1)
    quality_score: Probability
    selected: bool
    selected_manually: bool


class ImageSequenceSourceSelectionResponse(ApiModel):
    game_id: UUID
    sequence_number: int = Field(ge=1)
    candidates: tuple[ImageSequenceSourceCandidateResponse, ...] = Field(min_length=1)
    manual_override_review_item_id: UUID | None
    override_revision: int = Field(ge=0)


class ImageSequenceSourceOverrideCommand(ApiModel):
    review_item_id: UUID | None
    selected_by: str = Field(min_length=1, max_length=200)


class OperationalImageReviewResolutionCell(ApiModel):
    cell_index: int = Field(ge=0, lt=IMAGE_REVIEW_CELL_COUNT)
    crop_sample_id: Sha256
    symbol_code: str = Field(min_length=1, max_length=64)


class OperationalImageReviewResolutionCommand(ApiModel):
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)
    action: ImageReviewAction
    sequence_number: int | None = Field(default=None, ge=1)
    geometry_revision: int = Field(ge=0)
    cells: tuple[OperationalImageReviewResolutionCell, ...] = Field(
        default=(),
        max_length=IMAGE_REVIEW_CELL_COUNT,
    )
    rejection_reason: str | None = Field(default=None, max_length=500)
    resolved_by: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_variant(self) -> Self:
        if self.action is ImageReviewAction.REJECTED:
            if self.sequence_number is not None or self.cells or not self.rejection_reason:
                raise ValueError("Rejected resolution requires only rejectionReason.")
        elif (
            self.sequence_number is None
            or len(self.cells) != IMAGE_REVIEW_CELL_COUNT
            or self.rejection_reason is not None
        ):
            raise ValueError("Accepted/corrected resolution requires sequenceNumber and 15 cells.")
        return self


class OperationalImageReviewResolutionEventResponse(ApiModel):
    id: UUID
    review_item_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    action: str
    command_sha256: Sha256
    resolved_value: dict[str, object]
    resolved_by: str
    created_at: datetime


class OperationalImageReviewResolutionResponse(ApiModel):
    item: OperationalImageReviewItemResponse
    event: OperationalImageReviewResolutionEventResponse
    created: bool
    counts: OperationalImageReviewCountsResponse
    queue_version: int = Field(ge=1)


class OperationalImageReviewGeometryPreviewCommand(ApiModel):
    lattice_nodes: SourceLatticeNodesPayload | None = None
    expected_proposal_checksum_sha256: Sha256 | None = None
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ] = Field(
        description=(
            "Source-image outer corners of the 5 by 3 symbol lattice in row-major winding; "
            "negative coordinates require an explicitly partial qualification"
        )
    )
    geometry_qualification: GeometryQualificationPayload | None = None

    @model_validator(mode="after")
    def validate_signed_corners(self) -> Self:
        # TASK-0798: the same rule as the grid correction queue; the source
        # editing bounds themselves are enforced by the virtual geometry domain.
        partial = (
            self.geometry_qualification is not None
            and self.geometry_qualification.completeness_status == "pending_partial"
        )
        if not partial and any(point.x < 0 or point.y < 0 for point in self.corners):
            raise ValueError("signed corners require explicitly partial geometry")
        return self


class OperationalImageReviewGeometryCommand(OperationalImageReviewGeometryPreviewCommand):
    idempotency_key: UUID
    corrected_by: str = Field(min_length=1, max_length=200)


class OperationalImageReviewGeometryCellResponse(ApiModel):
    cell_index: int = Field(ge=0, lt=IMAGE_REVIEW_CELL_COUNT)
    row_index: int = Field(ge=0, lt=3)
    column_index: int = Field(ge=0, lt=5)
    crop_sample_id: Sha256
    crop_checksum_sha256: Sha256


class OperationalImageReviewGeometryRevisionResponse(ApiModel):
    lattice_nodes: SourceLatticeNodesPayload | None = None
    expected_proposal_checksum_sha256: Sha256 | None = None
    """One ``virtual_source`` manual geometry revision (D-467 S6, TASK-0796).

    The former v19 file-crop fields (board crop checksum, manual decision
    checksum) are gone: the revision is bound by its source geometry and
    render manifest checksums instead.
    """

    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    command_sha256: Sha256
    # Signed: a partial board may extend past the photo (TASK-0798).
    corners: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ]
    geometry_qualification: GeometryQualificationPayload | None = None
    source_geometry_revision_id: UUID
    geometry_checksum_sha256: Sha256
    virtual_render_spec_checksum_sha256: Sha256
    cropper_version: str
    cells: tuple[OperationalImageReviewGeometryCellResponse, ...] = Field(
        max_length=IMAGE_REVIEW_CELL_COUNT,
    )
    corrected_by: str
    created_at: datetime


class OperationalImageReviewGeometryResponse(ApiModel):
    item: OperationalImageReviewItemResponse
    geometry_revision: OperationalImageReviewGeometryRevisionResponse
    created: bool


def to_operational_item_response(
    item: ImageReviewItem,
) -> OperationalImageReviewItemResponse:
    return OperationalImageReviewItemResponse(
        id=item.id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=item.recognized_board_id,
        status=item.status,
        source_order_index=item.source_order_index,
        position_index=item.position_index,
        sequence_number=item.queue_sequence_number,
        suggested_sequence_number=item.suggested_sequence_number,
        source_checksum_sha256=item.source_checksum_sha256,
        board_checksum_sha256=item.board_checksum_sha256,
        geometry_revision=item.geometry_revision,
        geometry=dict(item.geometry),
        lattice_nodes=lattice_nodes_payload(item.geometry.get("latticeNodes")),
        expected_proposal_checksum_sha256=(
            str(item.geometry["neuralProposalChecksumSha256"])
            if isinstance(item.geometry.get("neuralProposalChecksumSha256"), str)
            else None
        ),
        geometry_qualification=_client_qualification(item.geometry_qualification),
        source_width=item.source_width,
        source_height=item.source_height,
        pipeline_fingerprint=item.pipeline_fingerprint,
        cells=tuple(
            OperationalImageReviewCellResponse(
                cell_index=cell.cell_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
                crop_sample_id=cell.crop_sample_id,
                crop_checksum_sha256=cell.crop_checksum_sha256,
                predicted_symbol_code=cell.predicted_symbol_code,
                current_symbol_code=cell.current_symbol_code or "?",
                confidence=cell.confidence,
                alternatives=tuple(
                    OperationalImageReviewAlternativeResponse(
                        symbol_code=alternative.symbol_code,
                        confidence=alternative.confidence,
                    )
                    for alternative in cell.alternatives
                ),
            )
            for cell in item.cells
        ),
        resolved_value=dict(item.resolved_value) if item.resolved_value else None,
        resolved_by=item.resolved_by,
        resolved_at=item.resolved_at,
        resolution_revision=item.resolution_revision,
        created_at=item.created_at,
    )


def to_operational_page_response(
    page: OperationalImageReviewPage,
) -> OperationalImageReviewPageResponse:
    return OperationalImageReviewPageResponse(
        game_id=page.game_id,
        import_job_id=page.import_job_id,
        view=page.view,
        grid_issue_view=page.grid_issue_view,
        items=tuple(to_operational_item_response(item) for item in page.items),
        counts=to_operational_counts_response(page.counts),
        needs_grid_fix_count=page.needs_grid_fix_count,
        queue_version=page.queue_version,
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_canonical_page_response(
    page: CanonicalImageReviewPage,
) -> CanonicalImageReviewPageResponse:
    return CanonicalImageReviewPageResponse(
        game_id=page.game_id,
        items=tuple(to_operational_item_response(item) for item in page.items),
        counts=to_operational_counts_response(page.counts),
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_operational_counts_response(
    counts: ImageReviewCounts,
) -> OperationalImageReviewCountsResponse:
    return OperationalImageReviewCountsResponse(
        pending=counts.pending,
        accepted=counts.accepted,
        corrected=counts.corrected,
        rejected=counts.rejected,
        superseded=counts.superseded,
        completed=counts.completed,
        total=counts.total,
    )


def to_pending_grid_reinference_preview_response(
    preview: PendingGridReinferencePreview,
) -> PendingGridReinferencePreviewResponse:
    return PendingGridReinferencePreviewResponse(
        game_id=preview.game_id,
        pending_board_count=preview.pending_board_count,
        recalculable_board_count=preview.recalculable_board_count,
        current_v19_board_count=preview.current_v19_board_count,
        protected_board_count=preview.protected_board_count,
        unsupported_virtual_board_count=preview.unsupported_virtual_board_count,
        pending_source_count=preview.pending_source_count,
        partially_resolved_source_count=preview.partially_resolved_source_count,
        fully_resolved_source_count=preview.fully_resolved_source_count,
        geometry_version=preview.geometry_version,
        cropper_version=preview.cropper_version,
        audit_report_checksum_sha256=preview.audit_report_checksum_sha256,
    )


def to_board_import_coverage_response(
    report: BoardImportCoverageReport,
) -> BoardImportCoverageResponse:
    range_from = report.range_from
    range_to = report.range_to
    has_range = range_from is not None or range_to is not None
    return BoardImportCoverageResponse(
        game_id=report.game_id,
        expected_layout_count=report.expected_layout_count,
        counts=BoardImportCoverageCountsResponse(
            expected=report.counts.expected,
            added=report.counts.added,
            missing=report.counts.missing,
            approved=report.counts.approved,
            out_of_range=report.counts.out_of_range,
        ),
        missing_by_reason={
            reason.value: count for reason, count in report.missing_by_reason.items()
        },
        notices=BoardImportCoverageNoticesResponse(
            unnumbered_cut_board_count=report.notices.unnumbered_cut_board_count,
            failed_sources_without_range_count=report.notices.failed_sources_without_range_count,
            active_import_job_count=report.notices.active_import_job_count,
            active_sources_without_range_count=(report.notices.active_sources_without_range_count),
        ),
        view=BoardImportCoverageView(report.view),
        range=(
            BoardImportCoverageRangeResponse(
                **{
                    "from": range_from if range_from is not None else 1,
                    "to": (range_to if range_to is not None else report.expected_layout_count),
                }
            )
            if has_range
            else None
        ),
        range_counts=(
            BoardImportCoverageRangeCountsResponse(
                added=report.range_counts[0],
                missing=report.range_counts[1],
            )
            if report.range_counts is not None
            else None
        ),
        segments=tuple(
            BoardImportCoverageSegmentResponse(
                start=segment.start,
                end=segment.end,
                count=segment.count,
                state=segment.state,
                error_code=segment.error_code,
                geometry_reason_code=segment.geometry_reason_code,
                import_job_id=segment.import_job_id,
            )
            for segment in report.page.segments
        ),
        next_after_sequence_number=report.page.next_after_sequence_number,
        computed_at=report.computed_at,
    )


def to_image_dataset_completeness_response(
    report: ImageDatasetCompleteness,
) -> ImageDatasetCompletenessResponse:
    return ImageDatasetCompletenessResponse(
        game_id=report.game_id,
        expected_layout_count=report.expected_layout_count,
        accepted_board_count=report.accepted_board_count,
        unique_sequence_count=report.unique_sequence_count,
        missing_sequence_count=report.missing_sequence_count,
        duplicate_sequence_count=report.duplicate_sequence_count,
        out_of_range_sequence_count=report.out_of_range_sequence_count,
        missing_sequence_numbers=report.missing_sequence_numbers,
        missing_sequence_numbers_truncated=report.missing_sequence_numbers_truncated,
        manual_override_count=report.manual_override_count,
        completion_percentage=report.completion_percentage,
    )


def to_image_sequence_source_selection_response(
    selection: ImageSequenceSourceSelection,
) -> ImageSequenceSourceSelectionResponse:
    return ImageSequenceSourceSelectionResponse(
        game_id=selection.game_id,
        sequence_number=selection.sequence_number,
        candidates=tuple(
            ImageSequenceSourceCandidateResponse(
                review_item_id=candidate.review_item_id,
                recognized_board_id=candidate.recognized_board_id,
                import_job_id=candidate.import_job_id,
                sequence_number=candidate.sequence_number,
                source_checksum_sha256=candidate.source_checksum_sha256,
                source_relative_path=candidate.source_relative_path,
                width=candidate.width,
                height=candidate.height,
                board_confidence=candidate.board_confidence,
                sequence_confidence=candidate.sequence_confidence,
                geometry_revision=candidate.geometry_revision,
                automatic_rank=candidate.automatic_rank,
                quality_score=candidate.quality_score,
                selected=candidate.selected,
                selected_manually=candidate.selected_manually,
            )
            for candidate in selection.candidates
        ),
        manual_override_review_item_id=selection.manual_override_review_item_id,
        override_revision=selection.override_revision,
    )


def to_operational_event_response(
    event: ImageReviewResolutionEvent,
) -> OperationalImageReviewResolutionEventResponse:
    return OperationalImageReviewResolutionEventResponse(
        id=event.id,
        review_item_id=event.review_item_id,
        revision=event.revision,
        idempotency_key=event.idempotency_key,
        action=event.action,
        command_sha256=event.command_sha256,
        resolved_value=dict(event.resolved_value),
        resolved_by=event.resolved_by,
        created_at=event.created_at,
    )


def to_operational_geometry_revision_response(
    revision: VirtualGridGeometryRevision,
) -> OperationalImageReviewGeometryRevisionResponse:
    return OperationalImageReviewGeometryRevisionResponse(
        id=revision.id,
        review_item_id=revision.review_item_id,
        recognized_board_id=revision.recognized_board_id,
        revision=revision.revision,
        idempotency_key=revision.idempotency_key,
        command_sha256=revision.command_sha256,
        corners=(
            ManualSourceGeometryPoint(x=revision.corners[0].x, y=revision.corners[0].y),
            ManualSourceGeometryPoint(x=revision.corners[1].x, y=revision.corners[1].y),
            ManualSourceGeometryPoint(x=revision.corners[2].x, y=revision.corners[2].y),
            ManualSourceGeometryPoint(x=revision.corners[3].x, y=revision.corners[3].y),
        ),
        lattice_nodes=lattice_nodes_payload(
            None if revision.lattice_nodes is None else revision.lattice_nodes.to_dict()
        ),
        expected_proposal_checksum_sha256=revision.expected_proposal_checksum_sha256,
        geometry_qualification=(
            None
            if revision.geometry_qualification is None
            else GeometryQualificationPayload.model_validate(
                revision.geometry_qualification.to_client_dict()
            )
        ),
        source_geometry_revision_id=revision.source_geometry_revision_id,
        geometry_checksum_sha256=revision.geometry_checksum_sha256,
        virtual_render_spec_checksum_sha256=revision.virtual_render_spec_checksum_sha256,
        cropper_version=revision.cropper_version,
        cells=tuple(
            OperationalImageReviewGeometryCellResponse(
                cell_index=cell.cell_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
                crop_sample_id=cell.crop_sample_id,
                crop_checksum_sha256=cell.crop_checksum_sha256,
            )
            for cell in revision.cells
        ),
        corrected_by=revision.corrected_by,
        created_at=revision.created_at,
    )


__all__ = [
    "OperationalImageReviewPageResponse",
    "CanonicalImageReviewPageResponse",
    "PendingSymbolReinferencePreviewResponse",
    "PendingGridReinferencePreviewResponse",
    "ImageDatasetCompletenessResponse",
    "BoardImportCoverageCountsResponse",
    "BoardImportCoverageNoticesResponse",
    "BoardImportCoverageRangeResponse",
    "BoardImportCoverageRangeCountsResponse",
    "BoardImportCoverageSegmentResponse",
    "BoardImportCoverageResponse",
    "ImageSequenceSourceOverrideCommand",
    "ImageSequenceSourceSelectionResponse",
    "OperationalImageReviewGeometryCommand",
    "OperationalImageReviewGeometryPreviewCommand",
    "OperationalImageReviewGeometryResponse",
    "OperationalImageReviewResolutionCommand",
    "OperationalImageReviewResolutionEventResponse",
    "OperationalImageReviewResolutionResponse",
    "to_operational_event_response",
    "to_operational_counts_response",
    "to_operational_geometry_revision_response",
    "to_operational_item_response",
    "to_operational_page_response",
    "to_canonical_page_response",
    "to_pending_grid_reinference_preview_response",
    "to_image_dataset_completeness_response",
    "to_board_import_coverage_response",
    "to_image_sequence_source_selection_response",
]
