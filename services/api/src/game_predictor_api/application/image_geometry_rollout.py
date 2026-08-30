"""Application boundary for bounded v0.10 geometry rollout validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    ImageImportEnginePolicyPreview,
    ImageImportEnginePolicySnapshot,
)
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

    def engine_policy(self, game_id: UUID) -> ImageImportEnginePolicySnapshot: ...

    def preview_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
    ) -> ImageImportEnginePolicyPreview: ...

    def apply_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
        expected_revision: int,
        preview_token: str,
    ) -> ImageImportEnginePolicySnapshot: ...


class ImageGeometryRolloutService:
    def __init__(self, repository: ImageGeometryRolloutRepository) -> None:
        self._repository = repository

    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        return self._repository.status(game_id)

    def start(self, game_id: UUID) -> ImageGeometryRolloutStart:
        return self._repository.start(game_id)

    def engine_policy(self, game_id: UUID) -> ImageImportEnginePolicySnapshot:
        return self._repository.engine_policy(game_id)

    def preview_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
    ) -> ImageImportEnginePolicyPreview:
        return self._repository.preview_engine_policy(game_id, target=target)

    def apply_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
        expected_revision: int,
        preview_token: str,
    ) -> ImageImportEnginePolicySnapshot:
        return self._repository.apply_engine_policy(
            game_id,
            target=target,
            expected_revision=expected_revision,
            preview_token=preview_token,
        )


__all__ = [
    "ImageGeometryBackfillStatus",
    "ImageGeometryRolloutRepository",
    "ImageGeometryRolloutService",
    "ImageGeometryRolloutStart",
    "ImageGeometryRolloutStatus",
]
