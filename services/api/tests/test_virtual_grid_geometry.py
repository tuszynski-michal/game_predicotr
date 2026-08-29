from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from game_predictor_api.application.virtual_grid_geometry import (
    PreparedVirtualGridGeometry,
    VirtualGridGeometryContext,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySaveResult,
    VirtualGridGeometryService,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import DirectCellRenderConfiguration
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VirtualCellRenderer,
)
from PIL import Image


class MemoryVirtualGridGeometryRepository:
    def __init__(self, context: VirtualGridGeometryContext) -> None:
        self.context = context
        self.saved: list[PreparedVirtualGridGeometry] = []

    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
    ) -> VirtualGridGeometryContext:
        assert game_id == self.context.game_id
        assert import_job_id == self.context.import_job_id
        assert review_item_id == self.context.review_item_id
        return self.context

    def save_virtual_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometry,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySaveResult:
        self.saved.append(prepared)
        return VirtualGridGeometrySaveResult(
            revision=VirtualGridGeometryRevision(
                id=uuid4(),
                review_item_id=prepared.context.review_item_id,
                recognized_board_id=prepared.context.recognized_board_id,
                revision=prepared.context.geometry_revision + 1,
                idempotency_key=idempotency_key,
                command_sha256=prepared.command.command_sha256,
                corners=prepared.command.corners,
                source_geometry_revision_id=prepared.context.source_geometry_revision_id,
                geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
                virtual_render_spec_checksum_sha256=(prepared.virtual_render_spec_checksum_sha256),
                cropper_version=prepared.cropper_version,
                cells=prepared.cells,
                corrected_by=prepared.command.corrected_by,
                created_at=created_at,
            ),
            created=True,
        )


def _fixture(tmp_path: Path) -> tuple[VirtualGridGeometryService, VirtualGridGeometryContext]:
    source_path = tmp_path / "data" / "originals" / "source.jpg"
    source_path.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), color=(120, 80, 40)).save(
        source_path,
        format="JPEG",
        quality=95,
    )
    source_checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
    loader = CanonicalSourceLoader()
    frame = loader.load(
        source_path,
        expected_source_checksum_sha256=source_checksum,
    )
    context = VirtualGridGeometryContext(
        game_id=uuid4(),
        import_job_id=uuid4(),
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        source_image_id=uuid4(),
        position_index=0,
        sequence_number=1,
        source_relative_path="originals/source.jpg",
        source_checksum_sha256=source_checksum,
        raw_width=frame.raw_width,
        raw_height=frame.raw_height,
        oriented_width=frame.source.width,
        oriented_height=frame.source.height,
        exif_orientation=frame.source.exif_orientation,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        normalization_adapter_version=frame.source.normalization_adapter_version,
        resolution_revision=0,
        geometry_revision=0,
        topology=BoardTopology(rows=3, columns=5),
        topology_rules_version_id=uuid4(),
        source_geometry_revision_id=uuid4(),
        source_geometry_revision=1,
        sequence_range_start=1,
        sequence_range_end=1,
        active_board_slots=(0,),
        global_initialization=None,
        board_geometries=({"positionIndex": 0, "sequenceNumber": 1},),
        render_configuration=DirectCellRenderConfiguration(
            extractor_version=VirtualCellRenderer.version,
            preprocessing_version="rgb-v1",
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=12,
            output_height=12,
            padding_fraction=0.0,
        ),
    )
    repository = MemoryVirtualGridGeometryRepository(context)
    return VirtualGridGeometryService(repository, tmp_path), context


def _corners() -> tuple[ImageReviewGeometryPoint, ...]:
    return (
        ImageReviewGeometryPoint(5, 5),
        ImageReviewGeometryPoint(114, 5),
        ImageReviewGeometryPoint(114, 74),
        ImageReviewGeometryPoint(5, 74),
    )


def test_virtual_preview_renders_all_cells_without_persisting_png(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    files_before = tuple(path for path in tmp_path.rglob("*") if path.is_file())

    preview = service.preview(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
    )

    assert preview.contact_sheet_png.startswith(b"\x89PNG")
    assert len(preview.cells) == 15
    assert [cell.cell_index for cell in preview.cells] == list(range(15))
    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == files_before


def test_virtual_save_delegates_only_checksum_bound_metadata(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test
    idempotency_key = uuid4()
    created_at = datetime(2026, 8, 29, tzinfo=UTC)

    result = service.save(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        idempotency_key=idempotency_key,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
        actor="local-admin",
        created_at=created_at,
    )

    assert result.created is True
    assert result.revision.idempotency_key == idempotency_key
    assert len(result.revision.cells) == 15
    assert all(cell.crop_checksum_sha256 for cell in result.revision.cells)
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    assert len(repository.saved) == 1
    assert not any(path.suffix == ".png" for path in (tmp_path / "data").rglob("*"))
