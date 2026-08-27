"""Durable preparation of the symbol-cell review projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import Job

SymbolCellReviewProjectionState = Literal[
    "not_started", "rebuilding", "ready", "failed"
]


@dataclass(frozen=True, slots=True)
class SymbolCellReviewProjectionStatus:
    game_id: UUID
    status: SymbolCellReviewProjectionState
    expected_board_count: int
    expected_cell_count: int
    processed_board_count: int
    persisted_cell_count: int
    missing_sequence_count: int
    invalid_crop_count: int
    invalid_geometry_count: int
    failure_message: str | None
    sample_problem_review_item_ids: tuple[UUID, ...]
    active_job_id: UUID | None


@dataclass(frozen=True, slots=True)
class SymbolCellReviewProjectionStart:
    status: SymbolCellReviewProjectionStatus
    job: Job | None
    created: bool


class SymbolCellReviewBackfillRepository(Protocol):
    def status(self, game_id: UUID) -> SymbolCellReviewProjectionStatus: ...

    def start(self, game_id: UUID) -> SymbolCellReviewProjectionStart: ...


class SymbolCellReviewBackfillService:
    def __init__(self, repository: SymbolCellReviewBackfillRepository) -> None:
        self._repository = repository

    def status(self, game_id: UUID) -> SymbolCellReviewProjectionStatus:
        return self._repository.status(game_id)

    def start(self, game_id: UUID) -> SymbolCellReviewProjectionStart:
        return self._repository.start(game_id)


__all__ = [
    "SymbolCellReviewBackfillRepository",
    "SymbolCellReviewBackfillService",
    "SymbolCellReviewProjectionStart",
    "SymbolCellReviewProjectionState",
    "SymbolCellReviewProjectionStatus",
]
