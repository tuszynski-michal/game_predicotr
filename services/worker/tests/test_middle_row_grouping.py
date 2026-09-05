from __future__ import annotations

from collections.abc import Iterable

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    FinalizedMiddleRowGroup,
    MiddleRowGroupingAccumulator,
    select_middle_row_exact_observation,
)


def _source(index: int) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=f"photos/frame-{index:04d}.jpg",
        size_bytes=100 + index,
        checksum_sha256=f"{index + 1:064x}",
    )


def _exact(
    index: int,
    expected_index: int,
    *,
    readability: float = 10.0,
    confidence: float = 0.95,
) -> RangeEvidenceResult:
    start = expected_index * 9 + 1
    return RangeEvidenceResult(
        source=_source(index),
        status=RangeEvidenceStatus.EXACT_RANGE,
        observed_range=SemiAutomaticSelectionRange(start=start, end=start + 8),
        expected_index=expected_index,
        confidence=confidence,
        reason_codes=("MIDDLE_ROW_TRIPLE_EXACT",),
        local_readability_score=readability,
        minimum_ocr_confidence=confidence,
        observation_key=f"{index + 1:064x}",
    )


def _unknown(index: int) -> RangeEvidenceResult:
    return RangeEvidenceResult(
        source=_source(index),
        status=RangeEvidenceStatus.RANGE_UNREADABLE,
        observed_range=None,
        expected_index=None,
        confidence=None,
        reason_codes=("LOCAL_BLUR",),
        observation_key=f"{index + 1:064x}",
    )


def _finish(
    evidence: Iterable[RangeEvidenceResult],
    *,
    maximum_gap: int = 160,
) -> tuple[FinalizedMiddleRowGroup, ...]:
    accumulator = MiddleRowGroupingAccumulator(maximum_consecutive_unknown_sources=maximum_gap)
    finalized: list[FinalizedMiddleRowGroup] = []
    for item in evidence:
        finalized.extend(accumulator.consume(item))
    finalized.extend(accumulator.finish())
    return tuple(finalized)


def test_internal_unknown_bridges_the_same_exact_range_without_becoming_candidate() -> None:
    groups = _finish((_exact(0, 0), _unknown(1), _exact(2, 0)))

    assert len(groups) == 1
    result = groups[0]
    assert result.group.first_source_index == 0
    assert result.group.last_source_index == 2
    assert result.group.exact_observation_count == 2
    assert result.selection.evidence.source.source_index == 0
    assert result.selection.selection_method == MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION


def test_leading_and_trailing_unknown_do_not_extend_the_evidence_span() -> None:
    groups = _finish((_unknown(0), _unknown(1), _exact(2, 0), _unknown(3), _unknown(4)))

    assert len(groups) == 1
    result = groups[0]
    assert (result.group.first_source_index, result.group.last_source_index) == (2, 2)
    assert result.selection.evidence.source.source_index == 2


def test_unknown_between_two_ranges_is_not_assigned_to_either_boundary() -> None:
    groups = _finish((_exact(0, 0), _unknown(1), _exact(2, 1)))

    assert [
        (item.group.expected_index, item.group.first_source_index, item.group.last_source_index)
        for item in groups
    ] == [
        (0, 0, 0),
        (1, 2, 2),
    ]


def test_several_internal_unknowns_bridge_only_within_the_pinned_limit() -> None:
    bridged = _finish(
        (_exact(0, 0), _unknown(1), _unknown(2), _unknown(3), _exact(4, 0)),
        maximum_gap=3,
    )
    split = _finish(
        (_exact(0, 0), _unknown(1), _unknown(2), _unknown(3), _unknown(4), _exact(5, 0)),
        maximum_gap=3,
    )

    assert len(bridged) == 1
    assert [(item.group.first_source_index, item.group.last_source_index) for item in split] == [
        (0, 0),
        (5, 5),
    ]


def test_repeated_and_out_of_order_ranges_remain_distinct_auditable_groups() -> None:
    groups = _finish(
        (
            _exact(0, 1),
            _exact(1, 1),
            _exact(2, 0),
            _exact(3, 0),
            _exact(4, 1),
        )
    )

    assert [item.group.expected_index for item in groups] == [1, 0, 1]
    assert [item.group.group_order for item in groups] == [0, 1, 2]


def test_evidence_span_midpoint_uses_quality_only_as_a_tie_break() -> None:
    groups = _finish(
        (
            _exact(0, 0, readability=100, confidence=0.99),
            _unknown(1),
            _exact(2, 0, readability=1, confidence=0.90),
            _unknown(3),
            _exact(4, 0, readability=1000, confidence=1.0),
        )
    )

    assert groups[0].selection.evidence.source.source_index == 2


def test_even_exact_candidates_prefer_readability_then_confidence_then_lower_index() -> None:
    readability_wins = _finish(
        (
            _exact(0, 0, readability=10, confidence=0.99),
            _exact(1, 0, readability=20, confidence=0.90),
        )
    )[0]
    confidence_wins = _finish(
        (
            _exact(0, 0, readability=20, confidence=0.94),
            _exact(1, 0, readability=20, confidence=0.96),
        )
    )[0]
    index_wins = _finish(
        (
            _exact(0, 0, readability=20, confidence=0.95),
            _exact(1, 0, readability=20, confidence=0.95),
        )
    )[0]

    assert readability_wins.selection.evidence.source.source_index == 1
    assert confidence_wins.selection.evidence.source.source_index == 1
    assert index_wins.selection.evidence.source.source_index == 0


def test_one_exact_candidate_is_valid() -> None:
    result = _finish((_exact(0, 0),))[0]

    assert result.selection.evidence.source.source_index == 0


def test_grouping_checkpoint_resumes_with_identical_candidate_and_no_reprocessing() -> None:
    first = MiddleRowGroupingAccumulator(maximum_consecutive_unknown_sources=3)
    first.consume(_exact(0, 0, readability=12, confidence=0.93))
    first.consume(_unknown(1))

    resumed = MiddleRowGroupingAccumulator(
        maximum_consecutive_unknown_sources=3,
        checkpoint=first.checkpoint(),
    )
    resumed.consume(_exact(2, 0, readability=30, confidence=0.96))
    result = resumed.finish()[0]

    uninterrupted = _finish(
        (
            _exact(0, 0, readability=12, confidence=0.93),
            _unknown(1),
            _exact(2, 0, readability=30, confidence=0.96),
        ),
        maximum_gap=3,
    )[0]
    assert result.group == uninterrupted.group
    assert result.selection.evidence == uninterrupted.selection.evidence

    with pytest.raises(SemiAutomaticSelectionError) as repeated:
        resumed.consume(_exact(2, 0))
    assert repeated.value.code == "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID"


def test_selector_rejects_unknown_only_input() -> None:
    result = _finish((_exact(0, 0),))[0]

    with pytest.raises(SemiAutomaticSelectionError) as raised:
        select_middle_row_exact_observation(result.group, (_unknown(0),))
    assert raised.value.code == "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT"
