"""OpenAPI contracts for bounded virtual-geometry rollout validation."""

from __future__ import annotations

from uuid import UUID

from game_predictor_worker.images.lateral_partial_contract import (
    GeometryEngineVariant,
    LateralPartialContractError,
    require_geometry_engine_variant_available,
)
from pydantic import Field

from game_predictor_api.application.image_geometry_rollout import (
    ImageGeometryRolloutStart,
    ImageGeometryRolloutStatus,
)
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    ImageImportEnginePolicyPreview,
    ImageImportEnginePolicySnapshot,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.jobs import JobResponse


class ImageGeometryRolloutStatusResponse(ApiModel):
    game_id: UUID
    geometry_mode: str
    cell_asset_mode: str
    rollout_revision: int = Field(ge=0)
    backfill_status: str
    source_count: int = Field(ge=0)
    processed_source_count: int = Field(ge=0)
    virtual_source_count: int = Field(ge=0)
    active_job_id: UUID | None
    last_source_image_id: UUID | None
    failure_code: str | None
    failure_message: str | None


class ImageGeometryRolloutStartResponse(ApiModel):
    rollout: ImageGeometryRolloutStatusResponse
    job: JobResponse | None
    created: bool


class GeometryEngineVariantCapabilityResponse(ApiModel):
    variant: GeometryEngineVariant
    label: str
    enabled: bool
    blocker_code: str | None = None
    blocker_message: str | None = None


class ImageImportEnginePolicyResponse(ApiModel):
    game_id: UUID
    policy: ImageImportEnginePolicy
    geometry_mode: str
    cell_asset_mode: str
    revision: int = Field(ge=0)
    geometry_engine_variants: list[GeometryEngineVariantCapabilityResponse] = Field(
        default_factory=list
    )


class ImageImportEnginePolicyPreviewRequest(ApiModel):
    target_policy: ImageImportEnginePolicy


class ImageImportEnginePolicyPreviewResponse(ApiModel):
    current: ImageImportEnginePolicyResponse
    target: ImageImportEnginePolicyResponse
    preview_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    changes_existing_jobs: bool


class ImageImportEnginePolicyUpdateRequest(ApiModel):
    target_policy: ImageImportEnginePolicy
    expected_revision: int = Field(ge=0)
    preview_token: str = Field(pattern=r"^[0-9a-f]{64}$")


def to_image_import_engine_policy_response(
    value: ImageImportEnginePolicySnapshot,
) -> ImageImportEnginePolicyResponse:
    capabilities: list[GeometryEngineVariantCapabilityResponse] = []
    for variant, label in (
        (GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES, "v1.0 — niepełne boki"),
        (GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1, "v1.1 — korekta plansz"),
    ):
        blocker_code: str | None = None
        blocker_message: str | None = None
        try:
            require_geometry_engine_variant_available(variant)
        except LateralPartialContractError as error:
            blocker_code = error.code
            blocker_message = str(error)
        capabilities.append(
            GeometryEngineVariantCapabilityResponse(
                variant=variant,
                label=label,
                enabled=blocker_code is None,
                blocker_code=blocker_code,
                blocker_message=blocker_message,
            )
        )
    return ImageImportEnginePolicyResponse(
        game_id=value.game_id,
        policy=value.policy,
        geometry_mode=value.geometry_mode,
        cell_asset_mode=value.cell_asset_mode,
        revision=value.revision,
        geometry_engine_variants=capabilities,
    )


def to_image_import_engine_policy_preview_response(
    value: ImageImportEnginePolicyPreview,
) -> ImageImportEnginePolicyPreviewResponse:
    return ImageImportEnginePolicyPreviewResponse(
        current=to_image_import_engine_policy_response(value.current),
        target=to_image_import_engine_policy_response(value.target),
        preview_token=value.preview_token,
        changes_existing_jobs=value.changes_existing_jobs,
    )


def to_image_geometry_rollout_status_response(
    value: ImageGeometryRolloutStatus,
) -> ImageGeometryRolloutStatusResponse:
    return ImageGeometryRolloutStatusResponse(
        game_id=value.game_id,
        geometry_mode=value.geometry_mode,
        cell_asset_mode=value.cell_asset_mode,
        rollout_revision=value.rollout_revision,
        backfill_status=value.backfill_status,
        source_count=value.source_count,
        processed_source_count=value.processed_source_count,
        virtual_source_count=value.virtual_source_count,
        active_job_id=value.active_job_id,
        last_source_image_id=value.last_source_image_id,
        failure_code=value.failure_code,
        failure_message=value.failure_message,
    )


def to_image_geometry_rollout_start_response(
    value: ImageGeometryRolloutStart,
) -> ImageGeometryRolloutStartResponse:
    return ImageGeometryRolloutStartResponse(
        rollout=to_image_geometry_rollout_status_response(value.rollout),
        job=None if value.job is None else JobResponse.from_domain(value.job),
        created=value.created,
    )


__all__ = [
    "GeometryEngineVariantCapabilityResponse",
    "ImageImportEnginePolicyPreviewRequest",
    "ImageImportEnginePolicyPreviewResponse",
    "ImageImportEnginePolicyResponse",
    "ImageImportEnginePolicyUpdateRequest",
    "ImageGeometryRolloutStartResponse",
    "ImageGeometryRolloutStatusResponse",
    "to_image_geometry_rollout_start_response",
    "to_image_geometry_rollout_status_response",
    "to_image_import_engine_policy_preview_response",
    "to_image_import_engine_policy_response",
]
