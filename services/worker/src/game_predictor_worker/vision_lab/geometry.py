"""Baseline adapter and topology-independent validation/cropping."""

import cv2
import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.images.screen_layout_v3.engine import (
    SCREEN_LAYOUT_V3_VERSION,
    detect_screen_layout_v3,
)

from .contracts import Board, GeometryResult, Point, Topology


def cell_quads(board: Board, topology: Topology) -> list[NDArray[np.float32]]:
    if len(board.nodes) != (topology.rows + 1) * (topology.columns + 1):
        raise ValueError("GRID_INCOMPLETE")
    points = np.asarray([(p.x, p.y) for p in board.nodes], dtype=np.float32)
    if not np.isfinite(points).all():
        raise ValueError("GRID_NONFINITE")
    grid = points.reshape(topology.rows + 1, topology.columns + 1, 2)
    quads = []
    for row in range(topology.rows):
        for col in range(topology.columns):
            quad = np.array(
                [grid[row, col], grid[row, col + 1], grid[row + 1, col + 1], grid[row + 1, col]],
                dtype=np.float32,
            )
            edges = np.roll(quad, -1, axis=0) - quad
            turns = edges[:, 0] * np.roll(edges[:, 1], -1) - edges[:, 1] * np.roll(edges[:, 0], -1)
            if not np.all(turns > 0) or cv2.contourArea(quad, oriented=True) <= 1:
                raise ValueError("GRID_ORDER_OR_INTERSECTION_INVALID")
            quads.append(quad)
    # Non-neighbour cells must not overlap; this also catches folded whole grids.
    for index, quad in enumerate(quads):
        for other in quads[index + 1 :]:
            area, _ = cv2.intersectConvexConvex(quad, other)
            if area > 0.1:
                raise ValueError("GRID_CELLS_OVERLAP")
    return quads


def crop_cell(rgb: NDArray[np.uint8], quad: NDArray[np.float32]) -> NDArray[np.uint8] | None:
    height, width = rgb.shape[:2]
    if (quad < 0).any() or (quad[:, 0] > width - 1).any() or (quad[:, 1] > height - 1).any():
        return None
    target = np.array([[0, 0], [95, 0], [95, 95], [0, 95]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(quad, target)
    return np.asarray(cv2.warpPerspective(rgb, matrix, (96, 96)), dtype=np.uint8)


class BaselineEngine:
    def detect(self, source_id: str, rgb: NDArray[np.uint8], topology: Topology) -> GeometryResult:
        result = GeometryResult(
            source_id=source_id,
            topology=topology,
            model_version=SCREEN_LAYOUT_V3_VERSION,
            status="unsupported",
            width=rgb.shape[1],
            height=rgb.shape[0],
        )
        if topology.columns != 5:
            result.reasons = ["BASELINE_TOPOLOGY_UNSUPPORTED"]
            return result
        detected = detect_screen_layout_v3(rgb)
        result.status = "detected" if detected.status == "detected" else "failed"
        result.reasons = [detected.reason_code] if detected.reason_code else []
        for board in sorted(detected.boards, key=lambda b: b.position_index):
            mapped = Board(
                position_index=board.position_index,
                status=board.status.value,
                nodes=[Point(x=float(x), y=float(y)) for x, y in board.points.reshape(-1, 2)],
                reasons=list(board.reason_codes),
            )
            try:
                cell_quads(mapped, topology)
            except ValueError as error:
                mapped.status = "needs_review"
                mapped.reasons.append(str(error))
            result.boards.append(mapped)
        return result
