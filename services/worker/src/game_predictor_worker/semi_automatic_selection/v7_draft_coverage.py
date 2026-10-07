"""Complete editable draft coverage; timing estimates never become OCR evidence."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .v7_draft_selection import _draft_anchors


@dataclass(frozen=True, slots=True)
class V7CoverageChoice:
    expected_index: int
    range_start: int
    range_end: int
    source_index: int
    interval_first: int
    interval_last: int
    left_anchor_source: int | None
    right_anchor_source: int | None
    left_anchor_range: int | None
    right_anchor_range: int | None
    conflicting_labels: int
    reused_source: bool
    reason: str


def _monotone_anchors(
    anchors: Sequence[tuple[int, int, int]], *, pages: int, descending: bool
) -> list[tuple[int, int, int]]:
    """Longest increasing ordinal chain; equal ranks keep the earlier occurrence."""
    tails: list[int] = []
    tail_indexes: list[int] = []
    parents = [-1] * len(anchors)
    for index, (_, _, page) in enumerate(anchors):
        rank = pages - 1 - page if descending else page
        at = bisect_left(tails, rank)
        if at < len(tails) and tails[at] == rank:
            continue
        parents[index] = tail_indexes[at - 1] if at else -1
        if at == len(tails):
            tails.append(rank)
            tail_indexes.append(index)
        else:
            tails[at] = rank
            tail_indexes[at] = index
    result = []
    index = tail_indexes[-1] if tail_indexes else -1
    while index != -1:
        result.append(anchors[index])
        index = parents[index]
    return list(reversed(result))


def suggest_complete_choices(
    diagnostics: Sequence[Mapping[str, Any]],
    *,
    first: int,
    last: int,
    source_count: int,
    direction: str = "ascending",
    occupied: frozenset[int] = frozenset(),
    used_sources: frozenset[int] = frozenset(),
) -> tuple[V7CoverageChoice, ...]:
    """Select every remaining configured page, recording uncertainty instead of holes.

    Anchors partition the source into occurrences, intervening groups and edges.
    A short/empty partition uses the nearest usable source, possibly again. Only
    absent usable source data fails; publication still verifies actual JPEG bytes.
    """
    if first < 1 or last < first or (last - first + 1) % 9:
        raise ValueError("Coverage requires complete nine-number pages.")
    if direction not in {"ascending", "descending"}:
        raise ValueError("Invalid coverage direction.")
    if source_count < 1:
        raise ValueError("Coverage requires at least one source image.")
    pages = (last - first + 1) // 9
    if any(not 0 <= page < pages for page in occupied):
        raise ValueError("Occupied page outside configured coverage.")
    ordered = sorted(diagnostics, key=lambda item: int(item["sourceIndex"]))
    by_source = {int(item["sourceIndex"]): item for item in ordered}
    if len(by_source) != len(ordered) or any(
        not 0 <= source < source_count for source in by_source
    ):
        raise ValueError("Duplicate or out-of-bounds source diagnostics.")
    if len(occupied) == pages:
        return ()
    usable = [
        source
        for source in range(source_count)
        if by_source.get(source, {}).get("sourceErrorCode") is None
    ]
    if not usable:
        raise ValueError("Coverage has no usable source image.")
    usable_set = set(usable)
    labels: dict[int, list[int]] = {
        source: [
            int(label["sequenceNumber"]) - int(label["positionIndex"])
            for label in item.get("labels", ())
            if float(label["positionConfidence"]) >= 0.9
            and float(label["recognitionConfidence"]) >= 0.75
        ]
        for source, item in by_source.items()
    }
    descending = direction == "descending"
    anchors = _monotone_anchors(
        _draft_anchors(ordered, first=first, last=last), pages=pages, descending=descending
    )
    # Virtual anchors cover the prefix/suffix and the whole source without OCR.
    boundaries = (
        [(-1, -1, -1)]
        + [(lo, hi, pages - 1 - page if descending else page) for lo, hi, page in anchors]
        + [(source_count, source_count, pages)]
    )
    result: dict[int, V7CoverageChoice] = {}
    selected = set(used_sources)

    def choose(
        rank: int,
        begin: int,
        end: int,
        left: tuple[int, int, int],
        right: tuple[int, int, int],
        reason: str,
    ) -> None:
        expected = pages - 1 - rank if descending else rank
        if expected in occupied:
            return
        start = first + 9 * expected
        candidates = [source for source in range(begin, end + 1) if source in usable_set]
        nearest = not candidates
        center_twice = begin + end
        if nearest:
            at = bisect_left(usable, (center_twice + 1) // 2)
            candidates = usable[max(0, at - 1) : at + 1]
        source = min(
            candidates,
            key=lambda value: (
                # No move outside the partition solely to avoid contrary OCR.
                sum(label != start for label in labels.get(value, ())) if not nearest else 0,
                abs(2 * value - center_twice),
                value,
            ),
        )
        conflicts = sum(label != start for label in labels.get(source, ()))
        result[expected] = V7CoverageChoice(
            expected,
            start,
            start + 8,
            source,
            begin,
            end,
            left[1] if left[2] >= 0 else None,
            right[0] if right[2] < pages else None,
            first + 9 * (pages - 1 - left[2] if descending else left[2]) if left[2] >= 0 else None,
            first + 9 * (pages - 1 - right[2] if descending else right[2])
            if right[2] < pages
            else None,
            conflicts,
            source in selected,
            "estimated_nearest_available" if nearest else reason,
        )
        selected.add(source)

    for left, right in zip(boundaries, boundaries[1:], strict=False):
        count = right[2] - left[2] - 1
        lo, hi = left[1] + 1, right[0] - 1
        length = hi - lo + 1
        reason = (
            "estimated_whole_source"
            if not anchors
            else "estimated_prefix"
            if left[2] == -1
            else "estimated_suffix"
            if right[2] == pages
            else "estimated_partition"
        )
        for offset in range(count):
            choose(
                left[2] + offset + 1,
                lo + length * offset // count,
                lo + length * (offset + 1) // count - 1,
                left,
                right,
                reason,
            )
        if right[2] < pages:
            choose(right[2], right[0], right[1], right, right, "estimated_anchor_occurrence")
    if len(result) + len(occupied) != pages:
        raise ValueError("Incomplete draft coverage.")
    return tuple(result[page] for page in sorted(result))
