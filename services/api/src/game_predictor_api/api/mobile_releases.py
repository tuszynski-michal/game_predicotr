"""HTTP boundary for immutable mobile release selections."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from game_predictor_api.application.mobile_releases import (
    MobileReleaseService,
)
from game_predictor_api.application.release_artifacts import (
    resolve_mobile_release_apk,
)
from game_predictor_api.domain.mobile_releases import MobileReleaseGameInput
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.mobile_releases import (
    MobileReleaseBuildResponse,
    MobileReleaseCreate,
    MobileReleaseResponse,
    to_mobile_release_response,
)

MobileReleaseServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Release source not found"},
    409: {"model": ErrorResponse, "description": "Release state conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_mobile_releases_router(
    service_dependency: MobileReleaseServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/mobile-releases",
        tags=["mobile-releases"],
    )
    service_parameter = Depends(service_dependency)

    @router.get(
        "",
        response_model=list[MobileReleaseResponse],
        operation_id="listMobileReleases",
        summary="List immutable mobile releases",
        responses=ERROR_RESPONSES,
    )
    def list_mobile_releases(
        service: Annotated[MobileReleaseService, service_parameter],
    ) -> list[MobileReleaseResponse]:
        return [to_mobile_release_response(item) for item in service.list_mobile_releases()]

    @router.post(
        "",
        response_model=MobileReleaseResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="createMobileRelease",
        summary="Create an immutable draft mobile release",
        responses=ERROR_RESPONSES,
    )
    def create_mobile_release(
        payload: MobileReleaseCreate,
        service: Annotated[MobileReleaseService, service_parameter],
    ) -> MobileReleaseResponse:
        return to_mobile_release_response(
            service.create_mobile_release(
                version=payload.version,
                games=tuple(
                    MobileReleaseGameInput(
                        game_id=game.game_id,
                        dataset_version_id=game.dataset_version_id,
                        rules_version_id=game.rules_version_id,
                    )
                    for game in payload.games
                ),
            )
        )

    @router.get(
        "/{mobile_release_id}",
        response_model=MobileReleaseResponse,
        operation_id="getMobileRelease",
        summary="Get an immutable mobile release",
        responses=ERROR_RESPONSES,
    )
    def get_mobile_release(
        mobile_release_id: UUID,
        service: Annotated[MobileReleaseService, service_parameter],
    ) -> MobileReleaseResponse:
        return to_mobile_release_response(service.get_mobile_release(mobile_release_id))

    @router.get(
        "/{mobile_release_id}/apk",
        response_class=FileResponse,
        operation_id="downloadMobileReleaseApk",
        summary="Download the verified APK of a ready mobile release",
        responses={
            **ERROR_RESPONSES,
            200: {
                "content": {
                    "application/vnd.android.package-archive": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
                "description": "Verified immutable Android package",
            },
        },
    )
    def download_mobile_release_apk(
        mobile_release_id: UUID,
        service: Annotated[MobileReleaseService, service_parameter],
    ) -> FileResponse:
        artifact = resolve_mobile_release_apk(
            service.get_mobile_release(mobile_release_id),
            artifact_root,
        )
        return FileResponse(
            artifact.path,
            filename=artifact.download_name,
            media_type="application/vnd.android.package-archive",
        )

    @router.post(
        "/{mobile_release_id}/build",
        response_model=MobileReleaseBuildResponse,
        status_code=status.HTTP_201_CREATED,
        operation_id="buildMobileRelease",
        summary="Start the one controlled release build workflow",
        responses=ERROR_RESPONSES,
    )
    def build_mobile_release(
        mobile_release_id: UUID,
        service: Annotated[MobileReleaseService, service_parameter],
    ) -> MobileReleaseBuildResponse:
        return MobileReleaseBuildResponse.from_job(
            service.start_mobile_release_build(mobile_release_id)
        )

    return router
