"""Application boundary for compact, partial-board search."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.super_game_markers import SuperGameMarkerSource
from game_predictor_api.domain.board_search import (
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    validate_board_search_query,
)
from game_predictor_api.domain.super_game_markers import (
    NO_SUPER_GAME_STATE,
    SuperGameMarkers,
)


class BoardSearchRepository(Protocol):
    def search(
        self,
        *,
        game_id: UUID,
        query: Sequence[BoardSearchQueryCell],
        scope: BoardSearchScope,
        limit: int,
    ) -> tuple[BoardSearchResult, ...]: ...


@dataclass(frozen=True, slots=True)
class BoardSearchOutcome:
    """Ranked results plus the super game markers of their positions and the
    freshness of the generation the markers come from (TASK-0935)."""

    results: tuple[BoardSearchResult, ...]
    super_game: SuperGameMarkers


class BoardSearchService:
    def __init__(
        self,
        repository: BoardSearchRepository,
        super_game_markers: SuperGameMarkerSource | None = None,
    ) -> None:
        self._repository = repository
        self._super_game_markers = super_game_markers

    def search(
        self,
        *,
        game_id: UUID,
        cells: Iterable[BoardSearchQueryCell],
        scope: BoardSearchScope,
        limit: int,
    ) -> tuple[BoardSearchResult, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("board-search limit must be between 1 and 100")
        query = validate_board_search_query(cells)
        return self._repository.search(
            game_id=game_id,
            query=query,
            scope=scope,
            limit=limit,
        )

    def search_with_super_game(
        self,
        *,
        game_id: UUID,
        cells: Iterable[BoardSearchQueryCell],
        scope: BoardSearchScope,
        limit: int,
    ) -> BoardSearchOutcome:
        """`search` plus the super game markers of the found positions.

        Without a marker source (no series storage wired) nothing is marked
        and the state is the fresh state of a game without a super game.
        """

        results = self.search(game_id=game_id, cells=cells, scope=scope, limit=limit)
        if self._super_game_markers is None:
            return BoardSearchOutcome(
                results=results, super_game=SuperGameMarkers(state=NO_SUPER_GAME_STATE)
            )
        return BoardSearchOutcome(
            results=results,
            super_game=self._super_game_markers.markers(
                game_id, [result.sequence_number for result in results]
            ),
        )


__all__ = ["BoardSearchOutcome", "BoardSearchRepository", "BoardSearchService"]
