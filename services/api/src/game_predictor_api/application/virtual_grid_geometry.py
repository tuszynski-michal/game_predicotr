"""Source-direct preview and persistence boundary for manual virtual geometry."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from PIL import Image

from game_predictor_api.application.image_review_assets import (
    resolve_grid_review_source_asset,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    ImageGeometryContractError,
    NormalizedSourceImage,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    canonical_json_bytes,
    derive_virtual_cells,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewSourceAsset,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryPoint,
    ValidatedImageReviewGeometryCommand,
    validate_image_review_geometry_command,
)

if TYPE_CHECKING:
    from game_predictor_worker.images.virtual_cell_extraction import (
        VirtualCellRender,
    )

VIRTUAL_MANUAL_GEOMETRY_VERSION = "manual-source-geometry-v1"
VIRTUAL_MANUAL_RENDER_MANIFEST_VERSION = "virtual-board-render-manifest-v2-dual-identity-v1"


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryContext:
    game_id: UUID
    import_job_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    source_image_id: UUID
    file_execution_key: str
    position_index: int
    sequence_number: int
    source_relative_path: str
    source_checksum_sha256: str
    raw_width: int
    raw_height: int
    oriented_width: int
    oriented_height: int
    exif_orientation: int | None
    normalized_pixel_checksum_sha256: str
    normalization_adapter_version: str
    resolution_revision: int
    geometry_revision: int
    topology: BoardTopology
    topology_rules_version_id: UUID
    source_geometry_revision_id: UUID
    source_geometry_revision: int
    sequence_range_start: int
    sequence_range_end: int
    active_board_slots: tuple[int, ...]
    global_initialization: Mapping[str, object] | None
    board_geometries: tuple[Mapping[str, object], ...]
    render_configuration: DirectCellRenderConfiguration

    @property
    def source_asset(self) -> ImageGridReviewSourceAsset:
        return ImageGridReviewSourceAsset(
            review_item_id=self.review_item_id,
            source_relative_path=self.source_relative_path,
            source_checksum_sha256=self.source_checksum_sha256,
            source_width=self.oriented_width,
            source_height=self.oriented_height,
            geometry_revision=self.geometry_revision,
            resolution_revision=self.resolution_revision,
            topology=self.topology,
        )


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryCell:
    cell_index: int
    row_index: int
    column_index: int
    crop_sample_id: str
    crop_checksum_sha256: str
    logical_cell_key: str
    logical_cell_key_v2: str | None
    render_spec: Mapping[str, object]
    render_spec_checksum_sha256: str
    rendered_pixel_checksum_sha256: str
    extractor_version: str


@dataclass(frozen=True, slots=True)
class PreparedVirtualGridGeometry:
    command: ValidatedImageReviewGeometryCommand
    context: VirtualGridGeometryContext
    source_geometry_checksum_sha256: str
    board_geometries: tuple[Mapping[str, object], ...]
    board_geometry: Mapping[str, object]
    virtual_render_spec: Mapping[str, object]
    virtual_render_spec_checksum_sha256: str
    cells: tuple[VirtualGridGeometryCell, ...]
    cropper_version: str


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryPreview:
    contact_sheet_png: bytes
    cells: tuple[VirtualGridGeometryCell, ...]
    cropper_version: str


@dataclass(frozen=True, slots=True)
class VirtualGridGeometryRevision:
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int
    idempotency_key: UUID
    command_sha256: str
    corners: tuple[ImageReviewGeometryPoint, ...]
    source_geometry_revision_id: UUID
    geometry_checksum_sha256: str
    virtual_render_spec_checksum_sha256: str
    cropper_version: str
    cells: tuple[VirtualGridGeometryCell, ...]
    corrected_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VirtualGridGeometrySaveResult:
    revision: VirtualGridGeometryRevision
    created: bool


class VirtualGridGeometryRepository(Protocol):
    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
    ) -> VirtualGridGeometryContext: ...

    def save_virtual_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySaveResult: ...


class VirtualGridGeometryService:
    """Render manual virtual crops once and persist metadata-only provenance."""

    def __init__(self, repository: VirtualGridGeometryRepository, artifact_root: Path) -> None:
        self._repository = repository
        self._artifact_root = artifact_root.resolve()

    def preview(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
    ) -> VirtualGridGeometryPreview:
        prepared, renders = self._prepare(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
            expected_source_width=expected_source_width,
            expected_source_height=expected_source_height,
            expected_grid_rows=expected_grid_rows,
            expected_grid_columns=expected_grid_columns,
            corners=corners,
            actor="local-admin-preview",
        )
        return VirtualGridGeometryPreview(
            contact_sheet_png=_contact_sheet_png(renders, prepared.context.topology),
            cells=prepared.cells,
            cropper_version=prepared.cropper_version,
        )

    def save(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
        created_at: datetime,
    ) -> VirtualGridGeometrySaveResult:
        prepared, _renders = self._prepare(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
            expected_source_width=expected_source_width,
            expected_source_height=expected_source_height,
            expected_grid_rows=expected_grid_rows,
            expected_grid_columns=expected_grid_columns,
            corners=corners,
            actor=actor,
        )
        return self._repository.save_virtual_geometry_revision(
            prepared=prepared,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def _prepare(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        corners: Sequence[ImageReviewGeometryPoint],
        actor: str,
    ) -> tuple[PreparedVirtualGridGeometry, tuple[VirtualCellRender, ...]]:
        from game_predictor_worker.images.normalization import (
            CanonicalSourceLoader,
            CanonicalSourceLoadError,
        )
        from game_predictor_worker.images.virtual_cell_extraction import (
            VirtualCellExtractionError,
            VirtualCellRenderer,
        )

        command = validate_image_review_geometry_command(
            corners=corners,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            corrected_by=actor,
        )
        context = self._repository.virtual_geometry_context(
            game_id=game_id,
            import_job_id=import_job_id,
            review_item_id=review_item_id,
        )
        _require_expected_context(
            context,
            command=command,
            source_checksum=expected_source_checksum_sha256,
            source_width=expected_source_width,
            source_height=expected_source_height,
            topology=BoardTopology(rows=expected_grid_rows, columns=expected_grid_columns),
        )
        source_path = resolve_grid_review_source_asset(
            context.source_asset,
            self._artifact_root,
        ).path
        loader = CanonicalSourceLoader()
        try:
            frame = loader.load(
                source_path,
                expected_source_checksum_sha256=context.source_checksum_sha256,
            )
            _require_frame(
                context,
                frame.source,
                raw_width=frame.raw_width,
                raw_height=frame.raw_height,
            )
            quad = SourceQuad(
                corners=cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(SourcePoint(x=point.x, y=point.y) for point in command.corners),
                )
            )
            geometry = VirtualBoardGeometry(
                source=frame.source,
                source_occurrence=SourceOccurrence(
                    import_job_id=context.import_job_id,
                    file_execution_key=context.file_execution_key,
                ),
                slot=ActiveBoardSlot(
                    range_start=context.sequence_range_start,
                    range_end=context.sequence_range_end,
                    position_index=context.position_index,
                    sequence_number=context.sequence_number,
                ),
                topology=context.topology,
                topology_rules_version_id=context.topology_rules_version_id,
                geometry_revision=context.geometry_revision + 1,
                geometry_version=VIRTUAL_MANUAL_GEOMETRY_VERSION,
                engine_kind=GeometryEngineKind.MANUAL_V1,
                symbol_grid_quad=quad,
            )
            renders = VirtualCellRenderer().render(
                frame,
                derive_virtual_cells(
                    geometry=geometry,
                    configuration=context.render_configuration,
                ),
            )
        except (
            CanonicalSourceLoadError,
            ImageGeometryContractError,
            VirtualCellExtractionError,
        ) as error:
            raise ImageGridReviewError(
                getattr(error, "code", "IMAGE_GRID_REVIEW_VIRTUAL_RENDER_FAILED"),
                str(error),
            ) from error
        finally:
            loader.clear()

        board_geometries = _replace_board_geometry(context, quad)
        source_geometry_checksum = hashlib.sha256(
            canonical_json_bytes(
                {
                    "activeBoardSlots": list(context.active_board_slots),
                    "boardGeometries": list(board_geometries),
                    "engineKind": GeometryEngineKind.MANUAL_V1.value,
                    "engineVersion": VIRTUAL_MANUAL_GEOMETRY_VERSION,
                    "previousSourceGeometryRevisionId": str(context.source_geometry_revision_id),
                    "sourceChecksumSha256": context.source_checksum_sha256,
                    "topologyRulesVersionId": str(context.topology_rules_version_id),
                }
            )
        ).hexdigest()
        cells = tuple(_cell_from_render(context.recognized_board_id, render) for render in renders)
        render_manifest: dict[str, object] = {
            "assetMode": "virtual_source",
            "cells": [
                {
                    "cellIndex": cell.cell_index,
                    "cropSampleId": cell.crop_sample_id,
                    "logicalCellKeySha256": cell.logical_cell_key,
                    "logicalCellKeyV2Sha256": cell.logical_cell_key_v2,
                    "renderSpec": dict(cell.render_spec),
                    "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
                    "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                }
                for cell in cells
            ],
            "geometryChecksumSha256": source_geometry_checksum,
            "schemaVersion": VIRTUAL_MANUAL_RENDER_MANIFEST_VERSION,
        }
        board_geometry = _recognized_board_geometry(context, quad, command.command_sha256)
        return (
            PreparedVirtualGridGeometry(
                command=command,
                context=context,
                source_geometry_checksum_sha256=source_geometry_checksum,
                board_geometries=board_geometries,
                board_geometry=board_geometry,
                virtual_render_spec=render_manifest,
                virtual_render_spec_checksum_sha256=hashlib.sha256(
                    canonical_json_bytes(render_manifest)
                ).hexdigest(),
                cells=cells,
                cropper_version=VirtualCellRenderer.version,
            ),
            renders,
        )


def _require_expected_context(
    context: VirtualGridGeometryContext,
    *,
    command: ValidatedImageReviewGeometryCommand,
    source_checksum: str,
    source_width: int,
    source_height: int,
    topology: BoardTopology,
) -> None:
    if (
        context.geometry_revision != command.expected_geometry_revision
        or context.resolution_revision != command.expected_resolution_revision
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
            "The virtual grid review changed after it was loaded.",
        )
    if (
        context.source_checksum_sha256 != source_checksum
        or context.oriented_width != source_width
        or context.oriented_height != source_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The virtual source identity changed after the grid review was loaded.",
        )
    if context.topology != topology:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
            "The board topology changed after the grid review was loaded.",
        )


def _require_frame(
    context: VirtualGridGeometryContext,
    source: NormalizedSourceImage,
    *,
    raw_width: int,
    raw_height: int,
) -> None:
    if (
        source.source_checksum_sha256 != context.source_checksum_sha256
        or source.normalized_pixel_checksum_sha256 != context.normalized_pixel_checksum_sha256
        or source.width != context.oriented_width
        or source.height != context.oriented_height
        or source.exif_orientation != context.exif_orientation
        or source.normalization_adapter_version != context.normalization_adapter_version
        or raw_width != context.raw_width
        or raw_height != context.raw_height
    ):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "The decoded virtual source differs from its canonical coordinate metadata.",
        )


def _replace_board_geometry(
    context: VirtualGridGeometryContext,
    quad: SourceQuad,
) -> tuple[Mapping[str, object], ...]:
    if context.active_board_slots != tuple(range(len(context.board_geometries))):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
            "Virtual manual geometry requires a complete attested source prefix.",
        )
    values = [dict(value) for value in context.board_geometries]
    if not 0 <= context.position_index < len(values):
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_SOURCE_GEOMETRY_INVALID",
            "The board slot is outside the attested source geometry.",
        )
    values[context.position_index].update(
        {
            "disposition": "automatic",
            "finalQuad": quad.to_dict(),
            "geometrySource": "manual",
            "positionIndex": context.position_index,
            "sequenceNumber": context.sequence_number,
        }
    )
    return tuple(values)


def _recognized_board_geometry(
    context: VirtualGridGeometryContext,
    quad: SourceQuad,
    command_checksum: str,
) -> Mapping[str, object]:
    value = dict(context.board_geometries[context.position_index])
    value.update(
        {
            "commandChecksumSha256": command_checksum,
            "coordinateSpace": "exif-normalized-rgb-pixels-v1",
            "geometryVersion": VIRTUAL_MANUAL_GEOMETRY_VERSION,
            "latticeBoundsQuad": quad.to_dict(),
            "source": "manual_override",
            "sourceQuad": quad.to_dict(),
        }
    )
    return value


def _cell_from_render(board_id: UUID, render: VirtualCellRender) -> VirtualGridGeometryCell:
    sample_id = hashlib.sha256(
        canonical_json_bytes(
            {
                "assetMode": "virtual_source",
                "recognizedBoardId": str(board_id),
                "renderSpecChecksumSha256": render.render_spec_checksum_sha256,
            }
        )
    ).hexdigest()
    return VirtualGridGeometryCell(
        cell_index=render.cell_index,
        row_index=render.row_index,
        column_index=render.column_index,
        crop_sample_id=sample_id,
        crop_checksum_sha256=render.rendered_pixel_checksum_sha256,
        logical_cell_key=render.logical_cell_key_sha256,
        logical_cell_key_v2=render.logical_cell_key_v2_sha256,
        render_spec=render.render_spec,
        render_spec_checksum_sha256=render.render_spec_checksum_sha256,
        rendered_pixel_checksum_sha256=render.rendered_pixel_checksum_sha256,
        extractor_version=render.extractor_version,
    )


def _contact_sheet_png(
    renders: Sequence[VirtualCellRender],
    topology: BoardTopology,
) -> bytes:
    if len(renders) != topology.cell_count:
        raise ImageGridReviewError(
            "IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE",
            "The virtual geometry preview is missing configured board cells.",
        )
    tile_width = max(render.rgb.shape[1] for render in renders)
    tile_height = max(render.rgb.shape[0] for render in renders)
    sheet = Image.new(
        "RGB",
        (topology.columns * tile_width, topology.rows * tile_height),
        color=(0, 0, 0),
    )
    for render in renders:
        sheet.paste(
            Image.fromarray(render.rgb, mode="RGB"),
            (render.column_index * tile_width, render.row_index * tile_height),
        )
    output = BytesIO()
    sheet.save(output, format="PNG", optimize=False)
    return output.getvalue()


__all__ = [
    "PreparedVirtualGridGeometry",
    "VirtualGridGeometryCell",
    "VirtualGridGeometryContext",
    "VirtualGridGeometryPreview",
    "VirtualGridGeometryRepository",
    "VirtualGridGeometryRevision",
    "VirtualGridGeometrySaveResult",
    "VirtualGridGeometryService",
]
