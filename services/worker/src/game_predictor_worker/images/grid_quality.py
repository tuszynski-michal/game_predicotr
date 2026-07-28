"""Shared deterministic geometry metrics for board-grid quality reports."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile from an empty sample.")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * fraction
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


def metric_summary(values: Sequence[float]) -> dict[str, object]:
    return {
        "lineCount": len(values),
        "maxAbsoluteErrorPx": round(max(values), 4),
        "p50AbsoluteErrorPx": round(percentile(values, 0.5), 4),
        "p95AbsoluteErrorPx": round(percentile(values, 0.95), 4),
    }


def quad_to_canonical_matrix(
    quad: Quad,
    *,
    board_width: int,
    board_height: int,
) -> NDArray[np.float64]:
    source = np.asarray(quad, dtype=np.float32)
    destination = np.asarray(
        (
            (0.0, 0.0),
            (board_width - 1.0, 0.0),
            (board_width - 1.0, board_height - 1.0),
            (0.0, board_height - 1.0),
        ),
        dtype=np.float32,
    )
    return cast(
        NDArray[np.float64],
        cv2.getPerspectiveTransform(source, destination),
    )


def project_points(
    points: Sequence[Point],
    matrix: NDArray[np.float64],
) -> tuple[Point, ...]:
    values = np.asarray(points, dtype=np.float64).reshape((-1, 1, 2))
    projected = cv2.perspectiveTransform(values, matrix).reshape((-1, 2))
    return tuple((round(float(point[0]), 4), round(float(point[1]), 4)) for point in projected)


__all__ = [
    "Point",
    "Quad",
    "metric_summary",
    "percentile",
    "project_points",
    "quad_to_canonical_matrix",
]
