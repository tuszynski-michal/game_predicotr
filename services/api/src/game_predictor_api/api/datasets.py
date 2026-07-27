"""HTTP boundary for bounded mock dataset staging."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.datasets import (
    DatasetLayoutPageResponse,
    DatasetValidationReportResponse,
    DatasetVersionResponse,
    MockDatasetCreate,
)

DatasetServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Dataset state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_datasets_router(
    service_dependency: DatasetServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["datasets"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/games/{game_id}/dataset-versions",
        response_model=list[DatasetVersionResponse],
        operation_id="listDatasetVersions",
        summary="List game dataset versions",
        responses=ERROR_RESPONSES,
    )
    def list_dataset_versions(
        game_id: UUID,
        service: Annotated[DatasetService, service_parameter],
    ) -> list[DatasetVersionResponse]:
        return [
            DatasetVersionResponse.model_validate(item)
            for item in service.list_dataset_versions(game_id)
        ]

    @router.post(
        "/games/{game_id}/dataset-versions/mock",
        response_model=DatasetVersionResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="generateMockDataset",
        summary="Generate a deterministic 1000-layout staging dataset",
        responses=ERROR_RESPONSES,
    )
    def generate_mock_dataset(
        game_id: UUID,
        payload: MockDatasetCreate,
        service: Annotated[DatasetService, service_parameter],
    ) -> DatasetVersionResponse:
        return DatasetVersionResponse.model_validate(
            service.generate_mock_dataset(
                game_id,
                rules_version_id=payload.rules_version_id,
                seed=payload.seed,
            )
        )

    @router.get(
        "/dataset-versions/{dataset_version_id}",
        response_model=DatasetVersionResponse,
        operation_id="getDatasetVersion",
        summary="Get a dataset version",
        responses=ERROR_RESPONSES,
    )
    def get_dataset_version(
        dataset_version_id: UUID,
        service: Annotated[DatasetService, service_parameter],
    ) -> DatasetVersionResponse:
        return DatasetVersionResponse.model_validate(
            service.get_dataset_version(dataset_version_id)
        )

    @router.get(
        "/dataset-versions/{dataset_version_id}/layouts",
        response_model=DatasetLayoutPageResponse,
        operation_id="listDatasetLayouts",
        summary="List a stable page of dataset layouts",
        responses=ERROR_RESPONSES,
    )
    def list_dataset_layouts(
        dataset_version_id: UUID,
        service: Annotated[DatasetService, service_parameter],
        after_sequence_number: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> DatasetLayoutPageResponse:
        return DatasetLayoutPageResponse.model_validate(
            service.list_layouts(
                dataset_version_id,
                after_sequence_number=after_sequence_number,
                limit=limit,
            )
        )

    @router.get(
        "/dataset-versions/{dataset_version_id}/validation-report",
        response_model=DatasetValidationReportResponse,
        operation_id="getDatasetValidationReport",
        summary="Validate a bounded staging dataset",
        responses=ERROR_RESPONSES,
    )
    def get_dataset_validation_report(
        dataset_version_id: UUID,
        service: Annotated[DatasetService, service_parameter],
    ) -> DatasetValidationReportResponse:
        return DatasetValidationReportResponse.model_validate(
            service.get_validation_report(dataset_version_id)
        )

    @router.post(
        "/dataset-versions/{dataset_version_id}/publish",
        response_model=DatasetVersionResponse,
        operation_id="publishDatasetVersion",
        summary="Validate and publish an immutable dataset version",
        responses=ERROR_RESPONSES,
    )
    def publish_dataset_version(
        dataset_version_id: UUID,
        service: Annotated[DatasetService, service_parameter],
    ) -> DatasetVersionResponse:
        return DatasetVersionResponse.model_validate(
            service.publish_dataset_version(dataset_version_id)
        )

    @router.delete(
        "/dataset-versions/{dataset_version_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="archiveDatasetVersion",
        summary="Archive a published dataset version",
        responses=ERROR_RESPONSES,
    )
    def archive_dataset_version(
        dataset_version_id: UUID,
        service: Annotated[DatasetService, service_parameter],
    ) -> Response:
        service.archive_dataset_version(dataset_version_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
