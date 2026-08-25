"""Inference for one checksum-bound manual v19 board-cell correction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)

from .manual_board_cell_geometry_preview import ManualBoardCellGeometryPreview
from .symbol_model_release import SymbolModelReleaseError, build_symbol_predictions
from .symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError


class ManualBoardCellSymbolPredictionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ManualBoardCellSymbolPrediction:
    model_iteration_id: str | None
    model_manifest_checksum_sha256: str
    model_version: str
    temperature_applied: float
    cells: tuple[dict[str, object], ...]


class ManualBoardCellSymbolPredictor:
    """Use exactly the model snapshot pinned to the originating import."""

    def __init__(self, repository_root: Path, artifact_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._artifact_root = artifact_root.resolve()
        self._cache: dict[str, LocalSymbolOnnxAdapter] = {}

    def predict(
        self,
        preview: ManualBoardCellGeometryPreview,
        snapshot: SymbolModelJobSnapshot,
    ) -> ManualBoardCellSymbolPrediction:
        if len(preview.cells) != 15 or preview.cell_output_size != snapshot.input_size:
            raise ManualBoardCellSymbolPredictionError(
                "IMAGE_BOARD_CELL_MANUAL_PREDICTION_INPUT_INVALID",
                "Manual geometry must provide exactly 15 crops at the pinned model size.",
            )
        tensors: list[np.ndarray] = []
        expected_order = [(row, column) for row in range(3) for column in range(5)]
        if [(cell.row_index, cell.column_index) for cell in preview.cells] != expected_order:
            raise ManualBoardCellSymbolPredictionError(
                "IMAGE_BOARD_CELL_MANUAL_PREDICTION_ORDER_INVALID",
                "Manual geometry crops are not complete row-major input.",
            )
        for cell in preview.cells:
            encoded = np.frombuffer(cell.png, dtype=np.uint8)
            bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if bgr is None or bgr.shape[:2] != (snapshot.input_size, snapshot.input_size):
                raise ManualBoardCellSymbolPredictionError(
                    "IMAGE_BOARD_CELL_MANUAL_PREDICTION_DECODE_FAILED",
                    "A manual geometry crop cannot be decoded at the pinned model size.",
                )
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            normalized = rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
            tensors.append(((normalized - 0.5) / 0.5).astype(np.float32))
        try:
            inference = self._adapter(snapshot).infer(np.stack(tensors).astype(np.float32))
            predictions = build_symbol_predictions(
                inference.logits,
                temperature=max(0.50, snapshot.temperature),
                class_codes=snapshot.class_codes,
                alternative_limit=3,
            )
        except (SymbolOnnxError, SymbolModelReleaseError) as error:
            raise ManualBoardCellSymbolPredictionError(
                f"IMAGE_{error.code}",
                str(error),
            ) from error
        return ManualBoardCellSymbolPrediction(
            model_iteration_id=None
            if snapshot.iteration_id is None
            else str(snapshot.iteration_id),
            model_manifest_checksum_sha256=snapshot.manifest_checksum_sha256,
            model_version=snapshot.model_version,
            temperature_applied=max(0.50, snapshot.temperature),
            cells=tuple(
                {
                    **prediction.to_dict(),
                    "columnIndex": index % 5,
                    "rowIndex": index // 5,
                }
                for index, prediction in enumerate(predictions)
            ),
        )

    def _adapter(self, snapshot: SymbolModelJobSnapshot) -> LocalSymbolOnnxAdapter:
        cached = self._cache.get(snapshot.inference_fingerprint)
        if cached is not None:
            return cached
        root = (
            self._repository_root
            if snapshot.storage_root is SymbolModelStorageRoot.REPOSITORY
            else self._artifact_root
        )
        relative = PurePosixPath(snapshot.onnx_relative_path)
        model_path = root.joinpath(*relative.parts).resolve()
        if not model_path.is_relative_to(root):
            raise ManualBoardCellSymbolPredictionError(
                "IMAGE_SYMBOL_MODEL_PATH_INVALID",
                "The pinned symbol model path escapes its storage root.",
            )
        try:
            adapter = LocalSymbolOnnxAdapter(
                model_path,
                expected_sha256=snapshot.onnx_checksum_sha256,
                class_codes=snapshot.class_codes,
                input_size=snapshot.input_size,
            )
        except SymbolOnnxError as error:
            raise ManualBoardCellSymbolPredictionError(
                f"IMAGE_{error.code}",
                str(error),
            ) from error
        self._cache[snapshot.inference_fingerprint] = adapter
        return adapter


__all__ = [
    "ManualBoardCellSymbolPrediction",
    "ManualBoardCellSymbolPredictionError",
    "ManualBoardCellSymbolPredictor",
]
