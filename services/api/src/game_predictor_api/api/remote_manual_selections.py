"""Local-only host setup routes for remote manual image selection."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.remote_manual_selections import (
    RemoteManualSelectionBaseCapabilityResponse,
)


def create_remote_manual_selections_admin_router(
    service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/remote-manual-selections")
    service_parameter = Depends(service_dependency)

    @router.post(
        "/base-capabilities",
        response_model=RemoteManualSelectionBaseCapabilityResponse,
        operation_id="selectRemoteManualSelectionHostBase",
        summary="Select a local host base for remote manual image selection",
        tags=["remote-manual-selections"],
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def select_host_base(
        service: Annotated[RemoteManualSelectionHostService, service_parameter],
    ) -> RemoteManualSelectionBaseCapabilityResponse:
        selected = service.select_base()
        return (
            RemoteManualSelectionBaseCapabilityResponse.cancelled()
            if selected is None
            else RemoteManualSelectionBaseCapabilityResponse.selected(selected)
        )

    return router


__all__ = ["create_remote_manual_selections_admin_router"]
