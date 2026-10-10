from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
    cold_start_unclassified_symbol_snapshot,
)
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPredictionError,
    ManualBoardCellSymbolPredictor,
    RenderedBoardCell,
)
from game_predictor_worker.images.symbol_onnx import OnnxInference


class CapturingAdapter:
    def __init__(self) -> None:
        self.inputs: list[np.ndarray] = []

    def infer(self, images: np.ndarray) -> OnnxInference:
        self.inputs.append(images)
        logits = np.zeros((15, 2), dtype=np.float32)
        logits[:, 0] = np.arange(15, dtype=np.float32) % 2
        logits[:, 1] = 1 - logits[:, 0]
        shifted = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return OnnxInference(
            logits=logits,
            probabilities=probabilities.astype(np.float32),
            class_indexes=np.argmax(logits, axis=1).astype(np.int64),
        )


def _snapshot() -> SymbolModelJobSnapshot:
    return SymbolModelJobSnapshot(
        iteration_id=uuid4(),
        model_version="manual-pinned-model-v1",
        manifest_checksum_sha256="a" * 64,
        onnx_checksum_sha256="b" * 64,
        onnx_relative_path="models/manual/model.onnx",
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=("lemon", "seven"),
        input_size=64,
        temperature=0.05,
    )


def _cells(size: int = 64, *, skip: frozenset[int] = frozenset()) -> list[RenderedBoardCell]:
    return [
        RenderedBoardCell(
            row_index=index // 5,
            column_index=index % 5,
            rgb=np.full((size, size, 3), 10 * index, dtype=np.uint8),
        )
        for index in range(15)
        if index not in skip
    ]


def test_manual_prediction_uses_exact_pinned_model_and_row_major_renders(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)
    adapter = _SizedCapturingAdapter()
    predictor._cache[snapshot.inference_fingerprint] = adapter  # type: ignore[attr-defined]

    result = predictor.predict_rendered_cells(_cells(), snapshot)

    assert result.model_iteration_id == str(snapshot.iteration_id)
    assert result.model_manifest_checksum_sha256 == snapshot.manifest_checksum_sha256
    assert result.model_version == snapshot.model_version
    assert result.temperature_applied == 0.50
    assert [(cell["rowIndex"], cell["columnIndex"]) for cell in result.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert len(adapter.inputs) == 1
    assert adapter.inputs[0].shape == (15, 3, 64, 64)
    assert adapter.inputs[0].dtype == np.float32


def test_manual_prediction_resizes_renders_to_the_pinned_model_size(tmp_path: Path) -> None:
    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)
    adapter = _SizedCapturingAdapter()
    predictor._cache[snapshot.inference_fingerprint] = adapter  # type: ignore[attr-defined]

    predictor.predict_rendered_cells(_cells(48), snapshot)

    assert adapter.inputs[0].shape == (15, 3, 64, 64)


def test_manual_prediction_rejects_unordered_cells(tmp_path: Path) -> None:
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)

    with pytest.raises(ManualBoardCellSymbolPredictionError) as error:
        predictor.predict_rendered_cells(list(reversed(_cells())), _snapshot())

    assert error.value.code == "IMAGE_BOARD_CELL_MANUAL_PREDICTION_ORDER_INVALID"


class _SizedCapturingAdapter(CapturingAdapter):
    def infer(self, images: np.ndarray) -> OnnxInference:
        self.inputs.append(images)
        count = images.shape[0]
        logits = np.zeros((count, 2), dtype=np.float32)
        logits[:, 0] = np.arange(count, dtype=np.float32) % 2
        logits[:, 1] = 1 - logits[:, 0]
        shifted = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return OnnxInference(
            logits=logits,
            probabilities=probabilities.astype(np.float32),
            class_indexes=np.argmax(logits, axis=1).astype(np.int64),
        )


def test_manual_prediction_classifies_only_rendered_available_cells(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)
    adapter = _SizedCapturingAdapter()
    predictor._cache[snapshot.inference_fingerprint] = adapter  # type: ignore[attr-defined]

    result = predictor.predict_rendered_cells(_cells(skip=frozenset({2, 7})), snapshot)

    assert [(cell["rowIndex"], cell["columnIndex"]) for cell in result.cells] == [
        (index // 5, index % 5) for index in range(15) if index not in {2, 7}
    ]
    assert all("symbolCode" in cell for cell in result.cells)
    # Only the 13 rendered cells reach the model, never a synthesized crop.
    assert adapter.inputs[0].shape == (13, 3, 64, 64)


def test_manual_prediction_for_cold_start_import_returns_unknown_cells_without_onnx(
    tmp_path: Path,
) -> None:
    snapshot = cold_start_unclassified_symbol_snapshot(("lemon", "seven"))
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)

    result = predictor.predict_rendered_cells(_cells(), snapshot)

    assert result.model_version == snapshot.model_version
    assert result.model_manifest_checksum_sha256 == snapshot.manifest_checksum_sha256
    assert [(cell["rowIndex"], cell["columnIndex"]) for cell in result.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert {cell["symbolCode"] for cell in result.cells} == {"?"}
    assert predictor._cache == {}
