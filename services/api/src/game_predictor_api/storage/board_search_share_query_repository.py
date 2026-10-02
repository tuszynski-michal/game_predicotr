"""Persistence of board-search share query log entries (D-472)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select
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
        kind: BoardSearchShareQueryKind | None = None,
    ) -> Sequence[BoardSearchShareQueryEvent]:
        model = BoardSearchShareQueryEventModel
        statement = select(model).where(model.session_id == session_id)
        if kind is not None:
            statement = statement.where(model.kind == kind.value)
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

    def next_event_key(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind | None,
        after: tuple[datetime, UUID],
    ) -> tuple[datetime, UUID] | None:
        model = BoardSearchShareQueryEventModel
        statement = select(model.occurred_at, model.id).where(
            model.session_id == session_id, _key_after(after)
        )
        if kind is not None:
            statement = statement.where(model.kind == kind.value)
        row = self._session.execute(
            statement.order_by(model.occurred_at, model.id).limit(1)
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    def latest_successful_event_between(
        self,
        *,
        session_id: UUID,
        kind: BoardSearchShareQueryKind,
        after: tuple[datetime, UUID],
        before: tuple[datetime, UUID] | None,
    ) -> BoardSearchShareQueryEvent | None:
        model = BoardSearchShareQueryEventModel
        statement = select(model).where(
            model.session_id == session_id,
            model.kind == kind.value,
            model.outcome_code == QUERY_OUTCOME_OK,
            _key_after(after),
        )
        if before is not None:
            statement = statement.where(_key_before(before))
        row = self._session.scalar(
            statement.order_by(model.occurred_at.desc(), model.id.desc()).limit(1)
        )
        return None if row is None else _event(row)

    def delete_events(
        self,
        *,
        session_id: UUID,
        start: tuple[datetime, UUID],
        end: tuple[datetime, UUID] | None,
    ) -> int:
        model = BoardSearchShareQueryEventModel
        occurred_at, event_id = start
        statement = delete(model).where(
            model.session_id == session_id,
            or_(
                model.occurred_at > occurred_at,
                and_(model.occurred_at == occurred_at, model.id >= event_id),
            ),
        )
        if end is not None:
            statement = statement.where(_key_before(end))
        try:
            deleted = len(self._session.execute(statement.returning(model.id)).all())
            self._session.commit()
        except BaseException:
            self._session.rollback()
            raise
        return deleted


def _key_after(key: tuple[datetime, UUID]) -> Any:
    model = BoardSearchShareQueryEventModel
    occurred_at, event_id = key
    return or_(
        model.occurred_at > occurred_at,
        and_(model.occurred_at == occurred_at, model.id > event_id),
    )


def _key_before(key: tuple[datetime, UUID]) -> Any:
    model = BoardSearchShareQueryEventModel
    occurred_at, event_id = key
    return or_(
        model.occurred_at < occurred_at,
        and_(model.occurred_at == occurred_at, model.id < event_id),
    )


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
