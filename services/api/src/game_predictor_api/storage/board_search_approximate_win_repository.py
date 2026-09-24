"""PostgreSQL repository for the admin "Przybliżona wygrana" range calculator.

Combines three read-only concerns that `BoardSearchApproximateWinService`
needs and that do not naturally belong to a single existing repository: the
game's sequence length, the latest published rules version's payout
configuration (reused from the worker package, independent of any dataset —
TASK-0650), and board-search projection evidence for a contiguous sequence
range (delegated to `SqlAlchemyBoardSearchProjectionRepository`, so both
board search and approximate win read the exact same source and raise the
exact same readiness errors).
"""

from __future__ import annotations

from uuid import UUID

from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from game_predictor_worker.payouts.store import load_rules_payout_configuration
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import ApproximateWinDocument
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.models import GameModel, RulesVersionModel


class SqlAlchemyBoardSearchApproximateWinRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._projection = SqlAlchemyBoardSearchProjectionRepository(session)

    def game_sequence_length(self, game_id: UUID) -> int:
        """The game's current completeness target (`games.expected_layout_count`),
        i.e. the deterministic sequence length `L` used to plan and wrap the
        approximate-win range.
        """
        game = self._session.get(GameModel, game_id)
        if game is None:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        return int(game.expected_layout_count)

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        """The most recently published rules version's payout configuration,
        or `None` when the game has never published one.
        """
        rules_version_id = self._session.scalar(
            select(RulesVersionModel.id)
            .where(
                RulesVersionModel.game_id == game_id,
                RulesVersionModel.status == RulesVersionStatus.PUBLISHED,
            )
            .order_by(RulesVersionModel.version.desc())
            .limit(1)
        )
        if rules_version_id is None:
            return None
        return load_rules_payout_configuration(self._session, rules_version_id)

    def range_documents(
        self,
        *,
        game_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
    ) -> tuple[BoardSearchAssetMode, tuple[ApproximateWinDocument, ...]]:
        """Delegate to the board-search projection repository so approximate
        win reads the same source, with the same readiness errors, as
        partial board search.
        """
        return self._projection.range_documents(
            game_id=game_id,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
        )


__all__ = ["SqlAlchemyBoardSearchApproximateWinRepository"]
