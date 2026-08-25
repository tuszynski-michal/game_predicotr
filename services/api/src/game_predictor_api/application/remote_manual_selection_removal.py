"""Durable checksum-guarded quarantine for remote selection tombstones."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostRepository,
    RemoteManualSelectionRemovalScope,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionHostActionRecord,
    RemoteManualSelectionRemovalContext,
    SqlAlchemyRemoteManualSelectionRepository,
)

REMOVAL_JOURNAL_SCHEMA = "remote-manual-selection-removal-v1"
MATERIALIZATION_JOURNAL_SCHEMA = "remote-manual-selection-materialization-v1"
MAX_JOURNAL_BYTES = 16 * 1024
CHUNK_BYTES = 1024 * 1024


class RemoteManualSelectionRemovalHost(Protocol):
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
    ) -> AbstractContextManager[RemoteManualSelectionRemovalScope]: ...


class RemoteManualSelectionRemovalResult(StrEnum):
    NO_ACTION = "no_action"
    QUARANTINED = "quarantined"
    ALREADY_ABSENT = "already_absent"
    SUPERSEDED = "superseded"
    RETRY = "retry"
    FAILED = "failed"
    LEASE_LOST = "lease_lost"


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionRemovalLimits:
    lease_duration: timedelta = timedelta(seconds=60)
    max_attempts: int = 5
    max_actions_per_cycle: int = 4

    def __post_init__(self) -> None:
        if (
            self.lease_duration.total_seconds() <= 0
            or self.max_attempts < 1
            or self.max_actions_per_cycle < 1
        ):
            raise ValueError("Removal limits must be positive.")


class RemoteManualSelectionHostRemover:
    def __init__(
        self,
        host: RemoteManualSelectionRemovalHost,
        *,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        self._host = host
        self._fault = fault or (lambda _point: None)

    def remove(
        self,
        repository: RemoteManualSelectionHostRepository,
        context: RemoteManualSelectionRemovalContext,
        *,
        on_quarantined: Callable[[], None] | None = None,
    ) -> RemoteManualSelectionRemovalResult:
        transfer_id = context.action.transfer_id
        if transfer_id is None:
            raise _removal_conflict(
                "REMOTE_SELECTION_REMOVAL_OWNERSHIP_MISSING",
                "The removal action has no materialized transfer identity.",
            )
        with self._host.open_removal_scope(
            repository,
            session_id=context.action.session_id,
            batch_id=context.action.batch_id,
            file_id=context.action.file_id,
            transfer_id=transfer_id,
            materialization_action_id=context.materialization_action_id,
            removal_action_id=context.action.id,
            materialized_generation=context.materialized_generation,
            tombstone_generation=context.action.generation,
            output_name=context.output_name,
        ) as scope_value:
            scope = scope_value
            identity = _RemovalIdentity.from_context(context)
            journal = _read_removal_journal(scope.removal_journal_path)
            if journal is not None:
                journal.assert_identity(identity)

            target_exists = scope.target_path.exists()
            quarantine_exists = scope.quarantine_path.exists()
            if target_exists and quarantine_exists:
                raise _removal_conflict(
                    "REMOTE_SELECTION_REMOVAL_HALF_STATE_CONFLICT",
                    "Both the final output and its quarantine target are occupied.",
                )
            if quarantine_exists:
                if journal is None:
                    raise _removal_conflict(
                        "REMOTE_SELECTION_REMOVAL_QUARANTINE_FOREIGN",
                        "The quarantine target exists without matching ownership.",
                    )
                if _checksum_regular_file(scope.quarantine_path) != context.checksum_sha256:
                    raise _removal_conflict(
                        "REMOTE_SELECTION_REMOVAL_QUARANTINE_CHANGED",
                        "The quarantined output no longer matches its recorded checksum.",
                    )
                if journal.state != "quarantined":
                    _write_removal_journal(
                        scope.removal_journal_path,
                        identity.with_state("quarantined"),
                    )
                if on_quarantined is not None:
                    on_quarantined()
                return RemoteManualSelectionRemovalResult.QUARANTINED

            if not target_exists:
                if on_quarantined is not None:
                    on_quarantined()
                return RemoteManualSelectionRemovalResult.ALREADY_ABSENT

            _assert_materialization_ownership(
                scope.materialization_journal_path,
                context,
            )
            self._fault("before_removal_journal")
            _write_removal_journal(
                scope.removal_journal_path,
                identity.with_state("prepared"),
            )
            self._fault("after_removal_journal")
            scope.quarantine_target(context.checksum_sha256)
            self._fault("after_quarantine")
            if _checksum_regular_file(scope.quarantine_path) != context.checksum_sha256:
                raise _removal_conflict(
                    "REMOTE_SELECTION_REMOVAL_QUARANTINE_CHANGED",
                    "The quarantine checksum differs from the owned final output.",
                )
            _write_removal_journal(
                scope.removal_journal_path,
                identity.with_state("quarantined"),
            )
            self._fault("after_quarantined_journal")
            if on_quarantined is not None:
                on_quarantined()
            return RemoteManualSelectionRemovalResult.QUARANTINED


class RemoteManualSelectionRemovalRunner:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        remover: RemoteManualSelectionHostRemover,
        *,
        worker_id: str,
        limits: RemoteManualSelectionRemovalLimits | None = None,
        clock: Callable[[], datetime] | None = None,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("Removal worker_id cannot be empty.")
        self._session_factory = session_factory
        self._remover = remover
        self._worker_id = worker_id.strip()
        self._limits = limits or RemoteManualSelectionRemovalLimits()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._fault = fault or (lambda _point: None)

    def run_once(self) -> RemoteManualSelectionRemovalResult:
        with self._session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            claim = repository.claim_next_removal_action(
                lease_owner=self._worker_id,
                lease_duration=self._limits.lease_duration,
                claimed_at=self._clock(),
            )
            session.commit()
        if claim is None:
            return RemoteManualSelectionRemovalResult.NO_ACTION
        if claim.lease_token is None:
            raise RuntimeError("A claimed removal action has no fencing token.")
        lease_token = claim.lease_token
        try:
            with self._session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                context = repository.lock_removal_context(
                    action_id=claim.action.id,
                    lease_token=lease_token,
                    locked_at=self._clock(),
                )
                if context is None:
                    session.commit()
                    return RemoteManualSelectionRemovalResult.SUPERSEDED
                filesystem_result = RemoteManualSelectionRemovalResult.ALREADY_ABSENT

                def complete() -> None:
                    self._fault("before_removed_commit")
                    repository.complete_removal_action(
                        context,
                        lease_token=lease_token,
                        completed_at=self._clock(),
                    )
                    session.commit()
                    self._fault("after_removed_commit")

                filesystem_result = self._remover.remove(
                    repository,
                    context,
                    on_quarantined=complete,
                )
                return filesystem_result
        except RemoteManualSelectionConflictError as error:
            if error.code == "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST":
                return RemoteManualSelectionRemovalResult.LEASE_LOST
            return self._record_failure(claim, error.code, terminal=True)
        except (OSError, RemoteManualSelectionError) as error:
            code = (
                error.code
                if isinstance(error, RemoteManualSelectionError)
                else "REMOTE_SELECTION_REMOVAL_IO_FAILED"
            )
            return self._record_failure(
                claim,
                code,
                terminal=claim.action.attempt >= self._limits.max_attempts,
            )

    def run_bounded_cycle(self) -> tuple[RemoteManualSelectionRemovalResult, ...]:
        results: list[RemoteManualSelectionRemovalResult] = []
        for _index in range(self._limits.max_actions_per_cycle):
            result = self.run_once()
            results.append(result)
            if result is RemoteManualSelectionRemovalResult.NO_ACTION:
                break
        return tuple(results)

    def _record_failure(
        self,
        claim: RemoteManualSelectionHostActionRecord,
        error_code: str,
        *,
        terminal: bool,
    ) -> RemoteManualSelectionRemovalResult:
        assert claim.lease_token is not None
        now = self._clock()
        retry_at = None if terminal else now + _retry_delay(claim.action.attempt)
        try:
            with self._session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                repository.finish_materialization_failure(
                    action_id=claim.action.id,
                    lease_token=claim.lease_token,
                    error_code=error_code,
                    failed_at=now,
                    retry_at=retry_at,
                )
                session.commit()
        except RemoteManualSelectionConflictError as lease_error:
            if lease_error.code == "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST":
                return RemoteManualSelectionRemovalResult.LEASE_LOST
            raise
        return (
            RemoteManualSelectionRemovalResult.FAILED
            if terminal
            else RemoteManualSelectionRemovalResult.RETRY
        )


@dataclass(frozen=True, slots=True)
class _RemovalIdentity:
    action_id: UUID
    session_id: UUID
    batch_id: UUID
    file_id: UUID
    transfer_id: UUID
    materialization_action_id: UUID
    materialized_generation: int
    tombstone_generation: int
    output_name: str
    checksum_sha256: str
    state: str

    @classmethod
    def from_context(cls, context: RemoteManualSelectionRemovalContext) -> _RemovalIdentity:
        if context.action.transfer_id is None:
            raise ValueError("Removal context requires a transfer ID.")
        return cls(
            action_id=context.action.id,
            session_id=context.action.session_id,
            batch_id=context.action.batch_id,
            file_id=context.action.file_id,
            transfer_id=context.action.transfer_id,
            materialization_action_id=context.materialization_action_id,
            materialized_generation=context.materialized_generation,
            tombstone_generation=context.action.generation,
            output_name=context.output_name,
            checksum_sha256=context.checksum_sha256,
            state="prepared",
        )

    def with_state(self, state: str) -> _RemovalIdentity:
        if state not in {"prepared", "quarantined"}:
            raise ValueError("Unsupported removal journal state.")
        return _RemovalIdentity(
            action_id=self.action_id,
            session_id=self.session_id,
            batch_id=self.batch_id,
            file_id=self.file_id,
            transfer_id=self.transfer_id,
            materialization_action_id=self.materialization_action_id,
            materialized_generation=self.materialized_generation,
            tombstone_generation=self.tombstone_generation,
            output_name=self.output_name,
            checksum_sha256=self.checksum_sha256,
            state=state,
        )

    def payload(self) -> dict[str, object]:
        return {
            "actionId": str(self.action_id),
            "batchId": str(self.batch_id),
            "checksumSha256": self.checksum_sha256,
            "fileId": str(self.file_id),
            "materializationActionId": str(self.materialization_action_id),
            "materializedGeneration": self.materialized_generation,
            "outputName": self.output_name,
            "schemaVersion": REMOVAL_JOURNAL_SCHEMA,
            "sessionId": str(self.session_id),
            "state": self.state,
            "tombstoneGeneration": self.tombstone_generation,
            "transferId": str(self.transfer_id),
        }

    def assert_identity(self, expected: _RemovalIdentity) -> None:
        if self.with_state(expected.state) != expected:
            raise _removal_conflict(
                "REMOTE_SELECTION_REMOVAL_JOURNAL_CONFLICT",
                "The removal journal belongs to different content.",
            )


def _assert_materialization_ownership(
    path: Path,
    context: RemoteManualSelectionRemovalContext,
) -> None:
    value = _read_json(path)
    expected = {
        "actionId": str(context.materialization_action_id),
        "batchId": str(context.action.batch_id),
        "checksumSha256": context.checksum_sha256,
        "fileId": str(context.action.file_id),
        "generation": context.materialized_generation,
        "outputName": context.output_name,
        "schemaVersion": MATERIALIZATION_JOURNAL_SCHEMA,
        "sessionId": str(context.action.session_id),
        "transferId": str(context.transfer.id),
    }
    if value is None or any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_TARGET_FOREIGN",
            "The final output has no matching materialization ownership journal.",
        )
    if value.get("state") not in {"prepared", "published"}:
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_TARGET_FOREIGN",
            "The final output materialization ownership is incomplete.",
        )


def _read_removal_journal(path: Path) -> _RemovalIdentity | None:
    value = _read_json(path)
    if value is None:
        return None
    try:
        identity = _RemovalIdentity(
            action_id=UUID(str(value["actionId"])),
            session_id=UUID(str(value["sessionId"])),
            batch_id=UUID(str(value["batchId"])),
            file_id=UUID(str(value["fileId"])),
            transfer_id=UUID(str(value["transferId"])),
            materialization_action_id=UUID(str(value["materializationActionId"])),
            materialized_generation=int(str(value["materializedGeneration"])),
            tombstone_generation=int(str(value["tombstoneGeneration"])),
            output_name=str(value["outputName"]),
            checksum_sha256=str(value["checksumSha256"]),
            state=str(value["state"]),
        )
        if value.get("schemaVersion") != REMOVAL_JOURNAL_SCHEMA or identity.state not in {
            "prepared",
            "quarantined",
        }:
            raise ValueError("schema")
        return identity
    except (KeyError, TypeError, ValueError) as error:
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_JOURNAL_CONFLICT",
            "The removal journal is invalid.",
        ) from error


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    _assert_regular_not_reparse(path)
    payload = path.read_bytes()
    if len(payload) > MAX_JOURNAL_BYTES:
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_JOURNAL_CONFLICT",
            "An ownership journal exceeds its bounded size.",
        )
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_JOURNAL_CONFLICT",
            "An ownership journal is invalid.",
        ) from error
    if not isinstance(value, dict):
        raise _removal_conflict(
            "REMOTE_SELECTION_REMOVAL_JOURNAL_CONFLICT",
            "An ownership journal is invalid.",
        )
    return value


def _write_removal_journal(path: Path, identity: _RemovalIdentity) -> None:
    encoded = (
        json.dumps(identity.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    temporary = path.with_suffix(".json.tmp")
    if temporary.exists():
        _assert_regular_not_reparse(temporary)
        temporary.unlink()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    _assert_regular_not_reparse(temporary)
    os.replace(temporary, path)


def _checksum_regular_file(path: Path) -> str:
    _assert_regular_not_reparse(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_regular_not_reparse(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise _removal_conflict(
            "REMOTE_SELECTION_PATH_UNSAFE",
            "A removal artifact is not a regular non-reparse file.",
        )


def _retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** max(0, attempt - 1)))


def _removal_conflict(code: str, message: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(code, message)


__all__ = [
    "RemoteManualSelectionHostRemover",
    "RemoteManualSelectionRemovalLimits",
    "RemoteManualSelectionRemovalResult",
    "RemoteManualSelectionRemovalRunner",
]
