"""Structural lattice validation independent of application contracts."""

import cv2
import numpy as np
from numpy.typing import NDArray


def lattice_cell_quads(
    points: NDArray[np.float32], rows: int = 3, columns: int = 5
) -> list[NDArray[np.float32]]:
    if len(points) != (rows + 1) * (columns + 1):
        raise ValueError("GRID_INCOMPLETE")
    points = np.asarray(points, dtype=np.float32)
    if not np.isfinite(points).all():
        raise ValueError("GRID_NONFINITE")
    grid = points.reshape(rows + 1, columns + 1, 2)
    quads = []
    for row in range(rows):
        for col in range(columns):
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


def structurally_valid(nodes: NDArray[np.float32]) -> bool:
    try:
        lattice_cell_quads(np.asarray(nodes, dtype=np.float32).reshape(24, 2))
    except ValueError:
        return False
    return True
