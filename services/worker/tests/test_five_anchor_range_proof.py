from __future__ import annotations

import ast
import inspect
from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection import five_anchor_range_proof as proof_module
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_proof import (
    FIVE_ANCHOR_PROOF_TYPE,
    FiveAnchorExactRangeObservation,
    FiveAnchorExactResolver,
    FiveAnchorExpectedRangeEntry,
    FiveAnchorExpectedRangeTable,
    FiveAnchorProofPolicy,
    FiveAnchorProofPosition,
    FiveAnchorProofUnknownReason,
    FiveAnchorRangeTopology,
    FiveAnchorRecognition,
    FiveAnchorRecognitionProof,
    FiveAnchorUnknownRangeObservation,
)


def _table(
    first: int = 21_169,
    last: int = 21_186,
    *,
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING,
) -> FiveAnchorExpectedRangeTable:
    return FiveAnchorExpectedRangeTable.from_bounds(
        SemiAutomaticSequenceBounds(
            first_sequence_number=first,
            last_sequence_number=last,
            direction=direction,
        )
    )


def _proof(
    values: tuple[str, str, str, str, str] = ("21169", "21171", "21173", "21175", "21177"),
    confidences: tuple[float, float, float, float, float] = (0.96, 0.95, 0.97, 0.95, 0.96),
    *,
    complete: tuple[bool, bool, bool, bool, bool] = (True, True, True, True, True),
    readable: tuple[bool, bool, bool, bool, bool] = (True, True, True, True, True),
) -> FiveAnchorRecognitionProof:
    positions = tuple(FiveAnchorProofPosition)
    return FiveAnchorRecognitionProof(
        observations=(
            FiveAnchorRecognition(
                positions[0], values[0], confidences[0], complete[0], readable[0]
            ),
            FiveAnchorRecognition(
                positions[1], values[1], confidences[1], complete[1], readable[1]
            ),
            FiveAnchorRecognition(
                positions[2], values[2], confidences[2], complete[2], readable[2]
            ),
            FiveAnchorRecognition(
                positions[3], values[3], confidences[3], complete[3], readable[3]
            ),
            FiveAnchorRecognition(
                positions[4], values[4], confidences[4], complete[4], readable[4]
            ),
        )
    )


def _unknown(result: object) -> FiveAnchorUnknownRangeObservation:
    assert isinstance(result, FiveAnchorUnknownRangeObservation)
    return result


def test_expected_table_maps_five_anchor_slots_for_full_and_partial_ranges() -> None:
    full = _table().entries[0]
    partial = _table(first=1, last=5).entries[0]

    assert full.sequence_filename == "seq_21169-21177.jpg"
    assert [full.value_for(position) for position in FiveAnchorProofPosition] == [
        21_169,
        21_171,
        21_173,
        21_175,
        21_177,
    ]
    assert [partial.value_for(position) for position in FiveAnchorProofPosition] == [
        1,
        3,
        5,
        None,
        None,
    ]
    assert partial.is_partial_page is True


def test_three_spanned_matching_anchors_with_center_prove_one_exact_range() -> None:
    result = FiveAnchorExactResolver(_table()).resolve(
        _proof(("21169", "", "21173", "", "21177"), (0.96, 0.0, 0.97, 0.0, 0.96))
    )

    assert isinstance(result, FiveAnchorExactRangeObservation)
    assert result.matched_expected_range.sequence_filename == "seq_21169-21177.jpg"
    assert result.confirmations == (
        FiveAnchorProofPosition.TOP_LEFT,
        FiveAnchorProofPosition.CENTER,
        FiveAnchorProofPosition.BOTTOM_RIGHT,
    )
    assert result.proof_type == FIVE_ANCHOR_PROOF_TYPE


def test_all_five_matching_anchors_are_checked_before_exact_result() -> None:
    result = FiveAnchorExactResolver(_table()).resolve(_proof())

    assert isinstance(result, FiveAnchorExactRangeObservation)
    assert result.confirmations == tuple(FiveAnchorProofPosition)
    assert result.average_confidence == pytest.approx(0.958)


@pytest.mark.parametrize(
    ("proof", "reason"),
    [
        (
            _proof(("21169", "21171", "", "21175", ""), (0.96, 0.95, 0.0, 0.95, 0.0)),
            FiveAnchorProofUnknownReason.INSUFFICIENT_SPANNED_EVIDENCE,
        ),
        (
            _proof(("21169", "", "21173", "", "21177"), (0.88, 0.0, 0.88, 0.0, 0.88)),
            FiveAnchorProofUnknownReason.LOW_OCR_CONFIDENCE,
        ),
        (
            _proof(("", "", "", "", ""), (0.0, 0.0, 0.0, 0.0, 0.0)),
            FiveAnchorProofUnknownReason.INCOMPLETE_OCR,
        ),
        (
            _proof(
                ("21169", "21171", "21173", "21175", "21177"),
                complete=(True, True, False, True, True),
            ),
            FiveAnchorProofUnknownReason.CROP_POSSIBLY_CLIPPED,
        ),
        (
            _proof(
                ("21169", "21171", "21173", "21175", "21177"),
                readable=(True, True, False, True, True),
            ),
            FiveAnchorProofUnknownReason.LOCAL_BLUR,
        ),
        (
            _proof(("90001", "90003", "90005", "90007", "90009")),
            FiveAnchorProofUnknownReason.NO_EXPECTED_RANGE_MATCH,
        ),
    ],
)
def test_proof_fails_closed_for_missing_or_unusable_anchor_evidence(
    proof: FiveAnchorRecognitionProof,
    reason: FiveAnchorProofUnknownReason,
) -> None:
    result = _unknown(FiveAnchorExactResolver(_table()).resolve(proof))

    assert result.reason_code is reason


def test_high_confidence_mismatching_or_non_numeric_anchor_vetoes_exact() -> None:
    resolver = FiveAnchorExactResolver(_table())
    mismatch = _unknown(
        resolver.resolve(
            _proof(("21169", "21172", "21173", "", "21177"), (0.96, 0.96, 0.97, 0.0, 0.96))
        )
    )
    non_numeric = _unknown(
        resolver.resolve(
            _proof(("21169", "oops", "21173", "", "21177"), (0.96, 0.96, 0.97, 0.0, 0.96))
        )
    )

    assert mismatch.reason_code is FiveAnchorProofUnknownReason.CONFLICTING_ANCHOR_VALUES
    assert mismatch.diagnostics == (FiveAnchorProofPosition.TOP_RIGHT.value,)
    assert non_numeric.reason_code is FiveAnchorProofUnknownReason.NON_NUMERIC_OCR
    assert non_numeric.diagnostics == (FiveAnchorProofPosition.TOP_RIGHT.value,)


def test_partial_range_cannot_be_promoted_to_exact() -> None:
    resolver = FiveAnchorExactResolver(_table(first=1, last=5))
    result = _unknown(
        resolver.resolve(_proof(("1", "3", "5", "", ""), (0.96, 0.96, 0.97, 0.0, 0.0)))
    )

    assert result.reason_code is FiveAnchorProofUnknownReason.PARTIAL_RANGE_REQUIRES_MANUAL_REVIEW


def test_collision_between_expected_ranges_stays_ambiguous() -> None:
    table = _table()
    duplicate = replace(table.entries[1], anchor_values=table.entries[0].anchor_values)
    ambiguous = replace(table, entries=(table.entries[0], duplicate))

    result = _unknown(FiveAnchorExactResolver(ambiguous).resolve(_proof()))

    assert result.reason_code is FiveAnchorProofUnknownReason.AMBIGUOUS_EXPECTED_RANGE


def test_descending_bounds_keep_canonical_anchor_values_and_fingerprint_is_versioned() -> None:
    descending = _table(
        first=21_186,
        last=21_169,
        direction=SemiAutomaticSelectionDirection.DESCENDING,
    )
    resolver = FiveAnchorExactResolver(descending)
    stricter = FiveAnchorExactResolver(
        descending,
        policy=replace(FiveAnchorProofPolicy(), minimum_average_confidence=0.95),
    )

    assert descending.entries[0].sequence_filename == "seq_21178-21186.jpg"
    assert descending.entries[0].value_for(FiveAnchorProofPosition.CENTER) == 21_182
    assert resolver.fingerprint != stricter.fingerprint


def test_contract_rejects_invalid_topology_entry_and_observation_order() -> None:
    with pytest.raises(ValueError, match="3x3"):
        FiveAnchorRangeTopology(rows=2, columns=4)
    with pytest.raises(ValueError, match="stable anchor order"):
        FiveAnchorRecognitionProof(
            observations=tuple(reversed(_proof().observations))  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="full range"):
        FiveAnchorExpectedRangeEntry(
            expected_index=0,
            sequence_range=SemiAutomaticSelectionRange(1, 9),
            anchor_values=(
                (FiveAnchorProofPosition.TOP_LEFT, 1),
                (FiveAnchorProofPosition.TOP_RIGHT, 3),
                (FiveAnchorProofPosition.CENTER, None),
                (FiveAnchorProofPosition.BOTTOM_LEFT, 7),
                (FiveAnchorProofPosition.BOTTOM_RIGHT, 9),
            ),
            is_partial_page=False,
            sequence_filename="seq_1-9.jpg",
        )


def test_proof_module_has_no_image_runtime_filename_or_heavy_pipeline_dependency() -> None:
    tree = ast.parse(inspect.getsource(proof_module))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {"hashlib", "json", "re"}
    assert imported_from_modules == {
        "__future__",
        "contracts",
        "dataclasses",
        "enum",
        "statistics",
        "typing",
    }
    source = inspect.getsource(proof_module)
    assert "expected_filename" not in source
    assert "source_index" not in source
    assert "open(" not in source
    assert "cv2" not in source
    assert "paddle" not in source.casefold()
