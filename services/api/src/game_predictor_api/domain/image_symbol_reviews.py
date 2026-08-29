"""Pure domain rules for checksum-bound review of individual symbol crops.

The existing operational Reviewer resolves a complete 3 by 5 board at once.
This module defines the smaller, persistent unit which later storage and HTTP
adapters will use.  It intentionally has no dependency on SQLAlchemy, FastAPI
or jobs so that every writer can apply the same validation and board aggregate
rules.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.board_topology import (
    LEGACY_IMAGE_BOARD_TOPOLOGY,
    BoardTopology,
    BoardTopologyError,
)
from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    ImageReviewAction,
    ImageReviewCell,
)

UNKNOWN_SYMBOL_CODE = "?"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SymbolCellReviewState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class SymbolCellAssignmentSource(StrEnum):
    MODEL = "model"
    HUMAN = "human"
    BOARD_DECISION = "board_decision"
    BACKFILL = "backfill"


class SymbolCellReviewAction(StrEnum):
    APPROVE = "approve"
    REASSIGN = "reassign"
    MARK_GRID_ISSUE = "mark_grid_issue"
    MARK_UNREADABLE = "mark_unreadable"


class SymbolCellQualityIssue(StrEnum):
    GRID_ISSUE = "grid_issue"
    UNREADABLE = "unreadable"


class SymbolCellCropApprovalState(StrEnum):
    CURRENT = "current"
    CHANGED_SINCE_APPROVAL = "changed_since_approval"
    UNVERIFIED = "unverified"


class SymbolCellReviewFilterState(StrEnum):
    """A bounded read filter for current symbol-cell review state."""

    ALL = "all"
    APPROVED = "approved"
    PENDING = "pending"


class SymbolCellReviewCursorDirection(StrEnum):
    AFTER = "after"
    BEFORE = "before"


class SymbolCellReviewError(ValueError):
    """Stable validation error shared by later persistence and transport layers."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class SymbolCellReviewListFilter:
    """One local-admin list scope.

    ``symbol_id=None`` means the deliberate synthetic ``unknown`` (`?`)
    filter, never an unfiltered scan of a whole game.
    """

    game_id: UUID
    symbol_id: UUID | None
    state: SymbolCellReviewFilterState
    min_confidence: float | None = None
    max_confidence: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("min_confidence", self.min_confidence),
            ("max_confidence", self.max_confidence),
        ):
            if value is not None and (
                isinstance(value, bool) or not 0.0 <= value <= 1.0
            ):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CONFIDENCE_INVALID",
                    f"{name} must be a number between 0 and 1.",
                )
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CONFIDENCE_RANGE_INVALID",
                "min_confidence cannot be greater than max_confidence.",
            )


@dataclass(frozen=True, slots=True)
class SymbolCellReviewListItem:
    """A compact current crop-review card, without binary crop bytes."""

    cell_review_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int
    cell_index: int
    row_index: int
    column_index: int
    assigned_symbol_id: UUID | None
    assigned_symbol_code: str | None
    assigned_symbol_name: str | None
    prediction_symbol_code: str | None
    review_state: SymbolCellReviewState
    has_grid_issue: bool
    quality_issue: SymbolCellQualityIssue | None
    crop_approval_state: SymbolCellCropApprovalState
    revision: int
    geometry_revision: int
    crop_sample_id: str
    crop_checksum_sha256: str
    board_status: str
    prediction_confidence: float | None = None
    asset_mode: str = "legacy_file"
    render_spec_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if not 0 <= self.cell_index < IMAGE_REVIEW_CELL_COUNT:
            raise ValueError("cell_index must be between 0 and 14")
        if self.row_index != self.cell_index // 5 or self.column_index != self.cell_index % 5:
            raise ValueError("cell coordinates must be row-major")
        if self.revision < 0 or self.geometry_revision < 0:
            raise ValueError("review and geometry revisions cannot be negative")
        if not _is_sha256(self.crop_sample_id) or not _is_sha256(self.crop_checksum_sha256):
            raise ValueError("crop identity must contain SHA-256 digests")
        if self.prediction_confidence is not None and not 0.0 <= self.prediction_confidence <= 1.0:
            raise ValueError("prediction_confidence must be between 0 and 1")
        if self.asset_mode not in {"legacy_file", "virtual_source"}:
            raise ValueError("asset_mode must be legacy_file or virtual_source")
        if self.asset_mode == "virtual_source" and not _is_sha256(
            self.render_spec_checksum_sha256 or ""
        ):
            raise ValueError("virtual_source requires a render spec checksum")

    @property
    def cursor_key(self) -> tuple[int, int, str]:
        return (self.sequence_number, self.cell_index, str(self.review_item_id))

    @property
    def is_unknown(self) -> bool:
        return self.assigned_symbol_id is None


@dataclass(frozen=True, slots=True)
class SymbolCellReviewCounts:
    all_count: int
    approved_count: int
    pending_count: int

    def __post_init__(self) -> None:
        if min(self.all_count, self.approved_count, self.pending_count) < 0:
            raise ValueError("symbol-cell review counts cannot be negative")
        if self.all_count != self.approved_count + self.pending_count:
            raise ValueError("all_count must equal approved_count plus pending_count")


@dataclass(frozen=True, slots=True)
class SymbolCellReviewPage:
    items: tuple[SymbolCellReviewListItem, ...]
    counts: SymbolCellReviewCounts
    catalog_revision: int
    next_cursor: str | None
    previous_cursor: str | None

    def __post_init__(self) -> None:
        if self.catalog_revision < 0:
            raise ValueError("catalog_revision cannot be negative")


@dataclass(frozen=True, slots=True)
class SymbolCellReviewAsset:
    """Current, checksum-bound crop metadata after owner verification."""

    cell_review_id: UUID
    crop_relative_path: str | None
    crop_checksum_sha256: str
    geometry_revision: int
    current_geometry_revision: int
    revision: int = 0
    asset_mode: str = "legacy_file"
    source_checksum_sha256: str | None = None
    normalized_pixel_checksum_sha256: str | None = None
    source_geometry_revision_id: UUID | None = None
    current_source_geometry_revision_id: UUID | None = None
    geometry_checksum_sha256: str | None = None
    logical_cell_key: str | None = None
    render_spec: Mapping[str, object] | None = None
    render_spec_checksum_sha256: str | None = None
    rendered_pixel_checksum_sha256: str | None = None
    extractor_version: str | None = None

    def __post_init__(self) -> None:
        if not _is_sha256(self.crop_checksum_sha256):
            raise ValueError("crop_checksum_sha256 must be a SHA-256 digest")
        if min(self.geometry_revision, self.current_geometry_revision, self.revision) < 0:
            raise ValueError("geometry revisions cannot be negative")
        if self.asset_mode == "legacy_file":
            if not self.crop_relative_path:
                raise ValueError("legacy symbol-cell assets require a crop path")
            return
        if self.asset_mode != "virtual_source":
            raise ValueError("asset_mode must be legacy_file or virtual_source")
        required_checksums = (
            self.source_checksum_sha256,
            self.normalized_pixel_checksum_sha256,
            self.geometry_checksum_sha256,
            self.logical_cell_key,
            self.render_spec_checksum_sha256,
            self.rendered_pixel_checksum_sha256,
        )
        if (
            self.crop_relative_path is not None
            or self.source_geometry_revision_id is None
            or self.current_source_geometry_revision_id is None
            or self.render_spec is None
            or not self.extractor_version
            or not all(value is not None and _is_sha256(value) for value in required_checksums)
        ):
            raise ValueError("virtual symbol-cell assets require complete render provenance")


@dataclass(frozen=True, slots=True)
class SymbolCellCropIdentity:
    """Identity of one exact crop revision, without image bytes."""

    cell_index: int
    crop_sample_id: str
    crop_relative_path: str
    crop_checksum_sha256: str
    geometry_revision: int
    cropper_version: str

    def __post_init__(self) -> None:
        if self.cell_index < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELL_INDEX_INVALID",
                "A symbol-cell review index cannot be negative.",
            )
        if not _is_sha256(self.crop_sample_id) or not _is_sha256(self.crop_checksum_sha256):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                "A symbol-cell crop identity requires SHA-256 sample and crop checksums.",
            )
        if not self.crop_relative_path or self.crop_relative_path.startswith(("/", "\\")):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                "A symbol-cell crop path must be a non-empty relative path.",
            )
        if self.geometry_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
                "A symbol-cell geometry revision cannot be negative.",
            )
        if not self.cropper_version.strip():
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                "A symbol-cell crop identity requires a cropper version.",
            )


@dataclass(frozen=True, slots=True)
class SymbolCellApprovedCropIdentity:
    """The exact crop whose pixels were approved together with a logical label."""

    crop_sample_id: str
    crop_checksum_sha256: str
    geometry_revision: int

    def __post_init__(self) -> None:
        if not _is_sha256(self.crop_sample_id) or not _is_sha256(self.crop_checksum_sha256):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_APPROVED_CROP_INVALID",
                "An approved crop identity requires SHA-256 sample and crop checksums.",
            )
        if self.geometry_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
                "An approved crop geometry revision cannot be negative.",
            )

    @classmethod
    def from_crop(cls, crop: SymbolCellCropIdentity) -> SymbolCellApprovedCropIdentity:
        return cls(
            crop_sample_id=crop.crop_sample_id,
            crop_checksum_sha256=crop.crop_checksum_sha256,
            geometry_revision=crop.geometry_revision,
        )

    def matches(self, crop: SymbolCellCropIdentity) -> bool:
        return (
            self.crop_sample_id == crop.crop_sample_id
            and self.crop_checksum_sha256 == crop.crop_checksum_sha256
            and self.geometry_revision == crop.geometry_revision
        )


@dataclass(frozen=True, slots=True)
class SymbolCellReview:
    """The mutable logical state of one crop, bound to its current identity."""

    crop: SymbolCellCropIdentity
    predicted_symbol_code: str | None
    assigned_symbol_code: str | None
    review_state: SymbolCellReviewState
    has_grid_issue: bool
    assignment_source: SymbolCellAssignmentSource
    revision: int
    quality_issue: SymbolCellQualityIssue | None = None
    approved_crop: SymbolCellApprovedCropIdentity | None = None

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_REVISION_INVALID",
                "A symbol-cell review revision cannot be negative.",
            )
        quality_issue = self.quality_issue
        if self.has_grid_issue:
            if quality_issue not in (None, SymbolCellQualityIssue.GRID_ISSUE):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_QUALITY_ISSUE_CONFLICT",
                    "Legacy grid state conflicts with the explicit crop-quality issue.",
                )
            quality_issue = SymbolCellQualityIssue.GRID_ISSUE
        if quality_issue is SymbolCellQualityIssue.GRID_ISSUE and not self.has_grid_issue:
            object.__setattr__(self, "has_grid_issue", True)
        if quality_issue is not self.quality_issue:
            object.__setattr__(self, "quality_issue", quality_issue)
        if (
            quality_issue is SymbolCellQualityIssue.GRID_ISSUE
            and self.review_state is not SymbolCellReviewState.PENDING
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_GRID_ISSUE_STATE_INVALID",
                "A crop marked with a grid issue must remain pending.",
            )
        if (
            self.review_state is SymbolCellReviewState.APPROVED
            and not _is_known_symbol(self.assigned_symbol_code)
            and quality_issue is not SymbolCellQualityIssue.UNREADABLE
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_APPROVAL_SYMBOL_INVALID",
                "An unknown label can be approved only as an unreadable crop.",
            )

    @property
    def cell_index(self) -> int:
        return self.crop.cell_index

    @property
    def crop_approval_state(self) -> SymbolCellCropApprovalState:
        if self.approved_crop is None:
            return SymbolCellCropApprovalState.UNVERIFIED
        if self.approved_crop.matches(self.crop):
            return SymbolCellCropApprovalState.CURRENT
        return SymbolCellCropApprovalState.CHANGED_SINCE_APPROVAL


@dataclass(frozen=True, slots=True)
class SymbolCellReviewTransition:
    review: SymbolCellReview
    changed: bool


@dataclass(frozen=True, slots=True)
class SymbolCellBoardResolution:
    """A complete board resolution derived solely from all current cell reviews."""

    action: ImageReviewAction
    symbol_codes: tuple[str | None, ...]


def map_current_symbol_cell_reviews(
    *,
    cells: Sequence[ImageReviewCell],
    geometry_revision: int,
    cropper_version: str,
    assignment_source: SymbolCellAssignmentSource,
    topology: BoardTopology = LEGACY_IMAGE_BOARD_TOPOLOGY,
) -> tuple[SymbolCellReview, ...]:
    """Map current operational crops into topology-bound cell-review state.

    ``ImageReviewItem.cells`` is already the shared representation which picks
    base ``cell_observations`` for geometry revision zero and the newest
    ``crop_artifacts`` for a corrected geometry.  Keeping this mapper on that
    boundary prevents later backfill and write-through paths from choosing
    different crop identities.
    """

    _validate_complete_cells(cells, topology=topology)
    if geometry_revision < 0:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
            "A symbol-cell geometry revision cannot be negative.",
        )
    if not cropper_version.strip():
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
            "Current crop mapping requires a cropper version.",
        )

    return tuple(
        SymbolCellReview(
            crop=SymbolCellCropIdentity(
                cell_index=cell.cell_index,
                crop_sample_id=cell.crop_sample_id,
                crop_relative_path=cell.crop_relative_path,
                crop_checksum_sha256=cell.crop_checksum_sha256,
                geometry_revision=geometry_revision,
                cropper_version=cropper_version,
            ),
            predicted_symbol_code=_normalize_symbol_code(cell.predicted_symbol_code),
            assigned_symbol_code=_normalize_symbol_code(cell.current_symbol_code),
            review_state=SymbolCellReviewState.PENDING,
            has_grid_issue=False,
            assignment_source=assignment_source,
            revision=0,
        )
        for cell in sorted(cells, key=lambda value: value.cell_index)
    )


def approve_symbol_cell_review(
    review: SymbolCellReview,
    *,
    active_symbol_codes: Iterable[str],
) -> SymbolCellReviewTransition:
    """Approve the exact current crop without changing its assigned symbol."""

    _require_active_symbol(review.assigned_symbol_code, active_symbol_codes)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.quality_issue is None
        and review.crop_approval_state
        in {
            SymbolCellCropApprovalState.CURRENT,
            SymbolCellCropApprovalState.UNVERIFIED,
        }
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
            quality_issue=None,
            approved_crop=SymbolCellApprovedCropIdentity.from_crop(review.crop),
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def reassign_symbol_cell_review(
    review: SymbolCellReview,
    *,
    target_symbol_code: str,
    active_symbol_codes: Iterable[str],
) -> SymbolCellReviewTransition:
    """Set a human-selected symbol and approve the exact current crop."""

    target = _normalize_symbol_code(target_symbol_code)
    _require_active_symbol(target, active_symbol_codes)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code == target
        and review.quality_issue is None
        and review.crop_approval_state
        in {
            SymbolCellCropApprovalState.CURRENT,
            SymbolCellCropApprovalState.UNVERIFIED,
        }
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            assigned_symbol_code=target,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
            quality_issue=None,
            approved_crop=SymbolCellApprovedCropIdentity.from_crop(review.crop),
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def mark_symbol_cell_grid_issue(review: SymbolCellReview) -> SymbolCellReviewTransition:
    """Keep the assignment for audit but reopen this crop for geometry correction."""

    if review.review_state is SymbolCellReviewState.PENDING and review.has_grid_issue:
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            review_state=SymbolCellReviewState.PENDING,
            has_grid_issue=True,
            quality_issue=SymbolCellQualityIssue.GRID_ISSUE,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def mark_symbol_cell_unreadable(review: SymbolCellReview) -> SymbolCellReviewTransition:
    """Reopen a logically unresolved crop without treating it as bad geometry."""

    if (
        review.review_state is SymbolCellReviewState.PENDING
        and review.quality_issue is SymbolCellQualityIssue.UNREADABLE
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            review_state=SymbolCellReviewState.PENDING,
            has_grid_issue=False,
            quality_issue=SymbolCellQualityIssue.UNREADABLE,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def resolve_unreadable_symbol_cell_review(
    review: SymbolCellReview,
    *,
    target_symbol_code: str | None,
    active_symbol_codes: Iterable[str],
) -> SymbolCellReviewTransition:
    """Approve a manual logical label while keeping the current crop non-training."""

    if review.quality_issue is not SymbolCellQualityIssue.UNREADABLE:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_UNREADABLE_REQUIRED",
            "Only a crop marked unreadable can be resolved through this workflow.",
        )
    target = _normalize_symbol_code(target_symbol_code)
    if target is not None:
        _require_active_symbol(target, active_symbol_codes)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code == target
        and review.crop_approval_state is SymbolCellCropApprovalState.CURRENT
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            assigned_symbol_code=target,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
            quality_issue=SymbolCellQualityIssue.UNREADABLE,
            approved_crop=SymbolCellApprovedCropIdentity.from_crop(review.crop),
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def invalidate_symbol_cell_reviews_for_geometry(
    *,
    existing_reviews: Sequence[SymbolCellReview],
    current_cells: Sequence[ImageReviewCell],
    geometry_revision: int,
    cropper_version: str,
    topology: BoardTopology = LEGACY_IMAGE_BOARD_TOPOLOGY,
) -> tuple[SymbolCellReview, ...]:
    """Apply new crop identities while preserving only safe logical decisions."""

    _validate_complete_symbol_cell_reviews(existing_reviews, topology=topology)
    previous_geometry_revisions = {review.crop.geometry_revision for review in existing_reviews}
    if len(previous_geometry_revisions) != 1 or geometry_revision != (
        next(iter(previous_geometry_revisions)) + 1
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
            "A new geometry must advance one shared revision for every board crop.",
        )
    mapped = map_current_symbol_cell_reviews(
        cells=current_cells,
        geometry_revision=geometry_revision,
        cropper_version=cropper_version,
        assignment_source=SymbolCellAssignmentSource.MODEL,
        topology=topology,
    )
    by_index = {review.cell_index: review for review in existing_reviews}
    updated: list[SymbolCellReview] = []
    for current in mapped:
        previous = by_index[current.cell_index]
        if previous.quality_issue is SymbolCellQualityIssue.GRID_ISSUE:
            updated.append(replace(current, revision=previous.revision + 1))
            continue
        if previous.review_state is SymbolCellReviewState.APPROVED:
            approved_crop = previous.approved_crop or SymbolCellApprovedCropIdentity.from_crop(
                previous.crop
            )
            updated.append(
                replace(
                    current,
                    assigned_symbol_code=previous.assigned_symbol_code,
                    review_state=SymbolCellReviewState.APPROVED,
                    quality_issue=previous.quality_issue,
                    assignment_source=previous.assignment_source,
                    approved_crop=approved_crop,
                    revision=previous.revision + 1,
                )
            )
            continue
        if previous.quality_issue is SymbolCellQualityIssue.UNREADABLE:
            updated.append(
                replace(
                    current,
                    assigned_symbol_code=previous.assigned_symbol_code,
                    quality_issue=SymbolCellQualityIssue.UNREADABLE,
                    assignment_source=previous.assignment_source,
                    revision=previous.revision + 1,
                )
            )
            continue
        updated.append(replace(current, revision=previous.revision + 1))
    return tuple(updated)


def derive_symbol_cell_board_resolution(
    *,
    reviews: Sequence[SymbolCellReview],
    active_symbol_codes: Iterable[str],
    topology: BoardTopology = LEGACY_IMAGE_BOARD_TOPOLOGY,
    geometry_approved: bool = True,
) -> SymbolCellBoardResolution | None:
    """Return a full-board decision only from approved geometry and labels.

    ``None`` means that the parent board must stay open because of pending
    labels, a grid issue or unapproved geometry. A manually approved unknown
    label completes the logical board but always makes its decision corrected.
    """

    _validate_complete_symbol_cell_reviews(reviews, topology=topology)
    if not geometry_approved:
        return None
    active = _normalized_active_symbols(active_symbol_codes)
    ordered = tuple(sorted(reviews, key=lambda review: review.cell_index))
    if any(
        review.review_state is not SymbolCellReviewState.APPROVED
        or review.quality_issue is SymbolCellQualityIssue.GRID_ISSUE
        or (review.assigned_symbol_code is not None and review.assigned_symbol_code not in active)
        for review in ordered
    ):
        return None
    symbols = tuple(review.assigned_symbol_code for review in ordered)
    predicted = tuple(review.predicted_symbol_code for review in ordered)
    action = ImageReviewAction.ACCEPTED if symbols == predicted else ImageReviewAction.CORRECTED
    return SymbolCellBoardResolution(action=action, symbol_codes=symbols)


def is_symbol_cell_training_eligible(
    review: SymbolCellReview,
    *,
    active_symbol_codes: Iterable[str],
    is_current_owner: bool,
    asset_checksum_verified: bool,
) -> bool:
    """Return the complete domain-side gate for using the current crop in training."""

    active = _normalized_active_symbols(active_symbol_codes)
    return (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code in active
        and review.quality_issue is None
        and review.crop_approval_state is SymbolCellCropApprovalState.CURRENT
        and is_current_owner
        and asset_checksum_verified
    )


def encode_symbol_cell_review_cursor(
    *,
    review_filter: SymbolCellReviewListFilter,
    direction: SymbolCellReviewCursorDirection,
    key: tuple[int, int, str],
) -> str:
    """Encode a keyset cursor that cannot be replayed in another list scope."""

    payload = {
        "direction": direction.value,
        "gameId": str(review_filter.game_id),
        "key": list(key),
        "maxConfidence": review_filter.max_confidence,
        "minConfidence": review_filter.min_confidence,
        "state": review_filter.state.value,
        "symbolId": "unknown" if review_filter.symbol_id is None else str(review_filter.symbol_id),
        "version": 2,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_symbol_cell_review_cursor(
    value: str,
    *,
    review_filter: SymbolCellReviewListFilter,
    direction: SymbolCellReviewCursorDirection,
) -> tuple[int, int, str]:
    """Decode and bind a cursor to game, symbol filter, state and direction."""

    try:
        payload = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        key = payload["key"]
        parsed_game_id = UUID(payload["gameId"])
        parsed_symbol_id = payload["symbolId"]
        parsed_direction = SymbolCellReviewCursorDirection(payload["direction"])
        parsed_state = SymbolCellReviewFilterState(payload["state"])
        parsed_min_confidence = payload.get("minConfidence")
        parsed_max_confidence = payload.get("maxConfidence")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor is invalid.",
        ) from error

    expected_symbol = "unknown" if review_filter.symbol_id is None else str(review_filter.symbol_id)
    if (
        payload.get("version") != 2
        or parsed_game_id != review_filter.game_id
        or parsed_symbol_id != expected_symbol
        or parsed_state is not review_filter.state
        or parsed_direction is not direction
        or parsed_min_confidence != review_filter.min_confidence
        or parsed_max_confidence != review_filter.max_confidence
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID",
            "The symbol-cell review cursor does not belong to this list scope.",
        )
    if (
        not isinstance(key, list)
        or len(key) != 3
        or not isinstance(key[0], int)
        or isinstance(key[0], bool)
        or key[0] < 1
        or not isinstance(key[1], int)
        or isinstance(key[1], bool)
        or not 0 <= key[1] < IMAGE_REVIEW_CELL_COUNT
        or not isinstance(key[2], str)
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor key is invalid.",
        )
    try:
        UUID(key[2])
    except ValueError as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor item identity is invalid.",
        ) from error
    return key[0], key[1], key[2]


def _validate_complete_cells(
    cells: Sequence[ImageReviewCell],
    *,
    topology: BoardTopology,
) -> None:
    indexes = sorted(cell.cell_index for cell in cells)
    try:
        for cell in cells:
            topology.validate_coordinates(
                cell_index=cell.cell_index,
                row_index=cell.row_index,
                column_index=cell.column_index,
            )
        coordinates_are_valid = True
    except BoardTopologyError:
        coordinates_are_valid = False
    if indexes != list(range(topology.cell_count)) or not coordinates_are_valid:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "Current symbol-cell mapping requires every configured row-major index exactly once.",
        )


def _validate_complete_symbol_cell_reviews(
    reviews: Sequence[SymbolCellReview],
    *,
    topology: BoardTopology,
) -> None:
    indexes = sorted(review.cell_index for review in reviews)
    if indexes != list(range(topology.cell_count)):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "A board aggregate requires every configured row-major index exactly once.",
        )


def _normalize_symbol_code(value: str | None) -> str | None:
    normalized = value.strip() if isinstance(value, str) else None
    return normalized if normalized and normalized != UNKNOWN_SYMBOL_CODE else None


def _normalized_active_symbols(symbol_codes: Iterable[str]) -> frozenset[str]:
    active = frozenset(
        normalized
        for symbol_code in symbol_codes
        if (normalized := _normalize_symbol_code(symbol_code)) is not None
    )
    if not active:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ACTIVE_SYMBOLS_EMPTY",
            "At least one active real symbol is required for a symbol-cell review.",
        )
    return active


def _require_active_symbol(symbol_code: str | None, active_symbol_codes: Iterable[str]) -> None:
    active = _normalized_active_symbols(active_symbol_codes)
    if symbol_code not in active:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_SYMBOL_INVALID",
            "A crop can be approved only with an active real game symbol.",
        )


def _is_known_symbol(symbol_code: str | None) -> bool:
    return _normalize_symbol_code(symbol_code) is not None


def _is_sha256(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value))


__all__ = [
    "UNKNOWN_SYMBOL_CODE",
    "SymbolCellAssignmentSource",
    "SymbolCellApprovedCropIdentity",
    "SymbolCellReviewAsset",
    "SymbolCellBoardResolution",
    "SymbolCellReviewCounts",
    "SymbolCellCropApprovalState",
    "SymbolCellCropIdentity",
    "SymbolCellReview",
    "SymbolCellReviewAction",
    "SymbolCellReviewCursorDirection",
    "SymbolCellReviewError",
    "SymbolCellReviewFilterState",
    "SymbolCellReviewListFilter",
    "SymbolCellReviewListItem",
    "SymbolCellReviewPage",
    "SymbolCellQualityIssue",
    "SymbolCellReviewState",
    "SymbolCellReviewTransition",
    "approve_symbol_cell_review",
    "decode_symbol_cell_review_cursor",
    "derive_symbol_cell_board_resolution",
    "encode_symbol_cell_review_cursor",
    "invalidate_symbol_cell_reviews_for_geometry",
    "is_symbol_cell_training_eligible",
    "map_current_symbol_cell_reviews",
    "mark_symbol_cell_grid_issue",
    "mark_symbol_cell_unreadable",
    "reassign_symbol_cell_review",
    "resolve_unreadable_symbol_cell_review",
]
