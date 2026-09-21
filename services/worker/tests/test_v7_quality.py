from __future__ import annotations

import json
from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_occurrences import (
    V7OccurrenceError,
    V7OccurrenceObservation,
    V7OccurrenceTracker,
)
from game_predictor_worker.semi_automatic_selection.v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7CropEdge,
    V7DecorationVisibility,
    V7FrameQuality,
    V7OcclusionSeverity,
    V7QualityError,
    V7QualityWarning,
    V7SymbolContentLoss,
    rank_v7_representatives,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7RangeProofKind,
    V7RangeProofResult,
)

RANGES = (SemiAutomaticSelectionRange(1, 9), SemiAutomaticSelectionRange(10, 18))


def _strong(source_id: str, sequence_range: SemiAutomaticSelectionRange) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.STRONG_FIVE_LABEL,
        sequence_range=sequence_range,
        supporting_source_ids=(source_id,),
        reason_codes=(),
    )


def _none() -> V7RangeProofResult:
    return V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("NO_LOCAL_PROOF",))


def _multi(
    sequence_range: SemiAutomaticSelectionRange,
    source_ids: tuple[str, str],
) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,
        sequence_range=sequence_range,
        supporting_source_ids=source_ids,
        reason_codes=(),
    )


def _consume(
    tracker: V7OccurrenceTracker,
    source_index: int,
    proof: V7RangeProofResult,
) -> None:
    tracker.consume(V7OccurrenceObservation(source_index, f"source-{source_index}", proof))


def _board(position_index: int) -> V7BoardQuality:
    return V7BoardQuality(
        position_index=position_index,
        symbol_content_loss=V7SymbolContentLoss.NONE,
        readability=V7BoardReadability.CLEAR,
        visibility=V7BoardVisibility.FULL,
        blur=V7BlurSeverity.NONE,
        occlusion=V7OcclusionSeverity.NONE,
        decoration=V7DecorationVisibility.COMPLETE,
    )


def _frame(
    source_index: int,
    *,
    changed_board: V7BoardQuality | None = None,
) -> V7FrameQuality:
    boards = tuple(
        changed_board
        if changed_board is not None and position == changed_board.position_index
        else _board(position)
        for position in range(9)
    )
    return V7FrameQuality(f"source-{source_index}", source_index, boards)


def _rank(
    tracker: V7OccurrenceTracker,
    qualities: tuple[V7FrameQuality, ...],
    *,
    border_style: V7BorderStyle = V7BorderStyle.TOP_AND_SIDES,
):
    return rank_v7_representatives(tracker, qualities, border_style=border_style)


def test_global_ranking_selects_later_better_a_without_rewinding_cursor() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    _consume(tracker, 1, _strong("source-1", RANGES[1]))
    _consume(tracker, 2, _strong("source-2", RANGES[0]))
    tracker.finish()

    major_loss = replace(_board(4), symbol_content_loss=V7SymbolContentLoss.MAJOR)
    selections = _rank(tracker, (_frame(0, changed_board=major_loss), _frame(1), _frame(2)))

    assert [(item.sequence_range, item.source_id) for item in selections] == [
        (RANGES[0], "source-2"),
        (RANGES[1], "source-1"),
    ]
    assert tracker.cursors.sequence_cursor_index == 1


def test_symbol_loss_precedes_readable_light_blur_but_unreadable_loses_to_minor_loss() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    _consume(tracker, 1, _strong("source-1", RANGES[0]))
    tracker.finish()

    light_blur = replace(
        _board(0), blur=V7BlurSeverity.LIGHT, readability=V7BoardReadability.READABLE
    )
    major_loss = replace(_board(0), symbol_content_loss=V7SymbolContentLoss.MAJOR)
    (selection,) = _rank(
        tracker, (_frame(0, changed_board=light_blur), _frame(1, changed_board=major_loss))
    )
    assert selection.source_id == "source-0"

    unreadable = replace(_board(0), readability=V7BoardReadability.UNREADABLE)
    minor_loss = replace(
        _board(0),
        symbol_content_loss=V7SymbolContentLoss.MINOR,
        visibility=V7BoardVisibility.PARTIAL,
        cropped_edges=frozenset({V7CropEdge.LEFT}),
    )
    (selection,) = _rank(
        tracker, (_frame(0, changed_board=unreadable), _frame(1, changed_board=minor_loss))
    )
    assert selection.source_id == "source-1"


def test_unknown_is_not_zero_risk_and_one_bad_board_is_not_averaged_away() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    _consume(tracker, 1, _strong("source-1", RANGES[0]))
    tracker.finish()

    unknown = replace(
        _board(8),
        symbol_content_loss=V7SymbolContentLoss.UNKNOWN,
        visibility=V7BoardVisibility.UNKNOWN,
    )
    minor_loss = replace(
        _board(4),
        symbol_content_loss=V7SymbolContentLoss.MINOR,
        visibility=V7BoardVisibility.PARTIAL,
    )
    (selection,) = _rank(
        tracker, (_frame(0, changed_board=unknown), _frame(1, changed_board=minor_loss))
    )

    assert selection.source_id == "source-1"
    assert (
        V7QualityWarning.SYMBOL_VISIBILITY_UNKNOWN
        in _frame(0, changed_board=unknown).summarize(V7BorderStyle.TOP_AND_SIDES).warnings
    )
    assert (
        V7QualityWarning.VISIBILITY_UNKNOWN
        in _frame(0, changed_board=unknown).summarize(V7BorderStyle.TOP_AND_SIDES).warnings
    )


def test_vertical_and_lateral_crop_warnings_are_explicit() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    tracker.finish()

    cropped = replace(
        _board(0),
        cropped_edges=frozenset({V7CropEdge.TOP, V7CropEdge.BOTTOM, V7CropEdge.LEFT}),
    )
    (selection,) = _rank(tracker, (_frame(0, changed_board=cropped),))

    assert {
        V7QualityWarning.TOP_CROPPED,
        V7QualityWarning.BOTTOM_CROPPED,
        V7QualityWarning.LEFT_CROPPED,
    }.issubset(selection.quality.warnings)


def test_strong_and_three_plus_three_are_equally_eligible_for_quality_ranking() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _none())
    _consume(tracker, 1, _multi(RANGES[0], ("source-0", "source-1")))
    _consume(tracker, 2, _strong("source-2", RANGES[0]))
    tracker.finish()

    major_loss = replace(_board(0), symbol_content_loss=V7SymbolContentLoss.MAJOR)
    light_blur = replace(
        _board(0), blur=V7BlurSeverity.LIGHT, readability=V7BoardReadability.READABLE
    )
    (selection,) = _rank(
        tracker,
        (_frame(0), _frame(1, changed_board=light_blur), _frame(2, changed_board=major_loss)),
    )

    assert selection.source_id == "source-0"
    assert selection.proof_kinds == (V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,)


def test_unproved_neighbour_cannot_win_and_missing_or_mismatched_quality_fails_closed() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    _consume(tracker, 1, _none())
    tracker.finish()

    bad_proven = replace(_board(0), symbol_content_loss=V7SymbolContentLoss.MAJOR)
    (selection,) = _rank(tracker, (_frame(0, changed_board=bad_proven), _frame(1)))
    assert selection.source_id == "source-0"

    with pytest.raises(V7QualityError, match="no frame quality"):
        _rank(tracker, (_frame(1),))
    with pytest.raises(V7QualityError, match="no frame quality"):
        _rank(tracker, (V7FrameQuality("source-0", 1, _frame(0).boards),))


def test_ranking_requires_eof_and_irregular_border_decoration_is_neutral_only_for_its_style() -> (
    None
):
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    with pytest.raises(V7OccurrenceError, match="EOF"):
        _rank(tracker, (_frame(0),))
    tracker.finish()

    no_regular_border = replace(_board(0), decoration=V7DecorationVisibility.NOT_APPLICABLE)
    (irregular_selection,) = _rank(
        tracker,
        (_frame(0, changed_board=no_regular_border),),
        border_style=V7BorderStyle.IRREGULAR_OR_NONE,
    )
    assert V7QualityWarning.DECORATION_LOSS not in irregular_selection.quality.warnings
    (framed_selection,) = _rank(
        tracker,
        (_frame(0, changed_board=no_regular_border),),
        border_style=V7BorderStyle.TOP_AND_SIDES,
    )
    assert V7QualityWarning.DECORATION_UNKNOWN in framed_selection.quality.warnings


def test_frame_requires_every_board_once_in_grid_order() -> None:
    with pytest.raises(V7QualityError, match="each 3x3 board"):
        V7FrameQuality("source-0", 0, tuple(_board(position) for position in range(8)))

    with pytest.raises(V7QualityError, match="quality payload"):
        replace(_board(0), visibility=V7BoardVisibility.UNKNOWN)


def test_deterministic_ties_use_occurrence_center_then_source_index_not_input_order() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _strong("source-0", RANGES[0]))
    _consume(tracker, 1, _strong("source-1", RANGES[0]))
    _consume(tracker, 2, _strong("source-2", RANGES[0]))
    tracker.finish()

    (selection,) = _rank(tracker, (_frame(2), _frame(0), _frame(1)))
    assert selection.source_id == "source-1"

    global_tie = V7OccurrenceTracker(RANGES)
    _consume(global_tie, 0, _strong("source-0", RANGES[0]))
    _consume(global_tie, 1, _strong("source-1", RANGES[1]))
    _consume(global_tie, 2, _strong("source-2", RANGES[0]))
    global_tie.finish()
    selections = _rank(global_tie, (_frame(2), _frame(1), _frame(0)))
    assert selections[0].source_id == "source-0"


def test_three_plus_three_ranking_survives_checkpoint_round_trip_and_rejects_wrong_index() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, _none())
    _consume(tracker, 1, _multi(RANGES[0], ("source-0", "source-1")))
    checkpoint = json.loads(json.dumps(tracker.checkpoint()))
    restored = V7OccurrenceTracker(RANGES, checkpoint=checkpoint)
    restored.finish()

    (selection,) = _rank(restored, (_frame(1), _frame(0)))
    assert selection.source_id == "source-0"
    with pytest.raises(V7QualityError, match="no frame quality"):
        _rank(restored, (V7FrameQuality("source-0", 1, _frame(0).boards), _frame(1)))
