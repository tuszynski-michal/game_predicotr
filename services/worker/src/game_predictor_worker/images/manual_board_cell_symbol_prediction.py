"""Inference for the rendered cells of one manually resolved deferred board.

Since D-467 (TASK-0790) a deferred board is resolved only through the virtual
source path: its cells are rendered in memory from the immutable source and
classified with exactly the symbol model pinned to the originating import.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from numpy.typing import NDArray

from .symbol_model_release import SymbolModelReleaseError, build_symbol_predictions
from .symbol_onnx import LocalSymbolOnnxAdapter, SymbolOnnxError, preprocess_rgb_batch


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


@dataclass(frozen=True, slots=True)
class RenderedBoardCell:
    """One rendered, available board cell in row-major order."""

    row_index: int
    column_index: int
    rgb: NDArray[np.uint8]


class ManualBoardCellSymbolPredictor:
    """Use exactly the model snapshot pinned to the originating import."""

    def __init__(self, repository_root: Path, artifact_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._artifact_root = artifact_root.resolve()
        self._cache: dict[str, LocalSymbolOnnxAdapter] = {}

    def predict_rendered_cells(
        self,
        cells: Sequence[RenderedBoardCell],
        snapshot: SymbolModelJobSnapshot,
    ) -> ManualBoardCellSymbolPrediction:
        """Classify exactly the given cells; unavailable cells are never rendered.

        The result has one prediction per input cell, in the input order, like
        the import pipeline's predictions of a virtual board.
        """

        positions = [(cell.row_index, cell.column_index) for cell in cells]
        if positions != sorted(positions) or len(set(positions)) != len(positions):
            raise ManualBoardCellSymbolPredictionError(
                "IMAGE_BOARD_CELL_MANUAL_PREDICTION_ORDER_INVALID",
                "Manual geometry cells are not unique row-major input.",
            )
        temperature = max(0.50, snapshot.temperature)
        if snapshot.inference_mode == "unclassified" or not cells:
            # A cold-start import has no ONNX model; mirror the import pipeline's
            # "?" cells instead of loading the placeholder artifact path.
            return self._result(
                snapshot,
                temperature,
                tuple(
                    {
                        "alternatives": [{"confidence": 1.0, "symbolCode": "?"}],
                        "columnIndex": column,
                        "confidence": 0.0,
                        "rowIndex": row,
                        "symbolCode": "?",
                    }
                    for row, column in positions
                ),
            )
        try:
            inference = self._adapter(snapshot).infer(
                preprocess_rgb_batch(
                    [cell.rgb for cell in cells],
                    input_size=snapshot.input_size,
                )
            )
            predictions = build_symbol_predictions(
                inference.logits,
                temperature=temperature,
                class_codes=snapshot.class_codes,
                alternative_limit=3,
            )
        except (SymbolOnnxError, SymbolModelReleaseError) as error:
            raise ManualBoardCellSymbolPredictionError(
                f"IMAGE_{error.code}",
                str(error),
            ) from error
        if len(predictions) != len(cells):
            raise ManualBoardCellSymbolPredictionError(
                "IMAGE_BOARD_CELL_MANUAL_PREDICTION_COUNT_INVALID",
                "The pinned model returned a different number of predictions.",
            )
        return self._result(
            snapshot,
            temperature,
            tuple(
                {**prediction.to_dict(), "columnIndex": column, "rowIndex": row}
                for (row, column), prediction in zip(positions, predictions, strict=True)
            ),
        )

    @staticmethod
    def _result(
        snapshot: SymbolModelJobSnapshot,
        temperature: float,
        cells: tuple[dict[str, object], ...],
    ) -> ManualBoardCellSymbolPrediction:
        return ManualBoardCellSymbolPrediction(
            model_iteration_id=None
            if snapshot.iteration_id is None
            else str(snapshot.iteration_id),
            model_manifest_checksum_sha256=snapshot.manifest_checksum_sha256,
            model_version=snapshot.model_version,
            temperature_applied=temperature,
            cells=cells,
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
    "RenderedBoardCell",
]
