"""Local management HTTP boundary; security middleware guards all writes."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.api.management_mutations import install_management_mutation_routes
from game_predictor_api.application.management import ManagementService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.management import (
    ManagementAssignmentCommand,
    ManagementMachineCommand,
    ManagementMachineResponse,
    ManagementPointCommand,
    ManagementPointResponse,
    ManagementSnapshotResponse,
)


def create_management_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/management",
        tags=["management"],
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    # Commit/rollback finishes before the response is sent, including commit errors.
    dependency = Depends(service_dependency, scope="function")

    @router.get("", response_model=ManagementSnapshotResponse, operation_id="getManagementSnapshot")
    def snapshot(service: Annotated[ManagementService, dependency]) -> ManagementSnapshotResponse:
        return service.snapshot()

    @router.post(
        "/points", response_model=ManagementPointResponse, operation_id="createManagementPoint"
    )
    def create_point(
        payload: ManagementPointCommand, service: Annotated[ManagementService, dependency]
    ) -> ManagementPointResponse:
        return service.point(None, payload)

    @router.put(
        "/points/{point_id}",
        response_model=ManagementPointResponse,
        operation_id="updateManagementPoint",
    )
    def update_point(
        point_id: UUID,
        payload: ManagementPointCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementPointResponse:
        return service.point(point_id, payload)

    @router.post(
        "/points/{point_id}/machines",
        response_model=ManagementMachineResponse,
        operation_id="createManagementMachine",
    )
    def create_machine(
        point_id: UUID,
        payload: ManagementMachineCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMachineResponse:
        return service.machine(point_id, None, payload)

    @router.put(
        "/points/{point_id}/machines/{machine_id}",
        response_model=ManagementMachineResponse,
        operation_id="updateManagementMachine",
    )
    def update_machine(
        point_id: UUID,
        machine_id: UUID,
        payload: ManagementMachineCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMachineResponse:
        return service.machine(point_id, machine_id, payload)

    @router.put(
        "/machines/{machine_id}/assignments",
        response_model=ManagementMachineResponse,
        operation_id="updateManagementAssignments",
    )
    def assignments(
        machine_id: UUID,
        payload: ManagementAssignmentCommand,
        service: Annotated[ManagementService, dependency],
    ) -> ManagementMachineResponse:
        return service.assignments(machine_id, payload)

    install_management_mutation_routes(router, service_dependency)
    return router
