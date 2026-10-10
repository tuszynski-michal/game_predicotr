"""Persistence for online board-search share sessions (D-471)."""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareRecord,
    BoardSearchShareRepository,
)
from game_predictor_api.domain.board_search_shares import BoardSearchShareAuditEventType
from game_predictor_api.storage.models import (
    BoardSearchShareAuditEventModel,
    BoardSearchShareSessionModel,
)

# Serialises the "at most N active sessions" check with the insert that
# follows it; transaction-scoped, released on commit or rollback.
_ACTIVE_SESSION_LOCK_KEY = 0x6273735F6C696D  # "bss_lim"

# Audit payloads describe counts and lifetimes only; a secret-looking key is
# a programming error, never data to store.
_FORBIDDEN_AUDIT_KEY_FRAGMENTS = ("code", "token", "salt", "hash", "secret", "password")


def validate_board_search_share_audit_payload(payload: dict[str, object]) -> None:
    for key, value in payload.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_AUDIT_KEY_FRAGMENTS):
            raise ValueError(f"Share audit payload key {key!r} looks like a secret.")
        if not isinstance(value, int | str | bool):
            raise ValueError(f"Share audit payload value for {key!r} must be a scalar.")


class SqlAlchemyBoardSearchShareRepository(BoardSearchShareRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord:
        self._session.add(
            BoardSearchShareSessionModel(
                id=record.id,
                game_id=record.game_id,
                label=record.label,
                code_salt=record.code_salt,
                code_hash=record.code_hash,
                failed_attempts=record.failed_attempts,
                locked_at=record.locked_at,
                revoked_at=record.revoked_at,
                token_hash=record.token_hash,
                token_expires_at=record.token_expires_at,
                last_unlocked_at=record.last_unlocked_at,
                created_at=record.created_at,
                expires_at=record.expires_at,
            )
        )
        self._session.flush()
        persisted = self._session.get(BoardSearchShareSessionModel, record.id)
        if persisted is None:
            raise RuntimeError("Board-search share session disappeared after insert.")
        return _from_model(persisted)

    def get_session(self, session_id: UUID) -> BoardSearchShareRecord | None:
        model = self._session.get(BoardSearchShareSessionModel, session_id)
        return None if model is None else _from_model(model)

    def get_session_for_update(self, session_id: UUID) -> BoardSearchShareRecord | None:
        model = self._session.scalar(
            select(BoardSearchShareSessionModel)
            .where(BoardSearchShareSessionModel.id == session_id)
            .with_for_update()
        )
        return None if model is None else _from_model(model)

    def find_session_by_token_hash(self, token_hash: bytes) -> BoardSearchShareRecord | None:
        models = tuple(
            self._session.scalars(
                select(BoardSearchShareSessionModel)
                .where(BoardSearchShareSessionModel.token_hash == token_hash)
                .limit(2)
            )
        )
        # The unique index makes a duplicate impossible; fail closed anyway.
        return _from_model(models[0]) if len(models) == 1 else None

    def save_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord:
        model = self._session.get(BoardSearchShareSessionModel, record.id)
        if model is None:
            raise RuntimeError("Board-search share session disappeared.")
        model.failed_attempts = record.failed_attempts
        model.locked_at = record.locked_at
        model.revoked_at = record.revoked_at
        model.token_hash = record.token_hash
        model.token_expires_at = record.token_expires_at
        model.last_unlocked_at = record.last_unlocked_at
        self._session.flush()
        return _from_model(model)

    def list_sessions(
        self,
        *,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[BoardSearchShareRecord]:
        statement = select(BoardSearchShareSessionModel)
        if game_id is not None:
            statement = statement.where(BoardSearchShareSessionModel.game_id == game_id)
        statement = statement.order_by(
            BoardSearchShareSessionModel.created_at.desc(),
            BoardSearchShareSessionModel.id.desc(),
        ).limit(limit)
        return tuple(_from_model(model) for model in self._session.scalars(statement))

    def count_active_sessions(self, now: datetime) -> int:
        count = self._session.scalar(
            select(func.count(BoardSearchShareSessionModel.id)).where(
                BoardSearchShareSessionModel.revoked_at.is_(None),
                BoardSearchShareSessionModel.locked_at.is_(None),
                BoardSearchShareSessionModel.expires_at > now,
            )
        )
        return int(count or 0)

    def count_active_sessions_locked(self, now: datetime) -> int:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ACTIVE_SESSION_LOCK_KEY}
        )
        return self.count_active_sessions(now)

    def append_audit_event(
        self,
        *,
        session_id: UUID,
        event_type: BoardSearchShareAuditEventType,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        validate_board_search_share_audit_payload(payload)
        self._session.add(
            BoardSearchShareAuditEventModel(
                id=uuid4(),
                session_id=session_id,
                event_type=event_type.value,
                outcome_code=outcome_code,
                payload=dict(payload),
                created_at=created_at,
            )
        )
        self._session.flush()


class InMemoryBoardSearchShareRepository(BoardSearchShareRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self.records: dict[UUID, BoardSearchShareRecord] = {}
        self.audit_events: list[dict[str, object]] = []

    def add_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord:
        with self._lock:
            if record.id in self.records:
                raise RuntimeError("Duplicate board-search share session.")
            self.records[record.id] = record
            return record

    def get_session(self, session_id: UUID) -> BoardSearchShareRecord | None:
        with self._lock:
            return self.records.get(session_id)

    def get_session_for_update(self, session_id: UUID) -> BoardSearchShareRecord | None:
        return self.get_session(session_id)

    def find_session_by_token_hash(self, token_hash: bytes) -> BoardSearchShareRecord | None:
        with self._lock:
            matches = tuple(
                record
                for record in self.records.values()
                if record.token_hash is not None
                and hmac.compare_digest(record.token_hash, token_hash)
            )
            return matches[0] if len(matches) == 1 else None

    def save_session(self, record: BoardSearchShareRecord) -> BoardSearchShareRecord:
        with self._lock:
            if record.id not in self.records:
                raise RuntimeError("Board-search share session disappeared.")
            self.records[record.id] = record
            return record

    def list_sessions(
        self,
        *,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[BoardSearchShareRecord]:
        with self._lock:
            records = [
                record
                for record in self.records.values()
                if game_id is None or record.game_id == game_id
            ]
            records.sort(key=lambda record: (record.created_at, record.id), reverse=True)
            return tuple(records[:limit])

    def count_active_sessions_locked(self, now: datetime) -> int:
        return self.count_active_sessions(now)

    def count_active_sessions(self, now: datetime) -> int:
        with self._lock:
            return sum(
                1
                for record in self.records.values()
                if record.revoked_at is None
                and record.locked_at is None
                and record.expires_at > now
            )

    def append_audit_event(
        self,
        *,
        session_id: UUID,
        event_type: BoardSearchShareAuditEventType,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        validate_board_search_share_audit_payload(payload)
        with self._lock:
            self.audit_events.append(
                {
                    "sessionId": session_id,
                    "eventType": event_type.value,
                    "outcomeCode": outcome_code,
                    "payload": dict(payload),
                    "createdAt": created_at,
                }
            )


def _from_model(model: BoardSearchShareSessionModel) -> BoardSearchShareRecord:
    return BoardSearchShareRecord(
        id=model.id,
        game_id=model.game_id,
        label=model.label,
        code_salt=model.code_salt,
        code_hash=model.code_hash,
        failed_attempts=model.failed_attempts,
        locked_at=model.locked_at,
        revoked_at=model.revoked_at,
        token_hash=model.token_hash,
        token_expires_at=model.token_expires_at,
        last_unlocked_at=model.last_unlocked_at,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )


__all__ = [
    "InMemoryBoardSearchShareRepository",
    "SqlAlchemyBoardSearchShareRepository",
    "validate_board_search_share_audit_payload",
]
