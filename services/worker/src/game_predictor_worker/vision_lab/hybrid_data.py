"""Image-only proposals/preprocessing, supervised matching and honest pilot scoring."""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from .contracts import Board, GeometryResult, Point, Topology
from .geometry import BaselineEngine, cell_quads
from .training_manifest import TrainingInputs, TrainingTarget

FloatArray = NDArray[np.float32]


def corners(nodes: Any) -> FloatArray:
    return np.asarray(nodes, dtype=np.float32)[[0, 5, 23, 18]]


@dataclass(frozen=True)
class Proposal:
    source_id: str
    board_index: int
    pixels: FloatArray
    quad: FloatArray
    affine: FloatArray
    width: int
    height: int
    baseline_nodes: FloatArray

    def normalize(self, quad: FloatArray) -> FloatArray:
        return np.asarray((quad * self.affine[0] + self.affine[1]) / 224.0, dtype=np.float32)

    def source(self, normalized: FloatArray) -> FloatArray:
        return np.asarray((normalized * 224.0 - self.affine[1]) / self.affine[0], dtype=np.float32)


def prepare_proposal(source_id: str, rgb: NDArray[np.uint8], board: Board) -> Proposal:
    cell_quads(board, Topology())
    quad = corners([(p.x, p.y) for p in board.nodes])
    height, width = rgb.shape[:2]
    lo, hi = quad.min(axis=0), quad.max(axis=0)
    margin = (hi - lo) * 0.2
    lo = np.maximum(np.floor(lo - margin), 0).astype(int)
    hi = np.minimum(np.ceil(hi + margin) + 1, [width, height]).astype(int)
    crop = rgb[lo[1] : hi[1], lo[0] : hi[0]]
    if not crop.size or (hi <= lo).any():
        raise ValueError("HYBRID_CROP_EMPTY")
    scale = 224 / max(crop.shape[:2])
    size = np.maximum(np.round(np.array([crop.shape[1], crop.shape[0]]) * scale), 1).astype(int)
    offset = (224 - size) // 2
    canvas = np.full((224, 224, 3), 114, dtype=np.uint8)
    canvas[offset[1] : offset[1] + size[1], offset[0] : offset[0] + size[0]] = cv2.resize(
        crop, tuple(size)
    )
    actual_scale = size / (hi - lo)
    affine = np.asarray([actual_scale, offset - lo * actual_scale], dtype=np.float32)
    return Proposal(
        source_id,
        board.position_index,
        np.asarray(canvas.astype(np.float32) / 255, dtype=np.float32),
        quad,
        affine,
        width,
        height,
        np.asarray([(p.x, p.y) for p in board.nodes], dtype=np.float32),
    )


def proposals(
    source_id: str, rgb: NDArray[np.uint8], engine: Any = None
) -> tuple[list[Proposal], list[str]]:
    detected = (engine or BaselineEngine()).detect(source_id, rgb, Topology())
    result, errors = [], list(detected.reasons)
    for board in detected.boards:
        try:
            result.append(prepare_proposal(source_id, rgb, board))
        except ValueError as error:
            errors.append(f"board-{board.position_index}:{error}")
    return result, errors


def quad_iou(left: FloatArray, right: FloatArray) -> float:
    intersection, _ = cv2.intersectConvexConvex(left, right)
    union = cv2.contourArea(left) + cv2.contourArea(right) - intersection
    return max(0.0, float(intersection / union)) if union > 0 else 0.0


def matches(proposal: Proposal, target: TrainingTarget) -> bool:
    return (
        proposal.source_id == target.source_id
        and proposal.board_index == target.board_index
        and quad_iou(proposal.quad, corners(target.nodes)) >= 0.25
    )


def grid_from_quad(quad: FloatArray, width: int, height: int, index: int) -> Board:
    if not np.isfinite(quad).all():
        raise ValueError("GRID_NONFINITE")
    if (quad < 0).any() or (quad[:, 0] > width - 1).any() or (quad[:, 1] > height - 1).any():
        raise ValueError("GRID_OUTSIDE_SOURCE")
    if not cv2.isContourConvex(quad) or cv2.contourArea(quad, oriented=True) <= 1:
        raise ValueError("GRID_ORDER_OR_INTERSECTION_INVALID")
    rectangle = np.array([[0, 0], [5, 0], [5, 3], [0, 3]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(rectangle, quad)
    points = np.array([(x, y) for y in range(4) for x in range(6)], dtype=np.float32)
    nodes = cv2.perspectiveTransform(points[None], transform)[0]
    if not np.isfinite(nodes).all() or (nodes < -0.001).any():
        raise ValueError("GRID_NONFINITE")
    board = Board(
        position_index=index,
        status="needs_review",
        nodes=[Point(x=float(x), y=float(y), provenance="model") for x, y in nodes],
        reasons=["HYBRID_GATE_UNCALIBRATED"],
    )
    cell_quads(board, Topology())
    return board


def result_from_deltas(
    source_id: str, width: int, height: int, values: list[Proposal], deltas: FloatArray
) -> GeometryResult:
    boards, errors = [], []
    for candidate, delta in zip(values, deltas, strict=True):
        try:
            quad = candidate.source(candidate.normalize(candidate.quad) + delta.reshape(4, 2))
            boards.append(grid_from_quad(quad, width, height, candidate.board_index))
        except ValueError as error:
            errors.append(f"board-{candidate.board_index}:{error}")
    return GeometryResult(
        source_id=source_id,
        topology=Topology(),
        model_version="hybrid-mobilenet-v1",
        status="detected" if boards else "failed",
        boards=boards,
        width=width,
        height=height,
        reasons=["HYBRID_GATE_UNCALIBRATED", *errors, *([] if values else ["NO_PROPOSAL"])],
    )


def normalized_batch(values: list[Proposal]) -> FloatArray:
    array = np.stack([p.pixels for p in values])
    normalized = (array - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32
    )
    return np.asarray(normalized.transpose(0, 3, 1, 2), dtype=np.float32)


def prepare_partition(
    inputs: TrainingInputs, targets: tuple[TrainingTarget, ...], heartbeat: Any = None
) -> tuple[list[Proposal], dict[str, Any]]:
    grouped: dict[str, list[TrainingTarget]] = defaultdict(list)
    for target in targets:
        grouped[target.source_id].append(target)
    all_proposals, rows = [], []
    for source_id, source_targets in sorted(grouped.items()):
        started = time.monotonic()
        if heartbeat:
            heartbeat()
        rgb = inputs.image(source_targets[0])
        try:
            candidates, errors = proposals(source_id, rgb)
        except (cv2.error, ValueError) as error:
            candidates, errors = [], [str(error)]
        matched = sum(any(matches(p, target) for p in candidates) for target in source_targets)
        rows.append(
            {
                "source_id": source_id,
                "targets": len(source_targets),
                "matched": matched,
                "missed": len(source_targets) - matched,
                "proposals": len(candidates),
                "errors": errors,
                "elapsed_seconds": time.monotonic() - started,
            }
        )
        all_proposals.extend(candidates)
    return all_proposals, {
        "targets": len(targets),
        "matched": sum(r["matched"] for r in rows),
        "sources": rows,
    }


def score(
    targets: tuple[TrainingTarget, ...],
    values: list[Proposal],
    deltas: FloatArray,
    *,
    original_baseline: bool = False,
) -> dict[str, Any]:
    predictions = {
        (p.source_id, p.board_index): (p, delta) for p, delta in zip(values, deltas, strict=True)
    }
    by_source: dict[str, list[float]] = defaultdict(list)
    raw, missed, invalid = [], 0, 0
    for target in targets:
        pair = predictions.get((target.source_id, target.board_index))
        cost = 1.0
        if pair is None or not matches(pair[0], target):
            missed += 1
        else:
            p, delta = pair
            try:
                quad = p.source(p.normalize(p.quad) + delta.reshape(4, 2))
                board = grid_from_quad(quad, p.width, p.height, p.board_index)
                nodes = np.array([(n.x, n.y) for n in board.nodes])
                if original_baseline:
                    nodes = p.baseline_nodes
                    if (
                        (nodes < 0).any()
                        or (nodes[:, 0] > p.width - 1).any()
                        or (nodes[:, 1] > p.height - 1).any()
                    ):
                        raise ValueError("GRID_OUTSIDE_SOURCE")
                truth = np.array(target.nodes)
                diagonal = float(np.linalg.norm(truth[23] - truth[0]))
                error = float(np.linalg.norm(nodes - truth, axis=1).mean() / max(diagonal, 1e-6))
                raw.append(error)
                cost = min(1.0, error)
            except ValueError:
                invalid += 1
        by_source[target.source_id].append(cost)
    return {
        "score": float(np.mean([np.mean(v) for v in by_source.values()])),
        "targets": len(targets),
        "valid": len(raw),
        "missed": missed,
        "invalid": invalid,
        "raw_nme_median": float(np.median(raw)) if raw else None,
        "raw_nme_p95": float(np.percentile(raw, 95)) if raw else None,
        "annotation_scope": "approved-geometries-only; unknown-is-not-absent",
    }
