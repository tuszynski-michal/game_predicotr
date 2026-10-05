"""Torch-free neural-grid decoding and CPU ONNX loading, without laboratory state."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from .metrics import quad_iou
from .preprocessing import (
    LATTICE,
    ByteImage,
    FloatArray,
    board_rectifier,
    crop_board,
    grid_from_quad,
    quad_is_usable,
    screen_input,
    transform_points,
)
from .settings import MODEL_VERSION, BoardPreset, FitPreset, ScreenPreset

GATE_REASON: Final = "NEURAL_GRID_GATE_UNCALIBRATED"
ScreenRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray]]
BoardRunner = Callable[[FloatArray], tuple[FloatArray, FloatArray, FloatArray]]


class InferencePreset(Protocol):
    screen: ScreenPreset
    board: BoardPreset
    fit: FitPreset


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
    def of(cls, preset: InferencePreset) -> DecodeSettings:
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
    """Two-stage pure CPU inference runtime, shared with the laboratory."""

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


BUNDLE_FILE: Final = "bundle.json"


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def onnx_engine(
    bundle_directory: Path, threads: int | None = None, *, expected_bundle_sha256: str | None = None
) -> NeuralGridEngine:
    """CPU ORT engine from an exported bundle; every file is checksum-bound."""

    import onnxruntime as ort  # type: ignore[import-untyped]

    bundle_bytes = (bundle_directory / BUNDLE_FILE).read_bytes()
    if (
        expected_bundle_sha256 is not None
        and hashlib.sha256(bundle_bytes).hexdigest() != expected_bundle_sha256
    ):
        raise ValueError("NEURAL_GRID_BUNDLE_CHECKSUM_MISMATCH")
    bundle = json.loads(bundle_bytes)
    raw = bundle["preset"]
    settings = DecodeSettings(
        ScreenPreset.model_validate(raw["screen"]),
        BoardPreset.model_validate(raw["board"]),
        FitPreset.model_validate(raw["fit"]),
    )
    options = ort.SessionOptions()
    if threads is not None:
        options.intra_op_num_threads = threads
    sessions = {}
    for name in ("screen", "board"):
        path = bundle_directory / f"{name}.onnx"
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != bundle["files"][f"{name}.onnx"]:
            raise ValueError("NEURAL_GRID_BUNDLE_CHECKSUM_MISMATCH")
        sessions[name] = ort.InferenceSession(content, options, providers=["CPUExecutionProvider"])

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
        settings,
        model_version=f"{MODEL_VERSION}:{raw['name']}:{bundle['weights_sha256'][:12]}",
    )
