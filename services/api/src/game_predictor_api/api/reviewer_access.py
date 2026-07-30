"""HTTP endpoints for local reviewer session creation and unlock."""

from uuid import UUID

from fastapi import APIRouter

from game_predictor_api.application.reviewer_access import ReviewerAccessService
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.reviewer_access import (
    ReviewerSessionCreate,
    ReviewerSessionCreatedResponse,
    ReviewerSessionScopeResponse,
    ReviewerSessionUnlock,
)


def create_reviewer_access_router(service: ReviewerAccessService) -> APIRouter:
    router = APIRouter(tags=["reviewer-access"])

    @router.post(
        "/admin/reviewer-sessions",
        response_model=ReviewerSessionCreatedResponse,
        status_code=201,
        operation_id="createReviewerSession",
        summary="Create one process-local game and import scoped reviewer session",
        responses={422: {"model": ErrorResponse}},
    )
    def create_reviewer_session(
        payload: ReviewerSessionCreate,
    ) -> ReviewerSessionCreatedResponse:
        return ReviewerSessionCreatedResponse.from_created(
            service.create(
                game_id=payload.game_id,
                import_job_id=payload.import_job_id,
                lifetime_minutes=payload.lifetime_minutes,
            )
        )

    @router.post(
        "/reviewer/sessions/{session_id}/unlock",
        response_model=ReviewerSessionScopeResponse,
        operation_id="unlockReviewerSession",
        summary="Unlock one local reviewer session with its separately shared code",
        responses={
            401: {"model": ErrorResponse, "description": "Invalid access code"},
            404: {"model": ErrorResponse, "description": "Missing or expired session"},
            422: {"model": ErrorResponse},
        },
    )
    def unlock_reviewer_session(
        session_id: UUID,
        payload: ReviewerSessionUnlock,
    ) -> ReviewerSessionScopeResponse:
        return ReviewerSessionScopeResponse.from_session(
            service.unlock(session_id, payload.access_code)
        )

    return router


__all__ = ["create_reviewer_access_router"]
