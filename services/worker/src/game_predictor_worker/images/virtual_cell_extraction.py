"""In-memory cell rendering directly from one canonical source decode."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    BOARD_SLOT_SEMANTICS_VERSION,
    BOARD_TOPOLOGY_FINGERPRINT_VERSION,
    SOURCE_COORDINATE_SPACE,
    SOURCE_OCCURRENCE_ID_VERSION,
    VIRTUAL_CELL_LOGICAL_ID_V2_VERSION,
    VIRTUAL_CELL_LOGICAL_ID_VERSION,
    VIRTUAL_CELL_RENDER_ID_V2_VERSION,
    VIRTUAL_CELL_RENDER_ID_VERSION,
    SourcePoint,
    SourceQuad,
    VirtualCell,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from .normalization import (
    RGB_PIXEL_CHECKSUM_VERSION,
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from .pipeline_contract import VIRTUAL_CELL_RENDERER_VERSION

VIRTUAL_CELL_RENDER_SPEC_VERSION = "virtual-cell-render-spec-v3-complete-provenance-v1"
VIRTUAL_CELL_INTERPOLATION_VERSION = "opencv-inter-linear-v1"
VIRTUAL_CELL_BORDER_POLICY_VERSION = "full-source-support-no-synthesis-v1"
MAX_VIRTUAL_CELLS_PER_BATCH = 135
_CANONICAL_CELL_SIZE = 100.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VirtualCellExtractionError(ValueError):
    """Stable failure raised before virtual pixels may be consumed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CellExtractionVariant(StrEnum):
    """Explicit diagnostic variants; only direct perspective is production."""

    NATIVE_BOUNDING_BOX = "native_bounding_box"
    DIRECT_PERSPECTIVE_CELL = "direct_perspective_cell"
    RECTIFIED_BOARD = "rectified_board"


@dataclass(frozen=True, slots=True, eq=False)
class VirtualCellRender:
    cell_index: int
    row_index: int
    column_index: int
    logical_cell_key_sha256: str
    logical_cell_key_v2_sha256: str
    render_spec: dict[str, object]
    render_spec_checksum_sha256: str
    rendered_pixel_checksum_sha256: str
    extractor_version: str
    source_quad: SourceQuad
    padded_source_quad: SourceQuad
    rgb: NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.rgb.dtype != np.uint8:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_RGB_INVALID",
                "A virtual cell render must use RGB uint8 without implicit conversion.",
            )
        contiguous = np.ascontiguousarray(self.rgb)
        if contiguous.ndim != 3 or contiguous.shape[2] != 3:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_RGB_INVALID",
                "A virtual cell render must contain RGB uint8 pixels.",
            )
        if rgb_pixel_checksum_sha256(contiguous) != self.rendered_pixel_checksum_sha256:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH",
                "Virtual cell pixels differ from their recorded checksum.",
            )
        if _sha256_json(self.render_spec) != self.render_spec_checksum_sha256:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_RENDER_SPEC_CHECKSUM_MISMATCH",
                "The virtual-cell render specification differs from its recorded checksum.",
            )
        _validate_render_spec(
            self.render_spec,
            cell_index=self.cell_index,
            row_index=self.row_index,
            column_index=self.column_index,
            logical_cell_key_sha256=self.logical_cell_key_sha256,
            logical_cell_key_v2_sha256=self.logical_cell_key_v2_sha256,
            extractor_version=self.extractor_version,
            source_quad=self.source_quad,
            padded_source_quad=self.padded_source_quad,
        )
        contiguous.setflags(write=False)
        object.__setattr__(self, "rgb", contiguous)

    @property
    def render_identity_v2_sha256(self) -> str:
        value = self.render_spec.get("renderIdentityV2Sha256")
        if not isinstance(value, str):
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_RENDER_ID_V2_INVALID",
                "A virtual cell render is missing its v2 render identity.",
            )
        return value


@dataclass(frozen=True, slots=True, eq=False)
class CellExtractionComparison:
    variant: CellExtractionVariant
    rendered_pixel_checksum_sha256: str
    rgb: NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.rgb.dtype != np.uint8:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_RGB_INVALID",
                "A comparison render must use RGB uint8 without implicit conversion.",
            )
        contiguous = np.ascontiguousarray(self.rgb)
        if rgb_pixel_checksum_sha256(contiguous) != self.rendered_pixel_checksum_sha256:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH",
                "Comparison pixels differ from their recorded checksum.",
            )
        contiguous.setflags(write=False)
        object.__setattr__(self, "rgb", contiguous)


class VirtualCellRenderer:
    """Render virtual fields without a board raster or a persistent crop file."""

    version = VIRTUAL_CELL_RENDERER_VERSION

    def render(
        self,
        frame: CanonicalSourceFrame,
        cells: tuple[VirtualCell, ...],
    ) -> tuple[VirtualCellRender, ...]:
        if len(cells) > MAX_VIRTUAL_CELLS_PER_BATCH:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_BATCH_LIMIT_EXCEEDED",
                "A virtual-cell batch cannot exceed 135 fields from one source.",
            )
        prepared = self._prepare(frame, cells)
        return tuple(
            self._render_prepared(frame, cell=cell, padded_source_quad=padded_quad)
            for cell, padded_quad in prepared
        )

    def _prepare(
        self,
        frame: CanonicalSourceFrame,
        cells: tuple[VirtualCell, ...],
    ) -> tuple[tuple[VirtualCell, SourceQuad], ...]:
        if frame.source.coordinate_space != SOURCE_COORDINATE_SPACE:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_COORDINATE_SPACE_MISMATCH",
                "Virtual cells require the canonical EXIF-normalized RGB coordinate space.",
            )
        if rgb_pixel_checksum_sha256(frame.rgb) != frame.source.normalized_pixel_checksum_sha256:
            raise VirtualCellExtractionError(
                "IMAGE_VIRTUAL_CELL_SOURCE_PIXEL_DRIFT",
                "Canonical source pixels changed after loading.",
            )
        logical_ids: set[str] = set()
        board_transforms: dict[str, NDArray[np.float64]] = {}
        prepared: list[tuple[VirtualCell, SourceQuad]] = []
        for cell in cells:
            if cell.geometry.source != frame.source:
                raise VirtualCellExtractionError(
                    "IMAGE_VIRTUAL_CELL_SOURCE_MISMATCH",
                    "A virtual cell belongs to a different canonical source.",
                )
            configuration = cell.configuration
            if configuration.extractor_version != self.version:
                raise VirtualCellExtractionError(
                    "IMAGE_VIRTUAL_CELL_EXTRACTOR_MISMATCH",
                    "The render specification pins a different virtual-cell extractor.",
                )
            if configuration.interpolation != VIRTUAL_CELL_INTERPOLATION_VERSION:
                raise VirtualCellExtractionError(
                    "IMAGE_VIRTUAL_CELL_INTERPOLATION_UNSUPPORTED",
                    "The pinned virtual-cell interpolation is not supported.",
                )
            if cell.logical_id_sha256 in logical_ids:
                raise VirtualCellExtractionError(
                    "IMAGE_VIRTUAL_CELL_DUPLICATE",
                    "A virtual-cell batch cannot contain the same logical field twice.",
                )
            logical_ids.add(cell.logical_id_sha256)
            geometry_key = cell.geometry.geometry_fingerprint_sha256
            transform = board_transforms.get(geometry_key)
            if transform is None:
                transform = _canonical_board_to_source_transform(cell)
                board_transforms[geometry_key] = transform
            padded_quad = _padded_cell_quad(cell, transform)
            _require_full_source_support(padded_quad, frame=frame)
            prepared.append((cell, padded_quad))
        return tuple(prepared)

    def _render_prepared(
        self,
        frame: CanonicalSourceFrame,
        *,
        cell: VirtualCell,
        padded_source_quad: SourceQuad,
    ) -> VirtualCellRender:
        configuration = cell.configuration
        rgb = source_direct_warp_rgb(
            frame.rgb,
            source_quad=padded_source_quad,
            output_width=configuration.output_width,
            output_height=configuration.output_height,
        )
        render_spec = _render_spec(cell, padded_source_quad=padded_source_quad)
        return VirtualCellRender(
            cell_index=cell.cell_index,
            row_index=cell.row_index,
            column_index=cell.column_index,
            logical_cell_key_sha256=cell.logical_id_sha256,
            logical_cell_key_v2_sha256=cell.logical_id_v2_sha256,
            render_spec=render_spec,
            render_spec_checksum_sha256=_sha256_json(render_spec),
            rendered_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
            extractor_version=self.version,
            source_quad=cell.source_quad,
            padded_source_quad=padded_source_quad,
            rgb=rgb,
        )


def source_direct_warp_rgb(
    rgb_image: NDArray[np.uint8],
    *,
    source_quad: SourceQuad | tuple[tuple[float, float], ...],
    output_width: int,
    output_height: int,
) -> NDArray[np.uint8]:
    """Apply exactly one source-to-output perspective warp."""

    if (
        rgb_image.ndim != 3
        or rgb_image.shape[2] != 3
        or rgb_image.dtype != np.uint8
        or output_width < 1
        or output_height < 1
    ):
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_RENDER_INPUT_INVALID",
            "Source-direct rendering requires RGB uint8 pixels and positive output dimensions.",
        )
    source = np.asarray(_quad_coordinates(source_quad), dtype=np.float32)
    if source.shape != (4, 2) or not bool(np.isfinite(source).all()):
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_QUAD_INVALID",
            "Source-direct rendering requires four finite source corners.",
        )
    destination = np.asarray(
        (
            (0.0, 0.0),
            (float(output_width - 1), 0.0),
            (float(output_width - 1), float(output_height - 1)),
            (0.0, float(output_height - 1)),
        ),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    return cast(
        NDArray[np.uint8],
        cv2.warpPerspective(
            rgb_image,
            transform,
            (output_width, output_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        ),
    )


def render_persisted_virtual_cell_rgb(
    frame: CanonicalSourceFrame,
    *,
    render_spec: Mapping[str, object],
    expected_render_spec_checksum_sha256: str,
    expected_rendered_pixel_checksum_sha256: str,
    expected_cell_index: int,
    expected_row_index: int,
    expected_column_index: int,
    expected_logical_cell_key_sha256: str,
    expected_logical_cell_key_v2_sha256: str,
    expected_extractor_version: str,
) -> NDArray[np.uint8]:
    """Recreate one persisted virtual crop after checking its frozen identity.

    This is the shared read path for consumers such as pending-only model
    reinference.  It deliberately accepts persisted provenance instead of a
    newly computed ``VirtualCell`` and therefore verifies the complete storage
    boundary before returning pixels.
    """

    spec = dict(render_spec)
    if _require_sha256(
        expected_render_spec_checksum_sha256, "render-spec checksum"
    ) != _sha256_json(spec):
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_RENDER_SPEC_CHECKSUM_MISMATCH",
            "The persisted virtual-cell render specification changed.",
        )
    _require_sha256(expected_rendered_pixel_checksum_sha256, "rendered-pixel checksum")
    if spec.get("schemaVersion") != VIRTUAL_CELL_RENDER_SPEC_VERSION:
        _render_spec_invalid("The persisted virtual cell uses an unsupported schema.")
    expected_fields: dict[str, object] = {
        "cellIndex": expected_cell_index,
        "rowIndex": expected_row_index,
        "columnIndex": expected_column_index,
        "logicalCellKeySha256": expected_logical_cell_key_sha256,
        "logicalCellKeyV1Sha256": expected_logical_cell_key_sha256,
        "logicalCellKeyV2Sha256": expected_logical_cell_key_v2_sha256,
        "coordinateSpace": SOURCE_COORDINATE_SPACE,
        "pixelChecksumVersion": RGB_PIXEL_CHECKSUM_VERSION,
        "sourceChecksumSha256": frame.source.source_checksum_sha256,
        "normalizedPixelChecksumSha256": frame.source.normalized_pixel_checksum_sha256,
    }
    if any(spec.get(field) != expected for field, expected in expected_fields.items()):
        _render_spec_invalid("Persisted virtual-cell provenance differs from its source or row.")
    configuration = _require_mapping(spec.get("configuration"), "configuration")
    if (
        configuration.get("extractorVersion") != expected_extractor_version
        or configuration.get("interpolation") != VIRTUAL_CELL_INTERPOLATION_VERSION
    ):
        _render_spec_invalid("Persisted virtual-cell renderer configuration is unsupported.")
    width = _require_integer(configuration.get("outputWidth"), "output width")
    height = _require_integer(configuration.get("outputHeight"), "output height")
    if width < 1 or height < 1:
        _render_spec_invalid("Persisted virtual-cell dimensions must be positive.")
    padded_quad = _persisted_quad(spec.get("paddedSourceQuad"))
    rgb = source_direct_warp_rgb(
        frame.rgb,
        source_quad=padded_quad,
        output_width=width,
        output_height=height,
    )
    if rgb_pixel_checksum_sha256(rgb) != expected_rendered_pixel_checksum_sha256:
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH",
            "Recreated virtual-cell pixels differ from their persisted checksum.",
        )
    return rgb


def compare_cell_extraction_variants(
    frame: CanonicalSourceFrame,
    cell: VirtualCell,
) -> tuple[CellExtractionComparison, ...]:
    """Render diagnostic A/B/C variants in memory without persisting artifacts.

    Variant B is the production contract. A and C exist only to support a
    controlled visual/pixel comparison while the rollout is evaluated.
    """

    renderer = VirtualCellRenderer()
    prepared = renderer._prepare(frame, (cell,))
    padded_quad = prepared[0][1]
    direct = renderer._render_prepared(
        frame,
        cell=cell,
        padded_source_quad=padded_quad,
    ).rgb
    variants = (
        (CellExtractionVariant.NATIVE_BOUNDING_BOX, _native_bounding_box(frame, cell, padded_quad)),
        (CellExtractionVariant.DIRECT_PERSPECTIVE_CELL, direct),
        (CellExtractionVariant.RECTIFIED_BOARD, _rectified_board_cell(frame, cell)),
    )
    return tuple(
        CellExtractionComparison(
            variant=variant,
            rendered_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
            rgb=rgb,
        )
        for variant, rgb in variants
    )


def _canonical_board_to_source_transform(cell: VirtualCell) -> NDArray[np.float64]:
    topology = cell.geometry.topology
    canonical = np.asarray(
        (
            (0.0, 0.0),
            (float(topology.columns) * _CANONICAL_CELL_SIZE, 0.0),
            (
                float(topology.columns) * _CANONICAL_CELL_SIZE,
                float(topology.rows) * _CANONICAL_CELL_SIZE,
            ),
            (0.0, float(topology.rows) * _CANONICAL_CELL_SIZE),
        ),
        dtype=np.float32,
    )
    source_points = np.asarray(_quad_coordinates(cell.geometry.symbol_grid_quad), dtype=np.float32)
    return cast(NDArray[np.float64], cv2.getPerspectiveTransform(canonical, source_points))


def _padded_cell_quad(
    cell: VirtualCell,
    canonical_to_source: NDArray[np.float64],
) -> SourceQuad:
    padding = cell.configuration.padding_fraction * _CANONICAL_CELL_SIZE
    left = cell.column_index * _CANONICAL_CELL_SIZE + padding
    top = cell.row_index * _CANONICAL_CELL_SIZE + padding
    right = (cell.column_index + 1) * _CANONICAL_CELL_SIZE - padding
    bottom = (cell.row_index + 1) * _CANONICAL_CELL_SIZE - padding
    canonical_quad = np.asarray(
        ((left, top), (right, top), (right, bottom), (left, bottom)),
        dtype=np.float32,
    )
    projected = cast(
        NDArray[np.float32],
        cv2.perspectiveTransform(canonical_quad.reshape((-1, 1, 2)), canonical_to_source).reshape(
            (-1, 2)
        ),
    )
    return SourceQuad(
        corners=cast(
            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
            tuple(SourcePoint(x=float(point[0]), y=float(point[1])) for point in projected),
        )
    )


def _require_full_source_support(quad: SourceQuad, *, frame: CanonicalSourceFrame) -> None:
    points = np.asarray(_quad_coordinates(quad), dtype=np.float32)
    if (
        not bool(np.isfinite(points).all())
        or cv2.contourArea(points) <= 4.0
        or any(
            x < 0.0 or x > frame.source.width - 1 or y < 0.0 or y > frame.source.height - 1
            for x, y in _quad_coordinates(quad)
        )
    ):
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE",
            "A padded virtual cell must be fully supported by the canonical source.",
        )


def _render_spec(cell: VirtualCell, *, padded_source_quad: SourceQuad) -> dict[str, object]:
    return {
        "boardSlot": cell.geometry.slot.position_index,
        "cellIndex": cell.cell_index,
        "columnIndex": cell.column_index,
        "configuration": cell.configuration.to_dict(),
        "coordinateSpace": cell.geometry.source.coordinate_space,
        "geometryEngineKind": cell.geometry.engine_kind.value,
        "geometryFingerprintSha256": cell.geometry.geometry_fingerprint_sha256,
        "geometryRevision": cell.geometry.geometry_revision,
        "geometryVersion": cell.geometry.geometry_version,
        "logicalCellKeySha256": cell.logical_id_sha256,
        "logicalCellKeyV1Sha256": cell.logical_id_v1_sha256,
        "logicalCellKeyV2Sha256": cell.logical_id_v2_sha256,
        "paddedSourceQuad": padded_source_quad.to_dict(),
        "pixelChecksumVersion": RGB_PIXEL_CHECKSUM_VERSION,
        "renderIdentitySha256": cell.render_id_sha256,
        "renderIdentityV1Sha256": cell.render_id_v1_sha256,
        "renderIdentityV2Sha256": cell.render_id_v2_sha256,
        "rowIndex": cell.row_index,
        "schemaVersion": VIRTUAL_CELL_RENDER_SPEC_VERSION,
        "normalizedPixelChecksumSha256": (cell.geometry.source.normalized_pixel_checksum_sha256),
        "sourceChecksumSha256": cell.geometry.source.source_checksum_sha256,
        "sourceOccurrence": cell.geometry.source_occurrence.to_dict(),
        "sourceOccurrenceIdSha256": cell.geometry.source_occurrence.identity_sha256,
        "sourceQuad": cell.source_quad.to_dict(),
        "topology": {
            "columns": cell.geometry.topology.columns,
            "contractVersion": BOARD_TOPOLOGY_FINGERPRINT_VERSION,
            "rows": cell.geometry.topology.rows,
            "slotSemanticsVersion": BOARD_SLOT_SEMANTICS_VERSION,
            "topologyRulesVersionId": str(cell.geometry.topology_rules_version_id),
        },
        "topologyFingerprintSha256": cell.geometry.topology_fingerprint_sha256,
    }


def _validate_render_spec(
    value: Mapping[str, object],
    *,
    cell_index: int,
    row_index: int,
    column_index: int,
    logical_cell_key_sha256: str,
    logical_cell_key_v2_sha256: str,
    extractor_version: str,
    source_quad: SourceQuad,
    padded_source_quad: SourceQuad,
) -> None:
    """Validate new render provenance without consulting storage or pixels."""

    if value.get("schemaVersion") != VIRTUAL_CELL_RENDER_SPEC_VERSION:
        _render_spec_invalid("A new virtual render uses an unsupported render-spec version.")
    configuration = _require_mapping(value.get("configuration"), "configuration")
    occurrence = _require_mapping(value.get("sourceOccurrence"), "sourceOccurrence")
    topology = _require_mapping(value.get("topology"), "topology")
    expected_fields: dict[str, object] = {
        "cellIndex": cell_index,
        "rowIndex": row_index,
        "columnIndex": column_index,
        "logicalCellKeySha256": logical_cell_key_sha256,
        "logicalCellKeyV1Sha256": logical_cell_key_sha256,
        "logicalCellKeyV2Sha256": logical_cell_key_v2_sha256,
        "coordinateSpace": SOURCE_COORDINATE_SPACE,
        "pixelChecksumVersion": RGB_PIXEL_CHECKSUM_VERSION,
        "sourceQuad": source_quad.to_dict(),
        "paddedSourceQuad": padded_source_quad.to_dict(),
    }
    if any(value.get(field) != expected for field, expected in expected_fields.items()):
        _render_spec_invalid("Virtual render metadata differs from its rendered cell.")
    if configuration.get("extractorVersion") != extractor_version:
        _render_spec_invalid("Virtual render configuration pins a different extractor.")

    source_checksum = _require_sha256(value.get("sourceChecksumSha256"), "source checksum")
    _require_sha256(value.get("normalizedPixelChecksumSha256"), "normalized-pixel checksum")
    geometry_fingerprint = _require_sha256(
        value.get("geometryFingerprintSha256"), "geometry fingerprint"
    )
    occurrence_id = _require_sha256(
        value.get("sourceOccurrenceIdSha256"), "source occurrence identity"
    )
    topology_fingerprint = _require_sha256(
        value.get("topologyFingerprintSha256"), "topology fingerprint"
    )
    if occurrence.get("contractVersion") != SOURCE_OCCURRENCE_ID_VERSION:
        _render_spec_invalid("Virtual render source occurrence uses an unsupported contract.")
    if _sha256_json(occurrence) != occurrence_id:
        _render_spec_invalid("Virtual render source occurrence differs from its identity.")
    if topology.get("contractVersion") != BOARD_TOPOLOGY_FINGERPRINT_VERSION:
        _render_spec_invalid("Virtual render topology uses an unsupported contract.")
    if topology.get("slotSemanticsVersion") != BOARD_SLOT_SEMANTICS_VERSION:
        _render_spec_invalid("Virtual render topology uses unsupported slot semantics.")
    if _sha256_json(topology) != topology_fingerprint:
        _render_spec_invalid("Virtual render topology differs from its fingerprint.")

    board_slot = _require_integer(value.get("boardSlot"), "board slot")
    expected_logical_v1 = _sha256_json(
        {
            "boardSlot": board_slot,
            "cellIndex": cell_index,
            "columnIndex": column_index,
            "contractVersion": VIRTUAL_CELL_LOGICAL_ID_VERSION,
            "rowIndex": row_index,
            "sourceChecksumSha256": source_checksum,
        }
    )
    expected_logical_v2 = _sha256_json(
        {
            "boardSlot": board_slot,
            "cellIndex": cell_index,
            "columnIndex": column_index,
            "contractVersion": VIRTUAL_CELL_LOGICAL_ID_V2_VERSION,
            "rowIndex": row_index,
            "sourceOccurrenceIdSha256": occurrence_id,
            "topologyFingerprintSha256": topology_fingerprint,
        }
    )
    if expected_logical_v1 != logical_cell_key_sha256:
        _render_spec_invalid("Virtual render logical-cell-v1 identity is inconsistent.")
    if expected_logical_v2 != logical_cell_key_v2_sha256:
        _render_spec_invalid("Virtual render logical-cell-v2 identity is inconsistent.")

    render_v1 = _sha256_json(
        {
            "configuration": dict(configuration),
            "contractVersion": VIRTUAL_CELL_RENDER_ID_VERSION,
            "geometryFingerprintSha256": geometry_fingerprint,
            "logicalCellIdSha256": logical_cell_key_sha256,
            "sourceQuad": source_quad.to_dict(),
        }
    )
    render_v2 = _sha256_json(
        {
            "configuration": dict(configuration),
            "contractVersion": VIRTUAL_CELL_RENDER_ID_V2_VERSION,
            "geometryFingerprintSha256": geometry_fingerprint,
            "logicalCellIdV2Sha256": logical_cell_key_v2_sha256,
            "sourceQuad": source_quad.to_dict(),
        }
    )
    if (
        value.get("renderIdentitySha256") != render_v1
        or value.get("renderIdentityV1Sha256") != render_v1
    ):
        _render_spec_invalid("Virtual render render-identity-v1 is inconsistent.")
    if value.get("renderIdentityV2Sha256") != render_v2:
        _render_spec_invalid("Virtual render render-identity-v2 is inconsistent.")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        _render_spec_invalid(f"Virtual render {label} must be an object.")
    return cast(Mapping[str, object], value)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _render_spec_invalid(f"Virtual render {label} must be a SHA-256 digest.")
    return cast(str, value)


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _render_spec_invalid(f"Virtual render {label} must be a non-negative integer.")
    return cast(int, value)


def _render_spec_invalid(message: str) -> None:
    raise VirtualCellExtractionError("IMAGE_VIRTUAL_CELL_RENDER_SPEC_INVALID", message)


def _native_bounding_box(
    frame: CanonicalSourceFrame,
    cell: VirtualCell,
    padded_quad: SourceQuad,
) -> NDArray[np.uint8]:
    coordinates = _quad_coordinates(padded_quad)
    left = max(0, math.floor(min(point[0] for point in coordinates)))
    top = max(0, math.floor(min(point[1] for point in coordinates)))
    right = min(frame.source.width, math.ceil(max(point[0] for point in coordinates)) + 1)
    bottom = min(frame.source.height, math.ceil(max(point[1] for point in coordinates)) + 1)
    if right <= left or bottom <= top:
        raise VirtualCellExtractionError(
            "IMAGE_VIRTUAL_CELL_BOUNDING_BOX_INVALID",
            "The diagnostic native bounding box is empty.",
        )
    crop = frame.rgb[top:bottom, left:right]
    return cast(
        NDArray[np.uint8],
        cv2.resize(
            crop,
            (cell.configuration.output_width, cell.configuration.output_height),
            interpolation=cv2.INTER_LINEAR,
        ),
    )


def _rectified_board_cell(
    frame: CanonicalSourceFrame,
    cell: VirtualCell,
) -> NDArray[np.uint8]:
    topology = cell.geometry.topology
    board_width = topology.columns * int(_CANONICAL_CELL_SIZE)
    board_height = topology.rows * int(_CANONICAL_CELL_SIZE)
    board = source_direct_warp_rgb(
        frame.rgb,
        source_quad=cell.geometry.symbol_grid_quad,
        output_width=board_width,
        output_height=board_height,
    )
    padding = int(round(cell.configuration.padding_fraction * _CANONICAL_CELL_SIZE))
    left = cell.column_index * int(_CANONICAL_CELL_SIZE) + padding
    top = cell.row_index * int(_CANONICAL_CELL_SIZE) + padding
    right = (cell.column_index + 1) * int(_CANONICAL_CELL_SIZE) - padding
    bottom = (cell.row_index + 1) * int(_CANONICAL_CELL_SIZE) - padding
    crop = board[top:bottom, left:right]
    return cast(
        NDArray[np.uint8],
        cv2.resize(
            crop,
            (cell.configuration.output_width, cell.configuration.output_height),
            interpolation=cv2.INTER_LINEAR,
        ),
    )


def _quad_coordinates(
    quad: SourceQuad | tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if isinstance(quad, SourceQuad):
        return tuple((point.x, point.y) for point in quad.corners)
    return tuple((float(point[0]), float(point[1])) for point in quad)


def _persisted_quad(value: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list | tuple) or len(value) != 4:
        _render_spec_invalid("A persisted virtual-cell quad must contain four corners.")
    points: list[tuple[float, float]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            _render_spec_invalid("A persisted virtual-cell corner must be an object.")
        x = raw.get("x")
        y = raw.get("y")
        if (
            isinstance(x, bool)
            or not isinstance(x, int | float)
            or isinstance(y, bool)
            or not isinstance(y, int | float)
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
        ):
            _render_spec_invalid("A persisted virtual-cell corner must be finite.")
        points.append((float(x), float(y)))
    return tuple(points)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "MAX_VIRTUAL_CELLS_PER_BATCH",
    "VIRTUAL_CELL_BORDER_POLICY_VERSION",
    "VIRTUAL_CELL_INTERPOLATION_VERSION",
    "VIRTUAL_CELL_RENDERER_VERSION",
    "VIRTUAL_CELL_RENDER_SPEC_VERSION",
    "CellExtractionComparison",
    "CellExtractionVariant",
    "VirtualCellExtractionError",
    "VirtualCellRender",
    "VirtualCellRenderer",
    "compare_cell_extraction_variants",
    "render_persisted_virtual_cell_rgb",
    "source_direct_warp_rgb",
]
