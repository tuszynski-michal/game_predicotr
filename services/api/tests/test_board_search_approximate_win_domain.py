from __future__ import annotations

from collections.abc import Sequence

import pytest
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import (
    APPROXIMATE_WIN_CELL_COUNT,
    ApproximateWinDocument,
    calculate_approximate_win,
    plan_approximate_win_positions,
)


def _codes(known: Sequence[int | None]) -> tuple[int | None, ...]:
    """Pad/trim a short row-major spec to the full 15-cell board."""
    padded = tuple(known) + (None,) * (APPROXIMATE_WIN_CELL_COUNT - len(known))
    assert len(padded) == APPROXIMATE_WIN_CELL_COUNT
    return padded


def _document(
    sequence_number: int,
    codes: tuple[int | None, ...],
    *,
    status: str = "pending",
    checksum: str | None = None,
) -> ApproximateWinDocument:
    return ApproximateWinDocument(
        sequence_number=sequence_number,
        status=status,
        board_checksum_sha256=checksum or f"{sequence_number:0>64}",
        mobile_codes=codes,
    )


def _sum_evaluate(cells: Sequence[int]) -> int:
    """A deterministic stand-in payout function for domain-level tests:
    total payout is simply the sum of known (non-zero) cell codes. Real
    payout-v3 semantics are already covered end to end against
    `PreparedPayoutEvaluator` in `services/worker/tests/test_payout.py`
    (TASK-0650); this module only needs to prove its own orchestration.
    """
    return sum(cells)


# --- plan_approximate_win_positions -----------------------------------------


def test_start_board_never_enters_the_range() -> None:
    positions = plan_approximate_win_positions(
        start_sequence_number=5, requested_spin_count=3, sequence_length=100
    )
    assert 5 not in positions
    assert positions == (6, 7, 8)


def test_positions_are_clamped_to_sequence_length_minus_one() -> None:
    positions = plan_approximate_win_positions(
        start_sequence_number=1, requested_spin_count=1000, sequence_length=5
    )
    assert len(positions) == 4  # L - 1
    assert positions == (2, 3, 4, 5)


def test_positions_wrap_cyclically_past_the_sequence_end() -> None:
    positions = plan_approximate_win_positions(
        start_sequence_number=8, requested_spin_count=5, sequence_length=10
    )
    assert positions == (9, 10, 1, 2, 3)


def test_last_position_wraps_to_the_start_of_the_sequence() -> None:
    positions = plan_approximate_win_positions(
        start_sequence_number=10, requested_spin_count=1, sequence_length=10
    )
    assert positions == (1,)


def test_full_cycle_evaluates_exactly_length_minus_one_spins_without_repeats() -> None:
    positions = plan_approximate_win_positions(
        start_sequence_number=4, requested_spin_count=9, sequence_length=10
    )
    assert len(positions) == 9
    assert len(set(positions)) == 9  # no repeats
    assert 4 not in positions
    assert sorted(positions) == [1, 2, 3, 5, 6, 7, 8, 9, 10]


@pytest.mark.parametrize(
    ("start", "length"),
    ((0, 10), (11, 10), (-1, 10)),
)
def test_invalid_start_raises_board_search_error(start: int, length: int) -> None:
    with pytest.raises(BoardSearchError) as captured:
        plan_approximate_win_positions(
            start_sequence_number=start, requested_spin_count=1, sequence_length=length
        )
    assert captured.value.code == "APPROXIMATE_WIN_START_OUT_OF_RANGE"


def test_zero_sequence_length_raises_board_search_error() -> None:
    with pytest.raises(BoardSearchError) as captured:
        plan_approximate_win_positions(
            start_sequence_number=1, requested_spin_count=1, sequence_length=0
        )
    assert captured.value.code == "APPROXIMATE_WIN_START_OUT_OF_RANGE"


def test_non_positive_spin_count_raises_board_search_error() -> None:
    with pytest.raises(BoardSearchError) as captured:
        plan_approximate_win_positions(
            start_sequence_number=1, requested_spin_count=0, sequence_length=10
        )
    assert captured.value.code == "APPROXIMATE_WIN_SPIN_COUNT_INVALID"


# --- calculate_approximate_win: categorization ------------------------------


def test_missing_position_adds_cost_and_zero_payout_without_calling_evaluate() -> None:
    calls: list[Sequence[int]] = []

    def spy(cells: Sequence[int]) -> int:
        calls.append(cells)
        return _sum_evaluate(cells)

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=3,
        sequence_length=100,
        documents=(),
        evaluate=spy,
        spin_cost=20,
    )

    assert calls == []
    assert result.summary.recognized_payout_credits == 0
    assert result.summary.spin_cost_credits == 60
    assert result.summary.balance_credits == -60
    assert result.completeness.missing_board_count == 3
    assert result.completeness.complete_board_count == 0
    assert result.completeness.partial_board_count == 0
    assert result.rows == ()


def test_complete_board_is_exact_and_partial_board_with_payout_stays_partial() -> None:
    complete = _document(2, _codes((1,) * APPROXIMATE_WIN_CELL_COUNT))
    partial_with_payout = _document(3, _codes((7,)))  # one known cell, rest unknown

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=3,
        sequence_length=100,
        documents=(complete, partial_with_payout),
        evaluate=_sum_evaluate,
        spin_cost=0,
    )

    assert result.completeness.complete_board_count == 1
    assert result.completeness.partial_board_count == 1
    assert result.completeness.missing_board_count == 1

    rows_by_sequence = {row.sequence_number: row for row in result.rows}
    assert rows_by_sequence[2].payout_kind == "exact"
    assert rows_by_sequence[2].payout_credits == APPROXIMATE_WIN_CELL_COUNT
    assert rows_by_sequence[3].payout_kind == "confirmed_minimum"
    assert rows_by_sequence[3].payout_credits == 7


def test_partial_board_without_any_payout_still_counts_as_partial() -> None:
    fully_unknown = _document(2, _codes(()))  # all 15 cells unknown

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=1,
        sequence_length=100,
        documents=(fully_unknown,),
        evaluate=_sum_evaluate,
        spin_cost=5,
    )

    assert result.completeness.partial_board_count == 1
    assert result.completeness.complete_board_count == 0
    assert result.rows == ()
    assert result.summary.recognized_payout_credits == 0
    assert result.summary.spin_cost_credits == 5


def test_categories_are_disjoint_and_sum_to_evaluated_spin_count() -> None:
    documents = (
        _document(2, _codes((1,) * APPROXIMATE_WIN_CELL_COUNT)),  # complete
        _document(3, _codes((2,))),  # partial
        # position 4 missing
        _document(5, _codes(())),  # partial (all unknown)
    )

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=4,
        sequence_length=100,
        documents=documents,
        evaluate=_sum_evaluate,
        spin_cost=1,
    )

    completeness = result.completeness
    assert (
        completeness.complete_board_count
        + completeness.partial_board_count
        + completeness.missing_board_count
        == result.evaluated_spin_count
        == 4
    )
    assert completeness.complete_board_count == 1
    assert completeness.partial_board_count == 2
    assert completeness.missing_board_count == 1


# --- calculate_approximate_win: cumulative accounting -----------------------


def test_control_example_matches_plan_numbers() -> None:
    """1000 spins @ spin_cost=20, 18000 recognized -> cost 20000, balance -2000."""

    win = _document(2, _codes((18_000,)))

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=1000,
        sequence_length=1002,
        documents=(win,),
        evaluate=_sum_evaluate,
        spin_cost=20,
    )

    assert result.evaluated_spin_count == 1000
    assert result.summary.recognized_payout_credits == 18_000
    assert result.summary.spin_cost_credits == 20_000
    assert result.summary.balance_credits == -2_000


def test_row_appears_even_while_cumulative_balance_is_negative_at_that_row() -> None:
    last_position_win = _document(11, _codes((5,)))  # last of 10 evaluated spins

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=10,
        sequence_length=12,
        documents=(last_position_win,),
        evaluate=_sum_evaluate,
        spin_cost=100,
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.payout_credits == 5
    assert row.cumulative_cost_credits == 1_000
    assert row.cumulative_balance_credits == 5 - 1_000
    assert row.cumulative_balance_credits < 0


def test_cumulative_totals_account_for_skipped_and_trailing_spins() -> None:
    documents = (
        _document(2, _codes((5,))),  # win
        # position 3 missing
        _document(4, _codes(())),  # partial, zero payout
        _document(5, _codes((3,))),  # win
        # position 6 missing (trailing, after the last win)
    )

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=5,
        sequence_length=22,
        documents=documents,
        evaluate=_sum_evaluate,
        spin_cost=20,
    )

    assert result.evaluated_spin_count == 5
    assert result.summary.spin_cost_credits == 100
    assert result.summary.recognized_payout_credits == 8
    assert result.summary.balance_credits == 8 - 100

    rows_by_sequence = {row.sequence_number: row for row in result.rows}
    assert set(rows_by_sequence) == {2, 5}
    assert rows_by_sequence[2].cumulative_cost_credits == 20
    assert rows_by_sequence[2].cumulative_payout_credits == 5
    assert rows_by_sequence[5].spin_number == 4
    assert rows_by_sequence[5].cumulative_cost_credits == 80
    assert rows_by_sequence[5].cumulative_payout_credits == 8
    assert rows_by_sequence[5].cumulative_balance_credits == 8 - 80


def test_empty_range_result_has_correct_summary_and_completeness() -> None:
    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=1,
        sequence_length=100,
        documents=(),
        evaluate=_sum_evaluate,
        spin_cost=7,
    )

    assert result.rows == ()
    assert result.summary == type(result.summary)(
        recognized_payout_credits=0, spin_cost_credits=7, balance_credits=-7
    )
    assert result.completeness.missing_board_count == 1


# --- calculate_approximate_win: wrapping metadata ---------------------------


def test_wrapped_at_sequence_end_is_false_when_the_range_stays_inside_the_sequence() -> None:
    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=3,
        sequence_length=10,
        documents=(),
        evaluate=_sum_evaluate,
        spin_cost=0,
    )
    assert result.wrapped_at_sequence_end is False


def test_wrapped_at_sequence_end_is_true_when_the_range_crosses_the_sequence_boundary() -> None:
    result = calculate_approximate_win(
        start_sequence_number=8,
        requested_spin_count=5,
        sequence_length=10,
        documents=(),
        evaluate=_sum_evaluate,
        spin_cost=0,
    )
    assert result.wrapped_at_sequence_end is True


def test_wrapped_at_sequence_end_is_true_when_the_start_is_the_last_position() -> None:
    result = calculate_approximate_win(
        start_sequence_number=10,
        requested_spin_count=1,
        sequence_length=10,
        documents=(),
        evaluate=_sum_evaluate,
        spin_cost=0,
    )
    assert result.wrapped_at_sequence_end is True


# --- calculate_approximate_win: error handling and integrity ---------------


def test_duplicate_document_for_the_same_sequence_number_raises() -> None:
    duplicate_a = _document(2, _codes((1,)))
    duplicate_b = _document(2, _codes((2,)))

    with pytest.raises(ValueError, match="Duplicate"):
        calculate_approximate_win(
            start_sequence_number=1,
            requested_spin_count=3,
            sequence_length=100,
            documents=(duplicate_a, duplicate_b),
            evaluate=_sum_evaluate,
            spin_cost=0,
        )


def test_a_document_outside_the_planned_range_is_ignored() -> None:
    outside_range = _document(999, _codes((123,)))

    result = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=2,
        sequence_length=1000,
        documents=(outside_range,),
        evaluate=_sum_evaluate,
        spin_cost=1,
    )

    assert result.rows == ()
    assert result.completeness.missing_board_count == 2


def test_evaluate_exception_propagates_uncaught() -> None:
    """A symbol outside the active rules configuration (D6) must fail the
    whole range instead of being silently skipped; this module never catches
    exceptions raised by `evaluate`."""

    def raising_evaluate(cells: Sequence[int]) -> int:
        raise RuntimeError("unrecognized mobile code")

    with pytest.raises(RuntimeError, match="unrecognized mobile code"):
        calculate_approximate_win(
            start_sequence_number=1,
            requested_spin_count=1,
            sequence_length=100,
            documents=(_document(2, _codes((1,))),),
            evaluate=raising_evaluate,
            spin_cost=0,
        )


def test_negative_spin_cost_is_rejected() -> None:
    with pytest.raises(ValueError, match="spin_cost"):
        calculate_approximate_win(
            start_sequence_number=1,
            requested_spin_count=1,
            sequence_length=100,
            documents=(),
            evaluate=_sum_evaluate,
            spin_cost=-1,
        )


# --- ApproximateWinDocument validation ---------------------------------


def test_document_rejects_wrong_cell_count() -> None:
    with pytest.raises(ValueError, match="mobile_codes"):
        ApproximateWinDocument(
            sequence_number=1,
            status="pending",
            board_checksum_sha256="a" * 64,
            mobile_codes=(1, 2, 3),
        )


def test_document_rejects_non_positive_sequence_number() -> None:
    with pytest.raises(ValueError, match="sequence_number"):
        ApproximateWinDocument(
            sequence_number=0,
            status="pending",
            board_checksum_sha256="a" * 64,
            mobile_codes=_codes(()),
        )


def test_document_is_complete_reflects_absence_of_unknown_cells() -> None:
    complete = _document(1, _codes((1,) * APPROXIMATE_WIN_CELL_COUNT))
    partial = _document(2, _codes((1,)))
    assert complete.is_complete is True
    assert partial.is_complete is False


# --- data fingerprint --------------------------------------------------


def test_fingerprint_is_deterministic_for_identical_input() -> None:
    documents = (_document(2, _codes((1, 2, 3)), status="accepted", checksum="a" * 64),)

    first = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=1,
        sequence_length=100,
        documents=documents,
        evaluate=_sum_evaluate,
        spin_cost=0,
    )
    second = calculate_approximate_win(
        start_sequence_number=1,
        requested_spin_count=1,
        sequence_length=100,
        documents=documents,
        evaluate=_sum_evaluate,
        spin_cost=0,
    )

    assert first.data_fingerprint_sha256 == second.data_fingerprint_sha256


@pytest.mark.parametrize(
    "mutate",
    (
        lambda document: _document(
            document.sequence_number, _codes((9, 9, 9)), status=document.status
        ),
        lambda document: _document(
            document.sequence_number,
            document.mobile_codes,
            status="corrected",
            checksum=document.board_checksum_sha256,
        ),
        lambda document: _document(
            document.sequence_number,
            document.mobile_codes,
            status=document.status,
            checksum="b" * 64,
        ),
    ),
)
def test_fingerprint_changes_when_evaluated_board_data_changes(mutate) -> None:
    baseline = _document(2, _codes((1, 2, 3)), status="accepted", checksum="a" * 64)
    mutated = mutate(baseline)

    def result_for(document: ApproximateWinDocument) -> str:
        return calculate_approximate_win(
            start_sequence_number=1,
            requested_spin_count=1,
            sequence_length=100,
            documents=(document,),
            evaluate=_sum_evaluate,
            spin_cost=0,
        ).data_fingerprint_sha256

    assert result_for(baseline) != result_for(mutated)
