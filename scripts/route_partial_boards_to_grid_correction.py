"""Send boards with unknown search cells to the manual grid-correction queue.

A board whose search document has an unknown cell is shown as "częściowa
(potwierdzone minimum)" in board search (TASK-0818). This command reports the
unknown cells a human marked `unreadable` or `partial_visibility` and, with
`--apply`, marks them `Zła siatka` through the same checksum-bound decision
as the Reviewer, so the board enters the grid-correction queue. One
transaction per board; a board changed meanwhile is skipped and reported.
Re-running is safe: cells already reported are no longer selected.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
)
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from sqlalchemy import text

ACTOR = "system:partial-board-grid-route-v1"
ROUTED_QUALITY_ISSUES = ("unreadable", "partial_visibility")
_SAMPLE_SIZE = 20

SessionScope = Callable[[], AbstractContextManager[Any]]

# Unknown positions of every search document, joined to the board's current
# cell record (same current-geometry rule as the grid-correction queue).
_TARGET_CELLS = text(
    """
    SELECT d.sequence_number, d.review_item_id, c.id, c.cell_index, c.revision,
           c.geometry_revision, c.crop_sample_id, c.crop_checksum_sha256, c.quality_issue
    FROM image_board_search_fast_documents d
    JOIN image_review_items i ON i.id = d.review_item_id
    JOIN recognized_boards b ON b.id = i.recognized_board_id
    CROSS JOIN LATERAL unnest(d.primary_symbol_mobile_codes) WITH ORDINALITY u(code, ord)
    JOIN image_symbol_review_cells c
      ON c.game_id = d.game_id
     AND c.review_item_id = d.review_item_id
     AND c.recognized_board_id = b.id
     AND c.geometry_revision = b.geometry_revision
     AND c.cell_index = u.ord - 1
    WHERE d.game_id = :game_id
      AND u.code IS NULL
      AND c.source_available
      AND c.quality_issue = ANY(:issues)
    ORDER BY d.sequence_number, c.cell_index
    """
)


@dataclass(frozen=True, slots=True)
class TargetCell:
    sequence_number: int
    review_item_id: UUID
    cell_review_id: UUID
    cell_index: int
    revision: int
    geometry_revision: int
    crop_sample_id: str | None
    crop_checksum_sha256: str | None
    quality_issue: str


def target_cells(session: Any, game_id: UUID) -> tuple[TargetCell, ...]:
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    rows = session.execute(
        _TARGET_CELLS, {"game_id": game_id, "issues": list(ROUTED_QUALITY_ISSUES)}
    )
    return tuple(
        TargetCell(
            sequence_number=int(row[0]),
            review_item_id=row[1],
            cell_review_id=row[2],
            cell_index=int(row[3]),
            revision=int(row[4]),
            geometry_revision=int(row[5]),
            crop_sample_id=row[6],
            crop_checksum_sha256=row[7],
            quality_issue=str(row[8]),
        )
        for row in rows
    )


def boards_of(cells: Sequence[TargetCell]) -> dict[UUID, tuple[TargetCell, ...]]:
    """Target cells grouped by board, boards in sequence order."""

    boards: dict[UUID, list[TargetCell]] = {}
    for cell in cells:
        boards.setdefault(cell.review_item_id, []).append(cell)
    return {review_item_id: tuple(group) for review_item_id, group in boards.items()}


def summary(game_id: UUID, cells: Sequence[TargetCell]) -> dict[str, object]:
    boards = boards_of(cells)
    by_issue: dict[str, set[UUID]] = {}
    for cell in cells:
        by_issue.setdefault(cell.quality_issue, set()).add(cell.review_item_id)
    return {
        "gameId": str(game_id),
        "boardCount": len(boards),
        "cellCount": len(cells),
        "boardCountByQualityIssue": {issue: len(ids) for issue, ids in sorted(by_issue.items())},
        "sequenceSample": [group[0].sequence_number for group in boards.values()][:_SAMPLE_SIZE],
    }


def commands_for(game_id: UUID, cells: Sequence[TargetCell]) -> tuple[Any, ...]:
    return tuple(
        SymbolCellReviewMutationCommand(
            game_id=game_id,
            cell_review_id=cell.cell_review_id,
            action=SymbolCellReviewAction.MARK_GRID_ISSUE,
            expected_revision=cell.revision,
            expected_geometry_revision=cell.geometry_revision,
            expected_crop_sample_id=cell.crop_sample_id,
            expected_crop_checksum_sha256=cell.crop_checksum_sha256,
            target_symbol_id=None,
            actor=ACTOR,
        )
        for cell in cells
    )


def _apply_board(session: Any, commands: tuple[Any, ...]) -> None:
    GameStorageRouter().bind(session, commands[0].game_id, intent=GameStorageIntent.WRITE)
    SqlAlchemySymbolCellReviewMutationRepository(session).apply_board_mutations(commands)


def apply(
    sessions: SessionScope,
    game_id: UUID,
    cells: Sequence[TargetCell],
    *,
    apply_board: Callable[[Any, tuple[Any, ...]], None] = _apply_board,
) -> dict[str, object]:
    routed: list[int] = []
    skipped: list[dict[str, object]] = []
    for group in boards_of(cells).values():
        sequence_number = group[0].sequence_number
        try:
            with sessions() as session:
                apply_board(session, commands_for(game_id, group))
                session.commit()
        except SymbolCellReviewError as error:
            # The board changed since the selection; it is left as it is.
            skipped.append({"sequenceNumber": sequence_number, "code": error.code})
            continue
        routed.append(sequence_number)
    return {
        "routedBoardCount": len(routed),
        "skippedBoardCount": len(skipped),
        "skipped": skipped[:_SAMPLE_SIZE],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="write; default is preview")
    parser.add_argument("--max-boards", type=int, default=None, help="apply only")
    arguments = parser.parse_args(argv)
    factory = create_session_factory(
        create_maintenance_database_engine(ApiSettings.from_environment())
    )
    try:
        with factory() as session:
            cells = target_cells(session, arguments.game_id)
            session.rollback()
        report = summary(arguments.game_id, cells)
        report["mode"] = "apply" if arguments.apply else "preview"
        if arguments.apply:
            selected = tuple(boards_of(cells).values())[: arguments.max_boards]
            report.update(
                apply(factory, arguments.game_id, [cell for group in selected for cell in group])
            )
    except Exception as error:
        print(
            json.dumps({"code": "PARTIAL_BOARD_GRID_ROUTE_FAILED", "message": str(error)}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
