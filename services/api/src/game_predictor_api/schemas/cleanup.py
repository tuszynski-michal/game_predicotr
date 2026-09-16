"""OpenAPI schemas for preview-bound cleanup operations."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.cleanup import CleanupKind, CleanupPreview, CleanupResult
from game_predictor_api.schemas.catalog import ApiModel


class CleanupCommandRequest(ApiModel):
    preview_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_target: str = Field(min_length=1, max_length=20_000)
    confirmed: bool


class BoardSourceCleanupPreviewRequest(ApiModel):
    sequence_numbers: tuple[int, ...] = Field(min_length=1, max_length=500)


class BoardSourceCleanupCommandRequest(CleanupCommandRequest):
    sequence_numbers: tuple[int, ...] = Field(min_length=1, max_length=500)


class CleanupCountResponse(ApiModel):
    name: str
    count: int


class CleanupPreviewResponse(ApiModel):
    kind: CleanupKind
    target_id: UUID
    target_label: str
    confirmation_target: str
    preview_token: str
    counts: tuple[CleanupCountResponse, ...]
    artifact_paths: tuple[str, ...]
    retained_shared_artifact_count: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def from_domain(cls, preview: CleanupPreview) -> CleanupPreviewResponse:
        snapshot = preview.snapshot
        return cls(
            kind=snapshot.kind,
            target_id=snapshot.target_id,
            target_label=snapshot.target_label,
            confirmation_target=snapshot.confirmation_target,
            preview_token=preview.preview_token,
            counts=tuple(CleanupCountResponse.model_validate(item) for item in snapshot.counts),
            artifact_paths=snapshot.artifact_paths,
            retained_shared_artifact_count=snapshot.retained_shared_artifact_count,
            blockers=snapshot.blockers,
            warnings=snapshot.warnings,
        )


class CleanupResultResponse(ApiModel):
    kind: CleanupKind
    target_id: UUID
    target_label: str
    preview_token: str
    deleted_counts: tuple[CleanupCountResponse, ...]
    deleted_artifact_count: int
    retained_shared_artifact_count: int
    already_completed: bool

    @classmethod
    def from_domain(cls, result: CleanupResult) -> CleanupResultResponse:
        return cls(
            kind=result.kind,
            target_id=result.target_id,
            target_label=result.target_label,
            preview_token=result.preview_token,
            deleted_counts=tuple(
                CleanupCountResponse.model_validate(item) for item in result.deleted_counts
            ),
            deleted_artifact_count=result.deleted_artifact_count,
            retained_shared_artifact_count=result.retained_shared_artifact_count,
            already_completed=result.already_completed,
        )


__all__ = [
    "CleanupCommandRequest",
    "BoardSourceCleanupCommandRequest",
    "BoardSourceCleanupPreviewRequest",
    "CleanupCountResponse",
    "CleanupPreviewResponse",
    "CleanupResultResponse",
]
