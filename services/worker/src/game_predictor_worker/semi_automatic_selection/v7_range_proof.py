"""Source-local v7 page proof; it never derives a number from neighbouring frames."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import SemiAutomaticSelectionRange

V7_RANGE_PROOF_VERSION = "v7-range-proof-v1"


class V7RangeProofError(ValueError):
    """A malformed evidence payload that must not reach a selector."""


class V7RangeProofKind(StrEnum):
    NONE = "none"
    STRONG_FIVE_LABEL = "strong_five_label"
    MULTI_FRAME_THREE_PLUS_THREE = "multi_frame_three_plus_three"


@dataclass(frozen=True, slots=True)
class V7LabelEvidence:
    """One readable numerical label tied to its own 3x3 grid position."""

    position_index: int
    sequence_number: int
    recognition_confidence: float
    position_confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.position_index < 9 or self.sequence_number < 1:
            raise V7RangeProofError("Label position or number is invalid.")
        if not 0 <= self.recognition_confidence <= 1 or not 0 <= self.position_confidence <= 1:
            raise V7RangeProofError("Label confidence is invalid.")


@dataclass(frozen=True, slots=True)
class V7FrameEvidence:
    """OCR results of one source image, without quality or source-order context."""

    source_id: str
    occurrence_id: str
    visual_cluster_id: str
    labels: tuple[V7LabelEvidence, ...]

    def __post_init__(self) -> None:
        if not self.source_id or not self.occurrence_id or not self.visual_cluster_id:
            raise V7RangeProofError("Source, occurrence and visual-cluster IDs are required.")
        positions = tuple(item.position_index for item in self.labels)
        if len(set(positions)) != len(positions):
            raise V7RangeProofError("A frame cannot contain two labels at the same position.")


@dataclass(frozen=True, slots=True)
class V7RangeProofPolicy:
    """Provisional, versioned T02 thresholds; T05 must calibrate replacement values."""

    minimum_recognition_confidence: float = 0.90
    minimum_position_confidence: float = 0.90
    minimum_weak_labels: int = 3
    minimum_strong_labels: int = 5

    def __post_init__(self) -> None:
        if (
            not 0 <= self.minimum_recognition_confidence <= 1
            or not 0 <= self.minimum_position_confidence <= 1
            or self.minimum_weak_labels != 3
            or self.minimum_strong_labels != 5
        ):
            raise V7RangeProofError("V7 proof policy is invalid.")


@dataclass(frozen=True, slots=True)
class V7FrameHypothesis:
    """A single range backed by labels from exactly one source frame."""

    frame: V7FrameEvidence
    sequence_range: SemiAutomaticSelectionRange
    matching_labels: tuple[V7LabelEvidence, ...]
    conflicting_labels: tuple[V7LabelEvidence, ...]

    @property
    def is_weakly_eligible(self) -> bool:
        return len(self.matching_labels) >= 3 and not self.conflicting_labels

    @property
    def is_strong(self) -> bool:
        return len(self.matching_labels) >= 5 and not self.conflicting_labels


@dataclass(frozen=True, slots=True)
class V7RangeProofResult:
    """Auditable proof result. ``none`` is never silently repaired downstream."""

    kind: V7RangeProofKind
    sequence_range: SemiAutomaticSelectionRange | None
    supporting_source_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


class V7RangeProofResolver:
    """Match explicit labels to declared full pages, with conflict vetoes."""

    def __init__(
        self,
        expected_ranges: tuple[SemiAutomaticSelectionRange, ...],
        *,
        policy: V7RangeProofPolicy | None = None,
    ) -> None:
        if not expected_ranges or any(value.board_count != 9 for value in expected_ranges):
            raise V7RangeProofError("V7 proof requires declared full 3x3 expected ranges.")
        if len(set(expected_ranges)) != len(expected_ranges):
            raise V7RangeProofError("Expected ranges must be unique.")
        self._expected_ranges = expected_ranges
        self._policy = policy or V7RangeProofPolicy()

    def resolve_frame(self, frame: V7FrameEvidence) -> V7RangeProofResult:
        hypotheses = tuple(self._hypothesis(frame, value) for value in self._expected_ranges)
        strong = tuple(item for item in hypotheses if item.is_strong)
        if len(strong) == 1:
            return V7RangeProofResult(
                kind=V7RangeProofKind.STRONG_FIVE_LABEL,
                sequence_range=strong[0].sequence_range,
                supporting_source_ids=(frame.source_id,),
                reason_codes=(),
            )
        if len(strong) > 1:
            return self._none("AMBIGUOUS_RANGE_HYPOTHESIS")
        weak = tuple(item for item in hypotheses if item.is_weakly_eligible)
        if len(weak) > 1:
            return self._none("AMBIGUOUS_RANGE_HYPOTHESIS")
        if any(item.conflicting_labels for item in hypotheses if len(item.matching_labels) >= 3):
            return self._none("CONFLICTING_RELIABLE_LABEL")
        return self._none("INSUFFICIENT_OWN_LABEL_EVIDENCE")

    def resolve_pair(
        self,
        first: V7FrameEvidence,
        second: V7FrameEvidence,
    ) -> V7RangeProofResult:
        if first.source_id == second.source_id:
            return self._none("REENCODED_OR_DUPLICATE_SOURCE")
        if first.occurrence_id != second.occurrence_id:
            return self._none("CROSS_OCCURRENCE_CONFIRMATION_FORBIDDEN")
        if first.visual_cluster_id == second.visual_cluster_id:
            return self._none("VISUALLY_DEPENDENT_CONFIRMATION")
        first_hypotheses = tuple(self._hypothesis(first, value) for value in self._expected_ranges)
        second_hypotheses = tuple(
            self._hypothesis(second, value) for value in self._expected_ranges
        )
        common = tuple(
            left
            for left in first_hypotheses
            if left.is_weakly_eligible
            and any(
                right.is_weakly_eligible and right.sequence_range == left.sequence_range
                for right in second_hypotheses
            )
        )
        if len(common) == 1:
            return V7RangeProofResult(
                kind=V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,
                sequence_range=common[0].sequence_range,
                supporting_source_ids=(first.source_id, second.source_id),
                reason_codes=(),
            )
        if len(common) > 1:
            return self._none("AMBIGUOUS_RANGE_HYPOTHESIS")
        if any(
            item.conflicting_labels
            and len(item.matching_labels) >= self._policy.minimum_weak_labels
            for item in (*first_hypotheses, *second_hypotheses)
        ):
            return self._none("CONFLICTING_RELIABLE_LABEL")
        return self._none("INSUFFICIENT_INDEPENDENT_3_PLUS_3_EVIDENCE")

    def _hypothesis(
        self,
        frame: V7FrameEvidence,
        sequence_range: SemiAutomaticSelectionRange,
    ) -> V7FrameHypothesis:
        reliable = tuple(item for item in frame.labels if self._is_reliable(item))
        matching = tuple(
            item
            for item in reliable
            if item.sequence_number == sequence_range.start + item.position_index
        )
        conflicts = tuple(item for item in reliable if item not in matching)
        return V7FrameHypothesis(frame, sequence_range, matching, conflicts)

    def _is_reliable(self, label: V7LabelEvidence) -> bool:
        return (
            label.recognition_confidence >= self._policy.minimum_recognition_confidence
            and label.position_confidence >= self._policy.minimum_position_confidence
        )

    @staticmethod
    def _none(reason: str) -> V7RangeProofResult:
        return V7RangeProofResult(V7RangeProofKind.NONE, None, (), (reason,))
