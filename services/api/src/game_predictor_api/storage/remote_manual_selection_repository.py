"""Transactional persistence for remote manual image-selection contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

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
    RemoteSourceKind,
    RemoteSourceManifestEntryV1,
    apply_remote_manual_selection_operation,
    build_remote_source_manifest,
    transition_remote_file_status,
    transition_remote_host_action_status,
    transition_remote_transfer_status,
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


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionFileDelta:
    file: RemoteManualSelectionFileV1
    server_revision: int


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionSourceRegistration:
    batch: RemoteManualSelectionBatchV1
    files: tuple[RemoteManualSelectionFileV1, ...]
    created_count: int
    total_file_count: int


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionTransferRecord:
    transfer: RemoteManualSelectionTransferV1
    temp_relative_path: str | None


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionHostActionRecord:
    action: RemoteManualSelectionHostActionV1
    lease_owner: str | None
    lease_token: UUID | None
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    last_error_code: str | None


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionMaterializationContext:
    action: RemoteManualSelectionHostActionV1
    file: RemoteManualSelectionFileV1
    transfer: RemoteManualSelectionTransferV1
    verified_relative_path: str
    output_name: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionRemovalContext:
    action: RemoteManualSelectionHostActionV1
    file: RemoteManualSelectionFileV1
    transfer: RemoteManualSelectionTransferV1
    materialization_action_id: UUID
    materialized_generation: int
    output_name: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionFinalFileRecord:
    file: RemoteManualSelectionFileV1
    final_relative_path: str | None


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionFinalizationSnapshot:
    batch: RemoteManualSelectionBatchV1
    collection: RemoteManualSelectionCollectionV1
    files: tuple[RemoteManualSelectionFinalFileRecord, ...]
    operations: tuple[RemoteManualSelectionOperationV1, ...]
    transfers: tuple[RemoteManualSelectionTransferV1, ...]
    host_actions: tuple[RemoteManualSelectionHostActionV1, ...]
    total_file_count: int
    selected_file_count: int
    transferred_file_count: int
    final_manifest_checksum_sha256: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionRecoveryTransferCandidate:
    transfer: RemoteManualSelectionTransferV1
    file: RemoteManualSelectionFileV1
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionQueueSnapshot:
    pending_operation_count: int
    uploading_transfer_count: int
    pending_transfer_bytes: int
    materializing_action_count: int
    pending_host_action_count: int
    synced_file_count: int
    conflict_file_count: int
    recovery_findings: tuple[tuple[str, int], ...]


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

    def get_host_binding(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionHostBinding | None:
        record = self._session.get(RemoteManualSelectionSessionModel, session_id)
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

    def get_batch_total_file_count(self, batch_id: UUID) -> int | None:
        return self._session.scalar(
            select(RemoteManualSelectionBatchModel.total_file_count).where(
                RemoteManualSelectionBatchModel.id == batch_id
            )
        )

    def get_finalization_snapshot(
        self,
        *,
        batch_id: UUID,
        for_update: bool = False,
    ) -> RemoteManualSelectionFinalizationSnapshot | None:
        batch_query = select(RemoteManualSelectionBatchModel).where(
            RemoteManualSelectionBatchModel.id == batch_id
        )
        if for_update:
            batch_query = batch_query.with_for_update()
        batch_record = self._session.scalar(batch_query)
        if batch_record is None:
            return None
        collection_record = self._session.get(
            RemoteManualSelectionCollectionModel,
            batch_record.collection_id,
        )
        if collection_record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The finalization collection is unavailable.",
            )
        files = tuple(
            RemoteManualSelectionFinalFileRecord(
                file=_file_from_record(record),
                final_relative_path=record.final_relative_path,
            )
            for record in self._session.scalars(
                select(RemoteManualSelectionFileModel)
                .where(RemoteManualSelectionFileModel.batch_id == batch_id)
                .order_by(
                    RemoteManualSelectionFileModel.source_index,
                    RemoteManualSelectionFileModel.id,
                )
            )
        )
        operations = tuple(
            _operation_from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionOperationModel)
                .where(RemoteManualSelectionOperationModel.batch_id == batch_id)
                .order_by(
                    RemoteManualSelectionOperationModel.client_sequence,
                    RemoteManualSelectionOperationModel.id,
                )
            )
        )
        transfers = tuple(
            _transfer_from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionTransferModel)
                .where(RemoteManualSelectionTransferModel.batch_id == batch_id)
                .order_by(
                    RemoteManualSelectionTransferModel.created_at,
                    RemoteManualSelectionTransferModel.id,
                )
            )
        )
        host_actions = tuple(
            _host_action_from_record(record)
            for record in self._session.scalars(
                select(RemoteManualSelectionHostActionModel)
                .where(RemoteManualSelectionHostActionModel.batch_id == batch_id)
                .order_by(
                    RemoteManualSelectionHostActionModel.created_at,
                    RemoteManualSelectionHostActionModel.id,
                )
            )
        )
        return RemoteManualSelectionFinalizationSnapshot(
            batch=_batch_from_record(batch_record),
            collection=_collection_from_record(collection_record),
            files=files,
            operations=operations,
            transfers=transfers,
            host_actions=host_actions,
            total_file_count=batch_record.total_file_count,
            selected_file_count=batch_record.selected_file_count,
            transferred_file_count=batch_record.transferred_file_count,
            final_manifest_checksum_sha256=(batch_record.final_manifest_checksum_sha256),
            updated_at=batch_record.updated_at,
        )

    def mark_batch_finalizing(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        changed_at: datetime,
    ) -> RemoteManualSelectionBatchV1:
        record = self._locked_batch_for_finalization(
            session_id=session_id,
            batch_id=batch_id,
        )
        if record.server_revision != expected_server_revision:
            raise _finalization_revision_conflict(record.server_revision)
        if record.status == RemoteManualSelectionBatchStatus.ACTIVE.value:
            record.status = RemoteManualSelectionBatchStatus.FINALIZING.value
            record.updated_at = changed_at
            self._session.flush()
        elif record.status != RemoteManualSelectionBatchStatus.FINALIZING.value:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_BATCH_NOT_FINALIZABLE",
                "Only an active or finalizing batch can be finalized.",
            )
        return _batch_from_record(record)

    def complete_batch_finalization(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        final_manifest_checksum_sha256: str,
        completed_at: datetime,
        actor: str,
    ) -> RemoteManualSelectionFinalizationSnapshot:
        record = self._locked_batch_for_finalization(
            session_id=session_id,
            batch_id=batch_id,
        )
        if record.server_revision != expected_server_revision:
            raise _finalization_revision_conflict(record.server_revision)
        if record.status != RemoteManualSelectionBatchStatus.FINALIZING.value:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_BATCH_NOT_FINALIZING",
                "The batch must remain finalizing until every manifest is durable.",
            )
        record.status = RemoteManualSelectionBatchStatus.COMPLETED.value
        record.server_revision += 1
        record.final_manifest_checksum_sha256 = final_manifest_checksum_sha256
        record.updated_at = completed_at
        self._session.add(
            RemoteManualSelectionAuditEventModel(
                session_id=session_id,
                batch_id=batch_id,
                event_type="batch_finalized",
                actor=actor,
                outcome_code="REMOTE_SELECTION_BATCH_FINALIZED",
                payload={
                    "finalManifestChecksumSha256": final_manifest_checksum_sha256,
                    "serverRevision": record.server_revision,
                },
                created_at=completed_at,
            )
        )
        self._session.flush()
        snapshot = self.get_finalization_snapshot(batch_id=batch_id)
        assert snapshot is not None
        return snapshot

    def reopen_completed_batch(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        expected_final_manifest_checksum_sha256: str,
        reopened_at: datetime,
    ) -> RemoteManualSelectionFinalizationSnapshot:
        record = self._locked_batch_for_finalization(
            session_id=session_id,
            batch_id=batch_id,
        )
        if record.server_revision != expected_server_revision:
            raise _finalization_revision_conflict(record.server_revision)
        if (
            record.status != RemoteManualSelectionBatchStatus.COMPLETED.value
            or record.final_manifest_checksum_sha256 != expected_final_manifest_checksum_sha256
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_REOPEN_PRECONDITION_FAILED",
                "The completed batch checksum no longer matches the reopen command.",
            )
        record.status = RemoteManualSelectionBatchStatus.ACTIVE.value
        record.server_revision += 1
        record.final_manifest_checksum_sha256 = None
        record.updated_at = reopened_at
        self._session.add(
            RemoteManualSelectionAuditEventModel(
                session_id=session_id,
                batch_id=batch_id,
                event_type="batch_reopened",
                actor="local-owner",
                outcome_code="REMOTE_SELECTION_BATCH_REOPENED",
                payload={
                    "previousFinalManifestChecksumSha256": (
                        expected_final_manifest_checksum_sha256
                    ),
                    "serverRevision": record.server_revision,
                },
                created_at=reopened_at,
            )
        )
        self._session.flush()
        snapshot = self.get_finalization_snapshot(batch_id=batch_id)
        assert snapshot is not None
        return snapshot

    def _locked_batch_for_finalization(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
    ) -> RemoteManualSelectionBatchModel:
        record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(
                RemoteManualSelectionBatchModel.id == batch_id,
                RemoteManualSelectionBatchModel.session_id == session_id,
            )
            .with_for_update()
        )
        if record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The batch does not belong to the remote selection session.",
            )
        return record

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

    def get_operation(
        self,
        operation_id: UUID,
    ) -> RemoteManualSelectionOperationV1 | None:
        record = self._session.get(RemoteManualSelectionOperationModel, operation_id)
        return None if record is None else _operation_from_record(record)

    def get_applied_select_operation(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionOperationV1 | None:
        record = self._session.scalar(
            select(RemoteManualSelectionOperationModel)
            .where(
                RemoteManualSelectionOperationModel.batch_id == batch_id,
                RemoteManualSelectionOperationModel.file_id == file_id,
                RemoteManualSelectionOperationModel.selection_generation == generation,
                RemoteManualSelectionOperationModel.operation_type
                == RemoteManualSelectionOperationType.SELECT.value,
                RemoteManualSelectionOperationModel.status
                == RemoteManualSelectionOperationStatus.APPLIED.value,
            )
            .order_by(RemoteManualSelectionOperationModel.created_at.desc())
            .limit(1)
        )
        return None if record is None else _operation_from_record(record)

    def get_transfer_record(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
    ) -> RemoteManualSelectionTransferRecord | None:
        record = self._session.scalar(
            select(RemoteManualSelectionTransferModel).where(
                RemoteManualSelectionTransferModel.id == transfer_id,
                RemoteManualSelectionTransferModel.batch_id == batch_id,
                RemoteManualSelectionTransferModel.file_id == file_id,
            )
        )
        return None if record is None else _transfer_record_from_record(record)

    def get_verified_transfer_record(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionTransferRecord | None:
        record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(
                RemoteManualSelectionTransferModel.batch_id == batch_id,
                RemoteManualSelectionTransferModel.file_id == file_id,
                RemoteManualSelectionTransferModel.generation == generation,
                RemoteManualSelectionTransferModel.status.in_(
                    (
                        RemoteManualSelectionTransferStatus.VERIFIED.value,
                        RemoteManualSelectionTransferStatus.MATERIALIZED.value,
                    )
                ),
            )
            .order_by(RemoteManualSelectionTransferModel.attempt.desc())
            .limit(1)
        )
        return None if record is None else _transfer_record_from_record(record)

    def next_transfer_attempt(self, *, file_id: UUID, generation: int) -> int:
        current = self._session.scalar(
            select(func.max(RemoteManualSelectionTransferModel.attempt)).where(
                RemoteManualSelectionTransferModel.file_id == file_id,
                RemoteManualSelectionTransferModel.generation == generation,
            )
        )
        return int(current or 0) + 1

    def session_reserved_transfer_bytes(self, session_id: UUID) -> int:
        value = self._session.scalar(
            select(
                func.coalesce(func.sum(RemoteManualSelectionTransferModel.declared_bytes), 0)
            ).where(
                RemoteManualSelectionTransferModel.session_id == session_id,
                RemoteManualSelectionTransferModel.status.in_(
                    (
                        RemoteManualSelectionTransferStatus.UPLOADING.value,
                        RemoteManualSelectionTransferStatus.STORED_TEMP.value,
                        RemoteManualSelectionTransferStatus.VERIFIED.value,
                    )
                ),
            )
        )
        return int(value or 0)

    def update_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None,
    ) -> RemoteManualSelectionTransferV1:
        record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == value.id)
            .with_for_update()
        )
        if record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_TRANSFER_NOT_FOUND",
                "The remote selection transfer does not exist.",
            )
        current = RemoteManualSelectionTransferStatus(record.status)
        if current is not value.status:
            transition_remote_transfer_status(current, value.status)
        record.received_bytes = value.received_bytes
        record.status = value.status.value
        record.declared_checksum_sha256 = value.declared_checksum_sha256
        record.verified_checksum_sha256 = value.verified_checksum_sha256
        record.temp_relative_path = temp_relative_path
        self._session.flush()
        return _transfer_from_record(record)

    def cancel_failed_transfer_attempts(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        except_transfer_id: UUID,
    ) -> int:
        records = tuple(
            self._session.scalars(
                select(RemoteManualSelectionTransferModel)
                .where(
                    RemoteManualSelectionTransferModel.batch_id == batch_id,
                    RemoteManualSelectionTransferModel.file_id == file_id,
                    RemoteManualSelectionTransferModel.generation == generation,
                    RemoteManualSelectionTransferModel.id != except_transfer_id,
                    RemoteManualSelectionTransferModel.status
                    == RemoteManualSelectionTransferStatus.FAILED.value,
                )
                .with_for_update()
            )
        )
        for record in records:
            transition_remote_transfer_status(
                RemoteManualSelectionTransferStatus.FAILED,
                RemoteManualSelectionTransferStatus.CANCELLED,
            )
            record.status = RemoteManualSelectionTransferStatus.CANCELLED.value
            record.temp_relative_path = None
        self._session.flush()
        return len(records)

    def update_file_transfer_status(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        status: RemoteManualSelectionFileStatus,
        temp_relative_path: str | None = None,
        host_checksum_sha256: str | None = None,
    ) -> RemoteManualSelectionFileV1:
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(
                RemoteManualSelectionFileModel.batch_id == batch_id,
                RemoteManualSelectionFileModel.id == file_id,
            )
            .with_for_update()
        )
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == batch_id)
            .with_for_update()
        )
        if (
            file_record is None
            or batch_record is None
            or not file_record.desired_selected
            or file_record.selection_generation != generation
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_TRANSFER_GENERATION_CONFLICT",
                "The selected file generation changed during transfer.",
            )
        current = RemoteManualSelectionFileStatus(file_record.status)
        if current is not status:
            transition_remote_file_status(current, status)
        batch_record.server_revision += 1
        file_record.status = status.value
        file_record.temp_relative_path = temp_relative_path
        file_record.host_checksum_sha256 = host_checksum_sha256
        file_record.last_server_revision = batch_record.server_revision
        self._session.flush()
        return _file_from_record(file_record)

    def register_source_files(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        values: Sequence[RemoteManualSelectionFileV1],
        source_kind: RemoteSourceKind,
        complete: bool,
    ) -> RemoteManualSelectionSourceRegistration:
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(
                RemoteManualSelectionBatchModel.id == batch_id,
                RemoteManualSelectionBatchModel.session_id == session_id,
            )
            .with_for_update()
        )
        if batch_record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The batch does not belong to the remote selection session.",
            )
        existing_records = tuple(
            self._session.scalars(
                select(RemoteManualSelectionFileModel)
                .where(RemoteManualSelectionFileModel.batch_id == batch_id)
                .order_by(RemoteManualSelectionFileModel.source_index)
            )
        )
        by_id = {record.id: record for record in existing_records}
        by_index = {record.source_index: record for record in existing_records}
        by_path = {record.relative_path: record for record in existing_records}
        accepted: list[RemoteManualSelectionFileV1] = []
        new_records: list[RemoteManualSelectionFileModel] = []
        for value in values:
            if value.session_id != session_id or value.batch_id != batch_id:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "A source item does not belong to the remote selection scope.",
                )
            matches = {
                record.id: record
                for record in (
                    by_id.get(value.id),
                    by_index.get(value.source_index),
                    by_path.get(value.relative_path),
                )
                if record is not None
            }
            if matches:
                if len(matches) != 1:
                    raise _source_manifest_conflict()
                existing = _file_from_record(next(iter(matches.values())))
                if existing != value:
                    raise _source_manifest_conflict()
                accepted.append(existing)
                continue
            if batch_record.status == RemoteManualSelectionBatchStatus.ACTIVE.value:
                raise _source_manifest_immutable()
            record = _file_record_from_domain(value)
            new_records.append(record)
            by_id[record.id] = record
            by_index[record.source_index] = record
            by_path[record.relative_path] = record
            accepted.append(value)

        if len(existing_records) + len(new_records) > batch_record.total_file_count:
            raise _source_manifest_conflict()
        try:
            with self._session.begin_nested():
                self._session.add_all(new_records)
                self._session.flush()
        except IntegrityError as error:
            raise _map_integrity_error(error) from error

        all_records = tuple(
            self._session.scalars(
                select(RemoteManualSelectionFileModel)
                .where(RemoteManualSelectionFileModel.batch_id == batch_id)
                .order_by(RemoteManualSelectionFileModel.source_index)
            )
        )
        if complete:
            if len(all_records) != batch_record.total_file_count:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_SOURCE_MANIFEST_INCOMPLETE",
                    "The source manifest does not contain the declared number of files.",
                    details={
                        "actualFileCount": len(all_records),
                        "expectedFileCount": batch_record.total_file_count,
                    },
                )
            manifest = build_remote_source_manifest(
                tuple(
                    RemoteSourceManifestEntryV1(
                        ordinal=record.source_index,
                        relative_path=record.relative_path,
                        name=record.relative_path.rsplit("/", 1)[-1],
                        size_bytes=record.size_bytes,
                        last_modified_ms=record.last_modified_ms,
                        mime_type=record.mime_type,
                    )
                    for record in all_records
                ),
                source_kind=source_kind,
            )
            if manifest.manifest_checksum_sha256 != batch_record.source_manifest_checksum_sha256:
                raise _source_manifest_conflict()
            if batch_record.status == RemoteManualSelectionBatchStatus.INDEXING.value:
                batch_record.status = RemoteManualSelectionBatchStatus.ACTIVE.value
                batch_record.updated_at = func.now()
            elif batch_record.status != RemoteManualSelectionBatchStatus.ACTIVE.value:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_BATCH_NOT_INDEXING",
                    "The batch cannot accept source items in its current state.",
                )
        elif batch_record.status != RemoteManualSelectionBatchStatus.INDEXING.value:
            if not (
                batch_record.status == RemoteManualSelectionBatchStatus.ACTIVE.value
                and not new_records
            ):
                raise _source_manifest_immutable()
        self._session.flush()
        return RemoteManualSelectionSourceRegistration(
            batch=_batch_from_record(batch_record),
            files=tuple(accepted),
            created_count=len(new_records),
            total_file_count=len(all_records),
        )

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
        target_record = (
            None
            if command.target_operation_id is None
            else self._session.get(
                RemoteManualSelectionOperationModel,
                command.target_operation_id,
            )
        )
        target_operation = None if target_record is None else _operation_from_record(target_record)
        application = apply_remote_manual_selection_operation(
            _batch_from_record(batch_record),
            None if file_record is None else _file_from_record(file_record),
            command,
            existing_operation=existing,
            target_operation=target_operation,
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
                    was_transferred = file_record.final_relative_path is not None
                    _copy_file_state(file_record, application.file)
                    file_record.last_server_revision = application.batch.server_revision
                    file_record.updated_at = func.now()
                    if was_selected != application.file.desired_selected:
                        batch_record.selected_file_count += (
                            1 if application.file.desired_selected else -1
                        )
                        if (
                            was_transferred
                            and not application.file.desired_selected
                            and batch_record.transferred_file_count > 0
                        ):
                            batch_record.transferred_file_count -= 1
                    if command.operation_type in {
                        RemoteManualSelectionOperationType.DESELECT,
                        RemoteManualSelectionOperationType.UNDO,
                    }:
                        self._prepare_deselect(
                            file_record=file_record,
                            tombstone_generation=command.selection_generation,
                            applied_at=command.recorded_at,
                        )
                self._session.add(_operation_record_from_domain(application.operation))
                self._session.flush()
        except IntegrityError as error:
            raise _map_integrity_error(error) from error
        if file_record is not None and application.file is not None:
            application = replace(application, file=_file_from_record(file_record))
        return application

    def _prepare_deselect(
        self,
        *,
        file_record: RemoteManualSelectionFileModel,
        tombstone_generation: int,
        applied_at: datetime,
    ) -> None:
        cancelable = (
            RemoteManualSelectionTransferStatus.QUEUED.value,
            RemoteManualSelectionTransferStatus.UPLOADING.value,
            RemoteManualSelectionTransferStatus.STORED_TEMP.value,
            RemoteManualSelectionTransferStatus.VERIFIED.value,
            RemoteManualSelectionTransferStatus.FAILED.value,
            RemoteManualSelectionTransferStatus.RETRYING.value,
        )
        transfers = self._session.scalars(
            select(RemoteManualSelectionTransferModel)
            .where(
                RemoteManualSelectionTransferModel.file_id == file_record.id,
                RemoteManualSelectionTransferModel.generation < tombstone_generation,
            )
            .with_for_update()
        ).all()
        for transfer in transfers:
            if transfer.status in cancelable:
                transition_remote_transfer_status(
                    RemoteManualSelectionTransferStatus(transfer.status),
                    RemoteManualSelectionTransferStatus.CANCELLED,
                )
                transfer.status = RemoteManualSelectionTransferStatus.CANCELLED.value
                transfer.retry_at = None
                transfer.updated_at = func.now()

        active_statuses = (
            RemoteManualSelectionHostActionStatus.QUEUED.value,
            RemoteManualSelectionHostActionStatus.PROCESSING.value,
            RemoteManualSelectionHostActionStatus.RETRY.value,
        )
        materializations = self._session.scalars(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.file_id == file_record.id,
                RemoteManualSelectionHostActionModel.generation < tombstone_generation,
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.MATERIALIZE.value,
            )
            .order_by(
                RemoteManualSelectionHostActionModel.generation.desc(),
                RemoteManualSelectionHostActionModel.created_at.desc(),
                RemoteManualSelectionHostActionModel.id,
            )
            .with_for_update()
        ).all()
        materialization = next(
            (
                action
                for action in materializations
                if action.transfer_id is not None
                and next(
                    (
                        transfer
                        for transfer in transfers
                        if transfer.id == action.transfer_id
                        and transfer.verified_checksum_sha256 is not None
                    ),
                    None,
                )
                is not None
            ),
            None,
        )
        for action in materializations:
            if action.status in active_statuses:
                transition_remote_host_action_status(
                    RemoteManualSelectionHostActionStatus(action.status),
                    RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                action.status = RemoteManualSelectionHostActionStatus.SUPERSEDED.value
                _clear_action_lease(action, updated_at=applied_at)

        existing_remove = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.file_id == file_record.id,
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.REMOVE.value,
                RemoteManualSelectionHostActionModel.status.in_(active_statuses),
            )
            .order_by(RemoteManualSelectionHostActionModel.created_at)
            .limit(1)
        )
        if existing_remove is not None:
            file_record.status = RemoteManualSelectionFileStatus.DESELECT_PENDING.value
            return
        if materialization is None:
            file_record.status = RemoteManualSelectionFileStatus.REMOVED.value
            file_record.temp_relative_path = None
            file_record.final_relative_path = None
            return
        self._session.add(
            RemoteManualSelectionHostActionModel(
                id=uuid4(),
                session_id=file_record.session_id,
                batch_id=file_record.batch_id,
                file_id=file_record.id,
                transfer_id=materialization.transfer_id,
                generation=tombstone_generation,
                action_type=RemoteManualSelectionHostActionType.REMOVE.value,
                status=RemoteManualSelectionHostActionStatus.QUEUED.value,
                attempt=0,
            )
        )
        file_record.status = RemoteManualSelectionFileStatus.DESELECT_PENDING.value

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

    def list_file_delta_records(
        self,
        *,
        batch_id: UUID,
        after_revision: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionFileDelta, ...]:
        _require_page(limit)
        return tuple(
            RemoteManualSelectionFileDelta(
                file=_file_from_record(record),
                server_revision=record.last_server_revision,
            )
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

    def list_stale_transfer_candidates(
        self,
        *,
        stale_before: datetime,
        limit: int,
    ) -> tuple[RemoteManualSelectionRecoveryTransferCandidate, ...]:
        _require_page(limit)
        records = self._session.execute(
            select(RemoteManualSelectionTransferModel, RemoteManualSelectionFileModel)
            .join(
                RemoteManualSelectionFileModel,
                RemoteManualSelectionFileModel.id
                == RemoteManualSelectionTransferModel.file_id,
            )
            .where(
                RemoteManualSelectionTransferModel.status.in_(
                    (
                        RemoteManualSelectionTransferStatus.QUEUED.value,
                        RemoteManualSelectionTransferStatus.UPLOADING.value,
                        RemoteManualSelectionTransferStatus.STORED_TEMP.value,
                        RemoteManualSelectionTransferStatus.RETRYING.value,
                    )
                ),
                RemoteManualSelectionTransferModel.updated_at <= stale_before,
            )
            .order_by(
                RemoteManualSelectionTransferModel.updated_at,
                RemoteManualSelectionTransferModel.id,
            )
            .limit(limit)
        )
        return tuple(
            RemoteManualSelectionRecoveryTransferCandidate(
                transfer=_transfer_from_record(transfer),
                file=_file_from_record(file),
                updated_at=transfer.updated_at,
            )
            for transfer, file in records
        )

    def recover_verified_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        verified_relative_path: str,
        checksum_sha256: str,
        recovered_at: datetime,
    ) -> bool:
        transfer = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == candidate.transfer.id)
            .with_for_update()
        )
        file = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == candidate.file.id)
            .with_for_update()
        )
        batch = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == candidate.file.batch_id)
            .with_for_update()
        )
        if transfer is None or file is None or batch is None:
            return False
        if transfer.status in {
            RemoteManualSelectionTransferStatus.VERIFIED.value,
            RemoteManualSelectionTransferStatus.MATERIALIZED.value,
        }:
            return False
        if (
            transfer.updated_at != candidate.updated_at
            or transfer.generation != file.selection_generation
            or not file.desired_selected
            or checksum_sha256 != transfer.declared_checksum_sha256
        ):
            return False
        transfer.received_bytes = transfer.declared_bytes
        transfer.status = RemoteManualSelectionTransferStatus.VERIFIED.value
        transfer.verified_checksum_sha256 = checksum_sha256
        transfer.temp_relative_path = verified_relative_path
        transfer.retry_at = None
        transfer.updated_at = recovered_at
        batch.server_revision += 1
        batch.updated_at = recovered_at
        file.status = RemoteManualSelectionFileStatus.VERIFIED.value
        file.temp_relative_path = verified_relative_path
        file.host_checksum_sha256 = checksum_sha256
        file.last_server_revision = batch.server_revision
        file.updated_at = recovered_at
        self._session.flush()
        self.ensure_materialization_action(
            session_id=file.session_id,
            batch_id=file.batch_id,
            file_id=file.id,
            transfer_id=transfer.id,
            generation=transfer.generation,
        )
        return True

    def fail_stale_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        error_code: str,
        recovered_at: datetime,
    ) -> bool:
        transfer = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == candidate.transfer.id)
            .with_for_update()
        )
        file = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == candidate.file.id)
            .with_for_update()
        )
        batch = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == candidate.file.batch_id)
            .with_for_update()
        )
        if transfer is None or file is None or batch is None:
            return False
        if (
            transfer.updated_at != candidate.updated_at
            or transfer.status
            not in {
                RemoteManualSelectionTransferStatus.QUEUED.value,
                RemoteManualSelectionTransferStatus.UPLOADING.value,
                RemoteManualSelectionTransferStatus.STORED_TEMP.value,
                RemoteManualSelectionTransferStatus.RETRYING.value,
            }
        ):
            return False
        transfer.status = RemoteManualSelectionTransferStatus.FAILED.value
        transfer.retry_at = None
        transfer.updated_at = recovered_at
        if (
            file.desired_selected
            and file.selection_generation == transfer.generation
            and file.status
            in {
                RemoteManualSelectionFileStatus.UPLOAD_QUEUED.value,
                RemoteManualSelectionFileStatus.UPLOADING.value,
                RemoteManualSelectionFileStatus.STORED_TEMPORARILY.value,
                RemoteManualSelectionFileStatus.RETRYING.value,
            }
        ):
            batch.server_revision += 1
            batch.updated_at = recovered_at
            file.status = RemoteManualSelectionFileStatus.FAILED.value
            file.last_server_revision = batch.server_revision
            file.updated_at = recovered_at
        self.append_audit_event(
            event_id=uuid4(),
            session_id=transfer.session_id,
            batch_id=transfer.batch_id,
            event_type="transfer_recovery",
            actor="local-reconciler",
            outcome_code=error_code,
            payload={"generation": transfer.generation},
            created_at=recovered_at,
        )
        self._session.flush()
        return True

    def get_batch_queue_snapshot(
        self,
        *,
        batch_id: UUID,
        now: datetime,
        stale_before: datetime,
    ) -> RemoteManualSelectionQueueSnapshot:
        def count(model: Any, *conditions: Any) -> int:
            return int(
                self._session.scalar(select(func.count()).select_from(model).where(*conditions))
                or 0
            )

        pending_operation_count = count(
            RemoteManualSelectionOperationModel,
            RemoteManualSelectionOperationModel.batch_id == batch_id,
            RemoteManualSelectionOperationModel.status.in_(("queued", "sending", "retry")),
        )
        uploading_statuses = ("queued", "uploading", "stored_temp", "retrying")
        uploading_transfer_count = count(
            RemoteManualSelectionTransferModel,
            RemoteManualSelectionTransferModel.batch_id == batch_id,
            RemoteManualSelectionTransferModel.status.in_(uploading_statuses),
        )
        pending_transfer_bytes = int(
            self._session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            RemoteManualSelectionTransferModel.declared_bytes
                            - RemoteManualSelectionTransferModel.received_bytes
                        ),
                        0,
                    )
                ).where(
                    RemoteManualSelectionTransferModel.batch_id == batch_id,
                    RemoteManualSelectionTransferModel.status.in_(uploading_statuses),
                )
            )
            or 0
        )
        active_action_statuses = ("queued", "processing", "retry")
        materializing_action_count = count(
            RemoteManualSelectionHostActionModel,
            RemoteManualSelectionHostActionModel.batch_id == batch_id,
            RemoteManualSelectionHostActionModel.action_type == "materialize",
            RemoteManualSelectionHostActionModel.status.in_(active_action_statuses),
        )
        pending_host_action_count = count(
            RemoteManualSelectionHostActionModel,
            RemoteManualSelectionHostActionModel.batch_id == batch_id,
            RemoteManualSelectionHostActionModel.status.in_(active_action_statuses),
        )
        synced_file_count = count(
            RemoteManualSelectionFileModel,
            RemoteManualSelectionFileModel.batch_id == batch_id,
            RemoteManualSelectionFileModel.status == "synced",
        )
        conflict_file_count = count(
            RemoteManualSelectionFileModel,
            RemoteManualSelectionFileModel.batch_id == batch_id,
            RemoteManualSelectionFileModel.status == "failed",
        )
        findings: dict[str, int] = {}
        stale = count(
            RemoteManualSelectionTransferModel,
            RemoteManualSelectionTransferModel.batch_id == batch_id,
            RemoteManualSelectionTransferModel.status.in_(uploading_statuses),
            RemoteManualSelectionTransferModel.updated_at <= stale_before,
        )
        if stale:
            findings["REMOTE_SELECTION_STALE_TRANSFER"] = stale
        expired_actions = count(
            RemoteManualSelectionHostActionModel,
            RemoteManualSelectionHostActionModel.batch_id == batch_id,
            RemoteManualSelectionHostActionModel.status == "processing",
            RemoteManualSelectionHostActionModel.lease_expires_at <= now,
        )
        if expired_actions:
            findings["REMOTE_SELECTION_EXPIRED_HOST_ACTION_LEASE"] = expired_actions
        if conflict_file_count:
            findings["REMOTE_SELECTION_CONFLICT_REQUIRES_ATTENTION"] = conflict_file_count
        batch_status = self._session.scalar(
            select(RemoteManualSelectionBatchModel.status).where(
                RemoteManualSelectionBatchModel.id == batch_id
            )
        )
        if batch_status == RemoteManualSelectionBatchStatus.FINALIZING.value:
            findings["REMOTE_SELECTION_FINALIZATION_RETRY_REQUIRED"] = 1
        return RemoteManualSelectionQueueSnapshot(
            pending_operation_count=pending_operation_count,
            uploading_transfer_count=uploading_transfer_count,
            pending_transfer_bytes=pending_transfer_bytes,
            materializing_action_count=materializing_action_count,
            pending_host_action_count=pending_host_action_count,
            synced_file_count=synced_file_count,
            conflict_file_count=conflict_file_count,
            recovery_findings=tuple(sorted(findings.items())),
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

    def ensure_materialization_action(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionHostActionV1:
        existing = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.session_id == session_id,
                RemoteManualSelectionHostActionModel.batch_id == batch_id,
                RemoteManualSelectionHostActionModel.file_id == file_id,
                RemoteManualSelectionHostActionModel.transfer_id == transfer_id,
                RemoteManualSelectionHostActionModel.generation == generation,
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.MATERIALIZE.value,
            )
            .order_by(
                RemoteManualSelectionHostActionModel.created_at,
                RemoteManualSelectionHostActionModel.id,
            )
            .limit(1)
        )
        if existing is not None:
            return _host_action_from_record(existing)
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(
                RemoteManualSelectionFileModel.id == file_id,
                RemoteManualSelectionFileModel.batch_id == batch_id,
                RemoteManualSelectionFileModel.session_id == session_id,
            )
            .with_for_update()
        )
        transfer_record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(
                RemoteManualSelectionTransferModel.id == transfer_id,
                RemoteManualSelectionTransferModel.file_id == file_id,
                RemoteManualSelectionTransferModel.batch_id == batch_id,
                RemoteManualSelectionTransferModel.session_id == session_id,
            )
            .with_for_update()
        )
        if (
            file_record is None
            or transfer_record is None
            or file_record.selection_generation != generation
            or not file_record.desired_selected
            or file_record.status != RemoteManualSelectionFileStatus.VERIFIED.value
            or transfer_record.generation != generation
            or transfer_record.status != RemoteManualSelectionTransferStatus.VERIFIED.value
            or transfer_record.verified_checksum_sha256 is None
            or transfer_record.temp_relative_path is None
            or file_record.host_checksum_sha256 != transfer_record.verified_checksum_sha256
            or file_record.output_name is None
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_MATERIALIZATION_NOT_READY",
                "Only a verified current selected generation can be queued for materialization.",
            )
        action = RemoteManualSelectionHostActionV1(
            id=uuid4(),
            session_id=session_id,
            batch_id=batch_id,
            file_id=file_id,
            transfer_id=transfer_id,
            generation=generation,
            action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
            status=RemoteManualSelectionHostActionStatus.QUEUED,
            attempt=0,
        )
        try:
            return self.add_host_action(action)
        except RemoteManualSelectionConflictError:
            existing = self._session.scalar(
                select(RemoteManualSelectionHostActionModel)
                .where(
                    RemoteManualSelectionHostActionModel.file_id == file_id,
                    RemoteManualSelectionHostActionModel.generation == generation,
                    RemoteManualSelectionHostActionModel.action_type
                    == RemoteManualSelectionHostActionType.MATERIALIZE.value,
                    RemoteManualSelectionHostActionModel.status.in_(
                        (
                            RemoteManualSelectionHostActionStatus.QUEUED.value,
                            RemoteManualSelectionHostActionStatus.PROCESSING.value,
                            RemoteManualSelectionHostActionStatus.RETRY.value,
                        )
                    ),
                )
                .limit(1)
            )
            if existing is None:
                raise
            return _host_action_from_record(existing)

    def enqueue_missing_materialization_actions(self, *, limit: int) -> int:
        """Recover verified current generations that predate or lost their queue action."""

        if limit < 1:
            raise ValueError("Materialization reconciliation limit must be positive.")
        action_exists = (
            select(RemoteManualSelectionHostActionModel.id)
            .where(
                RemoteManualSelectionHostActionModel.file_id == RemoteManualSelectionFileModel.id,
                RemoteManualSelectionHostActionModel.generation
                == RemoteManualSelectionFileModel.selection_generation,
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.MATERIALIZE.value,
            )
            .exists()
        )
        files = self._session.scalars(
            select(RemoteManualSelectionFileModel)
            .where(
                RemoteManualSelectionFileModel.desired_selected.is_(True),
                RemoteManualSelectionFileModel.status
                == RemoteManualSelectionFileStatus.VERIFIED.value,
                RemoteManualSelectionFileModel.host_checksum_sha256.is_not(None),
                ~action_exists,
            )
            .order_by(
                RemoteManualSelectionFileModel.updated_at,
                RemoteManualSelectionFileModel.batch_id,
                RemoteManualSelectionFileModel.source_index,
                RemoteManualSelectionFileModel.id,
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        ).all()
        created = 0
        for file_record in files:
            transfer_record = self._session.scalar(
                select(RemoteManualSelectionTransferModel)
                .where(
                    RemoteManualSelectionTransferModel.file_id == file_record.id,
                    RemoteManualSelectionTransferModel.batch_id == file_record.batch_id,
                    RemoteManualSelectionTransferModel.session_id == file_record.session_id,
                    RemoteManualSelectionTransferModel.generation
                    == file_record.selection_generation,
                    RemoteManualSelectionTransferModel.status
                    == RemoteManualSelectionTransferStatus.VERIFIED.value,
                    RemoteManualSelectionTransferModel.verified_checksum_sha256
                    == file_record.host_checksum_sha256,
                    RemoteManualSelectionTransferModel.temp_relative_path.is_not(None),
                )
                .order_by(
                    RemoteManualSelectionTransferModel.attempt.desc(),
                    RemoteManualSelectionTransferModel.id,
                )
                .limit(1)
            )
            if transfer_record is None:
                continue
            self.ensure_materialization_action(
                session_id=file_record.session_id,
                batch_id=file_record.batch_id,
                file_id=file_record.id,
                transfer_id=transfer_record.id,
                generation=file_record.selection_generation,
            )
            created += 1
        return created

    def claim_next_materialization_action(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> RemoteManualSelectionHostActionRecord | None:
        if not lease_owner.strip() or lease_duration.total_seconds() <= 0:
            raise ValueError("A materialization lease requires an owner and positive duration.")
        eligible = or_(
            RemoteManualSelectionHostActionModel.status
            == RemoteManualSelectionHostActionStatus.QUEUED.value,
            (
                (
                    RemoteManualSelectionHostActionModel.status
                    == RemoteManualSelectionHostActionStatus.RETRY.value
                )
                & or_(
                    RemoteManualSelectionHostActionModel.next_attempt_at.is_(None),
                    RemoteManualSelectionHostActionModel.next_attempt_at <= claimed_at,
                )
            ),
            (
                (
                    RemoteManualSelectionHostActionModel.status
                    == RemoteManualSelectionHostActionStatus.PROCESSING.value
                )
                & (RemoteManualSelectionHostActionModel.lease_expires_at <= claimed_at)
            ),
        )
        removal_action = aliased(RemoteManualSelectionHostActionModel)
        pending_removal = (
            select(removal_action.id)
            .where(
                removal_action.action_type == RemoteManualSelectionHostActionType.REMOVE.value,
                or_(
                    removal_action.status == RemoteManualSelectionHostActionStatus.QUEUED.value,
                    (
                        (removal_action.status == RemoteManualSelectionHostActionStatus.RETRY.value)
                        & or_(
                            removal_action.next_attempt_at.is_(None),
                            removal_action.next_attempt_at <= claimed_at,
                        )
                    ),
                    (
                        (
                            removal_action.status
                            == RemoteManualSelectionHostActionStatus.PROCESSING.value
                        )
                        & (removal_action.lease_expires_at <= claimed_at)
                    ),
                ),
            )
            .exists()
        )
        record = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.MATERIALIZE.value,
                eligible,
                ~pending_removal,
            )
            .order_by(
                RemoteManualSelectionHostActionModel.next_attempt_at.asc().nulls_first(),
                RemoteManualSelectionHostActionModel.created_at,
                RemoteManualSelectionHostActionModel.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return None
        token = uuid4()
        record.status = RemoteManualSelectionHostActionStatus.PROCESSING.value
        record.attempt += 1
        record.lease_owner = lease_owner.strip()
        record.lease_token = token
        record.lease_expires_at = claimed_at + lease_duration
        record.next_attempt_at = None
        record.updated_at = claimed_at
        self._session.flush()
        return _host_action_record_from_record(record)

    def claim_next_removal_action(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> RemoteManualSelectionHostActionRecord | None:
        if not lease_owner.strip() or lease_duration.total_seconds() <= 0:
            raise ValueError("A removal lease requires an owner and positive duration.")
        eligible = or_(
            RemoteManualSelectionHostActionModel.status
            == RemoteManualSelectionHostActionStatus.QUEUED.value,
            (
                (
                    RemoteManualSelectionHostActionModel.status
                    == RemoteManualSelectionHostActionStatus.RETRY.value
                )
                & or_(
                    RemoteManualSelectionHostActionModel.next_attempt_at.is_(None),
                    RemoteManualSelectionHostActionModel.next_attempt_at <= claimed_at,
                )
            ),
            (
                (
                    RemoteManualSelectionHostActionModel.status
                    == RemoteManualSelectionHostActionStatus.PROCESSING.value
                )
                & (RemoteManualSelectionHostActionModel.lease_expires_at <= claimed_at)
            ),
        )
        record = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.REMOVE.value,
                eligible,
            )
            .order_by(
                RemoteManualSelectionHostActionModel.next_attempt_at.asc().nulls_first(),
                RemoteManualSelectionHostActionModel.created_at,
                RemoteManualSelectionHostActionModel.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return None
        token = uuid4()
        record.status = RemoteManualSelectionHostActionStatus.PROCESSING.value
        record.attempt += 1
        record.lease_owner = lease_owner.strip()
        record.lease_token = token
        record.lease_expires_at = claimed_at + lease_duration
        record.next_attempt_at = None
        record.updated_at = claimed_at
        self._session.flush()
        return _host_action_record_from_record(record)

    def lock_removal_context(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        locked_at: datetime,
    ) -> RemoteManualSelectionRemovalContext | None:
        action = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(RemoteManualSelectionHostActionModel.id == action_id)
            .with_for_update()
        )
        if (
            action is None
            or action.action_type != RemoteManualSelectionHostActionType.REMOVE.value
            or action.status != RemoteManualSelectionHostActionStatus.PROCESSING.value
            or action.lease_token != lease_token
            or action.lease_expires_at is None
            or action.lease_expires_at <= locked_at
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                "The removal action lease is no longer owned by this executor.",
            )
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == action.file_id)
            .with_for_update()
        )
        transfer_record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == action.transfer_id)
            .with_for_update()
        )
        if file_record is None or transfer_record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The removal action references unavailable state.",
            )
        if file_record.selection_generation < action.generation or (
            file_record.selection_generation == action.generation and file_record.desired_selected
        ):
            transition_remote_host_action_status(
                RemoteManualSelectionHostActionStatus.PROCESSING,
                RemoteManualSelectionHostActionStatus.SUPERSEDED,
            )
            action.status = RemoteManualSelectionHostActionStatus.SUPERSEDED.value
            _clear_action_lease(action, updated_at=locked_at)
            self._session.flush()
            return None
        checksum = transfer_record.verified_checksum_sha256
        materialization = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(
                RemoteManualSelectionHostActionModel.file_id == action.file_id,
                RemoteManualSelectionHostActionModel.transfer_id == transfer_record.id,
                RemoteManualSelectionHostActionModel.generation == transfer_record.generation,
                RemoteManualSelectionHostActionModel.action_type
                == RemoteManualSelectionHostActionType.MATERIALIZE.value,
            )
            .order_by(
                RemoteManualSelectionHostActionModel.created_at.desc(),
                RemoteManualSelectionHostActionModel.id,
            )
            .limit(1)
        )
        select_operation = self._session.scalar(
            select(RemoteManualSelectionOperationModel)
            .where(
                RemoteManualSelectionOperationModel.file_id == action.file_id,
                RemoteManualSelectionOperationModel.selection_generation
                == transfer_record.generation,
                RemoteManualSelectionOperationModel.operation_type
                == RemoteManualSelectionOperationType.SELECT.value,
                RemoteManualSelectionOperationModel.status
                == RemoteManualSelectionOperationStatus.APPLIED.value,
            )
            .order_by(RemoteManualSelectionOperationModel.created_at.desc())
            .limit(1)
        )
        if (
            checksum is None
            or materialization is None
            or select_operation is None
            or select_operation.output_name is None
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_REMOVAL_OWNERSHIP_MISSING",
                "The removal action has no immutable materialization ownership proof.",
            )
        return RemoteManualSelectionRemovalContext(
            action=_host_action_from_record(action),
            file=_file_from_record(file_record),
            transfer=_transfer_from_record(transfer_record),
            materialization_action_id=materialization.id,
            materialized_generation=transfer_record.generation,
            output_name=select_operation.output_name,
            checksum_sha256=checksum,
        )

    def complete_removal_action(
        self,
        context: RemoteManualSelectionRemovalContext,
        *,
        lease_token: UUID,
        completed_at: datetime,
    ) -> RemoteManualSelectionFileV1:
        action = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(RemoteManualSelectionHostActionModel.id == context.action.id)
            .with_for_update()
        )
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == context.file.id)
            .with_for_update()
        )
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == context.file.batch_id)
            .with_for_update()
        )
        if (
            action is None
            or file_record is None
            or batch_record is None
            or action.status != RemoteManualSelectionHostActionStatus.PROCESSING.value
            or action.lease_token != lease_token
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                "The removal action cannot be completed by this executor.",
            )
        if file_record.selection_generation < action.generation:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_REMOVAL_GENERATION_CONFLICT",
                "The file generation is older than its removal tombstone.",
            )
        projection_changed = False
        if file_record.final_relative_path == context.output_name:
            file_record.final_relative_path = None
            projection_changed = True
        if not file_record.desired_selected:
            if file_record.status != RemoteManualSelectionFileStatus.REMOVED.value:
                transition_remote_file_status(
                    RemoteManualSelectionFileStatus(file_record.status),
                    RemoteManualSelectionFileStatus.REMOVED,
                )
                file_record.status = RemoteManualSelectionFileStatus.REMOVED.value
                projection_changed = True
            file_record.host_checksum_sha256 = None
            file_record.temp_relative_path = None
        action.status = RemoteManualSelectionHostActionStatus.COMPLETED.value
        action.last_error_code = None
        _clear_action_lease(action, updated_at=completed_at)
        if projection_changed:
            batch_record.server_revision += 1
            file_record.last_server_revision = batch_record.server_revision
            file_record.updated_at = completed_at
            batch_record.updated_at = completed_at
        self._session.flush()
        return _file_from_record(file_record)

    def lock_materialization_context(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        locked_at: datetime,
    ) -> RemoteManualSelectionMaterializationContext | None:
        action = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(RemoteManualSelectionHostActionModel.id == action_id)
            .with_for_update()
        )
        if (
            action is None
            or action.status != RemoteManualSelectionHostActionStatus.PROCESSING.value
            or action.lease_token != lease_token
            or action.lease_expires_at is None
            or action.lease_expires_at <= locked_at
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                "The materialization action lease is no longer owned by this executor.",
            )
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == action.file_id)
            .with_for_update()
        )
        transfer_record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == action.transfer_id)
            .with_for_update()
        )
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == action.batch_id)
            .with_for_update()
        )
        if file_record is None or transfer_record is None or batch_record is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The materialization action references unavailable state.",
            )
        if (
            not file_record.desired_selected
            or file_record.selection_generation != action.generation
            or transfer_record.generation != action.generation
        ):
            transition_remote_host_action_status(
                RemoteManualSelectionHostActionStatus.PROCESSING,
                RemoteManualSelectionHostActionStatus.SUPERSEDED,
            )
            action.status = RemoteManualSelectionHostActionStatus.SUPERSEDED.value
            _clear_action_lease(action, updated_at=locked_at)
            self._session.flush()
            return None
        if (
            file_record.status != RemoteManualSelectionFileStatus.VERIFIED.value
            or transfer_record.status != RemoteManualSelectionTransferStatus.VERIFIED.value
            or transfer_record.verified_checksum_sha256 is None
            or transfer_record.temp_relative_path is None
            or file_record.output_name is None
            or file_record.host_checksum_sha256 != transfer_record.verified_checksum_sha256
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_MATERIALIZATION_NOT_READY",
                "The claimed action no longer has a consistent verified source.",
            )
        return RemoteManualSelectionMaterializationContext(
            action=_host_action_from_record(action),
            file=_file_from_record(file_record),
            transfer=_transfer_from_record(transfer_record),
            verified_relative_path=transfer_record.temp_relative_path,
            output_name=file_record.output_name,
            checksum_sha256=transfer_record.verified_checksum_sha256,
        )

    def complete_materialization_action(
        self,
        context: RemoteManualSelectionMaterializationContext,
        *,
        lease_token: UUID,
        final_relative_path: str,
        completed_at: datetime,
    ) -> RemoteManualSelectionFileV1:
        action = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(RemoteManualSelectionHostActionModel.id == context.action.id)
            .with_for_update()
        )
        file_record = self._session.scalar(
            select(RemoteManualSelectionFileModel)
            .where(RemoteManualSelectionFileModel.id == context.file.id)
            .with_for_update()
        )
        transfer_record = self._session.scalar(
            select(RemoteManualSelectionTransferModel)
            .where(RemoteManualSelectionTransferModel.id == context.transfer.id)
            .with_for_update()
        )
        batch_record = self._session.scalar(
            select(RemoteManualSelectionBatchModel)
            .where(RemoteManualSelectionBatchModel.id == context.file.batch_id)
            .with_for_update()
        )
        if (
            action is None
            or file_record is None
            or transfer_record is None
            or batch_record is None
            or action.status != RemoteManualSelectionHostActionStatus.PROCESSING.value
            or action.lease_token != lease_token
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                "The materialization action cannot be completed by this executor.",
            )
        if (
            not file_record.desired_selected
            or file_record.selection_generation != context.action.generation
            or transfer_record.generation != context.action.generation
            or transfer_record.verified_checksum_sha256 != context.checksum_sha256
            or file_record.host_checksum_sha256 != context.checksum_sha256
            or file_record.output_name != context.output_name
            or final_relative_path != context.output_name
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_MATERIALIZATION_GENERATION_CONFLICT",
                "The selected generation changed before materialization commit.",
            )
        was_synced = file_record.status == RemoteManualSelectionFileStatus.SYNCED.value
        if not was_synced:
            current_file_status = RemoteManualSelectionFileStatus(file_record.status)
            transition_remote_file_status(
                current_file_status,
                RemoteManualSelectionFileStatus.MATERIALIZED,
            )
            transition_remote_file_status(
                RemoteManualSelectionFileStatus.MATERIALIZED,
                RemoteManualSelectionFileStatus.SYNCED,
            )
            transition_remote_transfer_status(
                RemoteManualSelectionTransferStatus(transfer_record.status),
                RemoteManualSelectionTransferStatus.MATERIALIZED,
            )
            batch_record.server_revision += 1
            batch_record.transferred_file_count += 1
            file_record.status = RemoteManualSelectionFileStatus.SYNCED.value
            file_record.final_relative_path = final_relative_path
            file_record.last_server_revision = batch_record.server_revision
            transfer_record.status = RemoteManualSelectionTransferStatus.MATERIALIZED.value
            transfer_record.updated_at = completed_at
        elif (
            file_record.final_relative_path != final_relative_path
            or transfer_record.status != RemoteManualSelectionTransferStatus.MATERIALIZED.value
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_MATERIALIZATION_STATE_CONFLICT",
                "The persisted materialized state differs from the host artifact.",
            )
        action.status = RemoteManualSelectionHostActionStatus.COMPLETED.value
        action.last_error_code = None
        _clear_action_lease(action, updated_at=completed_at)
        file_record.updated_at = completed_at
        batch_record.updated_at = completed_at
        self._session.flush()
        return _file_from_record(file_record)

    def finish_materialization_failure(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        error_code: str,
        failed_at: datetime,
        retry_at: datetime | None,
    ) -> RemoteManualSelectionHostActionV1:
        action = self._session.scalar(
            select(RemoteManualSelectionHostActionModel)
            .where(RemoteManualSelectionHostActionModel.id == action_id)
            .with_for_update()
        )
        if (
            action is None
            or action.status != RemoteManualSelectionHostActionStatus.PROCESSING.value
            or action.lease_token != lease_token
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                "The failed materialization action lease was already replaced.",
            )
        target = (
            RemoteManualSelectionHostActionStatus.FAILED
            if retry_at is None
            else RemoteManualSelectionHostActionStatus.RETRY
        )
        transition_remote_host_action_status(
            RemoteManualSelectionHostActionStatus.PROCESSING,
            target,
        )
        action.status = target.value
        action.last_error_code = error_code
        action.next_attempt_at = retry_at
        _clear_action_lease(action, updated_at=failed_at)
        self._session.flush()
        return _host_action_from_record(action)

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
        validate_remote_selection_audit_payload(payload)
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
        self.batch_file_counts: dict[UUID, int] = {}
        self.base_mappings: set[tuple[UUID, str, str]] = set()
        self.transfers: dict[UUID, RemoteManualSelectionTransferV1] = {}
        self.transfer_paths: dict[UUID, str | None] = {}
        self.transfer_updated_at: dict[UUID, datetime] = {}
        self.host_actions: dict[UUID, RemoteManualSelectionHostActionV1] = {}
        self.host_action_metadata: dict[
            UUID,
            tuple[str | None, UUID | None, datetime | None, datetime | None, str | None],
        ] = {}
        self.file_final_paths: dict[UUID, str] = {}
        self.audit_event_ids: set[UUID] = set()
        self.batch_final_checksums: dict[UUID, str] = {}
        self.batch_updated_at: dict[UUID, datetime] = {}

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

    def get_host_binding(
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
            self.batch_file_counts[value.id] = total_file_count
            session = self.sessions.get(value.session_id)
            if session is not None:
                self.batch_updated_at[value.id] = session.updated_at
            return value

    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None:
        return self.batches.get(batch_id)

    def get_batch_total_file_count(self, batch_id: UUID) -> int | None:
        return self.batch_file_counts.get(batch_id)

    def get_finalization_snapshot(
        self,
        *,
        batch_id: UUID,
        for_update: bool = False,
    ) -> RemoteManualSelectionFinalizationSnapshot | None:
        del for_update
        with self._lock:
            batch = self.batches.get(batch_id)
            if batch is None:
                return None
            collection = self.collections.get(batch.collection_id)
            if collection is None:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The finalization collection is unavailable.",
                )
            files = tuple(
                RemoteManualSelectionFinalFileRecord(
                    file=item,
                    final_relative_path=self.file_final_paths.get(item.id),
                )
                for item in sorted(
                    (item for item in self.files.values() if item.batch_id == batch_id),
                    key=lambda item: (item.source_index, str(item.id)),
                )
            )
            operations = tuple(
                sorted(
                    (
                        item
                        for item in self.operations.values()
                        if item.command.batch_id == batch_id
                    ),
                    key=lambda item: (
                        item.command.client_sequence,
                        str(item.command.operation_id),
                    ),
                )
            )
            transfers = tuple(
                sorted(
                    (item for item in self.transfers.values() if item.batch_id == batch_id),
                    key=lambda item: (item.attempt, str(item.id)),
                )
            )
            host_actions = tuple(
                sorted(
                    (item for item in self.host_actions.values() if item.batch_id == batch_id),
                    key=lambda item: (item.attempt, str(item.id)),
                )
            )
            selected = sum(item.file.desired_selected for item in files)
            transferred = sum(
                item.file.desired_selected
                and item.file.status is RemoteManualSelectionFileStatus.SYNCED
                and item.final_relative_path is not None
                for item in files
            )
            return RemoteManualSelectionFinalizationSnapshot(
                batch=batch,
                collection=collection,
                files=files,
                operations=operations,
                transfers=transfers,
                host_actions=host_actions,
                total_file_count=self.batch_file_counts[batch_id],
                selected_file_count=selected,
                transferred_file_count=transferred,
                final_manifest_checksum_sha256=self.batch_final_checksums.get(batch_id),
                updated_at=self.batch_updated_at.get(
                    batch_id,
                    self.sessions[batch.session_id].updated_at,
                ),
            )

    def mark_batch_finalizing(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        changed_at: datetime,
    ) -> RemoteManualSelectionBatchV1:
        with self._lock:
            batch = self._finalization_batch(session_id, batch_id)
            if batch.server_revision != expected_server_revision:
                raise _finalization_revision_conflict(batch.server_revision)
            if batch.status is RemoteManualSelectionBatchStatus.ACTIVE:
                batch = replace(batch, status=RemoteManualSelectionBatchStatus.FINALIZING)
                self.batches[batch_id] = batch
                self.batch_updated_at[batch_id] = changed_at
            elif batch.status is not RemoteManualSelectionBatchStatus.FINALIZING:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_BATCH_NOT_FINALIZABLE",
                    "Only an active or finalizing batch can be finalized.",
                )
            return batch

    def complete_batch_finalization(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        final_manifest_checksum_sha256: str,
        completed_at: datetime,
        actor: str,
    ) -> RemoteManualSelectionFinalizationSnapshot:
        del actor
        with self._lock:
            batch = self._finalization_batch(session_id, batch_id)
            if batch.server_revision != expected_server_revision:
                raise _finalization_revision_conflict(batch.server_revision)
            if batch.status is not RemoteManualSelectionBatchStatus.FINALIZING:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_BATCH_NOT_FINALIZING",
                    "The batch must remain finalizing until every manifest is durable.",
                )
            self.batches[batch_id] = replace(
                batch,
                status=RemoteManualSelectionBatchStatus.COMPLETED,
                server_revision=batch.server_revision + 1,
            )
            self.batch_final_checksums[batch_id] = final_manifest_checksum_sha256
            self.batch_updated_at[batch_id] = completed_at
            snapshot = self.get_finalization_snapshot(batch_id=batch_id)
            assert snapshot is not None
            return snapshot

    def reopen_completed_batch(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        expected_server_revision: int,
        expected_final_manifest_checksum_sha256: str,
        reopened_at: datetime,
    ) -> RemoteManualSelectionFinalizationSnapshot:
        with self._lock:
            batch = self._finalization_batch(session_id, batch_id)
            if batch.server_revision != expected_server_revision:
                raise _finalization_revision_conflict(batch.server_revision)
            if (
                batch.status is not RemoteManualSelectionBatchStatus.COMPLETED
                or self.batch_final_checksums.get(batch_id)
                != expected_final_manifest_checksum_sha256
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_REOPEN_PRECONDITION_FAILED",
                    "The completed batch checksum no longer matches the reopen command.",
                )
            self.batches[batch_id] = replace(
                batch,
                status=RemoteManualSelectionBatchStatus.ACTIVE,
                server_revision=batch.server_revision + 1,
            )
            self.batch_final_checksums.pop(batch_id, None)
            self.batch_updated_at[batch_id] = reopened_at
            snapshot = self.get_finalization_snapshot(batch_id=batch_id)
            assert snapshot is not None
            return snapshot

    def _finalization_batch(
        self,
        session_id: UUID,
        batch_id: UUID,
    ) -> RemoteManualSelectionBatchV1:
        batch = self.batches.get(batch_id)
        if batch is None or batch.session_id != session_id:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The batch does not belong to the remote selection session.",
            )
        return batch

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

    def get_operation(
        self,
        operation_id: UUID,
    ) -> RemoteManualSelectionOperationV1 | None:
        return self.operations.get(operation_id)

    def get_applied_select_operation(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionOperationV1 | None:
        return next(
            (
                item
                for item in self.operations.values()
                if item.command.batch_id == batch_id
                and item.command.file_id == file_id
                and item.command.selection_generation == generation
                and item.command.operation_type is RemoteManualSelectionOperationType.SELECT
                and item.status is RemoteManualSelectionOperationStatus.APPLIED
            ),
            None,
        )

    def get_transfer_record(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
    ) -> RemoteManualSelectionTransferRecord | None:
        value = self.transfers.get(transfer_id)
        if value is None or value.batch_id != batch_id or value.file_id != file_id:
            return None
        return RemoteManualSelectionTransferRecord(value, self.transfer_paths.get(value.id))

    def get_verified_transfer_record(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionTransferRecord | None:
        matches = [
            item
            for item in self.transfers.values()
            if item.batch_id == batch_id
            and item.file_id == file_id
            and item.generation == generation
            and item.status
            in {
                RemoteManualSelectionTransferStatus.VERIFIED,
                RemoteManualSelectionTransferStatus.MATERIALIZED,
            }
        ]
        if not matches:
            return None
        value = max(matches, key=lambda item: item.attempt)
        return RemoteManualSelectionTransferRecord(value, self.transfer_paths.get(value.id))

    def next_transfer_attempt(self, *, file_id: UUID, generation: int) -> int:
        return (
            max(
                (
                    item.attempt
                    for item in self.transfers.values()
                    if item.file_id == file_id and item.generation == generation
                ),
                default=0,
            )
            + 1
        )

    def session_reserved_transfer_bytes(self, session_id: UUID) -> int:
        return sum(
            item.declared_bytes
            for item in self.transfers.values()
            if item.session_id == session_id
            and item.status
            in {
                RemoteManualSelectionTransferStatus.UPLOADING,
                RemoteManualSelectionTransferStatus.STORED_TEMP,
                RemoteManualSelectionTransferStatus.VERIFIED,
            }
        )

    def update_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None,
    ) -> RemoteManualSelectionTransferV1:
        with self._lock:
            current = self.transfers.get(value.id)
            if current is None:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_TRANSFER_NOT_FOUND",
                    "The remote selection transfer does not exist.",
                )
            if current.status is not value.status:
                transition_remote_transfer_status(current.status, value.status)
            self.transfers[value.id] = value
            self.transfer_paths[value.id] = temp_relative_path
            self.transfer_updated_at[value.id] = datetime.now(UTC)
            return value

    def cancel_failed_transfer_attempts(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        except_transfer_id: UUID,
    ) -> int:
        with self._lock:
            matching_ids = tuple(
                item.id
                for item in self.transfers.values()
                if item.batch_id == batch_id
                and item.file_id == file_id
                and item.generation == generation
                and item.id != except_transfer_id
                and item.status is RemoteManualSelectionTransferStatus.FAILED
            )
            for transfer_id in matching_ids:
                current = self.transfers[transfer_id]
                transition_remote_transfer_status(
                    current.status,
                    RemoteManualSelectionTransferStatus.CANCELLED,
                )
                self.transfers[transfer_id] = replace(
                    current,
                    status=RemoteManualSelectionTransferStatus.CANCELLED,
                )
                self.transfer_paths[transfer_id] = None
                self.transfer_updated_at[transfer_id] = datetime.now(UTC)
            return len(matching_ids)

    def update_file_transfer_status(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        status: RemoteManualSelectionFileStatus,
        temp_relative_path: str | None = None,
        host_checksum_sha256: str | None = None,
    ) -> RemoteManualSelectionFileV1:
        del temp_relative_path
        with self._lock:
            file = self.files.get(file_id)
            batch = self.batches.get(batch_id)
            if (
                file is None
                or batch is None
                or not file.desired_selected
                or file.selection_generation != generation
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_TRANSFER_GENERATION_CONFLICT",
                    "The selected file generation changed during transfer.",
                )
            if file.status is not status:
                transition_remote_file_status(file.status, status)
            batch = replace(batch, server_revision=batch.server_revision + 1)
            file = replace(file, status=status, host_checksum_sha256=host_checksum_sha256)
            self.batches[batch_id] = batch
            self.files[file_id] = file
            self.file_revisions[file_id] = batch.server_revision
            return file

    def register_source_files(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        values: Sequence[RemoteManualSelectionFileV1],
        source_kind: RemoteSourceKind,
        complete: bool,
    ) -> RemoteManualSelectionSourceRegistration:
        with self._lock:
            batch = self.batches.get(batch_id)
            if batch is None or batch.session_id != session_id:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The batch does not belong to the remote selection session.",
                )
            existing = tuple(
                sorted(
                    (item for item in self.files.values() if item.batch_id == batch_id),
                    key=lambda item: item.source_index,
                )
            )
            by_id = {item.id: item for item in existing}
            by_index = {item.source_index: item for item in existing}
            by_path = {item.relative_path: item for item in existing}
            accepted: list[RemoteManualSelectionFileV1] = []
            new_values: list[RemoteManualSelectionFileV1] = []
            for value in values:
                if value.session_id != session_id or value.batch_id != batch_id:
                    raise RemoteManualSelectionError(
                        "REMOTE_SELECTION_SCOPE_MISMATCH",
                        "A source item does not belong to the remote selection scope.",
                    )
                matches = {
                    item.id: item
                    for item in (
                        by_id.get(value.id),
                        by_index.get(value.source_index),
                        by_path.get(value.relative_path),
                    )
                    if item is not None
                }
                if matches:
                    if len(matches) != 1 or next(iter(matches.values())) != value:
                        raise _source_manifest_conflict()
                    accepted.append(next(iter(matches.values())))
                    continue
                if batch.status is RemoteManualSelectionBatchStatus.ACTIVE:
                    raise _source_manifest_immutable()
                by_id[value.id] = value
                by_index[value.source_index] = value
                by_path[value.relative_path] = value
                accepted.append(value)
                new_values.append(value)
            all_files = tuple(
                sorted(
                    (*existing, *new_values),
                    key=lambda item: item.source_index,
                )
            )
            declared_count = self.batch_file_counts[batch_id]
            if len(all_files) > declared_count:
                raise _source_manifest_conflict()
            if complete:
                if len(all_files) != declared_count:
                    raise RemoteManualSelectionConflictError(
                        "REMOTE_SELECTION_SOURCE_MANIFEST_INCOMPLETE",
                        "The source manifest does not contain the declared number of files.",
                        details={
                            "actualFileCount": len(all_files),
                            "expectedFileCount": declared_count,
                        },
                    )
                manifest = build_remote_source_manifest(
                    tuple(
                        RemoteSourceManifestEntryV1(
                            ordinal=item.source_index,
                            relative_path=item.relative_path,
                            name=item.relative_path.rsplit("/", 1)[-1],
                            size_bytes=item.size_bytes,
                            last_modified_ms=item.last_modified_ms,
                            mime_type=item.mime_type,
                        )
                        for item in all_files
                    ),
                    source_kind=source_kind,
                )
                if manifest.manifest_checksum_sha256 != batch.source_manifest_checksum_sha256:
                    raise _source_manifest_conflict()
                if batch.status is RemoteManualSelectionBatchStatus.INDEXING:
                    batch = replace(batch, status=RemoteManualSelectionBatchStatus.ACTIVE)
                elif batch.status is not RemoteManualSelectionBatchStatus.ACTIVE:
                    raise RemoteManualSelectionConflictError(
                        "REMOTE_SELECTION_BATCH_NOT_INDEXING",
                        "The batch cannot accept source items in its current state.",
                    )
            elif batch.status is not RemoteManualSelectionBatchStatus.INDEXING:
                if not (batch.status is RemoteManualSelectionBatchStatus.ACTIVE and not new_values):
                    raise _source_manifest_immutable()
            for value in new_values:
                self.files[value.id] = value
                self.file_revisions[value.id] = 0
            self.batches[batch_id] = batch
            return RemoteManualSelectionSourceRegistration(
                batch=batch,
                files=tuple(accepted),
                created_count=len(new_values),
                total_file_count=len(all_files),
            )

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
                target_operation=(
                    None
                    if command.target_operation_id is None
                    else self.operations.get(command.target_operation_id)
                ),
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
                    if command.operation_type in {
                        RemoteManualSelectionOperationType.DESELECT,
                        RemoteManualSelectionOperationType.UNDO,
                    }:
                        self._prepare_deselect_in_memory(
                            file_id=result.file.id,
                            tombstone_generation=command.selection_generation,
                        )
                        result = replace(result, file=self.files[result.file.id])
                self.operations[command.operation_id] = result.operation
            return result

    def _prepare_deselect_in_memory(
        self,
        *,
        file_id: UUID,
        tombstone_generation: int,
    ) -> None:
        transfers = sorted(
            (
                transfer
                for transfer in self.transfers.values()
                if transfer.file_id == file_id and transfer.generation < tombstone_generation
            ),
            key=lambda transfer: (transfer.generation, transfer.attempt, str(transfer.id)),
            reverse=True,
        )
        cancelable = {
            RemoteManualSelectionTransferStatus.QUEUED,
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.VERIFIED,
            RemoteManualSelectionTransferStatus.FAILED,
            RemoteManualSelectionTransferStatus.RETRYING,
        }
        for transfer in transfers:
            if transfer.status in cancelable:
                transition_remote_transfer_status(
                    transfer.status,
                    RemoteManualSelectionTransferStatus.CANCELLED,
                )
                self.transfers[transfer.id] = replace(
                    transfer,
                    status=RemoteManualSelectionTransferStatus.CANCELLED,
                )

        materializations = sorted(
            (
                action
                for action in self.host_actions.values()
                if action.file_id == file_id
                and action.generation < tombstone_generation
                and action.action_type is RemoteManualSelectionHostActionType.MATERIALIZE
            ),
            key=lambda action: (action.generation, str(action.id)),
            reverse=True,
        )
        materialization = next(
            (
                action
                for action in materializations
                if action.transfer_id is not None
                and self.transfers[action.transfer_id].verified_checksum_sha256 is not None
            ),
            None,
        )
        active = {
            RemoteManualSelectionHostActionStatus.QUEUED,
            RemoteManualSelectionHostActionStatus.PROCESSING,
            RemoteManualSelectionHostActionStatus.RETRY,
        }
        for action in materializations:
            if action.status in active:
                transition_remote_host_action_status(
                    action.status,
                    RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                self.host_actions[action.id] = replace(
                    action,
                    status=RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                self.host_action_metadata[action.id] = (None, None, None, None, None)

        file = self.files[file_id]
        existing_remove = next(
            (
                action
                for action in self.host_actions.values()
                if action.file_id == file_id
                and action.action_type is RemoteManualSelectionHostActionType.REMOVE
                and action.status in active
            ),
            None,
        )
        if existing_remove is not None:
            self.files[file_id] = replace(
                file,
                status=RemoteManualSelectionFileStatus.DESELECT_PENDING,
            )
            return
        if materialization is None:
            self.files[file_id] = replace(
                file,
                status=RemoteManualSelectionFileStatus.REMOVED,
            )
            self.file_final_paths.pop(file_id, None)
            return
        action = RemoteManualSelectionHostActionV1(
            id=uuid4(),
            session_id=file.session_id,
            batch_id=file.batch_id,
            file_id=file.id,
            transfer_id=materialization.transfer_id,
            generation=tombstone_generation,
            action_type=RemoteManualSelectionHostActionType.REMOVE,
            status=RemoteManualSelectionHostActionStatus.QUEUED,
            attempt=0,
        )
        self.add_host_action(action)
        self.files[file_id] = replace(
            file,
            status=RemoteManualSelectionFileStatus.DESELECT_PENDING,
        )

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

    def list_file_delta_records(
        self,
        *,
        batch_id: UUID,
        after_revision: int,
        limit: int,
    ) -> tuple[RemoteManualSelectionFileDelta, ...]:
        _require_page(limit)
        return tuple(
            RemoteManualSelectionFileDelta(
                file=value,
                server_revision=self.file_revisions[value.id],
            )
            for value in sorted(
                (
                    item
                    for item in self.files.values()
                    if item.batch_id == batch_id and self.file_revisions[item.id] > after_revision
                ),
                key=lambda item: (
                    self.file_revisions[item.id],
                    item.source_index,
                    item.id,
                ),
            )[:limit]
        )

    def list_stale_transfer_candidates(
        self,
        *,
        stale_before: datetime,
        limit: int,
    ) -> tuple[RemoteManualSelectionRecoveryTransferCandidate, ...]:
        _require_page(limit)
        active = {
            RemoteManualSelectionTransferStatus.QUEUED,
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.RETRYING,
        }
        values = sorted(
            (
                item
                for item in self.transfers.values()
                if item.status in active
                and self.transfer_updated_at.get(item.id, datetime.min.replace(tzinfo=UTC))
                <= stale_before
            ),
            key=lambda item: (self.transfer_updated_at[item.id], item.id),
        )[:limit]
        return tuple(
            RemoteManualSelectionRecoveryTransferCandidate(
                transfer=item,
                file=self.files[item.file_id],
                updated_at=self.transfer_updated_at[item.id],
            )
            for item in values
        )

    def recover_verified_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        verified_relative_path: str,
        checksum_sha256: str,
        recovered_at: datetime,
    ) -> bool:
        with self._lock:
            transfer = self.transfers.get(candidate.transfer.id)
            file = self.files.get(candidate.file.id)
            batch = self.batches.get(candidate.file.batch_id)
            if transfer is None or file is None or batch is None:
                return False
            if transfer.status in {
                RemoteManualSelectionTransferStatus.VERIFIED,
                RemoteManualSelectionTransferStatus.MATERIALIZED,
            }:
                return False
            if (
                self.transfer_updated_at.get(transfer.id) != candidate.updated_at
                or transfer.generation != file.selection_generation
                or not file.desired_selected
                or checksum_sha256 != transfer.declared_checksum_sha256
            ):
                return False
            recovered_transfer = replace(
                transfer,
                received_bytes=transfer.declared_bytes,
                status=RemoteManualSelectionTransferStatus.VERIFIED,
                verified_checksum_sha256=checksum_sha256,
            )
            next_revision = batch.server_revision + 1
            self.transfers[transfer.id] = recovered_transfer
            self.transfer_paths[transfer.id] = verified_relative_path
            self.transfer_updated_at[transfer.id] = recovered_at
            self.files[file.id] = replace(
                file,
                status=RemoteManualSelectionFileStatus.VERIFIED,
                host_checksum_sha256=checksum_sha256,
            )
            self.file_revisions[file.id] = next_revision
            self.batches[batch.id] = replace(batch, server_revision=next_revision)
            self.ensure_materialization_action(
                session_id=file.session_id,
                batch_id=file.batch_id,
                file_id=file.id,
                transfer_id=transfer.id,
                generation=transfer.generation,
            )
            return True

    def fail_stale_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        error_code: str,
        recovered_at: datetime,
    ) -> bool:
        del error_code
        with self._lock:
            transfer = self.transfers.get(candidate.transfer.id)
            file = self.files.get(candidate.file.id)
            batch = self.batches.get(candidate.file.batch_id)
            if transfer is None or file is None or batch is None:
                return False
            if self.transfer_updated_at.get(transfer.id) != candidate.updated_at:
                return False
            active = {
                RemoteManualSelectionTransferStatus.QUEUED,
                RemoteManualSelectionTransferStatus.UPLOADING,
                RemoteManualSelectionTransferStatus.STORED_TEMP,
                RemoteManualSelectionTransferStatus.RETRYING,
            }
            if transfer.status not in active:
                return False
            self.transfers[transfer.id] = replace(
                transfer,
                status=RemoteManualSelectionTransferStatus.FAILED,
            )
            self.transfer_updated_at[transfer.id] = recovered_at
            if file.desired_selected and file.selection_generation == transfer.generation:
                next_revision = batch.server_revision + 1
                self.files[file.id] = replace(
                    file,
                    status=RemoteManualSelectionFileStatus.FAILED,
                )
                self.file_revisions[file.id] = next_revision
                self.batches[batch.id] = replace(batch, server_revision=next_revision)
            return True

    def get_batch_queue_snapshot(
        self,
        *,
        batch_id: UUID,
        now: datetime,
        stale_before: datetime,
    ) -> RemoteManualSelectionQueueSnapshot:
        transfers = tuple(item for item in self.transfers.values() if item.batch_id == batch_id)
        files = tuple(item for item in self.files.values() if item.batch_id == batch_id)
        actions = tuple(item for item in self.host_actions.values() if item.batch_id == batch_id)
        operations = tuple(
            item for item in self.operations.values() if item.command.batch_id == batch_id
        )
        active_transfer = {
            RemoteManualSelectionTransferStatus.QUEUED,
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.RETRYING,
        }
        active_action = {
            RemoteManualSelectionHostActionStatus.QUEUED,
            RemoteManualSelectionHostActionStatus.PROCESSING,
            RemoteManualSelectionHostActionStatus.RETRY,
        }
        findings: dict[str, int] = {}
        stale = sum(
            1
            for item in transfers
            if item.status in active_transfer
            and self.transfer_updated_at.get(item.id, datetime.min.replace(tzinfo=UTC))
            <= stale_before
        )
        if stale:
            findings["REMOTE_SELECTION_STALE_TRANSFER"] = stale
        expired = 0
        for item in actions:
            lease_expires_at = self.host_action_metadata.get(
                item.id,
                (None, None, None, None, None),
            )[2]
            if (
                item.status is RemoteManualSelectionHostActionStatus.PROCESSING
                and lease_expires_at is not None
                and lease_expires_at <= now
            ):
                expired += 1
        if expired:
            findings["REMOTE_SELECTION_EXPIRED_HOST_ACTION_LEASE"] = expired
        conflicts = sum(
            1 for item in files if item.status is RemoteManualSelectionFileStatus.FAILED
        )
        if conflicts:
            findings["REMOTE_SELECTION_CONFLICT_REQUIRES_ATTENTION"] = conflicts
        if self.batches[batch_id].status is RemoteManualSelectionBatchStatus.FINALIZING:
            findings["REMOTE_SELECTION_FINALIZATION_RETRY_REQUIRED"] = 1
        return RemoteManualSelectionQueueSnapshot(
            pending_operation_count=sum(
                1
                for item in operations
                if item.status
                in {
                    RemoteManualSelectionOperationStatus.QUEUED,
                    RemoteManualSelectionOperationStatus.SENDING,
                    RemoteManualSelectionOperationStatus.RETRY,
                }
            ),
            uploading_transfer_count=sum(
                1 for item in transfers if item.status in active_transfer
            ),
            pending_transfer_bytes=sum(
                item.declared_bytes - item.received_bytes
                for item in transfers
                if item.status in active_transfer
            ),
            materializing_action_count=sum(
                1
                for item in actions
                if item.action_type is RemoteManualSelectionHostActionType.MATERIALIZE
                and item.status in active_action
            ),
            pending_host_action_count=sum(1 for item in actions if item.status in active_action),
            synced_file_count=sum(
                1 for item in files if item.status is RemoteManualSelectionFileStatus.SYNCED
            ),
            conflict_file_count=conflicts,
            recovery_findings=tuple(sorted(findings.items())),
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
        del retry_at
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
            self.transfer_paths[value.id] = temp_relative_path
            self.transfer_updated_at[value.id] = datetime.now(UTC)
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
            self.host_action_metadata[value.id] = (
                lease_owner,
                lease_token,
                lease_expires_at,
                next_attempt_at,
                None,
            )
            return value

    def ensure_materialization_action(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionHostActionV1:
        with self._lock:
            existing = next(
                (
                    action
                    for action in self.host_actions.values()
                    if action.session_id == session_id
                    and action.batch_id == batch_id
                    and action.file_id == file_id
                    and action.transfer_id == transfer_id
                    and action.generation == generation
                    and action.action_type is RemoteManualSelectionHostActionType.MATERIALIZE
                ),
                None,
            )
            if existing is not None:
                return existing
            file = self.files.get(file_id)
            transfer = self.transfers.get(transfer_id)
            if (
                file is None
                or transfer is None
                or file.session_id != session_id
                or file.batch_id != batch_id
                or not file.desired_selected
                or file.selection_generation != generation
                or file.status is not RemoteManualSelectionFileStatus.VERIFIED
                or transfer.generation != generation
                or transfer.status is not RemoteManualSelectionTransferStatus.VERIFIED
                or transfer.verified_checksum_sha256 is None
                or self.transfer_paths.get(transfer.id) is None
                or file.host_checksum_sha256 != transfer.verified_checksum_sha256
                or file.output_name is None
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_MATERIALIZATION_NOT_READY",
                    "Only a verified current selected generation can be queued for "
                    "materialization.",
                )
            action = RemoteManualSelectionHostActionV1(
                id=uuid4(),
                session_id=session_id,
                batch_id=batch_id,
                file_id=file_id,
                transfer_id=transfer_id,
                generation=generation,
                action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
                status=RemoteManualSelectionHostActionStatus.QUEUED,
                attempt=0,
            )
            return self.add_host_action(action)

    def enqueue_missing_materialization_actions(self, *, limit: int) -> int:
        if limit < 1:
            raise ValueError("Materialization reconciliation limit must be positive.")
        with self._lock:
            candidates = sorted(
                (
                    file
                    for file in self.files.values()
                    if file.desired_selected
                    and file.status is RemoteManualSelectionFileStatus.VERIFIED
                    and file.host_checksum_sha256 is not None
                    and not any(
                        action.file_id == file.id
                        and action.generation == file.selection_generation
                        and action.action_type is RemoteManualSelectionHostActionType.MATERIALIZE
                        for action in self.host_actions.values()
                    )
                ),
                key=lambda item: (str(item.batch_id), item.source_index, str(item.id)),
            )[:limit]
            created = 0
            for file in candidates:
                transfers = [
                    transfer
                    for transfer in self.transfers.values()
                    if transfer.file_id == file.id
                    and transfer.batch_id == file.batch_id
                    and transfer.session_id == file.session_id
                    and transfer.generation == file.selection_generation
                    and transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
                    and transfer.verified_checksum_sha256 == file.host_checksum_sha256
                    and self.transfer_paths.get(transfer.id) is not None
                ]
                if not transfers:
                    continue
                transfer = max(transfers, key=lambda item: (item.attempt, str(item.id)))
                self.ensure_materialization_action(
                    session_id=file.session_id,
                    batch_id=file.batch_id,
                    file_id=file.id,
                    transfer_id=transfer.id,
                    generation=file.selection_generation,
                )
                created += 1
            return created

    def claim_next_materialization_action(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> RemoteManualSelectionHostActionRecord | None:
        with self._lock:
            for pending in self.host_actions.values():
                metadata = self.host_action_metadata[pending.id]
                if pending.action_type is RemoteManualSelectionHostActionType.REMOVE and (
                    pending.status is RemoteManualSelectionHostActionStatus.QUEUED
                    or (
                        pending.status is RemoteManualSelectionHostActionStatus.RETRY
                        and (metadata[3] is None or metadata[3] <= claimed_at)
                    )
                    or (
                        pending.status is RemoteManualSelectionHostActionStatus.PROCESSING
                        and metadata[2] is not None
                        and metadata[2] <= claimed_at
                    )
                ):
                    return None
            candidates: list[RemoteManualSelectionHostActionV1] = []
            for action in self.host_actions.values():
                owner, token, expires_at, next_attempt_at, error_code = self.host_action_metadata[
                    action.id
                ]
                del owner, token, error_code
                if action.action_type is not RemoteManualSelectionHostActionType.MATERIALIZE:
                    continue
                if (
                    action.status is RemoteManualSelectionHostActionStatus.QUEUED
                    or (
                        action.status is RemoteManualSelectionHostActionStatus.RETRY
                        and (next_attempt_at is None or next_attempt_at <= claimed_at)
                    )
                    or (
                        action.status is RemoteManualSelectionHostActionStatus.PROCESSING
                        and expires_at is not None
                        and expires_at <= claimed_at
                    )
                ):
                    candidates.append(action)
            if not candidates:
                return None
            action = min(candidates, key=lambda item: (item.attempt, str(item.id)))
            token = uuid4()
            claimed = replace(
                action,
                status=RemoteManualSelectionHostActionStatus.PROCESSING,
                attempt=action.attempt + 1,
            )
            self.host_actions[action.id] = claimed
            self.host_action_metadata[action.id] = (
                lease_owner,
                token,
                claimed_at + lease_duration,
                None,
                self.host_action_metadata[action.id][4],
            )
            return RemoteManualSelectionHostActionRecord(
                action=claimed,
                lease_owner=lease_owner,
                lease_token=token,
                lease_expires_at=claimed_at + lease_duration,
                next_attempt_at=None,
                last_error_code=self.host_action_metadata[action.id][4],
            )

    def claim_next_removal_action(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> RemoteManualSelectionHostActionRecord | None:
        if not lease_owner.strip() or lease_duration.total_seconds() <= 0:
            raise ValueError("A removal lease requires an owner and positive duration.")
        with self._lock:
            candidates: list[RemoteManualSelectionHostActionV1] = []
            for action in self.host_actions.values():
                metadata = self.host_action_metadata[action.id]
                if action.action_type is not RemoteManualSelectionHostActionType.REMOVE:
                    continue
                if (
                    action.status is RemoteManualSelectionHostActionStatus.QUEUED
                    or (
                        action.status is RemoteManualSelectionHostActionStatus.RETRY
                        and (metadata[3] is None or metadata[3] <= claimed_at)
                    )
                    or (
                        action.status is RemoteManualSelectionHostActionStatus.PROCESSING
                        and metadata[2] is not None
                        and metadata[2] <= claimed_at
                    )
                ):
                    candidates.append(action)
            if not candidates:
                return None
            action = min(candidates, key=lambda item: (item.attempt, str(item.id)))
            token = uuid4()
            claimed = replace(
                action,
                status=RemoteManualSelectionHostActionStatus.PROCESSING,
                attempt=action.attempt + 1,
            )
            self.host_actions[action.id] = claimed
            self.host_action_metadata[action.id] = (
                lease_owner.strip(),
                token,
                claimed_at + lease_duration,
                None,
                self.host_action_metadata[action.id][4],
            )
            return RemoteManualSelectionHostActionRecord(
                action=claimed,
                lease_owner=lease_owner.strip(),
                lease_token=token,
                lease_expires_at=claimed_at + lease_duration,
                next_attempt_at=None,
                last_error_code=self.host_action_metadata[action.id][4],
            )

    def lock_removal_context(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        locked_at: datetime,
    ) -> RemoteManualSelectionRemovalContext | None:
        with self._lock:
            action = self.host_actions.get(action_id)
            metadata = self.host_action_metadata.get(action_id)
            if (
                action is None
                or metadata is None
                or action.action_type is not RemoteManualSelectionHostActionType.REMOVE
                or action.status is not RemoteManualSelectionHostActionStatus.PROCESSING
                or metadata[1] != lease_token
                or metadata[2] is None
                or metadata[2] <= locked_at
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                    "The removal action lease is no longer owned by this executor.",
                )
            file = self.files[action.file_id]
            transfer = None if action.transfer_id is None else self.transfers[action.transfer_id]
            if transfer is None:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The removal action references unavailable state.",
                )
            if file.selection_generation < action.generation or (
                file.selection_generation == action.generation and file.desired_selected
            ):
                self.host_actions[action.id] = replace(
                    action,
                    status=RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                self.host_action_metadata[action.id] = (None, None, None, None, metadata[4])
                return None
            materialization = next(
                (
                    item
                    for item in self.host_actions.values()
                    if item.file_id == action.file_id
                    and item.transfer_id == transfer.id
                    and item.generation == transfer.generation
                    and item.action_type is RemoteManualSelectionHostActionType.MATERIALIZE
                ),
                None,
            )
            selected = next(
                (
                    operation
                    for operation in self.operations.values()
                    if operation.command.file_id == action.file_id
                    and operation.command.selection_generation == transfer.generation
                    and operation.command.operation_type
                    is RemoteManualSelectionOperationType.SELECT
                    and operation.status is RemoteManualSelectionOperationStatus.APPLIED
                ),
                None,
            )
            if (
                materialization is None
                or selected is None
                or selected.command.output_name is None
                or transfer.verified_checksum_sha256 is None
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_REMOVAL_OWNERSHIP_MISSING",
                    "The removal action has no immutable materialization ownership proof.",
                )
            return RemoteManualSelectionRemovalContext(
                action=action,
                file=file,
                transfer=transfer,
                materialization_action_id=materialization.id,
                materialized_generation=transfer.generation,
                output_name=selected.command.output_name,
                checksum_sha256=transfer.verified_checksum_sha256,
            )

    def complete_removal_action(
        self,
        context: RemoteManualSelectionRemovalContext,
        *,
        lease_token: UUID,
        completed_at: datetime,
    ) -> RemoteManualSelectionFileV1:
        del completed_at
        with self._lock:
            action = self.host_actions.get(context.action.id)
            metadata = self.host_action_metadata.get(context.action.id)
            file = self.files.get(context.file.id)
            if (
                action is None
                or metadata is None
                or file is None
                or action.status is not RemoteManualSelectionHostActionStatus.PROCESSING
                or metadata[1] != lease_token
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                    "The removal action cannot be completed by this executor.",
                )
            if file.selection_generation < action.generation:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_REMOVAL_GENERATION_CONFLICT",
                    "The file generation is older than its removal tombstone.",
                )
            if self.file_final_paths.get(file.id) == context.output_name:
                self.file_final_paths.pop(file.id, None)
            if not file.desired_selected:
                if file.status is not RemoteManualSelectionFileStatus.REMOVED:
                    transition_remote_file_status(
                        file.status,
                        RemoteManualSelectionFileStatus.REMOVED,
                    )
                file = replace(
                    file,
                    status=RemoteManualSelectionFileStatus.REMOVED,
                    host_checksum_sha256=None,
                )
                self.files[file.id] = file
            self.host_actions[action.id] = replace(
                action,
                status=RemoteManualSelectionHostActionStatus.COMPLETED,
            )
            self.host_action_metadata[action.id] = (None, None, None, None, None)
            return file

    def lock_materialization_context(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        locked_at: datetime,
    ) -> RemoteManualSelectionMaterializationContext | None:
        with self._lock:
            action = self.host_actions.get(action_id)
            metadata = self.host_action_metadata.get(action_id)
            if (
                action is None
                or metadata is None
                or action.status is not RemoteManualSelectionHostActionStatus.PROCESSING
                or metadata[1] != lease_token
                or metadata[2] is None
                or metadata[2] <= locked_at
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                    "The materialization action lease is no longer owned by this executor.",
                )
            file = self.files.get(action.file_id)
            transfer = (
                None if action.transfer_id is None else self.transfers.get(action.transfer_id)
            )
            if file is None or transfer is None:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_SCOPE_MISMATCH",
                    "The materialization action references unavailable state.",
                )
            if (
                not file.desired_selected
                or file.selection_generation != action.generation
                or transfer.generation != action.generation
            ):
                transition_remote_host_action_status(
                    RemoteManualSelectionHostActionStatus.PROCESSING,
                    RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                self.host_actions[action.id] = replace(
                    action,
                    status=RemoteManualSelectionHostActionStatus.SUPERSEDED,
                )
                self.host_action_metadata[action.id] = (None, None, None, None, metadata[4])
                return None
            path = self.transfer_paths.get(transfer.id)
            if (
                file.status is not RemoteManualSelectionFileStatus.VERIFIED
                or transfer.status is not RemoteManualSelectionTransferStatus.VERIFIED
                or transfer.verified_checksum_sha256 is None
                or path is None
                or file.output_name is None
                or file.host_checksum_sha256 != transfer.verified_checksum_sha256
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_MATERIALIZATION_NOT_READY",
                    "The claimed action no longer has a consistent verified source.",
                )
            return RemoteManualSelectionMaterializationContext(
                action=action,
                file=file,
                transfer=transfer,
                verified_relative_path=path,
                output_name=file.output_name,
                checksum_sha256=transfer.verified_checksum_sha256,
            )

    def complete_materialization_action(
        self,
        context: RemoteManualSelectionMaterializationContext,
        *,
        lease_token: UUID,
        final_relative_path: str,
        completed_at: datetime,
    ) -> RemoteManualSelectionFileV1:
        del completed_at
        with self._lock:
            action = self.host_actions.get(context.action.id)
            metadata = self.host_action_metadata.get(context.action.id)
            file = self.files.get(context.file.id)
            transfer = self.transfers.get(context.transfer.id)
            batch = self.batches.get(context.file.batch_id)
            if (
                action is None
                or metadata is None
                or file is None
                or transfer is None
                or batch is None
                or action.status is not RemoteManualSelectionHostActionStatus.PROCESSING
                or metadata[1] != lease_token
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                    "The materialization action cannot be completed by this executor.",
                )
            if (
                not file.desired_selected
                or file.selection_generation != action.generation
                or transfer.generation != action.generation
                or transfer.verified_checksum_sha256 != context.checksum_sha256
                or file.host_checksum_sha256 != context.checksum_sha256
                or file.output_name != context.output_name
                or final_relative_path != context.output_name
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_MATERIALIZATION_GENERATION_CONFLICT",
                    "The selected generation changed before materialization commit.",
                )
            was_synced = file.status is RemoteManualSelectionFileStatus.SYNCED
            if not was_synced:
                transition_remote_file_status(
                    file.status,
                    RemoteManualSelectionFileStatus.MATERIALIZED,
                )
                transition_remote_file_status(
                    RemoteManualSelectionFileStatus.MATERIALIZED,
                    RemoteManualSelectionFileStatus.SYNCED,
                )
                transition_remote_transfer_status(
                    transfer.status,
                    RemoteManualSelectionTransferStatus.MATERIALIZED,
                )
                batch = replace(batch, server_revision=batch.server_revision + 1)
                file = replace(file, status=RemoteManualSelectionFileStatus.SYNCED)
                transfer = replace(
                    transfer,
                    status=RemoteManualSelectionTransferStatus.MATERIALIZED,
                )
                self.batches[batch.id] = batch
                self.files[file.id] = file
                self.transfers[transfer.id] = transfer
                self.file_revisions[file.id] = batch.server_revision
                self.file_final_paths[file.id] = final_relative_path
            elif self.file_final_paths.get(file.id) != final_relative_path:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_MATERIALIZATION_STATE_CONFLICT",
                    "The persisted materialized state differs from the host artifact.",
                )
            self.host_actions[action.id] = replace(
                action,
                status=RemoteManualSelectionHostActionStatus.COMPLETED,
            )
            self.host_action_metadata[action.id] = (None, None, None, None, None)
            return file

    def finish_materialization_failure(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        error_code: str,
        failed_at: datetime,
        retry_at: datetime | None,
    ) -> RemoteManualSelectionHostActionV1:
        del failed_at
        with self._lock:
            action = self.host_actions.get(action_id)
            metadata = self.host_action_metadata.get(action_id)
            if (
                action is None
                or metadata is None
                or action.status is not RemoteManualSelectionHostActionStatus.PROCESSING
                or metadata[1] != lease_token
            ):
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST",
                    "The failed materialization action lease was already replaced.",
                )
            target = (
                RemoteManualSelectionHostActionStatus.FAILED
                if retry_at is None
                else RemoteManualSelectionHostActionStatus.RETRY
            )
            transition_remote_host_action_status(action.status, target)
            updated = replace(action, status=target)
            self.host_actions[action_id] = updated
            self.host_action_metadata[action_id] = (None, None, None, retry_at, error_code)
            return updated

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
        validate_remote_selection_audit_payload(payload)
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


def _transfer_record_from_record(
    record: RemoteManualSelectionTransferModel,
) -> RemoteManualSelectionTransferRecord:
    return RemoteManualSelectionTransferRecord(
        transfer=_transfer_from_record(record),
        temp_relative_path=record.temp_relative_path,
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


def _host_action_record_from_record(
    record: RemoteManualSelectionHostActionModel,
) -> RemoteManualSelectionHostActionRecord:
    return RemoteManualSelectionHostActionRecord(
        action=_host_action_from_record(record),
        lease_owner=record.lease_owner,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        next_attempt_at=record.next_attempt_at,
        last_error_code=record.last_error_code,
    )


def _clear_action_lease(
    record: RemoteManualSelectionHostActionModel,
    *,
    updated_at: datetime,
) -> None:
    record.lease_owner = None
    record.lease_token = None
    record.lease_expires_at = None
    record.updated_at = updated_at


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


def _finalization_revision_conflict(
    server_revision: int,
) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_REVISION_CONFLICT",
        "The finalization server revision is stale.",
        details={"serverRevision": server_revision},
    )


def _source_manifest_conflict() -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_SOURCE_MANIFEST_CONFLICT",
        "Source items do not match the declared immutable manifest.",
    )


def _source_manifest_immutable() -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_SOURCE_MANIFEST_IMMUTABLE",
        "The source manifest cannot change after the batch becomes active.",
    )


def _require_page(limit: int) -> None:
    if limit < 1 or limit > 1000:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_PAGE_LIMIT_INVALID",
            "The page limit must be between 1 and 1000.",
        )


def validate_remote_selection_audit_payload(payload: dict[str, object]) -> None:
    """Reject credential-like fields and absolute host paths at any depth."""

    forbidden_fragments = {
        "authorization",
        "cookie",
        "path",
        "salt",
        "secret",
        "token",
    }
    keys = _payload_keys(payload)
    unsafe_key = bool(keys & {"accesscode", "codehash"}) or any(
        fragment in key for key in keys for fragment in forbidden_fragments
    )
    if unsafe_key or _payload_contains_absolute_windows_path(payload):
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


def _payload_contains_absolute_windows_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(_payload_contains_absolute_windows_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_payload_contains_absolute_windows_path(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.strip().replace("/", "\\")
    return (
        len(normalized) >= 3 and normalized[0].isalpha() and normalized[1:3] == ":\\"
    ) or normalized.startswith("\\\\")


__all__ = [
    "InMemoryRemoteManualSelectionRepository",
    "RemoteManualSelectionFileDelta",
    "RemoteManualSelectionFinalFileRecord",
    "RemoteManualSelectionFinalizationSnapshot",
    "RemoteManualSelectionHostActionRecord",
    "RemoteManualSelectionHostBinding",
    "RemoteManualSelectionMaterializationContext",
    "RemoteManualSelectionQueueSnapshot",
    "RemoteManualSelectionRecoveryTransferCandidate",
    "RemoteManualSelectionSessionSecrets",
    "RemoteManualSelectionSourceRegistration",
    "RemoteManualSelectionTransferRecord",
    "SqlAlchemyRemoteManualSelectionRepository",
]
