"""Immutable T05 validation reports and geometry-adoption registry."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7AcceptanceEvaluation,
    V7AcceptanceMetric,
    V7GeometryAdoption,
)

_SCHEMA_VERSION = 1
_LOCK_TIMEOUT_SECONDS = 5.0


class V7ValidationRegistryError(ValueError):
    """A persisted validation report or adoption cannot be trusted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class V7ValidationReport:
    """A canonical, immutable non-holdout validation result."""

    validation_report_fingerprint: str
    profile_fingerprint: str
    observer_fingerprint: str
    geometry_family_id: str
    source_game_ref: str
    corpus_manifest_fingerprint: str
    corpus_inventory_fingerprint: str
    acceptance: V7AcceptanceEvaluation
    truth: tuple[dict[str, object], ...]
    source_observations: tuple[dict[str, object], ...]
    prediction_snapshots: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if (
            not self.geometry_family_id
            or not self.source_game_ref
            or not _is_sha256(self.validation_report_fingerprint)
            or not _is_sha256(self.profile_fingerprint)
            or not _is_sha256(self.observer_fingerprint)
            or not _is_sha256(self.corpus_manifest_fingerprint)
            or not _is_sha256(self.corpus_inventory_fingerprint)
        ):
            _fail("V7_VALIDATION_REPORT_INVALID", "V7 validation report identity is invalid.")
        if self.validation_report_fingerprint != _fingerprint(self.body_dict()):
            _fail("V7_VALIDATION_REPORT_CORRUPT", "V7 validation report fingerprint is invalid.")

    def body_dict(self) -> dict[str, object]:
        return {
            "acceptance": self.acceptance.as_dict(),
            "corpusInventoryFingerprint": self.corpus_inventory_fingerprint,
            "corpusManifestFingerprint": self.corpus_manifest_fingerprint,
            "geometryFamilyId": self.geometry_family_id,
            "predictionSnapshots": list(self.prediction_snapshots),
            "observerFingerprint": self.observer_fingerprint,
            "profileFingerprint": self.profile_fingerprint,
            "sourceGameRef": self.source_game_ref,
            "sourceObservations": list(self.source_observations),
            "truth": list(self.truth),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.body_dict(),
            "validationReportFingerprint": self.validation_report_fingerprint,
        }

    @classmethod
    def create(
        cls,
        *,
        profile_fingerprint: str,
        observer_fingerprint: str,
        geometry_family_id: str,
        source_game_ref: str,
        corpus_manifest_fingerprint: str,
        corpus_inventory_fingerprint: str,
        acceptance: V7AcceptanceEvaluation,
        truth: tuple[dict[str, object], ...],
        source_observations: tuple[dict[str, object], ...],
        prediction_snapshots: tuple[dict[str, object], ...],
    ) -> V7ValidationReport:
        body = {
            "acceptance": acceptance.as_dict(),
            "corpusInventoryFingerprint": corpus_inventory_fingerprint,
            "corpusManifestFingerprint": corpus_manifest_fingerprint,
            "geometryFamilyId": geometry_family_id,
            "predictionSnapshots": list(prediction_snapshots),
            "observerFingerprint": observer_fingerprint,
            "profileFingerprint": profile_fingerprint,
            "sourceGameRef": source_game_ref,
            "sourceObservations": list(source_observations),
            "truth": list(truth),
        }
        return cls(
            validation_report_fingerprint=_fingerprint(body),
            profile_fingerprint=profile_fingerprint,
            observer_fingerprint=observer_fingerprint,
            geometry_family_id=geometry_family_id,
            source_game_ref=source_game_ref,
            corpus_manifest_fingerprint=corpus_manifest_fingerprint,
            corpus_inventory_fingerprint=corpus_inventory_fingerprint,
            acceptance=acceptance,
            truth=truth,
            source_observations=source_observations,
            prediction_snapshots=prediction_snapshots,
        )

    @classmethod
    def from_dict(cls, value: object) -> V7ValidationReport:
        try:
            raw_value = _mapping(value)
            acceptance_raw = _mapping(raw_value["acceptance"])
            acceptance = V7AcceptanceEvaluation(
                input_fingerprint=_string(acceptance_raw["inputFingerprint"]),
                range_recovery=_metric(acceptance_raw["rangeRecovery"]),
                representative_selection=_metric(acceptance_raw["representativeSelection"]),
                top_crop_recall=_metric(acceptance_raw["topCropRecall"]),
                bottom_crop_recall=_metric(acceptance_raw["bottomCropRecall"]),
                incorrect_automatic_range_count=_integer(
                    acceptance_raw["incorrectAutomaticRangeCount"]
                ),
                top_crop_false_positive_count=_integer(acceptance_raw["topCropFalsePositiveCount"]),
                bottom_crop_false_positive_count=_integer(
                    acceptance_raw["bottomCropFalsePositiveCount"]
                ),
                manual_review_count=_integer(acceptance_raw["manualReviewCount"]),
                total_case_count=_integer(acceptance_raw["totalCaseCount"]),
            )
            return cls(
                validation_report_fingerprint=_string(raw_value["validationReportFingerprint"]),
                profile_fingerprint=_string(raw_value["profileFingerprint"]),
                observer_fingerprint=_string(raw_value["observerFingerprint"]),
                geometry_family_id=_string(raw_value["geometryFamilyId"]),
                source_game_ref=_string(raw_value["sourceGameRef"]),
                corpus_manifest_fingerprint=_string(raw_value["corpusManifestFingerprint"]),
                corpus_inventory_fingerprint=_string(raw_value["corpusInventoryFingerprint"]),
                acceptance=acceptance,
                truth=_objects(raw_value["truth"]),
                source_observations=_objects(raw_value["sourceObservations"]),
                prediction_snapshots=_objects(raw_value["predictionSnapshots"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_REPORT_CORRUPT", "Stored V7 validation report is invalid."
            ) from error


@dataclass(frozen=True, slots=True)
class V7ValidationReceipt:
    operation_id: str
    operation_fingerprint: str
    validation_report_fingerprint: str


@dataclass(frozen=True, slots=True)
class V7AdoptionReceipt:
    operation_id: str
    operation_fingerprint: str
    adoption: V7GeometryAdoption


class V7ValidationRegistry:
    """Content-addressed local records with replay-safe operation receipts."""

    _thread_lock_guard = threading.Lock()
    _thread_locks: dict[Path, threading.Lock] = {}

    def __init__(self, runtime_root: Path) -> None:
        self._root = Path(runtime_root) / "v7-label-geometry" / "validation"

    def persist_report(
        self,
        *,
        operation_id: str,
        operation_fingerprint: str,
        report: V7ValidationReport,
    ) -> tuple[V7ValidationReport, bool]:
        _require_uuid(operation_id)
        _require_sha256(operation_fingerprint)
        with self._lock():
            receipt_path = self._report_operation_path(operation_id)
            if receipt_path.exists():
                receipt = self._read_report_receipt(receipt_path)
                if receipt.operation_fingerprint != operation_fingerprint:
                    _fail(
                        "V7_VALIDATION_OPERATION_ID_CONFLICT",
                        "Validation operation ID was already used with different content.",
                    )
                return self._get_report_unlocked(receipt.validation_report_fingerprint), False
            report_path = self._report_path(report.validation_report_fingerprint)
            created = _write_immutable(
                report_path,
                _canonical_json({"report": report.as_dict(), "schemaVersion": _SCHEMA_VERSION}),
                conflict_code="V7_VALIDATION_REPORT_CONFLICT",
                conflict_message="The immutable validation report path has different content.",
            )
            receipt = V7ValidationReceipt(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
                validation_report_fingerprint=report.validation_report_fingerprint,
            )
            _write_immutable(
                receipt_path,
                _canonical_json(
                    {
                        "operationFingerprint": receipt.operation_fingerprint,
                        "operationId": receipt.operation_id,
                        "schemaVersion": _SCHEMA_VERSION,
                        "validationReportFingerprint": receipt.validation_report_fingerprint,
                    }
                ),
                conflict_code="V7_VALIDATION_OPERATION_ID_CONFLICT",
                conflict_message="Validation operation ID was already used with different content.",
            )
            return report, created

    def replay_report(
        self,
        *,
        operation_id: str,
        operation_fingerprint: str,
    ) -> V7ValidationReport | None:
        """Return an existing receipt before mutable corpus checks run again."""

        _require_uuid(operation_id)
        _require_sha256(operation_fingerprint)
        with self._lock():
            receipt_path = self._report_operation_path(operation_id)
            if not receipt_path.exists():
                return None
            receipt = self._read_report_receipt(receipt_path)
            if receipt.operation_fingerprint != operation_fingerprint:
                _fail(
                    "V7_VALIDATION_OPERATION_ID_CONFLICT",
                    "Validation operation ID was already used with different content.",
                )
            return self._get_report_unlocked(receipt.validation_report_fingerprint)

    def get_report(self, validation_report_fingerprint: str) -> V7ValidationReport:
        _require_sha256(validation_report_fingerprint)
        with self._lock():
            return self._get_report_unlocked(validation_report_fingerprint)

    def _get_report_unlocked(self, validation_report_fingerprint: str) -> V7ValidationReport:
        if not self._report_is_committed_unlocked(validation_report_fingerprint):
            _fail(
                "V7_VALIDATION_REPORT_NOT_FOUND", "The requested validation report does not exist."
            )
        path = self._report_path(validation_report_fingerprint)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schemaVersion") != _SCHEMA_VERSION:
                raise ValueError("schema")
            report = V7ValidationReport.from_dict(value["report"])
            if report.validation_report_fingerprint != validation_report_fingerprint or value != {
                "report": report.as_dict(),
                "schemaVersion": _SCHEMA_VERSION,
            }:
                raise ValueError("identity")
            return report
        except FileNotFoundError as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_REPORT_NOT_FOUND", "The requested validation report does not exist."
            ) from error
        except (OSError, TypeError, ValueError, V7ValidationRegistryError) as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_REPORT_CORRUPT", "Stored V7 validation report is invalid."
            ) from error

    def list_adoptions(self) -> tuple[V7GeometryAdoption, ...]:
        with self._lock():
            root = self._adoptions_root()
            if not root.exists():
                return ()
            if root.is_symlink() or not root.is_dir():
                _fail(
                    "V7_VALIDATION_ADOPTION_STORE_INVALID",
                    "Geometry adoption store is unavailable.",
                )
            result = tuple(
                adoption
                for path in sorted(root.glob("*.json"), key=lambda item: item.name)
                if self._adoption_is_committed_unlocked(
                    adoption := self._read_adoption_unlocked(path)
                )
            )
            return tuple(sorted(result, key=lambda item: item.adoption_key))

    def persist_adoption(
        self,
        *,
        operation_id: str,
        operation_fingerprint: str,
        adoption: V7GeometryAdoption,
    ) -> tuple[V7GeometryAdoption, bool]:
        _require_uuid(operation_id)
        _require_sha256(operation_fingerprint)
        with self._lock():
            receipt_path = self._adoption_operation_path(operation_id)
            if receipt_path.exists():
                receipt = self._read_adoption_receipt(receipt_path)
                if receipt.operation_fingerprint != operation_fingerprint:
                    _fail(
                        "V7_VALIDATION_ADOPTION_OPERATION_ID_CONFLICT",
                        "Adoption operation ID was already used with different content.",
                    )
                return self._get_adoption_unlocked(receipt.adoption.adoption_key), False
            self._validate_adoption_unlocked(adoption)
            path = self._adoption_path(adoption.adoption_key)
            created = _write_immutable(
                path,
                _canonical_json({"adoption": adoption.as_dict(), "schemaVersion": _SCHEMA_VERSION}),
                conflict_code="V7_VALIDATION_ADOPTION_CONFLICT",
                conflict_message="The immutable geometry adoption path has different content.",
            )
            receipt = V7AdoptionReceipt(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
                adoption=adoption,
            )
            _write_immutable(
                receipt_path,
                _canonical_json(
                    {
                        "adoption": adoption.as_dict(),
                        "operationFingerprint": receipt.operation_fingerprint,
                        "operationId": receipt.operation_id,
                        "schemaVersion": _SCHEMA_VERSION,
                    }
                ),
                conflict_code="V7_VALIDATION_ADOPTION_OPERATION_ID_CONFLICT",
                conflict_message="Adoption operation ID was already used with different content.",
            )
            return adoption, created

    def replay_adoption(
        self,
        *,
        operation_id: str,
        operation_fingerprint: str,
    ) -> V7GeometryAdoption | None:
        """Return an existing receipt before mutable corpus checks run again."""

        _require_uuid(operation_id)
        _require_sha256(operation_fingerprint)
        with self._lock():
            receipt_path = self._adoption_operation_path(operation_id)
            if not receipt_path.exists():
                return None
            receipt = self._read_adoption_receipt(receipt_path)
            if receipt.operation_fingerprint != operation_fingerprint:
                _fail(
                    "V7_VALIDATION_ADOPTION_OPERATION_ID_CONFLICT",
                    "Adoption operation ID was already used with different content.",
                )
            return self._get_adoption_unlocked(receipt.adoption.adoption_key)

    def get_adoption(self, adoption_key: str) -> V7GeometryAdoption:
        if not _is_sha256(adoption_key):
            _fail(
                "V7_VALIDATION_ADOPTION_NOT_FOUND",
                "The requested geometry adoption does not exist.",
            )
        with self._lock():
            return self._get_adoption_unlocked(adoption_key)

    def _get_adoption_unlocked(self, adoption_key: str) -> V7GeometryAdoption:
        path = self._adoption_path(adoption_key)
        try:
            adoption = self._read_adoption_unlocked(path)
            if not self._adoption_is_committed_unlocked(adoption):
                _fail(
                    "V7_VALIDATION_ADOPTION_NOT_FOUND",
                    "The requested geometry adoption does not exist.",
                )
            return adoption
        except FileNotFoundError as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_ADOPTION_NOT_FOUND",
                "The requested geometry adoption does not exist.",
            ) from error

    def _report_path(self, fingerprint: str) -> Path:
        return self._root / "reports" / f"{fingerprint[:24]}.json"

    def _report_operation_path(self, operation_id: str) -> Path:
        return self._root / "report-operations" / f"{operation_id}.json"

    def _adoption_path(self, adoption_key: str) -> Path:
        return self._adoptions_root() / f"{adoption_key[:24]}.json"

    def _adoptions_root(self) -> Path:
        return self._root / "adoptions"

    def _adoption_operation_path(self, operation_id: str) -> Path:
        return self._root / "adoption-operations" / f"{operation_id}.json"

    def _lock_path(self) -> Path:
        return self._root / "registry.lock"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._root.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path()
        with self._thread_lock_guard:
            lock = self._thread_locks.setdefault(lock_path, threading.Lock())
        if not lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS):
            _fail("V7_VALIDATION_REGISTRY_LOCK_TIMEOUT", "Validation registry is busy.")
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

    def _read_report_receipt(self, path: Path) -> V7ValidationReceipt:
        value = _read_json(path, "V7_VALIDATION_REPORT_CORRUPT")
        try:
            if value.get("schemaVersion") != _SCHEMA_VERSION:
                raise ValueError("schema")
            receipt = V7ValidationReceipt(
                operation_id=_string(value["operationId"]),
                operation_fingerprint=_string(value["operationFingerprint"]),
                validation_report_fingerprint=_string(value["validationReportFingerprint"]),
            )
            _require_uuid(receipt.operation_id)
            _require_sha256(receipt.operation_fingerprint)
            _require_sha256(receipt.validation_report_fingerprint)
            if value != {
                "operationFingerprint": receipt.operation_fingerprint,
                "operationId": receipt.operation_id,
                "schemaVersion": _SCHEMA_VERSION,
                "validationReportFingerprint": receipt.validation_report_fingerprint,
            }:
                raise ValueError("content")
            return receipt
        except (KeyError, TypeError, ValueError) as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_REPORT_CORRUPT", "Stored validation receipt is invalid."
            ) from error

    def _read_adoption_receipt(self, path: Path) -> V7AdoptionReceipt:
        value = _read_json(path, "V7_VALIDATION_ADOPTION_STORE_INVALID")
        try:
            if value.get("schemaVersion") != _SCHEMA_VERSION:
                raise ValueError("schema")
            receipt = V7AdoptionReceipt(
                operation_id=_string(value["operationId"]),
                operation_fingerprint=_string(value["operationFingerprint"]),
                adoption=_adoption_from_dict(value["adoption"]),
            )
            _require_uuid(receipt.operation_id)
            _require_sha256(receipt.operation_fingerprint)
            if value != {
                "adoption": receipt.adoption.as_dict(),
                "operationFingerprint": receipt.operation_fingerprint,
                "operationId": receipt.operation_id,
                "schemaVersion": _SCHEMA_VERSION,
            }:
                raise ValueError("content")
            return receipt
        except (KeyError, TypeError, ValueError, V7ValidationRegistryError) as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_ADOPTION_STORE_INVALID", "Stored adoption receipt is invalid."
            ) from error

    def _read_adoption_unlocked(self, path: Path) -> V7GeometryAdoption:
        value = _read_json(path, "V7_VALIDATION_ADOPTION_STORE_INVALID")
        try:
            if value.get("schemaVersion") != _SCHEMA_VERSION:
                raise ValueError("schema")
            adoption = _adoption_from_dict(value["adoption"])
            expected = self._adoption_path(adoption.adoption_key)
            if path != expected or value != {
                "adoption": adoption.as_dict(),
                "schemaVersion": _SCHEMA_VERSION,
            }:
                raise ValueError("identity")
            self._validate_adoption_unlocked(adoption)
            return adoption
        except (KeyError, TypeError, ValueError, V7ValidationRegistryError) as error:
            raise V7ValidationRegistryError(
                "V7_VALIDATION_ADOPTION_STORE_INVALID", "Stored geometry adoption is invalid."
            ) from error

    def _report_is_committed_unlocked(self, fingerprint: str) -> bool:
        receipts_root = self._root / "report-operations"
        if not receipts_root.exists():
            return False
        if receipts_root.is_symlink() or not receipts_root.is_dir():
            _fail("V7_VALIDATION_REPORT_CORRUPT", "Validation receipt store is unavailable.")
        return any(
            self._read_report_receipt(path).validation_report_fingerprint == fingerprint
            for path in sorted(receipts_root.glob("*.json"), key=lambda item: item.name)
        )

    def _adoption_is_committed_unlocked(self, adoption: V7GeometryAdoption) -> bool:
        receipts_root = self._root / "adoption-operations"
        if not receipts_root.exists():
            return False
        if receipts_root.is_symlink() or not receipts_root.is_dir():
            _fail("V7_VALIDATION_ADOPTION_STORE_INVALID", "Adoption receipt store is unavailable.")
        return any(
            self._read_adoption_receipt(path).adoption == adoption
            for path in sorted(receipts_root.glob("*.json"), key=lambda item: item.name)
        )

    def _validate_adoption_unlocked(self, adoption: V7GeometryAdoption) -> None:
        expected_key = _fingerprint(
            {
                "geometryFamilyId": adoption.geometry_family_id,
                "profileFingerprint": adoption.profile_fingerprint,
                "sourceGameRef": adoption.source_game_ref,
            }
        )
        if adoption.adoption_key != expected_key:
            _fail("V7_VALIDATION_ADOPTION_STORE_INVALID", "Geometry adoption key is invalid.")
        report = self._get_report_unlocked(adoption.validation_report_fingerprint)
        if (
            report.acceptance.status.value != "passed"
            or report.profile_fingerprint != adoption.profile_fingerprint
            or report.geometry_family_id != adoption.geometry_family_id
            or report.source_game_ref != adoption.source_game_ref
        ):
            _fail(
                "V7_VALIDATION_ADOPTION_STORE_INVALID",
                "Geometry adoption does not match its passed validation report.",
            )


def _metric(value: object) -> V7AcceptanceMetric:
    raw = _mapping(value)
    return V7AcceptanceMetric(
        numerator=_integer(raw["numerator"]),
        denominator=_integer(raw["denominator"]),
        minimum_percent=(
            None if raw["minimumPercent"] is None else _integer(raw["minimumPercent"])
        ),
    )


def _adoption_from_dict(value: object) -> V7GeometryAdoption:
    raw = _mapping(value)
    return V7GeometryAdoption(
        adoption_key=_string(raw["adoptionKey"]),
        source_game_ref=_string(raw["sourceGameRef"]),
        geometry_family_id=_string(raw["geometryFamilyId"]),
        profile_fingerprint=_string(raw["profileFingerprint"]),
        validation_report_fingerprint=_string(raw["validationReportFingerprint"]),
    )


def _write_immutable(
    path: Path,
    content: bytes,
    *,
    conflict_code: str,
    conflict_message: str,
) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.stem}.{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        return True
    except FileExistsError:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            _fail(conflict_code, conflict_message)
        return False
    except OSError as error:
        raise V7ValidationRegistryError(
            "V7_VALIDATION_REGISTRY_WRITE_FAILED", "The validation registry could not be saved."
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_file_lock(handle: BinaryIO) -> None:
    """Acquire the Windows process lock after the in-process lock."""

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
                _fail("V7_VALIDATION_REGISTRY_LOCK_TIMEOUT", "Validation registry is busy.")
            time.sleep(0.02)


def _release_file_lock(handle: BinaryIO) -> None:
    import msvcrt

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _read_json(path: Path, code: str) -> dict[str, object]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("path")
        content = path.read_bytes()
        value = json.loads(content)
        if _canonical_json(value) != content:
            raise ValueError("canonical")
        return _mapping(value)
    except FileNotFoundError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise V7ValidationRegistryError(code, "Validation registry data is invalid.") from error


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("objects")
    return tuple(dict(item) for item in value)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("mapping")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("string")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("integer")
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_sha256(value: str) -> None:
    if not _is_sha256(value):
        _fail("V7_VALIDATION_REPORT_INVALID", "V7 validation fingerprint is invalid.")


def _require_uuid(value: str) -> None:
    try:
        UUID(value)
    except (AttributeError, ValueError) as error:
        raise V7ValidationRegistryError(
            "V7_VALIDATION_OPERATION_INVALID", "Validation operation ID is invalid."
        ) from error


def _fail(code: str, message: str) -> None:
    raise V7ValidationRegistryError(code, message)


__all__ = [
    "V7AdoptionReceipt",
    "V7ValidationReceipt",
    "V7ValidationRegistry",
    "V7ValidationRegistryError",
    "V7ValidationReport",
]
