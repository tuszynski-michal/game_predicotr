from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from game_predictor_api.application.virtual_grid_geometry import (
    PreparedVirtualGridGeometry,
    PreparedVirtualGridGeometrySource,
    VirtualGridGeometryContext,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySaveResult,
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    DirectCellRenderConfiguration,
    SourceOccurrence,
)
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
        self.contexts = {context.review_item_id: context}
        self.saved: list[PreparedVirtualGridGeometry] = []

    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
    ) -> VirtualGridGeometryContext:
        context = self.contexts[review_item_id]
        assert game_id == context.game_id
        assert import_job_id == context.import_job_id
        return context

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

    def save_virtual_source_geometry_revision(
        self,
        *,
        prepared: PreparedVirtualGridGeometrySource,
        idempotency_key: UUID,
        created_at: datetime,
    ) -> VirtualGridGeometrySourceSaveResult:
        results = tuple(
            self.save_virtual_geometry_revision(
                prepared=entry,
                idempotency_key=idempotency_key,
                created_at=created_at,
            )
            for entry in prepared.entries
        )
        return VirtualGridGeometrySourceSaveResult(
            revisions=tuple(result.revision for result in results),
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
        file_execution_key="f" * 64,
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
    occurrence = SourceOccurrence(
        import_job_id=context.import_job_id,
        file_execution_key=context.file_execution_key,
    )
    assert all(cell.logical_cell_key_v2 is not None for cell in preview.cells)
    assert all(
        cell.render_spec["sourceOccurrenceIdSha256"] == occurrence.identity_sha256
        for cell in preview.cells
    )
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


def test_virtual_source_save_renders_one_complete_source_without_png(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test

    result = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=(
            VirtualGridGeometrySourceCommand(
                review_item_id=context.review_item_id,
                expected_geometry_revision=context.geometry_revision,
                expected_resolution_revision=context.resolution_revision,
                expected_source_checksum_sha256=context.source_checksum_sha256,
                expected_source_width=context.oriented_width,
                expected_source_height=context.oriented_height,
                expected_grid_rows=context.topology.rows,
                expected_grid_columns=context.topology.columns,
                corners=_corners(),
            ),
        ),
        idempotency_key=uuid4(),
        actor="local-admin",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert result.created is True
    assert len(result.revisions) == 1
    assert len(result.revisions[0].cells) == context.topology.cell_count
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    assert len(repository.saved) == 1
    assert not any(path.suffix == ".png" for path in (tmp_path / "data").rglob("*"))


def test_virtual_source_save_requires_and_persists_all_nine_row_major_slots(
    tmp_path: Path,
) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - application port fixture
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)

    board_geometries = tuple(
        {"positionIndex": position, "sequenceNumber": position + 1} for position in range(9)
    )
    contexts = tuple(
        replace(
            context,
            review_item_id=uuid4(),
            recognized_board_id=uuid4(),
            position_index=position,
            sequence_number=position + 1,
            sequence_range_end=9,
            active_board_slots=tuple(range(9)),
            board_geometries=board_geometries,
        )
        for position in range(9)
    )
    repository.contexts = {entry.review_item_id: entry for entry in contexts}

    result = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=tuple(
            VirtualGridGeometrySourceCommand(
                review_item_id=entry.review_item_id,
                expected_geometry_revision=entry.geometry_revision,
                expected_resolution_revision=entry.resolution_revision,
                expected_source_checksum_sha256=entry.source_checksum_sha256,
                expected_source_width=entry.oriented_width,
                expected_source_height=entry.oriented_height,
                expected_grid_rows=entry.topology.rows,
                expected_grid_columns=entry.topology.columns,
                corners=_cell_corners(entry.position_index),
            )
            for entry in contexts
        ),
        idempotency_key=uuid4(),
        actor="local-admin",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    assert result.created is True
    assert [revision.review_item_id for revision in result.revisions] == [
        entry.review_item_id for entry in contexts
    ]
    assert len(repository.saved) == 9
    assert all(
        tuple(geometry["positionIndex"] for geometry in prepared.board_geometries)
        == tuple(range(9))
        for prepared in repository.saved
    )


def _cell_corners(position_index: int) -> tuple[ImageReviewGeometryPoint, ...]:
    row, column = divmod(position_index, 3)
    left = column * 40
    top = row * 26
    return (
        ImageReviewGeometryPoint(x=left, y=top),
        ImageReviewGeometryPoint(x=left + 38, y=top),
        ImageReviewGeometryPoint(x=left + 38, y=top + 24),
        ImageReviewGeometryPoint(x=left, y=top + 24),
    )
