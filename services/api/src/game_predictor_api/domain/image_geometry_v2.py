"""Pure v0.10 contracts for attested page slots and virtual cell geometry.

The contracts in this module deliberately describe *where* a cell is on the
EXIF-normalized source image, without deciding how geometry is found, how
pixels are rendered, or where anything is persisted.  That separation lets
the later structured-CV and manual engines share the same deterministic
identity model while the legacy crop files remain readable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from game_predictor_api.domain.board_topology import BoardTopology

MAX_PAGE_BOARD_SLOTS = 9
PAGE_BOARD_COLUMNS = 3
SOURCE_COORDINATE_SPACE = "exif-normalized-rgb-pixels-v1"
VIRTUAL_CELL_LOGICAL_ID_VERSION = "virtual-cell-logical-id-v1"
VIRTUAL_CELL_LOGICAL_ID_V2_VERSION = "virtual-cell-logical-id-v2"
VIRTUAL_CELL_RENDER_ID_VERSION = "virtual-cell-render-id-v1"
VIRTUAL_CELL_RENDER_ID_V2_VERSION = "virtual-cell-render-id-v2"
SOURCE_OCCURRENCE_ID_VERSION = "source-occurrence-id-v1"
BOARD_TOPOLOGY_FINGERPRINT_VERSION = "board-topology-fingerprint-v1"
BOARD_SLOT_SEMANTICS_VERSION = "attested-sequence-row-major-page-3x3-v1"
SEQUENCE_ATTESTATION_SCHEMA_VERSION = "source-sequence-attestation-v2"
_SEQUENCE_RANGE_FILENAME = re.compile(
    r"^seq_(?P<start>[1-9][0-9]*)-(?P<end>[1-9][0-9]*)\.(?:jpg|jpeg)$",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ImageGeometryContractError(ValueError):
    """Stable validation error for the future virtual-geometry boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json_bytes(value: object) -> bytes:
    """Encode finite JSON deterministically for virtual-cell identities."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ImageGeometryContractError(
            "IMAGE_GEOMETRY_CONTRACT_INVALID",
            "A virtual geometry contract must contain finite JSON values.",
        ) from error


def is_sequence_range_filename_candidate(value: str) -> bool:
    """Return whether a logical filename claims the ``seq_*`` convention."""

    return PurePosixPath(value.replace("\\", "/")).name.casefold().startswith("seq_")


def board_topology_fingerprint_sha256(
    *,
    topology_rules_version_id: UUID,
    topology: BoardTopology,
) -> str:
    """Fingerprint the pinned rules topology and row-major slot semantics."""

    payload = {
        "columns": topology.columns,
        "contractVersion": BOARD_TOPOLOGY_FINGERPRINT_VERSION,
        "rows": topology.rows,
        "slotSemanticsVersion": BOARD_SLOT_SEMANTICS_VERSION,
        "topologyRulesVersionId": str(topology_rules_version_id),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sequence_attestation_checksum_sha256(
    *,
    sequence_range_start: int,
    sequence_range_end: int,
    active_board_slots: tuple[int, ...],
) -> str:
    """Bind an explicit active-slot snapshot without changing legacy parsing."""

    attested = AttestedSequenceRange(start=sequence_range_start, end=sequence_range_end)
    expected_slots = tuple(slot.position_index for slot in attested.active_slots)
    if active_board_slots != expected_slots:
        raise ImageGeometryContractError(
            "IMAGE_SEQUENCE_ATTESTATION_SLOTS_INVALID",
            "The source sequence attestation does not match its active row-major slots.",
        )
    payload = {
        "activeBoardSlots": list(active_board_slots),
        "contractVersion": SEQUENCE_ATTESTATION_SCHEMA_VERSION,
        "sequenceRangeEnd": sequence_range_end,
        "sequenceRangeStart": sequence_range_start,
        "slotSemanticsVersion": BOARD_SLOT_SEMANTICS_VERSION,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class ActiveBoardSlot:
    """One active, row-major page slot attested by a contiguous ``seq_*`` range."""

    range_start: int
    range_end: int
    position_index: int
    sequence_number: int

    def __post_init__(self) -> None:
        range_value = AttestedSequenceRange(start=self.range_start, end=self.range_end)
        if not 0 <= self.position_index < range_value.board_count:
            raise ImageGeometryContractError(
                "IMAGE_SEQUENCE_SLOT_INVALID",
                "An active board slot must belong to its attested sequence range.",
            )
        if self.sequence_number != range_value.start + self.position_index:
            raise ImageGeometryContractError(
                "IMAGE_SEQUENCE_SLOT_INVALID",
                "An active board slot must use the attested row-major sequence number.",
            )

    @property
    def row_index(self) -> int:
        return self.position_index // PAGE_BOARD_COLUMNS

    @property
    def column_index(self) -> int:
        return self.position_index % PAGE_BOARD_COLUMNS


@dataclass(frozen=True, slots=True)
class AttestedSequenceRange:
    """A source-declared, inclusive sequence range with one to nine boards.

    The range always maps to the row-major *prefix* of the 3 by 3 page.  A
    partial final page therefore has active positions ``0..N-1`` only; it can
    never create a hole in the middle of a page.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.start, bool)
            or isinstance(self.end, bool)
            or not isinstance(self.start, int)
            or not isinstance(self.end, int)
            or self.start < 1
            or self.end < self.start
            or self.end - self.start + 1 > MAX_PAGE_BOARD_SLOTS
        ):
            raise ImageGeometryContractError(
                "IMAGE_SEQUENCE_RANGE_INVALID",
                "A seq_* range must declare one to nine consecutive positive sequence numbers.",
            )

    @property
    def board_count(self) -> int:
        return self.end - self.start + 1

    @property
    def active_slots(self) -> tuple[ActiveBoardSlot, ...]:
        return tuple(
            ActiveBoardSlot(
                range_start=self.start,
                range_end=self.end,
                position_index=position_index,
                sequence_number=self.start + position_index,
            )
            for position_index in range(self.board_count)
        )

    def to_dict(self) -> dict[str, int]:
        return {"sequenceRangeEnd": self.end, "sequenceRangeStart": self.start}


def parse_attested_sequence_range_filename(value: str) -> AttestedSequenceRange:
    """Parse one logical ``seq_<start>-<end>.jpg|jpeg`` filename.

    Only the basename has naming semantics.  Callers remain responsible for
    validating a relative path before using it as a filesystem location.
    """

    filename = PurePosixPath(value.replace("\\", "/")).name
    match = _SEQUENCE_RANGE_FILENAME.fullmatch(filename)
    if match is None:
        raise ImageGeometryContractError(
            "IMAGE_SEQUENCE_FILENAME_INVALID",
            "A seq_* filename must use seq_<start>-<end>.jpg or .jpeg.",
        )
    return AttestedSequenceRange(start=int(match.group("start")), end=int(match.group("end")))


class GeometryEngineKind(StrEnum):
    """Declared geometry source; feature activation remains a later concern."""

    LEGACY_V20 = "legacy_v20"
    STRUCTURED_OPENCV_V1 = "structured_opencv_v1"
    MANUAL_V1 = "manual_v1"
    KEYPOINT_FALLBACK_V1 = "keypoint_fallback_v1"


@dataclass(frozen=True, slots=True)
class NormalizedSourceImage:
    """The only coordinate system accepted by virtual geometry.

    Coordinates refer to RGB pixels after exactly one EXIF orientation
    application.  The raw JPEG remains immutable; this object has no path and
    does not imply that a normalized bitmap is persisted.
    """

    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    width: int
    height: int
    exif_orientation: int | None
    normalization_adapter_version: str
    coordinate_space: str = SOURCE_COORDINATE_SPACE

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.source_checksum_sha256) or not _SHA256.fullmatch(
            self.normalized_pixel_checksum_sha256
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_SOURCE_CHECKSUM_INVALID",
                "Virtual geometry requires source and normalized-pixel SHA-256 checksums.",
            )
        if (
            isinstance(self.width, bool)
            or isinstance(self.height, bool)
            or not isinstance(self.width, int)
            or not isinstance(self.height, int)
            or self.width < 1
            or self.height < 1
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_SOURCE_DIMENSIONS_INVALID",
                "Virtual geometry source dimensions must be positive integers.",
            )
        if self.exif_orientation is not None and (
            isinstance(self.exif_orientation, bool)
            or not isinstance(self.exif_orientation, int)
            or self.exif_orientation not in range(1, 9)
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_EXIF_ORIENTATION_INVALID",
                "EXIF orientation must be omitted or an integer from 1 through 8.",
            )
        if (
            self.coordinate_space != SOURCE_COORDINATE_SPACE
            or not self.normalization_adapter_version.strip()
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_SOURCE_COORDINATE_SPACE_INVALID",
                "Virtual geometry requires the canonical EXIF-normalized RGB coordinate space.",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "coordinateSpace": self.coordinate_space,
            "exifOrientation": self.exif_orientation,
            "height": self.height,
            "normalizationAdapterVersion": self.normalization_adapter_version,
            "normalizedPixelChecksumSha256": self.normalized_pixel_checksum_sha256,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class SourceOccurrence:
    """One immutable appearance of a source file inside an import job.

    Binary equality is deliberately not occurrence equality.  Reusing the
    same JPEG in another import creates a different occurrence while retries
    of the same ``job + fileExecutionKey`` retain the same identity.
    """

    import_job_id: UUID
    file_execution_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.import_job_id, UUID) or not _SHA256.fullmatch(
            self.file_execution_key
        ):
            raise ImageGeometryContractError(
                "IMAGE_SOURCE_OCCURRENCE_INVALID",
                "A source occurrence requires an import UUID and file-execution SHA-256.",
            )

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, str]:
        return {
            "contractVersion": SOURCE_OCCURRENCE_ID_VERSION,
            "fileExecutionKey": self.file_execution_key,
            "importJobId": str(self.import_job_id),
        }


@dataclass(frozen=True, slots=True)
class SourcePoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.x, bool)
            or isinstance(self.y, bool)
            or not isinstance(self.x, int | float)
            or not isinstance(self.y, int | float)
            or not math.isfinite(self.x)
            or not math.isfinite(self.y)
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_POINT_INVALID",
                "Geometry points must use finite source-image coordinates.",
            )

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True, slots=True)
class SourceQuad:
    """Four ordered source points: top-left, top-right, bottom-right, bottom-left.

    The contract requires a convex quadrilateral, but deliberately does not
    require a rectangle, a rhombus, parallel sides, or right angles in image
    coordinates.
    """

    corners: tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint]

    def __post_init__(self) -> None:
        if len(self.corners) != 4 or not all(
            isinstance(point, SourcePoint) for point in self.corners
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_QUAD_INVALID",
                "A source quadrilateral must contain exactly four ordered corners.",
            )
        cross_products = tuple(
            _cross(
                self.corners[index],
                self.corners[(index + 1) % 4],
                self.corners[(index + 2) % 4],
            )
            for index in range(4)
        )
        if any(abs(value) <= 1e-8 for value in cross_products) or not (
            all(value > 0 for value in cross_products) or all(value < 0 for value in cross_products)
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_QUAD_INVALID",
                "A source quadrilateral must be convex and non-self-intersecting.",
            )

    def require_within(self, source: NormalizedSourceImage) -> None:
        if any(
            point.x < 0 or point.x > source.width or point.y < 0 or point.y > source.height
            for point in self.corners
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_QUAD_OUT_OF_BOUNDS",
                "A source quadrilateral must lie inside the EXIF-normalized source image.",
            )

    def cell_quad(
        self,
        *,
        topology: BoardTopology,
        row_index: int,
        column_index: int,
    ) -> SourceQuad:
        if not 0 <= row_index < topology.rows or not 0 <= column_index < topology.columns:
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_CELL_COORDINATES_INVALID",
                "Virtual cell coordinates must belong to the board topology.",
            )
        u0 = column_index / topology.columns
        u1 = (column_index + 1) / topology.columns
        v0 = row_index / topology.rows
        v1 = (row_index + 1) / topology.rows
        return SourceQuad(
            corners=(
                _project_unit_square_to_quad(self.corners, u0, v0),
                _project_unit_square_to_quad(self.corners, u1, v0),
                _project_unit_square_to_quad(self.corners, u1, v1),
                _project_unit_square_to_quad(self.corners, u0, v1),
            )
        )

    def to_dict(self) -> list[dict[str, float]]:
        return [point.to_dict() for point in self.corners]


@dataclass(frozen=True, slots=True)
class VirtualBoardGeometry:
    """One current source-space grid quad for an active, attested board slot."""

    source: NormalizedSourceImage
    source_occurrence: SourceOccurrence
    slot: ActiveBoardSlot
    topology: BoardTopology
    topology_rules_version_id: UUID
    geometry_revision: int
    geometry_version: str
    engine_kind: GeometryEngineKind
    symbol_grid_quad: SourceQuad

    def __post_init__(self) -> None:
        if (
            isinstance(self.geometry_revision, bool)
            or not isinstance(self.geometry_revision, int)
            or self.geometry_revision < 0
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_REVISION_INVALID",
                "A geometry revision cannot be negative.",
            )
        if not isinstance(self.geometry_version, str) or not self.geometry_version.strip():
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_VERSION_INVALID",
                "A virtual board geometry requires a versioned geometry engine contract.",
            )
        self.symbol_grid_quad.require_within(self.source)

    @property
    def topology_fingerprint_sha256(self) -> str:
        return board_topology_fingerprint_sha256(
            topology_rules_version_id=self.topology_rules_version_id,
            topology=self.topology,
        )

    @property
    def geometry_fingerprint_sha256(self) -> str:
        payload = {
            "engineKind": self.engine_kind.value,
            "geometryRevision": self.geometry_revision,
            "geometryVersion": self.geometry_version,
            "slot": _slot_payload(self.slot),
            "source": self.source.to_dict(),
            "symbolGridQuad": self.symbol_grid_quad.to_dict(),
            "topology": {
                "columns": self.topology.columns,
                "rows": self.topology.rows,
                "rulesVersionId": str(self.topology_rules_version_id),
            },
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class DirectCellRenderConfiguration:
    """Pinned direct-render choices, without allocating a crop or a board raster."""

    extractor_version: str
    preprocessing_version: str
    interpolation: str
    output_width: int
    output_height: int
    padding_fraction: float

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.extractor_version, self.preprocessing_version, self.interpolation)
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_RENDER_CONFIGURATION_INVALID",
                "Virtual cell rendering requires versioned extractor, preprocessing "
                "and interpolation.",
            )
        if (
            isinstance(self.output_width, bool)
            or isinstance(self.output_height, bool)
            or not isinstance(self.output_width, int)
            or not isinstance(self.output_height, int)
            or isinstance(self.padding_fraction, bool)
            or not isinstance(self.padding_fraction, int | float)
            or self.output_width < 1
            or self.output_height < 1
            or not math.isfinite(self.padding_fraction)
            or not 0 <= self.padding_fraction < 0.5
        ):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_RENDER_CONFIGURATION_INVALID",
                "Virtual cell output dimensions and padding are invalid.",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "extractorVersion": self.extractor_version,
            "interpolation": self.interpolation,
            "outputHeight": self.output_height,
            "outputWidth": self.output_width,
            "paddingFraction": self.padding_fraction,
            "preprocessingVersion": self.preprocessing_version,
        }


@dataclass(frozen=True, slots=True)
class VirtualCell:
    """A stable logical cell plus the exact source-space render specification."""

    geometry: VirtualBoardGeometry
    configuration: DirectCellRenderConfiguration
    cell_index: int
    row_index: int
    column_index: int
    source_quad: SourceQuad

    def __post_init__(self) -> None:
        self.geometry.topology.validate_coordinates(
            cell_index=self.cell_index,
            row_index=self.row_index,
            column_index=self.column_index,
        )
        self.source_quad.require_within(self.geometry.source)
        expected = self.geometry.symbol_grid_quad.cell_quad(
            topology=self.geometry.topology,
            row_index=self.row_index,
            column_index=self.column_index,
        )
        if not _quads_close(self.source_quad, expected):
            raise ImageGeometryContractError(
                "IMAGE_GEOMETRY_CELL_DERIVATION_INVALID",
                "A virtual cell quad must be derived from its current symbol-grid geometry.",
            )

    @property
    def logical_id_sha256(self) -> str:
        """Historical content-based logical-cell-v1 identity."""

        payload = {
            "boardSlot": self.geometry.slot.position_index,
            "cellIndex": self.cell_index,
            "columnIndex": self.column_index,
            "contractVersion": VIRTUAL_CELL_LOGICAL_ID_VERSION,
            "rowIndex": self.row_index,
            "sourceChecksumSha256": self.geometry.source.source_checksum_sha256,
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @property
    def logical_id_v1_sha256(self) -> str:
        return self.logical_id_sha256

    @property
    def logical_id_v2_sha256(self) -> str:
        payload = {
            "boardSlot": self.geometry.slot.position_index,
            "cellIndex": self.cell_index,
            "columnIndex": self.column_index,
            "contractVersion": VIRTUAL_CELL_LOGICAL_ID_V2_VERSION,
            "rowIndex": self.row_index,
            "sourceOccurrenceIdSha256": self.geometry.source_occurrence.identity_sha256,
            "topologyFingerprintSha256": self.geometry.topology_fingerprint_sha256,
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @property
    def render_id_sha256(self) -> str:
        """Historical render-id-v1 retained for replay compatibility."""

        payload = {
            "configuration": self.configuration.to_dict(),
            "contractVersion": VIRTUAL_CELL_RENDER_ID_VERSION,
            "geometryFingerprintSha256": self.geometry.geometry_fingerprint_sha256,
            "logicalCellIdSha256": self.logical_id_sha256,
            "sourceQuad": self.source_quad.to_dict(),
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @property
    def render_id_v1_sha256(self) -> str:
        return self.render_id_sha256

    @property
    def render_id_v2_sha256(self) -> str:
        payload = {
            "configuration": self.configuration.to_dict(),
            "contractVersion": VIRTUAL_CELL_RENDER_ID_V2_VERSION,
            "geometryFingerprintSha256": self.geometry.geometry_fingerprint_sha256,
            "logicalCellIdV2Sha256": self.logical_id_v2_sha256,
            "sourceQuad": self.source_quad.to_dict(),
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def derive_virtual_cells(
    *,
    geometry: VirtualBoardGeometry,
    configuration: DirectCellRenderConfiguration,
) -> tuple[VirtualCell, ...]:
    """Derive exactly ``rows × columns`` virtual cells in deterministic row-major order."""

    cells: list[VirtualCell] = []
    for cell_index in range(geometry.topology.cell_count):
        row_index, column_index = geometry.topology.coordinates(cell_index)
        cells.append(
            VirtualCell(
                geometry=geometry,
                configuration=configuration,
                cell_index=cell_index,
                row_index=row_index,
                column_index=column_index,
                source_quad=geometry.symbol_grid_quad.cell_quad(
                    topology=geometry.topology,
                    row_index=row_index,
                    column_index=column_index,
                ),
            )
        )
    return tuple(cells)


def _slot_payload(slot: ActiveBoardSlot) -> dict[str, int]:
    return {
        "positionIndex": slot.position_index,
        "sequenceNumber": slot.sequence_number,
        "sequenceRangeEnd": slot.range_end,
        "sequenceRangeStart": slot.range_start,
    }


def _cross(first: SourcePoint, second: SourcePoint, third: SourcePoint) -> float:
    return (second.x - first.x) * (third.y - second.y) - (second.y - first.y) * (third.x - first.x)


def _project_unit_square_to_quad(
    quad: tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
    u: float,
    v: float,
) -> SourcePoint:
    """Apply the unique square-to-quad projective mapping without OpenCV.

    The affine branch handles parallelograms; the general branch preserves
    projective grid lines for photographed screens.
    """

    top_left, top_right, bottom_right, bottom_left = quad
    dx1 = top_right.x - bottom_right.x
    dx2 = bottom_left.x - bottom_right.x
    dx3 = top_left.x - top_right.x + bottom_right.x - bottom_left.x
    dy1 = top_right.y - bottom_right.y
    dy2 = bottom_left.y - bottom_right.y
    dy3 = top_left.y - top_right.y + bottom_right.y - bottom_left.y
    denominator = dx1 * dy2 - dx2 * dy1
    if abs(denominator) <= 1e-12:
        g = 0.0
        h = 0.0
    else:
        g = (dx3 * dy2 - dx2 * dy3) / denominator
        h = (dx1 * dy3 - dx3 * dy1) / denominator
    a = top_right.x - top_left.x + g * top_right.x
    b = bottom_left.x - top_left.x + h * bottom_left.x
    c = top_left.x
    d = top_right.y - top_left.y + g * top_right.y
    e = bottom_left.y - top_left.y + h * bottom_left.y
    f = top_left.y
    scale = g * u + h * v + 1.0
    if abs(scale) <= 1e-12:
        raise ImageGeometryContractError(
            "IMAGE_GEOMETRY_PROJECTIVE_MAPPING_INVALID",
            "A source quadrilateral cannot be mapped from the canonical grid.",
        )
    return SourcePoint(x=(a * u + b * v + c) / scale, y=(d * u + e * v + f) / scale)


def _quads_close(first: SourceQuad, second: SourceQuad) -> bool:
    return all(
        math.isclose(left.x, right.x, abs_tol=1e-6) and math.isclose(left.y, right.y, abs_tol=1e-6)
        for left, right in zip(first.corners, second.corners, strict=True)
    )


__all__ = [
    "BOARD_SLOT_SEMANTICS_VERSION",
    "BOARD_TOPOLOGY_FINGERPRINT_VERSION",
    "MAX_PAGE_BOARD_SLOTS",
    "PAGE_BOARD_COLUMNS",
    "SOURCE_COORDINATE_SPACE",
    "SOURCE_OCCURRENCE_ID_VERSION",
    "SEQUENCE_ATTESTATION_SCHEMA_VERSION",
    "ActiveBoardSlot",
    "AttestedSequenceRange",
    "DirectCellRenderConfiguration",
    "GeometryEngineKind",
    "ImageGeometryContractError",
    "NormalizedSourceImage",
    "SourcePoint",
    "SourceQuad",
    "SourceOccurrence",
    "VirtualBoardGeometry",
    "VirtualCell",
    "VIRTUAL_CELL_LOGICAL_ID_V2_VERSION",
    "VIRTUAL_CELL_LOGICAL_ID_VERSION",
    "VIRTUAL_CELL_RENDER_ID_V2_VERSION",
    "VIRTUAL_CELL_RENDER_ID_VERSION",
    "canonical_json_bytes",
    "board_topology_fingerprint_sha256",
    "derive_virtual_cells",
    "is_sequence_range_filename_candidate",
    "parse_attested_sequence_range_filename",
    "sequence_attestation_checksum_sha256",
]
