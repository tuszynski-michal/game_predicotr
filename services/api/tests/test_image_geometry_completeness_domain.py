from __future__ import annotations

import math
from uuid import UUID

import pytest
from game_predictor_api.domain.image_geometry_completeness import (
    INCOMPLETE_IMAGE_STATES,
    SOURCE_IMAGE_GEOMETRY_INCOMPLETE,
    GeometryImageCursor,
    GeometryImageState,
    GeometryPositionFacts,
    GeometryPositionState,
    LowQualityThresholds,
    SourceImageGeometryStatus,
    classify_image,
    classify_position,
    decode_geometry_image_cursor,
    encode_geometry_image_cursor,
    expected_sequence_number,
    extract_position_quad,
    geometry_gate_withholds_board,
    is_admitted_status,
    persisted_status_for,
    recomputed_status,
    require_geometry_exception_reason,
)
from game_predictor_api.domain.image_reviews import ImageReviewError

OK = GeometryPositionState.OK
UNCERTAIN = GeometryPositionState.UNCERTAIN
PARTIAL = GeometryPositionState.PARTIAL
MISSING = GeometryPositionState.MISSING
DEFERRED = GeometryPositionState.DEFERRED
SUPERSEDED = GeometryPositionState.SUPERSEDED


def _board(
    *,
    completeness: str = "complete",
    approved: bool = False,
    accepted: bool = False,
) -> GeometryPositionFacts:
    return GeometryPositionFacts(
        position_index=0,
        board_exists=True,
        completeness_status=completeness,
        geometry_approved=approved,
        source_revision_accepted=accepted,
    )


def test_missing_board_without_pending_row_is_missing() -> None:
    result = classify_position(GeometryPositionFacts(position_index=3, board_exists=False))

    assert result.state is MISSING
    assert result.reason_code is None


def test_missing_board_with_open_pending_row_is_deferred_with_its_reason() -> None:
    result = classify_position(
        GeometryPositionFacts(
            position_index=3, board_exists=False, deferred_reason_code="residual_too_high"
        )
    )

    assert result.state is DEFERRED
    assert result.reason_code == "residual_too_high"


def test_deferred_needs_a_missing_board_so_pending_row_of_existing_board_is_ignored() -> None:
    facts = GeometryPositionFacts(
        position_index=0,
        board_exists=True,
        completeness_status="complete",
        source_revision_accepted=True,
        deferred_reason_code="incomplete_lattice",
    )

    assert classify_position(facts).state is OK


def test_partial_board_is_partial_even_when_approved_or_accepted() -> None:
    assert classify_position(_board(completeness="pending_partial")).state is PARTIAL
    assert (
        classify_position(
            _board(completeness="pending_partial", approved=True, accepted=True)
        ).state
        is PARTIAL
    )


@pytest.mark.parametrize(
    ("approved", "accepted", "expected"),
    [
        (True, True, OK),
        (True, False, OK),
        (False, True, OK),
        (False, False, UNCERTAIN),
    ],
)
def test_complete_board_is_ok_only_when_approved_or_source_revision_accepted(
    approved: bool, accepted: bool, expected: GeometryPositionState
) -> None:
    assert classify_position(_board(approved=approved, accepted=accepted)).state is expected


def test_unknown_completeness_status_is_never_ok() -> None:
    assert (
        classify_position(_board(completeness="something_else", approved=True, accepted=True)).state
        is UNCERTAIN
    )


def test_position_without_a_live_board_and_a_live_sequence_elsewhere_is_superseded() -> None:
    # a ``rejected`` board is not a live board, so the repository passes board_exists=False
    result = classify_position(
        GeometryPositionFacts(position_index=2, board_exists=False, sequence_live_elsewhere=True)
    )

    assert result.state is SUPERSEDED
    assert result.reason_code is None


def test_position_without_a_live_board_and_without_a_live_sequence_elsewhere_is_missing() -> None:
    result = classify_position(
        GeometryPositionFacts(position_index=2, board_exists=False, sequence_live_elsewhere=False)
    )

    assert result.state is MISSING


def test_superseded_outranks_an_open_pending_row() -> None:
    result = classify_position(
        GeometryPositionFacts(
            position_index=2,
            board_exists=False,
            deferred_reason_code="residual_too_high",
            sequence_live_elsewhere=True,
        )
    )

    assert result.state is SUPERSEDED
    assert result.reason_code is None


def test_a_live_board_is_classified_by_its_geometry_whatever_exists_elsewhere() -> None:
    facts = GeometryPositionFacts(
        position_index=0,
        board_exists=True,
        completeness_status="complete",
        source_revision_accepted=True,
        sequence_live_elsewhere=True,
    )

    assert classify_position(facts).state is OK


def test_nine_ok_positions_make_a_complete_image() -> None:
    assert classify_image([OK] * 9, has_source_geometry=True) is GeometryImageState.COMPLETE


def test_four_ok_positions_of_a_four_board_range_make_a_complete_image() -> None:
    assert classify_image([OK] * 4, has_source_geometry=True) is GeometryImageState.COMPLETE


def test_eight_ok_and_one_deferred_is_incomplete_missing() -> None:
    assert (
        classify_image([OK] * 8 + [DEFERRED], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_MISSING
    )


def test_eight_ok_and_one_missing_is_incomplete_missing() -> None:
    assert (
        classify_image([OK] * 8 + [MISSING], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_MISSING
    )


def test_eight_ok_and_one_partial_is_incomplete_partial() -> None:
    assert (
        classify_image([OK] * 8 + [PARTIAL], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_PARTIAL
    )


def test_eight_ok_and_one_uncertain_is_incomplete_uncertain() -> None:
    assert (
        classify_image([OK] * 8 + [UNCERTAIN], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_UNCERTAIN
    )


def test_missing_outranks_partial_which_outranks_uncertain() -> None:
    assert (
        classify_image([PARTIAL, UNCERTAIN, MISSING, OK], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_MISSING
    )
    assert (
        classify_image([UNCERTAIN, PARTIAL, OK], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_PARTIAL
    )


def test_image_without_source_geometry_has_its_own_state() -> None:
    assert classify_image([], has_source_geometry=False) is GeometryImageState.NO_SOURCE_GEOMETRY


def test_image_with_every_position_superseded_is_superseded() -> None:
    assert (
        classify_image([SUPERSEDED] * 9, has_source_geometry=True, has_live_boards=False)
        is GeometryImageState.SUPERSEDED
    )
    assert (
        classify_image([SUPERSEDED] * 4, has_source_geometry=True, has_live_boards=False)
        is GeometryImageState.SUPERSEDED
    )


def test_seven_ok_and_two_superseded_positions_make_a_complete_image() -> None:
    assert (
        classify_image([OK] * 7 + [SUPERSEDED] * 2, has_source_geometry=True)
        is GeometryImageState.COMPLETE
    )


def test_seven_ok_one_superseded_and_one_missing_is_incomplete_missing() -> None:
    assert (
        classify_image([OK] * 7 + [SUPERSEDED, MISSING], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_MISSING
    )


def test_superseded_positions_are_skipped_by_the_partial_and_uncertain_states() -> None:
    assert (
        classify_image([OK] * 6 + [SUPERSEDED, SUPERSEDED, PARTIAL], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_PARTIAL
    )
    assert (
        classify_image([OK] * 6 + [SUPERSEDED, SUPERSEDED, UNCERTAIN], has_source_geometry=True)
        is GeometryImageState.INCOMPLETE_UNCERTAIN
    )


def test_image_without_live_boards_and_a_checksum_twin_is_superseded() -> None:
    assert (
        classify_image(
            [MISSING] * 9,
            has_source_geometry=True,
            has_live_boards=False,
            checksum_twin_has_live_boards=True,
            import_file_failed=True,
        )
        is GeometryImageState.SUPERSEDED
    )
    assert (
        classify_image(
            [],
            has_source_geometry=False,
            has_live_boards=False,
            checksum_twin_has_live_boards=True,
        )
        is GeometryImageState.SUPERSEDED
    )


def test_failed_import_without_live_boards_and_without_a_twin_is_import_failed() -> None:
    assert (
        classify_image(
            [MISSING] * 9,
            has_source_geometry=True,
            has_live_boards=False,
            import_file_failed=True,
        )
        is GeometryImageState.IMPORT_FAILED
    )
    assert (
        classify_image(
            [], has_source_geometry=False, has_live_boards=False, import_file_failed=True
        )
        is GeometryImageState.IMPORT_FAILED
    )


def test_a_twin_or_a_failed_file_changes_nothing_for_an_image_with_live_boards() -> None:
    assert (
        classify_image(
            [OK] * 9,
            has_source_geometry=True,
            checksum_twin_has_live_boards=True,
            import_file_failed=True,
        )
        is GeometryImageState.COMPLETE
    )


def test_image_without_live_boards_and_without_a_twin_or_failure_keeps_the_old_states() -> None:
    assert (
        classify_image([MISSING] * 9, has_source_geometry=True, has_live_boards=False)
        is GeometryImageState.INCOMPLETE_MISSING
    )
    assert (
        classify_image([], has_source_geometry=False, has_live_boards=False)
        is GeometryImageState.NO_SOURCE_GEOMETRY
    )


def test_the_default_list_holds_the_states_that_still_need_attention() -> None:
    assert set(INCOMPLETE_IMAGE_STATES) == set(GeometryImageState) - {
        GeometryImageState.COMPLETE,
        GeometryImageState.SUPERSEDED,
    }


def test_expected_sequence_number_offsets_the_range_start_by_the_position() -> None:
    assert expected_sequence_number(62281, 0) == 62281
    assert expected_sequence_number(62281, 8) == 62289


def _quad(offset: float = 0) -> list[dict[str, float]]:
    return [
        {"x": 10 + offset, "y": 20},
        {"x": 110 + offset, "y": 20},
        {"x": 110 + offset, "y": 90},
        {"x": 10 + offset, "y": 90},
    ]


def test_quad_prefers_the_symbol_grid_over_the_final_quad() -> None:
    quad = extract_position_quad({"symbolGridQuad": _quad(1), "finalQuad": _quad(2)})

    assert quad is not None
    assert quad[0] == (11.0, 20.0)


def test_quad_falls_back_to_the_final_quad() -> None:
    quad = extract_position_quad({"finalQuad": _quad()})

    assert quad == ((10.0, 20.0), (110.0, 20.0), (110.0, 90.0), (10.0, 90.0))


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        {"finalQuad": None},
        {"finalQuad": _quad()[:3]},
        {"finalQuad": "not a quad"},
        {"finalQuad": [{"x": 1, "y": 2}] * 3 + [{"x": "4", "y": 2}]},
        {"finalQuad": [{"x": 1, "y": 2}] * 3 + [{"x": math.nan, "y": 2}]},
        {"finalQuad": [{"x": 1, "y": 2}] * 3 + [{"x": True, "y": 2}]},
        {"finalQuad": [{"x": 1, "y": 2}] * 3 + [[4, 5]]},
    ],
)
def test_quad_is_none_instead_of_invented_when_the_entry_has_no_valid_quad(
    entry: dict[str, object] | None,
) -> None:
    assert extract_position_quad(entry) is None


def test_invalid_symbol_grid_quad_falls_through_to_a_valid_final_quad() -> None:
    quad = extract_position_quad({"symbolGridQuad": [{"x": 1}], "finalQuad": _quad()})

    assert quad is not None
    assert quad[2] == (110.0, 90.0)


def test_cursor_round_trips_a_path_with_unicode_and_separators() -> None:
    cursor = GeometryImageCursor("2026/Zażółć|gęślą.jpg", UUID(int=7))

    assert decode_geometry_image_cursor(encode_geometry_image_cursor(cursor)) == cursor


@pytest.mark.parametrize("value", ["", "!!!", "e30=", "bm90LWpzb24=", "WzEsMl0="])
def test_garbage_cursor_is_rejected_with_a_stable_code(value: str) -> None:
    with pytest.raises(ImageReviewError) as error:
        decode_geometry_image_cursor(value)

    assert error.value.code == "IMAGE_GEOMETRY_COMPLETENESS_CURSOR_INVALID"


def test_low_quality_thresholds_default_to_the_task_values() -> None:
    thresholds = LowQualityThresholds()

    assert (thresholds.max_confidence, thresholds.min_cells) == (0.80, 5)


@pytest.mark.parametrize(
    ("max_confidence", "min_cells"),
    [(-0.01, 5), (1.01, 5), (math.nan, 5), (0.8, 0), (0.8, 16), (0.8, True)],
)
def test_low_quality_thresholds_reject_out_of_range_values(
    max_confidence: float, min_cells: int
) -> None:
    with pytest.raises(ImageReviewError) as error:
        LowQualityThresholds(max_confidence=max_confidence, min_cells=min_cells)

    assert error.value.code == "IMAGE_GEOMETRY_LOW_QUALITY_THRESHOLD_INVALID"


# -- D-484 gate (TASK-0807) ---------------------------------------------------

COMPLETE_STATUS = SourceImageGeometryStatus.GEOMETRY_COMPLETE
INCOMPLETE_STATUS = SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
EXCEPTION_STATUS = SourceImageGeometryStatus.GEOMETRY_EXCEPTION


@pytest.mark.parametrize(
    ("state", "status"),
    [
        (GeometryImageState.COMPLETE, COMPLETE_STATUS),
        (GeometryImageState.INCOMPLETE_MISSING, INCOMPLETE_STATUS),
        (GeometryImageState.INCOMPLETE_PARTIAL, INCOMPLETE_STATUS),
        (GeometryImageState.INCOMPLETE_UNCERTAIN, INCOMPLETE_STATUS),
        (GeometryImageState.SUPERSEDED, None),
        (GeometryImageState.IMPORT_FAILED, None),
        (GeometryImageState.NO_SOURCE_GEOMETRY, None),
    ],
)
def test_every_image_state_maps_to_one_persisted_status(
    state: GeometryImageState, status: SourceImageGeometryStatus | None
) -> None:
    assert persisted_status_for(state) is status
    assert recomputed_status(current=None, state=state) is status


def test_a_recompute_keeps_an_exception_until_the_image_is_complete() -> None:
    for state in GeometryImageState:
        expected = COMPLETE_STATUS if state is GeometryImageState.COMPLETE else EXCEPTION_STATUS
        assert recomputed_status(current=EXCEPTION_STATUS, state=state) is expected
    assert (
        recomputed_status(current=COMPLETE_STATUS, state=GeometryImageState.INCOMPLETE_UNCERTAIN)
        is INCOMPLETE_STATUS
    )


def test_only_an_incomplete_status_is_not_admitted() -> None:
    assert is_admitted_status(None)
    assert is_admitted_status(COMPLETE_STATUS)
    assert is_admitted_status(EXCEPTION_STATUS)
    assert not is_admitted_status(INCOMPLETE_STATUS)


@pytest.mark.parametrize(
    ("image_status", "position_state", "qualified", "has_cells", "withheld"),
    [
        # NULL (not evaluated) keeps the behaviour from before the gate.
        (None, MISSING, False, False, False),
        (None, UNCERTAIN, False, False, False),
        (COMPLETE_STATUS, OK, False, False, False),
        (INCOMPLETE_STATUS, OK, False, False, True),
        (INCOMPLETE_STATUS, UNCERTAIN, False, False, True),
        (INCOMPLETE_STATUS, PARTIAL, True, False, True),
        # Existing cells are never undone: the gate only blocks new ones.
        (INCOMPLETE_STATUS, OK, False, True, False),
        (INCOMPLETE_STATUS, UNCERTAIN, False, True, False),
        # Exception: ok and approved qualified partial boards are cut (D-449).
        (EXCEPTION_STATUS, OK, False, False, False),
        (EXCEPTION_STATUS, PARTIAL, True, False, False),
        (EXCEPTION_STATUS, PARTIAL, False, False, True),
        (EXCEPTION_STATUS, UNCERTAIN, False, False, True),
        (EXCEPTION_STATUS, MISSING, False, False, True),
        (EXCEPTION_STATUS, UNCERTAIN, False, True, False),
    ],
)
def test_gate_withholds_only_uncut_boards_of_images_that_are_not_admitted(
    image_status: SourceImageGeometryStatus | None,
    position_state: GeometryPositionState,
    qualified: bool,
    has_cells: bool,
    withheld: bool,
) -> None:
    assert (
        geometry_gate_withholds_board(
            image_status=image_status,
            position_state=position_state,
            qualified_partial_approved=qualified,
            has_cells=has_cells,
        )
        is withheld
    )


def test_exception_reason_is_required_and_bounded() -> None:
    assert require_geometry_exception_reason("  Plansza poza kadrem ") == "Plansza poza kadrem"
    for value in ("", "   ", "x" * 1001):
        with pytest.raises(ImageReviewError) as error:
            require_geometry_exception_reason(value)
        assert error.value.code == "IMAGE_GEOMETRY_EXCEPTION_REASON_INVALID"
    assert SOURCE_IMAGE_GEOMETRY_INCOMPLETE == "SOURCE_IMAGE_GEOMETRY_INCOMPLETE"


@pytest.mark.parametrize(
    "position_state,qualified,withheld",
    [
        (OK, False, False),
        (PARTIAL, True, False),
        (PARTIAL, False, True),
        (UNCERTAIN, False, True),
        (MISSING, False, True),
    ],
)
def test_current_manual_neural_approval_admits_only_its_reviewable_position(
    position_state,
    qualified,
    withheld,
) -> None:
    assert (
        geometry_gate_withholds_board(
            image_status=INCOMPLETE_STATUS,
            position_state=position_state,
            qualified_partial_approved=qualified,
            has_cells=False,
            manual_neural_lattice_approved=True,
        )
        is withheld
    )
