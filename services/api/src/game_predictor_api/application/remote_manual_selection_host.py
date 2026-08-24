"""Host-only base capability and ownership-bound directory provisioning."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.application.controlled_folder_picker import WindowsFolderPicker
from game_predictor_api.application.remote_manual_selection_path_safety import (
    LockedWindowsBase,
    ValidatedWindowsComponent,
    WindowsPathGuard,
    validate_windows_component,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionHostBinding,
)

BASE_CAPABILITY_TTL = timedelta(minutes=5)
OWNERSHIP_SCHEMA = "remote-manual-selection-ownership-v1"
OWNERSHIP_DIRECTORY = ".game-predictor"
OWNERSHIP_VERSION_DIRECTORY = "remote-selection-v1"
OWNERSHIP_MARKER_NAME = "ownership.json"
MAX_OWNERSHIP_MARKER_BYTES = 16 * 1024


class RemoteManualSelectionHostRepository(Protocol):
    def get_host_binding(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionHostBinding | None: ...

    def get_host_binding_for_update(
        self,
        session_id: UUID,
    ) -> RemoteManualSelectionHostBinding | None: ...

    def get_collection(
        self,
        collection_id: UUID,
    ) -> RemoteManualSelectionCollectionV1 | None: ...

    def add_collection(
        self,
        value: RemoteManualSelectionCollectionV1,
    ) -> RemoteManualSelectionCollectionV1: ...

    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None: ...

    def add_batch(
        self,
        value: RemoteManualSelectionBatchV1,
        *,
        base_binding_id: UUID,
        normalized_collection_name: str,
        normalized_batch_name: str,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchV1: ...


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionBaseCapability:
    capability: str
    display_name: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ConsumedRemoteManualSelectionBase:
    """Host-internal value consumed by the future session creation service."""

    base_binding_id: UUID
    host_base_path: Path
    display_name: str


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionBatchMapping:
    session_id: UUID
    collection_id: UUID
    batch_id: UUID
    collection_name: str
    batch_name: str
    created: bool
    resumed: bool


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionTransferDirectory:
    """Host-internal transfer directory kept below a verified batch mapping."""

    path: Path
    relative_path: str


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionMaterializationScope:
    """Pinned owned paths for one atomic host materialization attempt."""

    source_path: Path
    target_path: Path
    working_path: Path
    journal_path: Path
    final_relative_path: str
    pin_target: Callable[[], None]


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionRemovalScope:
    """Pinned owned paths for one checksum-guarded quarantine attempt."""

    target_path: Path
    quarantine_path: Path
    removal_journal_path: Path
    materialization_journal_path: Path
    quarantine_relative_path: str
    quarantine_target: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class _StoredBaseCapability:
    value: RemoteManualSelectionBaseCapability
    base_binding_id: UUID
    host_base_path: Path


@dataclass(frozen=True, slots=True)
class _OwnershipMarker:
    session_id: UUID
    collection_id: UUID
    batch_id: UUID
    base_binding_id: UUID
    normalized_collection_name: str
    normalized_batch_name: str

    def payload(self) -> dict[str, object]:
        return {
            "baseBindingId": str(self.base_binding_id),
            "batchId": str(self.batch_id),
            "collectionId": str(self.collection_id),
            "normalizedBatchName": self.normalized_batch_name,
            "normalizedCollectionName": self.normalized_collection_name,
            "schemaVersion": OWNERSHIP_SCHEMA,
            "sessionId": str(self.session_id),
        }

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload())).hexdigest()

    def encoded(self) -> bytes:
        return (
            _canonical_json(
                {
                    **self.payload(),
                    "ownershipChecksumSha256": self.checksum_sha256,
                }
            )
            + b"\n"
        )


class RemoteManualSelectionHostService:
    """Local-only host filesystem boundary for remote manual selection."""

    def __init__(
        self,
        picker: WindowsFolderPicker | Callable[[], Path | None],
        *,
        path_guard: WindowsPathGuard | None = None,
        clock: Callable[[], datetime] | None = None,
        capability_ttl: timedelta = BASE_CAPABILITY_TTL,
    ) -> None:
        self._picker = picker.choose if isinstance(picker, WindowsFolderPicker) else picker
        self._path_guard = path_guard or WindowsPathGuard()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._capability_ttl = capability_ttl
        self._capabilities: dict[str, _StoredBaseCapability] = {}
        self._lock = Lock()
        self._picker_lock = Lock()
        self._mapping_lock = Lock()

    def select_base(self) -> RemoteManualSelectionBaseCapability | None:
        if not self._picker_lock.acquire(blocking=False):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_BASE_PICKER_ALREADY_OPEN",
                "A host base selection window is already open.",
            )
        try:
            selected_path = self._picker()
        finally:
            self._picker_lock.release()
        if selected_path is None:
            return None
        bound = self._path_guard.inspect_base(selected_path)
        now = self._clock()
        capability = RemoteManualSelectionBaseCapability(
            capability=token_urlsafe(32),
            display_name=bound.display_name,
            expires_at=now + self._capability_ttl,
        )
        stored = _StoredBaseCapability(
            value=capability,
            base_binding_id=uuid4(),
            host_base_path=bound.final_path,
        )
        with self._lock:
            self._drop_expired(now)
            self._capabilities[capability.capability] = stored
        return capability

    def consume_base_capability(self, capability: str) -> ConsumedRemoteManualSelectionBase:
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            stored = self._capabilities.pop(capability, None)
        if stored is None:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_BASE_CAPABILITY_INVALID",
                "The host base capability is invalid or expired.",
            )
        rebound = self._path_guard.inspect_base(stored.host_base_path)
        if _path_key(rebound.final_path) != _path_key(stored.host_base_path):
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_PATH_UNSAFE",
                "The selected host base final path changed.",
            )
        return ConsumedRemoteManualSelectionBase(
            base_binding_id=stored.base_binding_id,
            host_base_path=rebound.final_path,
            display_name=stored.value.display_name,
        )

    def validate_mapping_component(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        value: str,
    ) -> ValidatedWindowsComponent:
        binding = repository.get_host_binding(session_id)
        if binding is None:
            raise _scope_error()
        with self._path_guard.lock_base(Path(binding.host_base_path)) as locked:
            return validate_windows_component(value, limits=locked.bound_base.limits)

    def provision_batch_mapping(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        collection: RemoteManualSelectionCollectionV1,
        batch: RemoteManualSelectionBatchV1,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchMapping:
        with self._mapping_lock:
            return self._provision_batch_mapping_exclusive(
                repository,
                session_id=session_id,
                collection=collection,
                batch=batch,
                total_file_count=total_file_count,
            )

    def _provision_batch_mapping_exclusive(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        collection: RemoteManualSelectionCollectionV1,
        batch: RemoteManualSelectionBatchV1,
        total_file_count: int,
    ) -> RemoteManualSelectionBatchMapping:
        if collection.session_id != session_id or batch.session_id != session_id:
            raise _scope_error()
        if batch.collection_id != collection.id:
            raise _scope_error()
        binding = repository.get_host_binding_for_update(session_id)
        if binding is None:
            raise _scope_error()

        with self._path_guard.lock_base(Path(binding.host_base_path)) as locked:
            collection_component = validate_windows_component(
                collection.name,
                limits=locked.bound_base.limits,
            )
            batch_component = validate_windows_component(
                batch.name,
                limits=locked.bound_base.limits,
            )
            if collection.normalized_name != collection_component.normalized_name:
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_PATH_NORMALIZATION_MISMATCH",
                    "The collection normalized name does not match the Windows key.",
                )

            existing_collection = repository.get_collection(collection.id)
            if existing_collection is None:
                try:
                    repository.add_collection(collection)
                except RemoteManualSelectionConflictError:
                    existing_collection = repository.get_collection(collection.id)
                    if existing_collection != collection:
                        raise
            elif existing_collection != collection:
                raise _scope_error()

            existing_batch = repository.get_batch(batch.id)
            if existing_batch is None:
                try:
                    repository.add_batch(
                        batch,
                        base_binding_id=binding.base_binding_id,
                        normalized_collection_name=collection_component.normalized_name,
                        normalized_batch_name=batch_component.normalized_name,
                        total_file_count=total_file_count,
                    )
                except RemoteManualSelectionConflictError:
                    existing_batch = repository.get_batch(batch.id)
                    if existing_batch is None:
                        raise
                    _assert_same_batch_identity(existing_batch, batch)
            else:
                _assert_same_batch_identity(existing_batch, batch)

            marker = _OwnershipMarker(
                session_id=session_id,
                collection_id=collection.id,
                batch_id=batch.id,
                base_binding_id=binding.base_binding_id,
                normalized_collection_name=collection_component.normalized_name,
                normalized_batch_name=batch_component.normalized_name,
            )
            resumed = self._provision_filesystem(
                locked,
                collection_component=collection_component,
                batch_component=batch_component,
                marker=marker,
                database_mapping_exists=existing_batch is not None,
            )
        return RemoteManualSelectionBatchMapping(
            session_id=session_id,
            collection_id=collection.id,
            batch_id=batch.id,
            collection_name=collection_component.display_name,
            batch_name=batch_component.display_name,
            created=existing_batch is None,
            resumed=resumed,
        )

    @contextmanager
    def open_transfer_directory(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> Iterator[RemoteManualSelectionTransferDirectory]:
        """Open a non-reparse host-internal directory for one file generation."""

        if generation < 1:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_GENERATION_INVALID",
                "The transfer generation must be positive.",
            )
        binding = repository.get_host_binding_for_update(session_id)
        batch = repository.get_batch(batch_id)
        if binding is None or batch is None or batch.session_id != session_id:
            raise _scope_error()
        collection = repository.get_collection(batch.collection_id)
        if collection is None or collection.session_id != session_id:
            raise _scope_error()
        with self._path_guard.lock_base(Path(binding.host_base_path)) as locked:
            collection_component = validate_windows_component(
                collection.name,
                limits=locked.bound_base.limits,
            )
            batch_component = validate_windows_component(
                batch.name,
                limits=locked.bound_base.limits,
            )
            collection_path = locked.open_existing_child(
                locked.bound_base.final_path,
                collection_component,
            )
            if collection_path is None:
                raise _path_conflict("The persisted collection directory is missing.")
            batch_path = locked.open_existing_child(collection_path, batch_component)
            if batch_path is None:
                raise _path_conflict("The persisted batch directory is missing.")
            marker = _OwnershipMarker(
                session_id=session_id,
                collection_id=collection.id,
                batch_id=batch.id,
                base_binding_id=binding.base_binding_id,
                normalized_collection_name=collection.normalized_name,
                normalized_batch_name=batch.name.casefold(),
            )
            self._verify_marker(locked, batch_path, marker)
            components = (
                OWNERSHIP_DIRECTORY,
                OWNERSHIP_VERSION_DIRECTORY,
                "transfers",
                str(file_id),
                str(generation),
            )
            current = batch_path
            for value in components:
                current, _created = locked.open_or_create_child(
                    current,
                    validate_windows_component(value, limits=locked.bound_base.limits),
                )
            yield RemoteManualSelectionTransferDirectory(
                path=current,
                relative_path="/".join(components),
            )

    @contextmanager
    def open_materialization_scope(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
        action_id: UUID,
        generation: int,
        output_name: str,
        verified_relative_path: str,
    ) -> Iterator[RemoteManualSelectionMaterializationScope]:
        """Resolve only owned transfer and output paths while directory handles stay pinned."""

        if generation < 1:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_GENERATION_INVALID",
                "The materialization generation must be positive.",
            )
        binding = repository.get_host_binding_for_update(session_id)
        batch = repository.get_batch(batch_id)
        if binding is None or batch is None or batch.session_id != session_id:
            raise _scope_error()
        collection = repository.get_collection(batch.collection_id)
        if collection is None or collection.session_id != session_id:
            raise _scope_error()
        with self._path_guard.lock_base(Path(binding.host_base_path)) as locked:
            collection_component = validate_windows_component(
                collection.name,
                limits=locked.bound_base.limits,
            )
            batch_component = validate_windows_component(
                batch.name,
                limits=locked.bound_base.limits,
            )
            output_component = validate_windows_component(
                output_name,
                limits=locked.bound_base.limits,
            )
            collection_path = locked.open_existing_child(
                locked.bound_base.final_path,
                collection_component,
            )
            if collection_path is None:
                raise _path_conflict("The persisted collection directory is missing.")
            batch_path = locked.open_existing_child(collection_path, batch_component)
            if batch_path is None:
                raise _path_conflict("The persisted batch directory is missing.")
            marker = _OwnershipMarker(
                session_id=session_id,
                collection_id=collection.id,
                batch_id=batch.id,
                base_binding_id=binding.base_binding_id,
                normalized_collection_name=collection_component.normalized_name,
                normalized_batch_name=batch_component.normalized_name,
            )
            self._verify_marker(locked, batch_path, marker)
            transfer_components = (
                OWNERSHIP_DIRECTORY,
                OWNERSHIP_VERSION_DIRECTORY,
                "transfers",
                str(file_id),
                str(generation),
            )
            transfer_directory = batch_path
            for value in transfer_components:
                child = locked.open_existing_child(
                    transfer_directory,
                    validate_windows_component(value, limits=locked.bound_base.limits),
                )
                if child is None:
                    raise _path_conflict("The verified transfer directory is missing.")
                transfer_directory = child
            verified_name = f"{transfer_id}.verified"
            expected_relative_path = "/".join((*transfer_components, verified_name))
            if verified_relative_path != expected_relative_path:
                raise RemoteManualSelectionConflictError(
                    "REMOTE_SELECTION_TRANSFER_PATH_CONFLICT",
                    "The verified transfer path does not match its immutable identity.",
                )
            source_path = transfer_directory / verified_name
            locked.hold_regular_file(source_path)

            journal_directory = batch_path
            for value in (
                OWNERSHIP_DIRECTORY,
                OWNERSHIP_VERSION_DIRECTORY,
                "materializations",
                str(file_id),
                str(generation),
            ):
                journal_directory, _created = locked.open_or_create_child(
                    journal_directory,
                    validate_windows_component(value, limits=locked.bound_base.limits),
                )
            target_path = batch_path / output_component.display_name
            if target_path.exists():
                locked.hold_regular_file(target_path)
            yield RemoteManualSelectionMaterializationScope(
                source_path=source_path,
                target_path=target_path,
                working_path=journal_directory / f"{action_id}.materializing",
                journal_path=journal_directory / f"{action_id}.json",
                final_relative_path=output_component.display_name,
                pin_target=lambda: locked.hold_regular_file(target_path),
            )

    @contextmanager
    def open_removal_scope(
        self,
        repository: RemoteManualSelectionHostRepository,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
        materialization_action_id: UUID,
        removal_action_id: UUID,
        materialized_generation: int,
        tombstone_generation: int,
        output_name: str,
    ) -> Iterator[RemoteManualSelectionRemovalScope]:
        """Resolve an owned final target and its internal reversible quarantine."""

        if materialized_generation < 1 or tombstone_generation <= materialized_generation:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_GENERATION_INVALID",
                "A removal tombstone must be newer than its materialized generation.",
            )
        binding = repository.get_host_binding_for_update(session_id)
        batch = repository.get_batch(batch_id)
        if binding is None or batch is None or batch.session_id != session_id:
            raise _scope_error()
        collection = repository.get_collection(batch.collection_id)
        if collection is None or collection.session_id != session_id:
            raise _scope_error()
        with self._path_guard.lock_base(Path(binding.host_base_path)) as locked:
            collection_component = validate_windows_component(
                collection.name,
                limits=locked.bound_base.limits,
            )
            batch_component = validate_windows_component(
                batch.name,
                limits=locked.bound_base.limits,
            )
            output_component = validate_windows_component(
                output_name,
                limits=locked.bound_base.limits,
            )
            collection_path = locked.open_existing_child(
                locked.bound_base.final_path,
                collection_component,
            )
            if collection_path is None:
                raise _path_conflict("The persisted collection directory is missing.")
            batch_path = locked.open_existing_child(collection_path, batch_component)
            if batch_path is None:
                raise _path_conflict("The persisted batch directory is missing.")
            marker = _OwnershipMarker(
                session_id=session_id,
                collection_id=collection.id,
                batch_id=batch.id,
                base_binding_id=binding.base_binding_id,
                normalized_collection_name=collection_component.normalized_name,
                normalized_batch_name=batch_component.normalized_name,
            )
            self._verify_marker(locked, batch_path, marker)

            materialization_directory = batch_path
            for value in (
                OWNERSHIP_DIRECTORY,
                OWNERSHIP_VERSION_DIRECTORY,
                "materializations",
                str(file_id),
                str(materialized_generation),
            ):
                child = locked.open_existing_child(
                    materialization_directory,
                    validate_windows_component(value, limits=locked.bound_base.limits),
                )
                if child is None:
                    raise _path_conflict("The materialization ownership directory is missing.")
                materialization_directory = child

            quarantine_components = (
                OWNERSHIP_DIRECTORY,
                OWNERSHIP_VERSION_DIRECTORY,
                "quarantine",
                str(file_id),
                str(tombstone_generation),
            )
            quarantine_directory = batch_path
            for value in quarantine_components:
                quarantine_directory, _created = locked.open_or_create_child(
                    quarantine_directory,
                    validate_windows_component(value, limits=locked.bound_base.limits),
                )
            quarantine_name = f"{removal_action_id}.jpg"
            quarantine_path = quarantine_directory / quarantine_name
            target_path = batch_path / output_component.display_name
            if quarantine_path.exists():
                locked.hold_regular_file(quarantine_path)
            yield RemoteManualSelectionRemovalScope(
                target_path=target_path,
                quarantine_path=quarantine_path,
                removal_journal_path=quarantine_directory / f"{removal_action_id}.json",
                materialization_journal_path=(
                    materialization_directory / f"{materialization_action_id}.json"
                ),
                quarantine_relative_path="/".join((*quarantine_components, quarantine_name)),
                quarantine_target=lambda checksum: locked.quarantine_regular_file(
                    target_path,
                    quarantine_path,
                    expected_checksum_sha256=checksum,
                ),
            )

    def _provision_filesystem(
        self,
        locked: LockedWindowsBase,
        *,
        collection_component: ValidatedWindowsComponent,
        batch_component: ValidatedWindowsComponent,
        marker: _OwnershipMarker,
        database_mapping_exists: bool,
    ) -> bool:
        collection = collection_component
        batch = batch_component
        base_path = locked.bound_base.final_path
        existing_collection_path = locked.open_existing_child(base_path, collection)
        if database_mapping_exists and existing_collection_path is None:
            raise _path_conflict("The persisted collection directory is missing.")
        collection_path, _collection_created = (
            locked.open_or_create_child(base_path, collection)
            if existing_collection_path is None
            else (existing_collection_path, False)
        )
        existing_batch_path = locked.open_existing_child(collection_path, batch)
        if database_mapping_exists and existing_batch_path is None:
            raise _path_conflict("The persisted batch directory is missing.")
        batch_path, batch_created = (
            locked.open_or_create_child(collection_path, batch)
            if existing_batch_path is None
            else (existing_batch_path, False)
        )
        if batch_created:
            self._create_marker(locked, batch_path, marker)
            return False
        self._verify_marker(locked, batch_path, marker)
        return True

    def _create_marker(
        self,
        locked: LockedWindowsBase,
        batch_path: Path,
        expected: _OwnershipMarker,
    ) -> None:
        internal_component = validate_windows_component(
            OWNERSHIP_DIRECTORY,
            limits=locked.bound_base.limits,
        )
        version_component = validate_windows_component(
            OWNERSHIP_VERSION_DIRECTORY,
            limits=locked.bound_base.limits,
        )
        internal_path, _created = locked.open_or_create_child(batch_path, internal_component)
        version_path, _created = locked.open_or_create_child(internal_path, version_component)
        marker_path = version_path / OWNERSHIP_MARKER_NAME
        if marker_path.exists():
            self._verify_marker_at_path(locked, marker_path, expected)
            return
        temporary_path = version_path / f".{OWNERSHIP_MARKER_NAME}.{uuid4().hex}.tmp"
        descriptor = -1
        try:
            descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = -1
                stream.write(expected.encoded())
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Windows rename in one directory is atomic and does not replace
                # an existing destination.  This also works on volumes without
                # hard-link support.
                os.rename(temporary_path, marker_path)
            except FileExistsError:
                self._verify_marker_at_path(locked, marker_path, expected)
        except OSError as error:
            raise _path_conflict("The ownership marker could not be created atomically.") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    def _verify_marker(
        self,
        locked: LockedWindowsBase,
        batch_path: Path,
        expected: _OwnershipMarker,
    ) -> None:
        internal_component = validate_windows_component(
            OWNERSHIP_DIRECTORY,
            limits=locked.bound_base.limits,
        )
        version_component = validate_windows_component(
            OWNERSHIP_VERSION_DIRECTORY,
            limits=locked.bound_base.limits,
        )
        internal_path = locked.open_existing_child(batch_path, internal_component)
        if internal_path is None:
            raise _path_conflict("The existing batch has no ownership marker.")
        version_path = locked.open_existing_child(internal_path, version_component)
        if version_path is None:
            raise _path_conflict("The existing batch has no ownership marker.")
        marker_path = version_path / OWNERSHIP_MARKER_NAME
        if not marker_path.exists():
            raise _path_conflict("The existing batch has no ownership marker.")
        self._verify_marker_at_path(locked, marker_path, expected)

    def _verify_marker_at_path(
        self,
        locked: LockedWindowsBase,
        marker_path: Path,
        expected: _OwnershipMarker,
    ) -> None:
        payload = locked.read_regular_file(
            marker_path,
            max_bytes=MAX_OWNERSHIP_MARKER_BYTES,
        )
        actual = _parse_ownership_marker(payload)
        if actual != expected:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_OWNERSHIP_CONFLICT",
                "The existing batch belongs to a different or invalid mapping.",
            )

    def _drop_expired(self, now: datetime) -> None:
        expired = [
            token for token, stored in self._capabilities.items() if stored.value.expires_at <= now
        ]
        for token in expired:
            self._capabilities.pop(token, None)


def _parse_ownership_marker(payload: bytes) -> _OwnershipMarker:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _path_conflict("The ownership marker is invalid.") from error
    expected_keys = {
        "baseBindingId",
        "batchId",
        "collectionId",
        "normalizedBatchName",
        "normalizedCollectionName",
        "ownershipChecksumSha256",
        "schemaVersion",
        "sessionId",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise _path_conflict("The ownership marker is invalid.")
    if value.get("schemaVersion") != OWNERSHIP_SCHEMA:
        raise _path_conflict("The ownership marker schema is unsupported.")
    checksum = value.pop("ownershipChecksumSha256", None)
    if (
        not isinstance(checksum, str)
        or checksum != hashlib.sha256(_canonical_json(value)).hexdigest()
    ):
        raise _path_conflict("The ownership marker checksum is invalid.")
    try:
        return _OwnershipMarker(
            session_id=UUID(str(value["sessionId"])),
            collection_id=UUID(str(value["collectionId"])),
            batch_id=UUID(str(value["batchId"])),
            base_binding_id=UUID(str(value["baseBindingId"])),
            normalized_collection_name=str(value["normalizedCollectionName"]),
            normalized_batch_name=str(value["normalizedBatchName"]),
        )
    except (ValueError, TypeError, KeyError) as error:
        raise _path_conflict("The ownership marker is invalid.") from error


def _assert_same_batch_identity(
    existing: RemoteManualSelectionBatchV1,
    requested: RemoteManualSelectionBatchV1,
) -> None:
    if (
        existing.id != requested.id
        or existing.session_id != requested.session_id
        or existing.collection_id != requested.collection_id
        or existing.name != requested.name
        or existing.source_manifest_checksum_sha256 != requested.source_manifest_checksum_sha256
        or existing.first_layout != requested.first_layout
        or existing.direction != requested.direction
    ):
        raise _scope_error()


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _scope_error() -> RemoteManualSelectionError:
    return RemoteManualSelectionError(
        "REMOTE_SELECTION_SCOPE_MISMATCH",
        "The host mapping scope is invalid.",
    )


def _path_conflict(message: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError("REMOTE_SELECTION_PATH_COLLISION", message)


__all__ = [
    "BASE_CAPABILITY_TTL",
    "ConsumedRemoteManualSelectionBase",
    "RemoteManualSelectionBaseCapability",
    "RemoteManualSelectionBatchMapping",
    "RemoteManualSelectionTransferDirectory",
    "RemoteManualSelectionHostService",
]
