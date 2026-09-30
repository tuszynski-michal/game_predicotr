"""Persistence of board-search share query log entries (D-472)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from game_predictor_api.application.board_search_share_queries import BoardSearchShareQueryLog
from game_predictor_api.domain.board_search_share_queries import BoardSearchShareQueryEntry
from game_predictor_api.storage.models import BoardSearchShareQueryEventModel


class SqlAlchemyBoardSearchShareQueryLog(BoardSearchShareQueryLog):
    """Writes each entry in its own short transaction and commits it before
    the caller returns any data (fail-closed, R5)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        session_id: UUID,
        game_id: UUID,
        entry: BoardSearchShareQueryEntry,
        occurred_at: datetime,
    ) -> None:
        with self._session_factory() as session:
            try:
                session.add(
                    BoardSearchShareQueryEventModel(
                        id=uuid4(),
                        session_id=session_id,
                        game_id=game_id,
                        occurred_at=occurred_at,
                        kind=entry.kind.value,
                        request=dict(entry.request),
                        result_summary=dict(entry.result_summary),
                        outcome_code=entry.outcome_code,
                    )
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise


class InMemoryBoardSearchShareQueryLog(BoardSearchShareQueryLog):
    def __init__(self) -> None:
        self._lock = RLock()
        self.entries: list[dict[str, object]] = []
        self.fail = False

    def record(
        self,
        *,
        session_id: UUID,
        game_id: UUID,
        entry: BoardSearchShareQueryEntry,
        occurred_at: datetime,
    ) -> None:
        if self.fail:
            raise RuntimeError("Synthetic query log failure.")
        with self._lock:
            self.entries.append(
                {
                    "sessionId": session_id,
                    "gameId": game_id,
                    "kind": entry.kind.value,
                    "request": dict(entry.request),
                    "resultSummary": dict(entry.result_summary),
                    "outcomeCode": entry.outcome_code,
                    "occurredAt": occurred_at,
                }
            )


__all__ = ["InMemoryBoardSearchShareQueryLog", "SqlAlchemyBoardSearchShareQueryLog"]
