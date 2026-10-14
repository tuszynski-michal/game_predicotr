"""Read-only diagnostics with explicit populations; counters are not additive."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from game_predictor_api.domain.board_import_coverage import (
    MissingReason,
    ReasonSpan,
    SequenceInterval,
    count_missing_by_reason,
)

# Matches the Admin's existing symbol-review "below_60" confidence band.
GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD: Final = 0.6


@dataclass(frozen=True, slots=True)
class GridDiagnostics:
    review_rows_by_status: dict[str, int]
    review_sequences_by_status: dict[str, int]
    qualifying_review_rows: int
    qualifying_review_sequences: int
    canonical_sequences: int
    canonical_review_overlap: int
    duplicate_qualifying_review_rows: int
    deferred_slots_by_status: dict[str, int]
    deferred_slots_by_reason: dict[str, int]
    deferred_slot_coverage: dict[str, int]
    flagged_grid_boards: int
    unconfirmed_geometry_boards: int
    flagged_unconfirmed_boards: int
    symbol_cells: dict[str, int]
    symbol_cell_intersections: dict[str, int]
    missing_reason_signals: dict[str, int]
    missing_reason_intersections: dict[str, int]
    source_images: dict[str, int]
    source_positions: dict[str, int]
    source_gate: dict[str, int]
    low_confidence_threshold: float = GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD
    scope: str = "whole_game"


def missing_reason_diagnostics(
    *, expected: int, added: Sequence[SequenceInterval], reasons: Sequence[ReasonSpan]
) -> tuple[dict[str, int], dict[str, int]]:
    """Retain secondary reasons and intersections, without enumerating sequences.

    Dominant reasons remain in the coverage report. These signals only concern
    missing sequences; they must never be summed as additional missing boards.
    """
    grouped: dict[MissingReason, list[SequenceInterval]] = {}
    for span in reasons:
        grouped.setdefault(span.reason, []).append(span.interval)
    normalized: dict[MissingReason, list[SequenceInterval]] = {}
    for reason, intervals in grouped.items():
        merged: list[SequenceInterval] = []
        for interval in sorted(intervals, key=lambda item: (item.start, item.end)):
            if merged and interval.start <= merged[-1].end + 1:
                previous = merged.pop()
                merged.append(SequenceInterval(previous.start, max(previous.end, interval.end)))
            else:
                merged.append(interval)
        normalized[reason] = merged

    def count(intervals: Sequence[SequenceInterval]) -> int:
        return count_missing_by_reason(
            expected=expected,
            added=added,
            reasons=[ReasonSpan(interval, MissingReason.UNKNOWN) for interval in intervals],
        ).get(MissingReason.UNKNOWN, 0)

    signals = {reason.value: count(intervals) for reason, intervals in normalized.items()}
    intersections: dict[str, int] = {}
    ordered = sorted(normalized, key=lambda reason: reason.priority)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            left_intervals, right_intervals = normalized[left], normalized[right]
            overlaps: list[SequenceInterval] = []
            i = j = 0
            while i < len(left_intervals) and j < len(right_intervals):
                a, b = left_intervals[i], right_intervals[j]
                start, end = max(a.start, b.start), min(a.end, b.end)
                if start <= end:
                    overlaps.append(SequenceInterval(start, end))
                if a.end <= b.end:
                    i += 1
                else:
                    j += 1
            total = count(overlaps)
            if total:
                intersections[f"{left.value}&{right.value}"] = total
    return signals, intersections
