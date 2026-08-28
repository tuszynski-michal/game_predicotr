"""One-pass source-image crops for validated v19 board-cell geometry."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    BOARD_COLUMNS,
    BOARD_ROWS,
    MIN_INLIER_COUNT,
    MIN_RELIABLE_CENTER_COUNT,
    BoardCellGeometryContractError,
    BoardCellGeometryEntry,
    BoardCellQuad,
    BoardCellTopology,
    EvidenceKind,
    Quad,
    derive_board_cell_quads,
)

CROPPER_VERSION = "board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1"
PADDING_VERSION = "board-cell-padding-v19-canonical-inset-10-v1"
INTERPOLATION_VERSION = "opencv-inter-linear-v1"
BORDER_POLICY_VERSION = "full-source-support-no-synthesis-v1"
CANONICAL_CELL_SIZE = 100.0
FIXED_PADDING_CANONICAL_PX = 10.0
FIXED_PADDING_FRACTION = FIXED_PADDING_CANONICAL_PX / CANONICAL_CELL_SIZE
_CELL_COORDINATE_TOLERANCE = 0.0002


class BoardCellGeometryCropError(ValueError):
    """Stable programmer-input error for the v19 source-direct cropper."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BoardCellGeometrySourceCrop:
    row_index: int
    column_index: int
    source_quad: Quad
    padded_source_quad: Quad
    rgb: NDArray[np.uint8]

    def metadata_dict(self) -> dict[str, object]:
        return {
            "columnIndex": self.column_index,
            "paddedSourceQuad": _quad_dict(self.padded_source_quad),
            "rowIndex": self.row_index,
            "sourceQuad": _quad_dict(self.source_quad),
        }


@dataclass(frozen=True, slots=True)
class BoardCellGeometryCropResult:
    status: Literal["cropped", "needs_review"]
    sequence_number: int
    position_index: int
    source_image_checksum_sha256: str
    cell_output_size: int
    cropper_fingerprint_sha256: str
    cells: tuple[BoardCellGeometrySourceCrop, ...]
    review_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "borderPolicyVersion": BORDER_POLICY_VERSION,
            "cellCount": len(self.cells),
            "cellOutputSize": self.cell_output_size,
            "cells": [cell.metadata_dict() for cell in self.cells],
            "cropperFingerprintSha256": self.cropper_fingerprint_sha256,
            "cropperVersion": CROPPER_VERSION,
            "fixedPaddingCanonicalPx": FIXED_PADDING_CANONICAL_PX,
            "fixedPaddingFraction": FIXED_PADDING_FRACTION,
            "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
            "interpolationVersion": INTERPOLATION_VERSION,
            "paddingVersion": PADDING_VERSION,
            "positionIndex": self.position_index,
            "reviewReasons": list(self.review_reasons),
            "sequenceNumber": self.sequence_number,
            "sourceImageChecksumSha256": self.source_image_checksum_sha256,
            "status": self.status,
        }


class BoardCellGeometrySourceDirectCropper:
    """Project all 15 validated v19 cells straight from source RGB pixels.

    The canonical 5 x 3 plane exists only to derive the fixed inset. The
    implementation never materializes a rectified board bitmap: every final
    model crop is produced by one source-to-output ``warpPerspective`` call.
    """

    version = CROPPER_VERSION

    def __init__(
        self,
        *,
        cell_output_size: int,
        topology: BoardCellTopology | None = None,
    ) -> None:
        if cell_output_size <= 0:
            raise ValueError("cell_output_size must be positive")
        self.cell_output_size = cell_output_size
        self.topology = topology or BoardCellTopology(rows=BOARD_ROWS, columns=BOARD_COLUMNS)
        self.fingerprint_sha256 = cropper_fingerprint_sha256(
            cell_output_size=cell_output_size,
            topology=topology,
        )

    def crop(
        self,
        rgb_image: NDArray[np.uint8],
        geometry: BoardCellGeometryEntry,
    ) -> BoardCellGeometryCropResult:
        if rgb_image.ndim != 3 or rgb_image.shape[2] != 3 or rgb_image.dtype != np.uint8:
            raise BoardCellGeometryCropError(
                "BOARD_CELL_CROP_INVALID_IMAGE",
                "Cropper input must be an RGB uint8 image.",
            )
        image_height, image_width = rgb_image.shape[:2]
        if (
            geometry.source_image_width != image_width
            or geometry.source_image_height != image_height
        ):
            return self._needs_review(geometry, "BOARD_CELL_CROP_IMAGE_DIMENSIONS_MISMATCH")
        if geometry.topology != self.topology:
            return self._needs_review(geometry, "BOARD_CELL_CROP_TOPOLOGY_MISMATCH")
        reason = _geometry_review_reason(geometry, topology=self.topology)
        if reason is not None:
            return self._needs_review(geometry, reason)

        padded_quads = _padded_source_quads(
            geometry.lattice_bounds_quad,
            topology=self.topology,
        )
        if len(padded_quads) != self.topology.cell_count or not all(
            _quad_has_full_source_support(
                quad,
                source_width=image_width,
                source_height=image_height,
            )
            for quad in padded_quads
        ):
            return self._needs_review(geometry, "BOARD_CELL_CROP_SOURCE_SUPPORT_INCOMPLETE")

        # Validate the complete board before the first interpolation. A bad
        # final cell therefore cannot leave a partial crop result behind.
        prepared = tuple(zip(geometry.cells, padded_quads, strict=True))
        cells = tuple(
            BoardCellGeometrySourceCrop(
                row_index=cell.row_index,
                column_index=cell.column_index,
                source_quad=cell.quad,
                padded_source_quad=padded_quad,
                rgb=_project_source_quad_once(
                    rgb_image,
                    padded_source_quad=padded_quad,
                    output_size=self.cell_output_size,
                ),
            )
            for cell, padded_quad in prepared
        )
        return BoardCellGeometryCropResult(
            status="cropped",
            sequence_number=geometry.sequence_number,
            position_index=geometry.position_index,
            source_image_checksum_sha256=geometry.source_image_checksum_sha256,
            cell_output_size=self.cell_output_size,
            cropper_fingerprint_sha256=self.fingerprint_sha256,
            cells=cells,
            review_reasons=(),
        )

    def _needs_review(
        self,
        geometry: BoardCellGeometryEntry,
        reason: str,
    ) -> BoardCellGeometryCropResult:
        return BoardCellGeometryCropResult(
            status="needs_review",
            sequence_number=geometry.sequence_number,
            position_index=geometry.position_index,
            source_image_checksum_sha256=geometry.source_image_checksum_sha256,
            cell_output_size=self.cell_output_size,
            cropper_fingerprint_sha256=self.fingerprint_sha256,
            cells=(),
            review_reasons=(reason,),
        )


def cropper_fingerprint_sha256(
    *,
    cell_output_size: int,
    topology: BoardCellTopology | None = None,
) -> str:
    """Return the immutable fingerprint for one pinned raster-output contract."""

    if cell_output_size <= 0:
        raise ValueError("cell_output_size must be positive")
    payload = {
        "borderPolicyVersion": BORDER_POLICY_VERSION,
        "canonicalCellSize": CANONICAL_CELL_SIZE,
        "cellOutputSize": cell_output_size,
        "cropperVersion": CROPPER_VERSION,
        "fixedPaddingCanonicalPx": FIXED_PADDING_CANONICAL_PX,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "interpolationVersion": INTERPOLATION_VERSION,
        "paddingVersion": PADDING_VERSION,
        "sourceImageContract": "rgb-uint8-exif-normalized-v1",
    }
    if topology is not None:
        payload["gridRows"] = topology.rows
        payload["gridColumns"] = topology.columns
        payload["topologyRulesVersionId"] = topology.rules_version_id
    encoded = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _geometry_review_reason(
    geometry: BoardCellGeometryEntry,
    *,
    topology: BoardCellTopology,
) -> str | None:
    if not _evidence_is_valid(geometry.evidence.kind, geometry, topology=topology):
        return "BOARD_CELL_CROP_EVIDENCE_INVALID"
    if len(geometry.cells) != topology.cell_count:
        return "BOARD_CELL_CROP_CELL_COUNT_INVALID"
    if [(cell.row_index, cell.column_index) for cell in geometry.cells] != [
        (row, column) for row in range(topology.rows) for column in range(topology.columns)
    ]:
        return "BOARD_CELL_CROP_CELL_ORDER_INVALID"
    try:
        expected = derive_board_cell_quads(
            geometry.lattice_bounds_quad,
            source_image_width=geometry.source_image_width,
            source_image_height=geometry.source_image_height,
            topology=topology,
        )
    except BoardCellGeometryContractError as error:
        return error.code
    if any(
        not _cell_matches(actual, derived)
        for actual, derived in zip(geometry.cells, expected, strict=True)
    ):
        return "BOARD_CELL_CROP_CELL_DERIVATION_MISMATCH"
    return None


def _evidence_is_valid(
    kind: EvidenceKind,
    geometry: BoardCellGeometryEntry,
    *,
    topology: BoardCellTopology,
) -> bool:
    evidence = geometry.evidence
    if kind == "automatic":
        slots = evidence.inlier_slots
        return (
            evidence.candidate_center_count >= evidence.reliable_center_count
            and evidence.reliable_center_count >= evidence.inlier_count
            and evidence.reliable_center_count >= MIN_RELIABLE_CENTER_COUNT
            and evidence.inlier_count >= MIN_INLIER_COUNT
            and evidence.inlier_count == len(slots)
            and len(set(slots)) == len(slots)
            and {row for row, _ in slots} == set(range(topology.rows))
            and {column for _, column in slots} == set(range(topology.columns))
            and evidence.inlier_p95_residual_px is not None
            and math.isfinite(evidence.inlier_p95_residual_px)
            and evidence.locator_version is not None
            and evidence.homography_version is not None
            and evidence.decision_checksum_sha256 is None
        )
    return (
        kind in {"human_reviewed", "manual_override"}
        and evidence.candidate_center_count == 0
        and evidence.reliable_center_count == 0
        and evidence.inlier_count == 0
        and not evidence.inlier_slots
        and evidence.inlier_p95_residual_px is None
        and evidence.locator_version is None
        and evidence.homography_version is None
        and evidence.decision_checksum_sha256 is not None
    )


def _cell_matches(actual: BoardCellQuad, expected: BoardCellQuad) -> bool:
    return (
        actual.row_index == expected.row_index
        and actual.column_index == expected.column_index
        and all(
            abs(actual_value - expected_value) <= _CELL_COORDINATE_TOLERANCE
            for actual_point, expected_point in zip(actual.quad, expected.quad, strict=True)
            for actual_value, expected_value in zip(actual_point, expected_point, strict=True)
        )
    )


def _padded_source_quads(
    lattice_bounds_quad: Quad,
    *,
    topology: BoardCellTopology,
) -> tuple[Quad, ...]:
    canonical = np.asarray(
        (
            (0.0, 0.0),
            (float(topology.columns) * CANONICAL_CELL_SIZE, 0.0),
            (
                float(topology.columns) * CANONICAL_CELL_SIZE,
                float(topology.rows) * CANONICAL_CELL_SIZE,
            ),
            (0.0, float(topology.rows) * CANONICAL_CELL_SIZE),
        ),
        dtype=np.float32,
    )
    source = np.asarray(lattice_bounds_quad, dtype=np.float32)
    canonical_to_source = cv2.getPerspectiveTransform(canonical, source)
    quads: list[Quad] = []
    for row in range(topology.rows):
        for column in range(topology.columns):
            left = column * CANONICAL_CELL_SIZE + FIXED_PADDING_CANONICAL_PX
            top = row * CANONICAL_CELL_SIZE + FIXED_PADDING_CANONICAL_PX
            right = (column + 1) * CANONICAL_CELL_SIZE - FIXED_PADDING_CANONICAL_PX
            bottom = (row + 1) * CANONICAL_CELL_SIZE - FIXED_PADDING_CANONICAL_PX
            canonical_quad = np.asarray(
                ((left, top), (right, top), (right, bottom), (left, bottom)),
                dtype=np.float32,
            )
            projected = cast(
                NDArray[np.float32],
                cv2.perspectiveTransform(
                    canonical_quad.reshape((-1, 1, 2)), canonical_to_source
                ).reshape((-1, 2)),
            )
            quads.append(
                cast(
                    Quad,
                    tuple((float(point[0]), float(point[1])) for point in projected),
                )
            )
    return tuple(quads)


def _quad_has_full_source_support(
    quad: Quad,
    *,
    source_width: int,
    source_height: int,
) -> bool:
    points = np.asarray(quad, dtype=np.float32)
    return (
        bool(np.isfinite(points).all())
        and cv2.contourArea(points) > 4.0
        and all(0.0 <= x <= source_width - 1 and 0.0 <= y <= source_height - 1 for x, y in quad)
    )


def _project_source_quad_once(
    rgb_image: NDArray[np.uint8],
    *,
    padded_source_quad: Quad,
    output_size: int,
) -> NDArray[np.uint8]:
    source = np.asarray(padded_source_quad, dtype=np.float32)
    destination = np.asarray(
        (
            (0.0, 0.0),
            (float(output_size - 1), 0.0),
            (float(output_size - 1), float(output_size - 1)),
            (0.0, float(output_size - 1)),
        ),
        dtype=np.float32,
    )
    source_to_output = cv2.getPerspectiveTransform(source, destination)
    return cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            rgb_image,
            source_to_output,
            (output_size, output_size),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        ),
    )


def _quad_dict(quad: Quad) -> list[dict[str, float]]:
    return [{"x": round(x, 4), "y": round(y, 4)} for x, y in quad]


__all__ = [
    "BORDER_POLICY_VERSION",
    "CANONICAL_CELL_SIZE",
    "CROPPER_VERSION",
    "FIXED_PADDING_CANONICAL_PX",
    "FIXED_PADDING_FRACTION",
    "INTERPOLATION_VERSION",
    "PADDING_VERSION",
    "BoardCellGeometryCropError",
    "BoardCellGeometryCropResult",
    "BoardCellGeometrySourceCrop",
    "BoardCellGeometrySourceDirectCropper",
    "cropper_fingerprint_sha256",
]
