"""Deterministic, immutable recrop for one manually corrected board quad."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Point, Quad
from .rectification import (
    BOARD_COLUMNS,
    BOARD_ROWS,
    BoardCropError,
    BoardGeometry,
    PageGeometry,
    PerspectiveBoardCellCropperV2,
)

MANUAL_GEOMETRY_CROPPER_VERSION = "manual-review-geometry-v1"


@dataclass(frozen=True, slots=True)
class ManualGeometryCellPreview:
    row_index: int
    column_index: int
    png: bytes
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ManualGeometryPreview:
    source_quad: Quad
    image_width: int
    image_height: int
    board_png: bytes
    board_checksum_sha256: str
    transform_matrix: tuple[tuple[float, float, float], ...]
    cells: tuple[ManualGeometryCellPreview, ...]


@dataclass(frozen=True, slots=True)
class ManualGeometryCellArtifact:
    row_index: int
    column_index: int
    relative_path: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ManualGeometryArtifacts:
    source_quad: Quad
    image_width: int
    image_height: int
    board_relative_path: str
    board_checksum_sha256: str
    transform_matrix: tuple[tuple[float, float, float], ...]
    cropper_version: str
    cells: tuple[ManualGeometryCellArtifact, ...]


class ManualGeometryRecropper:
    """Use the retained v2 crop contract for an operator-provided source quad."""

    version = MANUAL_GEOMETRY_CROPPER_VERSION

    def __init__(self) -> None:
        self._cropper = PerspectiveBoardCellCropperV2()

    def preview(
        self,
        *,
        source_path: Path,
        expected_source_sha256: str,
        corners: Quad,
    ) -> ManualGeometryPreview:
        content = _read_source(source_path)
        if hashlib.sha256(content).hexdigest() != expected_source_sha256:
            raise BoardCropError(
                "MANUAL_GEOMETRY_SOURCE_CHECKSUM_DRIFT",
                "The source image changed before manual geometry correction.",
            )
        encoded = np.frombuffer(content, dtype=np.uint8)
        bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if bgr is None:
            raise BoardCropError(
                "MANUAL_GEOMETRY_SOURCE_DECODE_FAILED",
                "The source image cannot be decoded.",
            )
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        image_height, image_width = rgb.shape[:2]
        _validate_bounds(corners, image_width=image_width, image_height=image_height)
        geometry = PageGeometry(
            status="detected",
            image_width=image_width,
            image_height=image_height,
            boards=(
                BoardGeometry(
                    position_index=0,
                    quad=corners,
                    source_quad_source="manual_review",
                ),
            ),
        )
        result = self._cropper.crop(rgb, geometry)
        if result.status != "cropped" or len(result.boards) != 1:
            reason = result.review_reasons[0] if result.review_reasons else "unknown"
            raise BoardCropError(
                "MANUAL_GEOMETRY_INVALID",
                f"The corrected geometry cannot be cropped: {reason}.",
            )
        board = result.boards[0]
        board_png = _encode_png(board.board_rgb)
        cells = tuple(
            ManualGeometryCellPreview(
                row_index=cell.row_index,
                column_index=cell.column_index,
                png=(png := _encode_png(cell.rgb)),
                checksum_sha256=hashlib.sha256(png).hexdigest(),
            )
            for cell in board.cells
        )
        if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
            raise BoardCropError(
                "MANUAL_GEOMETRY_CELL_COUNT_INVALID",
                "Manual geometry correction must produce exactly 15 cells.",
            )
        return ManualGeometryPreview(
            source_quad=corners,
            image_width=image_width,
            image_height=image_height,
            board_png=board_png,
            board_checksum_sha256=hashlib.sha256(board_png).hexdigest(),
            transform_matrix=board.transform_matrix,
            cells=cells,
        )

    def persist(
        self,
        *,
        preview: ManualGeometryPreview,
        managed_data_root: Path,
        review_item_id: str,
        revision: int,
    ) -> ManualGeometryArtifacts:
        if revision < 1:
            raise BoardCropError(
                "MANUAL_GEOMETRY_REVISION_INVALID",
                "Manual geometry revision must be positive.",
            )
        review_path_key = hashlib.sha256(review_item_id.encode()).hexdigest()[:16]
        namespace = PurePosixPath(
            "image-review-geometry",
            review_path_key,
            f"r{revision}",
        )
        board_relative_path = str(namespace / f"board-{preview.board_checksum_sha256}.png")
        _write_immutable(
            managed_data_root.joinpath(*PurePosixPath(board_relative_path).parts),
            preview.board_png,
        )
        cells: list[ManualGeometryCellArtifact] = []
        for cell in preview.cells:
            relative_path = str(
                namespace
                / (f"cell-r{cell.row_index}-c{cell.column_index}-{cell.checksum_sha256}.png")
            )
            _write_immutable(
                managed_data_root.joinpath(*PurePosixPath(relative_path).parts),
                cell.png,
            )
            cells.append(
                ManualGeometryCellArtifact(
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    relative_path=relative_path,
                    checksum_sha256=cell.checksum_sha256,
                )
            )
        return ManualGeometryArtifacts(
            source_quad=preview.source_quad,
            image_width=preview.image_width,
            image_height=preview.image_height,
            board_relative_path=board_relative_path,
            board_checksum_sha256=preview.board_checksum_sha256,
            transform_matrix=preview.transform_matrix,
            cropper_version=self.version,
            cells=tuple(cells),
        )


def _read_source(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise BoardCropError(
            "MANUAL_GEOMETRY_SOURCE_UNREADABLE",
            "The source image cannot be read.",
        ) from error


def _validate_bounds(corners: Quad, *, image_width: int, image_height: int) -> None:
    if any(
        point.x < 0 or point.y < 0 or point.x >= image_width or point.y >= image_height
        for point in corners
    ):
        raise BoardCropError(
            "MANUAL_GEOMETRY_OUT_OF_BOUNDS",
            "Every corrected corner must remain inside the source image.",
        )


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise BoardCropError(
            "MANUAL_GEOMETRY_ENCODE_FAILED",
            "The corrected board cannot be encoded.",
        )
    return bytes(buffer)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        try:
            if path.read_bytes() != content:
                raise BoardCropError(
                    "MANUAL_GEOMETRY_ARTIFACT_COLLISION",
                    "An immutable geometry artifact has different content.",
                )
        except OSError as error:
            raise BoardCropError(
                "MANUAL_GEOMETRY_ARTIFACT_UNREADABLE",
                "An immutable geometry artifact cannot be read.",
            ) from error
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise BoardCropError(
            "MANUAL_GEOMETRY_ARTIFACT_WRITE_FAILED",
            "A corrected geometry artifact cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "MANUAL_GEOMETRY_CROPPER_VERSION",
    "ManualGeometryArtifacts",
    "ManualGeometryCellArtifact",
    "ManualGeometryCellPreview",
    "ManualGeometryPreview",
    "ManualGeometryRecropper",
    "Point",
]
