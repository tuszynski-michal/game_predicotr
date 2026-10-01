"""Persistence of board-search share query log entries (D-472)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryEvent,
    BoardSearchShareQueryLog,
    BoardSearchShareQueryRepository,
)
from game_predictor_api.domain.board_search_share_queries import (
    QUERY_OUTCOME_OK,
    BoardSearchShareQueryEntry,
    BoardSearchShareQueryKind,
)
from game_predictor_api.storage.models import (
    BoardSearchShareQueryEventModel,
    BoardSearchShareSessionModel,
)


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


class SqlAlchemyBoardSearchShareQueryRepository(BoardSearchShareQueryRepository):
    """Reads the log for the local owner (keyset pages on the
    `(session_id, occurred_at DESC, id DESC)` index)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def session_exists(self, session_id: UUID) -> bool:
        return self._session.get(BoardSearchShareSessionModel, session_id) is not None

    def list_events(
        self,
        *,
        session_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[BoardSearchShareQueryEvent]:
        model = BoardSearchShareQueryEventModel
        statement = select(model).where(model.session_id == session_id)
        if before is not None:
            occurred_at, event_id = before
            statement = statement.where(
                or_(
                    model.occurred_at < occurred_at,
                    and_(model.occurred_at == occurred_at, model.id < event_id),
                )
            )
        statement = statement.order_by(model.occurred_at.desc(), model.id.desc()).limit(limit)
        return tuple(_event(row) for row in self._session.scalars(statement))

    def get_event(self, event_id: UUID) -> BoardSearchShareQueryEvent | None:
        row = self._session.get(BoardSearchShareQueryEventModel, event_id)
        return None if row is None else _event(row)

    def latest_successful_event(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind,
        at_or_before: tuple[datetime, UUID],
    ) -> BoardSearchShareQueryEvent | None:
        model = BoardSearchShareQueryEventModel
        occurred_at, event_id = at_or_before
        row = self._session.scalar(
            select(model)
            .where(
                model.session_id == session_id,
                model.kind == kind.value,
                model.outcome_code == QUERY_OUTCOME_OK,
                or_(
                    model.occurred_at < occurred_at,
                    and_(model.occurred_at == occurred_at, model.id <= event_id),
                ),
            )
            .order_by(model.occurred_at.desc(), model.id.desc())
            .limit(1)
        )
        return None if row is None else _event(row)


def _event(row: BoardSearchShareQueryEventModel) -> BoardSearchShareQueryEvent:
    return BoardSearchShareQueryEvent(
        id=row.id,
        session_id=row.session_id,
        game_id=row.game_id,
        occurred_at=row.occurred_at,
        kind=BoardSearchShareQueryKind(row.kind),
        request=dict(row.request),
        result_summary=dict(row.result_summary),
        outcome_code=row.outcome_code,
    )


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


__all__ = [
    "InMemoryBoardSearchShareQueryLog",
    "SqlAlchemyBoardSearchShareQueryLog",
    "SqlAlchemyBoardSearchShareQueryRepository",
]
