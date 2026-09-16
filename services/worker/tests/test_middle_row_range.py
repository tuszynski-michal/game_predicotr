from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_range import (
    ExactRangeObservation,
    ExpectedRangeEntry,
    ExpectedRangeTable,
    MiddleRowExactResolver,
    MiddleRowProofPolicy,
    MiddleRowTripleProof,
    MiddleRowUnknownReason,
    PageRangeTopology,
    UnknownRangeObservation,
)


def _table(
    first: int = 21_169,
    last: int = 21_186,
    *,
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING,
) -> ExpectedRangeTable:
    return ExpectedRangeTable.from_bounds(
        SemiAutomaticSequenceBounds(
            first_sequence_number=first,
            last_sequence_number=last,
            direction=direction,
        )
    )


def _proof(
    values: tuple[str, str, str] = ("21172", "21173", "21174"),
    confidence: tuple[float, float, float] = (0.94, 0.95, 0.96),
) -> MiddleRowTripleProof:
    return MiddleRowTripleProof(values, confidence)


def test_expected_range_table_contains_middle_row_values_and_names() -> None:
    table = _table()

    assert [entry.sequence_filename for entry in table.entries] == [
        "seq_21169-21177.jpg",
        "seq_21178-21186.jpg",
    ]
    assert table.entries[0].active_slots == tuple(range(9))
    assert table.entries[0].middle_row_expected_values == (21_172, 21_173, 21_174)
    assert table.entries[0].is_partial_page is False
    assert table.fingerprint == table.fingerprint


def test_partial_page_with_complete_middle_row_remains_matchable() -> None:
    table = _table(last=21_174)

    partial = table.entries[0]
    assert partial.is_partial_page is True
    assert partial.active_slots == tuple(range(6))
    assert partial.middle_row_expected_values == (21_172, 21_173, 21_174)
    assert isinstance(MiddleRowExactResolver(table).resolve(_proof()), ExactRangeObservation)


def test_partial_page_without_complete_middle_row_is_not_synthesized() -> None:
    table = _table(last=21_173)

    assert table.entries[0].middle_row_expected_values is None
    result = MiddleRowExactResolver(table).resolve(_proof())
    assert result == UnknownRangeObservation(
        reason_code=MiddleRowUnknownReason.NO_EXPECTED_RANGE_MATCH,
        recognized_texts=_proof().recognized_texts,
        recognition_confidences=_proof().recognition_confidences,
    )


def test_descending_bounds_change_table_order_not_canonical_middle_values() -> None:
    table = _table(
        first=21_186,
        last=21_169,
        direction=SemiAutomaticSelectionDirection.DESCENDING,
    )

    assert table.entries[0].sequence_filename == "seq_21178-21186.jpg"
    assert table.entries[0].middle_row_expected_values == (21_181, 21_182, 21_183)
    assert table.entries[1].sequence_filename == "seq_21169-21177.jpg"


def test_topology_must_match_run_range_size() -> None:
    bounds = SemiAutomaticSequenceBounds(1, 9)

    with pytest.raises(ValueError, match="differs"):
        ExpectedRangeTable.from_bounds(bounds, topology=PageRangeTopology(rows=2, columns=4))


@pytest.mark.parametrize(
    ("proof", "reason"),
    [
        (
            MiddleRowTripleProof(("", "21173", "21174"), (0.95, 0.95, 0.95)),
            MiddleRowUnknownReason.INCOMPLETE_OCR,
        ),
        (
            MiddleRowTripleProof(("2117O", "21173", "21174"), (0.95, 0.95, 0.95)),
            MiddleRowUnknownReason.NON_NUMERIC_OCR,
        ),
        (
            MiddleRowTripleProof(("21172", "21174", "21175"), (0.95, 0.95, 0.95)),
            MiddleRowUnknownReason.INCONSISTENT_TRIPLE,
        ),
        (
            MiddleRowTripleProof(("21172", "21173", "21174"), (0.81, 0.99, 0.99)),
            MiddleRowUnknownReason.LOW_OCR_CONFIDENCE,
        ),
        (
            MiddleRowTripleProof(("21172", "21173", "21174"), (0.89, 0.90, 0.90)),
            MiddleRowUnknownReason.LOW_OCR_CONFIDENCE,
        ),
        (
            MiddleRowTripleProof(
                ("21172", "21173", "21174"),
                (0.95, 0.95, 0.95),
                crop_completeness=(True, False, True),
            ),
            MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED,
        ),
        (
            MiddleRowTripleProof(
                ("21172", "21173", "21174"),
                (0.95, 0.95, 0.95),
                crop_readability=(True, False, True),
            ),
            MiddleRowUnknownReason.LOCAL_BLUR,
        ),
    ],
)
def test_exact_resolver_fails_closed_without_fuzzy_repairs(
    proof: MiddleRowTripleProof,
    reason: MiddleRowUnknownReason,
) -> None:
    result = MiddleRowExactResolver(_table()).resolve(proof)

    assert isinstance(result, UnknownRangeObservation)
    assert result.reason_code is reason


def test_exact_resolver_matches_one_expected_range() -> None:
    result = MiddleRowExactResolver(_table()).resolve(_proof())

    assert isinstance(result, ExactRangeObservation)
    assert result.matched_expected_range.sequence_filename == "seq_21169-21177.jpg"
    assert result.recognized_values == (21_172, 21_173, 21_174)
    assert result.proof_type == "MIDDLE_ROW_TRIPLE_EXACT"


def test_exact_resolver_rejects_consecutive_values_outside_expected_table() -> None:
    result = MiddleRowExactResolver(_table()).resolve(_proof(("90001", "90002", "90003")))

    assert isinstance(result, UnknownRangeObservation)
    assert result.reason_code is MiddleRowUnknownReason.NO_EXPECTED_RANGE_MATCH


def test_exact_resolver_rejects_ambiguous_expected_range_match() -> None:
    table = _table()
    duplicate = replace(
        table.entries[1],
        middle_row_expected_values=table.entries[0].middle_row_expected_values,
    )
    ambiguous_table = replace(table, entries=(table.entries[0], duplicate))

    result = MiddleRowExactResolver(ambiguous_table).resolve(_proof())

    assert isinstance(result, UnknownRangeObservation)
    assert result.reason_code is MiddleRowUnknownReason.AMBIGUOUS_EXPECTED_RANGE


def test_exact_resolver_rejects_matched_entry_outside_run_bounds() -> None:
    table = _table()
    outside_range = SemiAutomaticSelectionRange(90_001, 90_009)
    outside = ExpectedRangeEntry(
        expected_index=0,
        sequence_range=outside_range,
        active_slots=tuple(range(9)),
        middle_row_expected_values=(90_004, 90_005, 90_006),
        is_partial_page=False,
        sequence_filename="seq_90001-90009.jpg",
    )
    inconsistent_table = replace(table, entries=(outside, table.entries[1]))

    result = MiddleRowExactResolver(inconsistent_table).resolve(_proof(("90004", "90005", "90006")))

    assert isinstance(result, UnknownRangeObservation)
    assert result.reason_code is MiddleRowUnknownReason.OUTSIDE_RUN_RANGE


def test_proof_fingerprint_changes_with_versioned_threshold() -> None:
    resolver = MiddleRowExactResolver(_table())
    stricter = MiddleRowExactResolver(
        _table(),
        policy=replace(MiddleRowProofPolicy(), minimum_average_confidence=0.95),
    )

    assert resolver.fingerprint != stricter.fingerprint
