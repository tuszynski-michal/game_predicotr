"""Bounded crash recovery and aggregate-only diagnostics for remote selections."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionGcPreview,
    RemoteManualSelectionHostRepository,
    RemoteManualSelectionHostService,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionError,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionQueueSnapshot,
    RemoteManualSelectionRecoveryTransferCandidate,
    SqlAlchemyRemoteManualSelectionRepository,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_RECOVERY_LIMIT = 100
_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|[\\/]{2})[^\s\"']+")
_SENSITIVE_KEY_PARTS = (
    "token",
    "code",
    "secret",
    "salt",
    "path",
    "cookie",
    "authorization",
    "lease_token",
)


class RemoteManualSelectionRecoveryRepository(RemoteManualSelectionHostRepository, Protocol):
    def get_batch(self, batch_id: UUID) -> RemoteManualSelectionBatchV1 | None: ...

    def list_stale_transfer_candidates(
        self,
        *,
        stale_before: datetime,
        limit: int,
    ) -> tuple[RemoteManualSelectionRecoveryTransferCandidate, ...]: ...

    def recover_verified_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        verified_relative_path: str,
        checksum_sha256: str,
        recovered_at: datetime,
    ) -> bool: ...

    def fail_stale_transfer(
        self,
        candidate: RemoteManualSelectionRecoveryTransferCandidate,
        *,
        error_code: str,
        recovered_at: datetime,
    ) -> bool: ...

    def enqueue_missing_materialization_actions(self, *, limit: int) -> int: ...

    def get_batch_queue_snapshot(
        self,
        *,
        batch_id: UUID,
        now: datetime,
        stale_before: datetime,
    ) -> RemoteManualSelectionQueueSnapshot: ...


@dataclass(frozen=True, slots=True)
class RemoteSelectionRecoveryFinding:
    code: str
    count: int


@dataclass(frozen=True, slots=True)
class RemoteSelectionRecoveryReport:
    inspected_transfer_count: int
    recovered_transfer_count: int
    failed_transfer_count: int
    queued_materialization_count: int
    findings: tuple[RemoteSelectionRecoveryFinding, ...]
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class RemoteSelectionRecoveryStatus:
    batch_id: UUID
    queue: RemoteManualSelectionQueueSnapshot
    gc_preview: RemoteManualSelectionGcPreview


class RemoteManualSelectionRecoveryService:
    def __init__(
        self,
        repository: RemoteManualSelectionRecoveryRepository,
        host: RemoteManualSelectionHostService,
        *,
        upload_timeout: timedelta = timedelta(seconds=120),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if upload_timeout.total_seconds() <= 0:
            raise ValueError("Remote selection recovery timeout must be positive.")
        self._repository = repository
        self._host = host
        self._upload_timeout = upload_timeout
        self._now = now or (lambda: datetime.now(UTC))

    def reconcile(self, *, limit: int = DEFAULT_RECOVERY_LIMIT) -> RemoteSelectionRecoveryReport:
        if limit < 1:
            raise ValueError("Remote selection recovery limit must be positive.")
        now = self._now()
        candidates = self._repository.list_stale_transfer_candidates(
            stale_before=now - self._upload_timeout,
            limit=limit,
        )
        findings: Counter[str] = Counter()
        recovered = 0
        failed = 0
        for candidate in candidates:
            transfer = candidate.transfer
            try:
                inspection = self._host.inspect_transfer_artifacts(
                    self._repository,
                    session_id=transfer.session_id,
                    batch_id=transfer.batch_id,
                    file_id=transfer.file_id,
                    generation=transfer.generation,
                    transfer_id=transfer.id,
                    expected_bytes=transfer.declared_bytes,
                    expected_checksum_sha256=transfer.declared_checksum_sha256,
                )
            except (OSError, RemoteManualSelectionError):
                code = "REMOTE_SELECTION_RECOVERY_INSPECTION_FAILED"
                if self._repository.fail_stale_transfer(
                    candidate,
                    error_code=code,
                    recovered_at=now,
                ):
                    failed += 1
                    findings[code] += 1
                continue
            if (
                inspection.state == "verified"
                and inspection.verified_relative_path is not None
                and inspection.checksum_sha256 is not None
            ):
                changed = self._repository.recover_verified_transfer(
                    candidate,
                    verified_relative_path=inspection.verified_relative_path,
                    checksum_sha256=inspection.checksum_sha256,
                    recovered_at=now,
                )
                if changed:
                    recovered += 1
                    findings["REMOTE_SELECTION_RECOVERED_VERIFIED_TRANSFER"] += 1
                continue
            code = {
                "partial": "REMOTE_SELECTION_ORPHAN_PART_RETAINED",
                "conflict": "REMOTE_SELECTION_TRANSFER_ARTIFACT_CONFLICT",
                "missing": "REMOTE_SELECTION_TRANSFER_ARTIFACT_MISSING",
            }.get(inspection.state, "REMOTE_SELECTION_TRANSFER_ARTIFACT_INVALID")
            if self._repository.fail_stale_transfer(
                candidate,
                error_code=code,
                recovered_at=now,
            ):
                failed += 1
                findings[code] += 1
        queued = self._repository.enqueue_missing_materialization_actions(limit=limit)
        if queued:
            findings["REMOTE_SELECTION_MATERIALIZATION_ACTION_RECOVERED"] += queued
        report = RemoteSelectionRecoveryReport(
            inspected_transfer_count=len(candidates),
            recovered_transfer_count=recovered,
            failed_transfer_count=failed,
            queued_materialization_count=queued,
            findings=tuple(
                RemoteSelectionRecoveryFinding(code, count)
                for code, count in sorted(findings.items())
            ),
            completed_at=now,
        )
        LOGGER.info(
            "remote_selection_recovery_complete inspected=%d recovered=%d failed=%d queued=%d",
            report.inspected_transfer_count,
            report.recovered_transfer_count,
            report.failed_transfer_count,
            report.queued_materialization_count,
        )
        return report

    def status(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
    ) -> RemoteSelectionRecoveryStatus:
        batch = self._repository.get_batch(batch_id)
        if batch is None or batch.session_id != session_id:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The batch does not belong to the remote selection session.",
            )
        now = self._now()
        return RemoteSelectionRecoveryStatus(
            batch_id=batch_id,
            queue=self._repository.get_batch_queue_snapshot(
                batch_id=batch_id,
                now=now,
                stale_before=now - self._upload_timeout,
            ),
            gc_preview=self._host.preview_gc(
                self._repository,
                session_id=session_id,
                batch_id=batch_id,
            ),
        )


class RemoteManualSelectionRecoveryRunner:
    """New-transaction wrapper used at process startup and by the general worker."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        host: RemoteManualSelectionHostService,
        *,
        enabled: bool = True,
        upload_timeout: timedelta = timedelta(seconds=120),
        limit: int = DEFAULT_RECOVERY_LIMIT,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._host = host
        self._enabled = enabled
        self._upload_timeout = upload_timeout
        self._limit = limit
        self._now = now

    def run_bounded_cycle(self) -> RemoteSelectionRecoveryReport | None:
        if not self._enabled:
            return None
        with self._session_factory() as session:
            report = RemoteManualSelectionRecoveryService(
                SqlAlchemyRemoteManualSelectionRepository(session),
                self._host,
                upload_timeout=self._upload_timeout,
                now=self._now,
            ).reconcile(limit=self._limit)
            session.commit()
            return report


def redact_remote_selection_diagnostic(value: object) -> object:
    """Recursively redact host paths and credential-like fields before logging."""

    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            result[str(key)] = (
                "[REDACTED]"
                if any(part in normalized for part in _SENSITIVE_KEY_PARTS)
                else redact_remote_selection_diagnostic(item)
            )
        return result
    if isinstance(value, list | tuple):
        return [redact_remote_selection_diagnostic(item) for item in value]
    if isinstance(value, str):
        return _WINDOWS_PATH.sub("[REDACTED_PATH]", value)
    return value


__all__ = [
    "RemoteManualSelectionRecoveryRunner",
    "RemoteManualSelectionRecoveryService",
    "RemoteSelectionRecoveryFinding",
    "RemoteSelectionRecoveryReport",
    "RemoteSelectionRecoveryStatus",
    "redact_remote_selection_diagnostic",
]
