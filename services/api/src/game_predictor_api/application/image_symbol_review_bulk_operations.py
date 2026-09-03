"""Application contract for durable, local-only bulk crop review operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)

MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS = 10_000


class SymbolCellReviewBulkSelectionKind(StrEnum):
    EXPLICIT = "explicit"
    FILTER = "filter"


class SymbolCellReviewBulkOperationStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SymbolCellReviewBulkTargetStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkExplicitTarget:
    cell_review_id: UUID
    expected_revision: int
    expected_geometry_revision: int
    expected_crop_sample_id: str
    expected_crop_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.expected_revision < 0 or self.expected_geometry_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_TARGET_REVISION_INVALID",
                "Expected crop and geometry revisions cannot be negative.",
            )
        if not _is_sha256(self.expected_crop_sample_id) or not _is_sha256(
            self.expected_crop_checksum_sha256
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_TARGET_CROP_INVALID",
                "Every explicit bulk target requires a lowercase SHA-256 crop identity.",
            )


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkFilterSelection:
    symbol_id: UUID | None
    state: SymbolCellReviewFilterState
    catalog_revision: int
    min_confidence: float | None = None
    max_confidence: float | None = None
    excluded_cell_review_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if self.catalog_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_CATALOG_REVISION_INVALID",
                "The filter catalog revision cannot be negative.",
            )
        for name, value in (
            ("min_confidence", self.min_confidence),
            ("max_confidence", self.max_confidence),
        ):
            if value is not None and (isinstance(value, bool) or not 0.0 <= value <= 1.0):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_CONFIDENCE_INVALID",
                    f"{name} must be a number between 0 and 1.",
                )
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_CONFIDENCE_RANGE_INVALID",
                "min_confidence cannot be greater than max_confidence.",
            )
        if len(self.excluded_cell_review_ids) > MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_EXCLUSIONS_LIMIT",
                "A filter bulk operation may exclude at most 10,000 crops.",
            )
        if len(set(self.excluded_cell_review_ids)) != len(self.excluded_cell_review_ids):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_EXCLUSIONS_DUPLICATE",
                "A filter bulk operation cannot contain the same excluded crop twice.",
            )


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkRequest:
    action: SymbolCellReviewAction
    target_symbol_id: UUID | None
    explicit_targets: tuple[SymbolCellReviewBulkExplicitTarget, ...] | None
    filter_selection: SymbolCellReviewBulkFilterSelection | None
    actor: str

    def __post_init__(self) -> None:
        actor = self.actor.strip()
        if not actor or len(actor) > 200:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ACTOR_INVALID",
                "actor must identify the local administrator.",
            )
        if (self.explicit_targets is None) == (self.filter_selection is None):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_SELECTION_INVALID",
                "Provide exactly one selection mode: explicit targets or a frozen filter.",
            )
        if self.explicit_targets is not None:
            if not self.explicit_targets:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_TARGETS_EMPTY",
                    "An explicit bulk operation needs at least one crop.",
                )
            if len(self.explicit_targets) > MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_TARGETS_LIMIT",
                    "An explicit bulk operation may contain at most 10,000 crops.",
                )
            identifiers = tuple(target.cell_review_id for target in self.explicit_targets)
            if len(set(identifiers)) != len(identifiers):
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_TARGETS_DUPLICATE",
                    "An explicit bulk operation cannot contain the same crop twice.",
                )
        if self.action is SymbolCellReviewAction.REASSIGN and self.target_symbol_id is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_REQUIRED",
                "Changing crop symbols requires an active target symbol.",
            )
        if (
            self.action
            not in {
                SymbolCellReviewAction.REASSIGN,
                SymbolCellReviewAction.MARK_BLURRY,
            }
            and self.target_symbol_id is not None
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_UNEXPECTED",
                "Only a symbol reassignment or blurry decision may specify a target symbol.",
            )

    @property
    def selection_kind(self) -> SymbolCellReviewBulkSelectionKind:
        return (
            SymbolCellReviewBulkSelectionKind.EXPLICIT
            if self.explicit_targets is not None
            else SymbolCellReviewBulkSelectionKind.FILTER
        )

    @property
    def command_sha256(self) -> str:
        payload: dict[str, object] = {
            "action": self.action.value,
            "selection": {
                "kind": self.selection_kind.value,
            },
            "targetSymbolId": None if self.target_symbol_id is None else str(self.target_symbol_id),
        }
        if self.explicit_targets is not None:
            payload["selection"] = {
                "kind": "explicit",
                "targets": [
                    {
                        "cellReviewId": str(target.cell_review_id),
                        "expectedCropChecksumSha256": target.expected_crop_checksum_sha256,
                        "expectedCropSampleId": target.expected_crop_sample_id,
                        "expectedGeometryRevision": target.expected_geometry_revision,
                        "expectedRevision": target.expected_revision,
                    }
                    for target in self.explicit_targets
                ],
            }
        else:
            assert self.filter_selection is not None
            payload["selection"] = {
                "catalogRevision": self.filter_selection.catalog_revision,
                "excludedCellReviewIds": sorted(
                    str(identifier) for identifier in self.filter_selection.excluded_cell_review_ids
                ),
                "kind": "filter",
                "maxConfidence": self.filter_selection.max_confidence,
                "minConfidence": self.filter_selection.min_confidence,
                "state": self.filter_selection.state.value,
                "symbolId": (
                    "unknown"
                    if self.filter_selection.symbol_id is None
                    else str(self.filter_selection.symbol_id)
                ),
            }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkPreview:
    action: SymbolCellReviewAction
    selection_kind: SymbolCellReviewBulkSelectionKind
    catalog_revision: int
    target_count: int
    board_count: int
    target_symbol_id: UUID | None


@dataclass(frozen=True, slots=True)
class SymbolCellReviewBulkOperation:
    id: UUID
    job_id: UUID
    game_id: UUID
    action: SymbolCellReviewAction
    target_symbol_id: UUID | None
    selection_kind: SymbolCellReviewBulkSelectionKind
    status: SymbolCellReviewBulkOperationStatus
    catalog_revision: int | None
    target_count: int
    applied_count: int
    conflict_count: int
    failed_count: int
    pending_count: int
    error_code: str | None
    error_message: str | None
    command_sha256: str


class SymbolCellReviewBulkOperationRepository(Protocol):
    def preview(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
    ) -> SymbolCellReviewBulkPreview: ...

    def start(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
        idempotency_key: UUID,
    ) -> tuple[SymbolCellReviewBulkOperation, bool]: ...

    def get(
        self,
        *,
        game_id: UUID,
        operation_id: UUID,
    ) -> SymbolCellReviewBulkOperation | None: ...


class SymbolCellReviewBulkOperationService:
    """Boundary shared by local Admin HTTP and the durable general worker."""

    def __init__(self, repository: SymbolCellReviewBulkOperationRepository) -> None:
        self._repository = repository

    def preview(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
    ) -> SymbolCellReviewBulkPreview:
        _validate_unknown_approval(request)
        return self._repository.preview(game_id=game_id, request=request)

    def start(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
        idempotency_key: UUID,
    ) -> tuple[SymbolCellReviewBulkOperation, bool]:
        _validate_unknown_approval(request)
        return self._repository.start(
            game_id=game_id,
            request=request,
            idempotency_key=idempotency_key,
        )

    def get(self, *, game_id: UUID, operation_id: UUID) -> SymbolCellReviewBulkOperation:
        operation = self._repository.get(game_id=game_id, operation_id=operation_id)
        if operation is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_BULK_OPERATION_NOT_FOUND",
                "The symbol-cell review bulk operation does not exist in this game.",
            )
        return operation


def _validate_unknown_approval(request: SymbolCellReviewBulkRequest) -> None:
    if (
        request.action is SymbolCellReviewAction.APPROVE
        and request.filter_selection is not None
        and request.filter_selection.symbol_id is None
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_BULK_UNKNOWN_APPROVAL_FORBIDDEN",
            "The unknown (?) filter cannot be approved without assigning a real symbol.",
        )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "MAX_EXPLICIT_SYMBOL_CELL_REVIEW_TARGETS",
    "SymbolCellReviewBulkExplicitTarget",
    "SymbolCellReviewBulkFilterSelection",
    "SymbolCellReviewBulkOperation",
    "SymbolCellReviewBulkOperationRepository",
    "SymbolCellReviewBulkOperationService",
    "SymbolCellReviewBulkOperationStatus",
    "SymbolCellReviewBulkPreview",
    "SymbolCellReviewBulkRequest",
    "SymbolCellReviewBulkSelectionKind",
    "SymbolCellReviewBulkTargetStatus",
]
