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
    PayoutRuleCreate,
    PayoutRuleResponse,
    PayoutRuleUpdate,
    RulesPublicationReadinessResponse,
    RulesVersionCreate,
    RulesVersionResponse,
    RulesVersionSymbolResponse,
    RulesVersionSymbolUpdate,
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

    @router.post(
        "/rules-versions/{rules_version_id}/draft",
        response_model=RulesVersionResponse,
        operation_id="createRulesDraftFromPublished",
        summary="Open the one current draft copied from a published version",
        responses=ERROR_RESPONSES,
    )
    def create_rules_draft_from_published(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionResponse:
        return RulesVersionResponse.model_validate(
            service.create_draft_from_published(rules_version_id)
        )

    @router.get(
        "/rules-versions/{rules_version_id}/publication-readiness",
        response_model=RulesPublicationReadinessResponse,
        operation_id="getRulesPublicationReadiness",
        summary="Validate a rules version before publication",
        responses=ERROR_RESPONSES,
    )
    def get_rules_publication_readiness(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesPublicationReadinessResponse:
        return RulesPublicationReadinessResponse.model_validate(
            service.get_publication_readiness(rules_version_id)
        )

    @router.post(
        "/rules-versions/{rules_version_id}/publish",
        response_model=RulesVersionResponse,
        operation_id="publishRulesVersion",
        summary="Publish a ready draft rules version",
        responses=ERROR_RESPONSES,
    )
    def publish_rules_version(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionResponse:
        return RulesVersionResponse.model_validate(service.publish_rules_version(rules_version_id))

    @router.delete(
        "/rules-versions/{rules_version_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archiveRulesVersion",
        summary="Archive a published rules version",
        responses=ERROR_RESPONSES,
    )
    def archive_rules_version(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> Response:
        service.archive_rules_version(rules_version_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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

    @router.get(
        "/rules-versions/{rules_version_id}/symbols",
        response_model=list[RulesVersionSymbolResponse],
        operation_id="listRulesVersionSymbols",
        summary="List configured rules-version symbols",
        responses=ERROR_RESPONSES,
    )
    def list_rules_version_symbols(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> list[RulesVersionSymbolResponse]:
        return [
            RulesVersionSymbolResponse.model_validate(item)
            for item in service.list_rules_version_symbols(rules_version_id)
        ]

    @router.patch(
        "/rules-versions/{rules_version_id}/symbols/{symbol_id}",
        response_model=RulesVersionSymbolResponse,
        operation_id="updateRulesVersionSymbol",
        summary="Configure a draft rules-version symbol",
        responses=ERROR_RESPONSES,
    )
    def update_rules_version_symbol(
        rules_version_id: UUID,
        symbol_id: UUID,
        payload: RulesVersionSymbolUpdate,
        service: Annotated[RulesService, service_parameter],
    ) -> RulesVersionSymbolResponse:
        return RulesVersionSymbolResponse.model_validate(
            service.update_rules_version_symbol(
                rules_version_id,
                symbol_id,
                minimum_match_length=payload.minimum_match_length,
                is_active=payload.is_active,
            )
        )

    @router.get(
        "/rules-versions/{rules_version_id}/payout-rules",
        response_model=list[PayoutRuleResponse],
        operation_id="listPayoutRules",
        summary="List rules-version payout rules",
        responses=ERROR_RESPONSES,
    )
    def list_payout_rules(
        rules_version_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> list[PayoutRuleResponse]:
        return [
            PayoutRuleResponse.model_validate(item)
            for item in service.list_payout_rules(rules_version_id)
        ]

    @router.post(
        "/rules-versions/{rules_version_id}/payout-rules",
        response_model=PayoutRuleResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createPayoutRule",
        summary="Create a draft payout rule",
        responses=ERROR_RESPONSES,
    )
    def create_payout_rule(
        rules_version_id: UUID,
        payload: PayoutRuleCreate,
        service: Annotated[RulesService, service_parameter],
    ) -> PayoutRuleResponse:
        return PayoutRuleResponse.model_validate(
            service.create_payout_rule(
                rules_version_id,
                symbol_id=payload.symbol_id,
                match_length=payload.match_length,
                payout_credits=payload.payout_credits,
                is_active=payload.is_active,
            )
        )

    @router.get(
        "/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
        response_model=PayoutRuleResponse,
        operation_id="getPayoutRule",
        summary="Get a payout rule",
        responses=ERROR_RESPONSES,
    )
    def get_payout_rule(
        rules_version_id: UUID,
        payout_rule_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> PayoutRuleResponse:
        return PayoutRuleResponse.model_validate(
            service.get_payout_rule(rules_version_id, payout_rule_id)
        )

    @router.patch(
        "/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
        response_model=PayoutRuleResponse,
        operation_id="updatePayoutRule",
        summary="Update a draft payout rule",
        responses=ERROR_RESPONSES,
    )
    def update_payout_rule(
        rules_version_id: UUID,
        payout_rule_id: UUID,
        payload: PayoutRuleUpdate,
        service: Annotated[RulesService, service_parameter],
    ) -> PayoutRuleResponse:
        return PayoutRuleResponse.model_validate(
            service.update_payout_rule(
                rules_version_id,
                payout_rule_id,
                payout_credits=payload.payout_credits,
                is_active=payload.is_active,
            )
        )

    @router.delete(
        "/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archivePayoutRule",
        summary="Archive a draft payout rule",
        responses=ERROR_RESPONSES,
    )
    def archive_payout_rule(
        rules_version_id: UUID,
        payout_rule_id: UUID,
        service: Annotated[RulesService, service_parameter],
    ) -> Response:
        service.archive_payout_rule(rules_version_id, payout_rule_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
