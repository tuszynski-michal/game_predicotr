"""HTTP boundary for administrative rules versions."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from game_predictor_api.application.rules import RulesService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.rules import (
    PaylineCreate,
    PaylineResponse,
    PaylineUpdate,
    RulesVersionCreate,
    RulesVersionResponse,
    RulesVersionUpdate,
)

RulesServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Rules state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_rules_router(service_dependency: RulesServiceDependency) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["rules"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/games/{game_id}/rules-versions",
        response_model=list[RulesVersionResponse],
        operation_id="listRulesVersions",
        summary="List game rules versions",
        responses=ERROR_RESPONSES,
    )
    def list_rules_versions(
        game_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> list[RulesVersionResponse]:
        return [
            RulesVersionResponse.model_validate(item)
            for item in service.list_rules_versions(game_id)
        ]

    @router.post(
        "/games/{game_id}/rules-versions",
        response_model=RulesVersionResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createRulesVersion",
        summary="Create draft rules version",
        responses=ERROR_RESPONSES,
    )
    def create_rules_version(
        game_id: UUID,
        payload: RulesVersionCreate,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionResponse:
        return RulesVersionResponse.model_validate(
            service.create_rules_version(
                game_id,
                rows=payload.rows,
                columns=payload.columns,
                spin_cost=payload.spin_cost,
            )
        )

    @router.get(
        "/rules-versions/{rules_version_id}",
        response_model=RulesVersionResponse,
        operation_id="getRulesVersion",
        summary="Get rules version",
        responses=ERROR_RESPONSES,
    )
    def get_rules_version(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionResponse:
        return RulesVersionResponse.model_validate(service.get_rules_version(rules_version_id))

    @router.patch(
        "/rules-versions/{rules_version_id}",
        response_model=RulesVersionResponse,
        operation_id="updateRulesVersion",
        summary="Update draft rules version dimensions",
        responses=ERROR_RESPONSES,
    )
    def update_rules_version(
        rules_version_id: UUID,
        payload: RulesVersionUpdate,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionResponse:
        return RulesVersionResponse.model_validate(
            service.update_rules_version(
                rules_version_id,
                rows=payload.rows,
                columns=payload.columns,
                spin_cost=payload.spin_cost,
            )
        )

    @router.get(
        "/rules-versions/{rules_version_id}/paylines",
        response_model=list[PaylineResponse],
        operation_id="listPaylines",
        summary="List rules-version paylines",
        responses=ERROR_RESPONSES,
    )
    def list_paylines(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> list[PaylineResponse]:
        return [
            PaylineResponse.model_validate(payline)
            for payline in service.list_paylines(rules_version_id)
        ]

    @router.post(
        "/rules-versions/{rules_version_id}/paylines",
        response_model=PaylineResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createPayline",
        summary="Create draft payline",
        responses=ERROR_RESPONSES,
    )
    def create_payline(
        rules_version_id: UUID,
        payload: PaylineCreate,
        service: Annotated[RulesService, service_parameter],
    ) -> PaylineResponse:
        return PaylineResponse.model_validate(
            service.create_payline(
                rules_version_id,
                code=payload.code,
                name=payload.name,
                row_path=payload.row_path,
                display_order=payload.display_order,
                is_active=payload.is_active,
            )
        )

    @router.get(
        "/rules-versions/{rules_version_id}/paylines/{payline_id}",
        response_model=PaylineResponse,
        operation_id="getPayline",
        summary="Get payline",
        responses=ERROR_RESPONSES,
    )
    def get_payline(
        rules_version_id: UUID,
        payline_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> PaylineResponse:
        return PaylineResponse.model_validate(service.get_payline(rules_version_id, payline_id))

    @router.patch(
        "/rules-versions/{rules_version_id}/paylines/{payline_id}",
        response_model=PaylineResponse,
        operation_id="updatePayline",
        summary="Update draft payline",
        responses=ERROR_RESPONSES,
    )
    def update_payline(
        rules_version_id: UUID,
        payline_id: UUID,
        payload: PaylineUpdate,
        service: Annotated[RulesService, service_parameter],
    ) -> PaylineResponse:
        return PaylineResponse.model_validate(
            service.update_payline(
                rules_version_id,
                payline_id,
                name=payload.name,
                row_path=payload.row_path,
                display_order=payload.display_order,
                is_active=payload.is_active,
            )
        )

    @router.delete(
        "/rules-versions/{rules_version_id}/paylines/{payline_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archivePayline",
        summary="Archive draft payline",
        responses=ERROR_RESPONSES,
    )
    def archive_payline(
        rules_version_id: UUID,
        payline_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> Response:
        service.archive_payline(rules_version_id, payline_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
