"""Own-game geometry recording commands and coarse qualification views."""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from game_predictor_api.application.source_recording_groups import SourceRecordingGroupsService
from game_predictor_api.domain.source_recording_groups import RecordingError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.source_recording_groups import (
    SourceRecordingCommandRequest,
    SourceRecordingCommandResponse,
    SourceRecordingGroupListResponse,
)
from game_predictor_api.security.local_admin import ADMIN_ACTOR


def create_source_recording_groups_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/games/{game_id}/source-recording-groups",
        tags=["source-recording-groups"],
    )
    dependency = Depends(service_dependency)
    errors: dict[int | str, dict[str, Any]] = {
        code: {"model": ErrorResponse} for code in (403, 404, 409, 422, 503)
    }

    @router.get(
        "",
        operation_id="listSourceRecordingGroups",
        response_model=SourceRecordingGroupListResponse,
        responses=errors,
    )
    def list_groups(
        game_id: UUID,
        service: Annotated[SourceRecordingGroupsService, dependency],
        family_id: Annotated[UUID | None, Query(alias="familyId")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        after: UUID | None = None,
        group_id: Annotated[UUID | None, Query(alias="groupId")] = None,
    ) -> SourceRecordingGroupListResponse:
        return SourceRecordingGroupListResponse.model_validate(
            service.list_groups(game_id, family_id, limit, after, group_id)
        )

    @router.post(
        "/commands",
        operation_id="commandSourceRecordingGroups",
        response_model=SourceRecordingCommandResponse,
        responses=errors,
    )
    def command_groups(
        game_id: UUID,
        command: SourceRecordingCommandRequest,
        request: Request,
        service: Annotated[SourceRecordingGroupsService, dependency],
    ) -> SourceRecordingCommandResponse | JSONResponse:
        actor = getattr(request.state, "local_admin_actor", None)
        if actor != ADMIN_ACTOR:
            raise RecordingError(
                "RECORDING_ACTOR_REQUIRED", "Trusted local administrative context is required.", 403
            )
        result = service.execute(game_id, command, actor)
        receipt = SourceRecordingCommandResponse.model_validate(result)
        if receipt.status_code != 200:
            # Return after dependency commit; a typed refusal may retain trusted alias evidence.
            return JSONResponse(
                status_code=receipt.status_code,
                content={
                    "code": receipt.reason_code,
                    "message": "Recording qualification is blocked.",
                    "details": {"receipt": receipt.model_dump(mode="json", by_alias=True)},
                },
            )
        return receipt

    return router
