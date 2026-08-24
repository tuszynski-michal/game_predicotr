"""Transactional control plane for remote manual image selection."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessService,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionBatchMapping,
    RemoteManualSelectionHostService,
)
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
    RemoteManualSelectionOperationApplication,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationV1,
    RemoteSourceKind,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionFileDelta,
    RemoteManualSelectionHostBinding,
    RemoteManualSelectionSourceRegistration,
)


class RemoteManualSelectionControlRepository(Protocol):
    def get_host_binding_for_update(
        self, session_id: UUID
    ) -> RemoteManualSelectionHostBinding | None: ...

    def get_collection(self, collection_id: UUID) -> RemoteManualSelectionCollectionV1 | None: ...

    def add_collection(
        self, value: RemoteManualSelectionCollectionV1
    ) -> RemoteManualSelectionCollectionV1: ...

    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None: ...

    def get_batch_total_file_count(self, batch_id: UUID) -> int | None: ...

    def add_batch(
        self,
        value: RemoteManualSelectionBatchV1,
        *,
        base_binding_id: UUID,
        normalized_collection_name: str,
        normalized_batch_name: str,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchV1: ...

    def register_source_files(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        values: Sequence[RemoteManualSelectionFileV1],
        source_kind: RemoteSourceKind,
        complete: bool,
    ) -> RemoteManualSelectionSourceRegistration: ...

    def get_operation(self, operation_id: UUID) -> RemoteManualSelectionOperationV1 | None: ...

    def apply_operation(
        self, command: RemoteManualSelectionOperationCommandV1
    ) -> RemoteManualSelectionOperationApplication: ...

    def list_file_delta_records(
        self, *, batch_id: UUID, after_revision: int, limit: int
    ) -> tuple[RemoteManualSelectionFileDelta, ...]: ...


@dataclass(frozen=True, slots=True)
class CreatedRemoteManualSelectionCollection:
    collection: RemoteManualSelectionCollectionV1
    created: bool


@dataclass(frozen=True, slots=True)
class CreatedRemoteManualSelectionBatch:
    batch: RemoteManualSelectionBatchV1
    mapping: RemoteManualSelectionBatchMapping


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionStateDelta:
    batch: RemoteManualSelectionBatchV1
    files: tuple[RemoteManualSelectionFileDelta, ...]
    next_revision: int
    has_more: bool


class RemoteManualSelectionRateLimitError(RemoteManualSelectionError):
    """The bounded public control-plane budget has been exhausted."""


class RemoteManualSelectionControlRateLimiter:
    def __init__(
        self,
        *,
        limit: int = 1_200,
        window: timedelta = timedelta(minutes=1),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._limit = limit
        self._window = window
        self._now = now or (lambda: datetime.now(UTC))
        self._entries: dict[UUID, tuple[datetime, int]] = {}
        self._lock = Lock()

    def consume(self, session_id: UUID, client_instance_id: UUID) -> None:
        now = self._now()
        del client_instance_id
        key = session_id
        with self._lock:
            started_at, count = self._entries.get(key, (now, 0))
            if now - started_at >= self._window:
                started_at, count = now, 0
            if count >= self._limit:
                raise RemoteManualSelectionRateLimitError(
                    "REMOTE_SELECTION_CONTROL_RATE_LIMITED",
                    "The remote selection control request rate is too high.",
                )
            self._entries[key] = (started_at, count + 1)


class RemoteManualSelectionControlService:
    def __init__(
        self,
        repository: RemoteManualSelectionControlRepository,
        access_service: RemoteManualSelectionAccessService,
        host_service: RemoteManualSelectionHostService,
        *,
        rate_limiter: RemoteManualSelectionControlRateLimiter | None = None,
    ) -> None:
        self._repository = repository
        self._access = access_service
        self._host = host_service
        self._rate_limiter = rate_limiter or RemoteManualSelectionControlRateLimiter()

    def create_collection(
        self,
        *,
        session_id: UUID,
        collection_id: UUID,
        name: str,
        access_token: str,
        client_instance_id: UUID,
    ) -> CreatedRemoteManualSelectionCollection:
        self._access.authorize_session(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        component = self._host.validate_mapping_component(
            self._repository,
            session_id=session_id,
            value=name,
        )
        requested = RemoteManualSelectionCollectionV1(
            id=collection_id,
            session_id=session_id,
            name=component.display_name,
            normalized_name=component.normalized_name,
            status=RemoteManualSelectionCollectionStatus.ACTIVE,
            revision=0,
        )
        existing = self._repository.get_collection(collection_id)
        if existing is not None:
            if existing != requested:
                raise _idempotency_conflict("collectionId")
            return CreatedRemoteManualSelectionCollection(existing, False)
        self._authorize_writer(session_id, access_token, client_instance_id)
        try:
            created = self._repository.add_collection(requested)
        except RemoteManualSelectionConflictError:
            existing = self._repository.get_collection(collection_id)
            if existing != requested:
                raise
            return CreatedRemoteManualSelectionCollection(existing, False)
        return CreatedRemoteManualSelectionCollection(created, True)

    def create_batch(
        self,
        *,
        session_id: UUID,
        collection_id: UUID,
        batch_id: UUID,
        name: str,
        source_manifest_checksum_sha256: str,
        first_layout: int,
        direction: RemoteManualSelectionDirection,
        total_file_count: int,
        access_token: str,
        client_instance_id: UUID,
    ) -> CreatedRemoteManualSelectionBatch:
        self._access.authorize_session(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        if total_file_count < 1 or total_file_count > 100_000:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SOURCE_COUNT_INVALID",
                "The source file count must be between 1 and 100000.",
            )
        collection = self._repository.get_collection(collection_id)
        if collection is None or collection.session_id != session_id:
            raise _scope_mismatch()
        requested = RemoteManualSelectionBatchV1(
            id=batch_id,
            session_id=session_id,
            collection_id=collection_id,
            name=name,
            source_manifest_checksum_sha256=source_manifest_checksum_sha256,
            first_layout=first_layout,
            direction=direction,
            cursor_index=0,
            status=RemoteManualSelectionBatchStatus.INDEXING,
            server_revision=0,
            last_client_sequence=0,
        )
        existing = self._repository.get_batch(batch_id)
        if existing is None:
            self._authorize_writer(session_id, access_token, client_instance_id)
        mapping = self._host.provision_batch_mapping(
            self._repository,
            session_id=session_id,
            collection=collection,
            batch=requested,
            total_file_count=total_file_count,
        )
        persisted = self._repository.get_batch(batch_id)
        if (
            persisted is None
            or self._repository.get_batch_total_file_count(batch_id) != total_file_count
        ):
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_IDEMPOTENCY_CONFLICT",
                "The batch ID is already bound to different content.",
            )
        return CreatedRemoteManualSelectionBatch(persisted, mapping)

    def register_source_items(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        files: Sequence[RemoteManualSelectionFileV1],
        source_kind: RemoteSourceKind,
        complete: bool,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionSourceRegistration:
        self._access.authorize_session(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        if len(files) > 500:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SOURCE_PAGE_TOO_LARGE",
                "A source item page cannot contain more than 500 files.",
            )
        batch = self._repository.get_batch(batch_id)
        if batch is None or batch.session_id != session_id:
            raise _scope_mismatch()
        if batch.status is not RemoteManualSelectionBatchStatus.ACTIVE:
            self._authorize_writer(session_id, access_token, client_instance_id)
        return self._repository.register_source_files(
            session_id=session_id,
            batch_id=batch_id,
            values=files,
            source_kind=source_kind,
            complete=complete,
        )

    def state_delta(
        self,
        *,
        batch_id: UUID,
        since_revision: int,
        limit: int,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionStateDelta:
        context = self._access.context(
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        session_id = context.session_id
        self._rate_limiter.consume(session_id, client_instance_id)
        if since_revision < 0:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_REVISION_INVALID",
                "sinceRevision cannot be negative.",
            )
        batch = self._repository.get_batch(batch_id)
        if batch is None or batch.session_id != session_id:
            raise _scope_mismatch()
        if since_revision > batch.server_revision:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_REVISION_CONFLICT",
                "The requested server revision is ahead of canonical state.",
                details={"serverRevision": batch.server_revision},
            )
        page = self._repository.list_file_delta_records(
            batch_id=batch_id,
            after_revision=since_revision,
            limit=limit + 1,
        )
        has_more = len(page) > limit
        files = page[:limit]
        next_revision = files[-1].server_revision if has_more and files else batch.server_revision
        return RemoteManualSelectionStateDelta(batch, files, next_revision, has_more)

    def apply_operation(
        self,
        *,
        command: RemoteManualSelectionOperationCommandV1,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionOperationApplication:
        if command.client_instance_id != client_instance_id:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The operation client does not match the authenticated client.",
            )
        self._access.authorize_session(
            session_id=command.session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        if self._repository.get_operation(command.operation_id) is not None:
            return self._repository.apply_operation(command)
        self._rate_limiter.consume(command.session_id, client_instance_id)
        self._access.authorize_writer(
            session_id=command.session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        return self._repository.apply_operation(command)

    def _authorize_session(
        self, session_id: UUID, access_token: str, client_instance_id: UUID
    ) -> None:
        self._access.authorize_session(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        self._rate_limiter.consume(session_id, client_instance_id)

    def _authorize_writer(
        self, session_id: UUID, access_token: str, client_instance_id: UUID
    ) -> None:
        self._access.authorize_writer(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        self._rate_limiter.consume(session_id, client_instance_id)


def source_file(
    *,
    file_id: UUID,
    session_id: UUID,
    batch_id: UUID,
    source_index: int,
    relative_path: str,
    size_bytes: int,
    last_modified_ms: int,
    mime_type: str,
) -> RemoteManualSelectionFileV1:
    return RemoteManualSelectionFileV1(
        id=file_id,
        session_id=session_id,
        batch_id=batch_id,
        source_index=source_index,
        relative_path=relative_path,
        size_bytes=size_bytes,
        last_modified_ms=last_modified_ms,
        mime_type=mime_type,
        desired_selected=False,
        selection_generation=0,
        status=RemoteManualSelectionFileStatus.UNSELECTED,
    )


def _scope_mismatch() -> RemoteManualSelectionError:
    return RemoteManualSelectionError(
        "REMOTE_SELECTION_SCOPE_MISMATCH",
        "The resource does not belong to the remote selection session.",
    )


def _idempotency_conflict(field: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_IDEMPOTENCY_CONFLICT",
        "An idempotency identifier was already used with different content.",
        details={"field": field},
    )


__all__ = [
    "CreatedRemoteManualSelectionBatch",
    "CreatedRemoteManualSelectionCollection",
    "RemoteManualSelectionControlRateLimiter",
    "RemoteManualSelectionControlService",
    "RemoteManualSelectionRateLimitError",
    "RemoteManualSelectionStateDelta",
    "source_file",
]
