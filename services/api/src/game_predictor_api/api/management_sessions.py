"""Local-only link administration using the existing Reviewer ingress controller."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
    ensure_online_reviewer_ingress,
)
from game_predictor_api.schemas.management_sessions import (
    ManagementSessionCreate,
    ManagementSessionCreated,
    ManagementSessionList,
    ManagementSessionResponse,
)


def create_management_sessions_router(
    access_dependency: Callable[..., object], ingress_dependency: Callable[..., object]
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/management/sessions", tags=["management-links"])
    access = Depends(access_dependency, scope="function")
    ingress = Depends(ingress_dependency)

    @router.post(
        "",
        response_model=ManagementSessionCreated,
        status_code=201,
        operation_id="createManagementSession",
    )
    def create(
        payload: ManagementSessionCreate,
        service: Annotated[ManagementAccessService, access],
        controller: Annotated[ReviewerIngressService, ingress],
    ) -> ManagementSessionCreated:
        service.validate_create(payload.label, payload.lifetime_minutes)
        service.lock_ingress()
        status = ensure_online_reviewer_ingress(controller)
        record, code = service.create(payload.label, payload.lifetime_minutes)
        return ManagementSessionCreated(
            session=ManagementSessionResponse.view(record, status), access_code=code
        )

    @router.get("", response_model=ManagementSessionList, operation_id="listManagementSessions")
    def list_sessions(
        service: Annotated[ManagementAccessService, access],
        controller: Annotated[ReviewerIngressService, ingress],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> ManagementSessionList:
        try:
            status = controller.status()
        except ReviewerIngressError:
            status = None
        return ManagementSessionList(
            sessions=tuple(
                ManagementSessionResponse.view(record, status) for record in service.list(limit)
            )
        )

    @router.post(
        "/{session_id}/revoke",
        response_model=ManagementSessionResponse,
        operation_id="revokeManagementSession",
    )
    def revoke(
        session_id: UUID, service: Annotated[ManagementAccessService, access]
    ) -> ManagementSessionResponse:
        return ManagementSessionResponse.view(service.revoke(session_id))

    return router
