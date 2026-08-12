"""HTTP boundary for local worker-lane health."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from game_predictor_api.application.worker_lanes import WorkerLaneStatusService
from game_predictor_api.schemas.worker_lanes import WorkerLaneStatusResponse

WorkerLaneStatusServiceDependency = Callable[..., object]


def create_worker_lanes_router(
    service_dependency: WorkerLaneStatusServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/worker-lanes", tags=["worker-lanes"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "",
        response_model=list[WorkerLaneStatusResponse],
        operation_id="listWorkerLanes",
        summary="List health and resource budgets for local worker lanes",
    )
    def list_worker_lanes(
        service: Annotated[WorkerLaneStatusService, service_parameter],
    ) -> list[WorkerLaneStatusResponse]:
        return [
            WorkerLaneStatusResponse.from_domain(item)
            for item in service.list_statuses()
        ]

    return router
