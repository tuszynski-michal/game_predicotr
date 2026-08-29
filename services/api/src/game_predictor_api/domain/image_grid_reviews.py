"""Pure states and transitions for validation of one board geometry revision."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_symbol_reviews import SymbolCellQualityIssue


class ImageGridReviewState(StrEnum):
    NEEDS_VALIDATION = "needs_validation"
    NEEDS_CORRECTION = "needs_correction"
    APPROVED = "approved"


class ImageGridReviewView(StrEnum):
    NEEDS_VALIDATION = "needs_validation"
    NEEDS_CORRECTION = "needs_correction"
    ALL = "all"


class ImageGridReviewCursorDirection(StrEnum):
    AFTER = "after"
    BEFORE = "before"


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


@dataclass(frozen=True, slots=True)
class ImageGridReviewListFilter:
    game_id: UUID
    view: ImageGridReviewView
    import_job_id: UUID | None
    source_image_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ImageGridReviewListItem:
    review_item_id: UUID
    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID
    source_image_id: UUID
    position_index: int
    sequence_number: int
    source_checksum_sha256: str
    source_width: int
    source_height: int
    geometry_revision: int
    approved_geometry_revision: int | None
    resolution_revision: int
    topology: BoardTopology
    geometry: Mapping[str, object]
    asset_mode: str
    geometry_engine_name: str | None
    geometry_engine_version: str | None
    board_confidence: float
    reason_codes: tuple[str, ...]
    state: ImageGridReviewState

    @property
    def cursor_key(self) -> tuple[int, str]:
        return self.sequence_number, str(self.review_item_id)


@dataclass(frozen=True, slots=True)
class ImageGridReviewCounts:
    needs_validation: int
    needs_correction: int
    approved: int

    @property
    def total(self) -> int:
        return self.needs_validation + self.needs_correction + self.approved


@dataclass(frozen=True, slots=True)
class ImageGridReviewPage:
    items: tuple[ImageGridReviewListItem, ...]
    counts: ImageGridReviewCounts
    previous_cursor: str | None
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ImageGridReviewSourceAsset:
    review_item_id: UUID
    source_relative_path: str
    source_checksum_sha256: str
    source_width: int
    source_height: int
    geometry_revision: int
    resolution_revision: int
    topology: BoardTopology
    asset_mode: str = "legacy_file"


@dataclass(frozen=True, slots=True)
class ImageGridApprovalResult:
    item: ImageGridReviewListItem
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


def encode_image_grid_review_cursor(
    *,
    review_filter: ImageGridReviewListFilter,
    direction: ImageGridReviewCursorDirection,
    key: tuple[int, str],
) -> str:
    payload = {
        "direction": direction.value,
        "gameId": str(review_filter.game_id),
        "importJobId": (
            None if review_filter.import_job_id is None else str(review_filter.import_job_id)
        ),
        "sourceImageId": (
            None if review_filter.source_image_id is None else str(review_filter.source_image_id)
        ),
        "key": list(key),
        "version": 1,
        "view": review_filter.view.value,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_image_grid_review_cursor(
    value: str,
    *,
    review_filter: ImageGridReviewListFilter,
    direction: ImageGridReviewCursorDirection,
) -> tuple[int, str]:
    try:
        payload = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        key = payload["key"]
        parsed_game_id = UUID(payload["gameId"])
        parsed_import_job_id = (
            None if payload["importJobId"] is None else UUID(payload["importJobId"])
        )
        parsed_source_image_id = (
            None if payload.get("sourceImageId") is None else UUID(payload["sourceImageId"])
        )
        parsed_direction = ImageGridReviewCursorDirection(payload["direction"])
        parsed_view = ImageGridReviewView(payload["view"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CURSOR_INVALID",
            "The grid review cursor is invalid.",
        ) from error
    if (
        payload.get("version") != 1
        or parsed_game_id != review_filter.game_id
        or parsed_import_job_id != review_filter.import_job_id
        or parsed_source_image_id != review_filter.source_image_id
        or parsed_direction is not direction
        or parsed_view is not review_filter.view
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID",
            "The grid review cursor does not belong to this list scope.",
        )
    if (
        not isinstance(key, list)
        or len(key) != 2
        or not isinstance(key[0], int)
        or isinstance(key[0], bool)
        or key[0] < 1
        or not isinstance(key[1], str)
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CURSOR_INVALID",
            "The grid review cursor key is invalid.",
        )
    try:
        UUID(key[1])
    except ValueError as error:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_CURSOR_INVALID",
            "The grid review cursor item identity is invalid.",
        ) from error
    return key[0], key[1]


__all__ = [
    "ImageGridApprovalTransition",
    "ImageGridApprovalResult",
    "ImageGridReview",
    "ImageGridReviewCounts",
    "ImageGridReviewCursorDirection",
    "ImageGridReviewError",
    "ImageGridReviewListFilter",
    "ImageGridReviewListItem",
    "ImageGridReviewPage",
    "ImageGridReviewSourceAsset",
    "ImageGridReviewState",
    "ImageGridReviewView",
    "approve_image_grid_review",
    "decode_image_grid_review_cursor",
    "derive_image_grid_review",
    "encode_image_grid_review_cursor",
]
