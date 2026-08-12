"""Admin endpoints for geometry calibration candidates and activation."""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.grid_calibration import GridCalibrationService
from game_predictor_api.domain.grid_calibration import GridProfileActivationAction
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_calibration import (
    CreateGridCalibrationCandidateResponse,
    GridCalibrationProfileResponse,
    GridProfileActivationCommand,
    GridProfileActivationCommandResponse,
    GridProfileActivationPreviewResponse,
    GridProfileActivationResponse,
    to_activation_preview_response,
    to_activation_response,
    to_cohort_response,
    to_profile_response,
)


def create_grid_calibration_router(
    service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/grid-calibration-profiles",
        tags=["grid-calibration-profiles"],
    )
    dependency = Depends(service_dependency)
    errors: dict[int | str, dict[str, Any]] = {
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }

    @router.post(
        "",
        response_model=CreateGridCalibrationCandidateResponse,
        operation_id="createGridCalibrationCandidate",
        responses=errors,
    )
    def create_candidate(
        game_id: UUID,
        service: Annotated[GridCalibrationService, dependency],
    ) -> CreateGridCalibrationCandidateResponse:
        cohort, profile, created = service.create_candidate(game_id=game_id)
        return CreateGridCalibrationCandidateResponse(
            cohort=to_cohort_response(cohort),
            profile=to_profile_response(profile),
            created=created,
        )

    @router.get(
        "",
        response_model=list[GridCalibrationProfileResponse],
        operation_id="listGridCalibrationProfiles",
        responses=errors,
    )
    def list_profiles(
        game_id: UUID,
        service: Annotated[GridCalibrationService, dependency],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[GridCalibrationProfileResponse]:
        return [
            to_profile_response(item)
            for item in service.list_profiles(game_id=game_id, limit=limit)
        ]

    @router.get(
        "/{profile_id}/activation-preview",
        response_model=GridProfileActivationPreviewResponse,
        operation_id="previewGridProfileActivation",
        responses=errors,
    )
    def preview_activation(
        game_id: UUID,
        profile_id: UUID,
        service: Annotated[GridCalibrationService, dependency],
        action: GridProfileActivationAction = GridProfileActivationAction.ACTIVATE,
    ) -> GridProfileActivationPreviewResponse:
        return to_activation_preview_response(
            service.preview_activation(game_id=game_id, profile_id=profile_id, action=action)
        )

    def execute_activation(
        *,
        game_id: UUID,
        profile_id: UUID,
        payload: GridProfileActivationCommand,
        action: GridProfileActivationAction,
        service: GridCalibrationService,
    ) -> GridProfileActivationCommandResponse:
        activation, created = service.activate(
            game_id=game_id,
            profile_id=profile_id,
            expected_profile_checksum_sha256=payload.expected_profile_checksum_sha256,
            expected_current_profile_id=payload.expected_current_profile_id,
            action=action,
            actor=payload.actor,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
        return GridProfileActivationCommandResponse(
            activation=to_activation_response(activation), created=created
        )

    @router.post(
        "/{profile_id}/activate",
        response_model=GridProfileActivationCommandResponse,
        operation_id="activateGridProfile",
        responses=errors,
    )
    def activate(
        game_id: UUID,
        profile_id: UUID,
        payload: GridProfileActivationCommand,
        service: Annotated[GridCalibrationService, dependency],
    ) -> GridProfileActivationCommandResponse:
        return execute_activation(
            game_id=game_id,
            profile_id=profile_id,
            payload=payload,
            action=GridProfileActivationAction.ACTIVATE,
            service=service,
        )

    @router.post(
        "/{profile_id}/rollback",
        response_model=GridProfileActivationCommandResponse,
        operation_id="rollbackGridProfile",
        responses=errors,
    )
    def rollback(
        game_id: UUID,
        profile_id: UUID,
        payload: GridProfileActivationCommand,
        service: Annotated[GridCalibrationService, dependency],
    ) -> GridProfileActivationCommandResponse:
        return execute_activation(
            game_id=game_id,
            profile_id=profile_id,
            payload=payload,
            action=GridProfileActivationAction.ROLLBACK,
            service=service,
        )

    @router.get(
        "/registry/activations",
        response_model=list[GridProfileActivationResponse],
        operation_id="listGridProfileActivations",
        responses=errors,
    )
    def list_activations(
        game_id: UUID,
        service: Annotated[GridCalibrationService, dependency],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[GridProfileActivationResponse]:
        return [
            to_activation_response(item)
            for item in service.list_activations(game_id=game_id, limit=limit)
        ]

    return router


__all__ = ["create_grid_calibration_router"]
