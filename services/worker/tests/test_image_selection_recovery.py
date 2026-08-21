from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    RangeLabelObservation,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.recovery import (
    RecoveredBlock,
    RecoverySourceGroup,
    assemble_recovery_projection,
    plan_recovery_blocks,
    prepare_recovery_block,
    prepare_source_groups_for_bounds,
    reconcile_projection_to_sequence_bounds,
    require_representative_range_evidence,
    restore_recovered_block,
)
from game_predictor_worker.images.selection.sequence_bounds import (
    SequenceBounds,
    parse_sequence_bounds_display_name,
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


def _group_with_range(
    order: int,
    status: SelectionGroupStatus,
    recognized_range: SequenceRange,
) -> RecoverySourceGroup:
    source_group = _group(order, status, (_source(order),))
    assert source_group.result.selected_candidate is not None
    selected = replace(
        source_group.result.selected_candidate,
        recognized_range=recognized_range,
    )
    return replace(
        source_group,
        result=replace(
            source_group.result,
            range=recognized_range,
            selected_candidate=selected,
            top_candidates=(selected,),
        ),
    )


def _proof_group(
    order: int,
    recognized_range: SequenceRange,
    *reasons: str,
) -> RecoverySourceGroup:
    source_group = _group_with_range(
        order,
        SelectionGroupStatus.AUTO_SELECTED,
        recognized_range,
    )
    assert source_group.result.selected_candidate is not None
    selected = replace(
        source_group.result.selected_candidate,
        recognized_range=recognized_range,
        reason_codes=reasons,
        range_label_observations=tuple(
            RangeLabelObservation(
                position,
                recognized_range.start + position,
                0.96,
                "layout_anchored",
            )
            for position in (0, 1, 4)
        ),
    )
    return replace(
        source_group,
        result=replace(
            source_group.result,
            selected_candidate=selected,
            top_candidates=(selected,),
        ),
    )


def _expected_sequence_review_group(
    order: int,
    recognized_range: SequenceRange,
    observations: tuple[RangeLabelObservation, ...],
    *,
    board_count: int = 6,
) -> RecoverySourceGroup:
    source_group = _group_with_range(
        order,
        SelectionGroupStatus.RANGE_REQUIRED,
        recognized_range,
    )
    assert source_group.result.selected_candidate is not None
    selected = replace(
        source_group.result.selected_candidate,
        reason_codes=(
            "RANGE_OCR_FUZZY_CANDIDATE",
            "RANGE_OCR_LAYOUT_ANCHORED_TWO_LABEL",
        ),
        range_label_observations=observations,
    )
    return replace(
        source_group,
        result=replace(
            source_group.result,
            board_count_consensus=board_count,
            selected_candidate=selected,
            top_candidates=(selected,),
        ),
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
        _group(index, status, (_source(index),)) for index, status in enumerate(statuses)
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
        _group(index, status, (_source(index),)) for index, status in enumerate(statuses)
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


def test_projection_reconciles_duplicate_ranges_across_independent_blocks() -> None:
    recognized_range = SequenceRange(100, 108, 0.96)
    source_groups = (
        _group_with_range(0, SelectionGroupStatus.AUTO_SELECTED, recognized_range),
        _group_with_range(1, SelectionGroupStatus.AUTO_SELECTED, recognized_range),
    )

    projection = assemble_recovery_projection(source_groups, ())

    assert projection.groups[0].status is SelectionGroupStatus.AUTO_SELECTED
    assert projection.groups[1].status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    assert projection.groups[1].duplicate_of_group_order == 0
    assert projection.groups[1].selected_candidate is None
    assert projection.groups[1].top_candidates == ()


def test_projection_keeps_owner_decision_when_duplicate_range_precedes_it() -> None:
    recognized_range = SequenceRange(100, 108, 0.96)
    source_groups = (
        _group_with_range(0, SelectionGroupStatus.AUTO_SELECTED, recognized_range),
        _group_with_range(1, SelectionGroupStatus.RANGE_CONFIRMED, recognized_range),
    )

    projection = assemble_recovery_projection(source_groups, ())

    assert projection.groups[0].status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    assert projection.groups[0].duplicate_of_group_order == 1
    assert projection.groups[1].status is SelectionGroupStatus.RANGE_CONFIRMED


def test_projection_keeps_two_conflicting_owner_decisions_fail_closed() -> None:
    recognized_range = SequenceRange(100, 108, 0.96)
    source_groups = (
        _group_with_range(0, SelectionGroupStatus.MANUALLY_SELECTED, recognized_range),
        _group_with_range(1, SelectionGroupStatus.RANGE_CONFIRMED, recognized_range),
    )

    projection = assemble_recovery_projection(source_groups, ())

    assert projection.groups[0].status is SelectionGroupStatus.MANUALLY_SELECTED
    assert projection.groups[1].status is SelectionGroupStatus.RANGE_CONFIRMED
    assert projection.groups[0].duplicate_of_group_order is None
    assert projection.groups[1].duplicate_of_group_order is None


def test_recovery_demotes_range_inferred_without_representative_ocr() -> None:
    inferred_range = SequenceRange(10, 18, 0.9)
    selected = replace(
        _candidate(_source(10)),
        recognized_range=inferred_range,
        reason_codes=("RANGE_INFERRED_FROM_BOUNDED_GAP",),
    )
    group = SelectionGroupResult(
        group_order=0,
        source_count=1,
        range=inferred_range,
        fingerprint_sha256="a" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.AUTO_SELECTED,
        selected_candidate=selected,
        top_candidates=(selected,),
    )

    (recovered,) = require_representative_range_evidence((group,))

    assert recovered.status is SelectionGroupStatus.RANGE_REQUIRED
    assert recovered.range is None
    assert recovered.selected_candidate is not None
    assert recovered.selected_candidate.decision is CandidateDecision.ELIGIBLE
    assert recovered.selected_candidate.recognized_range is None


def test_recovery_keeps_exact_ocr_backed_representative() -> None:
    recognized_range = SequenceRange(100, 108, 0.96)
    selected = replace(
        _candidate(_source(10)),
        recognized_range=recognized_range,
        reason_codes=("RANGE_OCR_EXACT",),
    )
    group = SelectionGroupResult(
        group_order=0,
        source_count=1,
        range=recognized_range,
        fingerprint_sha256="a" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.AUTO_SELECTED,
        selected_candidate=selected,
        top_candidates=(selected,),
    )

    assert require_representative_range_evidence((group,)) == (group,)


def test_sequence_bounds_count_inclusive_groups_and_keep_partial_tail() -> None:
    bounds = SequenceBounds(229_913, 248_184)

    assert bounds.sequence_count == 18_272
    assert bounds.expected_group_count == 2_031
    assert bounds.range_for_group(0) == SequenceRange(229_913, 229_921, 1.0)
    assert bounds.range_for_group(2_030) == SequenceRange(248_183, 248_184, 1.0)
    assert (
        parse_sequence_bounds_display_name(
            "229913 - 248184",
            first_sequence_number=229_913,
            direction="ascending",
        )
        == bounds
    )


def test_cardinality_plan_restores_over_rejected_group_and_rebuilds_wrong_grid() -> None:
    bounds = SequenceBounds(1, 27)
    groups = (
        _group_with_range(0, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(1, 9, 0.9)),
        _group_with_range(
            1,
            SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
            SequenceRange(1, 9, 0.9),
        ),
        _group_with_range(
            2,
            SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
            SequenceRange(10, 18, 0.9),
        ),
        _group_with_range(3, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(11, 19, 0.9)),
    )

    prepared = prepare_source_groups_for_bounds(groups, bounds=bounds)

    assert [group.result.status for group in prepared] == [
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.RANGE_REQUIRED,
    ]


def test_cardinality_projection_has_exact_continuous_owner_grid() -> None:
    bounds = SequenceBounds(1, 27)
    groups = (
        _group_with_range(0, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(1, 9, 0.9)),
        _group_with_range(1, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(1, 9, 0.9)),
        _group(2, SelectionGroupStatus.RANGE_REQUIRED, (_source(2),)),
        _group_with_range(3, SelectionGroupStatus.AUTO_SELECTED, SequenceRange(19, 27, 0.9)),
    )
    projection = assemble_recovery_projection(groups, (), reconcile_duplicates=False)

    reconciled = reconcile_projection_to_sequence_bounds(projection, bounds=bounds)

    owners = tuple(
        group
        for group in reconciled.groups
        if group.status is not SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    )
    assert len(owners) == 3
    assert [(group.range.start, group.range.end) for group in owners if group.range] == [
        (1, 9),
        (10, 18),
        (19, 27),
    ]
    assert [group.status for group in owners] == [
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.MANUAL_REQUIRED,
        SelectionGroupStatus.AUTO_SELECTED,
    ]
    assert (
        sum(
            group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
            for group in reconciled.groups
        )
        == 1
    )


def test_cardinality_projection_never_overwrites_conflicting_candidate_range() -> None:
    wrong = replace(
        _candidate(_source(0)),
        recognized_range=SequenceRange(10, 18, 0.99),
    )
    unknown = _candidate(_source(1))
    source_group = _group(0, SelectionGroupStatus.RANGE_REQUIRED, (_source(0), _source(1)))
    source_group = replace(
        source_group,
        result=replace(
            source_group.result,
            selected_candidate=wrong,
            top_candidates=(wrong, unknown),
        ),
    )
    projection = assemble_recovery_projection(
        (source_group,),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 9),
    )

    selected = reconciled.groups[0].selected_candidate
    assert selected is not None
    assert selected.source.order_index == 1
    assert selected.recognized_range == SequenceRange(1, 9, 1.0)


def test_cardinality_projection_preserves_complete_user_decision() -> None:
    decided_range = SequenceRange(1, 9, 0.77)
    source_group = _group_with_range(
        0,
        SelectionGroupStatus.MANUALLY_SELECTED,
        decided_range,
    )
    projection = assemble_recovery_projection(
        (source_group,),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 9),
    )

    assert reconciled.groups[0] == source_group.result


def test_proof_first_projection_never_promotes_unknown_or_cardinality_range() -> None:
    unknown = _group(0, SelectionGroupStatus.RANGE_REQUIRED, (_source(0),))
    inferred = _proof_group(
        1,
        SequenceRange(10, 18, 1.0),
        "RANGE_CARDINALITY_INFERRED",
    )
    projection = assemble_recovery_projection(
        (unknown, inferred),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
    )

    assert all(
        group.status is SelectionGroupStatus.RANGE_REQUIRED and group.range is None
        for group in reconciled.groups
    )
    assert all(
        group.selected_candidate is not None
        and group.selected_candidate.decision is CandidateDecision.ELIGIBLE
        for group in reconciled.groups
    )


def test_proof_first_projection_keeps_only_strong_local_range_and_deduplicates_it() -> None:
    first = _proof_group(
        0,
        SequenceRange(1, 9, 0.94),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    duplicate = _proof_group(
        1,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LABEL_LATTICE_WINDOW",
    )
    projection = assemble_recovery_projection(
        (first, duplicate),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 9),
        require_local_range_proof=True,
    )

    assert reconciled.groups[0].status is SelectionGroupStatus.AUTO_SELECTED
    assert reconciled.groups[0].range == SequenceRange(1, 9, 0.94)
    assert reconciled.groups[1].status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    assert reconciled.groups[1].duplicate_of_group_order == 0


def test_proof_first_projection_rejects_two_labels_and_shifted_range() -> None:
    two_labels = _proof_group(
        0,
        SequenceRange(1, 9, 0.99),
        "RANGE_OCR_FUZZY_CANDIDATE",
        "RANGE_OCR_LABEL_LATTICE_TWO_LABEL",
    )
    shifted = _proof_group(
        1,
        SequenceRange(2, 10, 0.99),
        "RANGE_OCR_LAYOUT_ANCHORED_FOUR_LABEL",
    )
    projection = assemble_recovery_projection(
        (two_labels, shifted),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
    )

    assert all(
        group.status is SelectionGroupStatus.RANGE_REQUIRED and group.range is None
        for group in reconciled.groups
    )


def test_proof_first_projection_rejects_one_mutated_position_label() -> None:
    source_group = _proof_group(
        0,
        SequenceRange(1, 9, 0.99),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    assert source_group.result.selected_candidate is not None
    selected = replace(
        source_group.result.selected_candidate,
        range_label_observations=(
            RangeLabelObservation(0, 1, 0.96, "layout_anchored"),
            RangeLabelObservation(1, 2, 0.95, "layout_anchored"),
            RangeLabelObservation(4, 6, 0.94, "layout_anchored"),
        ),
    )
    projection = assemble_recovery_projection(
        (
            replace(
                source_group,
                result=replace(
                    source_group.result,
                    selected_candidate=selected,
                    top_candidates=(selected,),
                ),
            ),
        ),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 9),
        require_local_range_proof=True,
    )

    assert reconciled.groups[0].status is SelectionGroupStatus.RANGE_REQUIRED
    assert reconciled.groups[0].range is None


def test_proof_first_projection_promotes_two_labels_matching_expected_sequence() -> None:
    anchor = _proof_group(
        0,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    expected = _expected_sequence_review_group(
        1,
        SequenceRange(10, 18, 0.88),
        (
            RangeLabelObservation(1, 11, 0.93, "layout_anchored"),
            RangeLabelObservation(5, 15, 0.91, "layout_anchored"),
        ),
    )
    projection = assemble_recovery_projection(
        (anchor, expected),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    promoted = reconciled.groups[1]
    assert promoted.status is SelectionGroupStatus.AUTO_SELECTED
    assert promoted.range == SequenceRange(10, 18, 0.9)
    assert promoted.selected_candidate is not None
    assert "RANGE_EXPECTED_SEQUENCE_CONFIRMED" in promoted.selected_candidate.reason_codes


def test_sequence_confirmation_marks_surplus_fragment_as_existing_range() -> None:
    first = _proof_group(
        0,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    surplus = _group(1, SelectionGroupStatus.RANGE_REQUIRED, (_source(1),))
    second = _proof_group(
        2,
        SequenceRange(10, 18, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    projection = assemble_recovery_projection(
        (first, surplus, second),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    assert [group.status for group in reconciled.groups] == [
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        SelectionGroupStatus.AUTO_SELECTED,
    ]
    assert reconciled.groups[1].range == SequenceRange(1, 9, 1.0)
    assert reconciled.groups[1].duplicate_of_group_order == 0
    assert reconciled.groups[1].selected_candidate is None
    assert reconciled.groups[1].top_candidates == ()


def test_sequence_confirmation_preserves_engine_linked_transition_fragment() -> None:
    first = _proof_group(
        0,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    fragment = _group_with_range(
        1,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        SequenceRange(10, 18, 0.96),
    )
    fragment = replace(
        fragment,
        result=replace(
            fragment.result,
            selected_candidate=None,
            top_candidates=(),
            duplicate_of_group_order=2,
        ),
    )
    owner = _proof_group(
        2,
        SequenceRange(10, 18, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    projection = assemble_recovery_projection(
        (first, fragment, owner),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    assert [group.status for group in reconciled.groups] == [
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
        SelectionGroupStatus.AUTO_SELECTED,
    ]
    assert reconciled.groups[1].range is not None
    assert (reconciled.groups[1].range.start, reconciled.groups[1].range.end) == (10, 18)
    assert reconciled.groups[1].duplicate_of_group_order == 2


def test_sequence_confirmation_demotes_automatic_ranges_with_conflicting_slot_order() -> None:
    groups = (
        _proof_group(
            0,
            SequenceRange(1, 9, 0.96),
            "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
        ),
        _proof_group(
            1,
            SequenceRange(19, 27, 0.96),
            "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
        ),
        _proof_group(
            2,
            SequenceRange(10, 18, 0.96),
            "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
        ),
        _group(3, SelectionGroupStatus.RANGE_REQUIRED, (_source(3),)),
    )
    projection = assemble_recovery_projection(
        groups,
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 27),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    assert [group.status for group in reconciled.groups] == [
        SelectionGroupStatus.AUTO_SELECTED,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.RANGE_REQUIRED,
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
    ]
    assert reconciled.groups[0].range == SequenceRange(1, 9, 0.96)
    assert reconciled.groups[1].range is None
    assert reconciled.groups[2].range is None
    assert reconciled.groups[1].selected_candidate is not None
    assert reconciled.groups[2].selected_candidate is not None


def test_proof_first_projection_keeps_off_by_one_label_in_range_review() -> None:
    anchor = _proof_group(
        0,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    conflicting = _expected_sequence_review_group(
        1,
        SequenceRange(10, 18, 0.88),
        (
            RangeLabelObservation(1, 11, 0.93, "layout_anchored"),
            RangeLabelObservation(5, 16, 0.91, "layout_anchored"),
        ),
    )
    projection = assemble_recovery_projection(
        (anchor, conflicting),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    assert reconciled.groups[1].status is SelectionGroupStatus.RANGE_REQUIRED
    assert reconciled.groups[1].range is None


def test_proof_first_projection_keeps_single_expected_label_in_range_review() -> None:
    anchor = _proof_group(
        0,
        SequenceRange(1, 9, 0.96),
        "RANGE_OCR_LAYOUT_ANCHORED_THREE_LABEL",
    )
    unclear = _expected_sequence_review_group(
        1,
        SequenceRange(10, 18, 0.88),
        (RangeLabelObservation(4, 14, 0.94, "layout_anchored"),),
    )
    projection = assemble_recovery_projection(
        (anchor, unclear),
        (),
        reconcile_duplicates=False,
    )

    reconciled = reconcile_projection_to_sequence_bounds(
        projection,
        bounds=SequenceBounds(1, 18),
        require_local_range_proof=True,
        allow_expected_sequence_confirmation=True,
    )

    assert reconciled.groups[1].status is SelectionGroupStatus.RANGE_REQUIRED
    assert reconciled.groups[1].range is None


def test_sequence_bounds_finds_complete_and_partial_group_in_constant_time() -> None:
    ascending = SequenceBounds(1, 14)
    descending = SequenceBounds(18, 5, "descending")

    assert ascending.group_index_for_range(SequenceRange(1, 9, 1.0)) == 0
    assert ascending.group_index_for_range(SequenceRange(10, 14, 1.0)) == 1
    assert ascending.group_index_for_range(SequenceRange(11, 14, 1.0)) is None
    assert descending.group_index_for_range(SequenceRange(10, 18, 1.0)) == 0
    assert descending.group_index_for_range(SequenceRange(5, 9, 1.0)) == 1
