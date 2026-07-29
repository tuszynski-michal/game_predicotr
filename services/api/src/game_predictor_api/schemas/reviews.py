"""OpenAPI schemas for immutable whole-layout review batches."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.reviews import (
    MAX_REVIEW_BATCH_ITEMS,
    REVIEW_ITEM_CELL_COUNT,
    ReviewBatch,
    ReviewFeedbackExport,
    ReviewItem,
    ReviewItemPage,
    ReviewItemStatus,
    ReviewResolution,
    ReviewResolutionAction,
)
from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ReviewAlternative(ApiModel):
    confidence: Probability
    symbol_code: str = Field(min_length=1, max_length=64)


class ReviewCellSnapshot(ApiModel):
    alternatives: tuple[ReviewAlternative, ...] = Field(min_length=1, max_length=3)
    cell_index: int = Field(ge=0, lt=REVIEW_ITEM_CELL_COUNT)
    column_index: int = Field(ge=0, lt=5)
    confidence: Probability
    crop_relative_path: str = Field(min_length=1, max_length=1000)
    entropy: Probability
    observation_id: Sha256
    predicted_symbol_code: str = Field(min_length=1, max_length=64)
    row_index: int = Field(ge=0, lt=3)
    sample_id: Sha256


class ReviewBoardSnapshot(ApiModel):
    board_id: Sha256
    board_relative_path: str = Field(min_length=1, max_length=1000)
    cells: tuple[ReviewCellSnapshot, ...] = Field(
        min_length=REVIEW_ITEM_CELL_COUNT,
        max_length=REVIEW_ITEM_CELL_COUNT,
    )
    predicted_class_rarity_score: Probability
    prediction_diversity_score: Probability
    selection_rank: int = Field(ge=1, le=MAX_REVIEW_BATCH_ITEMS)
    selection_score: Probability
    sequence_number: int = Field(ge=1)
    source_group: str = Field(min_length=1, max_length=200)
    source_image_checksum_sha256: Sha256
    source_image_id: str = Field(min_length=1, max_length=200)
    source_novelty_score: Probability
    uncertainty_score: Probability


class ReviewSelectionModel(ApiModel):
    model_version: str = Field(min_length=1, max_length=100)
    onnx_artifact_sha256: Sha256
    temperature: float = Field(gt=0)


class ReviewSelectionScoreWeights(ApiModel):
    predicted_class_rarity: Probability
    prediction_diversity: Probability
    source_novelty: Probability
    uncertainty: Probability


class ReviewSelectionBoundary(ApiModel):
    complete_pending_boards_only: bool
    maximum_one_board_per_source_until_all_sources_covered: bool
    mutates_reviewed_labels: bool


class ReviewSelectionReport(ApiModel):
    active_learning_version: str = Field(min_length=1, max_length=100)
    batch_size: int = Field(ge=1, le=MAX_REVIEW_BATCH_ITEMS)
    calibration_report_sha256: Sha256
    candidate_complete_pending_board_count: int = Field(ge=1)
    classes: tuple[str, ...] = Field(min_length=1)
    dataset_sha256: Sha256
    excluded_partial_pending_board_count: int = Field(ge=0)
    inventory_sha256: Sha256
    inventory_version: str = Field(min_length=1, max_length=100)
    model: ReviewSelectionModel
    pending_cell_count: int = Field(ge=1)
    schema_version: int
    score_weights: ReviewSelectionScoreWeights
    selected_board_count: int = Field(ge=1, le=MAX_REVIEW_BATCH_ITEMS)
    selected_boards: tuple[ReviewBoardSnapshot, ...] = Field(
        min_length=1,
        max_length=MAX_REVIEW_BATCH_ITEMS,
    )
    selection_boundary: ReviewSelectionBoundary
    split_sha256: Sha256
    status: str = Field(min_length=1, max_length=100)


class ReviewBatchImport(ApiModel):
    game_id: UUID
    source_report_sha256: Sha256
    report: ReviewSelectionReport


class ReviewBatchResponse(ApiModel):
    id: UUID
    game_id: UUID
    source_report_sha256: Sha256
    active_learning_version: str
    model_version: str
    model_artifact_sha256: Sha256
    calibration_report_sha256: Sha256
    dataset_sha256: Sha256
    split_sha256: Sha256
    inventory_sha256: Sha256
    temperature: float
    item_count: int
    created_at: datetime


class ReviewBatchImportResponse(ApiModel):
    batch: ReviewBatchResponse
    created: bool


class ReviewItemResponse(ApiModel):
    id: UUID
    review_batch_id: UUID
    status: ReviewItemStatus
    snapshot: ReviewBoardSnapshot
    created_at: datetime
    resolved_value: dict[str, object] | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_revision: int = Field(ge=0)


class ReviewItemPageResponse(ApiModel):
    review_batch_id: UUID
    items: tuple[ReviewItemResponse, ...]
    next_after_selection_rank: int | None


class ReviewResolutionLabel(ApiModel):
    cell_index: int = Field(ge=0, lt=REVIEW_ITEM_CELL_COUNT)
    sample_id: Sha256
    symbol_code: str = Field(min_length=1, max_length=64)


class ReviewResolutionCommand(ApiModel):
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)
    action: ReviewResolutionAction
    geometry_accepted: bool
    labels: tuple[ReviewResolutionLabel, ...] = Field(
        default=(),
        max_length=REVIEW_ITEM_CELL_COUNT,
    )
    rejection_reason: str | None = Field(default=None, max_length=500)
    resolved_by: str = Field(min_length=1, max_length=200)


class ReviewResolutionResponse(ApiModel):
    id: UUID
    review_item_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    action: ReviewResolutionAction
    command_sha256: Sha256
    resolved_value: dict[str, object]
    resolved_by: str
    created_at: datetime


class ReviewResolutionCommandResponse(ApiModel):
    item: ReviewItemResponse
    resolution: ReviewResolutionResponse
    created: bool


class ReviewFeedbackExportCreate(ApiModel):
    created_by: str = Field(min_length=1, max_length=200)


class ReviewFeedbackExportResponse(ApiModel):
    id: UUID
    review_batch_id: UUID
    game_id: UUID
    version: int = Field(ge=1)
    source_state_sha256: Sha256
    payload_sha256: Sha256
    sample_count: int = Field(ge=0)
    rejected_item_count: int = Field(ge=0)
    payload: dict[str, object]
    created_by: str
    created_at: datetime


class ReviewFeedbackExportCreateResponse(ApiModel):
    feedback_export: ReviewFeedbackExportResponse
    created: bool


def to_review_batch_response(batch: ReviewBatch) -> ReviewBatchResponse:
    return ReviewBatchResponse(
        id=batch.id,
        game_id=batch.game_id,
        source_report_sha256=batch.source_report_sha256,
        active_learning_version=batch.active_learning_version,
        model_version=batch.model_version,
        model_artifact_sha256=batch.model_artifact_sha256,
        calibration_report_sha256=batch.calibration_report_sha256,
        dataset_sha256=batch.dataset_sha256,
        split_sha256=batch.split_sha256,
        inventory_sha256=batch.inventory_sha256,
        temperature=batch.temperature,
        item_count=batch.item_count,
        created_at=batch.created_at,
    )


def to_review_item_response(item: ReviewItem) -> ReviewItemResponse:
    return ReviewItemResponse(
        id=item.id,
        review_batch_id=item.review_batch_id,
        status=item.status,
        snapshot=ReviewBoardSnapshot.model_validate(item.prediction_snapshot),
        created_at=item.created_at,
        resolved_value=dict(item.resolved_value) if item.resolved_value else None,
        resolved_by=item.resolved_by,
        resolved_at=item.resolved_at,
        resolution_revision=item.resolution_revision,
    )


def to_review_resolution_response(
    resolution: ReviewResolution,
) -> ReviewResolutionResponse:
    return ReviewResolutionResponse(
        id=resolution.id,
        review_item_id=resolution.review_item_id,
        revision=resolution.revision,
        idempotency_key=resolution.idempotency_key,
        action=resolution.action,
        command_sha256=resolution.command_sha256,
        resolved_value=dict(resolution.resolved_value),
        resolved_by=resolution.resolved_by,
        created_at=resolution.created_at,
    )


def to_review_feedback_export_response(
    feedback_export: ReviewFeedbackExport,
) -> ReviewFeedbackExportResponse:
    return ReviewFeedbackExportResponse(
        id=feedback_export.id,
        review_batch_id=feedback_export.review_batch_id,
        game_id=feedback_export.game_id,
        version=feedback_export.version,
        source_state_sha256=feedback_export.source_state_sha256,
        payload_sha256=feedback_export.payload_sha256,
        sample_count=feedback_export.sample_count,
        rejected_item_count=feedback_export.rejected_item_count,
        payload=dict(feedback_export.payload),
        created_by=feedback_export.created_by,
        created_at=feedback_export.created_at,
    )


def to_review_item_page_response(
    review_batch_id: UUID,
    page: ReviewItemPage,
) -> ReviewItemPageResponse:
    return ReviewItemPageResponse(
        review_batch_id=review_batch_id,
        items=tuple(to_review_item_response(item) for item in page.items),
        next_after_selection_rank=page.next_after_selection_rank,
    )


__all__ = [
    "ReviewBatchImport",
    "ReviewBatchImportResponse",
    "ReviewBatchResponse",
    "ReviewFeedbackExportCreate",
    "ReviewFeedbackExportCreateResponse",
    "ReviewFeedbackExportResponse",
    "ReviewItemPageResponse",
    "ReviewItemResponse",
    "ReviewResolutionCommand",
    "ReviewResolutionCommandResponse",
    "ReviewResolutionResponse",
    "ReviewSelectionReport",
    "to_review_batch_response",
    "to_review_feedback_export_response",
    "to_review_item_page_response",
    "to_review_item_response",
    "to_review_resolution_response",
]
