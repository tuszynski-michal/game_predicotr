"""Whole-panel session and machine/game boundary shared by public transports."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import ManagementError
from game_predictor_api.storage.management_models import ManagementAssignmentModel
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.models import GameModel


class ManagementPublicGuard:
    def __init__(
        self, session: Session, access: ManagementAccessService, token: str, expected: UUID
    ) -> None:
        self.session, self.access, self.token, self.expected = session, access, token, expected
        self.context = access.authenticate(token, expected, lock=True)

    def revalidate(self) -> None:
        self.access.authenticate(self.token, self.expected, lock=True)

    def before_commit(self) -> None:
        self.session.flush()
        self.revalidate()

    def game(self, machine_id: UUID, game_id: UUID, *, live: bool) -> None:
        self.revalidate()
        metadata = SqlAlchemyManagementRepository(self.session)
        point, machine = metadata.lock_machine(machine_id)
        assignment = self.session.get(
            ManagementAssignmentModel, (machine_id, game_id), populate_existing=True
        )
        if assignment is None:
            raise ManagementError(
                "MANAGEMENT_ASSIGNMENT_NOT_FOUND", "The game does not belong to this machine.", 404
            )
        if live:
            metadata.require_available(point, machine)
            game = self.session.scalar(
                select(GameModel)
                .where(GameModel.id == game_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
            if not assignment.attached or game is None or game.status != GameStatus.ACTIVE:
                raise ManagementError(
                    "MANAGEMENT_GAME_NOT_AVAILABLE",
                    "The assigned game must be active and attached.",
                )
