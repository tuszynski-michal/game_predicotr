"""Validated preview and immutable persistence for manual v19 cell geometry."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.filesystem import long_path_aware

from .board_cell_geometry_contract import (
    BOARD_CELL_COORDINATE_SPACE,
    BOARD_CELL_CORNER_SEMANTICS,
    BOARD_CELL_GEOMETRY_VERSION,
    LEGACY_BOARD_CELL_TOPOLOGY,
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    BoardCellTopology,
    Quad,
    canonical_json_bytes,
    derive_board_cell_quads,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceCrop,
    BoardCellGeometrySourceDirectCropper,
)

MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION = "manual-board-cell-geometry-v19-preview-v1"
MANUAL_BOARD_CELL_GEOMETRY_VERSION = "manual-board-cell-geometry-v19-append-only-v1"
MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE = 64
_SHA256_CHARS = frozenset("0123456789abcdef")


class ManualBoardCellGeometryPreviewError(ValueError):
    """Stable failure raised before a v19 preview can be returned."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryCellPreview:
    row_index: int
    column_index: int
    source_quad: Quad
    padded_source_quad: Quad
    png: bytes
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryPreview:
    review_item_id: str
    source_order_index: int
    source_image_id: str
    source_image_checksum_sha256: str
    source_image_relative_path: str
    source_group: str
    sequence_number: int
    position_index: int
    lattice_bounds_quad: Quad
    image_width: int
    image_height: int
    corrected_by: str
    expected_geometry_revision: int
    expected_resolution_revision: int
    command_checksum_sha256: str
    decision_checksum_sha256: str
    manual_geometry_version: str
    contact_sheet_png: bytes
    contact_sheet_checksum_sha256: str
    cell_output_size: int
    cropper_version: str
    cropper_fingerprint_sha256: str
    cells: tuple[ManualBoardCellGeometryCellPreview, ...]
    topology: BoardCellTopology = LEGACY_BOARD_CELL_TOPOLOGY


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryCellArtifact:
    row_index: int
    column_index: int
    source_quad: Quad
    padded_source_quad: Quad
    relative_path: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ManualBoardCellGeometryArtifacts:
    review_item_id: str
    source_order_index: int
    source_image_id: str
    source_image_checksum_sha256: str
    source_image_relative_path: str
    source_group: str
    sequence_number: int
    position_index: int
    lattice_bounds_quad: Quad
    image_width: int
    image_height: int
    corrected_by: str
    expected_geometry_revision: int
    expected_resolution_revision: int
    command_checksum_sha256: str
    decision_checksum_sha256: str
    manual_geometry_version: str
    cell_output_size: int
    cropper_version: str
    cropper_fingerprint_sha256: str
    cells: tuple[ManualBoardCellGeometryCellArtifact, ...]
    topology: BoardCellTopology = LEGACY_BOARD_CELL_TOPOLOGY


class ManualBoardCellGeometryPreviewer:
    """Validate one manual lattice and render all topology-defined crops."""

    version = MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION

    def __init__(
        self,
        *,
        cell_output_size: int = MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
        topology: BoardCellTopology = LEGACY_BOARD_CELL_TOPOLOGY,
    ) -> None:
        self._topology = topology
        self._cropper = BoardCellGeometrySourceDirectCropper(
            cell_output_size=cell_output_size,
            topology=topology if topology != LEGACY_BOARD_CELL_TOPOLOGY else None,
        )

    def preview(
        self,
        *,
        source_path: Path,
        expected_source_sha256: str,
        review_item_id: str,
        source_order_index: int,
        source_image_id: str,
        source_image_relative_path: str,
        source_group: str,
        sequence_number: int,
        position_index: int,
        lattice_bounds_quad: Quad,
        corrected_by: str,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        command_checksum_sha256: str,
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
        decision_checksum_sha256 = manual_board_cell_geometry_decision_checksum(
            review_item_id=review_item_id,
            source_order_index=source_order_index,
            source_image_id=source_image_id,
            source_image_checksum_sha256=expected_source_sha256,
            source_image_relative_path=source_image_relative_path,
            source_group=source_group,
            sequence_number=sequence_number,
            position_index=position_index,
            lattice_bounds_quad=lattice_bounds_quad,
            corrected_by=corrected_by,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            command_checksum_sha256=command_checksum_sha256,
            cropper_fingerprint_sha256=self._cropper.fingerprint_sha256,
            topology=self._topology,
        )
        try:
            cells = derive_board_cell_quads(
                lattice_bounds_quad,
                source_image_width=image_width,
                source_image_height=image_height,
                topology=self._topology,
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
            condition_tags=("manual-override",),
            sequence_number=sequence_number,
            position_index=position_index,
            lattice_bounds_quad=lattice_bounds_quad,
            cells=cells,
            evidence=BoardCellGeometryEvidence(
                kind="manual_override",
                estimator_version=MANUAL_BOARD_CELL_GEOMETRY_VERSION,
                thresholds_version=MANUAL_BOARD_CELL_GEOMETRY_VERSION,
                locator_version=None,
                homography_version=None,
                candidate_center_count=0,
                reliable_center_count=0,
                inlier_count=0,
                inlier_slots=(),
                inlier_p95_residual_px=None,
                decision_checksum_sha256=decision_checksum_sha256,
            ),
            topology=self._topology,
        )
        result = self._cropper.crop(rgb, geometry)
        if result.status != "cropped" or len(result.cells) != self._topology.cell_count:
            reason = result.review_reasons[0] if result.review_reasons else "unknown"
            raise ManualBoardCellGeometryPreviewError(
                reason,
                f"The board-cell geometry preview cannot be cropped: {reason}.",
            )
        previews = tuple(
            ManualBoardCellGeometryCellPreview(
                row_index=cell.row_index,
                column_index=cell.column_index,
                source_quad=cell.source_quad,
                padded_source_quad=cell.padded_source_quad,
                png=(png := _encode_png(cell.rgb)),
                checksum_sha256=hashlib.sha256(png).hexdigest(),
            )
            for cell in result.cells
        )
        contact_sheet = _contact_sheet(result.cells, topology=self._topology)
        contact_sheet_png = _encode_png(contact_sheet)
        return ManualBoardCellGeometryPreview(
            review_item_id=review_item_id,
            source_order_index=source_order_index,
            source_image_id=source_image_id,
            source_image_checksum_sha256=expected_source_sha256,
            source_image_relative_path=source_image_relative_path,
            source_group=source_group,
            sequence_number=sequence_number,
            position_index=position_index,
            lattice_bounds_quad=lattice_bounds_quad,
            image_width=image_width,
            image_height=image_height,
            corrected_by=corrected_by,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            command_checksum_sha256=command_checksum_sha256,
            decision_checksum_sha256=decision_checksum_sha256,
            manual_geometry_version=MANUAL_BOARD_CELL_GEOMETRY_VERSION,
            contact_sheet_png=contact_sheet_png,
            contact_sheet_checksum_sha256=hashlib.sha256(contact_sheet_png).hexdigest(),
            cell_output_size=self._cropper.cell_output_size,
            cropper_version=CROPPER_VERSION,
            cropper_fingerprint_sha256=result.cropper_fingerprint_sha256,
            cells=previews,
            topology=self._topology,
        )

    def persist(
        self,
        *,
        preview: ManualBoardCellGeometryPreview,
        managed_data_root: Path,
        revision: int,
        namespace_discriminator: str | None = None,
    ) -> ManualBoardCellGeometryArtifacts:
        """Persist the exact validated preview as immutable, revisioned cell files."""

        if revision < 1:
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_REVISION_INVALID",
                "A manual board-cell geometry revision must be positive.",
            )
        expected_decision_checksum = manual_board_cell_geometry_decision_checksum(
            review_item_id=preview.review_item_id,
            source_order_index=preview.source_order_index,
            source_image_id=preview.source_image_id,
            source_image_checksum_sha256=preview.source_image_checksum_sha256,
            source_image_relative_path=preview.source_image_relative_path,
            source_group=preview.source_group,
            sequence_number=preview.sequence_number,
            position_index=preview.position_index,
            lattice_bounds_quad=preview.lattice_bounds_quad,
            corrected_by=preview.corrected_by,
            expected_geometry_revision=preview.expected_geometry_revision,
            expected_resolution_revision=preview.expected_resolution_revision,
            command_checksum_sha256=preview.command_checksum_sha256,
            cropper_fingerprint_sha256=self._cropper.fingerprint_sha256,
            topology=preview.topology,
        )
        if (
            preview.decision_checksum_sha256 != expected_decision_checksum
            or preview.manual_geometry_version != MANUAL_BOARD_CELL_GEOMETRY_VERSION
            or preview.cropper_version != CROPPER_VERSION
            or preview.cropper_fingerprint_sha256 != self._cropper.fingerprint_sha256
            or preview.cell_output_size != self._cropper.cell_output_size
            or preview.topology != self._topology
        ):
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_ARTIFACT_PROVENANCE_DRIFT",
                "The validated board-cell geometry provenance changed before persistence.",
            )
        expected_order = [
            (row, column)
            for row in range(self._topology.rows)
            for column in range(self._topology.columns)
        ]
        if [(cell.row_index, cell.column_index) for cell in preview.cells] != expected_order:
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_ARTIFACT_CELLS_INVALID",
                "A manual board-cell geometry revision requires complete row-major crops.",
            )
        review_path_material = preview.review_item_id
        if namespace_discriminator is not None:
            normalized_discriminator = namespace_discriminator.strip().lower()
            if len(normalized_discriminator) != 64 or any(
                character not in _SHA256_CHARS for character in normalized_discriminator
            ):
                raise ManualBoardCellGeometryPreviewError(
                    "BOARD_CELL_GEOMETRY_ARTIFACT_NAMESPACE_INVALID",
                    "The manual geometry artifact namespace discriminator is invalid.",
                )
            review_path_material = f"{review_path_material}:{normalized_discriminator}"
        # Keep the historical Windows path length unchanged while isolating
        # competing pending commands in separate immutable namespaces.
        review_path_key = hashlib.sha256(review_path_material.encode()).hexdigest()[:16]
        namespace_parts = [
            "image-review-board-cell-geometry-v19",
            review_path_key,
            f"r{revision}",
        ]
        namespace = PurePosixPath(*namespace_parts)
        artifacts: list[ManualBoardCellGeometryCellArtifact] = []
        for cell in preview.cells:
            if hashlib.sha256(cell.png).hexdigest() != cell.checksum_sha256:
                raise ManualBoardCellGeometryPreviewError(
                    "BOARD_CELL_GEOMETRY_ARTIFACT_CHECKSUM_DRIFT",
                    "A validated board-cell crop changed before persistence.",
                )
            relative_path = str(
                namespace
                / (f"cell-r{cell.row_index}-c{cell.column_index}-{cell.checksum_sha256}.png")
            )
            _write_immutable(
                managed_data_root.joinpath(*PurePosixPath(relative_path).parts),
                cell.png,
            )
            artifacts.append(
                ManualBoardCellGeometryCellArtifact(
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    source_quad=cell.source_quad,
                    padded_source_quad=cell.padded_source_quad,
                    relative_path=relative_path,
                    checksum_sha256=cell.checksum_sha256,
                )
            )
        return ManualBoardCellGeometryArtifacts(
            review_item_id=preview.review_item_id,
            source_order_index=preview.source_order_index,
            source_image_id=preview.source_image_id,
            source_image_checksum_sha256=preview.source_image_checksum_sha256,
            source_image_relative_path=preview.source_image_relative_path,
            source_group=preview.source_group,
            sequence_number=preview.sequence_number,
            position_index=preview.position_index,
            lattice_bounds_quad=preview.lattice_bounds_quad,
            image_width=preview.image_width,
            image_height=preview.image_height,
            corrected_by=preview.corrected_by,
            expected_geometry_revision=preview.expected_geometry_revision,
            expected_resolution_revision=preview.expected_resolution_revision,
            command_checksum_sha256=preview.command_checksum_sha256,
            decision_checksum_sha256=preview.decision_checksum_sha256,
            manual_geometry_version=preview.manual_geometry_version,
            cell_output_size=preview.cell_output_size,
            cropper_version=preview.cropper_version,
            cropper_fingerprint_sha256=preview.cropper_fingerprint_sha256,
            cells=tuple(artifacts),
            topology=preview.topology,
        )


def manual_board_cell_geometry_decision_checksum(
    *,
    review_item_id: str,
    source_order_index: int,
    source_image_id: str,
    source_image_checksum_sha256: str,
    source_image_relative_path: str,
    source_group: str,
    sequence_number: int,
    position_index: int,
    lattice_bounds_quad: Quad,
    corrected_by: str,
    expected_geometry_revision: int,
    expected_resolution_revision: int,
    command_checksum_sha256: str,
    cropper_fingerprint_sha256: str,
    topology: BoardCellTopology = LEGACY_BOARD_CELL_TOPOLOGY,
) -> str:
    """Bind a human v19 decision to source, position, versions and actor."""

    if not corrected_by.strip():
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_ACTOR_INVALID",
            "A manual board-cell geometry decision requires an actor.",
        )
    for value, label in (
        (source_image_checksum_sha256, "source image"),
        (command_checksum_sha256, "command"),
        (cropper_fingerprint_sha256, "cropper fingerprint"),
    ):
        if len(value) != 64 or any(character not in _SHA256_CHARS for character in value):
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_CHECKSUM_INVALID",
                f"The {label} checksum is not a lowercase SHA-256 value.",
            )
    payload = {
        "commandChecksumSha256": command_checksum_sha256,
        "coordinateSpace": BOARD_CELL_COORDINATE_SPACE,
        "correctedBy": corrected_by.strip(),
        "cornerSemantics": BOARD_CELL_CORNER_SEMANTICS,
        "cropperFingerprintSha256": cropper_fingerprint_sha256,
        "cropperVersion": CROPPER_VERSION,
        "expectedGeometryRevision": expected_geometry_revision,
        "expectedResolutionRevision": expected_resolution_revision,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "latticeBoundsQuad": [
            {"x": float(point[0]), "y": float(point[1])} for point in lattice_bounds_quad
        ],
        "manualGeometryVersion": MANUAL_BOARD_CELL_GEOMETRY_VERSION,
        "positionIndex": position_index,
        "reviewItemId": review_item_id,
        "sequenceNumber": sequence_number,
        "sourceGroup": source_group,
        "sourceImageChecksumSha256": source_image_checksum_sha256,
        "sourceImageId": source_image_id,
        "sourceImageRelativePath": source_image_relative_path,
        "sourceOrderIndex": source_order_index,
    }
    if topology.rules_version_id is not None or not topology.is_legacy_3x5:
        payload["gridRows"] = topology.rows
        payload["gridColumns"] = topology.columns
        payload["topologyRulesVersionId"] = topology.rules_version_id
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


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
    *,
    topology: BoardCellTopology = LEGACY_BOARD_CELL_TOPOLOGY,
) -> NDArray[np.uint8]:
    if len(cells) != topology.cell_count:
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_PREVIEW_CELL_COUNT_INVALID",
            "Board-cell geometry preview requires a complete topology.",
        )
    rows = []
    for row_index in range(topology.rows):
        row_cells = cells[row_index * topology.columns : (row_index + 1) * topology.columns]
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


def _write_immutable(path: Path, content: bytes) -> None:
    filesystem_path = long_path_aware(path)
    filesystem_path.parent.mkdir(parents=True, exist_ok=True)
    if filesystem_path.exists():
        try:
            if filesystem_path.read_bytes() != content:
                raise ManualBoardCellGeometryPreviewError(
                    "BOARD_CELL_GEOMETRY_ARTIFACT_COLLISION",
                    "An immutable board-cell geometry artifact has different content.",
                )
        except OSError as error:
            raise ManualBoardCellGeometryPreviewError(
                "BOARD_CELL_GEOMETRY_ARTIFACT_UNREADABLE",
                "An immutable board-cell geometry artifact cannot be read.",
            ) from error
        return
    descriptor, temporary_name = tempfile.mkstemp(
        # Keep the temporary name short enough for the legacy Windows MAX_PATH
        # limit. The final checksum-bound filename can already be close to it.
        prefix=".geometry-cell-",
        suffix=".tmp",
        dir=filesystem_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, filesystem_path)
        except FileExistsError:
            if filesystem_path.read_bytes() != content:
                raise ManualBoardCellGeometryPreviewError(
                    "BOARD_CELL_GEOMETRY_ARTIFACT_COLLISION",
                    "An immutable board-cell geometry artifact has different content.",
                ) from None
    except ManualBoardCellGeometryPreviewError:
        raise
    except OSError as error:
        raise ManualBoardCellGeometryPreviewError(
            "BOARD_CELL_GEOMETRY_ARTIFACT_WRITE_FAILED",
            "A board-cell geometry artifact cannot be written atomically.",
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "MANUAL_BOARD_CELL_GEOMETRY_VERSION",
    "MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE",
    "MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION",
    "ManualBoardCellGeometryArtifacts",
    "ManualBoardCellGeometryCellArtifact",
    "ManualBoardCellGeometryCellPreview",
    "ManualBoardCellGeometryPreview",
    "ManualBoardCellGeometryPreviewError",
    "ManualBoardCellGeometryPreviewer",
    "manual_board_cell_geometry_decision_checksum",
]
