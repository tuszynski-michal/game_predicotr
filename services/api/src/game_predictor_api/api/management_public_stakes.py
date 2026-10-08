"""Narrow game-bound management routes, separate from multi-game metadata sessions."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from game_predictor_api.application.management_stakes import ManagementStakeService
from game_predictor_api.schemas.board_search_approximate_win import ApproximateWinResponse
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCellCorrectionResponse,
    BoardSearchSharePublicBoardDetailResponse,
    to_board_search_share_public_search_response,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.management_public import (
    ManagementPublicSearchResponse,
    named_actor,
    public_payload,
)
from game_predictor_api.schemas.management_stakes import (
    ManagementClearCommand,
    ManagementCorrectionCommand,
    ManagementJournalResponse,
    ManagementRefreshCommand,
    ManagementRefreshResponse,
    ManagementResultResponse,
    ManagementSaveCommand,
    ManagementSearchCommand,
    ManagementStake,
    ManagementStakeListResponse,
    ManagementStakeResponse,
)


def create_management_public_stake_router(service_dependency: Callable[..., object]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/management-public",
        tags=["management-public"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    dependency = Depends(service_dependency, scope="function")
    base = "/machines/{machine_id}/game/{game_id}"

    @router.get(
        base + "/approximate-win",
        response_model=ApproximateWinResponse,
        operation_id="getPublicManagementApproximateWin",
    )
    def preview(
        machine_id: UUID,
        game_id: UUID,
        service: Annotated[ManagementStakeService, dependency],
        start: Annotated[int, Query(alias="startSequenceNumber", ge=1)],
        count: Annotated[int, Query(alias="spinCount", ge=1, le=100000)],
    ) -> ApproximateWinResponse:
        return service.preview(machine_id, game_id, start, count)

    @router.get(
        base + "/stakes",
        response_model=ManagementStakeListResponse,
        operation_id="listPublicManagementStakes",
    )
    def slots(
        machine_id: UUID, game_id: UUID, service: Annotated[ManagementStakeService, dependency]
    ) -> ManagementStakeListResponse:
        return service.list_slots(machine_id, game_id)

    @router.get(
        base + "/stakes/{stake}",
        response_model=ManagementStakeResponse,
        operation_id="getPublicManagementStake",
    )
    def slot(
        machine_id: UUID,
        game_id: UUID,
        stake: ManagementStake,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementStakeResponse:
        return service.slot(machine_id, game_id, stake)

    @router.post(
        base + "/search",
        response_model=ManagementPublicSearchResponse,
        operation_id="searchPublicManagementBoards",
    )
    def search(
        machine_id: UUID,
        game_id: UUID,
        payload: ManagementSearchCommand,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementPublicSearchResponse:
        value = service.search(machine_id, game_id, payload)
        return ManagementPublicSearchResponse(
            search_context_id=value.search_context_id,
            search=to_board_search_share_public_search_response(value.search),
        )

    @router.put(
        base + "/stakes/{stake}",
        response_model=ManagementStakeResponse,
        operation_id="savePublicManagementStake",
    )
    def save(
        machine_id: UUID,
        game_id: UUID,
        stake: ManagementStake,
        payload: ManagementSaveCommand,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementStakeResponse:
        return service.save(machine_id, game_id, stake, payload)

    @router.post(
        base + "/stakes/{stake}/clear",
        response_model=ManagementStakeResponse,
        operation_id="clearPublicManagementStake",
    )
    def clear(
        machine_id: UUID,
        game_id: UUID,
        stake: ManagementStake,
        payload: ManagementClearCommand,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementStakeResponse:
        return service.clear(machine_id, game_id, stake, payload)

    @router.post(
        base + "/stakes/{stake}/refresh",
        response_model=ManagementRefreshResponse,
        operation_id="refreshPublicManagementStake",
    )
    def refresh(
        machine_id: UUID,
        game_id: UUID,
        stake: ManagementStake,
        payload: ManagementRefreshCommand,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementRefreshResponse:
        return service.refresh(machine_id, game_id, stake, payload)

    @router.get(
        base + "/results/{version_id}",
        response_model=ManagementResultResponse,
        operation_id="getPublicManagementResult",
    )
    def result(
        machine_id: UUID,
        game_id: UUID,
        version_id: UUID,
        service: Annotated[ManagementStakeService, dependency],
    ) -> ManagementResultResponse:
        value = service.result(machine_id, game_id, version_id)
        public_payload(value.model_dump(mode="json", by_alias=True))
        return value

    @router.get(
        "/machines/{machine_id}/journal",
        response_model=ManagementJournalResponse,
        operation_id="listPublicManagementJournal",
    )
    def journal(
        machine_id: UUID,
        service: Annotated[ManagementStakeService, dependency],
        game_id: Annotated[UUID | None, Query(alias="gameId")] = None,
        stake: Annotated[ManagementStake | None, Query(alias="stakeGrosze")] = None,
        before: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ManagementJournalResponse:
        value = service.journal(
            machine_id, game_id=game_id, stake=stake, before=before, limit=limit
        )
        public_payload(value.model_dump(mode="json", by_alias=True))
        return value.model_copy(
            update={
                "entries": tuple(
                    entry.model_copy(update={"actor": named_actor(entry.actor)})
                    for entry in value.entries
                )
            }
        )

    @router.get(
        base + "/boards/{sequence}",
        response_model=BoardSearchSharePublicBoardDetailResponse,
        operation_id="getPublicManagementBoardDetail",
    )
    def detail(
        machine_id: UUID,
        game_id: UUID,
        sequence: int,
        service: Annotated[ManagementStakeService, dependency],
    ) -> BoardSearchSharePublicBoardDetailResponse:
        return service.detail(machine_id, game_id, sequence)

    @router.post(
        base + "/stakes/{stake}/boards/{sequence}/cells/{cell}/decision",
        response_model=BoardSearchShareCellCorrectionResponse,
        operation_id="correctPublicManagementBoardCell",
    )
    def correct(
        machine_id: UUID,
        game_id: UUID,
        stake: ManagementStake,
        sequence: int,
        cell: int,
        payload: ManagementCorrectionCommand,
        service: Annotated[ManagementStakeService, dependency],
    ) -> BoardSearchShareCellCorrectionResponse:
        return service.correct(machine_id, game_id, stake, sequence, cell, payload)

    return router
