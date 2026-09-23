from __future__ import annotations

from uuid import UUID

import pytest
from game_predictor_api.domain.board_import_coverage import (
    MissingReason,
    ReasonSpan,
    SequenceInterval,
    build_coverage_page,
    count_missing_by_reason,
)


def _seg(page, index):
    return page.segments[index]


class TestBuildCoveragePageExamples:
    """The four E=20 examples from the TASK-0629 plan."""

    def test_no_signals_all_no_source(self) -> None:
        added = [SequenceInterval(3, 7), SequenceInterval(10, 17)]
        page = build_coverage_page(expected=20, added=added, reasons=[], view="missing")
        assert [(s.start, s.end, s.state) for s in page.segments] == [
            (1, 2, "no_source"),
            (8, 9, "no_source"),
            (18, 20, "no_source"),
        ]
        assert page.next_after_sequence_number is None

    def test_active_import_file_marks_in_progress(self) -> None:
        added = [SequenceInterval(3, 7), SequenceInterval(10, 17)]
        reasons = [
            ReasonSpan(SequenceInterval(8, 12), MissingReason.IMPORT_IN_PROGRESS),
        ]
        page = build_coverage_page(expected=20, added=added, reasons=reasons, view="missing")
        assert [(s.start, s.end, s.state) for s in page.segments] == [
            (1, 2, "no_source"),
            (8, 9, "import_in_progress"),
            (18, 20, "no_source"),
        ]

    def test_geometry_pending_does_not_undo_added(self) -> None:
        added = [SequenceInterval(1, 20)]
        reasons = [ReasonSpan(SequenceInterval(5, 5), MissingReason.WAITING_FOR_GEOMETRY)]
        page = build_coverage_page(expected=20, added=added, reasons=reasons, view="missing")
        assert page.segments == ()

    def test_partial_source_missing_with_reason(self) -> None:
        added = [SequenceInterval(1, 4), SequenceInterval(6, 20)]
        reasons = [ReasonSpan(SequenceInterval(5, 5), MissingReason.PARTIAL_SOURCE)]
        page = build_coverage_page(expected=20, added=added, reasons=reasons, view="missing")
        assert [(s.start, s.end, s.state) for s in page.segments] == [(5, 5, "partial_source")]


class TestReasonPriority:
    def test_import_in_progress_wins_over_waiting_for_geometry(self) -> None:
        reasons = [
            ReasonSpan(SequenceInterval(1, 10), MissingReason.WAITING_FOR_GEOMETRY),
            ReasonSpan(SequenceInterval(5, 5), MissingReason.IMPORT_IN_PROGRESS),
        ]
        page = build_coverage_page(expected=10, added=[], reasons=reasons, view="missing")
        assert [(s.start, s.end, s.state) for s in page.segments] == [
            (1, 4, "waiting_for_geometry"),
            (5, 5, "import_in_progress"),
            (6, 10, "waiting_for_geometry"),
        ]

    def test_full_priority_order(self) -> None:
        reasons = [
            ReasonSpan(SequenceInterval(n, n), reason)
            for n, reason in enumerate(
                [
                    MissingReason.UNKNOWN,
                    MissingReason.REJECTED,
                    MissingReason.FAILED,
                    MissingReason.PARTIAL_SOURCE,
                    MissingReason.WAITING_FOR_GEOMETRY,
                    MissingReason.IMPORT_IN_PROGRESS,
                ],
                start=1,
            )
        ]
        # Overlap all six spans onto number 1; highest priority (lowest enum
        # index) must win regardless of input order.
        overlapping = [ReasonSpan(SequenceInterval(1, 1), r.reason) for r in reasons]
        page = build_coverage_page(expected=1, added=[], reasons=overlapping, view="missing")
        assert _seg(page, 0).state == MissingReason.IMPORT_IN_PROGRESS.value


class TestMergingAndMetadata:
    def test_adjacent_same_reason_merges(self) -> None:
        reasons = [
            ReasonSpan(SequenceInterval(1, 3), MissingReason.FAILED, error_code="E1"),
            ReasonSpan(SequenceInterval(4, 6), MissingReason.FAILED, error_code="E1"),
        ]
        page = build_coverage_page(expected=6, added=[], reasons=reasons, view="missing")
        assert len(page.segments) == 1
        assert (_seg(page, 0).start, _seg(page, 0).end, _seg(page, 0).error_code) == (1, 6, "E1")

    def test_adjacent_same_reason_different_metadata_does_not_merge(self) -> None:
        reasons = [
            ReasonSpan(SequenceInterval(1, 3), MissingReason.FAILED, error_code="E1"),
            ReasonSpan(SequenceInterval(4, 6), MissingReason.FAILED, error_code="E2"),
        ]
        page = build_coverage_page(expected=6, added=[], reasons=reasons, view="missing")
        assert [(s.start, s.end, s.error_code) for s in page.segments] == [
            (1, 3, "E1"),
            (4, 6, "E2"),
        ]

    def test_import_job_id_travels_with_segment(self) -> None:
        job_id = UUID(int=7)
        reasons = [
            ReasonSpan(
                SequenceInterval(1, 5),
                MissingReason.IMPORT_IN_PROGRESS,
                import_job_id=job_id,
            )
        ]
        page = build_coverage_page(expected=5, added=[], reasons=reasons, view="missing")
        assert _seg(page, 0).import_job_id == job_id


class TestWindowAndCursor:
    def test_range_from_to_narrows_window(self) -> None:
        page = build_coverage_page(
            expected=100, added=[], reasons=[], view="missing", range_from=40, range_to=45
        )
        assert [(s.start, s.end) for s in page.segments] == [(40, 45)]

    def test_after_sequence_number_excludes_up_to_cursor(self) -> None:
        page = build_coverage_page(
            expected=10, added=[], reasons=[], view="missing", after_sequence_number=5
        )
        assert [(s.start, s.end) for s in page.segments] == [(6, 10)]

    def test_limit_plus_one_sets_next_cursor(self) -> None:
        added = [SequenceInterval(n, n) for n in range(1, 21, 2)]  # 1,3,5,...19 added
        page = build_coverage_page(expected=20, added=added, reasons=[], view="missing", limit=3)
        assert len(page.segments) == 3
        assert page.next_after_sequence_number == page.segments[-1].end

    def test_no_next_cursor_when_page_fits(self) -> None:
        page = build_coverage_page(expected=5, added=[], reasons=[], view="missing", limit=100)
        assert page.next_after_sequence_number is None

    def test_empty_window_returns_empty_page(self) -> None:
        page = build_coverage_page(
            expected=10, added=[], reasons=[], view="missing", after_sequence_number=10
        )
        assert page.segments == ()
        assert page.next_after_sequence_number is None


class TestEdgeCases:
    def test_expected_equals_one_missing(self) -> None:
        page = build_coverage_page(expected=1, added=[], reasons=[], view="missing")
        assert [(s.start, s.end, s.state) for s in page.segments] == [(1, 1, "no_source")]

    def test_expected_equals_one_added(self) -> None:
        page = build_coverage_page(
            expected=1, added=[SequenceInterval(1, 1)], reasons=[], view="missing"
        )
        assert page.segments == ()

    def test_all_missing_single_segment_when_no_data(self) -> None:
        # A single reasonless gap is one segment regardless of its size — the
        # 100-segment page limit caps row count, not numbers within a row.
        page = build_coverage_page(expected=500, added=[], reasons=[], view="missing")
        assert len(page.segments) == 1
        segment = _seg(page, 0)
        assert (segment.start, segment.end, segment.state) == (1, 500, "no_source")
        assert page.next_after_sequence_number is None

    def test_added_view_only_shows_added(self) -> None:
        added = [SequenceInterval(3, 7)]
        page = build_coverage_page(expected=10, added=added, reasons=[], view="added")
        assert [(s.start, s.end, s.state) for s in page.segments] == [(3, 7, "added")]

    def test_invalid_view_raises(self) -> None:
        with pytest.raises(ValueError):
            build_coverage_page(expected=10, added=[], reasons=[], view="all")

    def test_invalid_interval_raises(self) -> None:
        with pytest.raises(ValueError):
            SequenceInterval(5, 3)


class TestCountMissingByReason:
    def test_counts_sum_to_missing_total(self) -> None:
        added = [SequenceInterval(3, 7), SequenceInterval(10, 17)]
        reasons = [ReasonSpan(SequenceInterval(8, 9), MissingReason.IMPORT_IN_PROGRESS)]
        counts = count_missing_by_reason(expected=20, added=added, reasons=reasons)
        assert counts[MissingReason.IMPORT_IN_PROGRESS] == 2
        assert counts[MissingReason.NO_SOURCE] == 5  # 1-2 and 18-20
        assert sum(counts.values()) == 20 - (5 + 8)  # expected - added count

    def test_zero_when_everything_added(self) -> None:
        counts = count_missing_by_reason(
            expected=5, added=[SequenceInterval(1, 5)], reasons=[]
        )
        assert sum(counts.values()) == 0
