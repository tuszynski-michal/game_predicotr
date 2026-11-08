"""Extend geometry measurements with an actual, source-only blind labelling workflow."""

from collections.abc import Callable
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from game_predictor_api.application.grid_cell_content import ContentRepository
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_cell_content import (
    ContentBlindWrite,
    ContentReadinessResponse,
    ContentReferenceResponse,
    ContentSamplingPreview,
    ContentSamplingResponse,
    ContentSessionAdvance,
    ContentSessionCommandResponse,
    ContentSessionCreate,
    ContentSessionList,
    ContentSessionResponse,
    ContentWriteCommand,
    ContentWriteResponse,
)


def content_error_response(error: ContentError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "details": {} if error.report is None else {"report": error.report},
        },
    )


def create_grid_cell_content_router(dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/admin/games/{game_id}/grid-quality-measurements",
        tags=["grid-quality-measurements"],
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    parameter = Depends(dependency)

    def actor(request: Request) -> str:
        if getattr(request.state, "local_admin_actor", None) != "local-owner":
            raise HTTPException(403, "A validated local human actor is required.")
        return "local-owner"

    def repo(service: OperationalImageReviewService) -> ContentRepository:
        if service.grid_cell_content is None:
            raise HTTPException(503, "Independent content annotations are unavailable.")
        return service.grid_cell_content.repository

    def invoke(action: Callable[[], Any]) -> Any:
        # Let the request dependency roll back before the application's typed
        # exception handler creates the documented ErrorResponse.
        return action()

    @router.get(
        "/content-references/{source_id}/{position_index}",
        operation_id="getGridCellContentReference",
        response_model=ContentReferenceResponse,
    )
    def read(
        game_id: UUID,
        source_id: UUID,
        position_index: int,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        return invoke(lambda: repo(service).get(game_id, source_id, position_index))

    @router.post(
        "/content-references",
        operation_id="writeGridCellContentReference",
        response_model=ContentWriteResponse,
    )
    def write(
        request: Request,
        game_id: UUID,
        command: ContentWriteCommand,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        human = actor(request)
        return invoke(lambda: repo(service).write(game_id, command, human))

    @router.get(
        "/content-sessions",
        operation_id="listGridContentSessions",
        response_model=ContentSessionList,
    )
    def sessions(
        game_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
        limit: int = Query(default=20, ge=1, le=50),
    ) -> Any:
        return invoke(lambda: repo(service).list_sessions(game_id, limit))

    @router.post(
        "/content-sessions",
        operation_id="createGridContentSession",
        response_model=ContentSessionCommandResponse,
    )
    def create(
        request: Request,
        game_id: UUID,
        command: ContentSessionCreate,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        human = actor(request)
        return invoke(lambda: repo(service).create_session(game_id, command, human))

    @router.get(
        "/content-sessions/{session_id}",
        operation_id="getGridContentSession",
        response_model=ContentSessionResponse,
    )
    def session(
        game_id: UUID,
        session_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        return invoke(lambda: repo(service).get_session(game_id, session_id))

    @router.post(
        "/content-sessions/{session_id}/observations",
        operation_id="writeGridBlindContentObservation",
        response_model=ContentSessionCommandResponse,
    )
    def observe(
        request: Request,
        game_id: UUID,
        session_id: UUID,
        command: ContentBlindWrite,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        human = actor(request)
        return invoke(lambda: repo(service).blind_write(game_id, session_id, command, human))

    @router.post(
        "/content-sessions/{session_id}/advance",
        operation_id="advanceGridContentSession",
        response_model=ContentSessionCommandResponse,
    )
    def advance(
        request: Request,
        game_id: UUID,
        session_id: UUID,
        command: ContentSessionAdvance,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        human = actor(request)
        return invoke(lambda: repo(service).advance(game_id, session_id, command, human))

    @router.get(
        "/content-sessions/{session_id}/sources/{source_id}/asset",
        operation_id="getGridContentSessionSource",
        response_class=FileResponse,
    )
    def asset(
        game_id: UUID,
        session_id: UUID,
        source_id: UUID,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> FileResponse:
        path = invoke(lambda: repo(service).source_asset(game_id, session_id, source_id))
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.get(
        "/content-readiness",
        operation_id="getGridContentReadiness",
        response_model=ContentReadinessResponse,
    )
    def readiness(
        game_id: UUID,
        cohort_id: Annotated[UUID, Query(alias="cohortId")],
        manifest_sha256: Annotated[str, Query(alias="manifestSha256", pattern=r"^[0-9a-f]{64}$")],
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            invoke(lambda: repo(service).readiness(game_id, cohort_id, manifest_sha256)),
        )

    @router.post(
        "/content-sampling-preview",
        operation_id="previewGridContentSampling",
        response_model=ContentSamplingResponse,
    )
    def sampling(
        request: Request,
        game_id: UUID,
        command: ContentSamplingPreview,
        service: Annotated[OperationalImageReviewService, parameter],
    ) -> Any:
        actor(request)
        return invoke(lambda: repo(service).sampling_preview(game_id, command))

    return router
