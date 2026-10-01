"""Per-board inputs of the current review-cell mapper (D-467, TASK-0758/0759).

The Reviewer mapper (``materialize_current_image_review_cells``) needs, per
board, the render manifest of its current geometry revision
(``board_render_manifests``); predictions come from
``recognized_boards.cells_prediction`` or the newest prediction revision.
Every board is ``virtual_source`` since D-467 S6 (migration 0135, TASK-0796).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.storage.board_render_manifest_reader import (
    CurrentBoardRenderManifest,
    load_current_render_manifests,
)
from game_predictor_api.storage.models import RecognizedBoardModel


@dataclass(frozen=True, slots=True)
class CurrentBoardCellSources:
    render_manifest: CurrentBoardRenderManifest | None = None


NO_CELL_SOURCES = CurrentBoardCellSources()


def load_current_board_cell_sources(
    session: Session,
    boards: Iterable[tuple[RecognizedBoardModel, UUID]],
) -> dict[UUID, CurrentBoardCellSources]:
    """Load the mapper inputs for ``(board, game_id)`` pairs in batched reads."""

    boards_by_game: dict[UUID, list[RecognizedBoardModel]] = defaultdict(list)
    for board, game_id in boards:
        boards_by_game[game_id].append(board)
    manifests: dict[UUID, CurrentBoardRenderManifest] = {}
    for game_id, game_boards in boards_by_game.items():
        manifests.update(
            load_current_render_manifests(session, game_id=game_id, boards=game_boards)
        )
    return {
        board.id: CurrentBoardCellSources(render_manifest=manifests.get(board.id))
        for game_boards in boards_by_game.values()
        for board in game_boards
    }


def load_current_board_cell_source(
    session: Session, *, game_id: UUID, board: RecognizedBoardModel
) -> CurrentBoardCellSources:
    return load_current_board_cell_sources(session, ((board, game_id),)).get(
        board.id, NO_CELL_SOURCES
    )


__all__ = [
    "NO_CELL_SOURCES",
    "CurrentBoardCellSources",
    "load_current_board_cell_source",
    "load_current_board_cell_sources",
]
