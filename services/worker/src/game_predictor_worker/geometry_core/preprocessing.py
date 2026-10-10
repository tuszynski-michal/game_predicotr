"""The exact neural-grid image transforms; no dataset or run-state imports."""

from __future__ import annotations

import math
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

from .settings import BoardPreset, ScreenPreset

FloatArray = NDArray[np.float32]
ByteImage = NDArray[np.uint8]
LATTICE: Final = np.array([(c, r) for r in range(4) for c in range(6)], dtype=np.float32)
CORNERS: Final = (0, 5, 23, 18)
CELL_COUNT: Final = 15
PAD_VALUE: Final = 114


def corners(nodes: FloatArray) -> FloatArray:
    return np.asarray(nodes, dtype=np.float32)[list(CORNERS)]


def lattice_homography(quad: FloatArray) -> NDArray[np.float64]:
    return np.asarray(
        cv2.getPerspectiveTransform(LATTICE[list(CORNERS)], np.asarray(quad, np.float32)),
        dtype=np.float64,
    )


def grid_from_quad(quad: FloatArray) -> FloatArray:
    """24 projective nodes of a quad (the snapshot labels are exactly this, residual 1e-4 px)."""

    return transform_points(LATTICE, lattice_homography(quad))


def quad_centre(quad: FloatArray) -> FloatArray:
    centre = transform_points(np.array([[2.5, 1.5]], np.float32), lattice_homography(quad))
    return np.asarray(centre[0], dtype=np.float32)


def transform_points(points: FloatArray, matrix: NDArray[np.float64]) -> FloatArray:
    values = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.concatenate([values, np.ones((len(values), 1))], axis=1) @ matrix.T
    w = homogeneous[:, 2:3]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return np.asarray(homogeneous[:, :2] / w, dtype=np.float32)


def quad_is_usable(quad: FloatArray, min_area: float = 16.0) -> bool:
    quad = np.asarray(quad, dtype=np.float32)
    return (
        bool(np.isfinite(quad).all())
        and bool(cv2.isContourConvex(quad.reshape(-1, 1, 2)))
        and float(cv2.contourArea(quad, oriented=True)) > min_area
    )


def screen_geometry(width: int, height: int, long_side: int, pad: int) -> tuple[int, int, int, int]:
    """Resized size and padded canvas size of the screen stage."""

    scale = long_side / max(width, height)
    resized_w = max(1, round(width * scale))
    resized_h = max(1, round(height * scale))
    return (
        resized_w,
        resized_h,
        int(math.ceil(resized_w / pad) * pad),
        int(math.ceil(resized_h / pad) * pad),
    )


def screen_input(rgb: ByteImage, screen: ScreenPreset) -> tuple[ByteImage, float, float]:
    """Inference preprocessing: area resize to the long side, pad right/bottom to 32."""

    height, width = rgb.shape[:2]
    resized_w, resized_h, canvas_w, canvas_h = screen_geometry(
        width, height, screen.long_side, screen.pad_multiple
    )
    canvas = np.full((canvas_h, canvas_w, 3), PAD_VALUE, dtype=np.uint8)
    canvas[:resized_h, :resized_w] = cv2.resize(
        rgb, (resized_w, resized_h), interpolation=cv2.INTER_AREA
    )
    return canvas, resized_w / width, resized_h / height


def board_rectifier(quad: FloatArray, board: BoardPreset) -> NDArray[np.float64]:
    """Homography source -> crop; the quad lands on the inner rectangle (margin per side)."""

    width, height = board.canvas
    left = width * board.margin / (1 + 2 * board.margin)
    top = height * board.margin / (1 + 2 * board.margin)
    target = np.array(
        [[left, top], [width - left, top], [width - left, height - top], [left, height - top]],
        dtype=np.float32,
    )
    return np.asarray(
        cv2.getPerspectiveTransform(np.asarray(quad, np.float32), target), dtype=np.float64
    )


def crop_board(rgb: ByteImage, matrix: NDArray[np.float64], board: BoardPreset) -> ByteImage:
    return np.asarray(
        cv2.warpPerspective(
            rgb,
            matrix,
            tuple(board.canvas),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(PAD_VALUE, PAD_VALUE, PAD_VALUE),
        ),
        dtype=np.uint8,
    )
