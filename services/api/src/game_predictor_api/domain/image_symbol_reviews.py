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
    revision: int
    geometry_revision: int
    crop_checksum_sha256: str
    board_status: str

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if not 0 <= self.cell_index < IMAGE_REVIEW_CELL_COUNT:
            raise ValueError("cell_index must be between 0 and 14")
        if self.row_index != self.cell_index // 5 or self.column_index != self.cell_index % 5:
            raise ValueError("cell coordinates must be row-major")
        if self.revision < 0 or self.geometry_revision < 0:
            raise ValueError("review and geometry revisions cannot be negative")
        if not _is_sha256(self.crop_checksum_sha256):
            raise ValueError("crop_checksum_sha256 must be a SHA-256 digest")

    @property
    def cursor_key(self) -> tuple[int, int, str]:
        return (self.sequence_number, self.cell_index, str(self.review_item_id))


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
    crop_relative_path: str
    crop_checksum_sha256: str
    geometry_revision: int
    current_geometry_revision: int

    def __post_init__(self) -> None:
        if not _is_sha256(self.crop_checksum_sha256):
            raise ValueError("crop_checksum_sha256 must be a SHA-256 digest")
        if self.geometry_revision < 0 or self.current_geometry_revision < 0:
            raise ValueError("geometry revisions cannot be negative")


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
        if not 0 <= self.cell_index < IMAGE_REVIEW_CELL_COUNT:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CELL_INDEX_INVALID",
                "A symbol-cell review index must be between 0 and 14.",
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
class SymbolCellReview:
    """The mutable logical state of one crop, bound to its current identity."""

    crop: SymbolCellCropIdentity
    predicted_symbol_code: str | None
    assigned_symbol_code: str | None
    review_state: SymbolCellReviewState
    has_grid_issue: bool
    assignment_source: SymbolCellAssignmentSource
    revision: int

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_REVISION_INVALID",
                "A symbol-cell review revision cannot be negative.",
            )
        if self.has_grid_issue and self.review_state is not SymbolCellReviewState.PENDING:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_GRID_ISSUE_STATE_INVALID",
                "A crop marked with a grid issue must remain pending.",
            )
        if self.review_state is SymbolCellReviewState.APPROVED and not _is_known_symbol(
            self.assigned_symbol_code
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_APPROVAL_SYMBOL_INVALID",
                "A crop can be approved only with a real assigned symbol.",
            )

    @property
    def cell_index(self) -> int:
        return self.crop.cell_index


@dataclass(frozen=True, slots=True)
class SymbolCellReviewTransition:
    review: SymbolCellReview
    changed: bool


@dataclass(frozen=True, slots=True)
class SymbolCellBoardResolution:
    """A complete board resolution derived solely from all current cell reviews."""

    action: ImageReviewAction
    symbol_codes: tuple[str, ...]


def map_current_symbol_cell_reviews(
    *,
    cells: Sequence[ImageReviewCell],
    geometry_revision: int,
    cropper_version: str,
    assignment_source: SymbolCellAssignmentSource,
) -> tuple[SymbolCellReview, ...]:
    """Map the current 15 operational review crops into cell-review state.

    ``ImageReviewItem.cells`` is already the shared representation which picks
    base ``cell_observations`` for geometry revision zero and the newest
    ``crop_artifacts`` for a corrected geometry.  Keeping this mapper on that
    boundary prevents later backfill and write-through paths from choosing
    different crop identities.
    """

    _validate_complete_cells(cells)
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
    if review.review_state is SymbolCellReviewState.APPROVED and not review.has_grid_issue:
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
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
        and not review.has_grid_issue
    ):
        return SymbolCellReviewTransition(review=review, changed=False)
    return SymbolCellReviewTransition(
        review=replace(
            review,
            assigned_symbol_code=target,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
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
) -> tuple[SymbolCellReview, ...]:
    """Replace all 15 review states after a new geometry produced new crops."""

    _validate_complete_symbol_cell_reviews(existing_reviews)
    previous_geometry_revisions = {review.crop.geometry_revision for review in existing_reviews}
    if len(previous_geometry_revisions) != 1 or geometry_revision != (
        next(iter(previous_geometry_revisions)) + 1
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID",
            "A new geometry must advance one shared geometry revision for all 15 crops.",
        )
    mapped = map_current_symbol_cell_reviews(
        cells=current_cells,
        geometry_revision=geometry_revision,
        cropper_version=cropper_version,
        assignment_source=SymbolCellAssignmentSource.MODEL,
    )
    by_index = {review.cell_index: review for review in existing_reviews}
    return tuple(
        replace(review, revision=by_index[review.cell_index].revision + 1) for review in mapped
    )


def derive_symbol_cell_board_resolution(
    *,
    reviews: Sequence[SymbolCellReview],
    active_symbol_codes: Iterable[str],
) -> SymbolCellBoardResolution | None:
    """Return an accepted/corrected full-board decision only when all 15 approve.

    ``None`` means that the parent board must stay open: a pending crop, an
    unknown assignment or a grid issue is never silently converted into a full
    board decision.
    """

    _validate_complete_symbol_cell_reviews(reviews)
    active = _normalized_active_symbols(active_symbol_codes)
    ordered = tuple(sorted(reviews, key=lambda review: review.cell_index))
    if any(
        review.review_state is not SymbolCellReviewState.APPROVED
        or review.has_grid_issue
        or review.assigned_symbol_code not in active
        for review in ordered
    ):
        return None
    symbols = tuple(review.assigned_symbol_code for review in ordered)
    if any(symbol is None for symbol in symbols):
        return None
    assigned = tuple(symbol for symbol in symbols if symbol is not None)
    predicted = tuple(review.predicted_symbol_code for review in ordered)
    action = ImageReviewAction.ACCEPTED if assigned == predicted else ImageReviewAction.CORRECTED
    return SymbolCellBoardResolution(action=action, symbol_codes=assigned)


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
        "state": review_filter.state.value,
        "symbolId": "unknown" if review_filter.symbol_id is None else str(review_filter.symbol_id),
        "version": 1,
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
            "The symbol-cell review cursor is invalid.",
        ) from error

    expected_symbol = "unknown" if review_filter.symbol_id is None else str(review_filter.symbol_id)
    if (
        payload.get("version") != 1
        or parsed_game_id != review_filter.game_id
        or parsed_symbol_id != expected_symbol
        or parsed_state is not review_filter.state
        or parsed_direction is not direction
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


def _validate_complete_cells(cells: Sequence[ImageReviewCell]) -> None:
    indexes = sorted(cell.cell_index for cell in cells)
    if indexes != list(range(IMAGE_REVIEW_CELL_COUNT)) or any(
        cell.row_index != cell.cell_index // 5 or cell.column_index != cell.cell_index % 5
        for cell in cells
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "Current symbol-cell mapping requires row-major indexes 0..14 exactly once.",
        )


def _validate_complete_symbol_cell_reviews(reviews: Sequence[SymbolCellReview]) -> None:
    indexes = sorted(review.cell_index for review in reviews)
    if indexes != list(range(IMAGE_REVIEW_CELL_COUNT)):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE",
            "A board aggregate requires row-major indexes 0..14 exactly once.",
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
    "SymbolCellReviewAsset",
    "SymbolCellBoardResolution",
    "SymbolCellReviewCounts",
    "SymbolCellCropIdentity",
    "SymbolCellReview",
    "SymbolCellReviewAction",
    "SymbolCellReviewCursorDirection",
    "SymbolCellReviewError",
    "SymbolCellReviewFilterState",
    "SymbolCellReviewListFilter",
    "SymbolCellReviewListItem",
    "SymbolCellReviewPage",
    "SymbolCellReviewState",
    "SymbolCellReviewTransition",
    "approve_symbol_cell_review",
    "decode_symbol_cell_review_cursor",
    "derive_symbol_cell_board_resolution",
    "encode_symbol_cell_review_cursor",
    "invalidate_symbol_cell_reviews_for_geometry",
    "map_current_symbol_cell_reviews",
    "mark_symbol_cell_grid_issue",
    "reassign_symbol_cell_review",
]
