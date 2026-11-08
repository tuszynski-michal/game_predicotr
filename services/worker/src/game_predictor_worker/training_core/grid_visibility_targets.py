"""Versioned crop supervision derived from explicit content and actual pixel support."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..geometry_core.preprocessing import (
    board_rectifier,
    corners,
    crop_board,
    quad_is_usable,
    transform_points,
)
from ..geometry_core.rescue import BoardCropGeometryV1
from .neural_grid_augmentation import perturb_quad, photometric


def node_support_weights(nodes: np.ndarray, support: np.ndarray, stride: int) -> np.ndarray:
    """Bilinear support at the target and the closed softargmax coordinate range."""
    height, width = support.shape
    points = np.asarray(nodes, dtype=np.float32)
    if points.shape != (24, 2) or not np.isfinite(points).all():
        raise ValueError("GRID_NODE_TARGET_INVALID")
    reachable = (
        (points[:, 0] >= stride / 2)
        & (points[:, 0] <= width - stride / 2)
        & (points[:, 1] >= stride / 2)
        & (points[:, 1] <= height - stride / 2)
    )
    sampled = cv2.remap(
        support.astype(np.float32),
        points[:, 0:1],
        points[:, 1:2],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return np.asarray(reachable & (sampled[:, 0] >= 1 - 1e-6), dtype=np.float32)


def content_targets(
    reference: Any,
    matrix: np.ndarray,
    support: np.ndarray,
    supervision: Any,
) -> tuple[np.ndarray, np.ndarray]:
    targets, mask = np.zeros(15, np.float32), np.zeros(15, np.float32)
    if reference is None or not reference.humanApproved or not supervision.qualified:
        return targets, mask
    height, width = support.shape
    for i, cell in enumerate(reference.cells):
        if cell.state == "unknown":
            continue
        mask[i] = 1
        if cell.state != "visible":
            continue
        quad = transform_points(np.asarray(cell.quad, np.float32), matrix)
        if (
            not np.isfinite(quad).all()
            or not cv2.isContourConvex(quad)
            or abs(cv2.contourArea(quad)) <= 0
        ):
            mask[i] = 0
            continue
        # Inclusive raster pixel centres: any missing part makes the full symbol unavailable.
        if np.any(quad < 0) or np.any(quad[:, 0] > width - 1) or np.any(quad[:, 1] > height - 1):
            continue
        raster = np.zeros((height, width), np.uint8)
        cv2.fillConvexPoly(raster, np.rint(quad * 256).astype(np.int32), 1, shift=8)
        selected = support[raster > 0]
        if selected.size == 0:
            mask[i] = 0
        else:
            targets[i] = float(np.all(selected >= 1 - 1e-6))
    return targets, mask


def supervised_board_crop(
    rgb: np.ndarray,
    label_nodes: np.ndarray,
    board: Any,
    augmentation: Any,
    rng: np.random.Generator,
    *,
    reference: Any,
    supervision: Any,
    source_support: np.ndarray,
    geometry: BoardCropGeometryV1 | None = None,
) -> dict[str, np.ndarray]:
    """At most three jitter draws; an invalid draw never becomes an ideal GT crop."""
    if (
        source_support.shape != rgb.shape[:2]
        or not np.isfinite(source_support).all()
        or np.any(source_support < 0)
        or np.any(source_support > 1)
    ):
        raise ValueError("GRID_SOURCE_SUPPORT_INVALID")
    quad = None
    for _ in range(3):
        proposed = perturb_quad(corners(label_nodes), board, rng)
        if quad_is_usable(proposed):
            quad = proposed
            break
    width, height = board.canvas
    if quad is None:
        return {
            "crop": np.full((height, width, 3), 114, np.uint8),
            "nodes": np.zeros((24, 2), np.float32),
            "node_weights": np.zeros(24, np.float32),
            "visibility_targets": np.zeros(15, np.float32),
            "visibility_mask": np.zeros(15, np.float32),
        }
    matrix = board_rectifier(quad, board, geometry=geometry)
    support = cv2.warpPerspective(
        source_support.astype(np.float32),
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    content_support = np.asarray(support, dtype=np.float32).copy()
    crop = photometric(
        crop_board(rgb, matrix, board), augmentation, rng, content_support=content_support
    )
    nodes = transform_points(label_nodes, matrix)
    targets, mask = content_targets(reference, matrix, content_support, supervision)
    return {
        "crop": crop,
        "nodes": nodes,
        "node_weights": node_support_weights(nodes, support, board.stride),
        "visibility_targets": targets,
        "visibility_mask": mask,
    }
