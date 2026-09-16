"""Deterministic, unverified board-grid draft from accepted neighboring grids."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
)


def projected_review_draft(
    target_analysis: SourceQuad,
    confident_neighbors: Sequence[tuple[SourceQuad, SourceQuad]],
    *,
    width: int,
    height: int,
) -> SourceQuad | None:
    """Transfer median board-relative grid corners; never return accepted geometry."""

    if len(confident_neighbors) < 7 or width < 1 or height < 1:
        return None
    normalized: list[np.ndarray] = []
    unit = np.asarray(((0, 0), (1, 0), (1, 1), (0, 1)), dtype=np.float32)
    for analysis, grid in confident_neighbors:
        source = _points(analysis)
        measured = _points(grid)
        matrix = cv2.getPerspectiveTransform(source, unit)
        if not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-9:
            return None
        corners = cv2.perspectiveTransform(measured.reshape(1, 4, 2), matrix)[0]
        if not np.isfinite(corners).all() or np.any(corners < -0.2) or np.any(corners > 1.2):
            return None
        normalized.append(corners)
    median = np.median(np.stack(normalized), axis=0).astype(np.float32)
    target_matrix = cv2.getPerspectiveTransform(unit, _points(target_analysis))
    if not np.isfinite(target_matrix).all() or abs(float(np.linalg.det(target_matrix))) < 1e-9:
        return None
    projected = cv2.perspectiveTransform(median.reshape(1, 4, 2), target_matrix)[0]
    if not np.isfinite(projected).all():
        return None
    try:
        draft = SourceQuad(
            corners=cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(SourcePoint(round(float(x)), round(float(y))) for x, y in projected),
            )
        )
        draft.require_within(SourceImageBounds(width, height))
    except ImageGeometryContractError:
        return None
    return draft


def integer_review_draft(value: object, *, width: int, height: int) -> list[dict[str, int]] | None:
    """Expose four bounded integer handles without accepting the proposal."""

    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    if any(
        not isinstance(point, Mapping)
        or not isinstance(point.get("x"), int | float)
        or isinstance(point.get("x"), bool)
        or not isinstance(point.get("y"), int | float)
        or isinstance(point.get("y"), bool)
        for point in value
    ):
        return None
    try:
        quad = SourceQuad(
            corners=cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(
                    SourcePoint(round(float(point["x"])), round(float(point["y"])))
                    for point in value
                ),
            )
        )
        quad.require_within(SourceImageBounds(width, height))
    except (ImageGeometryContractError, OverflowError, ValueError):
        return None
    return [{"x": int(point.x), "y": int(point.y)} for point in quad.corners]


def _points(quad: SourceQuad) -> np.ndarray:
    return np.asarray([(point.x, point.y) for point in quad.corners], dtype=np.float32)
