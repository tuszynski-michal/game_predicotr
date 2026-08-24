"""Durable host-action runner for atomic remote selection materialization."""

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
    RemoteManualSelectionMaterializationScope,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionHostActionRecord,
    RemoteManualSelectionMaterializationContext,
    SqlAlchemyRemoteManualSelectionRepository,
)

MATERIALIZATION_JOURNAL_SCHEMA = "remote-manual-selection-materialization-v1"
MATERIALIZATION_CHUNK_BYTES = 1024 * 1024
MAX_MATERIALIZATION_JOURNAL_BYTES = 32 * 1024
DEFAULT_MATERIALIZATION_LEASE = timedelta(seconds=60)
DEFAULT_MAX_MATERIALIZATION_ATTEMPTS = 5


class RemoteManualSelectionMaterializationHost(Protocol):
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
    ) -> AbstractContextManager[RemoteManualSelectionMaterializationScope]: ...


class RemoteManualSelectionMaterializationRepository(
    RemoteManualSelectionHostRepository,
    Protocol,
):
    def enqueue_missing_materialization_actions(self, *, limit: int) -> int: ...

    def claim_next_materialization_action(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> RemoteManualSelectionHostActionRecord | None: ...

    def lock_materialization_context(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        locked_at: datetime,
    ) -> RemoteManualSelectionMaterializationContext | None: ...

    def complete_materialization_action(
        self,
        context: RemoteManualSelectionMaterializationContext,
        *,
        lease_token: UUID,
        final_relative_path: str,
        completed_at: datetime,
    ) -> object: ...

    def finish_materialization_failure(
        self,
        *,
        action_id: UUID,
        lease_token: UUID,
        error_code: str,
        failed_at: datetime,
        retry_at: datetime | None,
    ) -> object: ...


class RemoteManualSelectionMaterializationResult(StrEnum):
    NO_ACTION = "no_action"
    SYNCED = "synced"
    SUPERSEDED = "superseded"
    RETRY = "retry"
    FAILED = "failed"
    LEASE_LOST = "lease_lost"


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionMaterializationLimits:
    lease_duration: timedelta = DEFAULT_MATERIALIZATION_LEASE
    max_attempts: int = DEFAULT_MAX_MATERIALIZATION_ATTEMPTS
    max_actions_per_cycle: int = 4

    def __post_init__(self) -> None:
        if self.lease_duration.total_seconds() <= 0:
            raise ValueError("Materialization lease duration must be positive.")
        if self.max_attempts < 1 or self.max_actions_per_cycle < 1:
            raise ValueError("Materialization attempt and cycle limits must be positive.")


class RemoteManualSelectionHostMaterializer:
    """Publish one verified JPEG under an ownership-bound final name."""

    def __init__(
        self,
        host: RemoteManualSelectionMaterializationHost,
        *,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        self._host = host
        self._fault = fault or (lambda _point: None)

    def materialize(
        self,
        repository: RemoteManualSelectionMaterializationRepository,
        context: RemoteManualSelectionMaterializationContext,
        *,
        on_published: Callable[[str], None] | None = None,
    ) -> str:
        transfer_id = context.action.transfer_id
        if transfer_id is None:
            raise _materialization_conflict(
                "REMOTE_SELECTION_MATERIALIZATION_TRANSFER_MISSING",
                "The materialization action has no verified transfer identity.",
            )
        with self._host.open_materialization_scope(
            repository,
            session_id=context.action.session_id,
            batch_id=context.action.batch_id,
            file_id=context.action.file_id,
            transfer_id=transfer_id,
            action_id=context.action.id,
            generation=context.action.generation,
            output_name=context.output_name,
            verified_relative_path=context.verified_relative_path,
        ) as scope:
            expected = _JournalIdentity.from_context(context)
            source_checksum = _checksum_regular_file(scope.source_path)
            if source_checksum != context.checksum_sha256:
                raise _materialization_conflict(
                    "REMOTE_SELECTION_MATERIALIZATION_SOURCE_CHANGED",
                    "The verified transfer artifact changed before materialization.",
                )
            journal = _read_journal(scope.journal_path)
            if journal is not None:
                journal.assert_identity(expected)

            if scope.target_path.exists():
                if journal is None or journal.state not in {"prepared", "published"}:
                    raise _materialization_conflict(
                        "REMOTE_SELECTION_MATERIALIZATION_TARGET_FOREIGN",
                        "The final output name is already occupied without matching ownership.",
                    )
                if _checksum_regular_file(scope.target_path) != context.checksum_sha256:
                    raise _materialization_conflict(
                        "REMOTE_SELECTION_MATERIALIZATION_TARGET_CHANGED",
                        "The owned final output no longer matches its recorded checksum.",
                    )
                if scope.working_path.exists():
                    _assert_regular_not_reparse(scope.working_path)
                    if _checksum_regular_file(scope.working_path) != context.checksum_sha256:
                        raise _materialization_conflict(
                            "REMOTE_SELECTION_MATERIALIZATION_TEMP_CHANGED",
                            "The remaining owned temp differs from the published output.",
                        )
                    scope.working_path.unlink()
                if journal.state != "published":
                    _write_journal(scope.journal_path, expected.with_state("published"))
                if on_published is not None:
                    on_published(scope.final_relative_path)
                return scope.final_relative_path

            self._fault("before_temp_copy")
            _prepare_working_copy(
                source=scope.source_path,
                working=scope.working_path,
                expected_checksum=context.checksum_sha256,
            )
            self._fault("after_temp_copy")
            _write_journal(scope.journal_path, expected.with_state("prepared"))
            self._fault("after_prepared_journal")
            try:
                os.link(scope.working_path, scope.target_path)
            except FileExistsError as error:
                raise _materialization_conflict(
                    "REMOTE_SELECTION_MATERIALIZATION_TARGET_FOREIGN",
                    "The final output name was occupied concurrently.",
                ) from error
            scope.working_path.unlink()
            scope.pin_target()
            self._fault("after_publish")
            if _checksum_regular_file(scope.target_path) != context.checksum_sha256:
                raise _materialization_conflict(
                    "REMOTE_SELECTION_MATERIALIZATION_TARGET_CHANGED",
                    "The published output checksum differs from its verified transfer.",
                )
            _write_journal(scope.journal_path, expected.with_state("published"))
            self._fault("after_published_journal")
            if on_published is not None:
                on_published(scope.final_relative_path)
            return scope.final_relative_path


class RemoteManualSelectionHostActionRunner:
    """Claim and execute bounded materialization actions using fenced transactions."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        materializer: RemoteManualSelectionHostMaterializer,
        *,
        worker_id: str,
        limits: RemoteManualSelectionMaterializationLimits | None = None,
        clock: Callable[[], datetime] | None = None,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("Materialization worker_id cannot be empty.")
        self._session_factory = session_factory
        self._materializer = materializer
        self._worker_id = worker_id.strip()
        self._limits = limits or RemoteManualSelectionMaterializationLimits()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._fault = fault or (lambda _point: None)

    def run_once(self) -> RemoteManualSelectionMaterializationResult:
        with self._session_factory() as session:
            repository = SqlAlchemyRemoteManualSelectionRepository(session)
            repository.enqueue_missing_materialization_actions(
                limit=self._limits.max_actions_per_cycle
            )
            claim = repository.claim_next_materialization_action(
                lease_owner=self._worker_id,
                lease_duration=self._limits.lease_duration,
                claimed_at=self._clock(),
            )
            session.commit()
        if claim is None:
            return RemoteManualSelectionMaterializationResult.NO_ACTION
        if claim.lease_token is None:
            raise RuntimeError("A claimed materialization action has no fencing token.")
        lease_token = claim.lease_token

        try:
            with self._session_factory() as session:
                repository = SqlAlchemyRemoteManualSelectionRepository(session)
                context = repository.lock_materialization_context(
                    action_id=claim.action.id,
                    lease_token=lease_token,
                    locked_at=self._clock(),
                )
                if context is None:
                    session.commit()
                    return RemoteManualSelectionMaterializationResult.SUPERSEDED

                def complete(final_relative_path: str) -> None:
                    self._fault("before_synced_commit")
                    repository.complete_materialization_action(
                        context,
                        lease_token=lease_token,
                        final_relative_path=final_relative_path,
                        completed_at=self._clock(),
                    )
                    session.commit()
                    self._fault("after_synced_commit")

                self._materializer.materialize(
                    repository,
                    context,
                    on_published=complete,
                )
            return RemoteManualSelectionMaterializationResult.SYNCED
        except RemoteManualSelectionConflictError as error:
            if error.code == "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST":
                return RemoteManualSelectionMaterializationResult.LEASE_LOST
            return self._record_failure(claim, error.code, terminal=True)
        except (OSError, RemoteManualSelectionError) as error:
            code = (
                error.code
                if isinstance(error, RemoteManualSelectionError)
                else "REMOTE_SELECTION_MATERIALIZATION_IO_FAILED"
            )
            return self._record_failure(
                claim,
                code,
                terminal=claim.action.attempt >= self._limits.max_attempts,
            )

    def run_bounded_cycle(self) -> tuple[RemoteManualSelectionMaterializationResult, ...]:
        results: list[RemoteManualSelectionMaterializationResult] = []
        for _index in range(self._limits.max_actions_per_cycle):
            result = self.run_once()
            results.append(result)
            if result is RemoteManualSelectionMaterializationResult.NO_ACTION:
                break
        return tuple(results)

    def _record_failure(
        self,
        claim: RemoteManualSelectionHostActionRecord,
        error_code: str,
        *,
        terminal: bool,
    ) -> RemoteManualSelectionMaterializationResult:
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
                return RemoteManualSelectionMaterializationResult.LEASE_LOST
            raise
        return (
            RemoteManualSelectionMaterializationResult.FAILED
            if terminal
            else RemoteManualSelectionMaterializationResult.RETRY
        )


@dataclass(frozen=True, slots=True)
class _JournalIdentity:
    action_id: UUID
    session_id: UUID
    batch_id: UUID
    file_id: UUID
    transfer_id: UUID
    generation: int
    output_name: str
    checksum_sha256: str
    state: str

    @classmethod
    def from_context(
        cls,
        context: RemoteManualSelectionMaterializationContext,
    ) -> _JournalIdentity:
        if context.action.transfer_id is None:
            raise ValueError("Materialization context requires a transfer ID.")
        return cls(
            action_id=context.action.id,
            session_id=context.action.session_id,
            batch_id=context.action.batch_id,
            file_id=context.action.file_id,
            transfer_id=context.action.transfer_id,
            generation=context.action.generation,
            output_name=context.output_name,
            checksum_sha256=context.checksum_sha256,
            state="prepared",
        )

    def with_state(self, state: str) -> _JournalIdentity:
        if state not in {"prepared", "published"}:
            raise ValueError("Unsupported materialization journal state.")
        return _JournalIdentity(
            action_id=self.action_id,
            session_id=self.session_id,
            batch_id=self.batch_id,
            file_id=self.file_id,
            transfer_id=self.transfer_id,
            generation=self.generation,
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
            "generation": self.generation,
            "outputName": self.output_name,
            "schemaVersion": MATERIALIZATION_JOURNAL_SCHEMA,
            "sessionId": str(self.session_id),
            "state": self.state,
            "transferId": str(self.transfer_id),
        }

    def assert_identity(self, expected: _JournalIdentity) -> None:
        if self.with_state(expected.state) != expected:
            raise _materialization_conflict(
                "REMOTE_SELECTION_MATERIALIZATION_JOURNAL_CONFLICT",
                "The existing materialization journal belongs to different content.",
            )


def _prepare_working_copy(*, source: Path, working: Path, expected_checksum: str) -> None:
    if working.exists():
        _assert_regular_not_reparse(working)
        if _checksum_regular_file(working) == expected_checksum:
            return
        raise _materialization_conflict(
            "REMOTE_SELECTION_MATERIALIZATION_TEMP_CHANGED",
            "The owned materialization temp file has unexpected content.",
        )
    digest = hashlib.sha256()
    source_stream = source.open("rb")
    try:
        descriptor = os.open(working, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as target_stream:
            while chunk := source_stream.read(MATERIALIZATION_CHUNK_BYTES):
                target_stream.write(chunk)
                digest.update(chunk)
            target_stream.flush()
            os.fsync(target_stream.fileno())
    finally:
        source_stream.close()
    if digest.hexdigest() != expected_checksum:
        working.unlink(missing_ok=True)
        raise _materialization_conflict(
            "REMOTE_SELECTION_MATERIALIZATION_SOURCE_CHANGED",
            "The verified transfer changed while its materialization temp was written.",
        )
    _assert_regular_not_reparse(working)


def _read_journal(path: Path) -> _JournalIdentity | None:
    if not path.exists():
        return None
    _assert_regular_not_reparse(path)
    payload = path.read_bytes()
    if len(payload) > MAX_MATERIALIZATION_JOURNAL_BYTES:
        raise _materialization_conflict(
            "REMOTE_SELECTION_MATERIALIZATION_JOURNAL_CONFLICT",
            "The materialization journal exceeds its bounded size.",
        )
    try:
        value = json.loads(payload)
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != MATERIALIZATION_JOURNAL_SCHEMA
        ):
            raise ValueError("schema")
        identity = _JournalIdentity(
            action_id=UUID(str(value["actionId"])),
            session_id=UUID(str(value["sessionId"])),
            batch_id=UUID(str(value["batchId"])),
            file_id=UUID(str(value["fileId"])),
            transfer_id=UUID(str(value["transferId"])),
            generation=int(value["generation"]),
            output_name=str(value["outputName"]),
            checksum_sha256=str(value["checksumSha256"]),
            state=str(value["state"]),
        )
        if identity.state not in {"prepared", "published"}:
            raise ValueError("state")
        return identity
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise _materialization_conflict(
            "REMOTE_SELECTION_MATERIALIZATION_JOURNAL_CONFLICT",
            "The materialization journal is invalid.",
        ) from error


def _write_journal(path: Path, identity: _JournalIdentity) -> None:
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
        while chunk := stream.read(MATERIALIZATION_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_regular_not_reparse(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise _materialization_conflict(
            "REMOTE_SELECTION_MATERIALIZATION_PATH_UNAVAILABLE",
            "A materialization artifact cannot be inspected safely.",
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise _materialization_conflict(
            "REMOTE_SELECTION_PATH_UNSAFE",
            "A materialization artifact is not a regular non-reparse file.",
        )


def _retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** max(0, attempt - 1)))


def _materialization_conflict(code: str, message: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(code, message)


__all__ = [
    "RemoteManualSelectionHostActionRunner",
    "RemoteManualSelectionHostMaterializer",
    "RemoteManualSelectionMaterializationLimits",
    "RemoteManualSelectionMaterializationResult",
]
