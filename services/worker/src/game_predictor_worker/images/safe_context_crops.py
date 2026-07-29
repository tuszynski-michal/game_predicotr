"""Conservative full-frame crops with overlap instead of fragile symbol fitting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Point, Quad
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    LOGICAL_SLOT_HEIGHT,
    LOGICAL_SLOT_WIDTH,
    PROJECTIVE_SAFE_CONTEXT_CROPPER_VERSION,
    SAFE_CONTEXT_CROPPER_VERSION,
    BoardCropResult,
    BoardGeometry,
    CellCrop,
    GridContract,
    PageGeometry,
    PerspectiveBoardCellCropperV2,
    RectifiedBoard,
)

FRAME_PROFILE_SET_VERSION = "expanded-detector-bounding-frame-v2"
SOURCE_QUAD_SOURCE = "expanded-detector-bounding-frame"
FRAME_PAD_X_RATIO = 0.12
FRAME_PAD_Y_RATIO = 0.06
PROJECTIVE_FRAME_PROFILE_SET_VERSION = "expanded-detector-projective-quad-v1"
PROJECTIVE_SOURCE_QUAD_SOURCE = "expanded-detector-projective-quad"
PROJECTIVE_FRAME_PAD_X_RATIO = 0.08
PROJECTIVE_FRAME_PAD_Y_RATIO = 0.08
CELL_OVERLAP_PX = 24
GRID_OFFSET_Y_PX = 24
SAFE_CONTEXT_GRID = GridContract(
    rows=BOARD_ROWS,
    columns=BOARD_COLUMNS,
    cell_width=CELL_WIDTH,
    cell_height=CELL_HEIGHT,
    logical_slot_width=LOGICAL_SLOT_WIDTH,
    logical_slot_height=LOGICAL_SLOT_HEIGHT,
    inset_px=0,
    overlap_px=CELL_OVERLAP_PX,
    offset_y_px=GRID_OFFSET_Y_PX,
)


def _expanded_bounding_quad(
    bounding_box: tuple[int, int, int, int],
    *,
    image_width: int,
    image_height: int,
) -> Quad:
    x, y, width, height = bounding_box
    pad_x = max(2, round(width * FRAME_PAD_X_RATIO))
    pad_y = max(2, round(height * FRAME_PAD_Y_RATIO))
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(image_width - 1, x + width - 1 + pad_x)
    bottom = min(image_height - 1, y + height - 1 + pad_y)
    return (
        Point(left, top),
        Point(right, top),
        Point(right, bottom),
        Point(left, bottom),
    )


def _expanded_projective_quad(
    quad: Quad,
    *,
    image_width: int,
    image_height: int,
) -> Quad | None:
    source = np.asarray([(point.x, point.y) for point in quad], dtype=np.float32)
    source_contour = source.astype(np.int32)
    source_area = float(cv2.contourArea(source, oriented=True))
    if (
        not np.isfinite(source).all()
        or not cv2.isContourConvex(source_contour)
        or abs(source_area) < 100.0
    ):
        return None
    canonical = np.asarray(
        ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        dtype=np.float32,
    )
    canonical_to_source = cv2.getPerspectiveTransform(canonical, source)
    expanded_canonical = np.asarray(
        (
            (-PROJECTIVE_FRAME_PAD_X_RATIO, -PROJECTIVE_FRAME_PAD_Y_RATIO),
            (1.0 + PROJECTIVE_FRAME_PAD_X_RATIO, -PROJECTIVE_FRAME_PAD_Y_RATIO),
            (
                1.0 + PROJECTIVE_FRAME_PAD_X_RATIO,
                1.0 + PROJECTIVE_FRAME_PAD_Y_RATIO,
            ),
            (-PROJECTIVE_FRAME_PAD_X_RATIO, 1.0 + PROJECTIVE_FRAME_PAD_Y_RATIO),
        ),
        dtype=np.float32,
    ).reshape((-1, 1, 2))
    expanded = cv2.perspectiveTransform(
        expanded_canonical,
        canonical_to_source,
    ).reshape((-1, 2))
    if not np.isfinite(expanded).all():
        return None
    rounded = np.rint(expanded).astype(np.int32)
    expanded_area = float(cv2.contourArea(rounded, oriented=True))
    if (
        np.any(rounded[:, 0] < 0)
        or np.any(rounded[:, 1] < 0)
        or np.any(rounded[:, 0] >= image_width)
        or np.any(rounded[:, 1] >= image_height)
        or not cv2.isContourConvex(rounded)
        or abs(expanded_area) <= abs(source_area)
        or np.sign(expanded_area) != np.sign(source_area)
        or any(
            cv2.pointPolygonTest(
                rounded.astype(np.float32),
                (float(point[0]), float(point[1])),
                False,
            )
            < 0
            for point in source
        )
    ):
        return None
    return cast(
        Quad,
        tuple(Point(int(point[0]), int(point[1])) for point in rounded),
    )


@dataclass(slots=True)
class ExpandedBoundingFrameCalibrator:
    """Replace unstable red-mask extreme quads with complete local frames."""

    profile_set_sha256: str
    corpus_manifest_sha256: str
    detection_report_sha256: str
    profile_set_version: str = FRAME_PROFILE_SET_VERSION

    @classmethod
    def from_files(
        cls,
        manifest_path: Path,
        detection_report_path: Path,
    ) -> ExpandedBoundingFrameCalibrator:
        manifest_bytes = manifest_path.resolve(strict=True).read_bytes()
        detection_bytes = detection_report_path.resolve(strict=True).read_bytes()
        profile_sha = hashlib.sha256(
            FRAME_PROFILE_SET_VERSION.encode()
            + b"\0"
            + f"{FRAME_PAD_X_RATIO:.6f}".encode()
            + b"\0"
            + f"{FRAME_PAD_Y_RATIO:.6f}".encode()
            + b"\0"
            + detection_bytes
        ).hexdigest()
        return cls(
            profile_set_sha256=profile_sha,
            corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            detection_report_sha256=hashlib.sha256(detection_bytes).hexdigest(),
        )

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        del source_checksum_sha256
        if geometry.status != "detected":
            return geometry
        boards: list[BoardGeometry] = []
        for board in geometry.boards:
            if board.bounding_box is None:
                return PageGeometry(
                    status="needs_review",
                    image_width=geometry.image_width,
                    image_height=geometry.image_height,
                    boards=(),
                    review_reasons=("SAFE_CONTEXT_BOUNDING_FRAME_MISSING",),
                )
            boards.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=_expanded_bounding_quad(
                        board.bounding_box,
                        image_width=geometry.image_width,
                        image_height=geometry.image_height,
                    ),
                    bounding_box=board.bounding_box,
                    source_quad_source=SOURCE_QUAD_SOURCE,
                )
            )
        return PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(boards),
            review_reasons=(),
        )


@dataclass(slots=True)
class ProjectiveExpandedFrameCalibrator:
    """Expand each detector quad without discarding its projective axes."""

    profile_set_sha256: str
    corpus_manifest_sha256: str
    detection_report_sha256: str
    profile_set_version: str = PROJECTIVE_FRAME_PROFILE_SET_VERSION

    @classmethod
    def from_files(
        cls,
        manifest_path: Path,
        detection_report_path: Path,
    ) -> ProjectiveExpandedFrameCalibrator:
        manifest_bytes = manifest_path.resolve(strict=True).read_bytes()
        detection_bytes = detection_report_path.resolve(strict=True).read_bytes()
        profile_sha = hashlib.sha256(
            PROJECTIVE_FRAME_PROFILE_SET_VERSION.encode()
            + b"\0"
            + f"{PROJECTIVE_FRAME_PAD_X_RATIO:.6f}".encode()
            + b"\0"
            + f"{PROJECTIVE_FRAME_PAD_Y_RATIO:.6f}".encode()
            + b"\0"
            + detection_bytes
        ).hexdigest()
        return cls(
            profile_set_sha256=profile_sha,
            corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            detection_report_sha256=hashlib.sha256(detection_bytes).hexdigest(),
        )

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        del source_checksum_sha256
        if geometry.status != "detected":
            return geometry
        boards: list[BoardGeometry] = []
        for board in geometry.boards:
            expanded = _expanded_projective_quad(
                board.quad,
                image_width=geometry.image_width,
                image_height=geometry.image_height,
            )
            if expanded is None:
                return PageGeometry(
                    status="needs_review",
                    image_width=geometry.image_width,
                    image_height=geometry.image_height,
                    boards=(),
                    review_reasons=("PROJECTIVE_FRAME_EXPANSION_INVALID",),
                )
            boards.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=expanded,
                    bounding_box=board.bounding_box,
                    source_quad_source=PROJECTIVE_SOURCE_QUAD_SOURCE,
                    calibration_profile_id=board.calibration_profile_id,
                    calibration_profile_version=board.calibration_profile_version,
                    calibration_anchor_sequence_numbers=(
                        board.calibration_anchor_sequence_numbers
                    ),
                    calibration_interpolation_weight=(
                        board.calibration_interpolation_weight
                    ),
                    symbol_refinement=board.symbol_refinement,
                )
            )
        return PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(boards),
            review_reasons=(),
        )


def _safe_context_overlay(
    board_rgb: NDArray[np.uint8],
) -> NDArray[np.uint8]:
    overlay = board_rgb.copy()
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            left = max(0, column * LOGICAL_SLOT_WIDTH - CELL_OVERLAP_PX)
            right = min(
                BOARD_WIDTH,
                (column + 1) * LOGICAL_SLOT_WIDTH + CELL_OVERLAP_PX,
            )
            top = max(
                0,
                row * LOGICAL_SLOT_HEIGHT + GRID_OFFSET_Y_PX - CELL_OVERLAP_PX,
            )
            bottom = min(
                BOARD_HEIGHT,
                (row + 1) * LOGICAL_SLOT_HEIGHT + GRID_OFFSET_Y_PX + CELL_OVERLAP_PX,
            )
            cv2.rectangle(
                overlay,
                (left, top),
                (right - 1, bottom - 1),
                (25, 235, 90),
                2,
                cv2.LINE_AA,
            )
    return overlay


class SafeContextBoardCellCropper(PerspectiveBoardCellCropperV2):
    """Resize overlapping logical contexts to 90 × 90 without center fitting."""

    version = SAFE_CONTEXT_CROPPER_VERSION

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> BoardCropResult:
        rectified = super().crop(rgb_image, geometry)
        if rectified.status != "cropped":
            return rectified
        boards: list[RectifiedBoard] = []
        for board in rectified.boards:
            cells: list[CellCrop] = []
            for row in range(BOARD_ROWS):
                for column in range(BOARD_COLUMNS):
                    left = max(0, column * LOGICAL_SLOT_WIDTH - CELL_OVERLAP_PX)
                    right = min(
                        BOARD_WIDTH,
                        (column + 1) * LOGICAL_SLOT_WIDTH + CELL_OVERLAP_PX,
                    )
                    top = max(
                        0,
                        row * LOGICAL_SLOT_HEIGHT + GRID_OFFSET_Y_PX - CELL_OVERLAP_PX,
                    )
                    bottom = min(
                        BOARD_HEIGHT,
                        (row + 1) * LOGICAL_SLOT_HEIGHT + GRID_OFFSET_Y_PX + CELL_OVERLAP_PX,
                    )
                    cells.append(
                        CellCrop(
                            row_index=row,
                            column_index=column,
                            rgb=cast(
                                NDArray[np.uint8],
                                cv2.resize(
                                    board.board_rgb[top:bottom, left:right],
                                    (CELL_WIDTH, CELL_HEIGHT),
                                    interpolation=cv2.INTER_AREA,
                                ),
                            ),
                        )
                    )
            boards.append(
                RectifiedBoard(
                    position_index=board.position_index,
                    source_quad=board.source_quad,
                    transform_matrix=board.transform_matrix,
                    board_rgb=board.board_rgb,
                    grid_overlay_rgb=_safe_context_overlay(board.board_rgb),
                    cells=tuple(cells),
                    grid_contract=SAFE_CONTEXT_GRID,
                    source_quad_source=board.source_quad_source,
                )
            )
        return BoardCropResult(
            status="cropped",
            boards=tuple(boards),
            review_reasons=(),
        )


class ProjectiveSafeContextBoardCellCropper(SafeContextBoardCellCropper):
    """Versioned preflight cropper for perspective-preserving expanded quads."""

    version = PROJECTIVE_SAFE_CONTEXT_CROPPER_VERSION


__all__ = [
    "CELL_OVERLAP_PX",
    "FRAME_PROFILE_SET_VERSION",
    "GRID_OFFSET_Y_PX",
    "PROJECTIVE_FRAME_PAD_X_RATIO",
    "PROJECTIVE_FRAME_PAD_Y_RATIO",
    "PROJECTIVE_FRAME_PROFILE_SET_VERSION",
    "PROJECTIVE_SOURCE_QUAD_SOURCE",
    "SAFE_CONTEXT_GRID",
    "SOURCE_QUAD_SOURCE",
    "ExpandedBoundingFrameCalibrator",
    "ProjectiveExpandedFrameCalibrator",
    "ProjectiveSafeContextBoardCellCropper",
    "SafeContextBoardCellCropper",
]
