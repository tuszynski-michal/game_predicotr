from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    ManualBoardCellGeometryPreviewer,
)
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPredictionError,
    ManualBoardCellSymbolPredictor,
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


def _preview(tmp_path: Path):
    rgb = np.full((420, 620, 3), 128, dtype=np.uint8)
    encoded, payload = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert encoded
    content = bytes(payload)
    source = tmp_path / "source.png"
    source.write_bytes(content)
    return ManualBoardCellGeometryPreviewer().preview(
        source_path=source,
        expected_source_sha256=hashlib.sha256(content).hexdigest(),
        review_item_id="pending-id",
        source_order_index=1,
        source_image_id="source-id",
        source_image_relative_path="sources/source.png",
        source_group="import-id",
        sequence_number=64,
        position_index=0,
        lattice_bounds_quad=((60.0, 50.0), (560.0, 50.0), (560.0, 350.0), (60.0, 350.0)),
        corrected_by="local-owner",
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        command_checksum_sha256="c" * 64,
    )


def test_manual_prediction_uses_exact_pinned_model_and_row_major_crops(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)
    adapter = CapturingAdapter()
    predictor._cache[snapshot.inference_fingerprint] = adapter  # type: ignore[attr-defined]

    result = predictor.predict(_preview(tmp_path), snapshot)

    assert result.model_iteration_id == str(snapshot.iteration_id)
    assert result.model_manifest_checksum_sha256 == snapshot.manifest_checksum_sha256
    assert result.model_version == snapshot.model_version
    assert result.temperature_applied == 0.50
    assert len(result.cells) == 15
    assert [(cell["rowIndex"], cell["columnIndex"]) for cell in result.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert len(adapter.inputs) == 1
    assert adapter.inputs[0].shape == (15, 3, 64, 64)
    assert adapter.inputs[0].dtype == np.float32


def test_manual_prediction_fails_closed_for_wrong_model_input_size(tmp_path: Path) -> None:
    preview = _preview(tmp_path)
    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)

    with pytest.raises(ManualBoardCellSymbolPredictionError) as error:
        predictor.predict(preview, replace(snapshot, input_size=32))

    assert error.value.code == "IMAGE_BOARD_CELL_MANUAL_PREDICTION_INPUT_INVALID"
