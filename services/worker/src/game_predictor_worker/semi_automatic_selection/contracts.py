"""Framework-free contracts for independent range-only image selection.

The semi-automatic workflow identifies only the attested ``seq_<start>-<end>``
range visible on a source image. It deliberately has no board-geometry,
board-quality, cropper, or symbol-classification inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION = 1
SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION = "seq-inclusive-v1"
SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE = 9
SEMI_AUTOMATIC_SELECTION_MIN_SEQUENCE_NUMBER = 1

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


class SemiAutomaticSelectionError(ValueError):
    """Stable validation error for the semi-automatic selection contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SemiAutomaticSelectionDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class SemiAutomaticSelectionRunStatus(StrEnum):
    CONFIGURATION = "configuration"
    UPLOADING = "uploading"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ANALYSIS_COMPLETE = "analysis_complete"
    SYNCING_OUTPUT = "syncing_output"
    REVIEW_MODE = "review_mode"
    EDIT_SOURCE_MODE = "edit_source_mode"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SemiAutomaticSelectionRangeStatus(StrEnum):
    MISSING = "missing"
    AUTO_SELECTED = "auto_selected"
    OUTPUT_SYNCED = "output_synced"
    CONFLICT = "conflict"
    MANUALLY_ADDED = "manually_added"
    MANUALLY_REPLACED = "manually_replaced"
    PREEXISTING_PROTECTED = "preexisting_protected"


class RangeEvidenceStatus(StrEnum):
    EXACT_RANGE = "exact_range"
    RANGE_UNREADABLE = "range_unreadable"
    RANGE_AMBIGUOUS = "range_ambiguous"
    INVALID_RANGE = "invalid_range"
    OUTSIDE_REQUESTED_RANGE = "outside_requested_range"
    NOT_EXPECTED_RANGE = "not_expected_range"
    SOURCE_ERROR = "source_error"


@dataclass(frozen=True, slots=True, order=True)
class SemiAutomaticSelectionRange:
    """One positive, inclusive sequence range in canonical ascending spelling."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < SEMI_AUTOMATIC_SELECTION_MIN_SEQUENCE_NUMBER:
            _fail("SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID", "Range start must be positive.")
        if self.end < self.start:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "Range end must be greater than or equal to range start.",
            )

    @property
    def board_count(self) -> int:
        return self.end - self.start + 1

    def as_dict(self) -> dict[str, int]:
        return {"end": self.end, "start": self.start}


@dataclass(frozen=True, slots=True)
class SemiAutomaticSequenceBounds:
    """Expected inclusive ranges in the source traversal direction.

    Ranges themselves remain canonically ascending even when source images are
    traversed in descending sequence order.
    """

    first_sequence_number: int
    last_sequence_number: int
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING
    full_range_size: int = SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE

    def __post_init__(self) -> None:
        if self.full_range_size < 1:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "Full range size must be positive.",
            )
        if self.first_sequence_number < SEMI_AUTOMATIC_SELECTION_MIN_SEQUENCE_NUMBER:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "First sequence number must be positive.",
            )
        if self.last_sequence_number < SEMI_AUTOMATIC_SELECTION_MIN_SEQUENCE_NUMBER:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "Last sequence number must be positive.",
            )
        if (
            self.direction is SemiAutomaticSelectionDirection.ASCENDING
            and self.last_sequence_number < self.first_sequence_number
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "Ascending bounds cannot end before they start.",
            )
        if (
            self.direction is SemiAutomaticSelectionDirection.DESCENDING
            and self.last_sequence_number > self.first_sequence_number
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
                "Descending bounds cannot end after they start.",
            )

    @property
    def sequence_count(self) -> int:
        return abs(self.last_sequence_number - self.first_sequence_number) + 1

    @property
    def expected_range_count(self) -> int:
        return (self.sequence_count + self.full_range_size - 1) // self.full_range_size

    def range_for_expected_index(self, expected_index: int) -> SemiAutomaticSelectionRange:
        if not 0 <= expected_index < self.expected_range_count:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_EXPECTED_INDEX_INVALID",
                "Expected range index is outside the configured bounds.",
            )
        offset = expected_index * self.full_range_size
        if self.direction is SemiAutomaticSelectionDirection.ASCENDING:
            start = self.first_sequence_number + offset
            end = min(self.last_sequence_number, start + self.full_range_size - 1)
        else:
            end = self.first_sequence_number - offset
            start = max(self.last_sequence_number, end - self.full_range_size + 1)
        return SemiAutomaticSelectionRange(start=start, end=end)

    def expected_ranges(self) -> tuple[SemiAutomaticSelectionRange, ...]:
        return tuple(
            self.range_for_expected_index(index)
            for index in range(self.expected_range_count)
        )

    def expected_index_for_range(self, value: SemiAutomaticSelectionRange) -> int | None:
        anchor = (
            value.start
            if self.direction is SemiAutomaticSelectionDirection.ASCENDING
            else value.end
        )
        offset = (
            anchor - self.first_sequence_number
            if self.direction is SemiAutomaticSelectionDirection.ASCENDING
            else self.first_sequence_number - anchor
        )
        if offset < 0 or offset % self.full_range_size != 0:
            return None
        expected_index = offset // self.full_range_size
        if expected_index >= self.expected_range_count:
            return None
        return (
            expected_index
            if self.range_for_expected_index(expected_index) == value
            else None
        )

    def contains_sequence_range(self, value: SemiAutomaticSelectionRange) -> bool:
        lower = min(self.first_sequence_number, self.last_sequence_number)
        upper = max(self.first_sequence_number, self.last_sequence_number)
        return lower <= value.start and value.end <= upper


@dataclass(frozen=True, slots=True)
class SemiAutomaticSelectionSource:
    """Stable source identity; ordinal alone is deliberately insufficient."""

    source_index: int
    relative_path: str
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        if self.source_index < 0:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_INVALID",
                "Source index must be non-negative.",
            )
        safe_relative_path(self.relative_path)
        if self.size_bytes < 1:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_INVALID",
                "Source size must be positive.",
            )
        validate_sha256(self.checksum_sha256, field="checksumSha256")

    def as_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "relativePath": self.relative_path,
            "sizeBytes": self.size_bytes,
            "sourceIndex": self.source_index,
        }


@dataclass(frozen=True, slots=True)
class RangeEvidenceObservation:
    """OCR-adapter output before expected-range classification.

    ``has_strong_local_proof`` is supplied by the versioned OCR proof policy.
    This contract deliberately does not define another confidence threshold and
    has no image-quality fields.
    """

    source: SemiAutomaticSelectionSource
    observed_range: SemiAutomaticSelectionRange | None
    confidence: float | None
    has_strong_local_proof: bool
    is_ambiguous: bool = False
    source_decodable: bool = True
    diagnostic_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_CONFIDENCE_INVALID",
                "Range confidence must be between zero and one.",
            )
        if self.has_strong_local_proof and self.observed_range is None:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INVALID",
                "A strong local proof requires an observed range.",
            )
        if self.is_ambiguous and self.has_strong_local_proof:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INVALID",
                "An ambiguous observation cannot have a strong local proof.",
            )
        _validate_reason_codes(self.diagnostic_reason_codes)


@dataclass(frozen=True, slots=True)
class RangeEvidenceResult:
    """Range-only classification consumed later by the grouping engine."""

    source: SemiAutomaticSelectionSource
    status: RangeEvidenceStatus
    observed_range: SemiAutomaticSelectionRange | None
    expected_index: int | None
    confidence: float | None
    reason_codes: tuple[str, ...]
    local_readability_score: float | None = None
    minimum_ocr_confidence: float | None = None
    observation_key: str | None = None
    runtime_diagnostics: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.local_readability_score is not None and self.local_readability_score < 0:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_CONFIDENCE_INVALID",
                "Local readability score cannot be negative.",
            )
        if self.minimum_ocr_confidence is not None and not 0 <= self.minimum_ocr_confidence <= 1:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_CONFIDENCE_INVALID",
                "Minimum OCR confidence must be between zero and one.",
            )
        if self.observation_key is not None:
            validate_sha256(self.observation_key, field="observationKey")

    @property
    def is_exact_range(self) -> bool:
        return self.status is RangeEvidenceStatus.EXACT_RANGE


class RangeEvidenceGate:
    """Classify exact local range evidence without inspecting board quality."""

    def __init__(self, bounds: SemiAutomaticSequenceBounds) -> None:
        self._bounds = bounds

    def evaluate(self, observation: RangeEvidenceObservation) -> RangeEvidenceResult:
        diagnostics = observation.diagnostic_reason_codes
        if not observation.source_decodable:
            return _result(
                observation,
                RangeEvidenceStatus.SOURCE_ERROR,
                None,
                _with_reason(diagnostics, "SOURCE_DECODE_FAILED"),
            )
        if observation.observed_range is None:
            if observation.is_ambiguous:
                return _result(
                    observation,
                    RangeEvidenceStatus.RANGE_AMBIGUOUS,
                    None,
                    _with_reason(diagnostics, "RANGE_AMBIGUOUS"),
                )
            return _result(
                observation,
                RangeEvidenceStatus.RANGE_UNREADABLE,
                None,
                _with_reason(diagnostics, "RANGE_UNREADABLE"),
            )
        if observation.is_ambiguous or not observation.has_strong_local_proof:
            return _result(
                observation,
                RangeEvidenceStatus.RANGE_AMBIGUOUS,
                None,
                _with_reason(diagnostics, "RANGE_PROOF_INSUFFICIENT"),
            )
        if not self._bounds.contains_sequence_range(observation.observed_range):
            return _result(
                observation,
                RangeEvidenceStatus.OUTSIDE_REQUESTED_RANGE,
                None,
                _with_reason(diagnostics, "OUTSIDE_REQUESTED_RANGE"),
            )
        expected_index = self._bounds.expected_index_for_range(observation.observed_range)
        if expected_index is None:
            return _result(
                observation,
                RangeEvidenceStatus.NOT_EXPECTED_RANGE,
                None,
                _with_reason(diagnostics, "NOT_EXPECTED_RANGE"),
            )
        return _result(
            observation,
            RangeEvidenceStatus.EXACT_RANGE,
            expected_index,
            _with_reason(diagnostics, "EXACT_LOCAL_RANGE_PROOF"),
        )


def safe_relative_path(value: str) -> str:
    """Validate an unchanged portable relative path."""

    if not value or "\\" in value:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE",
            "Source relative path must be a non-empty portable relative path.",
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE",
            "Source relative path must not escape its source root.",
        )
    normalized = path.as_posix()
    if normalized != value:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE",
            "Source relative path must already be normalized.",
        )
    return normalized


def validate_sha256(value: str, *, field: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        _fail(
            "SEMI_AUTOMATIC_SELECTION_CHECKSUM_INVALID",
            f"{field} must be a lowercase SHA-256 hexadecimal value.",
        )
    return value


def fingerprint_sources(sources: Iterable[SemiAutomaticSelectionSource]) -> str:
    """Return a stable checksum for one naturally ordered, immutable source list."""

    values = tuple(sources)
    expected_indices = tuple(range(len(values)))
    if tuple(source.source_index for source in values) != expected_indices:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_ORDER_INVALID",
            "Sources must have contiguous indexes in natural source order.",
        )
    paths = tuple(source.relative_path for source in values)
    if len(set(paths)) != len(paths):
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_ORDER_INVALID",
            "Source relative paths must be unique.",
        )
    return _canonical_sha256(
        {
            "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
            "orderingPolicy": "natural_relative_path_v1",
            "sources": [source.as_dict() for source in values],
        }
    )


def expected_ranges_fingerprint(bounds: SemiAutomaticSequenceBounds) -> str:
    """Return a stable checksum for the run's ordered expected-range list."""

    return _canonical_sha256(
        {
            "bounds": {
                "direction": bounds.direction.value,
                "firstSequenceNumber": bounds.first_sequence_number,
                "fullRangeSize": bounds.full_range_size,
                "lastSequenceNumber": bounds.last_sequence_number,
            },
            "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
            "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            "ranges": [value.as_dict() for value in bounds.expected_ranges()],
        }
    )


def is_valid_run_status_transition(
    *,
    current: SemiAutomaticSelectionRunStatus,
    target: SemiAutomaticSelectionRunStatus,
) -> bool:
    """Return whether the contract permits a lifecycle transition."""

    if current is target:
        return True
    terminal_failure_statuses = {
        SemiAutomaticSelectionRunStatus.CANCELLED,
        SemiAutomaticSelectionRunStatus.FAILED,
    }
    if current in terminal_failure_statuses:
        return False
    if target in terminal_failure_statuses:
        return True
    allowed_targets = {
        SemiAutomaticSelectionRunStatus.CONFIGURATION: {
            SemiAutomaticSelectionRunStatus.UPLOADING,
        },
        SemiAutomaticSelectionRunStatus.UPLOADING: {
            SemiAutomaticSelectionRunStatus.READY,
        },
        SemiAutomaticSelectionRunStatus.READY: {
            SemiAutomaticSelectionRunStatus.RUNNING,
        },
        SemiAutomaticSelectionRunStatus.RUNNING: {
            SemiAutomaticSelectionRunStatus.PAUSED,
            SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
        },
        SemiAutomaticSelectionRunStatus.PAUSED: {
            SemiAutomaticSelectionRunStatus.RUNNING,
        },
        SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE: {
            SemiAutomaticSelectionRunStatus.SYNCING_OUTPUT,
        },
        SemiAutomaticSelectionRunStatus.SYNCING_OUTPUT: {
            SemiAutomaticSelectionRunStatus.REVIEW_MODE,
        },
        SemiAutomaticSelectionRunStatus.REVIEW_MODE: {
            SemiAutomaticSelectionRunStatus.EDIT_SOURCE_MODE,
            SemiAutomaticSelectionRunStatus.COMPLETED,
        },
        SemiAutomaticSelectionRunStatus.EDIT_SOURCE_MODE: {
            SemiAutomaticSelectionRunStatus.REVIEW_MODE,
        },
        SemiAutomaticSelectionRunStatus.COMPLETED: set(),
        SemiAutomaticSelectionRunStatus.CANCELLED: set(),
        SemiAutomaticSelectionRunStatus.FAILED: set(),
    }
    return target in allowed_targets[current]


def _result(
    observation: RangeEvidenceObservation,
    status: RangeEvidenceStatus,
    expected_index: int | None,
    reason_codes: tuple[str, ...],
) -> RangeEvidenceResult:
    return RangeEvidenceResult(
        source=observation.source,
        status=status,
        observed_range=observation.observed_range,
        expected_index=expected_index,
        confidence=observation.confidence,
        reason_codes=reason_codes,
    )


def _with_reason(reason_codes: tuple[str, ...], required_reason: str) -> tuple[str, ...]:
    return reason_codes if required_reason in reason_codes else (*reason_codes, required_reason)


def _validate_reason_codes(values: tuple[str, ...]) -> None:
    has_invalid_value = any(
        not _REASON_CODE_PATTERN.fullmatch(value) for value in values
    )
    if len(set(values)) != len(values) or has_invalid_value:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_REASON_CODES_INVALID",
            "Reason codes must be unique upper-case identifiers.",
        )


def _canonical_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _fail(code: str, message: str) -> None:
    raise SemiAutomaticSelectionError(code, message)
