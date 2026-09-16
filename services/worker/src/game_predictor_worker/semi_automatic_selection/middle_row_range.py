"""Pure v4.1 contracts for exact middle-row range evidence.

This module deliberately has no image, OCR-runtime, SQL, HTTP, board-geometry,
or symbol-classification dependencies.  It turns three recognition-only values
into an exact expected range or a stable unknown observation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from statistics import mean

from .contracts import (
    SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
    SemiAutomaticSelectionRange,
    SemiAutomaticSequenceBounds,
)

MIDDLE_ROW_RANGE_VARIANT = "semi-automatic-range-only-ocr-v4-middle-row-triple-v2"
MIDDLE_ROW_PROOF_TYPE = "MIDDLE_ROW_TRIPLE_EXACT"
MIDDLE_ROW_EXPECTED_RANGE_CONTRACT_VERSION = "expected-range-table-v1"
MIDDLE_ROW_PROOF_POLICY_VERSION = "middle-row-triple-exact-proof-v2"

_ASCII_DIGITS = re.compile(r"^[0-9]+$")


class MiddleRowUnknownReason(StrEnum):
    """Stable fail-closed reasons emitted before runtime grouping."""

    UNKNOWN_ORIENTATION = "UNKNOWN_ORIENTATION"
    UNKNOWN_LATTICE = "UNKNOWN_LATTICE"
    AMBIGUOUS_LATTICE = "AMBIGUOUS_LATTICE"
    INCOMPLETE_MIDDLE_ROW = "INCOMPLETE_MIDDLE_ROW"
    CROP_OUT_OF_BOUNDS = "CROP_OUT_OF_BOUNDS"
    CROP_POSSIBLY_CLIPPED = "CROP_POSSIBLY_CLIPPED"
    LOCAL_BLUR = "LOCAL_BLUR"
    LOW_LOCAL_CONTRAST = "LOW_LOCAL_CONTRAST"
    INCOMPLETE_OCR = "INCOMPLETE_OCR"
    NON_NUMERIC_OCR = "NON_NUMERIC_OCR"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    INCONSISTENT_TRIPLE = "INCONSISTENT_TRIPLE"
    NO_EXPECTED_RANGE_MATCH = "NO_EXPECTED_RANGE_MATCH"
    AMBIGUOUS_EXPECTED_RANGE = "AMBIGUOUS_EXPECTED_RANGE"
    OUTSIDE_RUN_RANGE = "OUTSIDE_RUN_RANGE"
    SOURCE_DECODE_ERROR = "SOURCE_DECODE_ERROR"


@dataclass(frozen=True, slots=True)
class PageRangeTopology:
    """Page slot topology used only to attest expected sequence values."""

    rows: int = 3
    columns: int = 3
    middle_row_index: int = 1

    def __post_init__(self) -> None:
        if self.rows < 1 or self.columns < 1:
            raise ValueError("Expected range topology must have positive dimensions.")
        if not 0 <= self.middle_row_index < self.rows:
            raise ValueError("Expected range middle row is outside the topology.")

    @property
    def slot_count(self) -> int:
        return self.rows * self.columns

    @property
    def middle_row_slots(self) -> tuple[int, ...]:
        start = self.middle_row_index * self.columns
        return tuple(range(start, start + self.columns))

    def as_dict(self) -> dict[str, object]:
        return {
            "columns": self.columns,
            "middleRowIndex": self.middle_row_index,
            "middleRowSlots": list(self.middle_row_slots),
            "rows": self.rows,
        }


@dataclass(frozen=True, slots=True)
class ExpectedRangeEntry:
    """One exact range and the visible values required from its middle row."""

    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    active_slots: tuple[int, ...]
    middle_row_expected_values: tuple[int, ...] | None
    is_partial_page: bool
    sequence_filename: str

    def __post_init__(self) -> None:
        if self.expected_index < 0:
            raise ValueError("Expected range index cannot be negative.")
        expected_slots = tuple(range(self.sequence_range.board_count))
        if self.active_slots != expected_slots:
            raise ValueError("Expected range active slots must be contiguous row-major slots.")
        expected_name = f"seq_{self.sequence_range.start}-{self.sequence_range.end}.jpg"
        if self.sequence_filename != expected_name:
            raise ValueError("Expected range filename does not match its inclusive range.")

    @property
    def range_start(self) -> int:
        return self.sequence_range.start

    @property
    def range_end(self) -> int:
        return self.sequence_range.end

    def as_dict(self) -> dict[str, object]:
        return {
            "activeSlots": list(self.active_slots),
            "expectedIndex": self.expected_index,
            "isPartialPage": self.is_partial_page,
            "middleRowExpectedValues": (
                None
                if self.middle_row_expected_values is None
                else list(self.middle_row_expected_values)
            ),
            "rangeEnd": self.range_end,
            "rangeStart": self.range_start,
            "sequenceFilename": self.sequence_filename,
        }


@dataclass(frozen=True, slots=True)
class ExpectedRangeTable:
    """Immutable lookup derived only from declared run bounds and topology."""

    bounds: SemiAutomaticSequenceBounds
    topology: PageRangeTopology
    entries: tuple[ExpectedRangeEntry, ...]
    version: str = MIDDLE_ROW_EXPECTED_RANGE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.bounds.full_range_size != self.topology.slot_count:
            raise ValueError("Expected range size must equal the declared page topology.")
        if len(self.entries) != self.bounds.expected_range_count:
            raise ValueError("Expected range table is incomplete.")
        if tuple(entry.expected_index for entry in self.entries) != tuple(range(len(self.entries))):
            raise ValueError("Expected range table indices are not contiguous.")

    @classmethod
    def from_bounds(
        cls,
        bounds: SemiAutomaticSequenceBounds,
        *,
        topology: PageRangeTopology | None = None,
    ) -> ExpectedRangeTable:
        resolved_topology = topology or PageRangeTopology()
        if bounds.full_range_size != resolved_topology.slot_count:
            raise ValueError("Run full range size differs from the page topology.")
        middle_slots = resolved_topology.middle_row_slots
        entries: list[ExpectedRangeEntry] = []
        for expected_index, value in enumerate(bounds.expected_ranges()):
            active_slots = tuple(range(value.board_count))
            has_full_middle_row = all(slot in active_slots for slot in middle_slots)
            middle_values = (
                tuple(value.start + slot for slot in middle_slots) if has_full_middle_row else None
            )
            entries.append(
                ExpectedRangeEntry(
                    expected_index=expected_index,
                    sequence_range=value,
                    active_slots=active_slots,
                    middle_row_expected_values=middle_values,
                    is_partial_page=value.board_count < resolved_topology.slot_count,
                    sequence_filename=f"seq_{value.start}-{value.end}.jpg",
                )
            )
        return cls(bounds=bounds, topology=resolved_topology, entries=tuple(entries))

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.as_dict())

    def matching_entries(self, values: tuple[int, ...]) -> tuple[ExpectedRangeEntry, ...]:
        return tuple(entry for entry in self.entries if entry.middle_row_expected_values == values)

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.bounds.direction.value,
            "entries": [entry.as_dict() for entry in self.entries],
            "firstSequenceNumber": self.bounds.first_sequence_number,
            "fullRangeSize": self.bounds.full_range_size,
            "lastSequenceNumber": self.bounds.last_sequence_number,
            "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            "topology": self.topology.as_dict(),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowProofPolicy:
    """Versioned exact proof thresholds; these remain tuning defaults."""

    version: str = MIDDLE_ROW_PROOF_POLICY_VERSION
    minimum_label_confidence: float = 0.82
    minimum_average_confidence: float = 0.90

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_label_confidence <= self.minimum_average_confidence <= 1:
            raise ValueError("Middle-row exact proof thresholds are invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "minimumAverageConfidence": self.minimum_average_confidence,
            "minimumLabelConfidence": self.minimum_label_confidence,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MiddleRowTripleProof:
    """Recognition-only evidence from exactly three source-local crops."""

    recognized_texts: tuple[str, str, str]
    recognition_confidences: tuple[float, float, float]
    crop_completeness: tuple[bool, bool, bool] = (True, True, True)
    crop_readability: tuple[bool, bool, bool] = (True, True, True)

    def __post_init__(self) -> None:
        if any(not 0 <= confidence <= 1 for confidence in self.recognition_confidences):
            raise ValueError("Middle-row OCR confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class ExactRangeObservation:
    """Exact local proof matched to one and only one expected range."""

    matched_expected_range: ExpectedRangeEntry
    recognized_values: tuple[int, int, int]
    recognition_confidences: tuple[float, float, float]
    average_confidence: float
    proof_type: str = MIDDLE_ROW_PROOF_TYPE


@dataclass(frozen=True, slots=True)
class UnknownRangeObservation:
    """Fail-closed range result with a stable reason and bounded diagnostics."""

    reason_code: MiddleRowUnknownReason
    recognized_texts: tuple[str, ...] = ()
    recognition_confidences: tuple[float, ...] = ()
    diagnostics: tuple[str, ...] = ()


MiddleRowRangeObservation = ExactRangeObservation | UnknownRangeObservation


class MiddleRowExactResolver:
    """Resolve three OCR values without fuzzy matching or continuity guesses."""

    def __init__(
        self,
        expected_ranges: ExpectedRangeTable,
        *,
        policy: MiddleRowProofPolicy | None = None,
    ) -> None:
        self._expected_ranges = expected_ranges
        self._policy = policy or MiddleRowProofPolicy()

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(
            {
                "expectedRangeTableFingerprint": self._expected_ranges.fingerprint,
                "proofPolicy": self._policy.as_dict(),
                "variantId": MIDDLE_ROW_RANGE_VARIANT,
            }
        )

    def resolve(self, proof: MiddleRowTripleProof) -> MiddleRowRangeObservation:
        if not all(proof.crop_completeness):
            return self._unknown(proof, MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED)
        if not all(proof.crop_readability):
            return self._unknown(proof, MiddleRowUnknownReason.LOCAL_BLUR)
        if any(text == "" for text in proof.recognized_texts):
            return self._unknown(proof, MiddleRowUnknownReason.INCOMPLETE_OCR)
        if any(_ASCII_DIGITS.fullmatch(text) is None for text in proof.recognized_texts):
            return self._unknown(proof, MiddleRowUnknownReason.NON_NUMERIC_OCR)
        if (
            min(proof.recognition_confidences) < self._policy.minimum_label_confidence
            or mean(proof.recognition_confidences) < self._policy.minimum_average_confidence
        ):
            return self._unknown(proof, MiddleRowUnknownReason.LOW_OCR_CONFIDENCE)

        values = tuple(int(text) for text in proof.recognized_texts)
        typed_values = (values[0], values[1], values[2])
        if not (typed_values[1] == typed_values[0] + 1 and typed_values[2] == typed_values[1] + 1):
            return self._unknown(proof, MiddleRowUnknownReason.INCONSISTENT_TRIPLE)

        matches = self._expected_ranges.matching_entries(typed_values)
        if not matches:
            return self._unknown(proof, MiddleRowUnknownReason.NO_EXPECTED_RANGE_MATCH)
        if len(matches) != 1:
            return self._unknown(proof, MiddleRowUnknownReason.AMBIGUOUS_EXPECTED_RANGE)
        matched = matches[0]
        if not self._expected_ranges.bounds.contains_sequence_range(matched.sequence_range):
            return self._unknown(proof, MiddleRowUnknownReason.OUTSIDE_RUN_RANGE)
        expected_lengths = tuple(
            len(str(value)) for value in matched.middle_row_expected_values or ()
        )
        if expected_lengths != tuple(len(text) for text in proof.recognized_texts):
            return self._unknown(proof, MiddleRowUnknownReason.NO_EXPECTED_RANGE_MATCH)
        average = float(mean(proof.recognition_confidences))
        return ExactRangeObservation(
            matched_expected_range=matched,
            recognized_values=typed_values,
            recognition_confidences=proof.recognition_confidences,
            average_confidence=average,
        )

    @staticmethod
    def _unknown(
        proof: MiddleRowTripleProof,
        reason: MiddleRowUnknownReason,
    ) -> UnknownRangeObservation:
        return UnknownRangeObservation(
            reason_code=reason,
            recognized_texts=proof.recognized_texts,
            recognition_confidences=proof.recognition_confidences,
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "MIDDLE_ROW_EXPECTED_RANGE_CONTRACT_VERSION",
    "MIDDLE_ROW_PROOF_POLICY_VERSION",
    "MIDDLE_ROW_PROOF_TYPE",
    "MIDDLE_ROW_RANGE_VARIANT",
    "ExactRangeObservation",
    "ExpectedRangeEntry",
    "ExpectedRangeTable",
    "MiddleRowExactResolver",
    "MiddleRowProofPolicy",
    "MiddleRowRangeObservation",
    "MiddleRowTripleProof",
    "MiddleRowUnknownReason",
    "PageRangeTopology",
    "UnknownRangeObservation",
]
