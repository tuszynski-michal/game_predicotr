"""Pure states and transitions for validation of one board geometry revision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_symbol_reviews import SymbolCellQualityIssue


class ImageGridReviewState(StrEnum):
    NEEDS_VALIDATION = "needs_validation"
    NEEDS_CORRECTION = "needs_correction"
    APPROVED = "approved"


class ImageGridReviewError(ValueError):
    """Stable geometry-review failure for later persistence and HTTP adapters."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ImageGridReview:
    topology: BoardTopology
    geometry_revision: int
    approved_geometry_revision: int | None
    state: ImageGridReviewState


@dataclass(frozen=True, slots=True)
class ImageGridApprovalTransition:
    review: ImageGridReview
    changed: bool


def derive_image_grid_review(
    *,
    topology: BoardTopology,
    geometry_revision: int,
    approved_geometry_revision: int | None,
    cell_quality_issues: tuple[SymbolCellQualityIssue | None, ...],
) -> ImageGridReview:
    """Derive one queue state without persisting a second workflow status."""

    if geometry_revision < 0 or (
        approved_geometry_revision is not None
        and not 0 <= approved_geometry_revision <= geometry_revision
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_GEOMETRY_REVISION_INVALID",
            "Approved geometry cannot be newer than the current geometry revision.",
        )
    if len(cell_quality_issues) != topology.cell_count:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE",
            "Geometry review requires one quality state for every configured board cell.",
        )
    if SymbolCellQualityIssue.GRID_ISSUE in cell_quality_issues:
        state = ImageGridReviewState.NEEDS_CORRECTION
    elif approved_geometry_revision != geometry_revision:
        state = ImageGridReviewState.NEEDS_VALIDATION
    else:
        state = ImageGridReviewState.APPROVED
    return ImageGridReview(
        topology=topology,
        geometry_revision=geometry_revision,
        approved_geometry_revision=approved_geometry_revision,
        state=state,
    )


def approve_image_grid_review(review: ImageGridReview) -> ImageGridApprovalTransition:
    """Approve the exact current revision unless a crop still reports bad geometry."""

    if review.state is ImageGridReviewState.NEEDS_CORRECTION:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CORRECTION_REQUIRED",
            "A geometry with a current grid issue must be corrected before approval.",
        )
    if review.state is ImageGridReviewState.APPROVED:
        return ImageGridApprovalTransition(review=review, changed=False)
    return ImageGridApprovalTransition(
        review=ImageGridReview(
            topology=review.topology,
            geometry_revision=review.geometry_revision,
            approved_geometry_revision=review.geometry_revision,
            state=ImageGridReviewState.APPROVED,
        ),
        changed=True,
    )


__all__ = [
    "ImageGridApprovalTransition",
    "ImageGridReview",
    "ImageGridReviewError",
    "ImageGridReviewState",
    "approve_image_grid_review",
    "derive_image_grid_review",
]
