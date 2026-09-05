"""Transient, checksum-bound crop preview for pre-import guard decisions."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from game_predictor_api.domain.jobs import JobError

CELL_WIDTH = 96
CELL_HEIGHT = 96
GRID_COLUMNS = 5
GRID_ROWS = 3


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardCellPreview:
    cell_index: int
    source_unavailable: bool
    current_data_url: str | None
    proposed_data_url: str | None


def render_image_geometry_guard_preview(
    *,
    source_content: bytes,
    symbol_grid_quad: tuple[dict[str, int], ...],
    proposed_symbol_grid_quad: object | None,
    unavailable_cell_indices: tuple[int, ...],
) -> tuple[int, int, tuple[ImageGeometryGuardCellPreview, ...]]:
    encoded = np.frombuffer(source_content, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_SOURCE_UNAVAILABLE",
            "The staged guard source cannot be decoded.",
        )
    image_height, image_width = image.shape[:2]
    current = _render_grid(image, symbol_grid_quad)
    proposed_quad = _coerce_quad(proposed_symbol_grid_quad)
    proposed = None if proposed_quad is None else _try_render_grid(image, proposed_quad)
    unavailable = set(unavailable_cell_indices)
    cells: list[ImageGeometryGuardCellPreview] = []
    for cell_index in range(GRID_COLUMNS * GRID_ROWS):
        missing = cell_index in unavailable
        cells.append(
            ImageGeometryGuardCellPreview(
                cell_index=cell_index,
                source_unavailable=missing,
                current_data_url=None if missing else _jpeg_data_url(current[cell_index]),
                proposed_data_url=(
                    None if missing or proposed is None else _jpeg_data_url(proposed[cell_index])
                ),
            )
        )
    return image_width, image_height, tuple(cells)


def _render_grid(image: np.ndarray, quad: tuple[dict[str, int], ...]) -> tuple[np.ndarray, ...]:
    source = _validated_quad(quad, image_width=image.shape[1], image_height=image.shape[0])
    width = CELL_WIDTH * GRID_COLUMNS
    height = CELL_HEIGHT * GRID_ROWS
    destination = np.asarray(
        ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(
        image,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return tuple(
        warped[
            row * CELL_HEIGHT : (row + 1) * CELL_HEIGHT,
            column * CELL_WIDTH : (column + 1) * CELL_WIDTH,
        ]
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    )


def _try_render_grid(
    image: np.ndarray, quad: tuple[dict[str, int], ...]
) -> tuple[np.ndarray, ...] | None:
    try:
        return _render_grid(image, quad)
    except JobError:
        return None


def _validated_quad(
    quad: tuple[dict[str, int], ...], *, image_width: int, image_height: int
) -> np.ndarray:
    if len(quad) != 4:
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_PREVIEW_GEOMETRY_INVALID",
            "The preview grid requires four corner points.",
        )
    points = np.asarray([(point.get("x"), point.get("y")) for point in quad], dtype=np.float32)
    if (
        points.shape != (4, 2)
        or not np.isfinite(points).all()
        or np.any(points[:, 0] < 0)
        or np.any(points[:, 1] < 0)
        or np.any(points[:, 0] >= image_width)
        or np.any(points[:, 1] >= image_height)
        or abs(float(cv2.contourArea(points))) < 25.0
        or not cv2.isContourConvex(points.astype(np.int32))
    ):
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_PREVIEW_GEOMETRY_INVALID",
            "The preview grid is outside the source image or is degenerate.",
        )
    return cast(np.ndarray, points)


def _coerce_quad(value: object | None) -> tuple[dict[str, int], ...] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    points: list[dict[str, int]] = []
    for raw in value:
        if not isinstance(raw, dict):
            return None
        x, y = raw.get("x"), raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
            or not np.isfinite(x)
            or not np.isfinite(y)
        ):
            return None
        points.append({"x": round(x), "y": round(y)})
    return tuple(points)


def _jpeg_data_url(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".jpg", image, (cv2.IMWRITE_JPEG_QUALITY, 86))
    if not success:
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_PREVIEW_RENDER_FAILED",
            "The guard crop preview could not be rendered.",
        )
    payload = base64.b64encode(cast(np.ndarray, encoded).tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


__all__ = [
    "ImageGeometryGuardCellPreview",
    "render_image_geometry_guard_preview",
]
