"""Build the compact partial-board search projection for one or all games."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import GameModel
from sqlalchemy import select


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--game-id", type=UUID)
    selector.add_argument("--all-games", action="store_true")
    return parser.parse_args()


def _game_ids(arguments: argparse.Namespace) -> tuple[UUID, ...]:
    if arguments.game_id is not None:
        return (arguments.game_id,)
    settings = ApiSettings.from_environment()
    factory = create_session_factory(create_database_engine(settings))
    with factory() as session:
        return tuple(session.scalars(select(GameModel.id).order_by(GameModel.id)).all())


def _rebuild(game_ids: Sequence[UUID]) -> list[dict[str, object]]:
    settings = ApiSettings.from_environment()
    factory = create_session_factory(create_database_engine(settings))
    reports: list[dict[str, object]] = []
    for game_id in game_ids:
        with factory.begin() as session:
            SqlAlchemyBoardSearchProjectionRepository(session).start_rebuild(game_id)
        try:
            with factory.begin() as session:
                result = SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game_id)
        except Exception as error:
            with factory.begin() as session:
                SqlAlchemyBoardSearchProjectionRepository(session).mark_rebuild_failed(
                    game_id,
                    str(error),
                )
            raise
        reports.append(
            {
                "gameId": str(game_id),
                "candidateCount": result.candidate_count,
                "documentCount": result.document_count,
                "skippedReviewItemCount": result.skipped_review_item_count,
            }
        )
    return reports


def main() -> int:
    arguments = _arguments()
    started = time.perf_counter()
    try:
        reports = _rebuild(_game_ids(arguments))
    except Exception as error:
        print(
            json.dumps(
                {
                    "code": "BOARD_SEARCH_PROJECTION_REBUILD_FAILED",
                    "message": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "elapsedSeconds": round(time.perf_counter() - started, 3),
                "games": reports,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
