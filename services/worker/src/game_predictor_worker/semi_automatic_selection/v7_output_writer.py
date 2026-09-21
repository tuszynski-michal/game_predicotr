"""Crash-safe V7 first-output writer for a local NTFS output directory.

Only this module writes the `seq_*.jpg` output.  It persists the intent before
copying, publishes with an NTFS hard-link that cannot replace a target, and
uses one advisory process lock for the complete check-to-commit critical
section. Manual replacement uses the same journal, generation and shared lock,
so recovery keeps an old committed operation as history after a new owner
replaces its target.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import NoReturn, cast
from uuid import UUID

from .contracts import SemiAutomaticSelectionRange
from .local_source_manifest import (
    LocalSourceManifest,
    LocalSourceManifestError,
    resolve_local_source_asset,
)
from .v7_run_state import V7PinnedSourceManifest, V7RunStateError

V7_OUTPUT_JOURNAL_SCHEMA_VERSION = 1
V7_OUTPUT_WRITER_VERSION = "v7-output-writer-v1"
_STATE_DIRECTORY = ".v7-selection-output"
_JOURNAL_FILE = "journal.json"
_LOCK_FILE = "directory.lock"
_TEMP_PREFIX = "output-"


class V7OutputWriterError(ValueError):
    """A stable failure that never silently overwrites a local target."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class V7OutputOperationState(StrEnum):
    PREPARED = "prepared"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    COMMITTED = "committed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    CONFLICT = "conflict"


class V7OutputDecisionKind(StrEnum):
    AUTOMATIC_FIRST = "automatic_first"
    MANUAL_FIRST = "manual_first"
    MANUAL_NO_OCR = "manual_no_ocr"
    MANUAL_REPLACE = "manual_replace"


@dataclass(frozen=True, slots=True)
class V7FirstOutputRequest:
    """The immutable identity of one automatic first-output command."""

    operation_id: UUID
    sequence_range: SemiAutomaticSelectionRange
    source_index: int
    source_relative_path: str
    source_size_bytes: int
    source_checksum_sha256: str
    decision_generation: int = 0

    def __post_init__(self) -> None:
        if (
            self.sequence_range.board_count != 9
            or self.source_index < 0
            or self.source_size_bytes < 1
            or self.decision_generation < 0
            or not self.source_relative_path
            or not _is_sha256(self.source_checksum_sha256)
        ):
            _fail("V7_OUTPUT_REQUEST_INVALID", "V7 first-output request is invalid.")

    @property
    def target_name(self) -> str:
        return f"seq_{self.sequence_range.start}-{self.sequence_range.end}.jpg"

    @property
    def decision_kind(self) -> V7OutputDecisionKind:
        return V7OutputDecisionKind.AUTOMATIC_FIRST

    @property
    def operator_confirmed_range(self) -> bool:
        return False

    @property
    def expected_previous_checksum_sha256(self) -> None:
        return None

    @property
    def expected_previous_owner_operation_id(self) -> None:
        return None

    @property
    def command_fingerprint(self) -> str:
        return _fingerprint(
            {
                "decisionGeneration": self.decision_generation,
                # Kept byte-for-byte compatible with journal operations
                # created by T08 before manual decision kinds existed.
                "kind": "automatic_first_write",
                "rangeEnd": self.sequence_range.end,
                "rangeStart": self.sequence_range.start,
                "sourceChecksumSha256": self.source_checksum_sha256,
                "sourceIndex": self.source_index,
                "sourceRelativePath": self.source_relative_path,
                "sourceSizeBytes": self.source_size_bytes,
                "targetName": self.target_name,
                "version": V7_OUTPUT_WRITER_VERSION,
            }
        )


@dataclass(frozen=True, slots=True)
class V7ManualOutputRequest:
    """A confirmed manual output command, optionally replacing a current target."""

    operation_id: UUID
    sequence_range: SemiAutomaticSelectionRange
    source_index: int
    source_relative_path: str
    source_size_bytes: int
    source_checksum_sha256: str
    decision_kind: V7OutputDecisionKind
    decision_generation: int = 0
    operator_confirmed_range: bool = False
    expected_previous_checksum_sha256: str | None = None
    expected_previous_owner_operation_id: UUID | None = None

    def __post_init__(self) -> None:
        partial_range = 1 <= self.sequence_range.board_count <= 9
        has_expected_target = (
            self.expected_previous_checksum_sha256 is not None
            and self.expected_previous_owner_operation_id is not None
        )
        valid_kind = self.decision_kind in {
            V7OutputDecisionKind.MANUAL_FIRST,
            V7OutputDecisionKind.MANUAL_NO_OCR,
            V7OutputDecisionKind.MANUAL_REPLACE,
        }
        requires_confirmation = self.decision_kind in {
            V7OutputDecisionKind.MANUAL_NO_OCR,
            V7OutputDecisionKind.MANUAL_REPLACE,
        }
        is_replace = self.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE
        if (
            not valid_kind
            or not partial_range
            or self.source_index < 0
            or self.source_size_bytes < 1
            or self.decision_generation < 0
            or not self.source_relative_path
            or not _is_sha256(self.source_checksum_sha256)
            or (
                self.expected_previous_owner_operation_id is not None
                and not isinstance(self.expected_previous_owner_operation_id, UUID)
            )
            or (requires_confirmation and not self.operator_confirmed_range)
            or (is_replace and not has_expected_target)
            or (
                not is_replace
                and (
                    self.expected_previous_checksum_sha256 is not None
                    or self.expected_previous_owner_operation_id is not None
                )
            )
            or (
                self.expected_previous_checksum_sha256 is not None
                and not _is_sha256(self.expected_previous_checksum_sha256)
            )
        ):
            _fail("V7_OUTPUT_REQUEST_INVALID", "V7 manual output request is invalid.")

    @property
    def target_name(self) -> str:
        return f"seq_{self.sequence_range.start}-{self.sequence_range.end}.jpg"

    @property
    def command_fingerprint(self) -> str:
        return _fingerprint(
            {
                "decisionGeneration": self.decision_generation,
                "expectedPreviousChecksumSha256": self.expected_previous_checksum_sha256,
                "expectedPreviousOwnerOperationId": (
                    None
                    if self.expected_previous_owner_operation_id is None
                    else str(self.expected_previous_owner_operation_id)
                ),
                "kind": self.decision_kind.value,
                "operatorConfirmedRange": self.operator_confirmed_range,
                "rangeEnd": self.sequence_range.end,
                "rangeStart": self.sequence_range.start,
                "sourceChecksumSha256": self.source_checksum_sha256,
                "sourceIndex": self.source_index,
                "sourceRelativePath": self.source_relative_path,
                "sourceSizeBytes": self.source_size_bytes,
                "targetName": self.target_name,
                "version": V7_OUTPUT_WRITER_VERSION,
            }
        )


V7OutputRequest = V7FirstOutputRequest | V7ManualOutputRequest


@dataclass(frozen=True, slots=True)
class V7OutputOperation:
    operation_id: UUID
    command_fingerprint: str
    target_name: str
    source_index: int
    source_relative_path: str
    source_size_bytes: int
    source_checksum_sha256: str
    decision_generation: int
    state: V7OutputOperationState
    decision_kind: V7OutputDecisionKind = V7OutputDecisionKind.AUTOMATIC_FIRST
    operator_confirmed_range: bool = False
    expected_previous_checksum_sha256: str | None = None
    expected_previous_owner_operation_id: UUID | None = None
    conflict_code: str | None = None

    @property
    def output_checksum_sha256(self) -> str:
        return self.source_checksum_sha256

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            V7OutputOperationState.COMMITTED,
            V7OutputOperationState.CANCELLED,
            V7OutputOperationState.SUPERSEDED,
            V7OutputOperationState.CONFLICT,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "commandFingerprint": self.command_fingerprint,
            "conflictCode": self.conflict_code,
            "decisionGeneration": self.decision_generation,
            "decisionKind": self.decision_kind.value,
            "expectedPreviousChecksumSha256": self.expected_previous_checksum_sha256,
            "expectedPreviousOwnerOperationId": (
                None
                if self.expected_previous_owner_operation_id is None
                else str(self.expected_previous_owner_operation_id)
            ),
            "operationId": str(self.operation_id),
            "operatorConfirmedRange": self.operator_confirmed_range,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceIndex": self.source_index,
            "sourceRelativePath": self.source_relative_path,
            "sourceSizeBytes": self.source_size_bytes,
            "state": self.state.value,
            "targetName": self.target_name,
        }

    @classmethod
    def from_dict(cls, value: object) -> V7OutputOperation:
        raw = _mapping(value, "V7 output operation must be an object.")
        try:
            operation = cls(
                operation_id=UUID(_string(raw["operationId"])),
                command_fingerprint=_sha256(raw["commandFingerprint"]),
                target_name=_target_name(raw["targetName"]),
                source_index=_int(raw["sourceIndex"]),
                source_relative_path=_string(raw["sourceRelativePath"]),
                source_size_bytes=_int(raw["sourceSizeBytes"]),
                source_checksum_sha256=_sha256(raw["sourceChecksumSha256"]),
                decision_generation=_int(raw["decisionGeneration"]),
                state=V7OutputOperationState(_string(raw["state"])),
                decision_kind=V7OutputDecisionKind(
                    _string(raw.get("decisionKind", V7OutputDecisionKind.AUTOMATIC_FIRST.value))
                ),
                operator_confirmed_range=_bool(raw.get("operatorConfirmedRange", False)),
                expected_previous_checksum_sha256=_optional_sha256(
                    raw.get("expectedPreviousChecksumSha256")
                ),
                expected_previous_owner_operation_id=_optional_uuid(
                    raw.get("expectedPreviousOwnerOperationId")
                ),
                conflict_code=_optional_string(raw.get("conflictCode")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_JOURNAL_INVALID", "V7 output operation is invalid."
            ) from error
        if operation.state is V7OutputOperationState.CONFLICT and operation.conflict_code is None:
            _fail("V7_OUTPUT_JOURNAL_INVALID", "A V7 output conflict requires a code.")
        if (
            operation.state is not V7OutputOperationState.CONFLICT
            and operation.conflict_code is not None
        ):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "Only a V7 output conflict has a code.")
        operation._validate_decision_fields()
        return operation

    def _validate_decision_fields(self) -> None:
        has_previous = (
            self.expected_previous_checksum_sha256 is not None
            and self.expected_previous_owner_operation_id is not None
        )
        if self.decision_kind is V7OutputDecisionKind.AUTOMATIC_FIRST and (
            self.operator_confirmed_range
            or has_previous
            or self.expected_previous_checksum_sha256 is not None
            or self.expected_previous_owner_operation_id is not None
        ):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "Automatic V7 output has manual fields.")
        if (
            self.decision_kind
            in {
                V7OutputDecisionKind.MANUAL_NO_OCR,
                V7OutputDecisionKind.MANUAL_REPLACE,
            }
            and not self.operator_confirmed_range
        ):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "Manual V7 output lacks range confirmation.")
        if (self.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE) != has_previous or (
            self.decision_kind is not V7OutputDecisionKind.MANUAL_REPLACE
            and (
                self.expected_previous_checksum_sha256 is not None
                or self.expected_previous_owner_operation_id is not None
            )
        ):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 replace fields are inconsistent.")


@dataclass(frozen=True, slots=True)
class V7TargetOwner:
    target_name: str
    generation: int
    operation_id: UUID | None
    checksum_sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "generation": self.generation,
            "operationId": None if self.operation_id is None else str(self.operation_id),
            "targetName": self.target_name,
        }

    @classmethod
    def from_dict(cls, value: object) -> V7TargetOwner:
        raw = _mapping(value, "V7 target owner must be an object.")
        try:
            operation_raw = raw.get("operationId")
            checksum_raw = raw.get("checksumSha256")
            return cls(
                target_name=_target_name(raw["targetName"]),
                generation=_int(raw["generation"]),
                operation_id=None if operation_raw is None else UUID(_string(operation_raw)),
                checksum_sha256=None if checksum_raw is None else _sha256(checksum_raw),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_JOURNAL_INVALID", "V7 target owner is invalid."
            ) from error


@dataclass(frozen=True, slots=True)
class V7OutputJournal:
    source_manifest: V7PinnedSourceManifest
    operations: tuple[V7OutputOperation, ...]
    owners: tuple[V7TargetOwner, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "operations": [item.as_dict() for item in self.operations],
            "owners": [item.as_dict() for item in self.owners],
            "schemaVersion": V7_OUTPUT_JOURNAL_SCHEMA_VERSION,
            "sourceManifest": self.source_manifest.as_dict(),
            "writerVersion": V7_OUTPUT_WRITER_VERSION,
        }

    @classmethod
    def empty(cls, source_manifest: V7PinnedSourceManifest) -> V7OutputJournal:
        return cls(source_manifest, (), ())

    @classmethod
    def from_dict(cls, value: object) -> V7OutputJournal:
        raw = _mapping(value, "V7 output journal must be an object.")
        try:
            if (
                raw.get("schemaVersion") != V7_OUTPUT_JOURNAL_SCHEMA_VERSION
                or raw.get("writerVersion") != V7_OUTPUT_WRITER_VERSION
            ):
                raise ValueError("journal version mismatch")
            journal = cls(
                source_manifest=V7PinnedSourceManifest.from_dict(raw["sourceManifest"]),
                operations=tuple(
                    V7OutputOperation.from_dict(item) for item in _items(raw["operations"])
                ),
                owners=tuple(V7TargetOwner.from_dict(item) for item in _items(raw["owners"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_JOURNAL_INVALID", "V7 output journal is invalid."
            ) from error
        if len({item.operation_id for item in journal.operations}) != len(journal.operations):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 output operation ID is duplicated.")
        if len({item.target_name for item in journal.owners}) != len(journal.owners):
            _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 output owner is duplicated.")
        operations = {item.operation_id: item for item in journal.operations}
        for owner in journal.owners:
            if owner.operation_id is None:
                if owner.checksum_sha256 is not None:
                    _fail(
                        "V7_OUTPUT_JOURNAL_INVALID",
                        "An unowned V7 target cannot retain a checksum.",
                    )
                continue
            operation = operations.get(owner.operation_id)
            if (
                operation is None
                or operation.target_name != owner.target_name
                or operation.state
                not in {V7OutputOperationState.COMMITTED, V7OutputOperationState.CONFLICT}
                or owner.checksum_sha256 != operation.output_checksum_sha256
            ):
                _fail(
                    "V7_OUTPUT_JOURNAL_INVALID",
                    "A V7 output owner must match its committed operation.",
                )
        return journal


FaultHook = Callable[[str, V7OutputOperation], None]
GenerationValidator = Callable[[V7OutputOperation], bool]


class V7OutputWriter:
    """Own the journal and non-clobber publication for one pinned V7 source folder."""

    def __init__(
        self,
        initial_manifest: LocalSourceManifest,
        *,
        refresh_manifest: Callable[[], LocalSourceManifest],
        generation_validator: GenerationValidator | None = None,
        fault_hook: FaultHook | None = None,
        filesystem_validator: Callable[[Path], bool] | None = None,
    ) -> None:
        self._initial_manifest = initial_manifest
        self._pinned_manifest = V7PinnedSourceManifest.from_local_manifest(initial_manifest)
        self._refresh_manifest = refresh_manifest
        self._generation_validator = generation_validator or (lambda _operation: True)
        self._fault_hook = fault_hook or (lambda _phase, _operation: None)
        self._filesystem_validator = filesystem_validator or _is_supported_local_ntfs
        source_root = initial_manifest.source_root
        if not source_root.name:
            _fail("V7_OUTPUT_PATH_UNSAFE", "V7 source folder cannot be a filesystem root.")
        self.output_root = source_root.with_name(f"{source_root.name} cut")
        self._state_root = self.output_root / _STATE_DIRECTORY
        self._journal_path = self._state_root / _JOURNAL_FILE

    def write_first(self, request: V7FirstOutputRequest) -> V7OutputOperation:
        """Prepare, copy, publish and commit one automatic first output safely."""

        return self._write(request)

    def write_manual_first(self, request: V7ManualOutputRequest) -> V7OutputOperation:
        """Persist an operator-accepted first output, including a 1–8 final page."""

        if request.decision_kind is not V7OutputDecisionKind.MANUAL_FIRST:
            _fail(
                "V7_OUTPUT_REQUEST_INVALID", "V7 manual first output has the wrong decision kind."
            )
        return self._write(request)

    def write_manual_no_ocr(self, request: V7ManualOutputRequest) -> V7OutputOperation:
        """Persist a manual range only after explicit operator confirmation."""

        if request.decision_kind is not V7OutputDecisionKind.MANUAL_NO_OCR:
            _fail(
                "V7_OUTPUT_REQUEST_INVALID", "V7 manual no-OCR output has the wrong decision kind."
            )
        return self._write(request)

    def manual_replace(self, request: V7ManualOutputRequest) -> V7OutputOperation:
        """Replace the current target only when its owner and old SHA still match."""

        if request.decision_kind is not V7OutputDecisionKind.MANUAL_REPLACE:
            _fail("V7_OUTPUT_REQUEST_INVALID", "V7 manual replace has the wrong decision kind.")
        return self._write(request)

    def _write(self, request: V7OutputRequest) -> V7OutputOperation:
        """Run the common intent → temp → publish → commit state machine."""

        self._ensure_directories()
        with _DirectoryLock(self._state_root / _LOCK_FILE):
            journal = self._load_journal()
            self._require_journal_manifest(journal)
            # A pending operation must never be reconciled against a changed
            # source set.  This applies to recovery just as it does to a new
            # publication: a non-selected source changing invalidates the V7
            # run's pinned evidence.
            self._require_current_manifest()
            journal = self._recover_locked(journal)
            operation, journal = self._get_or_prepare(journal, request)
            self._save_journal(journal)
            if operation.is_terminal:
                return operation
            current = self._require_current_manifest()
            source_path = self._require_source(current, operation)
            if operation.state is V7OutputOperationState.PREPARED:
                self._fault_hook("prepared", operation)
                self._write_temp(source_path, operation)
                operation = replace(operation, state=V7OutputOperationState.PUBLISHING)
                journal = _replace_operation(journal, operation)
                self._save_journal(journal)
                self._fault_hook("temp_written", operation)
            if operation.state is V7OutputOperationState.PUBLISHING:
                # The validation is deliberately adjacent to no-clobber publish.
                current = self._require_current_manifest()
                self._require_source(current, operation)
                self._fault_hook("before_publish", operation)
                if not self._generation_validator(operation):
                    operation = self._conflict(operation, "V7_OUTPUT_STALE_GENERATION")
                    journal = _replace_operation(journal, operation)
                    self._save_journal(journal)
                    return operation
                self._fault_hook("after_generation_validation", operation)
                if operation.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE:
                    self._require_replace_preconditions(journal, operation)
                    self._replace_target(operation)
                    self._fault_hook("target_replaced", operation)
                else:
                    self._publish_no_clobber(operation)
                    self._fault_hook("target_linked", operation)
                operation = replace(operation, state=V7OutputOperationState.PUBLISHED)
                journal = _replace_operation(journal, operation)
                self._save_journal(journal)
                self._fault_hook("published", operation)
            committed, _ = self._commit_locked(journal, operation)
            return committed

    def recover(self) -> V7OutputJournal:
        """Reconcile journal/target/temp after process loss without writing a JPEG."""

        self._ensure_directories()
        with _DirectoryLock(self._state_root / _LOCK_FILE):
            journal = self._load_journal()
            self._require_journal_manifest(journal)
            self._require_current_manifest()
            return self._recover_locked(journal)

    def supersede_pending(self, operation_id: UUID, *, next_generation: int) -> V7OutputOperation:
        """T09 seam: invalidate a pending old writer under the same directory lock."""

        self._ensure_directories()
        with _DirectoryLock(self._state_root / _LOCK_FILE):
            journal = self._load_journal()
            self._require_journal_manifest(journal)
            self._require_current_manifest()
            journal = self._recover_locked(journal)
            operation = _operation_by_id(journal, operation_id)
            if operation is None:
                _fail("V7_OUTPUT_OPERATION_NOT_FOUND", "V7 output operation was not found.")
            owner = _owner_for(journal, operation.target_name)
            if operation.is_terminal or owner.generation >= next_generation:
                _fail("V7_OUTPUT_GENERATION_INVALID", "V7 output generation cannot be superseded.")
            updated_owner = replace(owner, generation=next_generation)
            updated = replace(operation, state=V7OutputOperationState.SUPERSEDED)
            journal = _replace_owner(_replace_operation(journal, updated), updated_owner)
            self._save_journal(journal)
            self._discard_temp(updated)
            return updated

    def cancel_pending(self, operation_id: UUID) -> V7OutputOperation:
        """Cancel a not-yet-published intent without touching a current target."""

        self._ensure_directories()
        with _DirectoryLock(self._state_root / _LOCK_FILE):
            journal = self._load_journal()
            self._require_journal_manifest(journal)
            self._require_current_manifest()
            journal = self._recover_locked(journal)
            operation = _operation_by_id(journal, operation_id)
            if operation is None:
                _fail("V7_OUTPUT_OPERATION_NOT_FOUND", "V7 output operation was not found.")
            if operation.state is V7OutputOperationState.CANCELLED:
                return operation
            if operation.is_terminal:
                _fail("V7_OUTPUT_STATE_INVALID", "A completed V7 output cannot be cancelled.")
            cancelled = replace(operation, state=V7OutputOperationState.CANCELLED)
            journal = _replace_operation(journal, cancelled)
            self._save_journal(journal)
            self._discard_temp(cancelled)
            return cancelled

    def _get_or_prepare(
        self,
        journal: V7OutputJournal,
        request: V7OutputRequest,
    ) -> tuple[V7OutputOperation, V7OutputJournal]:
        existing = _operation_by_id(journal, request.operation_id)
        if existing is not None:
            if existing.command_fingerprint != request.command_fingerprint:
                _fail(
                    "V7_OUTPUT_IDEMPOTENCY_CONFLICT",
                    "An output operation ID cannot be reused for another command.",
                )
            return existing, journal
        owner = _owner_for(journal, request.target_name)
        target = self.output_root / request.target_name
        if request.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE:
            self._require_replace_request(owner, target, cast(V7ManualOutputRequest, request))
        elif owner.operation_id is not None or owner.generation != request.decision_generation:
            _fail(
                "V7_OUTPUT_TARGET_CONFLICT", "V7 output target already has an owner or generation."
            )
        elif target.exists():
            _fail("V7_OUTPUT_TARGET_CONFLICT", "V7 output target already exists and is protected.")
        operation = V7OutputOperation(
            operation_id=request.operation_id,
            command_fingerprint=request.command_fingerprint,
            target_name=request.target_name,
            source_index=request.source_index,
            source_relative_path=request.source_relative_path,
            source_size_bytes=request.source_size_bytes,
            source_checksum_sha256=request.source_checksum_sha256,
            decision_generation=request.decision_generation,
            state=V7OutputOperationState.PREPARED,
            decision_kind=request.decision_kind,
            operator_confirmed_range=request.operator_confirmed_range,
            expected_previous_checksum_sha256=request.expected_previous_checksum_sha256,
            expected_previous_owner_operation_id=request.expected_previous_owner_operation_id,
        )
        updated = V7OutputJournal(
            journal.source_manifest, (*journal.operations, operation), journal.owners
        )
        # A replace keeps the older owner until the new bytes were published and
        # committed. First writes retain the generation reservation without an
        # owner operation.
        return (
            operation,
            updated
            if request.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE
            else _replace_owner(updated, owner),
        )

    def _recover_locked(self, journal: V7OutputJournal) -> V7OutputJournal:
        self._require_no_orphan_temps(journal)
        changed = False
        for operation in tuple(journal.operations):
            updated = self._recover_operation(journal, operation)
            if updated != operation:
                journal = _replace_operation(journal, updated)
                changed = True
            # Publication is visible but ownership was not yet persisted.  The
            # recovery point must perform that last durable transition; leaving
            # it for a later HTTP retry would make "published" ambiguous.
            if updated.state is V7OutputOperationState.PUBLISHED:
                if not self._generation_validator(updated):
                    updated = self._conflict(updated, "V7_OUTPUT_STALE_GENERATION")
                    journal = _replace_operation(journal, updated)
                    changed = True
                else:
                    _, journal = self._commit_locked(journal, updated)
        if changed:
            self._save_journal(journal)
        return journal

    def _recover_operation(
        self,
        journal: V7OutputJournal,
        operation: V7OutputOperation,
    ) -> V7OutputOperation:
        if operation.state in {V7OutputOperationState.CANCELLED, V7OutputOperationState.SUPERSEDED}:
            self._discard_temp(operation)
            return operation
        if operation.state is V7OutputOperationState.CONFLICT:
            return operation
        target = self.output_root / operation.target_name
        temp = self._temp_path(operation)
        target_hash = _file_sha256_if_regular(target)
        temp_hash = _file_sha256_if_regular(temp)
        if temp_hash is not None and temp_hash != operation.output_checksum_sha256:
            return self._conflict(operation, "V7_OUTPUT_TEMP_CHECKSUM_MISMATCH")
        if operation.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE:
            return self._recover_replace_operation(
                journal,
                operation,
                target_hash=target_hash,
                temp_hash=temp_hash,
            )
        if target_hash is not None and target_hash != operation.output_checksum_sha256:
            owner = _owner_for(journal, operation.target_name)
            if operation.state is V7OutputOperationState.COMMITTED and (
                owner.operation_id != operation.operation_id
                or _is_pending_replacement_target(journal, operation, target_hash)
            ):
                return operation  # Historical owner; T09 owns the newer file.
            return self._conflict(operation, "V7_OUTPUT_TARGET_CHECKSUM_MISMATCH")
        if operation.state is V7OutputOperationState.PREPARED:
            return (
                replace(operation, state=V7OutputOperationState.PUBLISHED)
                if target_hash is not None
                else (
                    replace(operation, state=V7OutputOperationState.PUBLISHING)
                    if temp_hash is not None
                    else operation
                )
            )
        if operation.state is V7OutputOperationState.PUBLISHING:
            return (
                replace(operation, state=V7OutputOperationState.PUBLISHED)
                if target_hash
                else operation
            )
        if operation.state is V7OutputOperationState.PUBLISHED:
            return (
                operation if target_hash else self._conflict(operation, "V7_OUTPUT_TARGET_MISSING")
            )
        if operation.state is V7OutputOperationState.COMMITTED:
            owner = _owner_for(journal, operation.target_name)
            if owner.operation_id == operation.operation_id and target_hash is None:
                return self._conflict(operation, "V7_OUTPUT_TARGET_MISSING")
        return operation

    def _recover_replace_operation(
        self,
        journal: V7OutputJournal,
        operation: V7OutputOperation,
        *,
        target_hash: str | None,
        temp_hash: str | None,
    ) -> V7OutputOperation:
        expected_previous = operation.expected_previous_checksum_sha256
        expected_owner = operation.expected_previous_owner_operation_id
        if expected_previous is None or expected_owner is None:
            return self._conflict(operation, "V7_OUTPUT_REPLACE_JOURNAL_INVALID")
        owner = _owner_for(journal, operation.target_name)
        if operation.state is V7OutputOperationState.COMMITTED:
            if owner.operation_id != operation.operation_id or _is_pending_replacement_target(
                journal, operation, target_hash or ""
            ):
                return operation  # A newer owner superseded this historical output.
            return (
                operation
                if target_hash == operation.output_checksum_sha256
                else self._conflict(operation, "V7_OUTPUT_TARGET_CHECKSUM_MISMATCH")
            )
        if target_hash == operation.output_checksum_sha256:
            return replace(operation, state=V7OutputOperationState.PUBLISHED)
        if (
            owner.operation_id == expected_owner
            and owner.checksum_sha256 == expected_previous
            and owner.generation + 1 == operation.decision_generation
            and target_hash == expected_previous
        ):
            if operation.state is V7OutputOperationState.PREPARED and temp_hash is None:
                return operation
            return (
                replace(operation, state=V7OutputOperationState.PUBLISHING)
                if temp_hash is not None
                else self._conflict(operation, "V7_OUTPUT_TEMP_MISSING")
            )
        return self._conflict(operation, "V7_OUTPUT_REPLACE_STALE_TARGET")

    def _commit_locked(
        self,
        journal: V7OutputJournal,
        operation: V7OutputOperation,
    ) -> tuple[V7OutputOperation, V7OutputJournal]:
        if operation.state is V7OutputOperationState.COMMITTED:
            return operation, journal
        if operation.state is not V7OutputOperationState.PUBLISHED:
            _fail("V7_OUTPUT_STATE_INVALID", "Only a published V7 output can be committed.")
        target_hash = _file_sha256_if_regular(self.output_root / operation.target_name)
        if target_hash != operation.output_checksum_sha256:
            operation = self._conflict(operation, "V7_OUTPUT_TARGET_CHECKSUM_MISMATCH")
            journal = _replace_operation(journal, operation)
            self._save_journal(journal)
            return operation, journal
        owner = _owner_for(journal, operation.target_name)
        if operation.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE:
            if (
                owner.operation_id != operation.expected_previous_owner_operation_id
                or owner.checksum_sha256 != operation.expected_previous_checksum_sha256
                or owner.generation + 1 != operation.decision_generation
            ):
                operation = self._conflict(operation, "V7_OUTPUT_REPLACE_STALE_TARGET")
                journal = _replace_operation(journal, operation)
                self._save_journal(journal)
                return operation, journal
        else:
            if owner.generation != operation.decision_generation:
                operation = replace(operation, state=V7OutputOperationState.SUPERSEDED)
                journal = _replace_operation(journal, operation)
                self._save_journal(journal)
                return operation, journal
            if owner.operation_id not in {None, operation.operation_id}:
                operation = self._conflict(operation, "V7_OUTPUT_TARGET_OWNER_CONFLICT")
                journal = _replace_operation(journal, operation)
                self._save_journal(journal)
                return operation, journal
        committed = replace(operation, state=V7OutputOperationState.COMMITTED)
        journal = _replace_owner(
            _replace_operation(journal, committed),
            V7TargetOwner(
                target_name=operation.target_name,
                generation=operation.decision_generation,
                operation_id=operation.operation_id,
                checksum_sha256=operation.output_checksum_sha256,
            ),
        )
        self._save_journal(journal)
        self._temp_path(operation).unlink(missing_ok=True)
        return committed, journal

    def _require_no_orphan_temps(self, journal: V7OutputJournal) -> None:
        """Reject unknown writer state instead of treating it as harmless.

        A known operation may retain its temp after a process loss.  Any other
        ``output-*.part`` file cannot be tied to a command fingerprint and is
        therefore a recoverable-operator conflict, never a file to overwrite
        or silently ignore.
        """

        known = {self._temp_path(item).name for item in journal.operations}
        for candidate in self._state_root.glob(f"{_TEMP_PREFIX}*.part"):
            if candidate.name not in known:
                _fail(
                    "V7_OUTPUT_ORPHAN_TEMP",
                    "V7 output contains a temp file without a journal operation.",
                )

    def _write_temp(self, source_path: Path, operation: V7OutputOperation) -> None:
        temp = self._temp_path(operation)
        if temp.exists():
            current_hash = _file_sha256_if_regular(temp)
            if current_hash == operation.output_checksum_sha256:
                return
            _fail("V7_OUTPUT_TEMP_CONFLICT", "V7 output temp file has foreign content.")
        digest = hashlib.sha256()
        try:
            with source_path.open("rb") as source, temp.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
        except OSError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_WRITE_FAILED", "V7 output temp cannot be written."
            ) from error
        if digest.hexdigest() != operation.source_checksum_sha256:
            _fail("V7_OUTPUT_SOURCE_CHANGED", "V7 source changed while the output was copied.")

    def _discard_temp(self, operation: V7OutputOperation) -> None:
        temp = self._temp_path(operation)
        if not temp.exists():
            return
        if _file_sha256_if_regular(temp) != operation.output_checksum_sha256:
            _fail("V7_OUTPUT_TEMP_CHECKSUM_MISMATCH", "V7 output temp cannot be discarded.")
        temp.unlink()

    def _publish_no_clobber(self, operation: V7OutputOperation) -> None:
        target = self.output_root / operation.target_name
        temp = self._temp_path(operation)
        if _file_sha256_if_regular(target) is not None:
            _fail("V7_OUTPUT_TARGET_CONFLICT", "V7 output target appeared before publication.")
        if _file_sha256_if_regular(temp) != operation.output_checksum_sha256:
            _fail("V7_OUTPUT_TEMP_CHECKSUM_MISMATCH", "V7 output temp cannot be published.")
        try:
            os.link(temp, target)
        except FileExistsError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_TARGET_CONFLICT", "V7 output target appeared during publication."
            ) from error
        except OSError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_PUBLISH_FAILED", "V7 output cannot be published."
            ) from error

    def _require_replace_request(
        self,
        owner: V7TargetOwner,
        target: Path,
        request: V7ManualOutputRequest | V7OutputOperation,
    ) -> None:
        expected_checksum = request.expected_previous_checksum_sha256
        expected_owner = request.expected_previous_owner_operation_id
        if (
            expected_checksum is None
            or expected_owner is None
            or owner.operation_id != expected_owner
            or owner.checksum_sha256 != expected_checksum
            or request.decision_generation != owner.generation + 1
            or _file_sha256_if_regular(target) != expected_checksum
        ):
            _fail(
                "V7_OUTPUT_REPLACE_STALE_TARGET",
                "V7 manual replacement target, owner or generation changed.",
            )

    def _require_replace_preconditions(
        self,
        journal: V7OutputJournal,
        operation: V7OutputOperation,
    ) -> None:
        self._require_replace_request(
            _owner_for(journal, operation.target_name),
            self.output_root / operation.target_name,
            operation,
        )

    def _replace_target(self, operation: V7OutputOperation) -> None:
        target = self.output_root / operation.target_name
        temp = self._temp_path(operation)
        if _file_sha256_if_regular(temp) != operation.output_checksum_sha256:
            _fail("V7_OUTPUT_TEMP_CHECKSUM_MISMATCH", "V7 replacement temp cannot be published.")
        try:
            os.replace(temp, target)
        except OSError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_REPLACE_FAILED", "V7 output target cannot be replaced."
            ) from error

    def _require_current_manifest(self) -> LocalSourceManifest:
        try:
            current = self._refresh_manifest()
            self._pinned_manifest.require_matches(current)
            return current
        except (LocalSourceManifestError, V7RunStateError, V7OutputWriterError) as error:
            if isinstance(error, V7OutputWriterError):
                raise
            raise V7OutputWriterError("V7_OUTPUT_SOURCE_MANIFEST_DRIFT", str(error)) from error

    def _require_source(self, manifest: LocalSourceManifest, operation: V7OutputOperation) -> Path:
        try:
            path, source = resolve_local_source_asset(
                manifest,
                source_index=operation.source_index,
                expected_checksum_sha256=operation.source_checksum_sha256,
            )
        except LocalSourceManifestError as error:
            raise V7OutputWriterError("V7_OUTPUT_SOURCE_CHANGED", str(error)) from error
        if (
            source.relative_path != operation.source_relative_path
            or source.size_bytes != operation.source_size_bytes
        ):
            _fail(
                "V7_OUTPUT_SOURCE_CHANGED", "V7 selected source differs from the output operation."
            )
        return cast(Path, path)

    def _ensure_directories(self) -> None:
        if not self._filesystem_validator(self._initial_manifest.source_root):
            _fail(
                "V7_OUTPUT_FILESYSTEM_UNSUPPORTED",
                "V7 output requires a local NTFS source volume without network shares.",
            )
        _require_safe_directory(self._initial_manifest.source_root)
        try:
            self.output_root.mkdir(exist_ok=True)
            _require_safe_directory(self.output_root)
            self._state_root.mkdir(exist_ok=True)
            _require_safe_directory(self._state_root)
        except OSError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_PATH_UNSAFE", "V7 output directory cannot be created safely."
            ) from error

    def _load_journal(self) -> V7OutputJournal:
        if not self._journal_path.exists():
            return V7OutputJournal.empty(self._pinned_manifest)
        if not self._journal_path.is_file() or _is_link_or_reparse(self._journal_path):
            _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output journal path is unsafe.")
        try:
            return V7OutputJournal.from_dict(
                json.loads(self._journal_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, V7OutputWriterError) as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_JOURNAL_INVALID", "V7 output journal is invalid."
            ) from error

    def _save_journal(self, journal: V7OutputJournal) -> None:
        content = json.dumps(
            journal.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        temporary = self._state_root / f".{_JOURNAL_FILE}.{os.getpid()}.tmp"
        try:
            with temporary.open("xb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self._journal_path)
        except OSError as error:
            raise V7OutputWriterError(
                "V7_OUTPUT_JOURNAL_WRITE_FAILED", "V7 output journal cannot be saved."
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _require_journal_manifest(self, journal: V7OutputJournal) -> None:
        if journal.source_manifest != self._pinned_manifest:
            _fail(
                "V7_OUTPUT_JOURNAL_MANIFEST_CONFLICT",
                "V7 output journal belongs to another source manifest.",
            )

    def _temp_path(self, operation: V7OutputOperation) -> Path:
        return cast(Path, self._state_root / f"{_TEMP_PREFIX}{operation.operation_id.hex}.part")

    @staticmethod
    def _conflict(operation: V7OutputOperation, code: str) -> V7OutputOperation:
        return replace(operation, state=V7OutputOperationState.CONFLICT, conflict_code=code)


class _DirectoryLock(AbstractContextManager[None]):
    """A process lock whose lifetime is the entire check-to-commit section."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._descriptor: int | None = None

    def __enter__(self) -> None:
        try:
            if self._path.exists() and (
                not self._path.is_file() or _is_link_or_reparse(self._path)
            ):
                _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output lock path is unsafe.")
            descriptor = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output lock path is not a regular file.")
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - Windows is the supported runtime.
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]
                    descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
            self._descriptor = descriptor
        except OSError as error:
            if "descriptor" in locals():
                os.close(descriptor)
            raise V7OutputWriterError(
                "V7_OUTPUT_LOCK_BUSY", "V7 output directory is busy."
            ) from error
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        if self._descriptor is None:
            return None
        try:
            os.lseek(self._descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._descriptor, msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Windows is the supported runtime.
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]
                    self._descriptor,
                    fcntl.LOCK_UN,  # type: ignore[attr-defined]
                )
        finally:
            os.close(self._descriptor)
            self._descriptor = None
        return None


def _replace_operation(journal: V7OutputJournal, operation: V7OutputOperation) -> V7OutputJournal:
    return replace(
        journal,
        operations=tuple(
            item if item.operation_id != operation.operation_id else operation
            for item in journal.operations
        ),
    )


def _replace_owner(journal: V7OutputJournal, owner: V7TargetOwner) -> V7OutputJournal:
    existing = _owner_for(journal, owner.target_name)
    owners = tuple(item for item in journal.owners if item.target_name != owner.target_name)
    if existing == owner and any(item.target_name == owner.target_name for item in journal.owners):
        return journal
    return replace(journal, owners=(*owners, owner))


def _owner_for(journal: V7OutputJournal, target_name: str) -> V7TargetOwner:
    return next(
        (item for item in journal.owners if item.target_name == target_name),
        V7TargetOwner(target_name, 0, None, None),
    )


def _operation_by_id(journal: V7OutputJournal, operation_id: UUID) -> V7OutputOperation | None:
    return next((item for item in journal.operations if item.operation_id == operation_id), None)


def _is_pending_replacement_target(
    journal: V7OutputJournal,
    historical: V7OutputOperation,
    target_checksum_sha256: str,
) -> bool:
    """Keep O1 historical while recovery is about to commit its published O2."""

    return any(
        operation.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE
        and not operation.is_terminal
        and operation.target_name == historical.target_name
        and operation.expected_previous_owner_operation_id == historical.operation_id
        and operation.expected_previous_checksum_sha256 == historical.output_checksum_sha256
        and operation.output_checksum_sha256 == target_checksum_sha256
        for operation in journal.operations
    )


def _file_sha256_if_regular(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file() or _is_link_or_reparse(path):
        _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output path is not a safe regular file.")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise V7OutputWriterError("V7_OUTPUT_READ_FAILED", "V7 output cannot be read.") from error
    return digest.hexdigest()


def _require_safe_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or _is_link_or_reparse(path):
            _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output directory is unsafe.")
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise V7OutputWriterError(
            "V7_OUTPUT_PATH_UNSAFE", "V7 output directory is unavailable."
        ) from error
    if os.path.normcase(os.path.normpath(str(resolved))) != os.path.normcase(
        os.path.normpath(str(path))
    ):
        _fail("V7_OUTPUT_PATH_UNSAFE", "V7 output directory resolves through another path.")


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x0400
    )


def _is_supported_local_ntfs(path: Path) -> bool:
    """Accept only a fixed local NTFS volume for the V7 publication protocol."""

    if os.name != "nt" or str(path).startswith("\\\\"):
        return False
    try:
        resolved = path.resolve(strict=True)
        if str(resolved).startswith("\\\\") or not resolved.drive:
            return False
        root = f"{resolved.drive}\\"
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetDriveTypeW(root) != 3:  # DRIVE_FIXED; remote/mapped drives fail.
            return False
        filesystem = ctypes.create_unicode_buffer(261)
        return (
            bool(kernel32.GetVolumeInformationW(root, None, 0, None, None, None, filesystem, 261))
            and filesystem.value.casefold() == "ntfs"
        )
    except (OSError, AttributeError):
        return False


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _target_name(value: object) -> str:
    name = _string(value)
    if not name.startswith("seq_") or not name.endswith(".jpg") or Path(name).name != name:
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 output target name is invalid.")
    return name


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail("V7_OUTPUT_JOURNAL_INVALID", message)
    return cast(dict[str, object], value)


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 journal list is invalid.")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 journal string is invalid.")
    return value


def _optional_string(value: object) -> str | None:
    return None if value is None else _string(value)


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 journal boolean is invalid.")
    return value


def _optional_sha256(value: object) -> str | None:
    return None if value is None else _sha256(value)


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(_string(value))
    except (TypeError, ValueError) as error:
        raise V7OutputWriterError(
            "V7_OUTPUT_JOURNAL_INVALID", "V7 journal UUID is invalid."
        ) from error


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 journal integer is invalid.")
    return value


def _sha256(value: object) -> str:
    result = _string(value)
    if not _is_sha256(result):
        _fail("V7_OUTPUT_JOURNAL_INVALID", "V7 journal SHA-256 is invalid.")
    return result


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _fail(code: str, message: str) -> NoReturn:
    raise V7OutputWriterError(code, message)


__all__ = [
    "V7FirstOutputRequest",
    "V7ManualOutputRequest",
    "V7OutputDecisionKind",
    "V7OutputJournal",
    "V7OutputOperation",
    "V7OutputOperationState",
    "V7OutputWriter",
    "V7OutputWriterError",
]
