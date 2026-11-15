"""Shared, current-owner selection for explicit corrected-grid symbol jobs."""

from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.sql import Select

from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.source_replacement_guards import current_review_clause

MAX_CORRECTED_SYMBOL_TARGETS = 20_000


def corrected_grid_symbol_targets_query(
    game_id: UUID, *, import_job_id: UUID | None = None
) -> Select[tuple[UUID, int]]:
    """A persisted manual correction, with at least one still-pending real cell.

    The geometry revision join excludes old corrections and reverted geometry;
    the current-review guard excludes replaced sources. No browser state is used.
    """
    pending_cell = exists().where(
        ImageSymbolReviewCellModel.game_id == game_id,
        ImageSymbolReviewCellModel.review_item_id == ImageReviewItemModel.id,
        ImageSymbolReviewCellModel.recognized_board_id == RecognizedBoardModel.id,
        ImageSymbolReviewCellModel.geometry_revision == RecognizedBoardModel.geometry_revision,
        ImageSymbolReviewCellModel.source_available.is_(True),
        ImageSymbolReviewCellModel.review_state == "pending",
    )
    query = (
        select(ImageReviewItemModel.id, RecognizedBoardModel.geometry_revision)
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(
            ImageReviewItemModel.game_id == game_id,
            current_review_clause(ImageReviewItemModel.id),
            ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
            RecognizedBoardModel.asset_mode == "virtual_source",
            exists().where(
                ImageBoardGeometryRevisionModel.review_item_id == ImageReviewItemModel.id,
                ImageBoardGeometryRevisionModel.recognized_board_id == RecognizedBoardModel.id,
                ImageBoardGeometryRevisionModel.revision == RecognizedBoardModel.geometry_revision,
                ImageBoardGeometryRevisionModel.geometry["source"].astext == "manual_override",
                ~ImageBoardGeometryRevisionModel.corrected_by.startswith("system:"),
            ),
            pending_cell,
            or_(
                JobModel.status == JobStatus.WAITING_FOR_REVIEW,
                and_(
                    JobModel.status == JobStatus.COMPLETED,
                    RecognizedBoardModel.geometry_qualification.is_not(None),
                ),
            ),
        )
        .order_by(ImageReviewItemModel.id)
    )
    if import_job_id is not None:
        query = query.where(SourceImageModel.import_job_id == import_job_id)
    return query
