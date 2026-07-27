"""HTTP boundary for durable administrative jobs."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.jobs import JobCreateRequest, JobResponse

JobServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Job or game not found"},
    409: {"model": ErrorResponse, "description": "Job lifecycle conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_jobs_router(service_dependency: JobServiceDependency) -> APIRouter:
    router = APIRouter(prefix="/admin/jobs", tags=["jobs"])
    service_parameter = Depends(service_dependency)

    @router.post(
        "",
        response_model=JobResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createJob",
        summary="Persist a typed job for later worker execution",
        responses=ERROR_RESPONSES,
    )
    def create_job(
        payload: JobCreateRequest,
        service: Annotated[JobService, service_parameter],
    ) -> JobResponse:
        job = service.create_job(
            JobType(payload.job_type),
            game_id=payload.game_id,
            input_payload=dict(payload.input_payload.model_dump(mode="json")),
        )
        return JobResponse.from_domain(job)

    @router.get(
        "",
        response_model=list[JobResponse],
        operation_id="listJobs",
        summary="List a bounded set of newest jobs",
        responses=ERROR_RESPONSES,
    )
    def list_jobs(
        service: Annotated[JobService, service_parameter],
        job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
        job_type: JobType | None = None,
        game_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[JobResponse]:
        return [
            JobResponse.from_domain(job)
            for job in service.list_jobs(
                status=job_status,
                job_type=job_type,
                game_id=game_id,
                limit=limit,
            )
        ]

    @router.get(
        "/{job_id}",
        response_model=JobResponse,
        operation_id="getJob",
        summary="Get job status, progress and error",
        responses=ERROR_RESPONSES,
    )
    def get_job(
        job_id: UUID,
        service: Annotated[JobService, service_parameter],
    ) -> JobResponse:
        return JobResponse.from_domain(service.get_job(job_id))

    @router.post(
        "/{job_id}/cancel",
        response_model=JobResponse,
        operation_id="cancelJob",
        summary="Request cancellation at a safe worker checkpoint",
        responses=ERROR_RESPONSES,
    )
    def cancel_job(
        job_id: UUID,
        service: Annotated[JobService, service_parameter],
    ) -> JobResponse:
        return JobResponse.from_domain(service.cancel_job(job_id))

    @router.post(
        "/{job_id}/retry",
        response_model=JobResponse,
        operation_id="retryJob",
        summary="Requeue the same failed or review-paused job",
        responses=ERROR_RESPONSES,
    )
    def retry_job(
        job_id: UUID,
        service: Annotated[JobService, service_parameter],
    ) -> JobResponse:
        return JobResponse.from_domain(service.retry_job(job_id))

    return router
