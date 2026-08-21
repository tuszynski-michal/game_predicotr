"""Source-native board contexts and one-pass model cell projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Quad
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    CELL_INSET,
    LOGICAL_SLOT_HEIGHT,
    LOGICAL_SLOT_WIDTH,
    CellCrop,
    PageGeometry,
)

SOURCE_DIRECT_CROPPER_VERSION = "board-cell-crops-v18-source-direct-validated-v1"


class SourceDirectCropError(ValueError):
    """Stable invalid-input error for source-direct projections."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceContextBounds:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {
            "height": self.height,
            "width": self.width,
            "x": self.x,
            "y": self.y,
        }


@dataclass(frozen=True, slots=True)
class SourceDirectBoard:
    position_index: int
    context_rgb: NDArray[np.uint8]
    context_bounds: SourceContextBounds
    cells: tuple[CellCrop, ...]


@dataclass(frozen=True, slots=True)
class SourceDirectCropResult:
    status: Literal["cropped", "needs_review"]
    boards: tuple[SourceDirectBoard, ...]
    review_reasons: tuple[str, ...]


class SourceDirectBoardCellCropper:
    """Create native contexts and cells directly from normalized source pixels.

    The 500 x 300 coordinate system below is logical geometry only. No bitmap of
    that size is created. Every cell is projected from the source image straight
    to the pinned model input size in one interpolation operation.
    """

    version = SOURCE_DIRECT_CROPPER_VERSION

    def __init__(self, *, cell_output_size: int) -> None:
        if cell_output_size <= 0:
            raise ValueError("cell_output_size must be positive")
        self.cell_output_size = cell_output_size

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> SourceDirectCropResult:
        if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
            raise SourceDirectCropError(
                "BOARD_CROP_INVALID_IMAGE",
                "Cropper input must be an RGB uint8 image.",
            )
        image_height, image_width = rgb_image.shape[:2]
        if geometry.image_width != image_width or geometry.image_height != image_height:
            return SourceDirectCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_IMAGE_DIMENSIONS_MISMATCH",),
            )
        if geometry.status != "detected":
            return SourceDirectCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_UPSTREAM_NEEDS_REVIEW",),
            )
        # A layout import may only reach symbols from a complete verified page.
        # Partial pages used to be mathematically projectable, but could be a
        # whole row out of position and therefore are unsafe classifier input.
        if len(geometry.boards) != 9:
            return SourceDirectCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_BOARD_COUNT",),
            )
        positions = [board.position_index for board in geometry.boards]
        if positions != list(range(len(geometry.boards))):
            return SourceDirectCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_INDEX_SEQUENCE",),
            )

        projected: list[SourceDirectBoard] = []
        for board in geometry.boards:
            source_quad = _quad_array(board.quad)
            if not np.isfinite(source_quad).all() or cv2.contourArea(source_quad) <= 4.0:
                return SourceDirectCropResult(
                    status="needs_review",
                    boards=(),
                    review_reasons=("BOARD_CROP_SOURCE_QUAD_INVALID",),
                )
            context_bounds = _context_bounds(
                board.quad,
                image_width=image_width,
                image_height=image_height,
            )
            context = rgb_image[
                context_bounds.y : context_bounds.y + context_bounds.height,
                context_bounds.x : context_bounds.x + context_bounds.width,
            ].copy()
            board_to_source = cast(
                NDArray[np.float64],
                cv2.getPerspectiveTransform(
                    _logical_board_quad(),
                    source_quad,
                ),
            )
            if not np.isfinite(board_to_source).all():
                return SourceDirectCropResult(
                    status="needs_review",
                    boards=(),
                    review_reasons=("BOARD_CROP_TRANSFORM_INVALID",),
                )
            cells = tuple(
                CellCrop(
                    row_index=row,
                    column_index=column,
                    rgb=_project_cell_once(
                        rgb_image,
                        board_to_source,
                        row=row,
                        column=column,
                        output_size=self.cell_output_size,
                    ),
                )
                for row in range(BOARD_ROWS)
                for column in range(BOARD_COLUMNS)
            )
            projected.append(
                SourceDirectBoard(
                    position_index=board.position_index,
                    context_rgb=context,
                    context_bounds=context_bounds,
                    cells=cells,
                )
            )
        return SourceDirectCropResult(
            status="cropped",
            boards=tuple(projected),
            review_reasons=(),
        )


def _project_cell_once(
    rgb_image: NDArray[np.uint8],
    board_to_source: NDArray[np.float64],
    *,
    row: int,
    column: int,
    output_size: int,
) -> NDArray[np.uint8]:
    x0 = float(column * LOGICAL_SLOT_WIDTH + CELL_INSET)
    y0 = float(row * LOGICAL_SLOT_HEIGHT + CELL_INSET)
    x1 = float((column + 1) * LOGICAL_SLOT_WIDTH - CELL_INSET)
    y1 = float((row + 1) * LOGICAL_SLOT_HEIGHT - CELL_INSET)
    logical_cell = np.asarray(
        [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]],
        dtype=np.float32,
    )
    source_cell = cast(
        NDArray[np.float32],
        cv2.perspectiveTransform(logical_cell, board_to_source)[0],
    )
    destination = np.asarray(
        [
            [0.0, 0.0],
            [float(output_size - 1), 0.0],
            [float(output_size - 1), float(output_size - 1)],
            [0.0, float(output_size - 1)],
        ],
        dtype=np.float32,
    )
    source_to_cell = cv2.getPerspectiveTransform(source_cell, destination)
    return cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            rgb_image,
            source_to_cell,
            (output_size, output_size),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        ),
    )


def _context_bounds(
    quad: Quad,
    *,
    image_width: int,
    image_height: int,
) -> SourceContextBounds:
    xs = [point.x for point in quad]
    ys = [point.y for point in quad]
    board_width = max(xs) - min(xs)
    board_height = max(ys) - min(ys)
    left = max(0, int(np.floor(min(xs) - board_width * 0.12)))
    right = min(image_width, int(np.ceil(max(xs) + board_width * 0.12)) + 1)
    top = max(0, int(np.floor(min(ys) - board_height * 0.12)))
    bottom = min(image_height, int(np.ceil(max(ys) + board_height * 0.50)) + 1)
    return SourceContextBounds(
        x=left,
        y=top,
        width=max(1, right - left),
        height=max(1, bottom - top),
    )


def _logical_board_quad() -> NDArray[np.float32]:
    return np.asarray(
        [
            [0.0, 0.0],
            [float(BOARD_WIDTH - 1), 0.0],
            [float(BOARD_WIDTH - 1), float(BOARD_HEIGHT - 1)],
            [0.0, float(BOARD_HEIGHT - 1)],
        ],
        dtype=np.float32,
    )


def _quad_array(quad: Quad) -> NDArray[np.float32]:
    return np.asarray([[point.x, point.y] for point in quad], dtype=np.float32)
