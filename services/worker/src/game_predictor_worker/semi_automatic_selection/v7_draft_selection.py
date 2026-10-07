"""Tentative range suggestions, deliberately separate from automatic range proof."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class V7DraftChoice:
    expected_index: int
    range_start: int
    range_end: int
    source_index: int
    matching_labels: int
    conflicting_labels: int
    mean_confidence: float
    reason: str


def suggest_draft_choices(
    diagnostics: Sequence[Mapping[str, Any]],
    *,
    first: int,
    last: int,
    occupied: frozenset[int] = frozenset(),
) -> tuple[V7DraftChoice, ...]:
    """Use actual number/position votes; neighbours never invent an unseen page.

    Four votes at >=.75 or three at >=.90 can suggest a draft. Two votes at
    >=.75 require bracketing proven frames at most four pages apart. Conflicting
    labels are recorded, not transformed into evidence. Existing owners win.
    """
    if first < 1 or last < first or (last - first + 1) % 9:
        raise ValueError("Draft bounds must contain complete nine-number pages.")
    ordered = sorted(diagnostics, key=lambda item: int(item["sourceIndex"]))
    anchors: list[tuple[int, int]] = []
    for item in ordered:
        proof = item.get("proof")
        if isinstance(proof, Mapping) and proof.get("kind") != "none":
            start = proof.get("rangeStart")
            if isinstance(start, int) and first <= start <= last and (start - first) % 9 == 0:
                anchors.append((int(item["sourceIndex"]), (start - first) // 9))
    anchor_sources = [source for source, _ in anchors]
    candidates: dict[int, list[V7DraftChoice]] = defaultdict(list)
    for item in ordered:
        source = int(item["sourceIndex"])
        if item.get("sourceErrorCode") is not None:
            continue
        votes: dict[int, dict[int, float]] = defaultdict(dict)
        reliable_positions: set[int] = set()
        raw_labels = item.get("labels", ())
        if not isinstance(raw_labels, list | tuple):
            raise ValueError("Malformed stored label diagnostics.")
        for label in raw_labels:
            if not isinstance(label, Mapping):
                raise ValueError("Malformed stored label.")
            position = int(label["positionIndex"])
            confidence = float(label["recognitionConfidence"])
            if (
                not 0 <= position < 9
                or float(label["positionConfidence"]) < 0.9
                or confidence < 0.75
            ):
                continue
            reliable_positions.add(position)
            start = int(label["sequenceNumber"]) - position
            if first <= start <= last - 8 and (start - first) % 9 == 0:
                votes[(start - first) // 9][position] = confidence
        ranked = sorted(
            votes.items(), key=lambda pair: (-len(pair[1]), -sum(pair[1].values()), pair[0])
        )
        if not ranked:
            continue
        expected, matching = ranked[0]
        if expected in occupied or (len(ranked) > 1 and len(ranked[1][1]) >= len(matching)):
            continue
        at = bisect_left(anchor_sources, source)
        left = anchors[at - 1] if at else None
        right = anchors[at] if at < len(anchors) else None
        bracketed = left is not None and right is not None
        if bracketed:
            assert left is not None and right is not None
            lower, upper = sorted((left[1], right[1]))
            if not lower <= expected <= upper:
                continue
        strong_votes = sum(value >= 0.9 for value in matching.values())
        if len(matching) >= 4:
            reason = "partial_four_labels"
        elif strong_votes >= 3:
            reason = "partial_three_high_confidence_labels"
        elif (
            len(matching) >= 2
            and left is not None
            and right is not None
            and abs(left[1] - right[1]) <= 4
        ):
            reason = "partial_two_labels_between_proven_neighbours"
        else:
            continue
        candidates[expected].append(
            V7DraftChoice(
                expected,
                first + expected * 9,
                first + expected * 9 + 8,
                source,
                len(matching),
                len(reliable_positions - matching.keys()),
                sum(matching.values()) / len(matching),
                reason,
            )
        )
    choices = []
    for _expected, group in sorted(candidates.items()):
        midpoint = (group[0].source_index + group[-1].source_index) / 2
        choices.append(
            min(
                group,
                key=lambda choice: (
                    -choice.matching_labels,
                    choice.conflicting_labels,
                    -choice.mean_confidence,
                    abs(choice.source_index - midpoint),
                    choice.source_index,
                ),
            )
        )
    return tuple(choices)


@dataclass(frozen=True, slots=True)
class V7InterpolatedChoice:
    expected_index: int
    range_start: int
    range_end: int
    source_index: int
    interval_first: int
    interval_last: int
    left_anchor_source: int
    right_anchor_source: int
    left_anchor_range: int
    right_anchor_range: int
    reason: str = "estimated_equal_partition"


def suggest_interpolated_choices(
    diagnostics: Sequence[Mapping[str, Any]],
    *,
    first: int,
    last: int,
    direction: str = "ascending",
    occupied: frozenset[int] = frozenset(),
) -> tuple[V7InterpolatedChoice, ...]:
    """Partition unlabelled intervals, never claim the estimated page was read.

    Use occurrence edges rather than the selected representative of an anchor.
    Local contrary readings and source errors exclude frames. No edge extrapolation.
    """
    if first < 1 or last < first or (last - first + 1) % 9:
        raise ValueError("Interpolation requires complete nine-number pages.")
    if direction not in {"ascending", "descending"}:
        raise ValueError("Invalid interpolation direction.")
    step = 1 if direction == "ascending" else -1
    ordered = sorted(diagnostics, key=lambda item: int(item["sourceIndex"]))
    by_source = {int(item["sourceIndex"]): item for item in ordered}
    if len(by_source) != len(ordered):
        raise ValueError("Duplicate source diagnostics.")
    anchors = _draft_anchors(ordered, first=first, last=last)
    choices: dict[int, list[V7InterpolatedChoice]] = defaultdict(list)
    for left, right in zip(anchors, anchors[1:], strict=False):
        count = (right[2] - left[2]) * step - 1
        lo, hi = left[1] + 1, right[0] - 1
        length = hi - lo + 1
        if not 1 <= count <= 128 or length < 2 * count:
            continue
        for offset in range(count):
            expected = left[2] + step * (offset + 1)
            if expected in occupied:
                continue
            begin = lo + length * offset // count
            end = lo + length * (offset + 1) // count - 1
            start = first + 9 * expected
            eligible = []
            for source in range(begin, end + 1):
                frame = by_source.get(source)
                if frame is None or frame.get("sourceErrorCode") is not None:
                    continue
                contrary = any(
                    float(label["positionConfidence"]) >= 0.9
                    and float(label["recognitionConfidence"]) >= 0.75
                    and int(label["sequenceNumber"]) - int(label["positionIndex"]) != start
                    for label in frame.get("labels", ())
                )
                if not contrary:
                    eligible.append(source)
            if eligible:
                source = min(eligible, key=lambda value: (abs(2 * value - begin - end), value))
                choices[expected].append(
                    V7InterpolatedChoice(
                        expected,
                        start,
                        start + 8,
                        source,
                        begin,
                        end,
                        left[1],
                        right[0],
                        first + left[2] * 9,
                        first + right[2] * 9,
                    )
                )
    # Repeated/reversed sequences can suggest a page twice; do not silently choose.
    return tuple(values[0] for _, values in sorted(choices.items()) if len(values) == 1)


def _draft_anchors(
    ordered: Sequence[Mapping[str, Any]], *, first: int, last: int
) -> list[tuple[int, int, int]]:
    """Return tentative occurrence edges; callers decide how to handle ambiguity."""
    partial = {
        choice.source_index: choice.expected_index
        for item in ordered
        for choice in suggest_draft_choices([item], first=first, last=last)
    }
    anchors: list[tuple[int, int, int]] = []
    for item in ordered:
        source = int(item["sourceIndex"])
        if item.get("sourceErrorCode") is not None:
            continue
        proof = item.get("proof")
        start = proof.get("rangeStart") if isinstance(proof, Mapping) else None
        page = partial.get(source)
        if (
            isinstance(proof, Mapping)
            and proof.get("kind") not in {None, "none"}
            and type(start) is int
            and first <= start <= last - 8
            and (start - first) % 9 == 0
        ):
            page = (start - first) // 9
        if page is None:
            continue
        if anchors and anchors[-1][2] == page:
            anchors[-1] = (anchors[-1][0], source, page)
        else:
            anchors.append((source, source, page))
    return anchors
