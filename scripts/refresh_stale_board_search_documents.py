"""Refresh board-search documents written before their board's current grid.

Bulk form of the "Odśwież odczyt tej planszy" button (TASK-0773, TASK-0814).
Without `--apply` the command only counts stale documents. With `--apply`
each stale position is rebuilt by the same projection sync as the button, one
transaction per batch; an interrupted run is resumed by running it again,
because the selection is the staleness itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from game_predictor_api.application.board_search_board_detail import (
    BoardSearchStaleDocumentRefresh,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)

_PREVIEW_SAMPLE_SIZE = 20
_COUNT_PAGE_SIZE = 5_000

SessionScope = Callable[[], AbstractContextManager[Any]]


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="write; default is preview")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--max-boards",
        type=int,
        default=None,
        help="stop after this many stale positions (apply only)",
    )
    arguments = parser.parse_args(argv)
    if arguments.batch_size < 1:
        parser.error("--batch-size must be positive")
    if arguments.max_boards is not None and arguments.max_boards < 1:
        parser.error("--max-boards must be positive")
    return arguments


def _service(session: Any) -> BoardSearchStaleDocumentRefresh:
    return BoardSearchStaleDocumentRefresh(SqlAlchemyBoardSearchApproximateWinRepository(session))


def preview(sessions: SessionScope, game_id: UUID) -> dict[str, object]:
    """Read-only count; the transaction is rolled back."""

    count = 0
    sample: list[int] = []
    cursor = 0
    with sessions() as session:
        service = _service(session)
        while True:
            page = service.stale_sequence_numbers(
                game_id=game_id, after_sequence_number=cursor, limit=_COUNT_PAGE_SIZE
            )
            if not page:
                break
            count += len(page)
            sample.extend(page[: max(0, _PREVIEW_SAMPLE_SIZE - len(sample))])
            cursor = page[-1]
        session.rollback()
    return {"gameId": str(game_id), "mode": "preview", "staleCount": count, "sample": sample}


def apply(
    sessions: SessionScope,
    game_id: UUID,
    *,
    batch_size: int,
    max_boards: int | None,
    progress: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    refreshed = 0
    removed = 0
    still_stale: list[int] = []
    cursor = 0
    batches = 0
    while max_boards is None or refreshed + removed + len(still_stale) < max_boards:
        limit = batch_size
        if max_boards is not None:
            limit = min(limit, max_boards - refreshed - removed - len(still_stale))
        with sessions() as session:
            batch = _service(session).refresh_batch(
                game_id=game_id, after_sequence_number=cursor, limit=limit
            )
            session.commit()
        if batch.last_sequence_number is None:
            break
        batches += 1
        cursor = batch.last_sequence_number
        refreshed += len(batch.refreshed)
        removed += len(batch.removed)
        still_stale.extend(batch.still_stale)
        progress(
            {
                "batch": batches,
                "cursor": cursor,
                "refreshed": refreshed,
                "removed": removed,
                "stillStale": len(still_stale),
            }
        )
    return {
        "gameId": str(game_id),
        "mode": "apply",
        "batches": batches,
        "refreshedCount": refreshed,
        "removedCount": removed,
        "stillStaleCount": len(still_stale),
        "stillStaleSample": still_stale[:_PREVIEW_SAMPLE_SIZE],
    }


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    factory = create_session_factory(
        create_maintenance_database_engine(ApiSettings.from_environment())
    )
    started = time.perf_counter()
    try:
        if arguments.apply:
            report = apply(
                factory,
                arguments.game_id,
                batch_size=arguments.batch_size,
                max_boards=arguments.max_boards,
                progress=lambda line: print(json.dumps(line), flush=True),
            )
        else:
            report = preview(factory, arguments.game_id)
    except Exception as error:
        print(
            json.dumps({"code": "BOARD_SEARCH_STALE_REFRESH_FAILED", "message": str(error)}),
            file=sys.stderr,
        )
        return 1
    report["elapsedSeconds"] = round(time.perf_counter() - started, 3)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
