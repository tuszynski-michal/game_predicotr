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
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
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
    GEOMETRY_PARTIAL = "geometry_partial"


class SymbolCellReviewAction(StrEnum):
    APPROVE = "approve"
    REASSIGN = "reassign"
    MARK_GRID_ISSUE = "mark_grid_issue"
    MARK_BLURRY = "mark_blurry"
    MARK_UNREADABLE = "mark_unreadable"


class SymbolCellQualityIssue(StrEnum):
    GRID_ISSUE = "grid_issue"
    BLURRY = "blurry"
    UNREADABLE = "unreadable"
    PARTIAL_VISIBILITY = "partial_visibility"


class SymbolCellCropApprovalState(StrEnum):
    CURRENT = "current"
    CHANGED_SINCE_APPROVAL = "changed_since_approval"
    UNVERIFIED = "unverified"


class SymbolCellReviewFilterState(StrEnum):
    """A bounded read filter for current symbol-cell review state."""

    ALL = "all"
    ACTIVE_MODEL_COHORT = "active_model_cohort"
    APPROVED = "approved"
    PENDING = "pending"


class SymbolCellReviewPredictionSource(StrEnum):
    """Which writer produced a cell's current prediction (D-466)."""

    REFERENCE_LIBRARY = "reference_library"
    MODEL = "model"


REFERENCE_LIBRARY_PREDICTION_MODEL_VERSION = "symbol-reference-library-v1"


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
    filter unless ``include_all_symbols`` is set.  The explicit flag keeps the
    historical unknown scope distinct from the game-wide crop view.
    """

    game_id: UUID
    symbol_id: UUID | None
    state: SymbolCellReviewFilterState
    min_confidence: float | None = None
    max_confidence: float | None = None
    include_all_symbols: bool = False
    model_cohort_id: UUID | None = None
    storage_generation: int = 1
    outside_only: bool = False
    prediction_source: SymbolCellReviewPredictionSource | None = None
    changed_from: datetime | None = None
    changed_to: datetime | None = None

    @property
    def has_extended_filters(self) -> bool:
        return (
            self.prediction_source is not None
            or self.changed_from is not None
            or self.changed_to is not None
        )

    def __post_init__(self) -> None:
        if self.outside_only:
            if self.include_all_symbols or self.symbol_id is not None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_SYMBOL_FILTER_INVALID",
                    "Outside is a separate symbol scope.",
                )
            object.__setattr__(self, "min_confidence", None)
            object.__setattr__(self, "max_confidence", None)
        if self.storage_generation < 1:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_STORAGE_GENERATION_INVALID",
                "The symbol-cell review storage generation must be positive.",
            )
        if self.include_all_symbols and self.symbol_id is not None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_SYMBOL_FILTER_INVALID",
                "A game-wide crop filter cannot also select one symbol.",
            )
        if (
            self.state is not SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT
            and self.model_cohort_id is not None
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_MODEL_COHORT_SCOPE_INVALID",
                "A model cohort id is valid only for the active-model cohort filter.",
            )
        for name, value in (
            ("min_confidence", self.min_confidence),
            ("max_confidence", self.max_confidence),
        ):
            if value is not None and (isinstance(value, bool) or not 0.0 <= value <= 1.0):
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
        for name, moment in (("changed_from", self.changed_from), ("changed_to", self.changed_to)):
            if moment is not None and moment.tzinfo is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CHANGED_RANGE_INVALID",
                    f"{name} must include a time zone.",
                )
        if (
            self.changed_from is not None
            and self.changed_to is not None
            and self.changed_from > self.changed_to
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CHANGED_RANGE_INVALID",
                "changed_from cannot be later than changed_to.",
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
    crop_sample_id: str | None
    crop_checksum_sha256: str | None
    board_status: str
    prediction_confidence: float | None = None
    asset_mode: str = "legacy_file"
    render_spec_checksum_sha256: str | None = None
    source_visibility: Literal["full", "partial", "outside"] = "full"

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if not 0 <= self.cell_index < IMAGE_REVIEW_CELL_COUNT:
            raise ValueError("cell_index must be between 0 and 14")
        if self.row_index != self.cell_index // 5 or self.column_index != self.cell_index % 5:
            raise ValueError("cell coordinates must be row-major")
        if self.revision < 0 or self.geometry_revision < 0:
            raise ValueError("review and geometry revisions cannot be negative")
        if self.asset_mode == "none":
            if self.source_visibility != "outside" or any(
                value is not None
                for value in (
                    self.crop_sample_id,
                    self.crop_checksum_sha256,
                    self.render_spec_checksum_sha256,
                    self.prediction_confidence,
                    self.prediction_symbol_code,
                )
            ):
                raise ValueError("outside positions cannot contain an image or prediction")
        elif (
            self.source_visibility == "outside"
            or not _is_sha256(self.crop_sample_id)
            or not _is_sha256(self.crop_checksum_sha256)
        ):
            raise ValueError("crop identity must contain SHA-256 digests")
        if self.prediction_confidence is not None and not 0.0 <= self.prediction_confidence <= 1.0:
            raise ValueError("prediction_confidence must be between 0 and 1")
        if self.asset_mode not in {"legacy_file", "virtual_source", "none"}:
            raise ValueError("asset_mode must be legacy_file or virtual_source")
        if self.asset_mode == "virtual_source" and not _is_sha256(
            self.render_spec_checksum_sha256 or ""
        ):
            raise ValueError("virtual_source requires a render spec checksum")

    @property
    def cursor_key(self) -> tuple[int, int, UUID]:
        return (self.sequence_number, self.cell_index, self.cell_review_id)

    @property
    def is_unknown(self) -> bool:
        return self.assigned_symbol_id is None and self.source_visibility != "outside"


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
    catalog_revision: int
    next_cursor: str | None
    previous_cursor: str | None

    def __post_init__(self) -> None:
        if self.catalog_revision < 0:
            raise ValueError("catalog_revision cannot be negative")


@dataclass(frozen=True, slots=True)
class SymbolCellReviewCountSnapshot:
    counts: SymbolCellReviewCounts
    catalog_revision: int

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
    crop_relative_path: str | None
    crop_checksum_sha256: str
    geometry_revision: int
    cropper_version: str
    asset_mode: str = "legacy_file"

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
        if self.asset_mode == "legacy_file":
            if not self.crop_relative_path or self.crop_relative_path.startswith(("/", "\\")):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                    "A legacy symbol-cell crop path must be a non-empty relative path.",
                )
        elif self.asset_mode == "virtual_source":
            if self.crop_relative_path is not None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                    "A virtual symbol-cell crop identity cannot name a crop file.",
                )
        else:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                "A symbol-cell crop identity has an unsupported asset mode.",
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
class SymbolCellWithoutImageIdentity:
    """A logical position and geometry revision with explicitly absent pixels."""

    cell_index: int
    geometry_revision: int
    cropper_version: str
    asset_mode: Literal["none"] = "none"
    crop_sample_id: None = None
    crop_checksum_sha256: None = None
    crop_relative_path: None = None

    def __post_init__(self) -> None:
        if self.cell_index < 0 or self.geometry_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_REVISION_INVALID",
                "Logical position and revision must be nonnegative.",
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

    def matches(self, crop: SymbolCellCropIdentity | SymbolCellWithoutImageIdentity) -> bool:
        return (
            self.crop_sample_id == crop.crop_sample_id
            and self.crop_checksum_sha256 == crop.crop_checksum_sha256
            and self.geometry_revision == crop.geometry_revision
        )


@dataclass(frozen=True, slots=True)
class SymbolCellReview:
    """The mutable logical state of one crop, bound to its current identity."""

    crop: SymbolCellCropIdentity | SymbolCellWithoutImageIdentity
    predicted_symbol_code: str | None
    assigned_symbol_code: str | None
    review_state: SymbolCellReviewState
    has_grid_issue: bool
    assignment_source: SymbolCellAssignmentSource
    revision: int
    quality_issue: SymbolCellQualityIssue | None = None
    approved_crop: SymbolCellApprovedCropIdentity | None = None
    source_visibility: Literal["full", "partial", "outside"] = "full"

    def __post_init__(self) -> None:
        if (
            isinstance(self.crop, SymbolCellWithoutImageIdentity)
            and self.source_visibility != "outside"
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_INVALID", "Absent image requires outside visibility."
            )
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
            quality_issue is SymbolCellQualityIssue.BLURRY
            and self.review_state is not SymbolCellReviewState.APPROVED
            and not (
                self.assignment_source is SymbolCellAssignmentSource.HUMAN
                and self.approved_crop is not None
                and self.approved_crop.geometry_revision < self.crop.geometry_revision
            )
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BLURRY_STATE_INVALID",
                "A blurry crop keeps its recognized label approved.",
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
    unavailable_cell_indices: tuple[int, ...] | None = None,
) -> tuple[SymbolCellReview, ...]:
    """Map current operational crops into topology-bound cell-review state.

    ``ImageReviewItem.cells`` is already the shared representation which picks
    base ``cell_observations`` for geometry revision zero and the newest
    ``crop_artifacts`` for a corrected geometry.  Keeping this mapper on that
    boundary prevents later backfill and write-through paths from choosing
    different crop identities.
    """

    _validate_complete_cells(
        cells, topology=topology, unavailable_cell_indices=unavailable_cell_indices
    )
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
                asset_mode=cell.asset_mode,
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

    _require_image(review)
    _require_active_symbol(review.assigned_symbol_code, active_symbol_codes)
    retained_quality_issue = _retained_quality_issue_after_label_decision(review)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.quality_issue is retained_quality_issue
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
            quality_issue=retained_quality_issue,
            approved_crop=_current_crop_approval(review),
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
    retained_quality_issue = _retained_quality_issue_after_label_decision(review)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code == target
        and review.quality_issue is retained_quality_issue
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
            quality_issue=retained_quality_issue,
            approved_crop=_current_crop_approval(review),
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=review.revision + 1,
        ),
        changed=True,
    )


def _retained_quality_issue_after_label_decision(
    review: SymbolCellReview,
) -> SymbolCellQualityIssue | None:
    """Keep pixel-bound issues while allowing other issues to be resolved.

    Unreadable and partially visible crops stay permanently excluded from
    training (D-434/435) even once a human confidently labels them -- the
    underlying pixels are still incomplete, so a human's read of them is not
    the same guarantee as a normal, fully visible crop.
    """

    if review.quality_issue in (
        SymbolCellQualityIssue.UNREADABLE,
        SymbolCellQualityIssue.PARTIAL_VISIBILITY,
    ):
        return review.quality_issue
    return None


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


def mark_symbol_cell_blurry(
    review: SymbolCellReview,
    *,
    active_symbol_codes: Iterable[str],
    target_symbol_code: str | None = None,
) -> SymbolCellReviewTransition:
    """Approve one label while excluding the current blurry pixels from training."""

    _require_image(review)
    target = (
        review.assigned_symbol_code
        if target_symbol_code is None
        else _normalize_symbol_code(target_symbol_code)
    )
    _require_active_symbol(target, active_symbol_codes)
    if (
        review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code == target
        and review.quality_issue is SymbolCellQualityIssue.BLURRY
        and review.crop_approval_state is SymbolCellCropApprovalState.CURRENT
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            assigned_symbol_code=target,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
            quality_issue=SymbolCellQualityIssue.BLURRY,
            approved_crop=_current_crop_approval(review),
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
            approved_crop=_current_crop_approval(review),
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
    unavailable_cell_indices: tuple[int, ...] | None = None,
    unchanged_available_indices: frozenset[int] = frozenset(),
) -> tuple[SymbolCellReview, ...]:
    """Apply new crop identities while preserving only safe logical decisions."""

    qualified = unavailable_cell_indices is not None
    if not qualified:
        _validate_complete_symbol_cell_reviews(existing_reviews, topology=topology)
    elif len({review.cell_index for review in existing_reviews}) != len(existing_reviews) or any(
        not 0 <= review.cell_index < topology.cell_count for review in existing_reviews
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "Qualified source history has invalid or repeated logical cells.",
        )
    previous_geometry_revisions = {review.crop.geometry_revision for review in existing_reviews}
    if (
        not qualified
        and (
            len(previous_geometry_revisions) != 1
            or geometry_revision != (next(iter(previous_geometry_revisions)) + 1)
        )
    ) or (
        qualified and any(revision >= geometry_revision for revision in previous_geometry_revisions)
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
        unavailable_cell_indices=unavailable_cell_indices,
    )
    by_index = {review.cell_index: review for review in existing_reviews}
    human_sources = {SymbolCellAssignmentSource.HUMAN, SymbolCellAssignmentSource.BOARD_DECISION}
    updated: list[SymbolCellReview] = []
    for current in mapped:
        previous = by_index.get(current.cell_index)
        if previous is None:
            updated.append(current)
            continue
        available = not qualified or current.cell_index in unchanged_available_indices
        current_pixels = current.crop.crop_checksum_sha256
        history = previous.approved_crop
        if history is None and previous.review_state is SymbolCellReviewState.APPROVED:
            history = _current_crop_approval(previous)
        suggestion = replace(
            current,
            assigned_symbol_code=previous.assigned_symbol_code,
            assignment_source=previous.assignment_source,
            approved_crop=history,
            revision=previous.revision + 1,
        )
        if previous.review_state is SymbolCellReviewState.APPROVED:
            # D-462 R6/R10: only the approved pixels decide. A verification of
            # the current pixels is kept and rebound to the new identity; an
            # approval of other pixels becomes a pending suggestion.
            approved_pixels = (
                previous.crop.crop_checksum_sha256
                if previous.approved_crop is None
                else previous.approved_crop.crop_checksum_sha256
            )
            if available and approved_pixels == current_pixels:
                updated.append(
                    replace(
                        previous,
                        crop=current.crop,
                        approved_crop=_current_crop_approval(current),
                        revision=previous.revision + 1,
                    )
                )
            else:
                updated.append(suggestion)
            continue
        same_pixels = available and previous.crop.crop_checksum_sha256 == current_pixels
        human_label = previous.assignment_source in human_sources
        if previous.quality_issue is SymbolCellQualityIssue.GRID_ISSUE:
            # R5: a saved geometry resolves the report. The reported label is
            # a suggestion only for the same pixels.
            updated.append(
                suggestion
                if same_pixels and human_label
                else replace(current, approved_crop=history, revision=previous.revision + 1)
            )
            continue
        if human_label:
            # A pending human decision (e.g. `unreadable`) describes its
            # pixels: it stays for the same pixels and becomes a suggestion
            # without pixel-bound flags for new ones.
            updated.append(
                replace(previous, crop=current.crop, revision=previous.revision + 1)
                if same_pixels
                else suggestion
            )
            continue
        # A model suggestion follows the current prediction.
        updated.append(replace(current, approved_crop=history, revision=previous.revision + 1))
    return tuple(updated)


def symbol_cell_approval_pixels_changed(
    *,
    asset_mode: str | None,
    crop_checksum_sha256: str | None,
    approved_crop_checksum_sha256: str | None,
    rendered_pixel_checksum_sha256: str | None,
    approved_rendered_pixel_checksum_sha256: str | None,
) -> bool:
    """Whether an approval was given to other pixels than the current ones.

    D-462 R10: only the approved pixels decide; a new geometry revision that
    renders identical pixels keeps the verification.  An approval without any
    pixel identity (a logical position without an image, D-451) never changed.
    """

    if (
        asset_mode == "virtual_source"
        and approved_rendered_pixel_checksum_sha256 is not None
        and rendered_pixel_checksum_sha256 is not None
    ):
        return approved_rendered_pixel_checksum_sha256 != rendered_pixel_checksum_sha256
    if approved_crop_checksum_sha256 is None:
        return False
    return approved_crop_checksum_sha256 != crop_checksum_sha256


def derive_symbol_cell_board_resolution(
    *,
    reviews: Sequence[SymbolCellReview],
    active_symbol_codes: Iterable[str],
    topology: BoardTopology = LEGACY_IMAGE_BOARD_TOPOLOGY,
    stale_approval_cell_indices: frozenset[int] = frozenset(),
) -> SymbolCellBoardResolution | None:
    """Return a full-board decision derived solely from the current cells.

    D-462: the board is a container; approving its geometry is no condition.
    ``None`` means that the parent board stays open because a label is pending,
    a grid issue is reported, a position lacks full source pixels, or an
    approval covers other pixels than the current ones
    (``stale_approval_cell_indices``, see
    ``symbol_cell_approval_pixels_changed``). A manually approved unknown label
    completes the logical board but always makes its decision corrected.
    """

    _validate_complete_symbol_cell_reviews(reviews, topology=topology)
    if stale_approval_cell_indices or any(review.source_visibility != "full" for review in reviews):
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
        review.source_visibility == "full"
        and review.crop.asset_mode != "none"
        and review.review_state is SymbolCellReviewState.APPROVED
        and review.assigned_symbol_code in active
        and review.quality_issue is None
        and review.crop_approval_state is SymbolCellCropApprovalState.CURRENT
        and is_current_owner
        and asset_checksum_verified
    )


def utc_isoformat(value: datetime) -> str:
    """One spelling per instant, so the same range in another offset keeps its cursor."""

    return value.astimezone(UTC).isoformat()


def _extended_filter_payload(review_filter: SymbolCellReviewListFilter) -> dict[str, str]:
    """Only set filters enter a cursor, so cursors of unfiltered lists keep their bytes."""

    payload: dict[str, str] = {}
    if review_filter.prediction_source is not None:
        payload["predictionSource"] = review_filter.prediction_source.value
    if review_filter.changed_from is not None:
        payload["changedFrom"] = utc_isoformat(review_filter.changed_from)
    if review_filter.changed_to is not None:
        payload["changedTo"] = utc_isoformat(review_filter.changed_to)
    return payload


def encode_symbol_cell_review_cursor(
    *,
    review_filter: SymbolCellReviewListFilter,
    direction: SymbolCellReviewCursorDirection,
    key: tuple[int, int, UUID],
) -> str:
    """Encode a keyset cursor that cannot be replayed in another list scope."""

    payload = {
        "direction": direction.value,
        "gameId": str(review_filter.game_id),
        "key": [key[0], key[1], str(key[2])],
        "maxConfidence": review_filter.max_confidence,
        "minConfidence": review_filter.min_confidence,
        **_extended_filter_payload(review_filter),
        "state": review_filter.state.value,
        "storageGeneration": review_filter.storage_generation,
        "symbolId": _symbol_cell_review_filter_scope(review_filter),
        "version": 6,
    }
    if review_filter.state is SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT:
        payload["modelCohortId"] = (
            None if review_filter.model_cohort_id is None else str(review_filter.model_cohort_id)
        )
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_symbol_cell_review_cursor(
    value: str,
    *,
    review_filter: SymbolCellReviewListFilter,
    direction: SymbolCellReviewCursorDirection,
) -> tuple[int, int, UUID]:
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
        parsed_storage_generation = payload["storageGeneration"]
        parsed_model_cohort_id = (
            None if payload.get("modelCohortId") is None else UUID(payload["modelCohortId"])
        )
        # Older cursors omit the extended filters; absence means "not filtered".
        parsed_extended = {
            key: payload.get(key)
            for key in ("predictionSource", "changedFrom", "changedTo")
            if payload.get(key) is not None
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor is invalid.",
        ) from error

    expected_symbol = _symbol_cell_review_filter_scope(review_filter)
    if (
        not isinstance(parsed_storage_generation, int)
        or isinstance(parsed_storage_generation, bool)
        or parsed_storage_generation < 1
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor storage generation is invalid.",
        )
    if (
        payload.get("version") != 6
        or parsed_game_id != review_filter.game_id
        or parsed_symbol_id != expected_symbol
        or parsed_state is not review_filter.state
        or parsed_direction is not direction
        or parsed_min_confidence != review_filter.min_confidence
        or parsed_max_confidence != review_filter.max_confidence
        or parsed_storage_generation != review_filter.storage_generation
        or parsed_model_cohort_id != review_filter.model_cohort_id
        or parsed_extended != _extended_filter_payload(review_filter)
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
        cell_review_id = UUID(key[2])
    except ValueError as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor cell identity is invalid.",
        ) from error
    return key[0], key[1], cell_review_id


def _symbol_cell_review_filter_scope(review_filter: SymbolCellReviewListFilter) -> str:
    if review_filter.outside_only:
        return "outside"
    if review_filter.include_all_symbols:
        return "all"
    return "unknown" if review_filter.symbol_id is None else str(review_filter.symbol_id)


def _validate_complete_cells(
    cells: Sequence[ImageReviewCell],
    *,
    topology: BoardTopology,
    unavailable_cell_indices: tuple[int, ...] | None = None,
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
    missing = set(unavailable_cell_indices or ())
    if any(type(index) is not int or not 0 <= index < topology.cell_count for index in missing):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE", "Invalid unavailable cell mask."
        )
    if (
        indexes != [index for index in range(topology.cell_count) if index not in missing]
        or not coordinates_are_valid
    ):
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


def _is_sha256(value: str | None) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _current_crop_approval(review: SymbolCellReview) -> SymbolCellApprovedCropIdentity | None:
    if isinstance(review.crop, SymbolCellWithoutImageIdentity):
        return None
    return SymbolCellApprovedCropIdentity.from_crop(review.crop)


def _require_image(review: SymbolCellReview) -> None:
    if isinstance(review.crop, SymbolCellWithoutImageIdentity):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_IMAGE_ACTION_UNAVAILABLE",
            "This action requires an image. Assign a symbol or mark the position unreadable.",
        )


__all__ = [
    "UNKNOWN_SYMBOL_CODE",
    "SymbolCellAssignmentSource",
    "SymbolCellApprovedCropIdentity",
    "SymbolCellReviewAsset",
    "SymbolCellBoardResolution",
    "SymbolCellReviewCounts",
    "SymbolCellReviewCountSnapshot",
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
    "mark_symbol_cell_blurry",
    "mark_symbol_cell_grid_issue",
    "mark_symbol_cell_unreadable",
    "reassign_symbol_cell_review",
    "resolve_unreadable_symbol_cell_review",
    "symbol_cell_approval_pixels_changed",
]
