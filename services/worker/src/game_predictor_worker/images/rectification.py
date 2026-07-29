"""Per-board perspective correction and deterministic 3 × 5 cell crops."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import DETECTOR_VERSION, Point, Quad

CROPPER_VERSION = "board-cell-crops-v1"
V2_CROPPER_VERSION = "board-cell-crops-v2"
CALIBRATED_CROPPER_VERSION = "board-cell-crops-v2-calibrated-v1"
LOCAL_CALIBRATED_CROPPER_VERSION = "board-cell-crops-v3-local-calibrated-v1"
SYMBOL_AWARE_CROPPER_VERSION = "board-cell-crops-v4-symbol-aware-v1"
SYMBOL_AWARE_AFFINE_CROPPER_VERSION = "board-cell-crops-v5-symbol-aware-affine-v1"
DETECTOR_SYMBOL_AWARE_CROPPER_VERSION = "board-cell-crops-v6-detector-symbol-aware-affine-v1"
BOARD_WIDTH = 500
BOARD_HEIGHT = 300
BOARD_ROWS = 3
BOARD_COLUMNS = 5
MARGIN_X = 25
MARGIN_Y = 15
CELL_WIDTH = 90
CELL_HEIGHT = 90
LOGICAL_SLOT_WIDTH = 100
LOGICAL_SLOT_HEIGHT = 100
CELL_INSET = 5
MAX_BOARD_COUNT = 9


class BoardCropError(ValueError):
    """Stable fatal error for board crop orchestration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SymbolRefinementMetadata:
    refiner_version: str
    reliable_center_count: int
    inlier_count: int
    baseline_median_residual_px: float
    refined_median_residual_px: float
    refined_p95_residual_px: float

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "baselineMedianResidualPx": round(
                self.baseline_median_residual_px,
                4,
            ),
            "inlierCount": self.inlier_count,
            "refinedMedianResidualPx": round(
                self.refined_median_residual_px,
                4,
            ),
            "refinedP95ResidualPx": round(self.refined_p95_residual_px, 4),
            "refinerVersion": self.refiner_version,
            "reliableCenterCount": self.reliable_center_count,
        }


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    position_index: int
    quad: Quad
    bounding_box: tuple[int, int, int, int] | None = None
    source_quad_source: str | None = None
    calibration_profile_id: str | None = None
    calibration_profile_version: int | None = None
    calibration_anchor_sequence_numbers: tuple[int, ...] = ()
    calibration_interpolation_weight: float | None = None
    symbol_refinement: SymbolRefinementMetadata | None = None


@dataclass(frozen=True, slots=True)
class PageGeometry:
    status: Literal["detected", "needs_review"]
    image_width: int
    image_height: int
    boards: tuple[BoardGeometry, ...]
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CellCrop:
    row_index: int
    column_index: int
    rgb: NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class GridContract:
    rows: int
    columns: int
    cell_width: int
    cell_height: int
    margin_x: int | None = None
    margin_y: int | None = None
    logical_slot_width: int | None = None
    logical_slot_height: int | None = None
    inset_px: int | None = None

    def to_dict(self) -> dict[str, int]:
        value = {
            "cellHeight": self.cell_height,
            "cellWidth": self.cell_width,
            "columns": self.columns,
            "rows": self.rows,
        }
        if self.margin_x is not None and self.margin_y is not None:
            value["marginX"] = self.margin_x
            value["marginY"] = self.margin_y
        if (
            self.logical_slot_width is not None
            and self.logical_slot_height is not None
            and self.inset_px is not None
        ):
            value["insetPx"] = self.inset_px
            value["logicalSlotHeight"] = self.logical_slot_height
            value["logicalSlotWidth"] = self.logical_slot_width
        return value


V1_GRID_CONTRACT = GridContract(
    rows=BOARD_ROWS,
    columns=BOARD_COLUMNS,
    cell_width=CELL_WIDTH,
    cell_height=CELL_HEIGHT,
    margin_x=MARGIN_X,
    margin_y=MARGIN_Y,
)
V2_GRID_CONTRACT = GridContract(
    rows=BOARD_ROWS,
    columns=BOARD_COLUMNS,
    cell_width=CELL_WIDTH,
    cell_height=CELL_HEIGHT,
    logical_slot_width=LOGICAL_SLOT_WIDTH,
    logical_slot_height=LOGICAL_SLOT_HEIGHT,
    inset_px=CELL_INSET,
)


@dataclass(frozen=True, slots=True)
class RectifiedBoard:
    position_index: int
    source_quad: Quad
    transform_matrix: tuple[tuple[float, float, float], ...]
    board_rgb: NDArray[np.uint8]
    grid_overlay_rgb: NDArray[np.uint8]
    cells: tuple[CellCrop, ...]
    grid_contract: GridContract
    source_quad_source: str | None = None
    calibration_profile_id: str | None = None
    calibration_profile_version: int | None = None
    calibration_anchor_sequence_numbers: tuple[int, ...] = ()
    calibration_interpolation_weight: float | None = None
    symbol_refinement: SymbolRefinementMetadata | None = None


@dataclass(frozen=True, slots=True)
class BoardCropResult:
    status: Literal["cropped", "needs_review"]
    boards: tuple[RectifiedBoard, ...]
    review_reasons: tuple[str, ...]


class BoardCellCropper(Protocol):
    """Port for replaceable board rectification and grid extraction."""

    version: str

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> BoardCropResult:
        """Rectify a complete supported page without mutating its input."""


class PageGeometryCalibrator(Protocol):
    """Versioned pre-rectification source-quad calibration port."""

    profile_set_version: str
    profile_set_sha256: str
    corpus_manifest_sha256: str
    detection_report_sha256: str

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        """Return calibrated geometry for one verified source image."""


def _rounded_matrix(matrix: NDArray[np.float64]) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        (
            round(float(matrix[row, 0]), 10),
            round(float(matrix[row, 1]), 10),
            round(float(matrix[row, 2]), 10),
        )
        for row in range(3)
    )


def _quad_array(quad: Quad) -> NDArray[np.float32]:
    return np.array([[point.x, point.y] for point in quad], dtype=np.float32)


def _quad_review_reason(
    quad: Quad,
    *,
    image_width: int,
    image_height: int,
) -> str | None:
    points = _quad_array(quad)
    if any(
        point.x < 0 or point.y < 0 or point.x >= image_width or point.y >= image_height
        for point in quad
    ):
        return "BOARD_CROP_QUAD_OUT_OF_BOUNDS"
    contour = points.astype(np.int32)
    if not cv2.isContourConvex(contour):
        return "BOARD_CROP_QUAD_NOT_CONVEX"
    if abs(float(cv2.contourArea(points))) < 100:
        return "BOARD_CROP_QUAD_DEGENERATE"
    top = float(np.linalg.norm(points[1] - points[0]))
    right = float(np.linalg.norm(points[2] - points[1]))
    bottom = float(np.linalg.norm(points[2] - points[3]))
    left = float(np.linalg.norm(points[3] - points[0]))
    if min(top, right, bottom, left) < 10:
        return "BOARD_CROP_QUAD_DEGENERATE"
    return None


def _grid_overlay(board_rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    overlay = board_rgb.copy()
    color = (0, 255, 0)
    cv2.rectangle(
        overlay,
        (MARGIN_X, MARGIN_Y),
        (BOARD_WIDTH - MARGIN_X - 1, BOARD_HEIGHT - MARGIN_Y - 1),
        color,
        2,
    )
    for column in range(1, BOARD_COLUMNS):
        x = MARGIN_X + column * CELL_WIDTH
        cv2.line(overlay, (x, MARGIN_Y), (x, BOARD_HEIGHT - MARGIN_Y - 1), color, 2)
    for row in range(1, BOARD_ROWS):
        y = MARGIN_Y + row * CELL_HEIGHT
        cv2.line(overlay, (MARGIN_X, y), (BOARD_WIDTH - MARGIN_X - 1, y), color, 2)
    return overlay


def _grid_overlay_v2(board_rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    overlay = board_rgb.copy()
    slot_color = (0, 255, 255)
    inset_color = (0, 255, 0)
    for column in range(1, BOARD_COLUMNS):
        x = column * LOGICAL_SLOT_WIDTH
        cv2.line(overlay, (x, 0), (x, BOARD_HEIGHT - 1), slot_color, 2)
    for row in range(1, BOARD_ROWS):
        y = row * LOGICAL_SLOT_HEIGHT
        cv2.line(overlay, (0, y), (BOARD_WIDTH - 1, y), slot_color, 2)
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            x0 = column * LOGICAL_SLOT_WIDTH + CELL_INSET
            y0 = row * LOGICAL_SLOT_HEIGHT + CELL_INSET
            x1 = (column + 1) * LOGICAL_SLOT_WIDTH - CELL_INSET - 1
            y1 = (row + 1) * LOGICAL_SLOT_HEIGHT - CELL_INSET - 1
            cv2.rectangle(overlay, (x0, y0), (x1, y1), inset_color, 1)
    return overlay


class PerspectiveBoardCellCropper:
    """OpenCV perspective cropper for the supported 3 × 5 board."""

    version = CROPPER_VERSION

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> BoardCropResult:
        if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
            raise BoardCropError(
                "BOARD_CROP_INVALID_IMAGE",
                "Cropper input must be an RGB uint8 image.",
            )
        image_height, image_width = rgb_image.shape[:2]
        if geometry.image_width != image_width or geometry.image_height != image_height:
            return BoardCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_IMAGE_DIMENSIONS_MISMATCH",),
            )
        if geometry.status != "detected":
            return BoardCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_UPSTREAM_NEEDS_REVIEW",),
            )
        if not 1 <= len(geometry.boards) <= MAX_BOARD_COUNT:
            return BoardCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_BOARD_COUNT",),
            )
        if [board.position_index for board in geometry.boards] != list(range(len(geometry.boards))):
            return BoardCropResult(
                status="needs_review",
                boards=(),
                review_reasons=("BOARD_CROP_INDEX_SEQUENCE",),
            )
        for board in geometry.boards:
            reason = _quad_review_reason(
                board.quad,
                image_width=image_width,
                image_height=image_height,
            )
            if reason is not None:
                return BoardCropResult(
                    status="needs_review",
                    boards=(),
                    review_reasons=(reason,),
                )

        destination = np.array(
            [
                [0, 0],
                [BOARD_WIDTH - 1, 0],
                [BOARD_WIDTH - 1, BOARD_HEIGHT - 1],
                [0, BOARD_HEIGHT - 1],
            ],
            dtype=np.float32,
        )
        rectified: list[RectifiedBoard] = []
        for board in geometry.boards:
            matrix = cast(
                NDArray[np.float64],
                cv2.getPerspectiveTransform(_quad_array(board.quad), destination),
            )
            if not np.isfinite(matrix).all():
                return BoardCropResult(
                    status="needs_review",
                    boards=(),
                    review_reasons=("BOARD_CROP_TRANSFORM_INVALID",),
                )
            warped = cast(
                NDArray[np.uint8],
                cv2.warpPerspective(
                    rgb_image,
                    matrix,
                    (BOARD_WIDTH, BOARD_HEIGHT),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                ),
            )
            cells = tuple(
                CellCrop(
                    row_index=row,
                    column_index=column,
                    rgb=warped[
                        MARGIN_Y + row * CELL_HEIGHT : MARGIN_Y + (row + 1) * CELL_HEIGHT,
                        MARGIN_X + column * CELL_WIDTH : MARGIN_X + (column + 1) * CELL_WIDTH,
                    ].copy(),
                )
                for row in range(BOARD_ROWS)
                for column in range(BOARD_COLUMNS)
            )
            rectified.append(
                RectifiedBoard(
                    position_index=board.position_index,
                    source_quad=board.quad,
                    transform_matrix=_rounded_matrix(matrix),
                    board_rgb=warped,
                    grid_overlay_rgb=_grid_overlay(warped),
                    cells=cells,
                    grid_contract=V1_GRID_CONTRACT,
                )
            )
        return BoardCropResult(
            status="cropped",
            boards=tuple(rectified),
            review_reasons=(),
        )


class PerspectiveBoardCellCropperV2(PerspectiveBoardCellCropper):
    """Correct logical-slot cropper with a per-cell inset."""

    version = V2_CROPPER_VERSION

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: PageGeometry,
    ) -> BoardCropResult:
        rectified = super().crop(rgb_image, geometry)
        if rectified.status != "cropped":
            return rectified
        boards: list[RectifiedBoard] = []
        geometry_by_position = {board.position_index: board for board in geometry.boards}
        for board in rectified.boards:
            source_geometry = geometry_by_position[board.position_index]
            cells = tuple(
                CellCrop(
                    row_index=row,
                    column_index=column,
                    rgb=board.board_rgb[
                        row * LOGICAL_SLOT_HEIGHT + CELL_INSET : (row + 1) * LOGICAL_SLOT_HEIGHT
                        - CELL_INSET,
                        column * LOGICAL_SLOT_WIDTH + CELL_INSET : (column + 1) * LOGICAL_SLOT_WIDTH
                        - CELL_INSET,
                    ].copy(),
                )
                for row in range(BOARD_ROWS)
                for column in range(BOARD_COLUMNS)
            )
            boards.append(
                RectifiedBoard(
                    position_index=board.position_index,
                    source_quad=board.source_quad,
                    transform_matrix=board.transform_matrix,
                    board_rgb=board.board_rgb,
                    grid_overlay_rgb=_grid_overlay_v2(board.board_rgb),
                    cells=cells,
                    grid_contract=V2_GRID_CONTRACT,
                    source_quad_source=source_geometry.source_quad_source or "detector",
                    calibration_profile_id=source_geometry.calibration_profile_id,
                    calibration_profile_version=source_geometry.calibration_profile_version,
                    calibration_anchor_sequence_numbers=(
                        source_geometry.calibration_anchor_sequence_numbers
                    ),
                    calibration_interpolation_weight=(
                        source_geometry.calibration_interpolation_weight
                    ),
                    symbol_refinement=source_geometry.symbol_refinement,
                )
            )
        return BoardCropResult(
            status="cropped",
            boards=tuple(boards),
            review_reasons=(),
        )


class PerspectiveBoardCellCropperV2Calibrated(PerspectiveBoardCellCropperV2):
    """V2 logical cell cropper with versioned pre-rectification calibration."""

    version = CALIBRATED_CROPPER_VERSION


class PerspectiveBoardCellCropperV3LocalCalibrated(PerspectiveBoardCellCropperV2):
    """Logical-slot cropper using exact-source local-frame calibration."""

    version = LOCAL_CALIBRATED_CROPPER_VERSION


@dataclass(frozen=True, slots=True)
class CellArtifact:
    row_index: int
    column_index: int
    relative_path: str
    checksum_sha256: str
    width: int
    height: int

    def to_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "columnIndex": self.column_index,
            "height": self.height,
            "relativePath": self.relative_path,
            "rowIndex": self.row_index,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class BoardArtifact:
    position_index: int
    source_quad: Quad
    transform_matrix: tuple[tuple[float, float, float], ...]
    board_relative_path: str
    board_checksum_sha256: str
    overlay_relative_path: str
    overlay_checksum_sha256: str
    cells: tuple[CellArtifact, ...]
    grid_contract: GridContract
    source_quad_source: str | None
    calibration_profile_id: str | None
    calibration_profile_version: int | None
    calibration_anchor_sequence_numbers: tuple[int, ...]
    calibration_interpolation_weight: float | None
    symbol_refinement: SymbolRefinementMetadata | None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "boardChecksumSha256": self.board_checksum_sha256,
            "boardHeight": BOARD_HEIGHT,
            "boardRelativePath": self.board_relative_path,
            "boardWidth": BOARD_WIDTH,
            "cells": [cell.to_dict() for cell in self.cells],
            "grid": self.grid_contract.to_dict(),
            "overlayChecksumSha256": self.overlay_checksum_sha256,
            "overlayRelativePath": self.overlay_relative_path,
            "positionIndex": self.position_index,
            "sourceQuad": [point.to_dict() for point in self.source_quad],
            "transformMatrix": [list(row) for row in self.transform_matrix],
        }
        if self.source_quad_source is not None:
            value["sourceQuadSource"] = self.source_quad_source
        if self.calibration_profile_id is not None:
            value["calibrationProfile"] = {
                "anchorSequenceNumbers": list(self.calibration_anchor_sequence_numbers),
                "interpolationWeight": self.calibration_interpolation_weight,
                "profileId": self.calibration_profile_id,
                "profileVersion": self.calibration_profile_version,
            }
        if self.symbol_refinement is not None:
            value["symbolRefinement"] = self.symbol_refinement.to_dict()
        return value


@dataclass(frozen=True, slots=True)
class ImageCropArtifacts:
    source_checksum_sha256: str
    normalized_relative_path: str
    status: Literal["cropped", "needs_review"]
    review_reasons: tuple[str, ...]
    boards: tuple[BoardArtifact, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "boards": [board.to_dict() for board in self.boards],
            "normalizedRelativePath": self.normalized_relative_path,
            "reviewReasons": list(self.review_reasons),
            "sourceChecksumSha256": self.source_checksum_sha256,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CorpusCropReport:
    cropper_version: str
    normalization_report_sha256: str
    detection_report_sha256: str
    images: tuple[ImageCropArtifacts, ...]
    calibration_profile_set_version: str | None = None
    calibration_profile_set_sha256: str | None = None
    corpus_manifest_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        board_count = sum(len(image.boards) for image in self.images)
        cell_count = sum(len(board.cells) for image in self.images for board in image.boards)
        cropped_count = sum(image.status == "cropped" for image in self.images)
        value: dict[str, object] = {
            "boardCount": board_count,
            "cellCount": cell_count,
            "cropperVersion": self.cropper_version,
            "croppedImageCount": cropped_count,
            "detectionReportSha256": self.detection_report_sha256,
            "imageCount": len(self.images),
            "images": [image.to_dict() for image in self.images],
            "needsReviewCount": len(self.images) - cropped_count,
            "normalizationReportSha256": self.normalization_report_sha256,
            "numpyVersion": np.__version__,
            "opencvVersion": cv2.__version__,
            "schemaVersion": 1,
            "status": ("cropped" if cropped_count == len(self.images) else "needs_review"),
        }
        if self.calibration_profile_set_version is not None:
            value["calibrationProfileSetSha256"] = self.calibration_profile_set_sha256
            value["calibrationProfileSetVersion"] = self.calibration_profile_set_version
            value["corpusManifestSha256"] = self.corpus_manifest_sha256
        return value

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _safe_artifact_path(root: Path, value: object, label: str) -> tuple[str, Path]:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BoardCropError(
            "BOARD_CROP_UNSAFE_ARTIFACT_PATH",
            f"{label} must be a safe relative POSIX path.",
        )
    try:
        resolved = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise BoardCropError(
            "BOARD_CROP_NORMALIZED_IMAGE_UNREADABLE",
            f"{label} cannot be resolved.",
        ) from error
    if not resolved.is_relative_to(root):
        raise BoardCropError(
            "BOARD_CROP_UNSAFE_ARTIFACT_PATH",
            f"{label} escapes its artifact root.",
        )
    return text, resolved


def _point(value: object, label: str) -> Point:
    item = _mapping(value, label)
    return Point(
        x=_integer(item.get("x"), f"{label}.x"),
        y=_integer(item.get("y"), f"{label}.y"),
    )


def _page_geometry(value: Mapping[str, object], label: str) -> PageGeometry:
    status = value.get("status")
    if status not in {"detected", "needs_review"}:
        raise BoardCropError(
            "BOARD_CROP_REPORT_INVALID",
            f"{label}.status is invalid.",
        )
    boards: list[BoardGeometry] = []
    for index, board_value in enumerate(_sequence(value.get("boards"), f"{label}.boards")):
        board = _mapping(board_value, f"{label}.boards[{index}]")
        quad_values = _sequence(
            board.get("quad"),
            f"{label}.boards[{index}].quad",
        )
        if len(quad_values) != 4:
            raise BoardCropError(
                "BOARD_CROP_REPORT_INVALID",
                f"{label}.boards[{index}].quad must contain four points.",
            )
        quad = cast(
            Quad,
            tuple(
                _point(point, f"{label}.boards[{index}].quad[{point_index}]")
                for point_index, point in enumerate(quad_values)
            ),
        )
        raw_bounding_box = board.get("boundingBox")
        bounding_box: tuple[int, int, int, int] | None = None
        if raw_bounding_box is not None:
            bounding_box_value = _mapping(
                raw_bounding_box,
                f"{label}.boards[{index}].boundingBox",
            )
            bounding_box = (
                _integer(
                    bounding_box_value.get("x"),
                    f"{label}.boards[{index}].boundingBox.x",
                ),
                _integer(
                    bounding_box_value.get("y"),
                    f"{label}.boards[{index}].boundingBox.y",
                ),
                _integer(
                    bounding_box_value.get("width"),
                    f"{label}.boards[{index}].boundingBox.width",
                ),
                _integer(
                    bounding_box_value.get("height"),
                    f"{label}.boards[{index}].boundingBox.height",
                ),
            )
            if bounding_box[2] < 2 or bounding_box[3] < 2:
                raise BoardCropError(
                    "BOARD_CROP_REPORT_INVALID",
                    f"{label}.boards[{index}].boundingBox is degenerate.",
                )
        boards.append(
            BoardGeometry(
                position_index=_integer(
                    board.get("positionIndex"),
                    f"{label}.boards[{index}].positionIndex",
                ),
                quad=quad,
                bounding_box=bounding_box,
            )
        )
    reasons = tuple(
        _text(reason, f"{label}.reviewReasons[{index}]")
        for index, reason in enumerate(
            _sequence(value.get("reviewReasons"), f"{label}.reviewReasons")
        )
    )
    return PageGeometry(
        status=cast(Literal["detected", "needs_review"], status),
        image_width=_integer(value.get("imageWidth"), f"{label}.imageWidth"),
        image_height=_integer(value.get("imageHeight"), f"{label}.imageHeight"),
        boards=tuple(boards),
        review_reasons=reasons,
    )


def page_geometry_from_report(
    value: Mapping[str, object],
    label: str = "pageGeometry",
) -> PageGeometry:
    """Parse one detector result through the public crop contract boundary."""

    return _page_geometry(value, label)


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    encoded, buffer = cv2.imencode(
        ".png",
        bgr,
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise BoardCropError(
            "BOARD_CROP_ENCODE_FAILED",
            "Board crop artifact cannot be encoded.",
        )
    return bytes(buffer)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise BoardCropError(
                "BOARD_CROP_ARTIFACT_UNREADABLE",
                "Existing board crop artifact cannot be read.",
            ) from error
        if existing != content:
            raise BoardCropError(
                "BOARD_CROP_ARTIFACT_COLLISION",
                "Existing board crop artifact has different content.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise BoardCropError(
            "BOARD_CROP_ARTIFACT_WRITE_FAILED",
            "Board crop artifact cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact(
    *,
    artifact_root: Path,
    relative_path: str,
    rgb: NDArray[np.uint8],
) -> str:
    content = _encode_png(rgb)
    path = artifact_root / Path(*PurePosixPath(relative_path).parts)
    _write_immutable(path, content)
    return hashlib.sha256(content).hexdigest()


def _load_json(path: Path, code: str, message: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise BoardCropError(code, message) from error
    return content, _mapping(value, path.name)


def crop_detected_corpus(
    normalization_report_path: Path,
    detection_report_path: Path,
    normalization_root: Path,
    artifact_root: Path,
    *,
    cropper: BoardCellCropper | None = None,
    calibrator: PageGeometryCalibrator | None = None,
) -> CorpusCropReport:
    """Rectify every complete detection after verifying both upstream reports."""

    normalization_bytes, normalization = _load_json(
        normalization_report_path,
        "BOARD_CROP_NORMALIZATION_REPORT_INVALID",
        "Normalization report cannot be read.",
    )
    detection_bytes, detection = _load_json(
        detection_report_path,
        "BOARD_CROP_DETECTION_REPORT_INVALID",
        "Page detection report cannot be read.",
    )
    if (
        normalization.get("normalizationVersion") != "image-normalization-v1"
        or normalization.get("status") != "clean"
    ):
        raise BoardCropError(
            "BOARD_CROP_NORMALIZATION_UNSUPPORTED",
            "A clean image-normalization-v1 report is required.",
        )
    normalization_sha = hashlib.sha256(normalization_bytes).hexdigest()
    if (
        detection.get("detectorVersion") != DETECTOR_VERSION
        or detection.get("normalizationReportSha256") != normalization_sha
    ):
        raise BoardCropError(
            "BOARD_CROP_DETECTION_REPORT_DRIFT",
            "Page detection report does not match normalization input.",
        )
    detection_sha = hashlib.sha256(detection_bytes).hexdigest()
    if calibrator is not None and calibrator.detection_report_sha256 != detection_sha:
        raise BoardCropError(
            "BOARD_CROP_CALIBRATION_DETECTION_DRIFT",
            "Calibration profiles do not match the current detection report.",
        )
    try:
        normalization_base = normalization_root.resolve(strict=True)
    except OSError as error:
        raise BoardCropError(
            "BOARD_CROP_NORMALIZATION_ROOT_NOT_FOUND",
            "Normalization artifact root does not exist.",
        ) from error
    if not normalization_base.is_dir():
        raise BoardCropError(
            "BOARD_CROP_NORMALIZATION_ROOT_NOT_DIRECTORY",
            "Normalization artifact root must be a directory.",
        )
    crop_base = artifact_root.resolve()
    if crop_base == normalization_base or crop_base.is_relative_to(normalization_base):
        raise BoardCropError(
            "BOARD_CROP_OUTPUT_IN_NORMALIZATION_ROOT",
            "Board crop artifacts must use a separate root.",
        )

    normalized_by_source: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(_sequence(normalization.get("images"), "images")):
        item = _mapping(value, f"images[{index}]")
        source_checksum = _sha256(
            item.get("sourceChecksumSha256"),
            f"images[{index}].sourceChecksumSha256",
        )
        if source_checksum in normalized_by_source:
            raise BoardCropError(
                "BOARD_CROP_REPORT_INVALID",
                "Normalization report contains duplicate source checksums.",
            )
        normalized_by_source[source_checksum] = item

    detections = _sequence(detection.get("detections"), "detections")
    if len(detections) != len(normalized_by_source):
        raise BoardCropError(
            "BOARD_CROP_DETECTION_REPORT_DRIFT",
            "Detection and normalization image counts differ.",
        )
    implementation = cropper or PerspectiveBoardCellCropper()
    images: list[ImageCropArtifacts] = []
    seen_sources: set[str] = set()
    for index, value in enumerate(detections):
        item = _mapping(value, f"detections[{index}]")
        source_checksum = _sha256(
            item.get("sourceChecksumSha256"),
            f"detections[{index}].sourceChecksumSha256",
        )
        if source_checksum in seen_sources or source_checksum not in normalized_by_source:
            raise BoardCropError(
                "BOARD_CROP_DETECTION_REPORT_DRIFT",
                "Detection source identity is missing or duplicated.",
            )
        seen_sources.add(source_checksum)
        normalized = normalized_by_source[source_checksum]
        relative_path, normalized_path = _safe_artifact_path(
            normalization_base,
            normalized.get("normalizedRelativePath"),
            f"images[{index}].normalizedRelativePath",
        )
        if item.get("normalizedRelativePath") != relative_path:
            raise BoardCropError(
                "BOARD_CROP_DETECTION_REPORT_DRIFT",
                "Detection normalized path differs from normalization report.",
            )
        expected_checksum = _sha256(
            normalized.get("normalizedChecksumSha256"),
            f"images[{index}].normalizedChecksumSha256",
        )
        try:
            normalized_bytes = normalized_path.read_bytes()
        except OSError as error:
            raise BoardCropError(
                "BOARD_CROP_NORMALIZED_IMAGE_UNREADABLE",
                "Normalized image cannot be read.",
            ) from error
        if hashlib.sha256(normalized_bytes).hexdigest() != expected_checksum:
            raise BoardCropError(
                "BOARD_CROP_NORMALIZED_CHECKSUM_MISMATCH",
                "Normalized image checksum differs from its report.",
            )
        bgr = cv2.imdecode(
            np.frombuffer(normalized_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if bgr is None:
            raise BoardCropError(
                "BOARD_CROP_NORMALIZED_DECODE_FAILED",
                "Normalized image cannot be decoded.",
            )
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        geometry = _page_geometry(
            _mapping(item.get("result"), f"detections[{index}].result"),
            f"detections[{index}].result",
        )
        if calibrator is not None:
            geometry = calibrator.calibrate(source_checksum, geometry)
        result = implementation.crop(rgb, geometry)
        board_artifacts: list[BoardArtifact] = []
        if result.status == "cropped":
            image_root = PurePosixPath(
                implementation.version,
                source_checksum[:2],
                source_checksum,
            )
            for board in result.boards:
                board_root = image_root / f"board-{board.position_index:02d}"
                board_relative = (board_root / "board.png").as_posix()
                board_checksum = _artifact(
                    artifact_root=crop_base,
                    relative_path=board_relative,
                    rgb=board.board_rgb,
                )
                overlay_relative = (board_root / "grid-overlay.png").as_posix()
                overlay_checksum = _artifact(
                    artifact_root=crop_base,
                    relative_path=overlay_relative,
                    rgb=board.grid_overlay_rgb,
                )
                cell_artifacts: list[CellArtifact] = []
                for cell in board.cells:
                    cell_relative = (
                        board_root / "cells" / f"r{cell.row_index:02d}-c{cell.column_index:02d}.png"
                    ).as_posix()
                    cell_artifacts.append(
                        CellArtifact(
                            row_index=cell.row_index,
                            column_index=cell.column_index,
                            relative_path=cell_relative,
                            checksum_sha256=_artifact(
                                artifact_root=crop_base,
                                relative_path=cell_relative,
                                rgb=cell.rgb,
                            ),
                            width=int(cell.rgb.shape[1]),
                            height=int(cell.rgb.shape[0]),
                        )
                    )
                board_artifacts.append(
                    BoardArtifact(
                        position_index=board.position_index,
                        source_quad=board.source_quad,
                        transform_matrix=board.transform_matrix,
                        board_relative_path=board_relative,
                        board_checksum_sha256=board_checksum,
                        overlay_relative_path=overlay_relative,
                        overlay_checksum_sha256=overlay_checksum,
                        cells=tuple(cell_artifacts),
                        grid_contract=board.grid_contract,
                        source_quad_source=board.source_quad_source,
                        calibration_profile_id=board.calibration_profile_id,
                        calibration_profile_version=board.calibration_profile_version,
                        calibration_anchor_sequence_numbers=(
                            board.calibration_anchor_sequence_numbers
                        ),
                        calibration_interpolation_weight=(board.calibration_interpolation_weight),
                        symbol_refinement=board.symbol_refinement,
                    )
                )
        images.append(
            ImageCropArtifacts(
                source_checksum_sha256=source_checksum,
                normalized_relative_path=relative_path,
                status=result.status,
                review_reasons=result.review_reasons,
                boards=tuple(board_artifacts),
            )
        )
    return CorpusCropReport(
        cropper_version=implementation.version,
        normalization_report_sha256=normalization_sha,
        detection_report_sha256=detection_sha,
        images=tuple(images),
        calibration_profile_set_version=(
            calibrator.profile_set_version if calibrator is not None else None
        ),
        calibration_profile_set_sha256=(
            calibrator.profile_set_sha256 if calibrator is not None else None
        ),
        corpus_manifest_sha256=(
            calibrator.corpus_manifest_sha256 if calibrator is not None else None
        ),
    )
