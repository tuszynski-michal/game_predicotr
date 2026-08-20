"""Read-only v19 board-cell geometry preview for the Reviewer editor."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .board_cell_geometry_contract import (
    BOARD_CELL_COUNT,
    BOARD_COLUMNS,
    BOARD_ROWS,
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    Quad,
    derive_board_cell_quads,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceCrop,
    BoardCellGeometrySourceDirectCropper,
)

MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION = "manual-board-cell-geometry-v19-preview-v1"
MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE = 64


class ManualBoardCellGeometryPreviewError(ValueError):
    """Stable failure raised before a v19 preview can be returned."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryCellPreview:
    row_index: int
    column_index: int
    png: bytes
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryPreview:
    lattice_bounds_quad: Quad
    image_width: int
    image_height: int
    contact_sheet_png: bytes
    contact_sheet_checksum_sha256: str
    cropper_version: str
    cropper_fingerprint_sha256: str
    cells: tuple[ManualBoardCellGeometryCellPreview, ...]


class ManualBoardCellGeometryPreviewer:
    """Validate one manual lattice and render its 15 final v19 crops."""

    version = MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION

    def __init__(
        self,
        *,
        cell_output_size: int = MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
    ) -> None:
        self._cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=cell_output_size)

    def preview(
        self,
        *,
        source_path: Path,
        expected_source_sha256: str,
        source_order_index: int,
        source_image_id: str,
        source_image_relative_path: str,
        source_group: str,
        sequence_number: int,
        position_index: int,
        lattice_bounds_quad: Quad,
        decision_checksum_sha256: str,
    ) -> ManualBoardCellGeometryPreview:
        content = _read_source(source_path)
        if hashlib.sha256(content).hexdigest() != expected_source_sha256:
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_PREVIEW_SOURCE_CHECKSUM_DRIFT",
                "The source image changed before board-cell geometry preview.",
            )
        encoded = np.frombuffer(content, dtype=np.uint8)
        bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_PREVIEW_SOURCE_DECODE_FAILED",
                "The source image cannot be decoded for board-cell geometry preview.",
            )
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        image_height, image_width = rgb.shape[:2]
        try:
            cells = derive_board_cell_quads(
                lattice_bounds_quad,
                source_image_width=image_width,
                source_image_height=image_height,
            )
        except ValueError as error:
            code = getattr(error, "code", "BOARD_CELL_GEOMETRY_PREVIEW_INVALID")
            raise ManualBoardCellGeometryPreviewError(code, str(error)) from error
        geometry = BoardCellGeometryEntry(
            source_order_index=source_order_index,
            image_id=source_image_id,
            source_image_checksum_sha256=expected_source_sha256,
            source_image_relative_path=source_image_relative_path,
            source_image_width=image_width,
            source_image_height=image_height,
            source_group=source_group,
            condition_tags=("manual-preview",),
            sequence_number=sequence_number,
            position_index=position_index,
            lattice_bounds_quad=lattice_bounds_quad,
            cells=cells,
            evidence=BoardCellGeometryEvidence(
                kind="manual_override",
                estimator_version=self.version,
                thresholds_version=self.version,
                locator_version=None,
                homography_version=None,
                candidate_center_count=0,
                reliable_center_count=0,
                inlier_count=0,
                inlier_slots=(),
                inlier_p95_residual_px=None,
                decision_checksum_sha256=decision_checksum_sha256,
            ),
        )
        result = self._cropper.crop(rgb, geometry)
        if result.status != "cropped" or len(result.cells) != BOARD_CELL_COUNT:
            reason = result.review_reasons[0] if result.review_reasons else "unknown"
            raise ManualBoardCellGeometryPreviewError(
                reason,
                f"The board-cell geometry preview cannot be cropped: {reason}.",
            )
        previews = tuple(
            ManualBoardCellGeometryCellPreview(
                row_index=cell.row_index,
                column_index=cell.column_index,
                png=(png := _encode_png(cell.rgb)),
                checksum_sha256=hashlib.sha256(png).hexdigest(),
            )
            for cell in result.cells
        )
        contact_sheet = _contact_sheet(result.cells)
        contact_sheet_png = _encode_png(contact_sheet)
        return ManualBoardCellGeometryPreview(
            lattice_bounds_quad=lattice_bounds_quad,
            image_width=image_width,
            image_height=image_height,
            contact_sheet_png=contact_sheet_png,
            contact_sheet_checksum_sha256=hashlib.sha256(contact_sheet_png).hexdigest(),
            cropper_version=CROPPER_VERSION,
            cropper_fingerprint_sha256=result.cropper_fingerprint_sha256,
            cells=previews,
        )


def _read_source(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_PREVIEW_SOURCE_UNREADABLE",
            "The source image cannot be read for board-cell geometry preview.",
        ) from error


def _contact_sheet(
    cells: tuple[BoardCellGeometrySourceCrop, ...],
) -> NDArray[np.uint8]:
    if len(cells) != BOARD_CELL_COUNT:
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_PREVIEW_CELL_COUNT_INVALID",
            "Board-cell geometry preview requires exactly 15 crops.",
        )
    rows = []
    for row_index in range(BOARD_ROWS):
        row_cells = cells[row_index * BOARD_COLUMNS : (row_index + 1) * BOARD_COLUMNS]
        rows.append(np.concatenate([cell.rgb for cell in row_cells], axis=1))
    return cast(NDArray[np.uint8], np.concatenate(rows, axis=0))


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, payload = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not encoded:
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_PREVIEW_ENCODE_FAILED",
            "A final board-cell crop could not be encoded.",
        )
    return bytes(payload)


__all__ = [
    "MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE",
    "MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION",
    "ManualBoardCellGeometryCellPreview",
    "ManualBoardCellGeometryPreview",
    "ManualBoardCellGeometryPreviewError",
    "ManualBoardCellGeometryPreviewer",
]
