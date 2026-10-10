"""Identical structural mutation contracts under local and capability prefixes."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.application.management import ManagementService
from game_predictor_api.domain.management import (
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementDeleteResponse,
    ManagementMutationPreviewResponse,
    ManagementUpdatePreviewCommand,
)


def install_management_mutation_routes(
    router: APIRouter, service_dependency: Callable[..., object], *, public: bool = False
) -> None:
    dependency = Depends(service_dependency, scope="function")
    name = "PublicManagement" if public else "Management"

    @router.post(
        "/points/{point_id}/delete-preview",
        response_model=ManagementMutationPreviewResponse,
        operation_id=f"preview{name}PointDeletion",
    )
    def preview_point(
        point_id: UUID,
        payload: ManagementDeletePreviewCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMutationPreviewResponse:
        return service.delete_preview(point_id, None, payload)

    @router.post(
        "/points/{point_id}/delete",
        response_model=ManagementDeleteResponse,
        operation_id=f"delete{name}Point",
    )
    def delete_point(
        point_id: UUID,
        payload: ManagementDeleteCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementDeleteResponse:
        return service.delete_scope(point_id, None, payload)

    @router.post(
        "/points/{point_id}/machines/{machine_id}/delete-preview",
        response_model=ManagementMutationPreviewResponse,
        operation_id=f"preview{name}MachineDeletion",
    )
    def preview_machine(
        point_id: UUID,
        machine_id: UUID,
        payload: ManagementDeletePreviewCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMutationPreviewResponse:
        return service.delete_preview(point_id, machine_id, payload)

    @router.post(
        "/points/{point_id}/machines/{machine_id}/delete",
        response_model=ManagementDeleteResponse,
        operation_id=f"delete{name}Machine",
    )
    def delete_machine(
        point_id: UUID,
        machine_id: UUID,
        payload: ManagementDeleteCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementDeleteResponse:
        return service.delete_scope(point_id, machine_id, payload)

    @router.post(
        "/machines/{machine_id}/update-preview",
        response_model=ManagementMutationPreviewResponse,
        operation_id=f"preview{name}MachineUpdate",
    )
    def preview_update(
        machine_id: UUID,
        payload: ManagementUpdatePreviewCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMutationPreviewResponse:
        return service.update_preview(machine_id, payload.command)
