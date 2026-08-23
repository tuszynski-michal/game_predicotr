"""Pure contracts and state machines for remote manual image selection."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Literal, TypeVar
from uuid import UUID

REMOTE_SOURCE_MANIFEST_SCHEMA: Final[Literal["remote-source-manifest-v1"]] = (
    "remote-source-manifest-v1"
)
REMOTE_SELECTION_MANIFEST_SCHEMA: Final[Literal["remote-manual-image-selection-session-v1"]] = (
    "remote-manual-image-selection-session-v1"
)
REMOTE_OPERATION_SCHEMA: Final[Literal["remote-manual-selection-operation-v1"]] = (
    "remote-manual-selection-operation-v1"
)
OUTPUT_MANIFEST_SCHEMA: Final[Literal[1]] = 1
TRACE_MANIFEST_SCHEMA: Final[Literal[1]] = 1

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NATURAL_PARTS = re.compile(r"(\d+)")


class RemoteManualSelectionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RemoteManualSelectionConflictError(RemoteManualSelectionError):
    """A command conflicts with the canonical revision or operation journal."""


class RemoteManualSelectionSessionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class RemoteManualSelectionCollectionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class RemoteManualSelectionBatchStatus(StrEnum):
    DRAFT = "draft"
    INDEXING = "indexing"
    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class RemoteManualSelectionFileStatus(StrEnum):
    DISCOVERED = "discovered"
    UNSELECTED = "unselected"
    SELECTION_QUEUED = "selection_queued"
    UPLOAD_QUEUED = "upload_queued"
    UPLOADING = "uploading"
    STORED_TEMPORARILY = "stored_temporarily"
    VERIFIED = "verified"
    MATERIALIZED = "materialized"
    SYNCED = "synced"
    DESELECT_PENDING = "deselect_pending"
    REMOVED = "removed"
    FAILED = "failed"
    RETRYING = "retrying"


class RemoteManualSelectionOperationType(StrEnum):
    VIEWED = "viewed"
    SELECT = "select"
    SKIP = "skip"
    DESELECT = "deselect"
    UNDO = "undo"


class RemoteManualSelectionOperationStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    APPLIED = "applied"
    RETRY = "retry"
    SUPERSEDED = "superseded"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class RemoteManualSelectionTransferStatus(StrEnum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    STORED_TEMP = "stored_temp"
    VERIFIED = "verified"
    MATERIALIZED = "materialized"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RETRYING = "retrying"


class RemoteManualSelectionHostActionType(StrEnum):
    VERIFY = "verify"
    MATERIALIZE = "materialize"
    REMOVE = "remove"
    RECONCILE = "reconcile"


class RemoteManualSelectionHostActionStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    RETRY = "retry"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class RemoteManualSelectionDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class RemoteSourceKind(StrEnum):
    DIRECTORY_HANDLE = "directory_handle"
    WEBKITDIRECTORY_RESELECT = "webkitdirectory_reselect"


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionSessionV1:
    id: UUID
    status: RemoteManualSelectionSessionStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    schema_version: Literal["remote-manual-selection-session-v1"] = (
        "remote-manual-selection-session-v1"
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-session-v1")
        _require_non_negative(self.revision, field="revision")
        _require_time_order(self.created_at, self.updated_at, self.expires_at)


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionCollectionV1:
    id: UUID
    session_id: UUID
    name: str
    normalized_name: str
    status: RemoteManualSelectionCollectionStatus
    revision: int
    schema_version: Literal["remote-manual-selection-collection-v1"] = (
        "remote-manual-selection-collection-v1"
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-collection-v1")
        _require_text(self.name, field="name")
        _require_text(self.normalized_name, field="normalizedName")
        _require_non_negative(self.revision, field="revision")


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionBatchV1:
    id: UUID
    session_id: UUID
    collection_id: UUID
    name: str
    source_manifest_checksum_sha256: str
    first_layout: int
    direction: RemoteManualSelectionDirection
    cursor_index: int
    status: RemoteManualSelectionBatchStatus
    server_revision: int
    last_client_sequence: int
    schema_version: Literal["remote-manual-selection-batch-v1"] = "remote-manual-selection-batch-v1"

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-batch-v1")
        _require_text(self.name, field="name")
        _require_sha256(self.source_manifest_checksum_sha256, field="sourceManifestChecksumSha256")
        if self.first_layout < 1:
            raise _invalid_contract("firstLayout must be positive.", field="firstLayout")
        _require_non_negative(self.cursor_index, field="cursorIndex")
        _require_non_negative(self.server_revision, field="serverRevision")
        _require_non_negative(self.last_client_sequence, field="lastClientSequence")


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionFileV1:
    id: UUID
    session_id: UUID
    batch_id: UUID
    source_index: int
    relative_path: str
    size_bytes: int
    last_modified_ms: int
    mime_type: str
    desired_selected: bool
    selection_generation: int
    status: RemoteManualSelectionFileStatus
    range_start: int | None = None
    range_end: int | None = None
    output_name: str | None = None
    host_checksum_sha256: str | None = None
    schema_version: Literal["remote-manual-selection-file-v1"] = "remote-manual-selection-file-v1"

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-file-v1")
        _require_non_negative(self.source_index, field="sourceIndex")
        _require_safe_relative_path(self.relative_path)
        _require_non_negative(self.size_bytes, field="sizeBytes")
        _require_non_negative(self.last_modified_ms, field="lastModifiedMs")
        _require_non_negative(self.selection_generation, field="selectionGeneration")
        if (self.range_start is None) != (self.range_end is None):
            raise _invalid_contract(
                "rangeStart and rangeEnd must either both be set or both be null.",
                field="range",
            )
        if self.range_start is not None and (
            self.range_start < 1 or self.range_end != self.range_start + 8
        ):
            raise _invalid_contract(
                "A selected range must contain exactly nine layouts.",
                field="range",
            )
        if self.output_name is not None:
            _require_output_name(self.output_name)
        if self.host_checksum_sha256 is not None:
            _require_sha256(self.host_checksum_sha256, field="hostChecksumSha256")
        if self.status is RemoteManualSelectionFileStatus.SYNCED and (
            not self.desired_selected
            or None
            in (
                self.range_start,
                self.range_end,
                self.output_name,
                self.host_checksum_sha256,
            )
        ):
            raise _invalid_contract(
                "A synced file must be selected and fully materialized.",
                field="status",
            )


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionOperationCommandV1:
    operation_id: UUID
    session_id: UUID
    batch_id: UUID
    client_instance_id: UUID
    client_sequence: int
    expected_server_revision: int
    operation_type: RemoteManualSelectionOperationType
    selection_generation: int
    range_start: int
    range_end: int
    recorded_at: datetime
    file_id: UUID | None = None
    image_path: str | None = None
    source_index: int | None = None
    image_checksum_sha256: str | None = None
    output_name: str | None = None
    visible_milliseconds: int = 0
    decoded: bool = True
    target_operation_id: UUID | None = None
    schema_version: Literal["remote-manual-selection-operation-v1"] = REMOTE_OPERATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != REMOTE_OPERATION_SCHEMA:
            raise _invalid_contract("The operation schema version is unsupported.")
        if self.client_sequence < 1:
            raise _invalid_contract("clientSequence must be positive.", field="clientSequence")
        _require_non_negative(self.expected_server_revision, field="expectedServerRevision")
        _require_non_negative(self.selection_generation, field="selectionGeneration")
        if self.range_start < 1 or self.range_end != self.range_start + 8:
            raise _invalid_contract("An operation range must contain nine layouts.", field="range")
        _require_aware(self.recorded_at, field="recordedAt")
        _require_non_negative(self.visible_milliseconds, field="visibleMilliseconds")
        file_operation = self.operation_type in {
            RemoteManualSelectionOperationType.VIEWED,
            RemoteManualSelectionOperationType.SELECT,
            RemoteManualSelectionOperationType.DESELECT,
            RemoteManualSelectionOperationType.UNDO,
        }
        if file_operation != (self.file_id is not None):
            raise _invalid_contract(
                "This operation type has an invalid fileId.",
                field="fileId",
            )
        if self.image_path is not None:
            _require_safe_relative_path(self.image_path)
        if self.source_index is not None:
            _require_non_negative(self.source_index, field="sourceIndex")
        if self.image_checksum_sha256 is not None:
            _require_sha256(self.image_checksum_sha256, field="imageChecksumSha256")
        if self.output_name is not None:
            _require_output_name(self.output_name)
        if self.operation_type is RemoteManualSelectionOperationType.SELECT and (
            self.image_path is None or self.source_index is None or self.output_name is None
        ):
            raise _invalid_contract(
                "A select operation requires imagePath, sourceIndex and outputName.",
            )
        if (
            self.operation_type
            in {
                RemoteManualSelectionOperationType.DESELECT,
                RemoteManualSelectionOperationType.UNDO,
            }
            and self.target_operation_id is None
        ):
            raise _invalid_contract("Undo and deselect require targetOperationId.")

    def payload(self) -> dict[str, object]:
        return {
            "batchId": str(self.batch_id),
            "clientInstanceId": str(self.client_instance_id),
            "clientSequence": self.client_sequence,
            "decoded": self.decoded,
            "expectedServerRevision": self.expected_server_revision,
            "fileId": None if self.file_id is None else str(self.file_id),
            "imageChecksumSha256": self.image_checksum_sha256,
            "imagePath": self.image_path,
            "operationId": str(self.operation_id),
            "operationType": self.operation_type.value,
            "outputName": self.output_name,
            "rangeEnd": self.range_end,
            "rangeStart": self.range_start,
            "recordedAt": _isoformat(self.recorded_at),
            "schemaVersion": self.schema_version,
            "selectionGeneration": self.selection_generation,
            "sessionId": str(self.session_id),
            "sourceIndex": self.source_index,
            "targetOperationId": (
                None if self.target_operation_id is None else str(self.target_operation_id)
            ),
            "visibleMilliseconds": self.visible_milliseconds,
        }

    @property
    def checksum_sha256(self) -> str:
        return canonical_remote_checksum_sha256(self.payload())


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionOperationV1:
    command: RemoteManualSelectionOperationCommandV1
    command_checksum_sha256: str
    status: RemoteManualSelectionOperationStatus
    applied_server_revision: int
    outcome_code: str
    schema_version: Literal["remote-manual-selection-operation-result-v1"] = (
        "remote-manual-selection-operation-result-v1"
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-operation-result-v1")
        _require_sha256(self.command_checksum_sha256, field="commandChecksumSha256")
        if self.command_checksum_sha256 != self.command.checksum_sha256:
            raise _invalid_contract("The operation checksum does not match its command.")
        _require_non_negative(self.applied_server_revision, field="appliedServerRevision")
        _require_text(self.outcome_code, field="outcomeCode")


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionTransferV1:
    id: UUID
    session_id: UUID
    batch_id: UUID
    file_id: UUID
    generation: int
    attempt: int
    declared_bytes: int
    received_bytes: int
    status: RemoteManualSelectionTransferStatus
    declared_checksum_sha256: str | None = None
    verified_checksum_sha256: str | None = None
    schema_version: Literal["remote-manual-selection-transfer-v1"] = (
        "remote-manual-selection-transfer-v1"
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-transfer-v1")
        _require_non_negative(self.generation, field="generation")
        if self.attempt < 1:
            raise _invalid_contract("attempt must be positive.", field="attempt")
        _require_non_negative(self.declared_bytes, field="declaredBytes")
        _require_non_negative(self.received_bytes, field="receivedBytes")
        if self.received_bytes > self.declared_bytes:
            raise _invalid_contract("receivedBytes cannot exceed declaredBytes.")
        for field, checksum in (
            ("declaredChecksumSha256", self.declared_checksum_sha256),
            ("verifiedChecksumSha256", self.verified_checksum_sha256),
        ):
            if checksum is not None:
                _require_sha256(checksum, field=field)


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionHostActionV1:
    id: UUID
    session_id: UUID
    batch_id: UUID
    file_id: UUID
    transfer_id: UUID | None
    generation: int
    action_type: RemoteManualSelectionHostActionType
    status: RemoteManualSelectionHostActionStatus
    attempt: int
    schema_version: Literal["remote-manual-selection-host-action-v1"] = (
        "remote-manual-selection-host-action-v1"
    )

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, "remote-manual-selection-host-action-v1")
        _require_non_negative(self.generation, field="generation")
        if self.attempt < 0:
            raise _invalid_contract("attempt cannot be negative.", field="attempt")


@dataclass(frozen=True, slots=True)
class RemoteSourceManifestEntryV1:
    ordinal: int
    relative_path: str
    name: str
    size_bytes: int
    last_modified_ms: int
    mime_type: str

    def __post_init__(self) -> None:
        _require_non_negative(self.ordinal, field="ordinal")
        normalized = _require_safe_relative_path(self.relative_path)
        if self.relative_path != normalized:
            raise _invalid_source("relativePath must be normalized to NFC.")
        if self.name != normalized.rsplit("/", 1)[-1] or not self.name.lower().endswith(
            (".jpg", ".jpeg")
        ):
            raise _invalid_source("name must match the final JPEG path component.")
        _require_non_negative(self.size_bytes, field="sizeBytes")
        _require_non_negative(self.last_modified_ms, field="lastModifiedMs")

    def payload(self) -> dict[str, object]:
        return {
            "lastModifiedMs": self.last_modified_ms,
            "mimeType": self.mime_type,
            "name": self.name,
            "ordinal": self.ordinal,
            "relativePath": self.relative_path,
            "sizeBytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class RemoteSourceManifestV1:
    source_kind: RemoteSourceKind
    entries: tuple[RemoteSourceManifestEntryV1, ...]
    manifest_checksum_sha256: str
    schema_version: Literal["remote-source-manifest-v1"] = REMOTE_SOURCE_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != REMOTE_SOURCE_MANIFEST_SCHEMA:
            raise _invalid_source("The source manifest version is unsupported.")
        if not _SHA256.fullmatch(self.manifest_checksum_sha256):
            raise _invalid_source("manifestChecksumSha256 must be a lowercase SHA-256 value.")
        expected_paths = sorted(
            (item.relative_path for item in self.entries),
            key=_natural_path_key,
        )
        if [item.ordinal for item in self.entries] != list(range(len(self.entries))):
            raise _invalid_source("Source ordinals must be contiguous and zero-based.")
        if [item.relative_path for item in self.entries] != expected_paths:
            raise _invalid_source("Source entries must use deterministic natural order.")
        if len(set(expected_paths)) != len(expected_paths):
            raise _invalid_source("Source relative paths must be unique.")
        if self.manifest_checksum_sha256 != canonical_remote_checksum_sha256(
            self.payload_without_checksum()
        ):
            raise _invalid_source("The source manifest checksum does not match its content.")

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.entries)

    def payload_without_checksum(self) -> dict[str, object]:
        return {
            "entries": [item.payload() for item in self.entries],
            "fileCount": self.file_count,
            "schemaVersion": self.schema_version,
            "sourceKind": self.source_kind.value,
            "totalBytes": self.total_bytes,
        }

    def payload(self) -> dict[str, object]:
        return {
            **self.payload_without_checksum(),
            "manifestChecksumSha256": self.manifest_checksum_sha256,
        }


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionManifestV1:
    session_id: UUID
    collection_id: UUID
    batch: RemoteManualSelectionBatchV1
    files: tuple[RemoteManualSelectionFileV1, ...]
    operations: tuple[RemoteManualSelectionOperationV1, ...]
    transfers: tuple[RemoteManualSelectionTransferV1, ...]
    host_actions: tuple[RemoteManualSelectionHostActionV1, ...]
    generated_at: datetime
    schema_version: Literal["remote-manual-image-selection-session-v1"] = (
        REMOTE_SELECTION_MANIFEST_SCHEMA
    )

    def __post_init__(self) -> None:
        if self.schema_version != REMOTE_SELECTION_MANIFEST_SCHEMA:
            raise _invalid_contract("The remote selection manifest version is unsupported.")
        _require_aware(self.generated_at, field="generatedAt")
        if (
            self.batch.session_id != self.session_id
            or self.batch.collection_id != self.collection_id
        ):
            _raise_scope_mismatch("batch", self.batch.id)
        for file in self.files:
            _require_scope(self.session_id, self.batch.id, file.session_id, file.batch_id, "file")
        file_ids = {file.id for file in self.files}
        if len(file_ids) != len(self.files):
            raise _invalid_contract("Remote manifest file IDs must be unique.")
        operation_ids = {operation.command.operation_id for operation in self.operations}
        if len(operation_ids) != len(self.operations):
            raise _invalid_contract("Remote manifest operation IDs must be unique.")
        for operation in self.operations:
            _require_scope(
                self.session_id,
                self.batch.id,
                operation.command.session_id,
                operation.command.batch_id,
                "operation",
            )
            if operation.command.file_id is not None and operation.command.file_id not in file_ids:
                _raise_scope_mismatch("operationFile", operation.command.file_id)
        transfer_ids = {transfer.id for transfer in self.transfers}
        if len(transfer_ids) != len(self.transfers):
            raise _invalid_contract("Remote manifest transfer IDs must be unique.")
        for transfer in self.transfers:
            _require_scope(
                self.session_id,
                self.batch.id,
                transfer.session_id,
                transfer.batch_id,
                "transfer",
            )
            if transfer.file_id not in file_ids:
                _raise_scope_mismatch("transferFile", transfer.file_id)
        for action in self.host_actions:
            _require_scope(
                self.session_id,
                self.batch.id,
                action.session_id,
                action.batch_id,
                "hostAction",
            )
            if action.file_id not in file_ids:
                _raise_scope_mismatch("hostActionFile", action.file_id)
            if action.transfer_id is not None and action.transfer_id not in transfer_ids:
                _raise_scope_mismatch("hostActionTransfer", action.transfer_id)

    def payload(self) -> dict[str, object]:
        return {
            "batch": _batch_payload(self.batch),
            "collectionId": str(self.collection_id),
            "files": [_file_payload(item) for item in self.files],
            "generatedAt": _isoformat(self.generated_at),
            "hostActions": [_host_action_payload(item) for item in self.host_actions],
            "operations": [_operation_payload(item) for item in self.operations],
            "schemaVersion": self.schema_version,
            "sessionId": str(self.session_id),
            "transfers": [_transfer_payload(item) for item in self.transfers],
        }

    @property
    def checksum_sha256(self) -> str:
        return canonical_remote_checksum_sha256(self.payload())


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionOperationApplication:
    batch: RemoteManualSelectionBatchV1
    file: RemoteManualSelectionFileV1 | None
    operation: RemoteManualSelectionOperationV1
    exact_retry: bool


_SESSION_TRANSITIONS = {
    RemoteManualSelectionSessionStatus.DRAFT: frozenset(
        {RemoteManualSelectionSessionStatus.ACTIVE, RemoteManualSelectionSessionStatus.REVOKED}
    ),
    RemoteManualSelectionSessionStatus.ACTIVE: frozenset(
        {
            RemoteManualSelectionSessionStatus.COMPLETED,
            RemoteManualSelectionSessionStatus.EXPIRED,
            RemoteManualSelectionSessionStatus.REVOKED,
        }
    ),
}
_COLLECTION_TRANSITIONS = {
    RemoteManualSelectionCollectionStatus.ACTIVE: frozenset(
        {RemoteManualSelectionCollectionStatus.COMPLETED}
    )
}
_BATCH_TRANSITIONS = {
    RemoteManualSelectionBatchStatus.DRAFT: frozenset(
        {RemoteManualSelectionBatchStatus.INDEXING, RemoteManualSelectionBatchStatus.ABANDONED}
    ),
    RemoteManualSelectionBatchStatus.INDEXING: frozenset(
        {
            RemoteManualSelectionBatchStatus.ACTIVE,
            RemoteManualSelectionBatchStatus.FAILED,
            RemoteManualSelectionBatchStatus.ABANDONED,
        }
    ),
    RemoteManualSelectionBatchStatus.ACTIVE: frozenset(
        {
            RemoteManualSelectionBatchStatus.FINALIZING,
            RemoteManualSelectionBatchStatus.FAILED,
            RemoteManualSelectionBatchStatus.ABANDONED,
        }
    ),
    RemoteManualSelectionBatchStatus.FINALIZING: frozenset(
        {RemoteManualSelectionBatchStatus.COMPLETED, RemoteManualSelectionBatchStatus.FAILED}
    ),
    RemoteManualSelectionBatchStatus.FAILED: frozenset(
        {
            RemoteManualSelectionBatchStatus.INDEXING,
            RemoteManualSelectionBatchStatus.ACTIVE,
            RemoteManualSelectionBatchStatus.FINALIZING,
            RemoteManualSelectionBatchStatus.ABANDONED,
        }
    ),
}
_FILE_TRANSITIONS = {
    RemoteManualSelectionFileStatus.DISCOVERED: frozenset(
        {RemoteManualSelectionFileStatus.UNSELECTED}
    ),
    RemoteManualSelectionFileStatus.UNSELECTED: frozenset(
        {RemoteManualSelectionFileStatus.SELECTION_QUEUED}
    ),
    RemoteManualSelectionFileStatus.SELECTION_QUEUED: frozenset(
        {
            RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.UPLOAD_QUEUED: frozenset(
        {
            RemoteManualSelectionFileStatus.UPLOADING,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.UPLOADING: frozenset(
        {
            RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.STORED_TEMPORARILY: frozenset(
        {
            RemoteManualSelectionFileStatus.VERIFIED,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.VERIFIED: frozenset(
        {
            RemoteManualSelectionFileStatus.MATERIALIZED,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.MATERIALIZED: frozenset(
        {
            RemoteManualSelectionFileStatus.SYNCED,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.SYNCED: frozenset(
        {RemoteManualSelectionFileStatus.DESELECT_PENDING}
    ),
    RemoteManualSelectionFileStatus.DESELECT_PENDING: frozenset(
        {
            RemoteManualSelectionFileStatus.UNSELECTED,
            RemoteManualSelectionFileStatus.REMOVED,
            RemoteManualSelectionFileStatus.SELECTION_QUEUED,
            RemoteManualSelectionFileStatus.FAILED,
        }
    ),
    RemoteManualSelectionFileStatus.REMOVED: frozenset(
        {RemoteManualSelectionFileStatus.SELECTION_QUEUED}
    ),
    RemoteManualSelectionFileStatus.FAILED: frozenset(
        {RemoteManualSelectionFileStatus.RETRYING, RemoteManualSelectionFileStatus.DESELECT_PENDING}
    ),
    RemoteManualSelectionFileStatus.RETRYING: frozenset(
        {
            RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
            RemoteManualSelectionFileStatus.UNSELECTED,
            RemoteManualSelectionFileStatus.DESELECT_PENDING,
        }
    ),
}
_OPERATION_TRANSITIONS = {
    RemoteManualSelectionOperationStatus.QUEUED: frozenset(
        {RemoteManualSelectionOperationStatus.SENDING}
    ),
    RemoteManualSelectionOperationStatus.SENDING: frozenset(
        {
            RemoteManualSelectionOperationStatus.APPLIED,
            RemoteManualSelectionOperationStatus.RETRY,
            RemoteManualSelectionOperationStatus.SUPERSEDED,
            RemoteManualSelectionOperationStatus.CONFLICT,
            RemoteManualSelectionOperationStatus.REJECTED,
        }
    ),
    RemoteManualSelectionOperationStatus.RETRY: frozenset(
        {RemoteManualSelectionOperationStatus.SENDING}
    ),
    RemoteManualSelectionOperationStatus.APPLIED: frozenset(
        {RemoteManualSelectionOperationStatus.SUPERSEDED}
    ),
}
_TRANSFER_TRANSITIONS = {
    RemoteManualSelectionTransferStatus.QUEUED: frozenset(
        {
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.CANCELLED,
        }
    ),
    RemoteManualSelectionTransferStatus.UPLOADING: frozenset(
        {
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.CANCELLED,
            RemoteManualSelectionTransferStatus.FAILED,
        }
    ),
    RemoteManualSelectionTransferStatus.STORED_TEMP: frozenset(
        {
            RemoteManualSelectionTransferStatus.VERIFIED,
            RemoteManualSelectionTransferStatus.FAILED,
        }
    ),
    RemoteManualSelectionTransferStatus.VERIFIED: frozenset(
        {RemoteManualSelectionTransferStatus.MATERIALIZED}
    ),
    RemoteManualSelectionTransferStatus.FAILED: frozenset(
        {RemoteManualSelectionTransferStatus.RETRYING}
    ),
    RemoteManualSelectionTransferStatus.RETRYING: frozenset(
        {
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.CANCELLED,
        }
    ),
}
_HOST_ACTION_TRANSITIONS = {
    RemoteManualSelectionHostActionStatus.QUEUED: frozenset(
        {
            RemoteManualSelectionHostActionStatus.PROCESSING,
            RemoteManualSelectionHostActionStatus.SUPERSEDED,
        }
    ),
    RemoteManualSelectionHostActionStatus.PROCESSING: frozenset(
        {
            RemoteManualSelectionHostActionStatus.COMPLETED,
            RemoteManualSelectionHostActionStatus.RETRY,
            RemoteManualSelectionHostActionStatus.FAILED,
            RemoteManualSelectionHostActionStatus.SUPERSEDED,
        }
    ),
    RemoteManualSelectionHostActionStatus.RETRY: frozenset(
        {RemoteManualSelectionHostActionStatus.PROCESSING}
    ),
}

S = TypeVar("S", bound=StrEnum)


def transition_remote_session_status(
    current: RemoteManualSelectionSessionStatus,
    target: RemoteManualSelectionSessionStatus,
) -> RemoteManualSelectionSessionStatus:
    return _transition(current, target, _SESSION_TRANSITIONS, entity="session")


def transition_remote_collection_status(
    current: RemoteManualSelectionCollectionStatus,
    target: RemoteManualSelectionCollectionStatus,
) -> RemoteManualSelectionCollectionStatus:
    return _transition(current, target, _COLLECTION_TRANSITIONS, entity="collection")


def transition_remote_batch_status(
    current: RemoteManualSelectionBatchStatus,
    target: RemoteManualSelectionBatchStatus,
) -> RemoteManualSelectionBatchStatus:
    return _transition(current, target, _BATCH_TRANSITIONS, entity="batch")


def transition_remote_file_status(
    current: RemoteManualSelectionFileStatus,
    target: RemoteManualSelectionFileStatus,
) -> RemoteManualSelectionFileStatus:
    return _transition(current, target, _FILE_TRANSITIONS, entity="file")


def transition_remote_operation_status(
    current: RemoteManualSelectionOperationStatus,
    target: RemoteManualSelectionOperationStatus,
) -> RemoteManualSelectionOperationStatus:
    return _transition(current, target, _OPERATION_TRANSITIONS, entity="operation")


def transition_remote_transfer_status(
    current: RemoteManualSelectionTransferStatus,
    target: RemoteManualSelectionTransferStatus,
) -> RemoteManualSelectionTransferStatus:
    return _transition(current, target, _TRANSFER_TRANSITIONS, entity="transfer")


def transition_remote_host_action_status(
    current: RemoteManualSelectionHostActionStatus,
    target: RemoteManualSelectionHostActionStatus,
) -> RemoteManualSelectionHostActionStatus:
    return _transition(current, target, _HOST_ACTION_TRANSITIONS, entity="hostAction")


def parse_remote_operation_type(value: str) -> RemoteManualSelectionOperationType:
    try:
        return RemoteManualSelectionOperationType(value)
    except ValueError as cause:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_OPERATION_TYPE_INVALID",
            "The remote selection operation type is unsupported.",
            details={"operationType": value},
        ) from cause


def build_remote_source_manifest(
    entries: tuple[RemoteSourceManifestEntryV1, ...],
    *,
    source_kind: RemoteSourceKind,
) -> RemoteSourceManifestV1:
    ordered_values = sorted(entries, key=lambda item: _natural_path_key(item.relative_path))
    ordered = tuple(replace(item, ordinal=index) for index, item in enumerate(ordered_values))
    without_checksum: dict[str, object] = {
        "entries": [item.payload() for item in ordered],
        "fileCount": len(ordered),
        "schemaVersion": REMOTE_SOURCE_MANIFEST_SCHEMA,
        "sourceKind": source_kind.value,
        "totalBytes": sum(item.size_bytes for item in ordered),
    }
    return RemoteSourceManifestV1(
        source_kind=source_kind,
        entries=ordered,
        manifest_checksum_sha256=canonical_remote_checksum_sha256(without_checksum),
    )


def apply_remote_manual_selection_operation(
    batch: RemoteManualSelectionBatchV1,
    file: RemoteManualSelectionFileV1 | None,
    command: RemoteManualSelectionOperationCommandV1,
    *,
    existing_operation: RemoteManualSelectionOperationV1 | None = None,
) -> RemoteManualSelectionOperationApplication:
    _require_scope(
        batch.session_id,
        batch.id,
        command.session_id,
        command.batch_id,
        "operation",
    )
    if command.file_id is not None:
        if file is None or file.id != command.file_id:
            _raise_scope_mismatch("file", command.file_id)
        assert file is not None
        _require_scope(batch.session_id, batch.id, file.session_id, file.batch_id, "file")
    elif file is not None:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_SCOPE_MISMATCH",
            "A batch-scoped operation cannot receive a file.",
        )
    if existing_operation is not None:
        if existing_operation.command.operation_id != command.operation_id:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_OPERATION_ID_MISMATCH",
                "The stored operation has a different operationId.",
            )
        if existing_operation.command_checksum_sha256 != command.checksum_sha256:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_OPERATION_IDEMPOTENCY_CONFLICT",
                "The operationId was already used with a different command.",
                details={"operationId": str(command.operation_id)},
            )
        return RemoteManualSelectionOperationApplication(
            batch=batch,
            file=file,
            operation=existing_operation,
            exact_retry=True,
        )

    if batch.status is not RemoteManualSelectionBatchStatus.ACTIVE:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_BATCH_NOT_ACTIVE",
            "Operations can only be applied to an active batch.",
            details={"batchId": str(batch.id), "status": batch.status.value},
        )
    expected_sequence = batch.last_client_sequence + 1
    if command.client_sequence < expected_sequence:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY",
            "A consumed clientSequence requires its original operationId.",
            details={"expectedClientSequence": expected_sequence},
        )
    if command.client_sequence > expected_sequence:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_CLIENT_SEQUENCE_GAP",
            "The operation cannot skip a clientSequence value.",
            details={"expectedClientSequence": expected_sequence},
        )
    if command.expected_server_revision != batch.server_revision:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_REVISION_CONFLICT",
            "The operational server revision is stale.",
            details={"serverRevision": batch.server_revision},
        )

    next_batch = replace(batch, last_client_sequence=command.client_sequence)
    next_file = file
    file_mutation = command.operation_type in {
        RemoteManualSelectionOperationType.SELECT,
        RemoteManualSelectionOperationType.DESELECT,
        RemoteManualSelectionOperationType.UNDO,
    }
    if file_mutation:
        assert file is not None
        if command.selection_generation <= file.selection_generation:
            operation = _operation_result(
                command,
                status=RemoteManualSelectionOperationStatus.SUPERSEDED,
                revision=batch.server_revision,
                outcome="stale_generation",
            )
            return RemoteManualSelectionOperationApplication(
                batch=next_batch,
                file=file,
                operation=operation,
                exact_retry=False,
            )
        if command.selection_generation != file.selection_generation + 1:
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_GENERATION_GAP",
                "selectionGeneration must increase by exactly one.",
                details={"currentGeneration": file.selection_generation},
            )
        if command.operation_type is RemoteManualSelectionOperationType.SELECT:
            next_file = replace(
                file,
                desired_selected=True,
                selection_generation=command.selection_generation,
                status=RemoteManualSelectionFileStatus.SELECTION_QUEUED,
                range_start=command.range_start,
                range_end=command.range_end,
                output_name=command.output_name,
                host_checksum_sha256=None,
            )
        else:
            next_file = replace(
                file,
                desired_selected=False,
                selection_generation=command.selection_generation,
                status=RemoteManualSelectionFileStatus.DESELECT_PENDING,
                host_checksum_sha256=None,
            )

    next_revision = batch.server_revision + 1
    next_batch = replace(
        next_batch,
        server_revision=next_revision,
        cursor_index=max(
            batch.cursor_index,
            command.source_index if command.source_index is not None else batch.cursor_index,
        ),
    )
    operation = _operation_result(
        command,
        status=RemoteManualSelectionOperationStatus.APPLIED,
        revision=next_revision,
        outcome="applied",
    )
    return RemoteManualSelectionOperationApplication(
        batch=next_batch,
        file=next_file,
        operation=operation,
        exact_retry=False,
    )


def project_manual_selection_output_v1(
    *,
    workspace_id: str,
    session_key: str,
    source_directory_name: str,
    direction: RemoteManualSelectionDirection,
    first_layout: int,
    files: tuple[RemoteManualSelectionFileV1, ...],
    updated_at: datetime,
) -> dict[str, object]:
    _require_text(workspace_id, field="gameId")
    _require_text(session_key, field="sessionKey")
    _require_text(source_directory_name, field="sourceDirectoryName")
    _require_aware(updated_at, field="updatedAt")
    items: list[dict[str, object]] = []
    seen_ranges: set[tuple[int, int]] = set()
    for file in sorted(
        (item for item in files if item.desired_selected),
        key=lambda item: (
            item.range_start if item.range_start is not None else 2**63,
            item.source_index,
        ),
    ):
        if file.status is not RemoteManualSelectionFileStatus.SYNCED or None in (
            file.range_start,
            file.range_end,
            file.output_name,
            file.host_checksum_sha256,
        ):
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_PROJECTION_INCOMPLETE",
                "A selected file is not fully synchronized.",
                details={"fileId": str(file.id)},
            )
        assert file.range_start is not None
        assert file.range_end is not None
        assert file.output_name is not None
        assert file.host_checksum_sha256 is not None
        range_key = (file.range_start, file.range_end)
        if range_key in seen_ranges:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_PROJECTION_DUPLICATE_RANGE",
                "A final range has more than one selected file.",
                details={"rangeStart": file.range_start},
            )
        seen_ranges.add(range_key)
        items.append(
            {
                "imageChecksum": file.host_checksum_sha256,
                "imagePath": file.relative_path,
                "outputName": file.output_name,
                "rangeEnd": file.range_end,
                "rangeStart": file.range_start,
            }
        )
    return {
        "direction": direction.value,
        "firstLayout": first_layout,
        "gameId": workspace_id,
        "items": items,
        "schemaVersion": OUTPUT_MANIFEST_SCHEMA,
        "sessionKey": session_key,
        "sourceDirectoryName": source_directory_name,
        "updatedAt": _isoformat(updated_at),
    }


def project_manual_selection_trace_v1(
    *,
    workspace_id: str,
    session_key: str,
    source_directory_name: str,
    direction: RemoteManualSelectionDirection,
    first_layout: int,
    operations: tuple[RemoteManualSelectionOperationV1, ...],
    exported_at: datetime,
) -> dict[str, object]:
    _require_aware(exported_at, field="exportedAt")
    events: list[dict[str, object]] = []
    decision_ordinal = 0
    decision_ordinals_by_operation: dict[UUID, int] = {}
    for operation in sorted(
        operations,
        key=lambda item: (
            item.command.client_sequence,
            str(item.command.operation_id),
        ),
    ):
        if operation.status not in {
            RemoteManualSelectionOperationStatus.APPLIED,
            RemoteManualSelectionOperationStatus.SUPERSEDED,
        }:
            continue
        command = operation.command
        kind = _trace_kind(command.operation_type)
        if kind is None:
            continue
        event: dict[str, object] = {
            "decoded": command.decoded,
            "eventIndex": len(events),
            "gameId": workspace_id,
            "imagePath": command.image_path,
            "kind": kind,
            "rangeEnd": command.range_end,
            "rangeStart": command.range_start,
            "recordedAt": _isoformat(command.recorded_at),
            "sessionKey": session_key,
            "sourceIndex": command.source_index,
            "visibleMilliseconds": command.visible_milliseconds,
        }
        if kind == "accepted":
            decision_ordinals_by_operation[command.operation_id] = decision_ordinal
            event.update(
                {
                    "decisionOrdinal": decision_ordinal,
                    "imageChecksum": command.image_checksum_sha256,
                    "outputName": command.output_name,
                    "revertsDecisionOrdinal": None,
                }
            )
            decision_ordinal += 1
        elif kind == "skipped":
            decision_ordinals_by_operation[command.operation_id] = decision_ordinal
            event.update(
                {
                    "decisionOrdinal": decision_ordinal,
                    "imageChecksum": None,
                    "outputName": None,
                    "revertsDecisionOrdinal": None,
                }
            )
            decision_ordinal += 1
        elif kind == "undo":
            event.update(
                {
                    "decisionOrdinal": None,
                    "imageChecksum": None,
                    "outputName": None,
                    "revertsDecisionOrdinal": (
                        decision_ordinals_by_operation.get(command.target_operation_id)
                        if command.target_operation_id is not None
                        else None
                    ),
                }
            )
        events.append(event)
    return {
        "direction": direction.value,
        "events": events,
        "exportedAt": _isoformat(exported_at),
        "firstLayout": first_layout,
        "gameId": workspace_id,
        "schemaVersion": TRACE_MANIFEST_SCHEMA,
        "sessionKey": session_key,
        "sourceDirectoryName": source_directory_name,
    }


def canonical_remote_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_remote_checksum_sha256(value: object) -> str:
    return hashlib.sha256(canonical_remote_json_bytes(value)).hexdigest()


def _operation_result(
    command: RemoteManualSelectionOperationCommandV1,
    *,
    status: RemoteManualSelectionOperationStatus,
    revision: int,
    outcome: str,
) -> RemoteManualSelectionOperationV1:
    return RemoteManualSelectionOperationV1(
        command=command,
        command_checksum_sha256=command.checksum_sha256,
        status=status,
        applied_server_revision=revision,
        outcome_code=outcome,
    )


def _trace_kind(operation_type: RemoteManualSelectionOperationType) -> str | None:
    return {
        RemoteManualSelectionOperationType.VIEWED: "viewed",
        RemoteManualSelectionOperationType.SELECT: "accepted",
        RemoteManualSelectionOperationType.SKIP: "skipped",
        RemoteManualSelectionOperationType.DESELECT: "undo",
        RemoteManualSelectionOperationType.UNDO: "undo",
    }.get(operation_type)


def _transition(
    current: S,
    target: S,
    allowed: Mapping[S, frozenset[S]],
    *,
    entity: str,
) -> S:
    if current == target:
        return current
    if target not in allowed.get(current, frozenset()):
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_INVALID_TRANSITION",
            f"The {entity} transition is not allowed.",
            details={"entity": entity, "from": current.value, "to": target.value},
        )
    return target


def _require_scope(
    expected_session_id: UUID,
    expected_batch_id: UUID,
    session_id: UUID,
    batch_id: UUID,
    entity: str,
) -> None:
    if expected_session_id != session_id or expected_batch_id != batch_id:
        _raise_scope_mismatch(entity, batch_id)


def _raise_scope_mismatch(entity: str, entity_id: object) -> None:
    raise RemoteManualSelectionError(
        "REMOTE_SELECTION_SCOPE_MISMATCH",
        "A referenced identifier does not belong to the remote selection scope.",
        details={"entity": entity, "entityId": str(entity_id)},
    )


def _require_time_order(created_at: datetime, updated_at: datetime, expires_at: datetime) -> None:
    for field, value in (
        ("createdAt", created_at),
        ("updatedAt", updated_at),
        ("expiresAt", expires_at),
    ):
        _require_aware(value, field=field)
    if updated_at < created_at or expires_at <= created_at:
        raise _invalid_contract("Session timestamps are not monotonic.")


def _require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _invalid_contract(f"{field} must include a timezone.", field=field)


def _isoformat(value: datetime) -> str:
    _require_aware(value, field="timestamp")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _require_non_negative(value: int, *, field: str) -> None:
    if value < 0:
        raise _invalid_contract(f"{field} cannot be negative.", field=field)


def _require_text(value: str, *, field: str) -> None:
    if not value.strip():
        raise _invalid_contract(f"{field} cannot be blank.", field=field)


def _require_sha256(value: str, *, field: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise _invalid_contract(f"{field} must be a lowercase SHA-256 checksum.", field=field)


def _require_safe_relative_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or "\x00" in normalized
        or "\\" in normalized
        or normalized.startswith("/")
        or normalized.endswith("/")
        or re.match(r"^[a-zA-Z]:", normalized)
    ):
        raise _invalid_source("An absolute or malformed source path is not allowed.")
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise _invalid_source("A source path contains a forbidden segment.")
    return normalized


def _require_output_name(value: str) -> None:
    if re.fullmatch(r"seq_[1-9]\d*-[1-9]\d*\.jpg", value) is None:
        raise _invalid_contract("outputName must use seq_<start>-<end>.jpg.", field="outputName")


def _natural_path_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in _NATURAL_PARTS.split(value)
        if part
    )


def _invalid_contract(message: str, *, field: str | None = None) -> RemoteManualSelectionError:
    details: dict[str, object] = {} if field is None else {"field": field}
    return RemoteManualSelectionError(
        "REMOTE_SELECTION_CONTRACT_INVALID",
        message,
        details=details,
    )


def _invalid_source(message: str) -> RemoteManualSelectionError:
    return RemoteManualSelectionError("REMOTE_SELECTION_SOURCE_MANIFEST_INVALID", message)


def _require_schema(actual: str, expected: str) -> None:
    if actual != expected:
        raise _invalid_contract(
            "The contract schema version is unsupported.",
            field="schemaVersion",
        )


def _batch_payload(batch: RemoteManualSelectionBatchV1) -> dict[str, object]:
    return {
        "collectionId": str(batch.collection_id),
        "cursorIndex": batch.cursor_index,
        "direction": batch.direction.value,
        "firstLayout": batch.first_layout,
        "id": str(batch.id),
        "lastClientSequence": batch.last_client_sequence,
        "name": batch.name,
        "schemaVersion": batch.schema_version,
        "serverRevision": batch.server_revision,
        "sessionId": str(batch.session_id),
        "sourceManifestChecksumSha256": batch.source_manifest_checksum_sha256,
        "status": batch.status.value,
    }


def _file_payload(file: RemoteManualSelectionFileV1) -> dict[str, object]:
    return {
        "batchId": str(file.batch_id),
        "desiredSelected": file.desired_selected,
        "hostChecksumSha256": file.host_checksum_sha256,
        "id": str(file.id),
        "lastModifiedMs": file.last_modified_ms,
        "mimeType": file.mime_type,
        "outputName": file.output_name,
        "rangeEnd": file.range_end,
        "rangeStart": file.range_start,
        "relativePath": file.relative_path,
        "schemaVersion": file.schema_version,
        "selectionGeneration": file.selection_generation,
        "sessionId": str(file.session_id),
        "sizeBytes": file.size_bytes,
        "sourceIndex": file.source_index,
        "status": file.status.value,
    }


def _operation_payload(operation: RemoteManualSelectionOperationV1) -> dict[str, object]:
    return {
        "appliedServerRevision": operation.applied_server_revision,
        "command": operation.command.payload(),
        "commandChecksumSha256": operation.command_checksum_sha256,
        "outcomeCode": operation.outcome_code,
        "schemaVersion": operation.schema_version,
        "status": operation.status.value,
    }


def _transfer_payload(transfer: RemoteManualSelectionTransferV1) -> dict[str, object]:
    return {
        "attempt": transfer.attempt,
        "batchId": str(transfer.batch_id),
        "declaredBytes": transfer.declared_bytes,
        "declaredChecksumSha256": transfer.declared_checksum_sha256,
        "fileId": str(transfer.file_id),
        "generation": transfer.generation,
        "id": str(transfer.id),
        "receivedBytes": transfer.received_bytes,
        "schemaVersion": transfer.schema_version,
        "sessionId": str(transfer.session_id),
        "status": transfer.status.value,
        "verifiedChecksumSha256": transfer.verified_checksum_sha256,
    }


def _host_action_payload(action: RemoteManualSelectionHostActionV1) -> dict[str, object]:
    return {
        "actionType": action.action_type.value,
        "attempt": action.attempt,
        "batchId": str(action.batch_id),
        "fileId": str(action.file_id),
        "generation": action.generation,
        "id": str(action.id),
        "schemaVersion": action.schema_version,
        "sessionId": str(action.session_id),
        "status": action.status.value,
        "transferId": None if action.transfer_id is None else str(action.transfer_id),
    }


__all__ = [
    "REMOTE_OPERATION_SCHEMA",
    "REMOTE_SELECTION_MANIFEST_SCHEMA",
    "REMOTE_SOURCE_MANIFEST_SCHEMA",
    "RemoteManualSelectionBatchStatus",
    "RemoteManualSelectionBatchV1",
    "RemoteManualSelectionCollectionStatus",
    "RemoteManualSelectionCollectionV1",
    "RemoteManualSelectionConflictError",
    "RemoteManualSelectionDirection",
    "RemoteManualSelectionError",
    "RemoteManualSelectionFileStatus",
    "RemoteManualSelectionFileV1",
    "RemoteManualSelectionHostActionStatus",
    "RemoteManualSelectionHostActionType",
    "RemoteManualSelectionHostActionV1",
    "RemoteManualSelectionManifestV1",
    "RemoteManualSelectionOperationApplication",
    "RemoteManualSelectionOperationCommandV1",
    "RemoteManualSelectionOperationStatus",
    "RemoteManualSelectionOperationType",
    "RemoteManualSelectionOperationV1",
    "RemoteManualSelectionSessionStatus",
    "RemoteManualSelectionSessionV1",
    "RemoteManualSelectionTransferStatus",
    "RemoteManualSelectionTransferV1",
    "RemoteSourceKind",
    "RemoteSourceManifestEntryV1",
    "RemoteSourceManifestV1",
    "apply_remote_manual_selection_operation",
    "build_remote_source_manifest",
    "canonical_remote_checksum_sha256",
    "canonical_remote_json_bytes",
    "parse_remote_operation_type",
    "project_manual_selection_output_v1",
    "project_manual_selection_trace_v1",
    "transition_remote_batch_status",
    "transition_remote_collection_status",
    "transition_remote_file_status",
    "transition_remote_host_action_status",
    "transition_remote_operation_status",
    "transition_remote_session_status",
    "transition_remote_transfer_status",
]
