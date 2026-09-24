"""Pure computation of missing/added board segments for D-437 coverage.

Callers fetch two kinds of already-summarized intervals from storage and pass
them here as plain, sorted-by-nothing Python data: the sequence numbers that
are already "added" (per D-437) and the spans that explain *why* a number is
missing, ranked by priority. This module never touches the database; it only
does interval arithmetic, so it is fully unit-testable without PostgreSQL.
"""

from __future__ import annotations

import heapq
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class MissingReason(str, Enum):
    """Why a missing sequence number has no completed board, by priority.

    Lower value wins when multiple spans cover the same number. ``NO_SOURCE``
    is never supplied by a caller — it is the fallback when nothing else
    covers a missing number.
    """

    IMPORT_IN_PROGRESS = "import_in_progress"
    WAITING_FOR_GEOMETRY = "waiting_for_geometry"
    PARTIAL_SOURCE = "partial_source"
    FAILED = "failed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    NO_SOURCE = "no_source"

    @property
    def priority(self) -> int:
        return _REASON_PRIORITY[self]


_REASON_PRIORITY: dict[MissingReason, int] = {
    reason: index for index, reason in enumerate(MissingReason)
}


class BoardImportCoverageView(str, Enum):
    """Which side of D-437 coverage a page request lists."""

    MISSING = "missing"
    ADDED = "added"


@dataclass(frozen=True, slots=True)
class SequenceInterval:
    """An inclusive, 1-indexed range of sequence numbers: ``[start, end]``."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1 or self.end < self.start:
            raise ValueError(f"invalid sequence interval: [{self.start}, {self.end}]")


@dataclass(frozen=True, slots=True)
class ReasonSpan:
    """A ``reason`` that applies to every missing number in ``interval``.

    Overlapping spans are resolved by ``reason.priority``; the metadata
    fields only travel with the winning span and are attached to output
    segments where uniform across the whole merged segment.
    """

    interval: SequenceInterval
    reason: MissingReason
    error_code: str | None = None
    geometry_reason_code: str | None = None
    import_job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CoverageSegment:
    """One contiguous run of sequence numbers sharing the same state."""

    start: int
    end: int
    state: str  # "added" or a MissingReason value
    error_code: str | None = None
    geometry_reason_code: str | None = None
    import_job_id: UUID | None = None

    @property
    def count(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True, slots=True)
class CoveragePage:
    segments: tuple[CoverageSegment, ...]
    next_after_sequence_number: int | None


def _clip(
    interval: SequenceInterval, window_start: int, window_end: int
) -> SequenceInterval | None:
    start = max(interval.start, window_start)
    end = min(interval.end, window_end)
    if start > end:
        return None
    return SequenceInterval(start, end)


def _boundary_points(
    window_start: int,
    window_end: int,
    added: Sequence[SequenceInterval],
    reasons: Sequence[ReasonSpan],
) -> list[int]:
    points: set[int] = {window_start, window_end + 1}
    for interval in added:
        clipped = _clip(interval, window_start, window_end)
        if clipped is not None:
            points.add(clipped.start)
            points.add(clipped.end + 1)
    for span in reasons:
        clipped = _clip(span.interval, window_start, window_end)
        if clipped is not None:
            points.add(clipped.start)
            points.add(clipped.end + 1)
    return sorted(p for p in points if window_start <= p <= window_end + 1)


class _AddedLookup:
    """O(log n) "is this point added" queries over sorted, disjoint intervals.

    ``added`` is produced by a SQL gaps-and-islands query, so it always
    arrives sorted by start and non-overlapping — a linear scan per point
    (the original implementation) is O(points * len(added)), which is
    quadratic in practice: a game with hundreds of thousands of added
    numbers has thousands of islands, and a full-range sweep visits
    thousands of points, so the naive scan took tens of seconds on real
    data (see D-437 board-import-coverage performance regression). Binary
    search on the interval starts makes each query O(log len(added)).
    """

    def __init__(self, added: Sequence[SequenceInterval]) -> None:
        self._added = added
        self._starts = [interval.start for interval in added]

    def contains(self, point: int) -> bool:
        index = bisect_right(self._starts, point) - 1
        if index < 0:
            return False
        interval = self._added[index]
        return interval.start <= point <= interval.end


def _reason_sweep(
    points: Sequence[int], reasons: Sequence[ReasonSpan]
) -> dict[int, ReasonSpan]:
    """Map each of ``points`` to its highest-priority active span, if any.

    A classic interval sweep with a lazily-cleaned priority heap: O((len(
    points) + len(reasons)) * log(len(reasons))) overall, instead of the
    O(len(points) * len(reasons)) a per-point linear scan costs — the same
    quadratic blowup ``_AddedLookup`` above fixes, just for reasons instead
    of added islands. ``points`` must be sorted ascending.
    """

    starts_at: dict[int, list[ReasonSpan]] = {}
    ends_at: dict[int, list[ReasonSpan]] = {}
    for span in reasons:
        starts_at.setdefault(span.interval.start, []).append(span)
        ends_at.setdefault(span.interval.end + 1, []).append(span)

    heap: list[tuple[int, int, ReasonSpan]] = []
    counter = 0
    live_ids: set[int] = set()
    result: dict[int, ReasonSpan] = {}
    for point in points:
        for span in ends_at.get(point, ()):
            live_ids.discard(id(span))
        for span in starts_at.get(point, ()):
            counter += 1
            heapq.heappush(heap, (span.reason.priority, counter, span))
            live_ids.add(id(span))
        while heap and id(heap[0][2]) not in live_ids:
            heapq.heappop(heap)
        if heap:
            result[point] = heap[0][2]
    return result


def build_coverage_page(
    *,
    expected: int,
    added: Sequence[SequenceInterval],
    reasons: Sequence[ReasonSpan],
    view: str,
    range_from: int | None = None,
    range_to: int | None = None,
    after_sequence_number: int | None = None,
    limit: int = 100,
) -> CoveragePage:
    """Sweep ``[window_start, window_end]`` and return up to ``limit`` segments.

    ``view`` is ``"missing"`` or ``"added"``. The window defaults to
    ``[1, expected]``, narrowed by ``range_from``/``range_to`` and by
    ``after_sequence_number`` (exclusive keyset cursor on the sequence
    number, not the segment).
    """

    if view not in ("missing", "added"):
        raise ValueError(f"unknown view: {view!r}")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if expected < 1:
        raise ValueError("expected must be >= 1")

    window_start = max(1, range_from or 1)
    window_end = min(expected, range_to or expected)
    if after_sequence_number is not None:
        window_start = max(window_start, after_sequence_number + 1)
    if window_start > window_end:
        return CoveragePage(segments=(), next_after_sequence_number=None)

    points = _boundary_points(window_start, window_end, added, reasons)
    added_lookup = _AddedLookup(added)
    reason_by_point = _reason_sweep(points, reasons) if view == "missing" else {}
    segments: list[CoverageSegment] = []
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1] - 1
        if end < start:
            continue
        is_added = added_lookup.contains(start)
        if view == "added":
            if not is_added:
                continue
            state = "added"
            error_code = geometry_reason_code = None
            import_job_id = None
        else:
            if is_added:
                continue
            span = reason_by_point.get(start)
            reason = span.reason if span is not None else MissingReason.NO_SOURCE
            state = reason.value
            error_code = span.error_code if span is not None else None
            geometry_reason_code = span.geometry_reason_code if span is not None else None
            import_job_id = span.import_job_id if span is not None else None

        if (
            segments
            and segments[-1].state == state
            and segments[-1].error_code == error_code
            and segments[-1].geometry_reason_code == geometry_reason_code
            and segments[-1].import_job_id == import_job_id
            and segments[-1].end + 1 == start
        ):
            merged = CoverageSegment(
                start=segments[-1].start,
                end=end,
                state=state,
                error_code=error_code,
                geometry_reason_code=geometry_reason_code,
                import_job_id=import_job_id,
            )
            segments[-1] = merged
        else:
            segments.append(
                CoverageSegment(
                    start=start,
                    end=end,
                    state=state,
                    error_code=error_code,
                    geometry_reason_code=geometry_reason_code,
                    import_job_id=import_job_id,
                )
            )

    if len(segments) > limit:
        truncated = segments[:limit]
        next_after = truncated[-1].end
        return CoveragePage(segments=tuple(truncated), next_after_sequence_number=next_after)
    return CoveragePage(segments=tuple(segments), next_after_sequence_number=None)


def count_missing_by_reason(
    *,
    expected: int,
    added: Sequence[SequenceInterval],
    reasons: Sequence[ReasonSpan],
) -> dict[MissingReason, int]:
    """Total missing numbers per reason across the full ``[1, expected]`` range."""

    counts: dict[MissingReason, int] = {reason: 0 for reason in MissingReason}
    points = _boundary_points(1, expected, added, reasons)
    added_lookup = _AddedLookup(added)
    reason_by_point = _reason_sweep(points, reasons)
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1] - 1
        if end < start or added_lookup.contains(start):
            continue
        span = reason_by_point.get(start)
        reason = span.reason if span is not None else MissingReason.NO_SOURCE
        counts[reason] += end - start + 1
    return counts


__all__ = [
    "BoardImportCoverageView",
    "CoveragePage",
    "CoverageSegment",
    "MissingReason",
    "ReasonSpan",
    "SequenceInterval",
    "build_coverage_page",
    "count_missing_by_reason",
]
