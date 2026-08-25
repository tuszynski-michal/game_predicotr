from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.images.grid_symbol_diagnosis import (
    CellPrediction,
    DiagnosticBoard,
    GridSymbolDiagnosisError,
    build_diagnostic_document,
    document_checksum_sha256,
    production_preprocess_rgb,
)
from game_predictor_worker.images.symbol_classifier import load_image_tensor
from PIL import Image

MODEL = "a" * 64


def _board(
    *,
    board_id: str = "board",
    baseline: str = "star",
    corrected: str = "lemon",
) -> DiagnosticBoard:
    expected = ("lemon",) * 15
    return DiagnosticBoard(
        board_id=board_id,
        sequence_number=1 if board_id == "board" else 2,
        position_index=0,
        source_checksum_sha256="b" * 64,
        source_relative_path="seq_1-9.jpg",
        staging_label="1-19809",
        baseline_geometry_version="board-cell-crops-v18-source-direct-validated-v1",
        baseline_cropper_version="board-cell-crops-v18-source-direct-validated-v1",
        corrected_geometry_version="board-cell-geometry-v19-multi-point-source-direct-v1",
        corrected_cropper_version="board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1",
        baseline_model_fingerprint=MODEL,
        comparison_model_fingerprint=MODEL,
        expected_symbols=expected,
        baseline_predictions=tuple(CellPrediction(baseline, 0.9) for _ in range(15)),
        corrected_predictions=tuple(CellPrediction(corrected, 0.8) for _ in range(15)),
    )


def test_ab_report_measures_symbol_board_and_manual_correction_delta() -> None:
    document = build_diagnostic_document((_board(),), comparison_model_fingerprint=MODEL)

    summary = document["summary"]
    assert summary["delta"] == {
        "meanManualCorrectionsPerBoard": -15.0,
        "symbolAccuracy": 1.0,
        "wholeBoardAccuracy": 1.0,
    }
    assert summary["baseline"]["symbolAccuracy"] == 0.0
    assert summary["baseline"]["wholeBoardAccuracy"] == 0.0
    assert summary["baseline"]["meanManualCorrectionsPerBoard"] == 15.0
    assert summary["baseline"]["confidence"] == {"meanCorrect": None, "meanIncorrect": 0.9}
    assert summary["corrected"]["symbolAccuracy"] == 1.0
    assert summary["corrected"]["wholeBoardAccuracy"] == 1.0
    assert summary["corrected"]["meanManualCorrectionsPerBoard"] == 0.0
    assert summary["corrected"]["confidence"] == {"meanCorrect": 0.8, "meanIncorrect": None}
    assert summary["byStaging"]["1-19809"]["baseline"] == summary["baseline"]
    assert summary["byStaging"]["1-19809"]["corrected"] == summary["corrected"]


def test_report_is_deterministic_regardless_of_input_order() -> None:
    first = _board(board_id="first")
    second = _board(board_id="second")

    assert document_checksum_sha256(
        build_diagnostic_document((first, second), comparison_model_fingerprint=MODEL)
    ) == document_checksum_sha256(
        build_diagnostic_document((second, first), comparison_model_fingerprint=MODEL)
    )


def test_report_rejects_baseline_from_another_model() -> None:
    board = _board()
    mismatched = replace(board, baseline_model_fingerprint="c" * 64)

    with pytest.raises(GridSymbolDiagnosisError) as error:
        build_diagnostic_document((mismatched,), comparison_model_fingerprint=MODEL)

    assert error.value.code == "GRID_SYMBOL_DIAGNOSIS_MODEL_MISMATCH"


def test_production_preprocess_matches_training_contract_for_native_model_crop(
    tmp_path: Path,
) -> None:
    rgb = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    path = tmp_path / "native.png"
    Image.fromarray(rgb, mode="RGB").save(path)

    training = load_image_tensor(path, 64).numpy()
    production = production_preprocess_rgb(rgb, input_size=64)

    assert np.array_equal(production, training)
