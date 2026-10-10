"""Actor-bound application port shared by local and future public panel transports."""

from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.schemas.board_search_approximate_win import ApproximateWinResponse
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCellCorrectionResponse,
    BoardSearchSharePublicBoardDetailResponse,
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
    ManagementSearchResponse,
    ManagementStakeListResponse,
    ManagementStakeResponse,
)


class ManagementStakeRepository(Protocol):
    def before_commit(self) -> None: ...

    def list_slots(self, machine_id: UUID, game_id: UUID) -> ManagementStakeListResponse: ...

    def slot(self, machine_id: UUID, game_id: UUID, stake: int) -> ManagementStakeResponse: ...

    def search(
        self, machine_id: UUID, game_id: UUID, command: ManagementSearchCommand, actor: str
    ) -> ManagementSearchResponse: ...

    def save(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementSaveCommand,
        actor: str,
    ) -> ManagementStakeResponse: ...

    def clear(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementClearCommand,
        actor: str,
    ) -> ManagementStakeResponse: ...

    def refresh(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        command: ManagementRefreshCommand,
        actor: str,
    ) -> ManagementRefreshResponse: ...

    def result(
        self, machine_id: UUID, game_id: UUID, version_id: UUID
    ) -> ManagementResultResponse: ...

    def journal(
        self,
        machine_id: UUID,
        *,
        game_id: UUID | None = None,
        stake: int | None = None,
        before: str | None = None,
        limit: int = 20,
    ) -> ManagementJournalResponse: ...

    def detail(
        self, machine_id: UUID, game_id: UUID, sequence: int
    ) -> BoardSearchSharePublicBoardDetailResponse: ...

    def preview(
        self, machine_id: UUID, game_id: UUID, start: int, count: int
    ) -> ApproximateWinResponse: ...

    def correct(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        sequence: int,
        cell_index: int,
        command: ManagementCorrectionCommand,
        actor: str,
    ) -> BoardSearchShareCellCorrectionResponse: ...


class ManagementStakeService:
    def __init__(self, repository: ManagementStakeRepository, actor: str = "local-owner") -> None:
        self.repository, self.actor = repository, actor

    def before_commit(self) -> None:
        self.repository.before_commit()

    def list_slots(self, machine_id: UUID, game_id: UUID) -> ManagementStakeListResponse:
        return self.repository.list_slots(machine_id, game_id)

    def slot(self, machine_id: UUID, game_id: UUID, stake: int) -> ManagementStakeResponse:
        return self.repository.slot(machine_id, game_id, stake)

    def result(self, machine_id: UUID, game_id: UUID, version_id: UUID) -> ManagementResultResponse:
        return self.repository.result(machine_id, game_id, version_id)

    def journal(self, machine_id: UUID, **options: Any) -> ManagementJournalResponse:
        return self.repository.journal(machine_id, **options)

    def search(
        self, machine_id: UUID, game_id: UUID, command: ManagementSearchCommand
    ) -> ManagementSearchResponse:
        return self.repository.search(machine_id, game_id, command, self.actor)

    def save(
        self, machine_id: UUID, game_id: UUID, stake: int, command: ManagementSaveCommand
    ) -> ManagementStakeResponse:
        return self.repository.save(machine_id, game_id, stake, command, self.actor)

    def clear(
        self, machine_id: UUID, game_id: UUID, stake: int, command: ManagementClearCommand
    ) -> ManagementStakeResponse:
        return self.repository.clear(machine_id, game_id, stake, command, self.actor)

    def refresh(
        self, machine_id: UUID, game_id: UUID, stake: int, command: ManagementRefreshCommand
    ) -> ManagementRefreshResponse:
        return self.repository.refresh(machine_id, game_id, stake, command, self.actor)

    def detail(
        self, machine_id: UUID, game_id: UUID, sequence: int
    ) -> BoardSearchSharePublicBoardDetailResponse:
        return self.repository.detail(machine_id, game_id, sequence)

    def preview(
        self, machine_id: UUID, game_id: UUID, start: int, count: int
    ) -> ApproximateWinResponse:
        return self.repository.preview(machine_id, game_id, start, count)

    def correct(
        self,
        machine_id: UUID,
        game_id: UUID,
        stake: int,
        sequence: int,
        cell: int,
        command: ManagementCorrectionCommand,
    ) -> BoardSearchShareCellCorrectionResponse:
        return self.repository.correct(
            machine_id, game_id, stake, sequence, cell, command, self.actor
        )
