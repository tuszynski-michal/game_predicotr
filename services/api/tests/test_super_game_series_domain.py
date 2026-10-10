"""Pure derivation rules of super game series (TASK-0933, D-535)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from game_predictor_api.domain.super_game_series import (
    BoardTrigger,
    RunVerification,
    SeriesCompleteness,
    SuperGameSeriesDeriver,
    SuperGameSeriesError,
    SuperGameState,
    TriggerCellCount,
    derive_super_game_series,
    evaluate_board_trigger,
    series_positions,
    validate_super_symbol_candidate,
)


def _derive(
    *positions: int | tuple[int, bool],
    last_known: int | None,
    expected: int = 500_000,
) -> list:
    boards = [
        BoardTrigger(sequence_number=p, human_verified=True)
        if isinstance(p, int)
        else BoardTrigger(sequence_number=p[0], human_verified=p[1])
        for p in positions
    ]
    return derive_super_game_series(
        boards,
        series_length=10,
        retrigger_extension=10,
        expected_layout_count=expected,
        last_known_sequence_number=last_known,
    )


def test_trigger_and_retrigger_chain_builds_one_series() -> None:
    (series,) = _derive(100, 105, last_known=200)
    assert series.trigger_sequence_number == 100
    assert series.start_sequence_number == 101
    assert series.end_sequence_number == 120
    assert series.retrigger_sequence_numbers == (105,)
    assert series.completeness is SeriesCompleteness.COMPLETE


def test_trigger_inside_running_series_does_not_open_a_new_one() -> None:
    result = _derive(100, 105, 110, last_known=200)
    assert len(result) == 1
    assert result[0].retrigger_sequence_numbers == (105, 110)
    assert result[0].end_sequence_number == 130


def test_trigger_after_series_end_opens_new_series() -> None:
    first, second = _derive(100, 111, last_known=200)
    assert (first.trigger_sequence_number, first.end_sequence_number) == (100, 110)
    assert (second.trigger_sequence_number, second.start_sequence_number) == (111, 112)


def test_retrigger_on_last_spin_extends() -> None:
    (series,) = _derive(100, 110, last_known=200)
    assert series.retrigger_sequence_numbers == (110,)
    assert series.end_sequence_number == 120


def test_missing_board_inside_series_keeps_length() -> None:
    # Position 103 has no board at all: it is not fed and consumes a spin.
    (series,) = _derive(100, last_known=200)
    assert series.length == 10
    assert list(series_positions(100, series.length, 500_000)) == list(range(100, 111))


def test_series_beyond_last_known_board_is_incomplete() -> None:
    (series,) = _derive(100, last_known=108)
    assert series.completeness is SeriesCompleteness.INCOMPLETE
    (complete,) = _derive(100, last_known=110)
    assert complete.completeness is SeriesCompleteness.COMPLETE


def test_unverified_when_trigger_or_any_retrigger_relies_on_prediction() -> None:
    (series,) = _derive((100, False), last_known=200)
    assert series.run_verification is RunVerification.UNVERIFIED
    (series,) = _derive(100, (105, False), last_known=200)
    assert series.run_verification is RunVerification.UNVERIFIED
    (series,) = _derive(100, 105, last_known=200)
    assert series.run_verification is RunVerification.VERIFIED


def test_retrigger_numbers_above_smallint_range() -> None:
    (series,) = _derive(39_995, 40_000, last_known=50_000)
    assert series.retrigger_sequence_numbers == (40_000,)


def test_wrap_around_does_not_carry_a_series() -> None:
    # Audit P0-2: the spins 1001-1005 lie beyond the last known board 1000, so
    # the series is incomplete even at the sequence end; they are not carried
    # over to positions 1-5 either.
    (series,) = _derive(995, last_known=1_000, expected=1_000)
    assert series.end_sequence_number == 1_005
    assert series.completeness is SeriesCompleteness.INCOMPLETE
    assert list(series_positions(995, series.length, 1_000)) == list(range(995, 1_001))
    early, late = _derive(3, 995, last_known=1_000, expected=1_000)
    assert (early.trigger_sequence_number, early.retrigger_sequence_numbers) == (3, ())
    assert early.completeness is SeriesCompleteness.COMPLETE
    assert late.trigger_sequence_number == 995
    assert late.completeness is SeriesCompleteness.INCOMPLETE
    (inside,) = _derive(985, last_known=1_000, expected=1_000)
    assert inside.end_sequence_number == 995
    assert inside.completeness is SeriesCompleteness.COMPLETE
    deriver = SuperGameSeriesDeriver(
        series_length=10, retrigger_extension=10, expected_layout_count=1_000
    )
    with pytest.raises(SuperGameSeriesError, match="beyond"):
        deriver.feed(BoardTrigger(sequence_number=1_001, human_verified=True))


def test_boards_must_be_strictly_ascending() -> None:
    deriver = SuperGameSeriesDeriver(
        series_length=10, retrigger_extension=10, expected_layout_count=1_000
    )
    deriver.feed(BoardTrigger(sequence_number=5, human_verified=True))
    with pytest.raises(SuperGameSeriesError, match="ascending"):
        deriver.feed(BoardTrigger(sequence_number=5, human_verified=True))


def test_streaming_feed_closes_series_before_finish() -> None:
    deriver = SuperGameSeriesDeriver(
        series_length=10, retrigger_extension=10, expected_layout_count=1_000
    )
    assert deriver.feed(BoardTrigger(sequence_number=10, human_verified=True)) == []
    closed = deriver.feed(BoardTrigger(sequence_number=30, human_verified=True))
    assert [item.trigger_sequence_number for item in closed] == [10]
    assert [
        item.trigger_sequence_number for item in deriver.finish(last_known_sequence_number=35)
    ] == [30]


def test_board_trigger_threshold_and_human_verification() -> None:
    mumia, sarcophagus = uuid4(), uuid4()
    thresholds = {mumia: 3, sarcophagus: 4}
    assert evaluate_board_trigger(1, {mumia: TriggerCellCount(2, 2)}, thresholds) is None
    hit = evaluate_board_trigger(1, {mumia: TriggerCellCount(3, 2)}, thresholds)
    assert hit is not None and not hit.human_verified
    hit = evaluate_board_trigger(1, {mumia: TriggerCellCount(4, 3)}, thresholds)
    assert hit is not None and hit.human_verified
    assert evaluate_board_trigger(1, {sarcophagus: TriggerCellCount(3, 3)}, thresholds) is None


def test_state_freshness_is_derived_from_versions() -> None:
    assert SuperGameState(5, 5, has_super_game=True).fresh
    assert not SuperGameState(6, 5, has_super_game=True).fresh
    assert not SuperGameState(0, None, has_super_game=True).fresh
    assert SuperGameState(7, None, has_super_game=False).fresh


def test_super_symbol_must_be_ordinary() -> None:
    validate_super_symbol_candidate(
        is_wildcard=False, super_game_trigger_count=None, status="active"
    )
    for kwargs in (
        {"is_wildcard": True, "super_game_trigger_count": None, "status": "active"},
        {"is_wildcard": False, "super_game_trigger_count": 3, "status": "active"},
        {"is_wildcard": False, "super_game_trigger_count": None, "status": "archived"},
    ):
        with pytest.raises(SuperGameSeriesError, match="ordinary"):
            validate_super_symbol_candidate(**kwargs)  # type: ignore[arg-type]
