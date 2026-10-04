"""Local Admin HTTP surface of the grid-audit proposal queue (TASK-0840).

Read-only. The routes are used by the local Reviewer only (the browser calls the
loopback Admin API directly); they are not on the public Reviewer proxy
allowlist. Saving a correction uses the existing
``image-reviews/{id}/geometry-revisions`` route.
"""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from game_predictor_api.application.grid_audit_proposals import (
    MAX_GRID_AUDIT_QUEUE_PAGE_SIZE,
    GridAuditProposalService,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.grid_audit_proposals import (
    GridAuditProposalResponse,
    GridAuditQueuePageResponse,
    to_grid_audit_proposal_response,
    to_grid_audit_queue_page_response,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope

GridAuditProposalServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "No imported proposal list or item"},
    409: {"model": ErrorResponse, "description": "Proposal artifact checksum mismatch"},
    422: {"model": ErrorResponse, "description": "Invalid queue request or artifact"},
}


def create_grid_audit_proposals_router(
    service_dependency: GridAuditProposalServiceDependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["grid-audit-proposals"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/games/{game_id}/grid-audit-proposals",
        response_model=GridAuditQueuePageResponse,
        operation_id="listGridAuditProposals",
        summary="List the open boards of the imported grid-audit proposal list",
        responses=ERROR_RESPONSES,
    )
    def list_grid_audit_proposals(
        game_id: UUID,
        service: Annotated[GridAuditProposalService, service_parameter],
        after_ordinal: Annotated[int | None, Query(alias="afterOrdinal", ge=0)] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_GRID_AUDIT_QUEUE_PAGE_SIZE)] = 1,
    ) -> GridAuditQueuePageResponse:
        with game_storage_scope(game_id):
            page = service.queue(game_id=game_id, after_ordinal=after_ordinal, limit=limit)
        return to_grid_audit_queue_page_response(game_id=game_id, page=page)

    @router.get(
        "/games/{game_id}/grid-audit-proposals/{item_id}",
        response_model=GridAuditProposalResponse,
        operation_id="getGridAuditProposal",
        summary="Read one audited board with its network grid proposal",
        responses=ERROR_RESPONSES,
    )
    def get_grid_audit_proposal(
        game_id: UUID,
        item_id: Annotated[str, Path(pattern=r"^[a-z][0-9]{5}$")],
        service: Annotated[GridAuditProposalService, service_parameter],
    ) -> GridAuditProposalResponse:
        with game_storage_scope(game_id):
            view = service.proposal(game_id=game_id, item_id=item_id)
        return to_grid_audit_proposal_response(game_id=game_id, view=view)

    return router


__all__ = ["create_grid_audit_proposals_router"]
