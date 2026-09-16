"""Pure v5 contracts for transition-safe range-only OCR evidence.

This module deliberately contains no image processing, OCR runtime, SQL, HTTP,
board geometry, or symbol-classification dependencies.  A single row can open
only a provisional range observation.  A final automatic representative needs
two independently visible rows that agree on one expected range and no
conflicting complete row.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from statistics import mean

from .contracts import SemiAutomaticSelectionRange, SemiAutomaticSequenceBounds

ROW_FIRST_RANGE_VARIANT = "semi-automatic-range-only-ocr-v5-row-first-v1"
ROW_FIRST_PROOF_POLICY_VERSION = "row-first-range-proof-v1"
ROW_FIRST_EXPECTED_RANGE_CONTRACT_VERSION = "row-first-expected-range-table-v1"
ROW_FIRST_PROVISIONAL_PROOF_TYPE = "ROW_TRIPLE_PROVISIONAL_EXACT"
ROW_FIRST_VERIFIED_PROOF_TYPE = "TWO_ROW_RANGE_EXACT"

_ASCII_DIGITS = re.compile(r"^[0-9]+$")


class RangeRowOffset(StrEnum):
    """The row occupied by a three-number proof on a 3x3 range page."""

    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"

    @property
    def row_index(self) -> int:
        return {
            RangeRowOffset.TOP: 0,
            RangeRowOffset.MIDDLE: 1,
            RangeRowOffset.BOTTOM: 2,
        }[self]


class RangeProofUnknownReason(StrEnum):
    """Stable fail-closed reasons for provisional and final range proof."""

    CROP_POSSIBLY_CLIPPED = "CROP_POSSIBLY_CLIPPED"
    LOCAL_BLUR = "LOCAL_BLUR"
    INCOMPLETE_OCR = "INCOMPLETE_OCR"
    NON_NUMERIC_OCR = "NON_NUMERIC_OCR"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    INCONSISTENT_TRIPLE = "INCONSISTENT_TRIPLE"
    NO_EXPECTED_RANGE_MATCH = "NO_EXPECTED_RANGE_MATCH"
    AMBIGUOUS_EXPECTED_RANGE = "AMBIGUOUS_EXPECTED_RANGE"
    OUTSIDE_RUN_RANGE = "OUTSIDE_RUN_RANGE"
    PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW = "PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW"
    FINAL_PROOF_INSUFFICIENT = "FINAL_PROOF_INSUFFICIENT"
    COMPLETE_ROW_UNVERIFIED = "COMPLETE_ROW_UNVERIFIED"
    CONFLICTING_VISIBLE_ROWS = "CONFLICTING_VISIBLE_ROWS"


@dataclass(frozen=True, slots=True)
class RowRangeTopology:
    """The fixed nine-slot page topology used by range-only OCR v5."""

    rows: int = 3
    columns: int = 3

    def __post_init__(self) -> None:
        if self.rows != 3 or self.columns != 3:
            raise ValueError("Row-first range proof requires an explicit 3x3 topology.")

    @property
    def slot_count(self) -> int:
        return self.rows * self.columns

    def slots_for(self, row: RangeRowOffset) -> tuple[int, int, int]:
        start = row.row_index * self.columns
        return (start, start + 1, start + 2)

    def as_dict(self) -> dict[str, object]:
        return {"columns": self.columns, "rows": self.rows}


@dataclass(frozen=True, slots=True)
class RowExpectedRangeEntry:
    """One declared inclusive range and its visible full-row values."""

    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    row_values: tuple[tuple[RangeRowOffset, tuple[int, int, int]], ...]
    is_partial_page: bool
    sequence_filename: str

    def __post_init__(self) -> None:
        if self.expected_index < 0:
            raise ValueError("Expected range index cannot be negative.")
        expected_name = f"seq_{self.sequence_range.start}-{self.sequence_range.end}.jpg"
        if self.sequence_filename != expected_name:
            raise ValueError("Expected range filename does not match its inclusive range.")
        if self.is_partial_page and self.row_values:
            raise ValueError("A partial page cannot expose a full three-number row proof.")
        if not self.is_partial_page and len(self.row_values) != 3:
            raise ValueError("A full page must define all three row proofs.")
        if len({row for row, _values in self.row_values}) != len(self.row_values):
            raise ValueError("Expected range rows must be unique.")

    def values_for(self, row: RangeRowOffset) -> tuple[int, int, int] | None:
        return next((values for offset, values in self.row_values if offset is row), None)

    def as_dict(self) -> dict[str, object]:
        return {
            "expectedIndex": self.expected_index,
            "isPartialPage": self.is_partial_page,
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "rows": [
                {"offset": row.value, "values": list(values)}
                for row, values in self.row_values
            ],
            "sequenceFilename": self.sequence_filename,
        }


@dataclass(frozen=True, slots=True)
class RowExpectedRangeTable:
    """Immutable expected ranges derived only from declared run bounds."""

    bounds: SemiAutomaticSequenceBounds
    topology: RowRangeTopology
    entries: tuple[RowExpectedRangeEntry, ...]
    version: str = ROW_FIRST_EXPECTED_RANGE_CONTRACT_VERSION

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
        topology: RowRangeTopology | None = None,
    ) -> RowExpectedRangeTable:
        resolved_topology = topology or RowRangeTopology()
        if bounds.full_range_size != resolved_topology.slot_count:
            raise ValueError("Run full range size differs from the page topology.")
        entries: list[RowExpectedRangeEntry] = []
        for expected_index, sequence_range in enumerate(bounds.expected_ranges()):
            is_partial = sequence_range.board_count < resolved_topology.slot_count
            rows: tuple[tuple[RangeRowOffset, tuple[int, int, int]], ...] = ()
            if not is_partial:
                row_values: list[tuple[RangeRowOffset, tuple[int, int, int]]] = []
                for row in RangeRowOffset:
                    first, second, third = resolved_topology.slots_for(row)
                    row_values.append(
                        (
                            row,
                            (
                                sequence_range.start + first,
                                sequence_range.start + second,
                                sequence_range.start + third,
                            ),
                        )
                    )
                rows = tuple(row_values)
            entries.append(
                RowExpectedRangeEntry(
                    expected_index=expected_index,
                    sequence_range=sequence_range,
                    row_values=rows,
                    is_partial_page=is_partial,
                    sequence_filename=f"seq_{sequence_range.start}-{sequence_range.end}.jpg",
                )
            )
        return cls(bounds=bounds, topology=resolved_topology, entries=tuple(entries))

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.as_dict())

    def matching_entries(
        self,
        row: RangeRowOffset,
        values: tuple[int, int, int],
    ) -> tuple[RowExpectedRangeEntry, ...]:
        return tuple(entry for entry in self.entries if entry.values_for(row) == values)

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.bounds.direction.value,
            "entries": [entry.as_dict() for entry in self.entries],
            "firstSequenceNumber": self.bounds.first_sequence_number,
            "fullRangeSize": self.bounds.full_range_size,
            "lastSequenceNumber": self.bounds.last_sequence_number,
            "topology": self.topology.as_dict(),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RowRangeProofPolicy:
    """Versioned confidence thresholds for each source-local row proof."""

    version: str = ROW_FIRST_PROOF_POLICY_VERSION
    minimum_label_confidence: float = 0.82
    minimum_average_confidence: float = 0.90

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_label_confidence <= self.minimum_average_confidence <= 1:
            raise ValueError("Row-first exact proof thresholds are invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "minimumAverageConfidence": self.minimum_average_confidence,
            "minimumLabelConfidence": self.minimum_label_confidence,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RowTripleProof:
    """Recognition-only evidence from one detected source-local row."""

    row: RangeRowOffset
    recognized_texts: tuple[str, str, str]
    recognition_confidences: tuple[float, float, float]
    crop_completeness: tuple[bool, bool, bool] = (True, True, True)
    crop_readability: tuple[bool, bool, bool] = (True, True, True)

    def __post_init__(self) -> None:
        if any(not 0 <= confidence <= 1 for confidence in self.recognition_confidences):
            raise ValueError("Row-first OCR confidence must be between zero and one.")

    @property
    def is_complete_visible_row(self) -> bool:
        return all(self.crop_completeness)


@dataclass(frozen=True, slots=True)
class ProvisionalExactRangeObservation:
    """One exact row proof; insufficient by itself for automatic selection."""

    matched_expected_range: RowExpectedRangeEntry
    row: RangeRowOffset
    recognized_values: tuple[int, int, int]
    recognition_confidences: tuple[float, float, float]
    average_confidence: float
    proof_type: str = ROW_FIRST_PROVISIONAL_PROOF_TYPE


@dataclass(frozen=True, slots=True)
class UnknownRowRangeObservation:
    """Fail-closed result for one row candidate."""

    row: RangeRowOffset
    reason_code: RangeProofUnknownReason
    is_complete_visible_row: bool
    recognized_texts: tuple[str, ...] = ()
    recognition_confidences: tuple[float, ...] = ()


RowRangeObservation = ProvisionalExactRangeObservation | UnknownRowRangeObservation


@dataclass(frozen=True, slots=True)
class VerifiedRangeCandidate:
    """A candidate whose own visible rows establish one exact range."""

    matched_expected_range: RowExpectedRangeEntry
    verified_rows: tuple[RangeRowOffset, ...]
    average_confidence: float
    proof_type: str = ROW_FIRST_VERIFIED_PROOF_TYPE

    def __post_init__(self) -> None:
        if len(self.verified_rows) < 2:
            raise ValueError("A verified candidate requires two distinct row proofs.")
        if len(set(self.verified_rows)) != len(self.verified_rows):
            raise ValueError("Verified candidate rows must be distinct.")


class RowFirstExactResolver:
    """Resolve one row without fuzzy matching or continuity inference."""

    def __init__(
        self,
        expected_ranges: RowExpectedRangeTable,
        *,
        policy: RowRangeProofPolicy | None = None,
    ) -> None:
        self._expected_ranges = expected_ranges
        self._policy = policy or RowRangeProofPolicy()

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(
            {
                "expectedRangeTableFingerprint": self._expected_ranges.fingerprint,
                "proofPolicy": self._policy.as_dict(),
                "variantId": ROW_FIRST_RANGE_VARIANT,
            }
        )

    def resolve(self, proof: RowTripleProof) -> RowRangeObservation:
        if not proof.is_complete_visible_row:
            return self._unknown(proof, RangeProofUnknownReason.CROP_POSSIBLY_CLIPPED)
        if not all(proof.crop_readability):
            return self._unknown(proof, RangeProofUnknownReason.LOCAL_BLUR)
        if any(text == "" for text in proof.recognized_texts):
            return self._unknown(proof, RangeProofUnknownReason.INCOMPLETE_OCR)
        if any(_ASCII_DIGITS.fullmatch(text) is None for text in proof.recognized_texts):
            return self._unknown(proof, RangeProofUnknownReason.NON_NUMERIC_OCR)
        if (
            min(proof.recognition_confidences) < self._policy.minimum_label_confidence
            or mean(proof.recognition_confidences) < self._policy.minimum_average_confidence
        ):
            return self._unknown(proof, RangeProofUnknownReason.LOW_OCR_CONFIDENCE)

        values = tuple(int(text) for text in proof.recognized_texts)
        typed_values = (values[0], values[1], values[2])
        if not (typed_values[1] == typed_values[0] + 1 and typed_values[2] == typed_values[1] + 1):
            return self._unknown(proof, RangeProofUnknownReason.INCONSISTENT_TRIPLE)

        matches = self._expected_ranges.matching_entries(proof.row, typed_values)
        if not matches:
            if any(
                entry.is_partial_page
                and entry.sequence_range.start <= typed_values[0] <= entry.sequence_range.end
                for entry in self._expected_ranges.entries
            ):
                return self._unknown(
                    proof,
                    RangeProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW,
                )
            return self._unknown(proof, RangeProofUnknownReason.NO_EXPECTED_RANGE_MATCH)
        if len(matches) != 1:
            return self._unknown(proof, RangeProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE)
        matched = matches[0]
        if not self._expected_ranges.bounds.contains_sequence_range(matched.sequence_range):
            return self._unknown(proof, RangeProofUnknownReason.OUTSIDE_RUN_RANGE)
        expected_values = matched.values_for(proof.row)
        if expected_values is None or tuple(len(str(value)) for value in expected_values) != tuple(
            len(text) for text in proof.recognized_texts
        ):
            return self._unknown(proof, RangeProofUnknownReason.NO_EXPECTED_RANGE_MATCH)
        return ProvisionalExactRangeObservation(
            matched_expected_range=matched,
            row=proof.row,
            recognized_values=typed_values,
            recognition_confidences=proof.recognition_confidences,
            average_confidence=float(mean(proof.recognition_confidences)),
        )

    @staticmethod
    def _unknown(
        proof: RowTripleProof,
        reason: RangeProofUnknownReason,
    ) -> UnknownRowRangeObservation:
        return UnknownRowRangeObservation(
            row=proof.row,
            reason_code=reason,
            is_complete_visible_row=proof.is_complete_visible_row,
            recognized_texts=proof.recognized_texts,
            recognition_confidences=proof.recognition_confidences,
        )


def verify_range_candidate(
    observations: tuple[RowRangeObservation, ...],
) -> VerifiedRangeCandidate | UnknownRowRangeObservation:
    """Apply the final two-row proof rule to one candidate source image.

    Missing or clipped rows do not veto a candidate.  A row that was detected
    as complete but cannot be proven does veto it, because it could be a range
    transition frame rather than a safely hidden row.
    """

    if not observations:
        raise ValueError("Candidate verification requires at least one row observation.")
    if len({observation.row for observation in observations}) != len(observations):
        raise ValueError("Candidate verification cannot receive duplicate row observations.")

    exact = tuple(
        observation
        for observation in observations
        if isinstance(observation, ProvisionalExactRangeObservation)
    )
    complete_unknown = next(
        (
            observation
            for observation in observations
            if isinstance(observation, UnknownRowRangeObservation)
            and observation.is_complete_visible_row
        ),
        None,
    )
    if complete_unknown is not None:
        return UnknownRowRangeObservation(
            row=complete_unknown.row,
            reason_code=RangeProofUnknownReason.COMPLETE_ROW_UNVERIFIED,
            is_complete_visible_row=True,
            recognized_texts=complete_unknown.recognized_texts,
            recognition_confidences=complete_unknown.recognition_confidences,
        )
    if len(exact) < 2:
        return UnknownRowRangeObservation(
            row=observations[0].row,
            reason_code=RangeProofUnknownReason.FINAL_PROOF_INSUFFICIENT,
            is_complete_visible_row=False,
        )
    target = exact[0].matched_expected_range
    if any(observation.matched_expected_range != target for observation in exact[1:]):
        return UnknownRowRangeObservation(
            row=observations[0].row,
            reason_code=RangeProofUnknownReason.CONFLICTING_VISIBLE_ROWS,
            is_complete_visible_row=True,
        )
    return VerifiedRangeCandidate(
        matched_expected_range=target,
        verified_rows=tuple(observation.row for observation in exact),
        average_confidence=float(mean(observation.average_confidence for observation in exact)),
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ROW_FIRST_EXPECTED_RANGE_CONTRACT_VERSION",
    "ROW_FIRST_PROOF_POLICY_VERSION",
    "ROW_FIRST_PROVISIONAL_PROOF_TYPE",
    "ROW_FIRST_RANGE_VARIANT",
    "ROW_FIRST_VERIFIED_PROOF_TYPE",
    "ProvisionalExactRangeObservation",
    "RangeProofUnknownReason",
    "RangeRowOffset",
    "RowExpectedRangeEntry",
    "RowExpectedRangeTable",
    "RowFirstExactResolver",
    "RowRangeObservation",
    "RowRangeProofPolicy",
    "RowRangeTopology",
    "RowTripleProof",
    "UnknownRowRangeObservation",
    "VerifiedRangeCandidate",
    "verify_range_candidate",
]
