from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_worker.semi_automatic_selection.audit import (
    SemiAutomaticSelectionAudit,
)
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.engine import (
    MIDDLE_EXACT_SELECTOR_VERSION,
    RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES,
    RangeGroup,
    RangeGroupingAccumulator,
    grouping_policy_fingerprint,
    select_middle_exact_observation,
)

RUN_ID = UUID("8cc4aabe-2f65-42bd-b9e8-f64cb40b969e")


def _source(index: int) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=f"folder/photo-{index:04d}.jpg",
        size_bytes=index + 1,
        checksum_sha256=f"{index + 1:064x}",
    )


def _exact(
    index: int,
    expected_index: int,
    *,
    confidence: float = 0.95,
) -> RangeEvidenceResult:
    start = expected_index * 9 + 1
    return RangeEvidenceResult(
        source=_source(index),
        status=RangeEvidenceStatus.EXACT_RANGE,
        observed_range=SemiAutomaticSelectionRange(start=start, end=start + 8),
        expected_index=expected_index,
        confidence=confidence,
        reason_codes=("EXACT_LOCAL_RANGE_PROOF",),
    )


def _unreadable(index: int) -> RangeEvidenceResult:
    return RangeEvidenceResult(
        source=_source(index),
        status=RangeEvidenceStatus.RANGE_UNREADABLE,
        observed_range=None,
        expected_index=None,
        confidence=None,
        reason_codes=("RANGE_UNREADABLE",),
    )


def _finish(values: list[RangeEvidenceResult], *, maximum_gap: int = 160) -> tuple[RangeGroup, ...]:
    accumulator = RangeGroupingAccumulator(maximum_consecutive_unproven_sources=maximum_gap)
    groups: list[RangeGroup] = []
    for value in values:
        groups.extend(accumulator.consume(value))
    groups.extend(accumulator.finish())
    return tuple(groups)


def test_grouping_policy_fingerprint_covers_calibrated_policy() -> None:
    assert len(grouping_policy_fingerprint()) == 64
    assert RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES == 160


def test_many_equal_exact_observations_create_one_group() -> None:
    groups = _finish([_exact(index, 0) for index in range(6)])

    assert len(groups) == 1
    assert groups[0].first_source_index == 0
    assert groups[0].last_source_index == 5
    assert groups[0].exact_observation_count == 6


def test_a_b_a_ignores_isolated_range_observation() -> None:
    groups = _finish([_exact(0, 0), _exact(1, 1), _exact(2, 0)])

    assert [
        (group.expected_index, group.first_source_index, group.last_source_index)
        for group in groups
    ] == [(0, 0, 2)]
    assert groups[0].isolated_source_indexes == (1,)
    assert "ISOLATED_RANGE_OBSERVATION_IGNORED" in groups[0].reason_codes


def test_a_b_b_confirms_new_group() -> None:
    groups = _finish([_exact(0, 0), _exact(1, 1), _exact(2, 1)])

    assert [
        (group.expected_index, group.first_source_index, group.last_source_index)
        for group in groups
    ] == [(0, 0, 0), (1, 1, 2)]


def test_a_b_c_preserves_strong_b_as_singleton() -> None:
    groups = _finish([_exact(0, 0), _exact(1, 1), _exact(2, 2)])

    assert [
        (group.expected_index, group.first_source_index, group.last_source_index)
        for group in groups
    ] == [(0, 0, 0), (1, 1, 1), (2, 2, 2)]


def test_a_b_eof_preserves_b_as_singleton() -> None:
    groups = _finish([_exact(0, 0), _exact(1, 1)])

    assert [group.expected_index for group in groups] == [0, 1]


def test_duplicate_and_out_of_order_exact_groups_remain_auditable() -> None:
    duplicate = _finish(
        [
            _exact(0, 0),
            _exact(1, 0),
            _exact(2, 1),
            _exact(3, 1),
            _exact(4, 0),
            _exact(5, 0),
        ]
    )
    out_of_order = _finish([_exact(0, 1), _exact(1, 1), _exact(2, 0), _exact(3, 0)])

    assert [group.expected_index for group in duplicate] == [0, 1, 0]
    assert [group.expected_index for group in out_of_order] == [1, 0]


def test_unproven_gap_can_extend_but_never_open_a_group() -> None:
    groups = _finish(
        [_unreadable(0), _exact(1, 0), _unreadable(2), _unreadable(3)],
        maximum_gap=1,
    )

    assert len(groups) == 1
    assert (groups[0].first_source_index, groups[0].last_source_index) == (1, 2)


def test_middle_selector_uses_only_exact_proof_and_stable_ties() -> None:
    group = RangeGroup(
        group_order=0,
        expected_index=0,
        sequence_range=SemiAutomaticSelectionRange(1, 9),
        first_source_index=0,
        last_source_index=4,
        exact_observation_count=2,
    )
    selected = select_middle_exact_observation(
        group,
        [_exact(0, 0, confidence=0.91), _unreadable(2), _exact(4, 0, confidence=0.97)],
    )

    assert selected.evidence.source.source_index == 4
    assert selected.selection_method == MIDDLE_EXACT_SELECTOR_VERSION

    lower_index_wins = select_middle_exact_observation(
        replace_group(group, last_source_index=2),
        [_exact(0, 0), _unreadable(1), _exact(2, 0)],
    )
    assert lower_index_wins.evidence.source.source_index == 0


def replace_group(group: RangeGroup, *, last_source_index: int) -> RangeGroup:
    return RangeGroup(
        group_order=group.group_order,
        expected_index=group.expected_index,
        sequence_range=group.sequence_range,
        first_source_index=group.first_source_index,
        last_source_index=last_source_index,
        exact_observation_count=group.exact_observation_count,
    )


def test_middle_selector_rejects_group_without_exact_candidate() -> None:
    group = RangeGroup(
        group_order=0,
        expected_index=0,
        sequence_range=SemiAutomaticSelectionRange(1, 9),
        first_source_index=0,
        last_source_index=1,
        exact_observation_count=1,
    )

    with pytest.raises(SemiAutomaticSelectionError) as raised:
        select_middle_exact_observation(group, [_unreadable(0), _unreadable(1)])

    assert raised.value.code == "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT"


def test_checkpoint_resumes_open_transition_without_reprocessing_sources() -> None:
    first = RangeGroupingAccumulator()
    assert first.consume(_exact(0, 0)) == ()
    assert first.consume(_exact(1, 1)) == ()

    resumed = RangeGroupingAccumulator(checkpoint=first.checkpoint())
    emitted = resumed.consume(_exact(2, 1))

    assert resumed.next_source_index == 3
    assert [(group.expected_index, group.group_order) for group in emitted] == [(0, 0)]
    assert [group.expected_index for group in resumed.finish()] == [1]


def test_audit_reconciles_uncommitted_suffix_and_streams_middle_selection(
    tmp_path: Path,
) -> None:
    audit = SemiAutomaticSelectionAudit(tmp_path, RUN_ID)
    observations = [_exact(0, 0), _unreadable(1), _exact(2, 0)]
    group = _finish(observations)[0]
    for value in observations:
        audit.append_observation(value)
    audit.append_groups((group,))
    with audit.observations_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"sourceIndex": 3}) + "\n")

    audit.reconcile(observation_count=3, group_count=1)
    selection = tuple(audit.iter_group_selections())

    assert len(audit.observations_path.read_text(encoding="utf-8").splitlines()) == 3
    assert len(selection) == 1
    assert selection[0].evidence.source.source_index == 0


def test_audit_fails_closed_when_committed_jsonl_disappears(tmp_path: Path) -> None:
    audit = SemiAutomaticSelectionAudit(tmp_path, RUN_ID)

    with pytest.raises(SemiAutomaticSelectionError) as raised:
        audit.reconcile(observation_count=1, group_count=0)

    assert raised.value.code == "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID"
