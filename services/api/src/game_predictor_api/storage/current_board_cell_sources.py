"""Per-board inputs of the current review-cell mapper (D-467, TASK-0758).

The Reviewer mapper (``materialize_current_image_review_cells``) needs, per
board, exactly one of:

* ``virtual_source``: the render manifest of the current geometry revision
  (``board_render_manifests``); predictions come from
  ``recognized_boards.cells_prediction`` or the newest prediction revision;
* ``legacy_file`` at revision > 0: the current geometry revision's
  ``crop_artifacts`` (passed separately) and ``cells_prediction``;
* ``legacy_file`` at revision 0: the base cells of the isolated legacy
  observation adapter (removed in S5).
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
from game_predictor_api.storage.legacy_cell_observation_adapter import (
    LegacyBaseCell,
    legacy_base_cells,
)
from game_predictor_api.storage.models import RecognizedBoardModel


@dataclass(frozen=True, slots=True)
class CurrentBoardCellSources:
    render_manifest: CurrentBoardRenderManifest | None = None
    legacy_base_cells: tuple[LegacyBaseCell, ...] = ()


NO_CELL_SOURCES = CurrentBoardCellSources()


def needs_legacy_base_cells(board: RecognizedBoardModel) -> bool:
    return board.asset_mode == "legacy_file" and board.geometry_revision == 0


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
    all_boards = [board for game_boards in boards_by_game.values() for board in game_boards]
    legacy = legacy_base_cells(
        session, [board.id for board in all_boards if needs_legacy_base_cells(board)]
    )
    return {
        board.id: CurrentBoardCellSources(
            render_manifest=manifests.get(board.id),
            legacy_base_cells=legacy.get(board.id, ()),
        )
        for board in all_boards
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
    "needs_legacy_base_cells",
]
