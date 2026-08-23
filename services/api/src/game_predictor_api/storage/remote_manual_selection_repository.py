"""Transactional persistence for remote manual image-selection contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionError,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionHostActionType,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionOperationApplication,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationStatus,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
    apply_remote_manual_selection_operation,
)
from game_predictor_api.storage.models import (
    RemoteManualSelectionAuditEventModel,
    RemoteManualSelectionBatchModel,
    RemoteManualSelectionCollectionModel,
    RemoteManualSelectionFileModel,
    RemoteManualSelectionHostActionModel,
    RemoteManualSelectionOperationModel,
    RemoteManualSelectionSessionModel,
    RemoteManualSelectionTransferModel,
)


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionHostBinding:
    """Host-only mapping; this type must never be used as a public DTO."""

    session_id: UUID
    base_binding_id: UUID
    host_base_path: str
    display_name: str


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionSessionSecrets:
    code_salt: bytes | None = None
    code_hash: bytes | None = None
    token_hash: bytes | None = None
    token_expires_at: datetime | None = None


class SqlAlchemyRemoteManualSelectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_session(
        self,
        value: RemoteManualSelectionSessionV1,
        *,
        base_binding_id: UUID,
        host_base_path: str,
        display_name: str,
        secrets: RemoteManualSelectionSessionSecrets | None = None,
    ) -> RemoteManualSelectionSessionV1:
        secret_values = secrets or RemoteManualSelectionSessionSecrets()
        record = RemoteManualSelectionSessionModel(
            id=value.id,
            base_binding_id=base_binding_id,
            host_base_path=host_base_path,
            display_name=display_name,
            status=value.status.value,
            revision=value.revision,
            code_salt=secret_values.code_salt,
            code_hash=secret_values.code_hash,
            token_hash=secret_values.token_hash,
            token_expires_at=secret_values.token_expires_at,
            failed_attempts=0,
            created_at=value.created_at,
            updated_at=value.updated_at,
            expires_at=value.expires_at,
        )
        self._persist(record)
        return _session_from_record(record)

    def get_session(self, session_id: UUID) -> RemoteManualSelectionSessionV1 | None:
        record = self._session.get(RemoteManualSelectionSessionModel, session_id)
        return None if record is None else _session_from_record(record)

    def get_host_binding_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionHostBinding | None:
        record = self._session.scalar(
            select(RemoteManualSelectionSessionModel)
            .where(RemoteManualSelectionSessionModel.id == session_id)
            .with_for_update()
        )
        return None if record is None else _host_binding_from_record(record)

    def add_collection(
        self,
        value: RemoteManualSelectionCollectionV1,
    ) -> RemoteManualSelectionCollectionV1:
        record = RemoteManualSelectionCollectionModel(
            id=value.id,
            session_id=value.session_id,
            name=value.name,
            normalized_name=value.normalized_name,
            status=value.status.value,
            revision=value.revision,
        )
        self._persist(record)
        return _collection_from_record(record)

    def get_collection(
        self,
        collection_id: UUID,
    ) -> RemoteManualSelectionCollectionV1 | None:
        record = self._session.get(RemoteManualSelectionCollectionModel, collection_id)
        return None if record is None else _collection_from_record(record)

    def add_batch(
        self,
        value: RemoteManualSelectionBatchV1,
        *,
        base_binding_id: UUID,
        normalized_collection_name: str,
        normalized_batch_name: str,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchV1:
        self._lock_base_mapping(
            base_binding_id,
            normalized_collection_name,
            normalized_batch_name,
        )
        record = RemoteManualSelectionBatchModel(
            id=value.id,
            session_id=value.session_id,
            collection_id=value.collection_id,
            base_binding_id=base_binding_id,
            normalized_collection_name=normalized_collection_name,
            name=value.name,
            normalized_name=normalized_batch_name,
            source_manifest_checksum_sha256=value.source_manifest_checksum_sha256,
            first_layout=value.first_layout,
            direction=value.direction.value,
            cursor_index=value.cursor_index,
            status=value.status.value,
            server_revision=value.server_revision,
            last_client_sequence=value.last_client_sequence,
            total_file_count=total_file_count,
            selected_file_count=0,
            transferred_file_count=0,
        )
        self._persist(record)
        return _batch_from_record(record)

    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None:
        record = self._session.get(RemoteManualSelectionBatchModel, batch_id)
        return None if record is None else _batch_from_record(record)

    def add_files(
        self,
        values: Sequence[RemoteManualSelectionFileV1],
    ) -> tuple[RemoteManualSelectionFileV1, ...]:
        records = [_file_record_from_domain(value) for value in values]
        if not records:
            return ()
        batch_ids = {record.batch_id for record in records}
        if len(batch_ids) != 1:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "Files added together must belong to one batch.",
            )
        try:
            with self._session.begin_nested():
                self._session.add_all(records)
                self._session.flush()
        except IntegrityError as error:
            raise _map_integrity_error(error) from error
        return tuple(_file_from_record(record) for record in records)

    def get_file(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
    ) -> RemoteManualSelectionFileV1 | None:
        record = self._session.scalar(
            select(RemoteManualSelectionFileModel).where(
                RemoteManualSelectionFileModel.batch_id == batch_id,
                RemoteManualSelectionFileModel.id == file_id,
            )
        )
        return None if record is None else _file_from_record(record)

    def apply_operation(
        self,
        command: RemoteManualSelectionOperationCommandV1,
    ) -> RemoteManualSelectionOperationApplication:
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(
                RemoteManualSelectionBatchModel.id == command.batch_id,
                RemoteManualSelectionBatchModel.session_id == command.session_id,
            )
            .with_for_update()
        )
        if batch_record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The batch does not belong to the remote selection session.",
            )
        existing_record = self._session.get(
            RemoteManualSelectionOperationModel,
            command.operation_id,
        )
        file_record = self._locked_file(command)
        existing = None if existing_record is None else _operation_from_record(existing_record)
        application = apply_remote_manual_selection_operation(
            _batch_from_record(batch_record),
            None if file_record is None else _file_from_record(file_record),
            command,
            existing_operation=existing,
        )
        if application.exact_retry:
            return application

        try:
            with self._session.begin_nested():
                batch_record.server_revision = application.batch.server_revision
                batch_record.last_client_sequence = application.batch.last_client_sequence
                batch_record.cursor_index = application.batch.cursor_index
                batch_record.updated_at = func.now()
                if file_record is not None and application.file is not None:
                    was_selected = file_record.desired_selected
                    _copy_file_state(file_record, application.file)
                    file_record.last_server_revision = application.batch.server_revision
                    file_record.updated_at = func.now()
                    if was_selected != application.file.desired_selected:
                        batch_record.selected_file_count += (
                            1 if application.file.desired_selected else -1
                        )
                self._session.add(_operation_record_from_domain(application.operation))
                self._session.flush()
        except IntegrityError as error:
            raise _map_integrity_error(error) from error
        return application

    def list_file_delta(
        self,
        *,
        batch_id: UUID,
        after_revision: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionFileV1, ...]:
        _require_page(limit)
        return tuple(
            _file_from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionFileModel)
                .where(
                    RemoteManualSelectionFileModel.batch_id == batch_id,
                    RemoteManualSelectionFileModel.last_server_revision > after_revision,
                )
                .order_by(
                    RemoteManualSelectionFileModel.last_server_revision,
                    RemoteManualSelectionFileModel.source_index,
                    RemoteManualSelectionFileModel.id,
                )
                .limit(limit)
            )
        )

    def list_operations_after_sequence(
        self,
        *,
        batch_id: UUID,
        after_client_sequence: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionOperationV1, ...]:
        _require_page(limit)
        return tuple(
            _operation_from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionOperationModel)
                .where(
                    RemoteManualSelectionOperationModel.batch_id == batch_id,
                    RemoteManualSelectionOperationModel.client_sequence > after_client_sequence,
                )
                .order_by(
                    RemoteManualSelectionOperationModel.client_sequence,
                    RemoteManualSelectionOperationModel.id,
                )
                .limit(limit)
            )
        )

    def add_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None = None,
        retry_at: datetime | None = None,
    ) -> RemoteManualSelectionTransferV1:
        record = RemoteManualSelectionTransferModel(
            id=value.id,
            session_id=value.session_id,
            batch_id=value.batch_id,
            file_id=value.file_id,
            generation=value.generation,
            attempt=value.attempt,
            declared_bytes=value.declared_bytes,
            received_bytes=value.received_bytes,
            status=value.status.value,
            declared_checksum_sha256=value.declared_checksum_sha256,
            verified_checksum_sha256=value.verified_checksum_sha256,
            temp_relative_path=temp_relative_path,
            retry_at=retry_at,
        )
        self._persist(record)
        return _transfer_from_record(record)

    def add_host_action(
        self,
        value: RemoteManualSelectionHostActionV1,
        *,
        lease_owner: str | None = None,
        lease_token: UUID | None = None,
        lease_expires_at: datetime | None = None,
        next_attempt_at: datetime | None = None,
    ) -> RemoteManualSelectionHostActionV1:
        record = RemoteManualSelectionHostActionModel(
            id=value.id,
            session_id=value.session_id,
            batch_id=value.batch_id,
            file_id=value.file_id,
            transfer_id=value.transfer_id,
            generation=value.generation,
            action_type=value.action_type.value,
            status=value.status.value,
            attempt=value.attempt,
            lease_owner=lease_owner,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            next_attempt_at=next_attempt_at,
        )
        self._persist(record)
        return _host_action_from_record(record)

    def append_audit_event(
        self,
        *,
        event_id: UUID,
        session_id: UUID,
        batch_id: UUID | None,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> UUID:
        _reject_sensitive_audit_keys(payload)
        record = RemoteManualSelectionAuditEventModel(
            id=event_id,
            session_id=session_id,
            batch_id=batch_id,
            event_type=event_type,
            actor=actor,
            outcome_code=outcome_code,
            payload=payload,
            created_at=created_at,
        )
        self._persist(record)
        return event_id

    def _locked_file(
        self,
        command: RemoteManualSelectionOperationCommandV1,
    ) -> RemoteManualSelectionFileModel | None:
        if command.file_id is None:
            return None
        record = cast(
            RemoteManualSelectionFileModel | None,
            self._session.scalar(
                select(RemoteManualSelectionFileModel)
                .where(
                    RemoteManualSelectionFileModel.id == command.file_id,
                    RemoteManualSelectionFileModel.batch_id == command.batch_id,
                    RemoteManualSelectionFileModel.session_id == command.session_id,
                )
                .with_for_update()
            ),
        )
        if record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The file does not belong to the remote selection scope.",
            )
        return record

    def _lock_base_mapping(
        self,
        base_binding_id: UUID,
        normalized_collection_name: str,
        normalized_batch_name: str,
    ) -> None:
        payload = (
            f"{base_binding_id}\0{normalized_collection_name}\0{normalized_batch_name}"
        ).encode()
        lock_key = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=True)
        self._session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def _persist(self, record: object) -> None:
        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise _map_integrity_error(error) from error


class InMemoryRemoteManualSelectionRepository:
    """Deterministic parity double for domain and application tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.sessions: dict[UUID, RemoteManualSelectionSessionV1] = {}
        self.bindings: dict[UUID, RemoteManualSelectionHostBinding] = {}
        self.collections: dict[UUID, RemoteManualSelectionCollectionV1] = {}
        self.batches: dict[UUID, RemoteManualSelectionBatchV1] = {}
        self.files: dict[UUID, RemoteManualSelectionFileV1] = {}
        self.file_revisions: dict[UUID, int] = {}
        self.operations: dict[UUID, RemoteManualSelectionOperationV1] = {}
        self.base_mappings: set[tuple[UUID, str, str]] = set()
        self.transfers: dict[UUID, RemoteManualSelectionTransferV1] = {}
        self.host_actions: dict[UUID, RemoteManualSelectionHostActionV1] = {}
        self.audit_event_ids: set[UUID] = set()

    def add_session(
        self,
        value: RemoteManualSelectionSessionV1,
        *,
        base_binding_id: UUID,
        host_base_path: str,
        display_name: str,
        secrets: RemoteManualSelectionSessionSecrets | None = None,
    ) -> RemoteManualSelectionSessionV1:
        del secrets
        with self._lock:
            if value.id in self.sessions:
                raise _persistence_conflict()
            self.sessions[value.id] = value
            self.bindings[value.id] = RemoteManualSelectionHostBinding(
                value.id,
                base_binding_id,
                host_base_path,
                display_name,
            )
            return value

    def get_session(self, session_id: UUID) -> RemoteManualSelectionSessionV1 | None:
        return self.sessions.get(session_id)

    def get_host_binding_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionHostBinding | None:
        return self.bindings.get(session_id)

    def add_collection(
        self,
        value: RemoteManualSelectionCollectionV1,
    ) -> RemoteManualSelectionCollectionV1:
        with self._lock:
            if value.session_id not in self.sessions or any(
                item.session_id == value.session_id
                and item.normalized_name == value.normalized_name
                for item in self.collections.values()
            ):
                raise _persistence_conflict()
            self.collections[value.id] = value
            return value

    def get_collection(
        self,
        collection_id: UUID,
    ) -> RemoteManualSelectionCollectionV1 | None:
        return self.collections.get(collection_id)

    def add_batch(
        self,
        value: RemoteManualSelectionBatchV1,
        *,
        base_binding_id: UUID,
        normalized_collection_name: str,
        normalized_batch_name: str,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchV1:
        del total_file_count
        mapping = (base_binding_id, normalized_collection_name, normalized_batch_name)
        with self._lock:
            collection = self.collections.get(value.collection_id)
            binding = self.bindings.get(value.session_id)
            if (
                collection is None
                or collection.session_id != value.session_id
                or collection.normalized_name != normalized_collection_name
                or binding is None
                or binding.base_binding_id != base_binding_id
            ):
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The batch scope is invalid.",
                )
            if mapping in self.base_mappings:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_BASE_MAPPING_CONFLICT",
                    "The host base mapping is already assigned.",
                )
            self.base_mappings.add(mapping)
            self.batches[value.id] = value
            return value

    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None:
        return self.batches.get(batch_id)

    def add_files(
        self,
        values: Sequence[RemoteManualSelectionFileV1],
    ) -> tuple[RemoteManualSelectionFileV1, ...]:
        with self._lock:
            for value in values:
                batch = self.batches.get(value.batch_id)
                if batch is None or batch.session_id != value.session_id:
                    raise RemoteManualSelectionError(
                        "REMOTE_SELECTION_SCOPE_MISMATCH",
                        "The file scope is invalid.",
                    )
                if value.id in self.files or any(
                    item.batch_id == value.batch_id
                    and (
                        item.source_index == value.source_index
                        or item.relative_path == value.relative_path
                    )
                    for item in self.files.values()
                ):
                    raise _persistence_conflict()
            for value in values:
                self.files[value.id] = value
                self.file_revisions[value.id] = 0
            return tuple(values)

    def get_file(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
    ) -> RemoteManualSelectionFileV1 | None:
        value = self.files.get(file_id)
        return value if value is not None and value.batch_id == batch_id else None

    def apply_operation(
        self,
        command: RemoteManualSelectionOperationCommandV1,
    ) -> RemoteManualSelectionOperationApplication:
        with self._lock:
            batch = self.batches.get(command.batch_id)
            if batch is None:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The batch scope is invalid.",
                )
            file = None if command.file_id is None else self.files.get(command.file_id)
            result = apply_remote_manual_selection_operation(
                batch,
                file,
                command,
                existing_operation=self.operations.get(command.operation_id),
            )
            if not result.exact_retry:
                duplicate_sequence = any(
                    operation.command.batch_id == command.batch_id
                    and operation.command.client_instance_id == command.client_instance_id
                    and operation.command.client_sequence == command.client_sequence
                    for operation in self.operations.values()
                )
                if duplicate_sequence:
                    raise RemoteManualSelectionConflictError(
                        "REMOTE_SELECTION_CLIENT_SEQUENCE_CONFLICT",
                        "The client sequence is already assigned.",
                    )
                self.batches[command.batch_id] = result.batch
                if result.file is not None:
                    self.files[result.file.id] = result.file
                    self.file_revisions[result.file.id] = result.batch.server_revision
                self.operations[command.operation_id] = result.operation
            return result

    def list_file_delta(
        self,
        *,
        batch_id: UUID,
        after_revision: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionFileV1, ...]:
        _require_page(limit)
        return tuple(
            sorted(
                (
                    value
                    for value in self.files.values()
                    if value.batch_id == batch_id and self.file_revisions[value.id] > after_revision
                ),
                key=lambda value: (
                    self.file_revisions[value.id],
                    value.source_index,
                    value.id,
                ),
            )[:limit]
        )

    def list_operations_after_sequence(
        self,
        *,
        batch_id: UUID,
        after_client_sequence: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionOperationV1, ...]:
        _require_page(limit)
        return tuple(
            sorted(
                (
                    value
                    for value in self.operations.values()
                    if value.command.batch_id == batch_id
                    and value.command.client_sequence > after_client_sequence
                ),
                key=lambda value: (value.command.client_sequence, value.command.operation_id),
            )[:limit]
        )

    def add_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None = None,
        retry_at: datetime | None = None,
    ) -> RemoteManualSelectionTransferV1:
        del temp_relative_path, retry_at
        with self._lock:
            file = self.files.get(value.file_id)
            if (
                file is None
                or file.session_id != value.session_id
                or file.batch_id != value.batch_id
            ):
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The transfer scope is invalid.",
                )
            if value.id in self.transfers or any(
                transfer.file_id == value.file_id
                and transfer.generation == value.generation
                and transfer.attempt == value.attempt
                for transfer in self.transfers.values()
            ):
                raise _persistence_conflict()
            self.transfers[value.id] = value
            return value

    def add_host_action(
        self,
        value: RemoteManualSelectionHostActionV1,
        *,
        lease_owner: str | None = None,
        lease_token: UUID | None = None,
        lease_expires_at: datetime | None = None,
        next_attempt_at: datetime | None = None,
    ) -> RemoteManualSelectionHostActionV1:
        del lease_owner, lease_token, lease_expires_at, next_attempt_at
        with self._lock:
            file = self.files.get(value.file_id)
            transfer = None if value.transfer_id is None else self.transfers.get(value.transfer_id)
            if (
                file is None
                or file.session_id != value.session_id
                or file.batch_id != value.batch_id
                or (
                    value.transfer_id is not None
                    and (
                        transfer is None
                        or transfer.file_id != value.file_id
                        or transfer.session_id != value.session_id
                        or transfer.batch_id != value.batch_id
                    )
                )
            ):
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The host action scope is invalid.",
                )
            active_statuses = {
                RemoteManualSelectionHostActionStatus.QUEUED,
                RemoteManualSelectionHostActionStatus.PROCESSING,
                RemoteManualSelectionHostActionStatus.RETRY,
            }
            if value.id in self.host_actions or (
                value.status in active_statuses
                and any(
                    action.file_id == value.file_id
                    and action.generation == value.generation
                    and action.action_type == value.action_type
                    and action.status in active_statuses
                    for action in self.host_actions.values()
                )
            ):
                raise _persistence_conflict()
            self.host_actions[value.id] = value
            return value

    def append_audit_event(
        self,
        *,
        event_id: UUID,
        session_id: UUID,
        batch_id: UUID | None,
        event_type: str,
        actor: str,
        outcome_code: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> UUID:
        del event_type, actor, outcome_code, created_at
        _reject_sensitive_audit_keys(payload)
        with self._lock:
            if session_id not in self.sessions or (
                batch_id is not None
                and (
                    batch_id not in self.batches or self.batches[batch_id].session_id != session_id
                )
            ):
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The audit scope is invalid.",
                )
            if event_id in self.audit_event_ids:
                raise _persistence_conflict()
            self.audit_event_ids.add(event_id)
            return event_id


def _session_from_record(
    record: RemoteManualSelectionSessionModel,
) -> RemoteManualSelectionSessionV1:
    return RemoteManualSelectionSessionV1(
        id=record.id,
        status=RemoteManualSelectionSessionStatus(record.status),
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        expires_at=record.expires_at,
    )


def _host_binding_from_record(
    record: RemoteManualSelectionSessionModel,
) -> RemoteManualSelectionHostBinding:
    return RemoteManualSelectionHostBinding(
        session_id=record.id,
        base_binding_id=record.base_binding_id,
        host_base_path=record.host_base_path,
        display_name=record.display_name,
    )


def _collection_from_record(
    record: RemoteManualSelectionCollectionModel,
) -> RemoteManualSelectionCollectionV1:
    return RemoteManualSelectionCollectionV1(
        id=record.id,
        session_id=record.session_id,
        name=record.name,
        normalized_name=record.normalized_name,
        status=RemoteManualSelectionCollectionStatus(record.status),
        revision=record.revision,
    )


def _batch_from_record(record: RemoteManualSelectionBatchModel) -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=record.id,
        session_id=record.session_id,
        collection_id=record.collection_id,
        name=record.name,
        source_manifest_checksum_sha256=record.source_manifest_checksum_sha256,
        first_layout=record.first_layout,
        direction=RemoteManualSelectionDirection(record.direction),
        cursor_index=record.cursor_index,
        status=RemoteManualSelectionBatchStatus(record.status),
        server_revision=record.server_revision,
        last_client_sequence=record.last_client_sequence,
    )


def _file_record_from_domain(value: RemoteManualSelectionFileV1) -> RemoteManualSelectionFileModel:
    return RemoteManualSelectionFileModel(
        id=value.id,
        session_id=value.session_id,
        batch_id=value.batch_id,
        source_index=value.source_index,
        relative_path=value.relative_path,
        size_bytes=value.size_bytes,
        last_modified_ms=value.last_modified_ms,
        mime_type=value.mime_type,
        desired_selected=value.desired_selected,
        selection_generation=value.selection_generation,
        status=value.status.value,
        range_start=value.range_start,
        range_end=value.range_end,
        output_name=value.output_name,
        host_checksum_sha256=value.host_checksum_sha256,
        last_server_revision=0,
    )


def _file_from_record(record: RemoteManualSelectionFileModel) -> RemoteManualSelectionFileV1:
    return RemoteManualSelectionFileV1(
        id=record.id,
        session_id=record.session_id,
        batch_id=record.batch_id,
        source_index=record.source_index,
        relative_path=record.relative_path,
        size_bytes=record.size_bytes,
        last_modified_ms=record.last_modified_ms,
        mime_type=record.mime_type,
        desired_selected=record.desired_selected,
        selection_generation=record.selection_generation,
        status=RemoteManualSelectionFileStatus(record.status),
        range_start=record.range_start,
        range_end=record.range_end,
        output_name=record.output_name,
        host_checksum_sha256=record.host_checksum_sha256,
    )


def _copy_file_state(
    record: RemoteManualSelectionFileModel,
    value: RemoteManualSelectionFileV1,
) -> None:
    record.desired_selected = value.desired_selected
    record.selection_generation = value.selection_generation
    record.status = value.status.value
    record.range_start = value.range_start
    record.range_end = value.range_end
    record.output_name = value.output_name
    record.host_checksum_sha256 = value.host_checksum_sha256


def _operation_record_from_domain(
    value: RemoteManualSelectionOperationV1,
) -> RemoteManualSelectionOperationModel:
    command = value.command
    return RemoteManualSelectionOperationModel(
        id=command.operation_id,
        session_id=command.session_id,
        batch_id=command.batch_id,
        file_id=command.file_id,
        client_instance_id=command.client_instance_id,
        client_sequence=command.client_sequence,
        expected_server_revision=command.expected_server_revision,
        operation_type=command.operation_type.value,
        selection_generation=command.selection_generation,
        range_start=command.range_start,
        range_end=command.range_end,
        recorded_at=command.recorded_at,
        image_path=command.image_path,
        source_index=command.source_index,
        image_checksum_sha256=command.image_checksum_sha256,
        output_name=command.output_name,
        visible_milliseconds=command.visible_milliseconds,
        decoded=command.decoded,
        target_operation_id=command.target_operation_id,
        command_checksum_sha256=value.command_checksum_sha256,
        status=value.status.value,
        applied_server_revision=value.applied_server_revision,
        outcome_code=value.outcome_code,
    )


def _operation_from_record(
    record: RemoteManualSelectionOperationModel,
) -> RemoteManualSelectionOperationV1:
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=record.id,
        session_id=record.session_id,
        batch_id=record.batch_id,
        client_instance_id=record.client_instance_id,
        client_sequence=record.client_sequence,
        expected_server_revision=record.expected_server_revision,
        operation_type=RemoteManualSelectionOperationType(record.operation_type),
        selection_generation=record.selection_generation,
        range_start=record.range_start,
        range_end=record.range_end,
        recorded_at=record.recorded_at,
        file_id=record.file_id,
        image_path=record.image_path,
        source_index=record.source_index,
        image_checksum_sha256=record.image_checksum_sha256,
        output_name=record.output_name,
        visible_milliseconds=record.visible_milliseconds,
        decoded=record.decoded,
        target_operation_id=record.target_operation_id,
    )
    return RemoteManualSelectionOperationV1(
        command=command,
        command_checksum_sha256=record.command_checksum_sha256,
        status=RemoteManualSelectionOperationStatus(record.status),
        applied_server_revision=record.applied_server_revision,
        outcome_code=record.outcome_code,
    )


def _transfer_from_record(
    record: RemoteManualSelectionTransferModel,
) -> RemoteManualSelectionTransferV1:
    return RemoteManualSelectionTransferV1(
        id=record.id,
        session_id=record.session_id,
        batch_id=record.batch_id,
        file_id=record.file_id,
        generation=record.generation,
        attempt=record.attempt,
        declared_bytes=record.declared_bytes,
        received_bytes=record.received_bytes,
        status=RemoteManualSelectionTransferStatus(record.status),
        declared_checksum_sha256=record.declared_checksum_sha256,
        verified_checksum_sha256=record.verified_checksum_sha256,
    )


def _host_action_from_record(
    record: RemoteManualSelectionHostActionModel,
) -> RemoteManualSelectionHostActionV1:
    return RemoteManualSelectionHostActionV1(
        id=record.id,
        session_id=record.session_id,
        batch_id=record.batch_id,
        file_id=record.file_id,
        transfer_id=record.transfer_id,
        generation=record.generation,
        action_type=RemoteManualSelectionHostActionType(record.action_type),
        status=RemoteManualSelectionHostActionStatus(record.status),
        attempt=record.attempt,
    )


def _map_integrity_error(error: IntegrityError) -> RemoteManualSelectionError:
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_rms_batches_base_mapping":
        return RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_BASE_MAPPING_CONFLICT",
            "The host base mapping is already assigned.",
        )
    if constraint == "uq_rms_operations_client_sequence":
        return RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_CLIENT_SEQUENCE_CONFLICT",
            "The client sequence is already assigned.",
        )
    if constraint in {"pk_rms_operations", "uq_rms_operations_scope"}:
        return RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_OPERATION_IDEMPOTENCY_CONFLICT",
            "The operationId already exists with incompatible content.",
        )
    if constraint is not None and (
        constraint.startswith("fk_rms_") or constraint.endswith("_scope")
    ):
        return RemoteManualSelectionError(
            "REMOTE_SELECTION_SCOPE_MISMATCH",
            "The persisted record references a foreign remote selection scope.",
            details={"constraint": constraint},
        )
    return _persistence_conflict(constraint=constraint)


def _persistence_conflict(*, constraint: str | None = None) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_PERSISTENCE_CONFLICT",
        "Remote manual selection state conflicts with persisted data.",
        details={} if constraint is None else {"constraint": constraint},
    )


def _require_page(limit: int) -> None:
    if limit < 1 or limit > 1000:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_PAGE_LIMIT_INVALID",
            "The page limit must be between 1 and 1000.",
        )


def _reject_sensitive_audit_keys(payload: dict[str, object]) -> None:
    forbidden = {
        "basepath",
        "hostbasepath",
        "temppath",
        "codesalt",
        "codehash",
        "tokenhash",
        "leasetoken",
    }
    if _payload_keys(payload) & forbidden:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_AUDIT_PAYLOAD_SENSITIVE",
            "Audit payload cannot contain secrets or host paths.",
        )


def _payload_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {key.replace("_", "").lower() for key in value} | {
            nested for child in value.values() for nested in _payload_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _payload_keys(child)}
    return set()


__all__ = [
    "InMemoryRemoteManualSelectionRepository",
    "RemoteManualSelectionHostBinding",
    "RemoteManualSelectionSessionSecrets",
    "SqlAlchemyRemoteManualSelectionRepository",
]
