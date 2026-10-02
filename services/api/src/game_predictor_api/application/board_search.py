"""Application boundary for compact, partial-board search."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.board_search import (
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    validate_board_search_query,
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


class BoardSearchService:
    def __init__(self, repository: BoardSearchRepository) -> None:
        self._repository = repository

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


__all__ = ["BoardSearchRepository", "BoardSearchService"]
