"""One cross-process GPU lease for application grid runs (TASK-1005).

The lease is a JSON record next to a short-lived ``.lock`` file. Every read-decide-write
happens under that lock and the record is replaced atomically, so two workers never both
hold it. A live owner keeps the lease even after its term; the record is taken over only
when the term has passed and the owning PID with its creation time no longer exists.
An unreadable record or an unknown process state blocks instead of being removed.
The lease does not control CUDA processes outside the application or laboratory runs.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .process_identity import process_created

LEASE_FORMAT = "grid-gpu-lease-v1"
LEASE_SECONDS = 60.0
LOCK_WAIT_SECONDS = 5.0
LEASE_DIRECTORY = "grid-training"
LEASE_FILE = "gpu-lease.json"

RunKind = Literal["train", "smoke"]
LeaseState = Literal["free", "held", "stale", "unknown"]
ProcessProbe = Callable[[int], str | None]


class GpuLeaseError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LeaseRecord:
    token: str
    run_kind: RunKind
    run_id: str
    pid: int
    process_created: str
    acquired_at: float
    expires_at: float
    format: str = LEASE_FORMAT


@dataclass(frozen=True)
class LeaseObservation:
    state: LeaseState
    record: LeaseRecord | None


def _finite(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _validated(record: LeaseRecord) -> LeaseRecord:
    """Every field must have its exact type; anything else is an unknown lease."""
    texts = (record.token, record.run_id, record.process_created)
    if (
        record.format != LEASE_FORMAT
        or record.run_kind not in ("train", "smoke")
        or not all(isinstance(text, str) and text for text in texts)
        or not isinstance(record.pid, int)
        or isinstance(record.pid, bool)
        or record.pid <= 0
        or not _finite(record.acquired_at)
        or not _finite(record.expires_at)
    ):
        raise ValueError(LEASE_FORMAT)
    return record


def lease_path(artifact_root: Path) -> Path:
    return artifact_root / LEASE_DIRECTORY / LEASE_FILE


@contextmanager
def _locked(directory: Path, wait_seconds: float) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock"
    deadline = time.monotonic() + wait_seconds
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        while True:
            stream.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise GpuLeaseError("GRID_RUN_LEASE_LOCK_TIMEOUT") from error
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class GpuLease:
    """File-backed lease; ``clock`` is wall time because the term must survive a restart."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = time.time,
        probe: ProcessProbe = process_created,
        lease_seconds: float = LEASE_SECONDS,
        lock_wait_seconds: float = LOCK_WAIT_SECONDS,
    ) -> None:
        self.path = path
        self.clock = clock
        self.probe = probe
        self.lease_seconds = lease_seconds
        self.lock_wait_seconds = lock_wait_seconds

    def _read(self) -> LeaseRecord | None:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or value.get("format") != LEASE_FORMAT:
                raise ValueError(LEASE_FORMAT)
            return _validated(LeaseRecord(**value))
        except (ValueError, TypeError) as error:
            raise GpuLeaseError("GRID_RUN_LEASE_UNKNOWN") from error

    def _write(self, record: LeaseRecord) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        data = json.dumps(asdict(record), sort_keys=True).encode("utf-8")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def _state(self, record: LeaseRecord | None) -> LeaseState:
        if record is None:
            return "free"
        if self.clock() < record.expires_at:
            return "held"
        try:
            created = self.probe(record.pid)
        except Exception as error:  # noqa: BLE001 - unknown process state protects the GPU
            raise GpuLeaseError("GRID_RUN_LEASE_UNKNOWN") from error
        return "held" if created == record.process_created else "stale"

    def observe(self) -> LeaseObservation:
        """Read-only view; any doubt is ``unknown``, never ``free``."""
        try:
            record = self._read()
            return LeaseObservation(self._state(record), record)
        except GpuLeaseError:
            return LeaseObservation("unknown", None)
        except OSError:
            return LeaseObservation("unknown", None)

    def acquire(
        self, run_kind: RunKind, run_id: str, *, pid: int | None = None, created: str | None = None
    ) -> LeaseRecord:
        owner_pid = os.getpid() if pid is None else pid
        owner_created = self.probe(owner_pid) if created is None else created
        if owner_created is None:
            raise GpuLeaseError("GRID_RUN_LEASE_UNKNOWN")
        with _locked(self.path.parent, self.lock_wait_seconds):
            state = self._state(self._read())
            if state == "held":
                raise GpuLeaseError("GRID_RUN_LEASE_BUSY")
            now = self.clock()
            record = LeaseRecord(
                token=uuid.uuid4().hex,
                run_kind=run_kind,
                run_id=run_id,
                pid=owner_pid,
                process_created=owner_created,
                acquired_at=now,
                expires_at=now + self.lease_seconds,
            )
            self._write(record)
            return record

    def renew(self, record: LeaseRecord) -> LeaseRecord:
        with _locked(self.path.parent, self.lock_wait_seconds):
            current = self._read()
            if current is None or current.token != record.token:
                raise GpuLeaseError("GRID_RUN_LEASE_LOST")
            renewed = LeaseRecord(
                **{**asdict(current), "expires_at": self.clock() + self.lease_seconds}
            )
            self._write(renewed)
            return renewed

    def release(self, record: LeaseRecord) -> None:
        """Remove only the caller's own record; a foreign or missing one is a lost lease."""
        with _locked(self.path.parent, self.lock_wait_seconds):
            current = self._read()
            if current is None or current.token != record.token:
                raise GpuLeaseError("GRID_RUN_LEASE_LOST")
            self.path.unlink()
