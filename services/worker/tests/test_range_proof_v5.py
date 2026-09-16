from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionRange,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import (
    ProvisionalExactRangeObservation,
    RangeProofUnknownReason,
    RangeRowOffset,
    RowExpectedRangeEntry,
    RowExpectedRangeTable,
    RowFirstExactResolver,
    RowRangeProofPolicy,
    RowRangeTopology,
    RowTripleProof,
    UnknownRowRangeObservation,
    VerifiedRangeCandidate,
    verify_range_candidate,
)


def _table(first: int = 21_169, last: int = 21_186) -> RowExpectedRangeTable:
    return RowExpectedRangeTable.from_bounds(SemiAutomaticSequenceBounds(first, last))


def _proof(
    row: RangeRowOffset,
    values: tuple[str, str, str],
    confidence: tuple[float, float, float] = (0.94, 0.95, 0.96),
    *,
    complete: tuple[bool, bool, bool] = (True, True, True),
    readable: tuple[bool, bool, bool] = (True, True, True),
) -> RowTripleProof:
    return RowTripleProof(
        row=row,
        recognized_texts=values,
        recognition_confidences=confidence,
        crop_completeness=complete,
        crop_readability=readable,
    )


def test_table_attests_top_middle_and_bottom_rows_for_a_full_range() -> None:
    entry = _table().entries[0]

    assert entry.values_for(RangeRowOffset.TOP) == (21_169, 21_170, 21_171)
    assert entry.values_for(RangeRowOffset.MIDDLE) == (21_172, 21_173, 21_174)
    assert entry.values_for(RangeRowOffset.BOTTOM) == (21_175, 21_176, 21_177)
    assert entry.sequence_filename == "seq_21169-21177.jpg"


@pytest.mark.parametrize(
    ("row", "values"),
    [
        (RangeRowOffset.TOP, ("21169", "21170", "21171")),
        (RangeRowOffset.MIDDLE, ("21172", "21173", "21174")),
        (RangeRowOffset.BOTTOM, ("21175", "21176", "21177")),
    ],
)
def test_each_row_can_provisionally_prove_the_same_expected_range(
    row: RangeRowOffset,
    values: tuple[str, str, str],
) -> None:
    result = RowFirstExactResolver(_table()).resolve(_proof(row, values))

    assert isinstance(result, ProvisionalExactRangeObservation)
    assert result.row is row
    assert result.matched_expected_range.sequence_filename == "seq_21169-21177.jpg"


def test_one_exact_row_is_provisional_not_an_automatic_candidate() -> None:
    resolver = RowFirstExactResolver(_table())
    top = resolver.resolve(_proof(RangeRowOffset.TOP, ("21169", "21170", "21171")))

    result = verify_range_candidate((top,))

    assert isinstance(result, UnknownRowRangeObservation)
    assert result.reason_code is RangeProofUnknownReason.FINAL_PROOF_INSUFFICIENT


def test_two_agreeing_visible_rows_verify_a_candidate() -> None:
    resolver = RowFirstExactResolver(_table())
    top = resolver.resolve(_proof(RangeRowOffset.TOP, ("21169", "21170", "21171")))
    middle = resolver.resolve(
        _proof(RangeRowOffset.MIDDLE, ("21172", "21173", "21174"))
    )
    clipped_bottom = resolver.resolve(
        _proof(
            RangeRowOffset.BOTTOM,
            ("", "", ""),
            complete=(False, False, False),
        )
    )

    result = verify_range_candidate((top, middle, clipped_bottom))

    assert isinstance(result, VerifiedRangeCandidate)
    assert result.matched_expected_range.sequence_filename == "seq_21169-21177.jpg"
    assert result.verified_rows == (RangeRowOffset.TOP, RangeRowOffset.MIDDLE)


def test_mixed_transition_rows_are_rejected_even_when_two_rows_agree() -> None:
    table = _table(first=43_480, last=43_497)
    resolver = RowFirstExactResolver(table)
    old_middle = resolver.resolve(
        _proof(RangeRowOffset.MIDDLE, ("43483", "43484", "43485"))
    )
    old_bottom = resolver.resolve(
        _proof(RangeRowOffset.BOTTOM, ("43486", "43487", "43488"))
    )
    next_top = resolver.resolve(
        _proof(RangeRowOffset.TOP, ("43489", "43490", "43491"))
    )

    result = verify_range_candidate((next_top, old_middle, old_bottom))

    assert isinstance(result, UnknownRowRangeObservation)
    assert result.reason_code is RangeProofUnknownReason.CONFLICTING_VISIBLE_ROWS


def test_complete_row_that_cannot_be_read_vetoes_final_selection() -> None:
    resolver = RowFirstExactResolver(_table())
    top = resolver.resolve(_proof(RangeRowOffset.TOP, ("21169", "21170", "21171")))
    middle = resolver.resolve(
        _proof(RangeRowOffset.MIDDLE, ("21172", "21173", "21174"))
    )
    unreadable_bottom = resolver.resolve(
        _proof(RangeRowOffset.BOTTOM, ("", "", ""))
    )

    result = verify_range_candidate((top, middle, unreadable_bottom))

    assert isinstance(result, UnknownRowRangeObservation)
    assert result.reason_code is RangeProofUnknownReason.COMPLETE_ROW_UNVERIFIED


def test_partial_final_range_requires_manual_review() -> None:
    table = _table(first=21_169, last=21_173)

    result = RowFirstExactResolver(table).resolve(
        _proof(RangeRowOffset.TOP, ("21169", "21170", "21171"))
    )

    assert isinstance(result, UnknownRowRangeObservation)
    assert result.reason_code is RangeProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW


def test_resolver_rejects_fuzzy_or_low_confidence_values() -> None:
    resolver = RowFirstExactResolver(_table())

    inconsistent = resolver.resolve(
        _proof(RangeRowOffset.MIDDLE, ("21172", "21174", "21175"))
    )
    low_confidence = resolver.resolve(
        _proof(
            RangeRowOffset.MIDDLE,
            ("21172", "21173", "21174"),
            confidence=(0.81, 0.99, 0.99),
        )
    )

    assert isinstance(inconsistent, UnknownRowRangeObservation)
    assert inconsistent.reason_code is RangeProofUnknownReason.INCONSISTENT_TRIPLE
    assert isinstance(low_confidence, UnknownRowRangeObservation)
    assert low_confidence.reason_code is RangeProofUnknownReason.LOW_OCR_CONFIDENCE


def test_expected_range_collision_stays_fail_closed() -> None:
    table = _table()
    duplicate = replace(
        table.entries[1],
        row_values=table.entries[0].row_values,
    )
    ambiguous = replace(table, entries=(table.entries[0], duplicate))

    result = RowFirstExactResolver(ambiguous).resolve(
        _proof(RangeRowOffset.TOP, ("21169", "21170", "21171"))
    )

    assert isinstance(result, UnknownRowRangeObservation)
    assert result.reason_code is RangeProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE


def test_contract_rejects_non_3x3_topology_and_invalid_entry() -> None:
    with pytest.raises(ValueError, match="3x3"):
        RowRangeTopology(rows=2, columns=4)

    with pytest.raises(ValueError, match="full three-number"):
        RowExpectedRangeEntry(
            expected_index=0,
            sequence_range=SemiAutomaticSelectionRange(1, 5),
            row_values=((RangeRowOffset.TOP, (1, 2, 3)),),
            is_partial_page=True,
            sequence_filename="seq_1-5.jpg",
        )


def test_fingerprint_changes_when_thresholds_change() -> None:
    table = _table()
    resolver = RowFirstExactResolver(table)
    stricter = RowFirstExactResolver(
        table,
        policy=replace(RowRangeProofPolicy(), minimum_average_confidence=0.95),
    )

    assert resolver.fingerprint != stricter.fingerprint
