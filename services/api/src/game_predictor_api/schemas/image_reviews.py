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
from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    MAX_IMAGE_REVIEW_ALTERNATIVES,
    ImageDatasetCompleteness,
    ImageReviewAction,
    ImageReviewGeometryRevision,
    ImageReviewItem,
    ImageReviewResolutionEvent,
    ImageReviewView,
    ImageSequenceSourceSelection,
    crop_sample_id,
)
from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class OperationalImageReviewAlternativeResponse(ApiModel):
    symbol_code: str = Field(min_length=1, max_length=64)
    confidence: Probability


class OperationalImageReviewCellResponse(ApiModel):
    observation_id: UUID
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
    pipeline_fingerprint: Sha256
    cells: tuple[OperationalImageReviewCellResponse, ...] = Field(
        min_length=IMAGE_REVIEW_CELL_COUNT,
        max_length=IMAGE_REVIEW_CELL_COUNT,
    )
    resolved_value: dict[str, object] | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_revision: int = Field(ge=0)
    created_at: datetime


class OperationalImageReviewCountsResponse(ApiModel):
    pending: int = Field(ge=0)
    accepted: int = Field(ge=0)
    corrected: int = Field(ge=0)
    rejected: int = Field(ge=0)
    completed: int = Field(ge=0)
    total: int = Field(ge=0)


class OperationalImageReviewPageResponse(ApiModel):
    game_id: UUID
    import_job_id: UUID
    view: ImageReviewView
    items: tuple[OperationalImageReviewItemResponse, ...]
    counts: OperationalImageReviewCountsResponse
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
    protected_board_count: int = Field(ge=0)
    pending_source_count: int = Field(ge=0)
    partially_resolved_source_count: int = Field(ge=0)
    fully_resolved_source_count: int = Field(ge=0)
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


class OperationalImageReviewGeometryPoint(ApiModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class OperationalImageReviewGeometryPreviewCommand(ApiModel):
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ] = Field(
        description="Source-image outer corners of the 5 by 3 symbol lattice in row-major winding"
    )


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
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    command_sha256: Sha256
    decision_checksum_sha256: Sha256 | None = Field(
        default=None,
        description=(
            "Manual v19 decision checksum binding source, board position, versions and actor; "
            "null only for historical geometry revisions"
        ),
    )
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    board_checksum_sha256: Sha256
    cropper_version: str
    cells: tuple[OperationalImageReviewGeometryCellResponse, ...] = Field(
        min_length=IMAGE_REVIEW_CELL_COUNT,
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
        pipeline_fingerprint=item.pipeline_fingerprint,
        cells=tuple(
            OperationalImageReviewCellResponse(
                observation_id=cell.observation_id,
                cell_index=cell.cell_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
                crop_sample_id=cell.crop_sample_id,
                crop_checksum_sha256=cell.crop_checksum_sha256,
                predicted_symbol_code=cell.predicted_symbol_code,
                current_symbol_code=cell.current_symbol_code,
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
        items=tuple(to_operational_item_response(item) for item in page.items),
        counts=OperationalImageReviewCountsResponse(
            pending=page.counts.pending,
            accepted=page.counts.accepted,
            corrected=page.counts.corrected,
            rejected=page.counts.rejected,
            completed=page.counts.completed,
            total=page.counts.total,
        ),
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_canonical_page_response(
    page: CanonicalImageReviewPage,
) -> CanonicalImageReviewPageResponse:
    return CanonicalImageReviewPageResponse(
        game_id=page.game_id,
        items=tuple(to_operational_item_response(item) for item in page.items),
        counts=OperationalImageReviewCountsResponse(
            pending=page.counts.pending,
            accepted=page.counts.accepted,
            corrected=page.counts.corrected,
            rejected=page.counts.rejected,
            completed=page.counts.completed,
            total=page.counts.total,
        ),
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_pending_grid_reinference_preview_response(
    preview: PendingGridReinferencePreview,
) -> PendingGridReinferencePreviewResponse:
    return PendingGridReinferencePreviewResponse(
        game_id=preview.game_id,
        pending_board_count=preview.pending_board_count,
        protected_board_count=preview.protected_board_count,
        pending_source_count=preview.pending_source_count,
        partially_resolved_source_count=preview.partially_resolved_source_count,
        fully_resolved_source_count=preview.fully_resolved_source_count,
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
    revision: ImageReviewGeometryRevision,
) -> OperationalImageReviewGeometryRevisionResponse:
    return OperationalImageReviewGeometryRevisionResponse(
        id=revision.id,
        review_item_id=revision.review_item_id,
        recognized_board_id=revision.recognized_board_id,
        revision=revision.revision,
        idempotency_key=revision.idempotency_key,
        command_sha256=revision.command_sha256,
        decision_checksum_sha256=revision.decision_checksum_sha256,
        corners=(
            OperationalImageReviewGeometryPoint(x=revision.corners[0].x, y=revision.corners[0].y),
            OperationalImageReviewGeometryPoint(x=revision.corners[1].x, y=revision.corners[1].y),
            OperationalImageReviewGeometryPoint(x=revision.corners[2].x, y=revision.corners[2].y),
            OperationalImageReviewGeometryPoint(x=revision.corners[3].x, y=revision.corners[3].y),
        ),
        board_checksum_sha256=revision.board_checksum_sha256,
        cropper_version=revision.cropper_version,
        cells=tuple(
            OperationalImageReviewGeometryCellResponse(
                cell_index=cell.row_index * 5 + cell.column_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
                crop_sample_id=crop_sample_id(
                    recognized_board_id=revision.recognized_board_id,
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    cropper_version=revision.cropper_version,
                    crop_relative_path=cell.crop_relative_path,
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                ),
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
    "ImageSequenceSourceOverrideCommand",
    "ImageSequenceSourceSelectionResponse",
    "OperationalImageReviewGeometryCommand",
    "OperationalImageReviewGeometryPreviewCommand",
    "OperationalImageReviewGeometryResponse",
    "OperationalImageReviewResolutionCommand",
    "OperationalImageReviewResolutionEventResponse",
    "OperationalImageReviewResolutionResponse",
    "to_operational_event_response",
    "to_operational_geometry_revision_response",
    "to_operational_item_response",
    "to_operational_page_response",
    "to_canonical_page_response",
    "to_pending_grid_reinference_preview_response",
    "to_image_dataset_completeness_response",
    "to_image_sequence_source_selection_response",
]
