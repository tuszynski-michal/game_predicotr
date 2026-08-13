from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
)
from game_predictor_worker.images.selection.recovery import (
    RecoveredBlock,
    RecoverySourceGroup,
    assemble_recovery_projection,
    plan_recovery_blocks,
    prepare_recovery_block,
    restore_recovered_block,
)

QUALITY = ImageQualityMetrics(*(0.8 for _ in range(8)))


def _source(order: int, checksum_digit: str | None = None) -> ImageSelectionSource:
    checksum = (checksum_digit or format(order % 16, "x")) * 64
    return ImageSelectionSource(
        order_index=order,
        relative_path=f"{order:06d}.jpg",
        stored_relative_path=f"files/{order:06d}.jpg",
        checksum_sha256=checksum,
        size_bytes=100 + order,
    )


def _candidate(source: ImageSelectionSource) -> CandidateResult:
    return CandidateResult(
        source=source,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=QUALITY,
        recognized_range=None,
        reason_codes=(),
        width=100,
        height=100,
    )


def _group(
    order: int,
    status: SelectionGroupStatus,
    sources: tuple[ImageSelectionSource, ...],
) -> RecoverySourceGroup:
    selected = None if not sources else _candidate(sources[0])
    return RecoverySourceGroup(
        origin_group_id=UUID(int=order + 1),
        result=SelectionGroupResult(
            group_order=order,
            source_count=max(1, len(sources)),
            range=None,
            fingerprint_sha256=format(order % 16, "x") * 64,
            board_count_consensus=9,
            status=status,
            selected_candidate=selected,
            top_candidates=() if selected is None else (selected,),
        ),
        sources=sources,
    )


def _observation(source: ImageSelectionSource) -> CheapImageObservation:
    return CheapImageObservation(
        source=source,
        width=100,
        height=100,
        fingerprint_hex="a" * 16,
        geometry_signature=(0.1,),
        board_count=9,
        geometry_confidence=0.9,
        quality=QUALITY,
    )


def test_problem_spans_expand_by_two_auto_guards_and_merge_overlaps() -> None:
    statuses = (
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.AUTO_SELECTED,
    )
    groups = tuple(
        _group(index, status, (_source(index),))
        for index, status in enumerate(statuses)
    )

    blocks = plan_recovery_blocks(groups)

    assert len(blocks) == 1
    assert blocks[0].first_group_index == 0
    assert blocks[0].last_group_index == 6


def test_user_decision_is_a_hard_recovery_boundary() -> None:
    statuses = (
        SelectionGroupStatus.MANUALLY_SELECTED,
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.RANGE_CONFIRMED,
    )
    groups = tuple(
        _group(index, status, (_source(index),))
        for index, status in enumerate(statuses)
    )

    (block,) = plan_recovery_blocks(groups)

    assert block.first_group_index == 1
    assert block.last_group_index == 2


def test_block_input_deduplicates_checksum_and_restores_global_sources() -> None:
    duplicate = _source(11, "a")
    groups = (
        _group(0, SelectionGroupStatus.RANGE_REQUIRED, (_source(10, "a"), duplicate)),
        _group(1, SelectionGroupStatus.RANGE_REQUIRED, (_source(12, "c"),)),
    )
    block = plan_recovery_blocks(groups)[0]
    block_input = prepare_recovery_block(block)
    assert [source.order_index for source in block_input.sources] == [0, 1]
    assert [source.order_index for source in block_input.original_sources] == [10, 12]

    local_candidates = tuple(_candidate(source) for source in block_input.sources)
    local_groups = (
        replace(
            groups[0].result,
            group_order=0,
            source_count=1,
            selected_candidate=local_candidates[0],
            top_candidates=(local_candidates[0],),
        ),
        replace(
            groups[1].result,
            group_order=1,
            source_count=1,
            selected_candidate=local_candidates[1],
            top_candidates=(local_candidates[1],),
        ),
    )
    restored = restore_recovered_block(
        block=block,
        block_input=block_input,
        groups=local_groups,
        observations=tuple(_observation(source) for source in block_input.sources),
    )

    assert [
        group.selected_candidate.source.order_index
        for group in restored.groups
        if group.selected_candidate
    ] == [10, 12]
    assert [item[0].source.order_index for item in restored.group_sources] == [10, 12]
    assert len(set(restored.origin_group_ids)) == 2


def test_projection_replaces_only_recovery_interval_and_keeps_provenance() -> None:
    source_groups = (
        _group(0, SelectionGroupStatus.MANUALLY_SELECTED, (_source(0),)),
        _group(1, SelectionGroupStatus.RANGE_REQUIRED, (_source(1),)),
        _group(2, SelectionGroupStatus.AUTO_SELECTED, (_source(2),)),
    )
    block = plan_recovery_blocks(source_groups)[0]
    recovered_group = replace(
        source_groups[1].result,
        group_order=0,
        status=SelectionGroupStatus.AUTO_SELECTED,
    )
    recovered = RecoveredBlock(
        block=block,
        groups=(recovered_group,),
        group_sources=((_observation(_source(1)), _observation(_source(2))),),
        origin_group_ids=(source_groups[1].origin_group_id,),
    )

    projection = assemble_recovery_projection(source_groups, (recovered,))

    assert [group.group_order for group in projection.groups] == [0, 1]
    assert projection.groups[0].status is SelectionGroupStatus.MANUALLY_SELECTED
    assert projection.groups[1].status is SelectionGroupStatus.AUTO_SELECTED
    assert projection.origin_group_ids == {
        0: source_groups[0].origin_group_id,
        1: source_groups[1].origin_group_id,
    }
    assert set(projection.group_sources) == {1}
