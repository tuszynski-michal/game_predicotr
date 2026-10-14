"""Explicit, bounded historical acceptance commands; never a recognition run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

HISTORICAL_ACCEPTANCE_POLICY = "historical-v3-status-only-v1"
HISTORICAL_ACCEPTANCE_ACTOR = "system:historical-v3-status-only-v1"


@dataclass(frozen=True, slots=True)
class HistoricalAcceptanceItem:
    ordinal: int
    source_image_id: UUID
    revision_id: UUID | None
    previous_status: str | None
    reasons: tuple[str, ...]
    outcome: str | None


@dataclass(frozen=True, slots=True)
class HistoricalAcceptanceReport:
    game_id: UUID
    operation_id: UUID
    phase: str
    preparation_state: str | None
    started_at: datetime
    preview_cursor: int
    run_cursor: int
    source_count: int
    revision_count: int
    eligible_count: int
    accepted_count: int
    skipped_count: int
    preview_reasons: Mapping[str, int]
    run_reasons: Mapping[str, int]
    items: tuple[HistoricalAcceptanceItem, ...]
    next_item_cursor: int | None


class HistoricalAcceptanceRepository(Protocol):
    def create(self, game_id: UUID, key: UUID) -> HistoricalAcceptanceReport: ...

    def preview_next(
        self, game_id: UUID, operation_id: UUID, cursor: int
    ) -> HistoricalAcceptanceReport: ...

    def confirm(
        self, game_id: UUID, operation_id: UUID, key: UUID
    ) -> HistoricalAcceptanceReport: ...

    def run_next(
        self, game_id: UUID, operation_id: UUID, cursor: int, key: UUID
    ) -> HistoricalAcceptanceReport: ...

    def report(
        self, game_id: UUID, operation_id: UUID, after: int = 0
    ) -> HistoricalAcceptanceReport: ...


class HistoricalAcceptanceService:
    def __init__(self, repository: HistoricalAcceptanceRepository) -> None:
        self._repository = repository

    def create(self, game_id: UUID, key: UUID) -> HistoricalAcceptanceReport:
        return self._repository.create(game_id, key)

    def preview_next(
        self, game_id: UUID, operation_id: UUID, cursor: int
    ) -> HistoricalAcceptanceReport:
        return self._repository.preview_next(game_id, operation_id, cursor)

    def confirm(self, game_id: UUID, operation_id: UUID, key: UUID) -> HistoricalAcceptanceReport:
        return self._repository.confirm(game_id, operation_id, key)

    def run_next(
        self, game_id: UUID, operation_id: UUID, cursor: int, key: UUID
    ) -> HistoricalAcceptanceReport:
        return self._repository.run_next(game_id, operation_id, cursor, key)

    def report(
        self, game_id: UUID, operation_id: UUID, after: int = 0
    ) -> HistoricalAcceptanceReport:
        return self._repository.report(game_id, operation_id, after)
