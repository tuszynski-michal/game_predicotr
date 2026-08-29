"""Application boundary for bounded v0.10 geometry rollout validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import Job

ImageGeometryBackfillStatus = Literal["not_started", "processing", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class ImageGeometryRolloutStatus:
    game_id: UUID
    geometry_mode: str
    cell_asset_mode: str
    rollout_revision: int
    backfill_status: ImageGeometryBackfillStatus
    source_count: int
    processed_source_count: int
    virtual_source_count: int
    active_job_id: UUID | None
    last_source_image_id: UUID | None
    failure_code: str | None
    failure_message: str | None


@dataclass(frozen=True, slots=True)
class ImageGeometryRolloutStart:
    rollout: ImageGeometryRolloutStatus
    job: Job | None
    created: bool


class ImageGeometryRolloutRepository(Protocol):
    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus: ...

    def start(self, game_id: UUID) -> ImageGeometryRolloutStart: ...


class ImageGeometryRolloutService:
    def __init__(self, repository: ImageGeometryRolloutRepository) -> None:
        self._repository = repository

    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        return self._repository.status(game_id)

    def start(self, game_id: UUID) -> ImageGeometryRolloutStart:
        return self._repository.start(game_id)


__all__ = [
    "ImageGeometryBackfillStatus",
    "ImageGeometryRolloutRepository",
    "ImageGeometryRolloutService",
    "ImageGeometryRolloutStart",
    "ImageGeometryRolloutStatus",
]
