"""Admin endpoints that enqueue and inspect durable symbol training."""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.symbol_model_iterations import SymbolModelIterationService
from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryService
from game_predictor_api.domain.symbol_model_iterations import SymbolTrainingConfiguration
from game_predictor_api.domain.symbol_model_registry import SymbolModelActivationAction
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_api.schemas.symbol_model_iterations import (
    CreateSymbolTrainingCommand,
    CreateSymbolTrainingResponse,
    SymbolModelActivationCommand,
    SymbolModelActivationCommandResponse,
    SymbolModelActivationPreviewResponse,
    SymbolModelActivationResponse,
    SymbolModelIterationResponse,
    to_activation_preview_response,
    to_activation_response,
    to_iteration_response,
)


def create_symbol_model_iteration_router(
    service_dependency: Callable[..., object],
    registry_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/symbol-model-iterations", tags=["symbol-model-iterations"]
    )
    dependency = Depends(service_dependency)
    registry_dependency = Depends(registry_service_dependency)
    errors: dict[int | str, dict[str, Any]] = {
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }

    @router.post(
        "",
        response_model=CreateSymbolTrainingResponse,
        operation_id="createSymbolTraining",
        responses=errors,
    )
    def create_training(
        game_id: UUID,
        payload: CreateSymbolTrainingCommand,
        service: Annotated[SymbolModelIterationService, dependency],
    ) -> CreateSymbolTrainingResponse:
        value = payload.configuration
        iteration, job, created = service.create_training(
            game_id=game_id,
            cohort_id=payload.cohort_id,
            idempotency_key=payload.idempotency_key,
            configuration=SymbolTrainingConfiguration(
                epochs=value.epochs,
                batch_size=value.batch_size,
                learning_rate=value.learning_rate,
                weight_decay=value.weight_decay,
                seed=value.seed,
                input_size=value.input_size,
            ),
        )
        return CreateSymbolTrainingResponse(
            iteration=to_iteration_response(iteration),
            job=JobResponse.from_domain(job),
            created=created,
        )

    @router.get(
        "",
        response_model=list[SymbolModelIterationResponse],
        operation_id="listSymbolModelIterations",
        responses=errors,
    )
    def list_iterations(
        game_id: UUID,
        service: Annotated[SymbolModelIterationService, dependency],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[SymbolModelIterationResponse]:
        return [
            to_iteration_response(value) for value in service.list(game_id=game_id, limit=limit)
        ]

    @router.get(
        "/{iteration_id}",
        response_model=SymbolModelIterationResponse,
        operation_id="getSymbolModelIteration",
        responses=errors,
    )
    def get_iteration(
        game_id: UUID,
        iteration_id: UUID,
        service: Annotated[SymbolModelIterationService, dependency],
    ) -> SymbolModelIterationResponse:
        return to_iteration_response(service.get(game_id=game_id, iteration_id=iteration_id))

    @router.get(
        "/{iteration_id}/activation-preview",
        response_model=SymbolModelActivationPreviewResponse,
        operation_id="previewSymbolModelActivation",
        responses=errors,
    )
    def preview_activation(
        game_id: UUID,
        iteration_id: UUID,
        service: Annotated[SymbolModelRegistryService, registry_dependency],
        action: SymbolModelActivationAction = SymbolModelActivationAction.ACTIVATE,
    ) -> SymbolModelActivationPreviewResponse:
        return to_activation_preview_response(
            service.preview(
                game_id=game_id,
                model_iteration_id=iteration_id,
                action=action,
            )
        )

    def execute_activation(
        *,
        game_id: UUID,
        iteration_id: UUID,
        payload: SymbolModelActivationCommand,
        action: SymbolModelActivationAction,
        service: SymbolModelRegistryService,
    ) -> SymbolModelActivationCommandResponse:
        activation, created = service.activate(
            game_id=game_id,
            model_iteration_id=iteration_id,
            expected_manifest_checksum_sha256=payload.expected_manifest_checksum_sha256,
            expected_current_model_iteration_id=payload.expected_current_model_iteration_id,
            action=action,
            actor=payload.actor,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
        return SymbolModelActivationCommandResponse(
            activation=to_activation_response(activation), created=created
        )

    @router.post(
        "/{iteration_id}/activate",
        response_model=SymbolModelActivationCommandResponse,
        operation_id="activateSymbolModel",
        responses=errors,
    )
    def activate(
        game_id: UUID,
        iteration_id: UUID,
        payload: SymbolModelActivationCommand,
        service: Annotated[SymbolModelRegistryService, registry_dependency],
    ) -> SymbolModelActivationCommandResponse:
        return execute_activation(
            game_id=game_id,
            iteration_id=iteration_id,
            payload=payload,
            action=SymbolModelActivationAction.ACTIVATE,
            service=service,
        )

    @router.post(
        "/{iteration_id}/rollback",
        response_model=SymbolModelActivationCommandResponse,
        operation_id="rollbackSymbolModel",
        responses=errors,
    )
    def rollback(
        game_id: UUID,
        iteration_id: UUID,
        payload: SymbolModelActivationCommand,
        service: Annotated[SymbolModelRegistryService, registry_dependency],
    ) -> SymbolModelActivationCommandResponse:
        return execute_activation(
            game_id=game_id,
            iteration_id=iteration_id,
            payload=payload,
            action=SymbolModelActivationAction.ROLLBACK,
            service=service,
        )

    @router.get(
        "/registry/activations",
        response_model=list[SymbolModelActivationResponse],
        operation_id="listSymbolModelActivations",
        responses=errors,
    )
    def list_activations(
        game_id: UUID,
        service: Annotated[SymbolModelRegistryService, registry_dependency],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[SymbolModelActivationResponse]:
        return [
            to_activation_response(value) for value in service.list(game_id=game_id, limit=limit)
        ]

    return router


__all__ = ["create_symbol_model_iteration_router"]
