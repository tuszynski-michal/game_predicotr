from __future__ import annotations

from uuid import uuid4

import pytest
from game_predictor_worker.symbols.reference_library_writer import (
    LIBRARY_CONFIDENCE,
    MODEL_VERSION,
    ReferenceLibraryWriteError,
    TargetCell,
    predictions_digest,
    revert_checksum,
    rewrite_predictions,
)


def _predictions() -> list[dict[str, object]]:
    return [
        {
            "rowIndex": index // 5,
            "columnIndex": index % 5,
            "symbolCode": "ARBUZ" if index == 7 else "WISNIA",
            "confidence": 0.5,
            "alternatives": [{"symbolCode": "ARBUZ", "confidence": 0.5}],
            "virtualCell": {"renderSpec": {"cellIndex": index}},
        }
        for index in range(15)
    ]


def _target(index: int = 7, old: str = "ARBUZ", new: str = "CYTRYNA") -> TargetCell:
    return TargetCell(uuid4(), index, "a" * 64, old, new, 7, 7)


def test_only_target_cells_are_rewritten_and_provenance_is_kept() -> None:
    original = _predictions()

    rewritten = rewrite_predictions(original, [_target()])

    assert rewritten[7]["symbolCode"] == "CYTRYNA"
    assert rewritten[7]["confidence"] == LIBRARY_CONFIDENCE
    assert rewritten[7]["alternatives"] == [
        {"symbolCode": "CYTRYNA", "confidence": LIBRARY_CONFIDENCE}
    ]
    assert rewritten[7]["virtualCell"] == original[7]["virtualCell"]
    assert rewritten[7]["referenceLibrary"]["version"] == MODEL_VERSION
    assert rewritten[7]["referenceLibrary"]["previousSymbolCode"] == "ARBUZ"
    assert [entry for index, entry in enumerate(rewritten) if index != 7] == [
        entry for index, entry in enumerate(original) if index != 7
    ]
    assert original[7]["symbolCode"] == "ARBUZ"


def test_confirmation_keeps_the_symbol_and_records_the_library() -> None:
    rewritten = rewrite_predictions(_predictions(), [_target(new="ARBUZ")])

    assert rewritten[7]["symbolCode"] == "ARBUZ"
    assert rewritten[7]["confidence"] == LIBRARY_CONFIDENCE


def test_prediction_drift_and_unknown_cells_are_errors() -> None:
    with pytest.raises(ReferenceLibraryWriteError) as drift:
        rewrite_predictions(_predictions(), [_target(old="GWIAZDA")])
    with pytest.raises(ReferenceLibraryWriteError) as missing:
        rewrite_predictions(_predictions()[:10], [_target(index=12, old="WISNIA")])
    duplicated = _predictions() + [_predictions()[0]]
    with pytest.raises(ReferenceLibraryWriteError) as twice:
        rewrite_predictions(duplicated, [_target()])

    assert drift.value.code == "SYMBOL_REFERENCE_PREDICTION_DRIFT"
    assert missing.value.code == "SYMBOL_REFERENCE_PREDICTION_INVALID"
    assert twice.value.code == "SYMBOL_REFERENCE_PREDICTION_INVALID"


def test_prediction_digest_ignores_key_order_but_not_values() -> None:
    first = [{"a": 1, "b": 2}]
    reordered = [{"b": 2, "a": 1}]

    assert predictions_digest(first) == predictions_digest(reordered)
    assert predictions_digest(first) != predictions_digest([{"a": 1, "b": 3}])


def test_revert_checksum_is_distinct_and_valid() -> None:
    library = "b" * 64

    checksum = revert_checksum(library)

    assert checksum != library
    assert len(checksum) == 64
    assert checksum == revert_checksum(library)
    assert checksum != revert_checksum("c" * 64)
