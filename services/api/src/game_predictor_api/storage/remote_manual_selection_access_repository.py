"""Transactional access persistence for remote manual image selection."""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from datetime import datetime
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessRecord,
    RemoteManualSelectionAccessRepository,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
)
from game_predictor_api.storage.models import RemoteManualSelectionSessionModel
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionSessionSecrets,
    SqlAlchemyRemoteManualSelectionRepository,
)


class SqlAlchemyRemoteManualSelectionAccessRepository(RemoteManualSelectionAccessRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord:
        SqlAlchemyRemoteManualSelectionRepository(self._session).add_session(
            record.session,
            base_binding_id=record.base_binding_id,
            host_base_path=record.host_base_path,
            display_name=record.display_name,
            secrets=RemoteManualSelectionSessionSecrets(
                code_salt=record.code_salt,
                code_hash=record.code_hash,
                token_hash=record.token_hash,
                token_expires_at=record.token_expires_at,
            ),
        )
        persisted = self.get_access_session(record.session.id)
        if persisted is None:
            raise RuntimeError("Remote manual selection session disappeared after insert.")
        return persisted

    def get_access_session(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None:
        record = self._session.get(RemoteManualSelectionSessionModel, session_id)
        return None if record is None or record.code_salt is None else _from_record(record)

    def get_access_session_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None:
        record = self._session.scalar(
            select(RemoteManualSelectionSessionModel)
            .where(RemoteManualSelectionSessionModel.id == session_id)
            .with_for_update()
        )
        return None if record is None or record.code_salt is None else _from_record(record)

    def find_access_session_by_token_hash(
        self,
        token_hash: bytes,
    ) -> RemoteManualSelectionAccessRecord | None:
        records = tuple(
            self._session.scalars(
                select(RemoteManualSelectionSessionModel)
                .where(RemoteManualSelectionSessionModel.token_hash == token_hash)
                .limit(2)
            )
        )
        # A duplicate hash is cryptographically implausible, but fail closed if
        # corrupted legacy data ever violates the logical one-token invariant.
        return _from_record(records[0]) if len(records) == 1 else None

    def save_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord:
        persisted = self._session.get(RemoteManualSelectionSessionModel, record.session.id)
        if persisted is None:
            raise RuntimeError("Remote manual selection session disappeared.")
        persisted.status = record.session.status.value
        persisted.revision = record.session.revision
        persisted.updated_at = record.session.updated_at
        persisted.failed_attempts = record.failed_attempts
        persisted.locked_at = record.locked_at
        persisted.revoked_at = record.revoked_at
        persisted.token_hash = record.token_hash
        persisted.token_expires_at = record.token_expires_at
        persisted.writer_client_instance_id = record.writer_client_instance_id
        persisted.writer_lease_token = record.writer_lease_token
        persisted.writer_lease_expires_at = record.writer_lease_expires_at
        self._session.flush()
        return _from_record(persisted)

    def list_access_sessions(
        self,
        *,
        limit: int,
    ) -> Sequence[RemoteManualSelectionAccessRecord]:
        return tuple(
            _from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionSessionModel)
                .where(
                    RemoteManualSelectionSessionModel.code_salt.is_not(None),
                    RemoteManualSelectionSessionModel.code_hash.is_not(None),
                )
                .order_by(
                    RemoteManualSelectionSessionModel.created_at.desc(),
                    RemoteManualSelectionSessionModel.id.desc(),
                )
                .limit(limit)
            )
        )

    def append_access_audit(
        self,
        *,
        session_id: UUID,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        SqlAlchemyRemoteManualSelectionRepository(self._session).append_audit_event(
            event_id=uuid4(),
            session_id=session_id,
            batch_id=None,
            event_type=event_type,
            actor=actor,
            outcome_code=outcome_code,
            payload=payload,
            created_at=created_at,
        )


class InMemoryRemoteManualSelectionAccessRepository(RemoteManualSelectionAccessRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self.records: dict[UUID, RemoteManualSelectionAccessRecord] = {}
        self.audit_events: list[dict[str, object]] = []

    def add_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord:
        with self._lock:
            if record.session.id in self.records:
                raise RuntimeError("Duplicate remote manual selection session.")
            self.records[record.session.id] = record
            return record

    def get_access_session(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None:
        with self._lock:
            return self.records.get(session_id)

    def get_access_session_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionAccessRecord | None:
        return self.get_access_session(session_id)

    def find_access_session_by_token_hash(
        self,
        token_hash: bytes,
    ) -> RemoteManualSelectionAccessRecord | None:
        with self._lock:
            matches = tuple(
                record
                for record in self.records.values()
                if record.token_hash is not None
                and hmac.compare_digest(record.token_hash, token_hash)
            )
            return matches[0] if len(matches) == 1 else None

    def save_access_session(
        self,
        record: RemoteManualSelectionAccessRecord,
    ) -> RemoteManualSelectionAccessRecord:
        with self._lock:
            if record.session.id not in self.records:
                raise RuntimeError("Remote manual selection session disappeared.")
            self.records[record.session.id] = record
            return record

    def list_access_sessions(
        self,
        *,
        limit: int,
    ) -> Sequence[RemoteManualSelectionAccessRecord]:
        with self._lock:
            return tuple(
                sorted(
                    self.records.values(),
                    key=lambda record: (record.session.created_at, record.session.id),
                    reverse=True,
                )[:limit]
            )

    def append_access_audit(
        self,
        *,
        session_id: UUID,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        forbidden = {"code", "token", "path", "salt", "secret", "leaseToken"}
        if any(fragment.casefold() in str(payload).casefold() for fragment in forbidden):
            raise RuntimeError("Sensitive access audit payload.")
        with self._lock:
            self.audit_events.append(
                {
                    "sessionId": session_id,
                    "eventType": event_type,
                    "actor": actor,
                    "outcomeCode": outcome_code,
                    "payload": dict(payload),
                    "createdAt": created_at,
                }
            )


def _from_record(record: RemoteManualSelectionSessionModel) -> RemoteManualSelectionAccessRecord:
    if record.code_salt is None or record.code_hash is None:
        raise RuntimeError("Remote manual selection access credentials are missing.")
    return RemoteManualSelectionAccessRecord(
        session=RemoteManualSelectionSessionV1(
            id=record.id,
            status=RemoteManualSelectionSessionStatus(record.status),
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
        ),
        base_binding_id=record.base_binding_id,
        host_base_path=record.host_base_path,
        display_name=record.display_name,
        code_salt=record.code_salt,
        code_hash=record.code_hash,
        failed_attempts=record.failed_attempts,
        locked_at=record.locked_at,
        revoked_at=record.revoked_at,
        token_hash=record.token_hash,
        token_expires_at=record.token_expires_at,
        writer_client_instance_id=record.writer_client_instance_id,
        writer_lease_token=record.writer_lease_token,
        writer_lease_expires_at=record.writer_lease_expires_at,
    )


__all__ = [
    "InMemoryRemoteManualSelectionAccessRepository",
    "SqlAlchemyRemoteManualSelectionAccessRepository",
]
