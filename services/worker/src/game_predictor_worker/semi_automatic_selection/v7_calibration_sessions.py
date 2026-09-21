"""Durable, server-owned annotation sessions for V7 label geometry calibration.

The store deliberately accepts already-attested source identities rather than a
path supplied by a browser. HTTP, EXIF decoding and asset access are layered on
top in a later task.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from .contracts import validate_sha256
from .v7_calibration import V7AnnotationState, V7CropAssessment
from .v7_configuration import V7CorpusSplit

V7_CALIBRATION_SESSION_SCHEMA_VERSION = 1
_LOCK_TIMEOUT_SECONDS = 5.0


class V7CalibrationSessionError(ValueError):
    """A stable domain error for durable label-geometry session state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class V7CalibrationSessionStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED_SOURCE_DRIFT = "blocked_source_drift"


class V7CalibrationSessionOperationKind(StrEnum):
    ANNOTATED = "annotated"
    UNAVAILABLE = "unavailable"
    SET_CAPTURE_GROUP = "set_capture_group"


@dataclass(frozen=True, slots=True)
class V7CalibrationSessionSource:
    """A source identity supplied only by the server-side corpus resolver."""

    source_id: str
    source_checksum_sha256: str
    corpus_case_id: str
    split: V7CorpusSplit
    geometry_family_id: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.corpus_case_id or not self.geometry_family_id:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SOURCE_INVALID",
                "Calibration session source identity is invalid.",
            )
        try:
            validate_sha256(self.source_checksum_sha256, field="sourceChecksumSha256")
        except ValueError as error:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SOURCE_INVALID",
                "Calibration session source checksum is invalid.",
            ) from error

    def as_dict(self) -> dict[str, object]:
        return {
            "corpusCaseId": self.corpus_case_id,
            "geometryFamilyId": self.geometry_family_id,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
            "split": self.split.value,
        }


@dataclass(frozen=True, slots=True)
class V7CalibrationSessionSlot:
    """One explicit review state for a source and one of the nine label slots."""

    source_id: str
    position_index: int
    state: V7AnnotationState = V7AnnotationState.UNREVIEWED
    center_x: float | None = None
    center_y: float | None = None
    crop_assessment: V7CropAssessment | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not 0 <= self.position_index < 9:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SLOT_INVALID", "Calibration session slot is invalid."
            )
        is_annotated = self.state is V7AnnotationState.ANNOTATED
        if is_annotated:
            if self.center_x is None or self.center_y is None or self.crop_assessment is None:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_SLOT_INVALID",
                    "An annotated slot requires normalized centre and crop assessment.",
                )
            if not 0 < self.center_x < 1 or not 0 < self.center_y < 1:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_SLOT_INVALID",
                    "An annotated slot centre must be normalized.",
                )
        elif any(
            value is not None for value in (self.center_x, self.center_y, self.crop_assessment)
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SLOT_INVALID",
                "Only an annotated slot may contain label geometry.",
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "centerX": self.center_x,
            "centerY": self.center_y,
            "cropAssessment": (
                None if self.crop_assessment is None else self.crop_assessment.value
            ),
            "positionIndex": self.position_index,
            "sourceId": self.source_id,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class V7CalibrationSessionReceipt:
    """The durable answer to a potentially replayed mutation command."""

    operation_id: str
    operation_fingerprint: str
    revision: int

    def __post_init__(self) -> None:
        _validate_uuid(self.operation_id, "V7_CALIBRATION_SESSION_OPERATION_INVALID")
        if self.revision < 1:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_RECEIPT_INVALID", "Session receipt revision is invalid."
            )
        try:
            validate_sha256(self.operation_fingerprint, field="operationFingerprint")
        except ValueError as error:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_RECEIPT_INVALID",
                "Session receipt fingerprint is invalid.",
            ) from error

    def as_dict(self) -> dict[str, object]:
        return {
            "operationFingerprint": self.operation_fingerprint,
            "operationId": self.operation_id,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class V7CalibrationSessionOperation:
    """One compare-and-swap session mutation with a browser-stable operation ID."""

    operation_id: str
    expected_revision: int
    kind: V7CalibrationSessionOperationKind
    source_id: str
    position_index: int | None = None
    center_x: float | None = None
    center_y: float | None = None
    crop_assessment: V7CropAssessment | None = None
    capture_group_id: str | None = None

    def __post_init__(self) -> None:
        _validate_uuid(self.operation_id, "V7_CALIBRATION_SESSION_OPERATION_INVALID")
        if self.expected_revision < 0 or not self.source_id:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_OPERATION_INVALID", "Session operation is invalid."
            )
        is_point = self.kind is V7CalibrationSessionOperationKind.ANNOTATED
        is_unavailable = self.kind is V7CalibrationSessionOperationKind.UNAVAILABLE
        if (is_point or is_unavailable) and (
            self.position_index is None or not 0 <= self.position_index < 9
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_OPERATION_INVALID",
                "A slot operation requires a valid position index.",
            )
        if is_point:
            if (
                self.center_x is None
                or self.center_y is None
                or self.crop_assessment is None
                or not 0 < self.center_x < 1
                or not 0 < self.center_y < 1
                or self.capture_group_id is not None
            ):
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_OPERATION_INVALID",
                    "An annotation operation requires normalized centre and crop assessment.",
                )
        elif is_unavailable:
            if any(
                value is not None
                for value in (
                    self.center_x,
                    self.center_y,
                    self.crop_assessment,
                    self.capture_group_id,
                )
            ):
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_OPERATION_INVALID",
                    "An unavailable operation cannot contain annotation values.",
                )
        elif self.kind is V7CalibrationSessionOperationKind.SET_CAPTURE_GROUP and (
            self.position_index is not None
            or self.center_x is not None
            or self.center_y is not None
            or self.crop_assessment is not None
            or not self.capture_group_id
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_OPERATION_INVALID",
                "A capture-group operation requires only a non-empty group ID.",
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "captureGroupId": self.capture_group_id,
            "centerX": self.center_x,
            "centerY": self.center_y,
            "cropAssessment": (
                None if self.crop_assessment is None else self.crop_assessment.value
            ),
            "expectedRevision": self.expected_revision,
            "kind": self.kind.value,
            "operationId": self.operation_id,
            "positionIndex": self.position_index,
            "sourceId": self.source_id,
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class V7CalibrationSession:
    """The complete snapshot written atomically for one calibration session."""

    session_id: str
    revision: int
    manifest_fingerprint: str
    geometry_family_id: str
    sources: tuple[V7CalibrationSessionSource, ...]
    slots: tuple[V7CalibrationSessionSlot, ...]
    capture_groups: tuple[tuple[str, str], ...]
    receipts: tuple[V7CalibrationSessionReceipt, ...]
    status: V7CalibrationSessionStatus = V7CalibrationSessionStatus.ACTIVE

    def __post_init__(self) -> None:
        _validate_uuid(self.session_id, "V7_CALIBRATION_SESSION_INVALID")
        if self.revision < 0 or not self.geometry_family_id or not self.sources:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_INVALID", "Calibration session is invalid."
            )
        try:
            validate_sha256(self.manifest_fingerprint, field="manifestFingerprint")
        except ValueError as error:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_INVALID", "Calibration session manifest is invalid."
            ) from error
        source_ids = tuple(item.source_id for item in self.sources)
        source_checksums = tuple(item.source_checksum_sha256 for item in self.sources)
        if (
            len(source_ids) != len(set(source_ids))
            or len(source_checksums) != len(set(source_checksums))
            or any(
                item.split is not V7CorpusSplit.CALIBRATION
                or item.geometry_family_id != self.geometry_family_id
                for item in self.sources
            )
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SOURCE_INVALID",
                "Calibration session sources must be unique calibration sources of one family.",
            )
        slot_keys = tuple((item.source_id, item.position_index) for item in self.slots)
        if (
            len(slot_keys) != len(set(slot_keys))
            or any(item.source_id not in source_ids for item in self.slots)
            or len(self.slots) != len(source_ids) * 9
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_SLOT_INVALID", "Calibration session slots are incomplete."
            )
        groups = dict(self.capture_groups)
        if (
            len(groups) != len(self.capture_groups)
            or set(groups) - set(source_ids)
            or any(not group for group in groups.values())
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_GROUP_INVALID",
                "Calibration session capture groups are invalid.",
            )
        receipt_ids = tuple(item.operation_id for item in self.receipts)
        if len(receipt_ids) != len(set(receipt_ids)) or any(
            item.revision > self.revision for item in self.receipts
        ):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_RECEIPT_INVALID",
                "Calibration session receipts are invalid.",
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "captureGroups": [
                {"captureGroupId": group_id, "sourceId": source_id}
                for source_id, group_id in self.capture_groups
            ],
            "geometryFamilyId": self.geometry_family_id,
            "manifestFingerprint": self.manifest_fingerprint,
            "receipts": [item.as_dict() for item in self.receipts],
            "revision": self.revision,
            "sessionId": self.session_id,
            "slots": [item.as_dict() for item in self.slots],
            "sources": [item.as_dict() for item in self.sources],
            "status": self.status.value,
        }

    def export_dict(self) -> dict[str, object]:
        value = self.as_dict()
        value.pop("receipts")
        return {
            "session": value,
            "schemaVersion": V7_CALIBRATION_SESSION_SCHEMA_VERSION,
        }

    def receipt_for(self, operation_id: str) -> V7CalibrationSessionReceipt | None:
        return next((item for item in self.receipts if item.operation_id == operation_id), None)


@dataclass(frozen=True, slots=True)
class V7CalibrationSessionExport:
    """An immutable export reference; its checksum identifies its contents."""

    export_checksum_sha256: str
    revision: int
    path: Path

    def __post_init__(self) -> None:
        try:
            validate_sha256(self.export_checksum_sha256, field="exportChecksumSha256")
        except ValueError as error:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_EXPORT_INVALID", "Session export checksum is invalid."
            ) from error
        if self.revision < 0:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_EXPORT_INVALID", "Session export revision is invalid."
            )


class V7CalibrationSessionStore:
    """Atomic JSON snapshots with a process/file lock per session ID."""

    _thread_lock_guard = threading.Lock()
    _thread_locks: dict[Path, threading.Lock] = {}

    def __init__(self, runtime_root: Path) -> None:
        self._sessions_root = Path(runtime_root) / "v7-label-geometry" / "sessions"

    def create(
        self,
        *,
        manifest_fingerprint: str,
        geometry_family_id: str,
        sources: Sequence[V7CalibrationSessionSource],
        session_id: str | None = None,
    ) -> V7CalibrationSession:
        result_id = session_id or str(uuid4())
        _validate_uuid(result_id, "V7_CALIBRATION_SESSION_INVALID")
        if not geometry_family_id:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_INVALID", "Calibration session family is required."
            )
        frozen_sources = _sorted_sources(sources)
        session = V7CalibrationSession(
            session_id=result_id,
            revision=0,
            manifest_fingerprint=manifest_fingerprint,
            geometry_family_id=geometry_family_id,
            sources=frozen_sources,
            slots=tuple(
                V7CalibrationSessionSlot(source_id=item.source_id, position_index=position)
                for item in frozen_sources
                for position in range(9)
            ),
            capture_groups=(),
            receipts=(),
        )
        with self._lock(result_id):
            if self._state_path(result_id).exists() or self._temporary_path(result_id).exists():
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_EXISTS", "Calibration session already exists."
                )
            self._write_state(session)
        return session

    def read(self, session_id: str) -> V7CalibrationSession:
        _validate_uuid(session_id, "V7_CALIBRATION_SESSION_INVALID")
        with self._lock(session_id):
            return self._read_state(session_id)

    def apply(
        self,
        session_id: str,
        operation: V7CalibrationSessionOperation,
        *,
        current_sources: Sequence[V7CalibrationSessionSource],
    ) -> tuple[V7CalibrationSession, V7CalibrationSessionReceipt]:
        """Persist one operation or return its original receipt before revision checking."""

        _validate_uuid(session_id, "V7_CALIBRATION_SESSION_INVALID")
        with self._lock(session_id):
            session = self._read_state(session_id)
            receipt = session.receipt_for(operation.operation_id)
            if receipt is not None:
                if receipt.operation_fingerprint != operation.fingerprint:
                    raise V7CalibrationSessionError(
                        "V7_CALIBRATION_SESSION_OPERATION_ID_CONFLICT",
                        "Operation ID was already used with different content.",
                    )
                return session, receipt
            self._verify_current_sources(session, current_sources)
            if session.status is not V7CalibrationSessionStatus.ACTIVE:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_BLOCKED", "Calibration session is blocked."
                )
            if operation.expected_revision != session.revision:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_REVISION_CONFLICT",
                    "Calibration session changed in another client. Reload the session.",
                )
            updated = _apply_operation(session, operation)
            receipt = V7CalibrationSessionReceipt(
                operation_id=operation.operation_id,
                operation_fingerprint=operation.fingerprint,
                revision=updated.revision,
            )
            updated = V7CalibrationSession(
                session_id=updated.session_id,
                revision=updated.revision,
                manifest_fingerprint=updated.manifest_fingerprint,
                geometry_family_id=updated.geometry_family_id,
                sources=updated.sources,
                slots=updated.slots,
                capture_groups=updated.capture_groups,
                receipts=(*updated.receipts, receipt),
                status=updated.status,
            )
            self._write_state(updated)
            return updated, receipt

    def export(
        self,
        session_id: str,
        *,
        expected_revision: int,
        current_sources: Sequence[V7CalibrationSessionSource],
    ) -> V7CalibrationSessionExport:
        """Write a content-addressed, immutable export of the current session state."""

        _validate_uuid(session_id, "V7_CALIBRATION_SESSION_INVALID")
        with self._lock(session_id):
            session = self._read_state(session_id)
            self._verify_current_sources(session, current_sources)
            if session.status is not V7CalibrationSessionStatus.ACTIVE:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_BLOCKED", "Calibration session is blocked."
                )
            if expected_revision != session.revision:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_REVISION_CONFLICT",
                    "Calibration session changed in another client. Reload the session.",
                )
            content = _canonical_json(session.export_dict())
            checksum = hashlib.sha256(content).hexdigest()
            # Keep the Windows path safely below legacy MAX_PATH even below a
            # long operator/runtime root. The full digest remains in content
            # and in the returned export identity; a prefix collision fails closed.
            export_key = checksum[:24]
            path = self._session_directory(session_id) / "exports" / f"{export_key}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = path.parent / f".{export_key}.{uuid4().hex}.tmp"
            try:
                with temporary_path.open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(temporary_path, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise V7CalibrationSessionError(
                        "V7_CALIBRATION_SESSION_EXPORT_CONFLICT",
                        "An immutable export path has different content.",
                    ) from None
            finally:
                temporary_path.unlink(missing_ok=True)
            return V7CalibrationSessionExport(
                export_checksum_sha256=checksum,
                revision=session.revision,
                path=path,
            )

    def _verify_current_sources(
        self,
        session: V7CalibrationSession,
        current_sources: Sequence[V7CalibrationSessionSource],
    ) -> None:
        if _sorted_sources(current_sources) == session.sources:
            return
        if session.status is V7CalibrationSessionStatus.ACTIVE:
            blocked = V7CalibrationSession(
                session_id=session.session_id,
                revision=session.revision,
                manifest_fingerprint=session.manifest_fingerprint,
                geometry_family_id=session.geometry_family_id,
                sources=session.sources,
                slots=session.slots,
                capture_groups=session.capture_groups,
                receipts=session.receipts,
                status=V7CalibrationSessionStatus.BLOCKED_SOURCE_DRIFT,
            )
            self._write_state(blocked)
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_SOURCE_DRIFT",
            "A source changed after calibration session creation; the session is blocked.",
        )

    def _session_directory(self, session_id: str) -> Path:
        return self._sessions_root / session_id

    def _state_path(self, session_id: str) -> Path:
        return self._session_directory(session_id) / "state.json"

    def _temporary_path(self, session_id: str) -> Path:
        return self._session_directory(session_id) / "state.json.tmp"

    def _read_state(self, session_id: str) -> V7CalibrationSession:
        state_path = self._state_path(session_id)
        temporary_path = self._temporary_path(session_id)
        if temporary_path.exists():
            temporary = _read_session_file(temporary_path, expected_session_id=session_id)
            if state_path.exists():
                current = _read_session_file(state_path, expected_session_id=session_id)
                if not _is_recoverable_successor(current, temporary):
                    raise V7CalibrationSessionError(
                        "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT",
                        "Session temporary snapshot is not a valid successor of durable state.",
                    )
            os.replace(temporary_path, state_path)
            return temporary
        if not state_path.exists():
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_NOT_FOUND", "Calibration session does not exist."
            )
        return _read_session_file(state_path, expected_session_id=session_id)

    def _write_state(self, session: V7CalibrationSession) -> None:
        state_path = self._state_path(session.session_id)
        temporary_path = self._temporary_path(session.session_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if temporary_path.exists():
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT",
                "Session has an unfinished temporary snapshot.",
            )
        with temporary_path.open("xb") as output:
            output.write(_canonical_json({"session": session.as_dict(), "schemaVersion": 1}))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, state_path)

    @contextmanager
    def _lock(self, session_id: str) -> Iterator[None]:
        directory = self._session_directory(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = directory / "session.lock"
        with self._thread_lock_guard:
            lock = self._thread_locks.setdefault(lock_path, threading.Lock())
        if not lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS):
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_LOCK_TIMEOUT", "Calibration session is busy."
            )
        handle: BinaryIO | None = None
        acquired = False
        try:
            handle = lock_path.open("a+b")
            _acquire_file_lock(handle)
            acquired = True
            yield
        finally:
            if acquired and handle is not None:
                _release_file_lock(handle)
            if handle is not None:
                handle.close()
            lock.release()


def _apply_operation(
    session: V7CalibrationSession, operation: V7CalibrationSessionOperation
) -> V7CalibrationSession:
    if operation.source_id not in {item.source_id for item in session.sources}:
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_SOURCE_NOT_FOUND", "Calibration session source does not exist."
        )
    slots = list(session.slots)
    groups = dict(session.capture_groups)
    if operation.kind is V7CalibrationSessionOperationKind.SET_CAPTURE_GROUP:
        assert operation.capture_group_id is not None
        groups[operation.source_id] = operation.capture_group_id
    else:
        assert operation.position_index is not None
        index = next(
            index
            for index, item in enumerate(slots)
            if item.source_id == operation.source_id
            and item.position_index == operation.position_index
        )
        if operation.kind is V7CalibrationSessionOperationKind.ANNOTATED:
            slots[index] = V7CalibrationSessionSlot(
                source_id=operation.source_id,
                position_index=operation.position_index,
                state=V7AnnotationState.ANNOTATED,
                center_x=operation.center_x,
                center_y=operation.center_y,
                crop_assessment=operation.crop_assessment,
            )
        else:
            slots[index] = V7CalibrationSessionSlot(
                source_id=operation.source_id,
                position_index=operation.position_index,
                state=V7AnnotationState.UNAVAILABLE,
            )
    return V7CalibrationSession(
        session_id=session.session_id,
        revision=session.revision + 1,
        manifest_fingerprint=session.manifest_fingerprint,
        geometry_family_id=session.geometry_family_id,
        sources=session.sources,
        slots=tuple(slots),
        capture_groups=tuple(sorted(groups.items())),
        receipts=session.receipts,
        status=session.status,
    )


def _read_session_file(path: Path, *, expected_session_id: str) -> V7CalibrationSession:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", "Calibration session snapshot is unreadable."
        ) from error
    if (
        not isinstance(value, dict)
        or value.get("schemaVersion") != V7_CALIBRATION_SESSION_SCHEMA_VERSION
    ):
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", "Calibration session snapshot schema is invalid."
        )
    raw_session = value.get("session")
    if not isinstance(raw_session, dict):
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", "Calibration session snapshot lacks state."
        )
    try:
        raw_sources = _object_list(raw_session.get("sources"), "sources")
        sources = tuple(
            V7CalibrationSessionSource(
                source_id=_text(item.get("sourceId"), "sourceId"),
                source_checksum_sha256=_text(
                    item.get("sourceChecksumSha256"), "sourceChecksumSha256"
                ),
                corpus_case_id=_text(item.get("corpusCaseId"), "corpusCaseId"),
                split=V7CorpusSplit(_text(item.get("split"), "split")),
                geometry_family_id=_text(item.get("geometryFamilyId"), "geometryFamilyId"),
            )
            for item in raw_sources
        )
        slots = tuple(
            V7CalibrationSessionSlot(
                source_id=_text(item.get("sourceId"), "sourceId"),
                position_index=_integer(item.get("positionIndex"), "positionIndex"),
                state=V7AnnotationState(_text(item.get("state"), "state")),
                center_x=_optional_number(item.get("centerX"), "centerX"),
                center_y=_optional_number(item.get("centerY"), "centerY"),
                crop_assessment=(
                    None
                    if item.get("cropAssessment") is None
                    else V7CropAssessment(_text(item.get("cropAssessment"), "cropAssessment"))
                ),
            )
            for item in _object_list(raw_session.get("slots"), "slots")
        )
        groups = tuple(
            (
                _text(item.get("sourceId"), "sourceId"),
                _text(item.get("captureGroupId"), "captureGroupId"),
            )
            for item in _object_list(raw_session.get("captureGroups"), "captureGroups")
        )
        receipts = tuple(
            V7CalibrationSessionReceipt(
                operation_id=_text(item.get("operationId"), "operationId"),
                operation_fingerprint=_text(
                    item.get("operationFingerprint"), "operationFingerprint"
                ),
                revision=_integer(item.get("revision"), "revision"),
            )
            for item in _object_list(raw_session.get("receipts"), "receipts")
        )
        result = V7CalibrationSession(
            session_id=_text(raw_session.get("sessionId"), "sessionId"),
            revision=_integer(raw_session.get("revision"), "revision"),
            manifest_fingerprint=_text(
                raw_session.get("manifestFingerprint"), "manifestFingerprint"
            ),
            geometry_family_id=_text(raw_session.get("geometryFamilyId"), "geometryFamilyId"),
            sources=_sorted_sources(sources),
            slots=tuple(sorted(slots, key=lambda item: (item.source_id, item.position_index))),
            capture_groups=tuple(sorted(groups)),
            receipts=receipts,
            status=V7CalibrationSessionStatus(_text(raw_session.get("status"), "status")),
        )
        if result.session_id != expected_session_id:
            raise V7CalibrationSessionError(
                "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT",
                "Calibration session snapshot belongs to a different session.",
            )
        return result
    except (TypeError, ValueError) as error:
        if isinstance(error, V7CalibrationSessionError):
            raise
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", "Calibration session snapshot is invalid."
        ) from error


def _sorted_sources(
    values: Sequence[V7CalibrationSessionSource],
) -> tuple[V7CalibrationSessionSource, ...]:
    return tuple(sorted(values, key=lambda item: item.source_id))


def _is_recoverable_successor(
    current: V7CalibrationSession, temporary: V7CalibrationSession
) -> bool:
    """Recognize the only two writes that may be interrupted after temp fsync."""

    if (
        current.session_id != temporary.session_id
        or current.manifest_fingerprint != temporary.manifest_fingerprint
        or current.geometry_family_id != temporary.geometry_family_id
        or current.sources != temporary.sources
    ):
        return False
    if temporary.revision == current.revision + 1:
        return (
            current.status is V7CalibrationSessionStatus.ACTIVE
            and temporary.status is V7CalibrationSessionStatus.ACTIVE
            and temporary.receipts[: len(current.receipts)] == current.receipts
            and len(temporary.receipts) == len(current.receipts) + 1
            and temporary.receipts[-1].revision == temporary.revision
        )
    return (
        temporary.revision == current.revision
        and current.status is V7CalibrationSessionStatus.ACTIVE
        and temporary.status is V7CalibrationSessionStatus.BLOCKED_SOURCE_DRIFT
        and temporary.slots == current.slots
        and temporary.capture_groups == current.capture_groups
        and temporary.receipts == current.receipts
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _validate_uuid(value: str, code: str) -> None:
    try:
        UUID(value)
    except (TypeError, ValueError) as error:
        raise V7CalibrationSessionError(code, "Calibration session UUID is invalid.") from error


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", f"Calibration session {field} is invalid."
        )
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", f"Calibration session {field} is invalid."
        )
    return value


def _optional_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", f"Calibration session {field} is invalid."
        )
    return float(value)


def _object_list(value: object, field: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise V7CalibrationSessionError(
            "V7_CALIBRATION_SESSION_CORRUPT", f"Calibration session {field} is invalid."
        )
    return value


def _acquire_file_lock(handle: BinaryIO) -> None:
    """Acquire a short-lived non-blocking Windows lock after the in-process lock."""

    import msvcrt

    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    while True:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise V7CalibrationSessionError(
                    "V7_CALIBRATION_SESSION_LOCK_TIMEOUT", "Calibration session is busy."
                ) from None
            time.sleep(0.02)


def _release_file_lock(handle: BinaryIO) -> None:
    import msvcrt

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


__all__ = [
    "V7CalibrationSession",
    "V7CalibrationSessionError",
    "V7CalibrationSessionExport",
    "V7CalibrationSessionOperation",
    "V7CalibrationSessionOperationKind",
    "V7CalibrationSessionReceipt",
    "V7CalibrationSessionSlot",
    "V7CalibrationSessionSource",
    "V7CalibrationSessionStatus",
    "V7CalibrationSessionStore",
]
