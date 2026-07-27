"""HTTP boundary for bounded mock dataset staging."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.datasets import (
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

    return router
