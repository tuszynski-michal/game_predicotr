"""neural_grid engine: screen decoding, board nodes, projective grid fit, GeometryEngine.

Torch-free. The same ``NeuralGridEngine`` runs with torch runners during training
(checkpoint selection) and with ONNX Runtime runners after export, so evaluation and
inference share one decoding path. The number of boards follows from the screen heatmap
peaks; nothing assumes nine boards.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from .contracts import Board, GeometryResult, Point, Topology
from .geometry import cell_quads
from .neural_grid_data import (
    CELL_COUNT,
    LATTICE,
    ByteImage,
    FloatArray,
    PhotoSample,
    board_rectifier,
    corners,
    crop_board,
    grid_from_quad,
    prefetch,
    quad_is_usable,
    screen_input,
    transform_points,
)
from .neural_grid_metrics import PhotoEvaluation, evaluate_photo, quad_iou, summarize
from .neural_grid_protocol import MODEL_VERSION, BoardPreset, FitPreset, Preset, ScreenPreset

GATE_REASON: Final = "NEURAL_GRID_GATE_UNCALIBRATED"
ScreenRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray]]
BoardRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray, FloatArray]]


@dataclass(frozen=True, slots=True)
class ScreenDetection:
    score: float
    quad: FloatArray  # (4, 2) canvas pixels, TL TR BR BL


def decode_screen(
    heat: FloatArray, offsets: FloatArray, screen: ScreenPreset
) -> list[ScreenDetection]:
    """Peaks of the centre heatmap (3 x 3 maximum, threshold, top-k) and quad NMS."""

    heat = np.asarray(heat, dtype=np.float32)
    dilated = cv2.dilate(heat, np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero((heat >= dilated) & (heat >= screen.decode_threshold))
    order = np.argsort(-heat[ys, xs], kind="stable")[: screen.top_k]
    candidates = []
    for index in order:
        y, x = int(ys[index]), int(xs[index])
        centre = np.array([(x + 0.5) * screen.stride, (y + 0.5) * screen.stride], np.float32)
        quad = centre + offsets[:, y, x].reshape(4, 2) * screen.offset_scale
        candidates.append(ScreenDetection(float(heat[y, x]), quad.astype(np.float32)))
    kept: list[ScreenDetection] = []
    for candidate in candidates:
        if not quad_is_usable(candidate.quad, min_area=4.0):
            continue
        if all(quad_iou(candidate.quad, other.quad) <= screen.nms_iou for other in kept):
            kept.append(candidate)
    return kept


@dataclass(frozen=True, slots=True)
class GridFit:
    nodes: FloatArray
    inliers: NDArray[np.bool_]
    residual: float  # RMS inlier error / scale
    max_inlier_error: float
    ok: bool


def _all_points_fit(nodes: FloatArray, scale: float) -> GridFit:
    """Fallback when RANSAC finds too few inliers: least squares on all 24 nodes, not ok."""

    matrix, _ = cv2.findHomography(LATTICE, nodes, 0)
    if matrix is None:
        return GridFit(nodes, np.zeros(24, bool), float("inf"), float("inf"), False)
    fitted = transform_points(LATTICE, np.asarray(matrix, np.float64))
    errors = np.linalg.norm(fitted - nodes, axis=1)
    if not np.isfinite(fitted).all():
        return GridFit(nodes, np.zeros(24, bool), float("inf"), float("inf"), False)
    return GridFit(
        fitted,
        np.zeros(24, bool),
        float(np.sqrt(np.mean(errors**2)) / max(scale, 1e-6)),
        float(errors.max() / max(scale, 1e-6)),
        False,
    )


def fit_grid(nodes: FloatArray, scale: float, fit: FitPreset) -> GridFit:
    """RANSAC homography lattice -> nodes, least squares on inliers, inlier refresh.

    ``ok`` is false when fewer than ``min_inliers`` nodes agree; the nodes are then the
    least-squares fit on all 24 nodes (or the input when even that fails) and the caller
    marks the board. The residual (RMS inlier error / ``scale``) is the fit confidence.
    """

    nodes = np.asarray(nodes, dtype=np.float32).reshape(24, 2)
    threshold = max(fit.inlier_threshold * scale, 1e-3)
    if not np.isfinite(nodes).all():
        return GridFit(nodes, np.zeros(24, bool), float("inf"), float("inf"), False)
    matrix, mask = cv2.findHomography(
        LATTICE, nodes, cv2.RANSAC, threshold, maxIters=2000, confidence=0.999
    )
    if matrix is None or mask is None or int(mask.sum()) < fit.min_inliers:
        return _all_points_fit(nodes, scale)
    inliers = mask.ravel().astype(bool)
    for _ in range(2):
        refit, _ = cv2.findHomography(LATTICE[inliers], nodes[inliers], 0)
        if refit is None:
            break
        matrix = refit
        errors = np.linalg.norm(transform_points(LATTICE, matrix) - nodes, axis=1)
        refreshed = errors <= threshold
        if refreshed.sum() < fit.min_inliers or np.array_equal(refreshed, inliers):
            break
        inliers = refreshed
    fitted = transform_points(LATTICE, np.asarray(matrix, np.float64))
    errors = np.linalg.norm(fitted - nodes, axis=1)[inliers]
    ok = bool(np.isfinite(fitted).all() and inliers.sum() >= fit.min_inliers)
    return GridFit(
        fitted,
        inliers,
        float(np.sqrt(np.mean(errors**2)) / max(scale, 1e-6)),
        float(errors.max() / max(scale, 1e-6)),
        ok,
    )


@dataclass(slots=True)
class BoardDetection:
    score: float
    screen_quad: FloatArray  # source pixels
    raw_nodes: FloatArray | None = None  # stage 2 nodes, source pixels
    nodes: FloatArray | None = None  # fitted grid, source pixels
    node_peak: FloatArray | None = None
    visibility: FloatArray | None = None
    fit_residual: float | None = None
    fit_max_error: float | None = None
    fit_inliers: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DecodeSettings:
    screen: ScreenPreset
    board: BoardPreset
    fit: FitPreset

    @classmethod
    def of(cls, preset: Preset) -> DecodeSettings:
        return cls(preset.screen, preset.board, preset.fit)


def reading_order(detections: list[BoardDetection]) -> list[BoardDetection]:
    """Rows by centre y (half the median board height apart), then x within a row."""

    if not detections:
        return []
    centres = np.array([d.screen_quad.mean(axis=0) for d in detections])
    heights = np.array(
        [np.linalg.norm(d.screen_quad[3] - d.screen_quad[0]) for d in detections], dtype=float
    )
    tolerance = max(1.0, float(np.median(heights)) * 0.5)
    order = sorted(range(len(detections)), key=lambda i: centres[i, 1])
    rows: list[list[int]] = []
    for index in order:
        if (
            rows
            and abs(centres[index, 1] - np.mean([centres[i, 1] for i in rows[-1]])) <= tolerance
        ):
            rows[-1].append(index)
        else:
            rows.append([index])
    return [detections[i] for row in rows for i in sorted(row, key=lambda i: centres[i, 0])]


class NeuralGridEngine:
    """Two-stage engine behind the ``GeometryEngine`` contract (``detect``)."""

    def __init__(
        self,
        screen_runner: ScreenRunner,
        board_runner: BoardRunner,
        settings: DecodeSettings,
        model_version: str = MODEL_VERSION,
        board_batch: int = 16,
    ) -> None:
        self.screen_runner = screen_runner
        self.board_runner = board_runner
        self.settings = settings
        self.model_version = model_version
        self.board_batch = board_batch
        self.timings: dict[str, float] = {}

    def analyse(self, rgb: ByteImage) -> list[BoardDetection]:
        started = time.perf_counter()
        canvas, sx, sy = screen_input(rgb, self.settings.screen)
        pixels = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        heat, offsets = self.screen_runner(pixels)
        screen_done = time.perf_counter()
        detections = []
        for found in decode_screen(heat[0, 0], offsets[0], self.settings.screen):
            quad = (found.quad / np.array([sx, sy], np.float32)).astype(np.float32)
            detections.append(BoardDetection(found.score, quad))
        detections = reading_order(detections)
        crops, matrices, owners = [], [], []
        for detection in detections:
            if not quad_is_usable(detection.screen_quad):
                detection.reasons.append("NEURAL_GRID_SCREEN_QUAD_INVALID")
                continue
            matrix = board_rectifier(detection.screen_quad, self.settings.board)
            crops.append(crop_board(rgb, matrix, self.settings.board).transpose(2, 0, 1))
            matrices.append(matrix)
            owners.append(detection)
        for start in range(0, len(crops), self.board_batch):
            batch = np.stack(crops[start : start + self.board_batch]).astype(np.float32)
            nodes, peak, visibility = self.board_runner(batch)
            for offset, detection in enumerate(owners[start : start + self.board_batch]):
                matrix = matrices[start + offset]
                raw = transform_points(nodes[offset], np.asarray(np.linalg.inv(matrix), np.float64))
                detection.raw_nodes = raw
                detection.node_peak = np.asarray(peak[offset], np.float32)
                detection.visibility = np.asarray(visibility[offset], np.float32)
                scale = float(np.linalg.norm(detection.screen_quad[2] - detection.screen_quad[0]))
                fitted = fit_grid(raw, scale, self.settings.fit)
                detection.fit_inliers = int(fitted.inliers.sum())
                detection.fit_residual = fitted.residual
                detection.fit_max_error = fitted.max_inlier_error
                if fitted.ok:
                    detection.nodes = fitted.nodes
                    if detection.fit_inliers < 24:
                        detection.reasons.append("NEURAL_GRID_FIT_OUTLIERS")
                else:
                    finite = np.isfinite(fitted.residual)
                    detection.nodes = (
                        fitted.nodes if finite else grid_from_quad(detection.screen_quad)
                    )
                    detection.reasons.append("NEURAL_GRID_FIT_FAILED")
        self.timings = {
            "screen_seconds": screen_done - started,
            "total_seconds": time.perf_counter() - started,
        }
        return detections

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


def structurally_valid(nodes: FloatArray) -> bool:
    board = Board(
        position_index=0,
        status="needs_review",
        nodes=[Point(x=float(x), y=float(y)) for x, y in np.asarray(nodes).reshape(24, 2)],
    )
    try:
        cell_quads(board, Topology())
    except ValueError:
        return False
    return True


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


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def onnx_engine(bundle_directory: Path, threads: int | None = None) -> NeuralGridEngine:
    """CPU ORT engine from an exported bundle; every file is checksum-bound."""

    import onnxruntime as ort  # type: ignore[import-untyped]

    from .neural_grid_protocol import Preset as PresetModel

    bundle = json.loads((bundle_directory / BUNDLE_FILE).read_text(encoding="utf-8"))
    preset = PresetModel.model_validate(bundle["preset"])
    options = ort.SessionOptions()
    if threads is not None:
        options.intra_op_num_threads = threads
    sessions = {}
    for name in ("screen", "board"):
        path = bundle_directory / f"{name}.onnx"
        if file_sha256(path) != bundle["files"][f"{name}.onnx"]:
            raise ValueError("NEURAL_GRID_BUNDLE_CHECKSUM_MISMATCH")
        sessions[name] = ort.InferenceSession(
            str(path), options, providers=["CPUExecutionProvider"]
        )

    def screen(pixels: FloatArray) -> tuple[FloatArray, FloatArray]:
        heat, offsets = sessions["screen"].run(["heat", "offsets"], {"pixels": pixels})
        return heat, offsets

    def board(crops: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        nodes, peak, visibility = sessions["board"].run(
            ["nodes", "peak", "visibility"], {"crops": crops}
        )
        return nodes, peak, visibility

    return NeuralGridEngine(
        screen,
        board,
        DecodeSettings.of(preset),
        model_version=f"{MODEL_VERSION}:{preset.name}:{bundle['weights_sha256'][:12]}",
    )


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
