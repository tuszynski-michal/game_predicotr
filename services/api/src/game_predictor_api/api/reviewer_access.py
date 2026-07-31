"""HTTP endpoints for durable Reviewer session lifecycle."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from game_predictor_api.api.reviewer_security import (
    create_required_reviewer_session_dependency,
)
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessService,
    ReviewerAccessSession,
)
from game_predictor_api.schemas.catalog import (
    ErrorResponse,
    GameResponse,
    SymbolResponse,
)
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_api.schemas.reviewer_access import (
    ReviewerSessionCreate,
    ReviewerSessionCreatedResponse,
    ReviewerSessionScopeResponse,
    ReviewerSessionUnlock,
    ReviewerSessionUnlockResponse,
)


def create_reviewer_access_router(
    service_dependency: Callable[..., object],
    catalog_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(tags=["reviewer-access"])
    service_parameter = Depends(service_dependency)
    catalog_parameter = Depends(catalog_service_dependency)
    job_parameter = Depends(job_service_dependency)
    authorized_session_parameter = Depends(
        create_required_reviewer_session_dependency(service_dependency)
    )

    @router.post(
        "/admin/reviewer-sessions",
        response_model=ReviewerSessionCreatedResponse,
        status_code=201,
        operation_id="createReviewerSession",
        summary="Create one durable game and import scoped reviewer session",
        responses={422: {"model": ErrorResponse}},
    )
    def create_reviewer_session(
        payload: ReviewerSessionCreate,
        service: Annotated[ReviewerAccessService, service_parameter],
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
        response_model=ReviewerSessionUnlockResponse,
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
        service: Annotated[ReviewerAccessService, service_parameter],
    ) -> ReviewerSessionUnlockResponse:
        return ReviewerSessionUnlockResponse.from_unlocked(
            service.unlock(session_id, payload.access_code)
        )

    @router.post(
        "/admin/reviewer-sessions/{session_id}/revoke",
        response_model=ReviewerSessionScopeResponse,
        operation_id="revokeReviewerSession",
        summary="Immediately revoke one Reviewer session",
        responses={404: {"model": ErrorResponse}},
    )
    def revoke_reviewer_session(
        session_id: UUID,
        service: Annotated[ReviewerAccessService, service_parameter],
    ) -> ReviewerSessionScopeResponse:
        return ReviewerSessionScopeResponse.from_session(service.revoke(session_id))

    @router.get(
        "/reviewer/context/games",
        response_model=list[GameResponse],
        operation_id="listReviewerGames",
        summary="Read only the game selected for the authenticated Reviewer session",
    )
    def list_reviewer_games(
        session: Annotated[ReviewerAccessSession, authorized_session_parameter],
        catalog: Annotated[CatalogService, catalog_parameter],
    ) -> list[GameResponse]:
        return [GameResponse.model_validate(catalog.get_game(session.game_id))]

    @router.get(
        "/reviewer/context/jobs",
        response_model=list[JobResponse],
        operation_id="listReviewerJobs",
        summary="Read only the import selected for the authenticated Reviewer session",
    )
    def list_reviewer_jobs(
        session: Annotated[ReviewerAccessSession, authorized_session_parameter],
        jobs: Annotated[JobService, job_parameter],
    ) -> list[JobResponse]:
        job = jobs.get_job(session.import_job_id)
        if job.game_id != session.game_id:
            raise RuntimeError("Persisted Reviewer session has an invalid scope.")
        return [JobResponse.from_domain(job)]

    @router.get(
        "/reviewer/context/games/{game_id}/symbols",
        response_model=list[SymbolResponse],
        operation_id="listReviewerSymbols",
        summary="Read symbols only for the authenticated Reviewer game",
    )
    def list_reviewer_symbols(
        game_id: UUID,
        session: Annotated[ReviewerAccessSession, authorized_session_parameter],
        service: Annotated[ReviewerAccessService, service_parameter],
        catalog: Annotated[CatalogService, catalog_parameter],
    ) -> list[SymbolResponse]:
        service.authorize_scope(
            session,
            game_id=game_id,
            import_job_id=session.import_job_id,
        )
        return [SymbolResponse.model_validate(symbol) for symbol in catalog.list_symbols(game_id)]

    return router


__all__ = ["create_reviewer_access_router"]
