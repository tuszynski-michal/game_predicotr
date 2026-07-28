"""HTTP boundary for normalized layout import reports and row preview."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportService,
)
from game_predictor_api.domain.layout_import_reports import (
    LayoutImportRowStatus,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.datasets import DatasetVersionResponse
from game_predictor_api.schemas.layout_import_reports import (
    LayoutImportIntegrityReportResponse,
    LayoutImportNormalizedRowPageResponse,
    LayoutImportStagingRejectionResponse,
)

LayoutImportReportServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {
        "model": ErrorResponse,
        "description": "Layout import validation not found",
    },
    409: {
        "model": ErrorResponse,
        "description": "Layout import validation state conflict",
    },
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_layout_import_reports_router(
    service_dependency: LayoutImportReportServiceDependency,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/layout-import-validations",
        tags=["layout-imports"],
    )
    service_parameter = Depends(service_dependency)

    @router.get(
        "/{validation_job_id}/integrity-report",
        response_model=LayoutImportIntegrityReportResponse,
        operation_id="getLayoutImportIntegrityReport",
        summary="Get exact integrity aggregates and bounded diagnostics",
        responses=ERROR_RESPONSES,
    )
    def get_layout_import_integrity_report(
        validation_job_id: UUID,
        service: Annotated[
            LayoutImportReportService,
            service_parameter,
        ],
    ) -> LayoutImportIntegrityReportResponse:
        return LayoutImportIntegrityReportResponse.model_validate(
            service.get_integrity_report(validation_job_id)
        )

    @router.get(
        "/{validation_job_id}/rows",
        response_model=LayoutImportNormalizedRowPageResponse,
        operation_id="listLayoutImportNormalizedRows",
        summary="List a stable page of normalized import rows",
        responses=ERROR_RESPONSES,
    )
    def list_layout_import_normalized_rows(
        validation_job_id: UUID,
        service: Annotated[
            LayoutImportReportService,
            service_parameter,
        ],
        after_line_number: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        row_status: Annotated[
            LayoutImportRowStatus,
            Query(alias="status"),
        ] = LayoutImportRowStatus.ALL,
        error_code: Annotated[
            str | None,
            Query(min_length=1, max_length=100),
        ] = None,
    ) -> LayoutImportNormalizedRowPageResponse:
        return LayoutImportNormalizedRowPageResponse.model_validate(
            service.list_normalized_rows(
                validation_job_id,
                after_line_number=after_line_number,
                limit=limit,
                row_status=row_status,
                error_code=error_code,
            )
        )

    @router.delete(
        "/{validation_job_id}/staging",
        response_model=LayoutImportStagingRejectionResponse,
        operation_id="rejectLayoutImportStaging",
        summary="Reject and remove unpublished import staging",
        responses=ERROR_RESPONSES,
    )
    def reject_layout_import_staging(
        validation_job_id: UUID,
        service: Annotated[
            LayoutImportReportService,
            service_parameter,
        ],
    ) -> LayoutImportStagingRejectionResponse:
        return LayoutImportStagingRejectionResponse.model_validate(
            service.reject_staging(validation_job_id)
        )

    @router.post(
        "/{validation_job_id}/publish",
        response_model=DatasetVersionResponse,
        operation_id="publishLayoutImportDataset",
        summary="Atomically publish a validated import as an immutable dataset",
        responses=ERROR_RESPONSES,
    )
    def publish_layout_import_dataset(
        validation_job_id: UUID,
        service: Annotated[
            LayoutImportReportService,
            service_parameter,
        ],
    ) -> DatasetVersionResponse:
        return DatasetVersionResponse.model_validate(service.publish_dataset(validation_job_id))

    return router
