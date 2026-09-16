"""Pure v6 exact-range proof for five independently located numeric labels.

The module deliberately has no image, OCR-runtime, job, storage or HTTP
dependencies. It can only attest an already recognized value against its fixed
source-local 3x3 page position; it never repairs text or infers a value from a
filename, source order, expected filename, or neighbouring image.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from statistics import mean
from typing import Final

from .contracts import SemiAutomaticSelectionRange, SemiAutomaticSequenceBounds

FIVE_ANCHOR_RANGE_VARIANT: Final = "semi-automatic-range-only-ocr-v6-five-anchor-v1"
FIVE_ANCHOR_EXPECTED_RANGE_CONTRACT_VERSION: Final = "five-anchor-expected-range-table-v1"
FIVE_ANCHOR_PROOF_POLICY_VERSION: Final = "five-anchor-range-proof-v1"
FIVE_ANCHOR_PROOF_TYPE: Final = "FIVE_ANCHOR_SPANNED_EXACT"

_ASCII_DIGITS = re.compile(r"^[0-9]+$")


class FiveAnchorProofPosition(StrEnum):
    """The five source-local numeric locations on a full 3x3 page."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    CENTER = "center"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"

    @property
    def slot_index(self) -> int:
        return {
            FiveAnchorProofPosition.TOP_LEFT: 0,
            FiveAnchorProofPosition.TOP_RIGHT: 2,
            FiveAnchorProofPosition.CENTER: 4,
            FiveAnchorProofPosition.BOTTOM_LEFT: 6,
            FiveAnchorProofPosition.BOTTOM_RIGHT: 8,
        }[self]

    @property
    def vertical_band(self) -> str:
        return {
            FiveAnchorProofPosition.TOP_LEFT: "top",
            FiveAnchorProofPosition.TOP_RIGHT: "top",
            FiveAnchorProofPosition.CENTER: "middle",
            FiveAnchorProofPosition.BOTTOM_LEFT: "bottom",
            FiveAnchorProofPosition.BOTTOM_RIGHT: "bottom",
        }[self]


_ANCHOR_ORDER: Final = (
    FiveAnchorProofPosition.TOP_LEFT,
    FiveAnchorProofPosition.TOP_RIGHT,
    FiveAnchorProofPosition.CENTER,
    FiveAnchorProofPosition.BOTTOM_LEFT,
    FiveAnchorProofPosition.BOTTOM_RIGHT,
)


class FiveAnchorProofUnknownReason(StrEnum):
    """Stable fail-closed outcomes produced by v6 before any grouping."""

    CROP_POSSIBLY_CLIPPED = "CROP_POSSIBLY_CLIPPED"
    LOCAL_BLUR = "LOCAL_BLUR"
    INCOMPLETE_OCR = "INCOMPLETE_OCR"
    NON_NUMERIC_OCR = "NON_NUMERIC_OCR"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    INSUFFICIENT_SPANNED_EVIDENCE = "INSUFFICIENT_SPANNED_EVIDENCE"
    CONFLICTING_ANCHOR_VALUES = "CONFLICTING_ANCHOR_VALUES"
    NO_EXPECTED_RANGE_MATCH = "NO_EXPECTED_RANGE_MATCH"
    AMBIGUOUS_EXPECTED_RANGE = "AMBIGUOUS_EXPECTED_RANGE"
    OUTSIDE_RUN_RANGE = "OUTSIDE_RUN_RANGE"
    PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW = "PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW"


@dataclass(frozen=True, slots=True)
class FiveAnchorRangeTopology:
    """The explicit 3x3 page topology asserted by the v6 anchor map."""

    rows: int = 3
    columns: int = 3

    def __post_init__(self) -> None:
        if self.rows != 3 or self.columns != 3:
            raise ValueError("Five-anchor range proof requires an explicit 3x3 topology.")

    @property
    def slot_count(self) -> int:
        return self.rows * self.columns

    def as_dict(self) -> dict[str, object]:
        return {
            "anchorSlots": [
                {"position": position.value, "slotIndex": position.slot_index}
                for position in _ANCHOR_ORDER
            ],
            "columns": self.columns,
            "rows": self.rows,
        }


@dataclass(frozen=True, slots=True)
class FiveAnchorExpectedRangeEntry:
    """One declared range and the values it assigns to its five anchors."""

    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    anchor_values: tuple[
        tuple[FiveAnchorProofPosition, int | None],
        tuple[FiveAnchorProofPosition, int | None],
        tuple[FiveAnchorProofPosition, int | None],
        tuple[FiveAnchorProofPosition, int | None],
        tuple[FiveAnchorProofPosition, int | None],
    ]
    is_partial_page: bool
    sequence_filename: str

    def __post_init__(self) -> None:
        if self.expected_index < 0:
            raise ValueError("Expected range index cannot be negative.")
        if tuple(position for position, _value in self.anchor_values) != _ANCHOR_ORDER:
            raise ValueError("Five-anchor expected values must use the stable anchor order.")
        if self.sequence_filename != (
            f"seq_{self.sequence_range.start}-{self.sequence_range.end}.jpg"
        ):
            raise ValueError("Expected range filename does not match its inclusive range.")
        if not self.is_partial_page and any(value is None for _, value in self.anchor_values):
            raise ValueError("A full range must provide all five anchor values.")

    def value_for(self, position: FiveAnchorProofPosition) -> int | None:
        return next(value for candidate, value in self.anchor_values if candidate is position)

    def as_dict(self) -> dict[str, object]:
        return {
            "anchors": [
                {"position": position.value, "value": value}
                for position, value in self.anchor_values
            ],
            "expectedIndex": self.expected_index,
            "isPartialPage": self.is_partial_page,
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "sequenceFilename": self.sequence_filename,
        }


@dataclass(frozen=True, slots=True)
class FiveAnchorExpectedRangeTable:
    """Checksum-stable expected values derived only from declared run bounds."""

    bounds: SemiAutomaticSequenceBounds
    topology: FiveAnchorRangeTopology
    entries: tuple[FiveAnchorExpectedRangeEntry, ...]
    version: str = FIVE_ANCHOR_EXPECTED_RANGE_CONTRACT_VERSION

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
        topology: FiveAnchorRangeTopology | None = None,
    ) -> FiveAnchorExpectedRangeTable:
        resolved_topology = topology or FiveAnchorRangeTopology()
        if bounds.full_range_size != resolved_topology.slot_count:
            raise ValueError("Run full range size differs from the page topology.")
        entries: list[FiveAnchorExpectedRangeEntry] = []
        for expected_index, sequence_range in enumerate(bounds.expected_ranges()):
            anchor_values = tuple(
                (
                    position,
                    (
                        sequence_range.start + position.slot_index
                        if position.slot_index < sequence_range.board_count
                        else None
                    ),
                )
                for position in _ANCHOR_ORDER
            )
            entries.append(
                FiveAnchorExpectedRangeEntry(
                    expected_index=expected_index,
                    sequence_range=sequence_range,
                    anchor_values=(
                        anchor_values[0],
                        anchor_values[1],
                        anchor_values[2],
                        anchor_values[3],
                        anchor_values[4],
                    ),
                    is_partial_page=sequence_range.board_count < resolved_topology.slot_count,
                    sequence_filename=(f"seq_{sequence_range.start}-{sequence_range.end}.jpg"),
                )
            )
        return cls(bounds=bounds, topology=resolved_topology, entries=tuple(entries))

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(self.as_dict())

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
class FiveAnchorProofPolicy:
    """Versioned confidence and coverage requirements for exact v6 proof."""

    version: str = FIVE_ANCHOR_PROOF_POLICY_VERSION
    minimum_label_confidence: float = 0.88
    minimum_average_confidence: float = 0.92
    minimum_confirming_anchors: int = 3
    require_center_anchor: bool = True
    require_vertical_span: bool = True

    def __post_init__(self) -> None:
        if (
            not 0 <= self.minimum_label_confidence <= self.minimum_average_confidence <= 1
            or not 3 <= self.minimum_confirming_anchors <= len(_ANCHOR_ORDER)
        ):
            raise ValueError("Five-anchor range proof policy is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "minimumAverageConfidence": self.minimum_average_confidence,
            "minimumConfirmingAnchors": self.minimum_confirming_anchors,
            "minimumLabelConfidence": self.minimum_label_confidence,
            "requireCenterAnchor": self.require_center_anchor,
            "requireVerticalSpan": self.require_vertical_span,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class FiveAnchorRecognition:
    """Recognition-only evidence for one source-direct candidate crop."""

    position: FiveAnchorProofPosition
    recognized_text: str
    recognition_confidence: float
    crop_complete: bool = True
    crop_readable: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.recognition_confidence <= 1:
            raise ValueError("Five-anchor OCR confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class FiveAnchorRecognitionProof:
    """Exactly five stable-order OCR values before range attestation."""

    observations: tuple[
        FiveAnchorRecognition,
        FiveAnchorRecognition,
        FiveAnchorRecognition,
        FiveAnchorRecognition,
        FiveAnchorRecognition,
    ]

    def __post_init__(self) -> None:
        if tuple(item.position for item in self.observations) != _ANCHOR_ORDER:
            raise ValueError("Five-anchor OCR values must use the stable anchor order.")


@dataclass(frozen=True, slots=True)
class FiveAnchorExactRangeObservation:
    """One exact expected range from independently visible, spanned anchors."""

    matched_expected_range: FiveAnchorExpectedRangeEntry
    confirmations: tuple[FiveAnchorProofPosition, ...]
    recognized_values: tuple[tuple[FiveAnchorProofPosition, int], ...]
    recognition_confidences: tuple[tuple[FiveAnchorProofPosition, float], ...]
    average_confidence: float
    proof_type: str = FIVE_ANCHOR_PROOF_TYPE


@dataclass(frozen=True, slots=True)
class FiveAnchorUnknownRangeObservation:
    """Fail-closed v6 range result with source-local OCR diagnostics only."""

    reason_code: FiveAnchorProofUnknownReason
    recognized_texts: tuple[tuple[FiveAnchorProofPosition, str], ...]
    recognition_confidences: tuple[tuple[FiveAnchorProofPosition, float], ...]
    diagnostics: tuple[str, ...] = ()


FiveAnchorRangeObservation = FiveAnchorExactRangeObservation | FiveAnchorUnknownRangeObservation


class FiveAnchorExactResolver:
    """Attest only anchor-position values; never repair or infer OCR text."""

    def __init__(
        self,
        expected_ranges: FiveAnchorExpectedRangeTable,
        *,
        policy: FiveAnchorProofPolicy | None = None,
    ) -> None:
        self._expected_ranges = expected_ranges
        self._policy = policy or FiveAnchorProofPolicy()

    @property
    def fingerprint(self) -> str:
        return _canonical_sha256(
            {
                "expectedRangeTableFingerprint": self._expected_ranges.fingerprint,
                "proofPolicy": self._policy.as_dict(),
                "variantId": FIVE_ANCHOR_RANGE_VARIANT,
            }
        )

    def resolve(self, proof: FiveAnchorRecognitionProof) -> FiveAnchorRangeObservation:
        if any(not item.crop_complete for item in proof.observations):
            return self._unknown(proof, FiveAnchorProofUnknownReason.CROP_POSSIBLY_CLIPPED)
        if any(not item.crop_readable for item in proof.observations):
            return self._unknown(proof, FiveAnchorProofUnknownReason.LOCAL_BLUR)
        full_entries = tuple(
            entry for entry in self._expected_ranges.entries if not entry.is_partial_page
        )
        partial_entries = tuple(
            entry for entry in self._expected_ranges.entries if entry.is_partial_page
        )
        full_matches = tuple(
            entry for entry in full_entries if self._has_spanned_confirmations(proof, entry)
        )
        if len(full_matches) > 1:
            return self._unknown(proof, FiveAnchorProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE)
        if len(full_matches) == 1:
            matched = full_matches[0]
            non_numeric = self._visible_non_numeric(proof)
            if non_numeric is not None:
                return self._unknown(
                    proof,
                    FiveAnchorProofUnknownReason.NON_NUMERIC_OCR,
                    diagnostics=(non_numeric.value,),
                )
            conflict = self._visible_conflict(proof, matched)
            if conflict is not None:
                return self._unknown(
                    proof,
                    FiveAnchorProofUnknownReason.CONFLICTING_ANCHOR_VALUES,
                    diagnostics=(conflict.value,),
                )
            return self._exact(proof, matched)

        partial_match = next(
            (entry for entry in partial_entries if self._has_partial_anchor_evidence(proof, entry)),
            None,
        )
        if partial_match is not None:
            return self._unknown(
                proof,
                FiveAnchorProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW,
            )
        if any(self._confirmations(proof, entry) for entry in full_entries):
            if any(
                self._has_structural_spanned_confirmations(proof, entry) for entry in full_entries
            ):
                return self._unknown(proof, FiveAnchorProofUnknownReason.LOW_OCR_CONFIDENCE)
            return self._unknown(proof, FiveAnchorProofUnknownReason.INSUFFICIENT_SPANNED_EVIDENCE)
        return self._unknown_for_no_match(proof)

    def _has_spanned_confirmations(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> bool:
        confirmations = self._confirmations(proof, entry)
        if not self._has_structural_spanned_confirmations(proof, entry):
            return False
        return float(mean(item.recognition_confidence for item in confirmations)) >= (
            self._policy.minimum_average_confidence
        )

    def _has_structural_spanned_confirmations(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> bool:
        confirmations = self._confirmations(proof, entry)
        positions = {item.position for item in confirmations}
        if len(confirmations) < self._policy.minimum_confirming_anchors:
            return False
        if self._policy.require_center_anchor and FiveAnchorProofPosition.CENTER not in positions:
            return False
        bands = {position.vertical_band for position in positions}
        return not self._policy.require_vertical_span or {"top", "bottom"}.issubset(bands)

    def _has_partial_anchor_evidence(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> bool:
        return any(
            self._matches_entry(observation, entry)
            for observation in proof.observations
            if entry.value_for(observation.position) is not None
        )

    def _confirmations(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> tuple[FiveAnchorRecognition, ...]:
        return tuple(
            observation
            for observation in proof.observations
            if self._matches_entry(observation, entry)
        )

    def _matches_entry(
        self,
        observation: FiveAnchorRecognition,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> bool:
        expected = entry.value_for(observation.position)
        return (
            expected is not None
            and observation.crop_complete
            and observation.crop_readable
            and observation.recognition_confidence >= self._policy.minimum_label_confidence
            and _ASCII_DIGITS.fullmatch(observation.recognized_text) is not None
            and int(observation.recognized_text) == expected
        )

    def _visible_conflict(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> FiveAnchorProofPosition | None:
        for observation in proof.observations:
            expected = entry.value_for(observation.position)
            if (
                expected is None
                or not observation.crop_complete
                or not observation.crop_readable
                or observation.recognition_confidence < self._policy.minimum_label_confidence
                or _ASCII_DIGITS.fullmatch(observation.recognized_text) is None
            ):
                continue
            if int(observation.recognized_text) != expected:
                return observation.position
        return None

    def _visible_non_numeric(
        self,
        proof: FiveAnchorRecognitionProof,
    ) -> FiveAnchorProofPosition | None:
        return next(
            (
                observation.position
                for observation in proof.observations
                if observation.crop_complete
                and observation.crop_readable
                and observation.recognition_confidence >= self._policy.minimum_label_confidence
                and observation.recognized_text != ""
                and _ASCII_DIGITS.fullmatch(observation.recognized_text) is None
            ),
            None,
        )

    def _exact(
        self,
        proof: FiveAnchorRecognitionProof,
        entry: FiveAnchorExpectedRangeEntry,
    ) -> FiveAnchorExactRangeObservation:
        confirmations = self._confirmations(proof, entry)
        recognized_values = tuple(
            (item.position, int(item.recognized_text))
            for item in proof.observations
            if _ASCII_DIGITS.fullmatch(item.recognized_text) is not None
        )
        confidences = tuple(
            (item.position, item.recognition_confidence) for item in proof.observations
        )
        return FiveAnchorExactRangeObservation(
            matched_expected_range=entry,
            confirmations=tuple(item.position for item in confirmations),
            recognized_values=recognized_values,
            recognition_confidences=confidences,
            average_confidence=float(mean(item.recognition_confidence for item in confirmations)),
        )

    def _unknown_for_no_match(
        self,
        proof: FiveAnchorRecognitionProof,
    ) -> FiveAnchorUnknownRangeObservation:
        observations = proof.observations
        if any(not item.crop_complete for item in observations):
            return self._unknown(proof, FiveAnchorProofUnknownReason.CROP_POSSIBLY_CLIPPED)
        if any(not item.crop_readable for item in observations):
            return self._unknown(proof, FiveAnchorProofUnknownReason.LOCAL_BLUR)
        if all(item.recognized_text == "" for item in observations):
            return self._unknown(proof, FiveAnchorProofUnknownReason.INCOMPLETE_OCR)
        if any(
            item.recognized_text != "" and _ASCII_DIGITS.fullmatch(item.recognized_text) is None
            for item in observations
        ):
            return self._unknown(proof, FiveAnchorProofUnknownReason.NON_NUMERIC_OCR)
        numeric = tuple(
            item for item in observations if _ASCII_DIGITS.fullmatch(item.recognized_text)
        )
        if (
            numeric
            and max(item.recognition_confidence for item in numeric)
            < self._policy.minimum_label_confidence
        ):
            return self._unknown(proof, FiveAnchorProofUnknownReason.LOW_OCR_CONFIDENCE)
        if any(
            item.recognized_text != ""
            and item.recognition_confidence >= self._policy.minimum_label_confidence
            for item in observations
        ):
            return self._unknown(proof, FiveAnchorProofUnknownReason.NO_EXPECTED_RANGE_MATCH)
        return self._unknown(proof, FiveAnchorProofUnknownReason.INSUFFICIENT_SPANNED_EVIDENCE)

    @staticmethod
    def _unknown(
        proof: FiveAnchorRecognitionProof,
        reason: FiveAnchorProofUnknownReason,
        *,
        diagnostics: tuple[str, ...] = (),
    ) -> FiveAnchorUnknownRangeObservation:
        return FiveAnchorUnknownRangeObservation(
            reason_code=reason,
            recognized_texts=tuple(
                (item.position, item.recognized_text) for item in proof.observations
            ),
            recognition_confidences=tuple(
                (item.position, item.recognition_confidence) for item in proof.observations
            ),
            diagnostics=diagnostics,
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "FIVE_ANCHOR_EXPECTED_RANGE_CONTRACT_VERSION",
    "FIVE_ANCHOR_PROOF_POLICY_VERSION",
    "FIVE_ANCHOR_PROOF_TYPE",
    "FIVE_ANCHOR_RANGE_VARIANT",
    "FiveAnchorExactRangeObservation",
    "FiveAnchorExactResolver",
    "FiveAnchorExpectedRangeEntry",
    "FiveAnchorExpectedRangeTable",
    "FiveAnchorProofPolicy",
    "FiveAnchorProofPosition",
    "FiveAnchorProofUnknownReason",
    "FiveAnchorRangeObservation",
    "FiveAnchorRangeTopology",
    "FiveAnchorRecognition",
    "FiveAnchorRecognitionProof",
    "FiveAnchorUnknownRangeObservation",
]
