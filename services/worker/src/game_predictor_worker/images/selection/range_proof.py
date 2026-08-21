"""Proof classification shared by selection and bounds reconciliation."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import RangeLabelObservation, SequenceRange

_STRONG_PROOF_REASONS = frozenset(
    {
        "RANGE_OCR_LABEL_LATTICE_WINDOW",
        "RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
        "RANGE_OCR_LAYOUT_ANCHORED_FOUR_LABEL",
    }
)
_NON_LOCAL_OR_WEAK_REASONS = frozenset(
    {
        "RANGE_CARDINALITY_INFERRED",
        "RANGE_EXACT_GAP_INFERRED",
        "RANGE_INFERRED_FROM_BOUNDED_GAP",
        "RANGE_OWNER_ANCHOR",
        "RANGE_OCR_FUZZY_CANDIDATE",
        "RANGE_OCR_LABEL_LATTICE_TWO_LABEL",
        "RANGE_OCR_LAYOUT_ANCHORED_TWO_LABEL",
        "RANGE_CONFLICT",
        "RANGE_OCR_FUSED_EVIDENCE_CONFLICT",
    }
)
_EXPECTED_SEQUENCE_REASON = "RANGE_EXPECTED_SEQUENCE_CONFIRMED"
_EXPECTED_SEQUENCE_FUZZY_REASON = "RANGE_EXPECTED_SEQUENCE_FUZZY_CONFIRMED"
_EXPECTED_SEQUENCE_BLOCKING_REASONS = frozenset(
    {
        "RANGE_CONFLICT",
        "RANGE_OCR_FUSED_EVIDENCE_CONFLICT",
    }
)


def has_strong_local_range_proof(
    recognized_range: SequenceRange | None,
    reason_codes: Iterable[str],
    *,
    minimum_confidence: float,
    label_observations: Iterable[RangeLabelObservation] = (),
    require_position_evidence: bool = False,
) -> bool:
    """Return whether one JPEG independently proves its canonical range."""

    reasons = frozenset(reason_codes)
    if _EXPECTED_SEQUENCE_FUZZY_REASON in reasons:
        if (
            recognized_range is None
            or recognized_range.confidence < minimum_confidence
            or reasons.intersection(_EXPECTED_SEQUENCE_BLOCKING_REASONS)
        ):
            return False
        if not require_position_evidence:
            return True
        fuzzy_positions: set[int] = set()
        exact_positions: set[int] = set()
        for observation in label_observations:
            if (
                observation.confidence < 0.82
                or observation.position_index >= recognized_range.board_count
                or observation.sequence_number
                != recognized_range.start + observation.position_index
                or observation.route
                not in {"expected_sequence_exact", "expected_sequence_fuzzy"}
            ):
                return False
            fuzzy_positions.add(observation.position_index)
            if observation.route == "expected_sequence_exact":
                exact_positions.add(observation.position_index)
        return (
            len(fuzzy_positions) >= 3
            and bool(exact_positions)
            and len({position // 3 for position in fuzzy_positions}) >= 2
            and len({position % 3 for position in fuzzy_positions}) >= 2
        )

    if _EXPECTED_SEQUENCE_REASON in reasons:
        if (
            recognized_range is None
            or recognized_range.confidence < minimum_confidence
            or reasons.intersection(_EXPECTED_SEQUENCE_BLOCKING_REASONS)
        ):
            return False
        if not require_position_evidence:
            return True
        expected_positions: set[int] = set()
        for observation in label_observations:
            if observation.confidence < 0.82:
                continue
            if (
                observation.position_index >= recognized_range.board_count
                or observation.sequence_number
                != recognized_range.start + observation.position_index
            ):
                return False
            expected_positions.add(observation.position_index)
        return len(expected_positions) >= 2

    route_is_strong = (
        recognized_range is not None
        and recognized_range.confidence >= minimum_confidence
        and not reasons.intersection(_NON_LOCAL_OR_WEAK_REASONS)
        and bool(reasons.intersection(_STRONG_PROOF_REASONS))
    )
    if not route_is_strong or recognized_range is None:
        return False
    if not require_position_evidence:
        return True
    by_position: dict[int, RangeLabelObservation] = {}
    minimum_label_confidence = (
        0.82
        if reasons.intersection(
            {
                "RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",
                "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
            }
        )
        else 0.72
    )
    for observation in label_observations:
        if (
            observation.sequence_number - observation.position_index != recognized_range.start
            or observation.confidence < minimum_label_confidence
        ):
            return False
        current = by_position.get(observation.position_index)
        if current is None or observation.confidence > current.confidence:
            by_position[observation.position_index] = observation
    strong_positions = frozenset(by_position)
    return len(strong_positions) >= 3 and any(
        position + 1 in strong_positions for position in strong_positions
    )


__all__ = ["has_strong_local_range_proof"]
