"""neural_grid engine: screen decoding, board nodes, projective grid fit, GeometryEngine.

Torch-free. The same ``NeuralGridEngine`` runs with torch runners during training
(checkpoint selection) and with ONNX Runtime runners after export, so evaluation and
inference share one decoding path. The number of boards follows from the screen heatmap
peaks; nothing assumes nine boards.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.geometry_core.inference import (
    BoardDetection as BoardDetection,
)
from game_predictor_worker.geometry_core.inference import (
    DecodeSettings as DecodeSettings,
)
from game_predictor_worker.geometry_core.inference import (
    GridFit as GridFit,
)
from game_predictor_worker.geometry_core.inference import (
    NeuralGridEngine as CoreNeuralGridEngine,
)
from game_predictor_worker.geometry_core.inference import (
    ScreenDetection as ScreenDetection,
)
from game_predictor_worker.geometry_core.inference import (
    _all_points_fit as _all_points_fit,
)
from game_predictor_worker.geometry_core.inference import (
    decode_screen as decode_screen,
)
from game_predictor_worker.geometry_core.inference import (
    file_sha256 as file_sha256,
)
from game_predictor_worker.geometry_core.inference import (
    fit_grid as fit_grid,
)
from game_predictor_worker.geometry_core.inference import (
    onnx_engine as core_onnx_engine,
)
from game_predictor_worker.geometry_core.inference import (
    reading_order as reading_order,
)
from game_predictor_worker.geometry_core.lattice import structurally_valid as structurally_valid

from .contracts import (
    Board as Board,
)
from .contracts import (
    GeometryResult as GeometryResult,
)
from .contracts import (
    Point as Point,
)
from .contracts import (
    Topology as Topology,
)
from .geometry import cell_quads as cell_quads
from .neural_grid_data import (
    CELL_COUNT as CELL_COUNT,
)
from .neural_grid_data import (
    LATTICE as LATTICE,
)
from .neural_grid_data import (
    ByteImage as ByteImage,
)
from .neural_grid_data import (
    FloatArray as FloatArray,
)
from .neural_grid_data import (
    PhotoSample as PhotoSample,
)
from .neural_grid_data import (
    board_rectifier as board_rectifier,
)
from .neural_grid_data import (
    corners as corners,
)
from .neural_grid_data import (
    crop_board as crop_board,
)
from .neural_grid_data import (
    grid_from_quad as grid_from_quad,
)
from .neural_grid_data import (
    prefetch as prefetch,
)
from .neural_grid_data import (
    quad_is_usable as quad_is_usable,
)
from .neural_grid_data import (
    screen_input as screen_input,
)
from .neural_grid_data import (
    transform_points as transform_points,
)
from .neural_grid_metrics import (
    PhotoEvaluation as PhotoEvaluation,
)
from .neural_grid_metrics import (
    evaluate_photo as evaluate_photo,
)
from .neural_grid_metrics import (
    quad_iou as quad_iou,
)
from .neural_grid_metrics import (
    summarize as summarize,
)
from .neural_grid_protocol import (
    MODEL_VERSION as MODEL_VERSION,
)
from .neural_grid_protocol import (
    BoardPreset as BoardPreset,
)
from .neural_grid_protocol import (
    FitPreset as FitPreset,
)
from .neural_grid_protocol import (
    Preset as Preset,
)
from .neural_grid_protocol import (
    ScreenPreset as ScreenPreset,
)

GATE_REASON: Final = "NEURAL_GRID_GATE_UNCALIBRATED"
ScreenRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray]]
BoardRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray, FloatArray]]


class NeuralGridEngine(CoreNeuralGridEngine):
    """Two-stage engine behind the ``GeometryEngine`` contract (``detect``)."""

    def detect(self, source_id: str, rgb: NDArray[np.uint8], topology: Topology) -> GeometryResult:
        result = GeometryResult(
            source_id=source_id,
            topology=topology,
            model_version=self.model_version,
            status="unsupported",
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
        )
        if topology.columns != 5 or topology.rows != 3:
            result.reasons = ["NEURAL_GRID_TOPOLOGY_UNSUPPORTED"]
            return result
        detections = [d for d in self.analyse(np.asarray(rgb, np.uint8)) if d.nodes is not None]
        for index, detection in enumerate(detections):
            assert detection.nodes is not None
            board = Board(
                position_index=index,
                status="needs_review",
                nodes=[
                    Point(x=float(x), y=float(y), provenance="model") for x, y in detection.nodes
                ],
                reasons=[GATE_REASON, *detection.reasons],
            )
            try:
                cell_quads(board, topology)
            except ValueError as error:
                board.reasons.append(str(error))
            result.boards.append(board)
        result.status = "detected" if result.boards else "failed"
        if not result.boards:
            result.reasons = ["NEURAL_GRID_NO_BOARD"]
        return result


def evaluate_samples(
    analyse: Callable[[ByteImage], list[FloatArray]],
    samples: list[PhotoSample],
    *,
    heartbeat: Callable[[], None] | None = None,
    decode_workers: int = 4,
) -> tuple[dict[str, Any], list[PhotoEvaluation]]:
    """Run any engine (``analyse`` returns predicted 24-node grids) through the metrics."""

    photos: list[PhotoEvaluation] = []
    started = time.perf_counter()
    for sample, rgb in prefetch(samples, decode_workers):
        if heartbeat is not None:
            heartbeat()
        labels = [board.nodes for board in sample.boards]
        if isinstance(rgb, Exception):
            predicted: list[tuple[FloatArray, bool]] = []
        else:
            predicted = [(nodes, structurally_valid(nodes)) for nodes in analyse(rgb)]
        photos.append(evaluate_photo(sample.image_id, sample.level, labels, predicted))
    summary = summarize(photos)
    summary["evaluation_seconds"] = time.perf_counter() - started
    return summary, photos


def engine_grids(engine: NeuralGridEngine) -> Callable[[ByteImage], list[FloatArray]]:
    def analyse(rgb: ByteImage) -> list[FloatArray]:
        return [d.nodes for d in engine.analyse(rgb) if d.nodes is not None]

    return analyse


def geometry_engine_grids(engine: Any) -> Callable[[ByteImage], list[FloatArray]]:
    """Adapter for any ``GeometryEngine`` (e.g. the lab baseline) to the evaluator."""

    def analyse(rgb: ByteImage) -> list[FloatArray]:
        result = engine.detect("evaluation", rgb, Topology())
        return [
            np.array([(p.x, p.y) for p in board.nodes], np.float32)
            for board in result.boards
            if len(board.nodes) == 24
        ]

    return analyse


def label_reference(sample: PhotoSample) -> list[FloatArray]:
    """The snapshot labels themselves as predictions (production output for level B)."""

    return [board.nodes for board in sample.boards]


# --- ONNX Runtime -----------------------------------------------------------------------------


BUNDLE_FILE: Final = "bundle.json"


__all__ = [
    "CELL_COUNT",
    "BoardDetection",
    "DecodeSettings",
    "GridFit",
    "NeuralGridEngine",
    "corners",
    "decode_screen",
    "evaluate_samples",
    "fit_grid",
    "onnx_engine",
]


def onnx_engine(bundle_directory: Path, threads: int | None = None) -> NeuralGridEngine:
    # Keep the lab GeometryEngine adapter while using exactly the worker runtime.
    bundle = json.loads((bundle_directory / BUNDLE_FILE).read_text(encoding="utf-8"))
    Preset.model_validate(bundle["preset"])
    core = core_onnx_engine(bundle_directory, threads)
    return NeuralGridEngine(
        core.screen_runner, core.board_runner, core.settings, core.model_version, core.board_batch
    )
