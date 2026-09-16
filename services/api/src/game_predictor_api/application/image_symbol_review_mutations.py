"""Application boundary for one atomic symbol-cell review decision.

Bulk orchestration intentionally does not live here.  TASK-0294 first needs a
small command that can be retried or composed by a later durable worker while
keeping all writes of one parent board in a single database transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellQualityIssue,
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewState,
)


@dataclass(frozen=True, slots=True)
class SymbolCellReviewMutationCommand:
    """An optimistic, checksum-bound command for exactly one current crop."""

    game_id: UUID
    cell_review_id: UUID
    action: SymbolCellReviewAction
    expected_revision: int
    expected_geometry_revision: int
    expected_crop_sample_id: str
    expected_crop_checksum_sha256: str
    target_symbol_id: UUID | None
    actor: str
    operation_id: UUID | None = None
    resolve_unreadable: bool = False

    def __post_init__(self) -> None:
        if self.expected_revision < 0 or self.expected_geometry_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_REVISION_INVALID",
                "Expected crop and geometry revisions cannot be negative.",
            )
        if not _is_sha256(self.expected_crop_sample_id) or not _is_sha256(
            self.expected_crop_checksum_sha256
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID",
                "A symbol-cell mutation requires the exact current crop identity.",
            )
        actor = self.actor.strip()
        if not actor or len(actor) > 200:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ACTOR_INVALID",
                "actor must identify the local administrator.",
            )
        if self.action is SymbolCellReviewAction.REASSIGN and self.target_symbol_id is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_TARGET_SYMBOL_REQUIRED",
                "Changing a crop symbol requires an active target symbol.",
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
        if self.resolve_unreadable and self.action not in {
            SymbolCellReviewAction.APPROVE,
            SymbolCellReviewAction.REASSIGN,
        }:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_UNREADABLE_ACTION_INVALID",
                "Unreadable cells can be resolved only as a symbol or logical unknown.",
            )


@dataclass(frozen=True, slots=True)
class SymbolCellReviewMutationResult:
    """Current state after one command and any required board aggregation."""

    cell_review_id: UUID
    review_item_id: UUID
    sequence_number: int
    cell_revision: int
    review_state: SymbolCellReviewState
    assigned_symbol_id: UUID | None
    has_grid_issue: bool
    quality_issue: SymbolCellQualityIssue | None
    board_status: str
    board_resolution_action: str | None
    board_reopened: bool
    catalog_revision: int


class SymbolCellReviewMutationRepository(Protocol):
    def apply_mutation(
        self,
        command: SymbolCellReviewMutationCommand,
    ) -> SymbolCellReviewMutationResult: ...

    def apply_board_mutations(
        self,
        commands: tuple[SymbolCellReviewMutationCommand, ...],
    ) -> tuple[SymbolCellReviewMutationResult, ...]: ...


class SymbolCellReviewMutationService:
    """Expose checksum-bound domain actions without coupling them to HTTP or jobs."""

    def __init__(self, repository: SymbolCellReviewMutationRepository) -> None:
        self._repository = repository

    def approve(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        return self._apply(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell_review_id,
                action=SymbolCellReviewAction.APPROVE,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=None,
                actor=actor,
            )
        )

    def reassign(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        target_symbol_id: UUID,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        return self._apply(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell_review_id,
                action=SymbolCellReviewAction.REASSIGN,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=target_symbol_id,
                actor=actor,
            )
        )

    def mark_grid_issue(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        return self._apply(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell_review_id,
                action=SymbolCellReviewAction.MARK_GRID_ISSUE,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=None,
                actor=actor,
            )
        )

    def mark_unreadable(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        return self._apply(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell_review_id,
                action=SymbolCellReviewAction.MARK_UNREADABLE,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=None,
                actor=actor,
            )
        )

    def mark_blurry(
        self,
        *,
        game_id: UUID,
        cell_review_id: UUID,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        target_symbol_id: UUID | None = None,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        return self._apply(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell_review_id,
                action=SymbolCellReviewAction.MARK_BLURRY,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=target_symbol_id,
                actor=actor,
            )
        )

    def _apply(
        self,
        command: SymbolCellReviewMutationCommand,
    ) -> SymbolCellReviewMutationResult:
        return self._repository.apply_mutation(command)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "SymbolCellReviewMutationCommand",
    "SymbolCellReviewMutationRepository",
    "SymbolCellReviewMutationResult",
    "SymbolCellReviewMutationService",
]
