from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.virtual_grid_geometry import (
    PreparedVirtualGridGeometry,
    PreparedVirtualGridGeometrySource,
    VirtualGridCellSymbol,
    VirtualGridGeometryContext,
    VirtualGridGeometryRevision,
    VirtualGridGeometrySaveResult,
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    DirectCellRenderConfiguration,
    SourceOccurrence,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPrediction,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VirtualCellRenderer,
)
from PIL import Image


class MemoryVirtualGridGeometryRepository:
    def __init__(self, context: VirtualGridGeometryContext) -> None:
        self.context = context
        self.contexts = {context.target_id: context}
        self.saved: list[PreparedVirtualGridGeometry] = []
        self.assigned: list[tuple[UUID, tuple[VirtualGridCellSymbol, ...], str]] = []
        self.replays: dict[tuple[UUID, UUID], VirtualGridGeometryRevision] = {}

    def assign_cell_symbols(self, *, game_id, review_item_id, cell_symbols, actor) -> int:
        self.assigned.append((review_item_id, tuple(cell_symbols), actor))
        return len(cell_symbols)

    def virtual_geometry_replay(self, *, context, idempotency_key):
        return self.replays.get((context.target_id, idempotency_key))

    def virtual_geometry_context(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID | None,
        pending_geometry_id: UUID | None,
    ) -> VirtualGridGeometryContext:
        context = self.contexts[pending_geometry_id or review_item_id]
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
                review_item_id=prepared.context.target_id,
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
        pending_geometry_id=None,
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
        pipeline_fingerprint="f" * 64,
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


@pytest.mark.parametrize("all_missing", [False, True])
def test_qualified_partial_preview_renders_partially_visible_masked_cells(
    tmp_path: Path, all_missing: bool
) -> None:
    service, context = _fixture(tmp_path)
    qualification = GeometryQualification(
        "pending_partial", tuple(range(15)) if all_missing else (0,), True, "missing_pixels"
    )
    corners = tuple(ImageReviewGeometryPoint(point.x - 12, point.y) for point in _corners())
    kwargs = dict(
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
        corners=corners,
        geometry_qualification=qualification,
    )
    preview = service.preview(**kwargs)
    # Masked cells that keep real source pixels are still rendered for manual
    # review (D-434, D-435); only cells fully outside the photo have no render.
    assert [cell.cell_index for cell in preview.cells] == list(range(15))
    assert preview.contact_sheet_png.startswith(b"\x89PNG")
    service.save(**kwargs, idempotency_key=uuid4(), actor="operator", created_at=datetime.now(UTC))
    prepared = service._repository.saved[0]
    expected_mask = list(range(15)) if all_missing else [0, 5, 10]
    assert (
        prepared.board_geometries[0]["geometryQualification"]["unavailableCellIndices"]
        == expected_mask
    )
    assert (
        prepared.board_geometry["geometryQualification"]
        == prepared.board_geometries[0]["geometryQualification"]
    )
    assert prepared.virtual_render_spec["configuration"] == context.render_configuration.to_dict()


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


def test_virtual_save_replays_after_lost_response_without_rendering_or_old_cas_error(
    tmp_path, monkeypatch
):
    service, context = _fixture(tmp_path)
    repository = service._repository
    key = uuid4()
    kwargs = dict(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        idempotency_key=key,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
        geometry_qualification=GeometryQualification("complete", (), True, "manual_exclusion"),
        actor="local-admin",
        created_at=datetime.now(UTC),
    )
    first = service.save(**kwargs)
    repository.replays[(context.target_id, key)] = first.revision
    repository.contexts[context.target_id] = replace(
        context, geometry_revision=1, resolution_revision=1
    )
    monkeypatch.setattr(service, "_prepare", lambda **_: pytest.fail("Replay must not render"))
    replay = service.save(**kwargs)
    assert not replay.created and replay.revision == first.revision and len(repository.saved) == 1
    with pytest.raises(ImageGridReviewError, match="another command"):
        service.save(
            **{
                **kwargs,
                "geometry_qualification": GeometryQualification("complete", (), False, None),
            }
        )
    with pytest.raises(ImageGridReviewError, match="source identity"):
        service.save(**{**kwargs, "expected_source_checksum_sha256": "0" * 64})


def test_virtual_source_save_renders_one_complete_source_without_png(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test

    result = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=(
            VirtualGridGeometrySourceCommand(
                review_item_id=context.review_item_id,
                pending_geometry_id=None,
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


def test_manual_correction_rebinds_cells_pinned_to_a_previous_renderer(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    historic = replace(
        context,
        render_configuration=replace(
            context.render_configuration,
            extractor_version="virtual-cell-renderer-source-direct-v1",
        ),
    )
    repository.contexts = {historic.target_id: historic}
    identity = dict(
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
    )

    saved = service.save(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        idempotency_key=uuid4(),
        actor="local-admin",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        **identity,
    )
    source = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=(
            VirtualGridGeometrySourceCommand(
                review_item_id=context.review_item_id,
                pending_geometry_id=None,
                **identity,
            ),
        ),
        idempotency_key=uuid4(),
        actor="local-admin",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    expected = replace(
        historic.render_configuration, extractor_version=VirtualCellRenderer.version
    ).to_dict()
    for cell in (*saved.revision.cells, *source.revisions[0].cells):
        assert cell.extractor_version == VirtualCellRenderer.version
        assert cell.render_spec["configuration"] == expected


def test_virtual_source_save_requires_and_persists_all_nine_row_major_slots(
    tmp_path: Path,
    monkeypatch,
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
    repository.contexts = {entry.target_id: entry for entry in contexts}

    commands = tuple(
        VirtualGridGeometrySourceCommand(
            review_item_id=entry.review_item_id,
            pending_geometry_id=None,
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
    )
    key = uuid4()
    result = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=commands,
        idempotency_key=key,
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
    for entry, prior in zip(contexts, result.revisions, strict=True):
        repository.replays[(entry.target_id, key)] = prior
        repository.contexts[entry.target_id] = replace(
            entry, geometry_revision=1, resolution_revision=1
        )
    monkeypatch.setattr(
        service, "_prepare_source", lambda **_: pytest.fail("Retry must not render")
    )
    kwargs = dict(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        idempotency_key=key,
        actor="local-admin",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    replay = service.save_source(commands=commands, **kwargs)
    assert replay.revisions == result.revisions and not replay.created
    with pytest.raises(ImageGridReviewError, match="every active slot"):
        service.save_source(commands=commands[:-1], **kwargs)
    repository.replays[(contexts[0].target_id, key)] = replace(
        result.revisions[0], source_geometry_revision_id=uuid4()
    )
    with pytest.raises(ImageGridReviewError, match="every active slot"):
        service.save_source(commands=commands, **kwargs)


@pytest.mark.parametrize("all_deferred", [False, True])
def test_virtual_source_save_accepts_one_deferred_slot_only_as_part_of_complete_source(
    tmp_path: Path,
    all_deferred: bool,
) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - application port fixture
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    board_geometries = tuple(
        {
            "positionIndex": position,
            "sequenceNumber": 1234 + position,
            **(
                {
                    "reviewDraftQuad": [
                        {"x": point.x, "y": point.y} for point in _cell_corners(position)
                    ],
                    "reviewDraftOrigin": "page_projection_confident_neighbors_v1",
                }
                if position == 5
                else {}
            ),
        }
        for position in range(9)
    )
    contexts = []
    for position in range(9):
        pending_id = uuid4() if position == 5 or all_deferred else None
        contexts.append(
            replace(
                context,
                review_item_id=None if pending_id is not None else uuid4(),
                recognized_board_id=pending_id or uuid4(),
                pending_geometry_id=pending_id,
                position_index=position,
                sequence_number=1234 + position,
                sequence_range_start=1234,
                sequence_range_end=1242,
                active_board_slots=tuple(range(9)),
                board_geometries=board_geometries,
            )
        )
    repository.contexts = {entry.target_id: entry for entry in contexts}

    result = service.save_source(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        commands=tuple(
            VirtualGridGeometrySourceCommand(
                review_item_id=entry.review_item_id,
                pending_geometry_id=entry.pending_geometry_id,
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
        created_at=datetime(2026, 9, 6, tzinfo=UTC),
    )

    assert len(result.revisions) == 9
    assert result.revisions[5].review_item_id == contexts[5].pending_geometry_id
    assert len(repository.saved) == 9
    assert repository.saved[5].command.corners == _cell_corners(5)


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


class RecordingSymbolPredictor:
    """Pinned-model stand-in: one deterministic prediction per rendered cell."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[tuple[int, int], ...], str]] = []

    def predict_rendered_cells(self, cells, snapshot):  # type: ignore[no-untyped-def]
        positions = tuple((cell.row_index, cell.column_index) for cell in cells)
        self.calls.append((positions, snapshot.model_version))
        return ManualBoardCellSymbolPrediction(
            model_iteration_id=None,
            model_manifest_checksum_sha256=snapshot.manifest_checksum_sha256,
            model_version=snapshot.model_version,
            temperature_applied=0.5,
            cells=tuple(
                {
                    "alternatives": [{"confidence": 1.0, "symbolCode": "seven"}],
                    "columnIndex": column,
                    "confidence": 0.9,
                    "rowIndex": row,
                    "symbolCode": "seven",
                }
                for row, column in positions
            ),
        )


def _deferred_source(
    tmp_path: Path,
    *,
    predictor: RecordingSymbolPredictor | None = None,
) -> tuple[
    VirtualGridGeometryService,
    MemoryVirtualGridGeometryRepository,
    tuple[VirtualGridGeometryContext, ...],
]:
    base_service, context = _fixture(tmp_path)
    repository = base_service._repository  # noqa: SLF001 - application port fixture
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    board_geometries = tuple(
        {
            "positionIndex": position,
            "sequenceNumber": 1234 + position,
            "finalQuad": None if position == 5 else {"existing": position},
        }
        for position in range(9)
    )
    contexts = tuple(
        replace(
            context,
            review_item_id=None if position == 5 else uuid4(),
            recognized_board_id=uuid4(),
            pending_geometry_id=uuid4() if position == 5 else None,
            position_index=position,
            sequence_number=1234 + position,
            sequence_range_start=1234,
            sequence_range_end=1242,
            active_board_slots=tuple(range(9)),
            board_geometries=board_geometries,
            pending_symbol_model=(
                bootstrap_symbol_model_snapshot().to_payload() if position == 5 else None
            ),
        )
        for position in range(9)
    )
    repository.contexts = {entry.target_id: entry for entry in contexts}
    service = VirtualGridGeometryService(
        repository,
        tmp_path,
        symbol_predictor=predictor,  # type: ignore[arg-type]
    )
    return service, repository, contexts


def test_pending_slot_save_resolves_only_the_deferred_slot_with_pinned_predictions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    predictor = RecordingSymbolPredictor()
    service, repository, contexts = _deferred_source(tmp_path, predictor=predictor)
    deferred = contexts[5]
    assert deferred.pending_geometry_id is not None
    key = uuid4()
    kwargs = dict(
        game_id=deferred.game_id,
        import_job_id=deferred.import_job_id,
        pending_geometry_id=deferred.pending_geometry_id,
        idempotency_key=key,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
        actor="reviewer-session:test",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    result = service.save_pending_slot(**kwargs)

    assert result.created is True
    assert len(result.revisions) == 1 and len(repository.saved) == 1
    prepared = repository.saved[0]
    assert prepared.context.target_id == deferred.pending_geometry_id
    # The other eight slots keep their current quads; only slot 5 changes.
    assert [geometry.get("finalQuad") for geometry in prepared.board_geometries[:5]] == [
        {"existing": position} for position in range(5)
    ]
    assert prepared.board_geometries[5]["geometrySource"] == "manual"
    assert prepared.virtual_render_spec["assetMode"] == "virtual_source"
    assert len(prepared.cells) == 15
    assert prepared.slot_prediction is not None
    assert [(cell["rowIndex"], cell["columnIndex"]) for cell in prepared.slot_prediction.cells] == [
        (cell.row_index, cell.column_index) for cell in prepared.cells
    ]
    assert prepared.slot_prediction.model_version == bootstrap_symbol_model_snapshot().model_version
    assert len(predictor.calls) == 1
    assert not any(path.suffix == ".png" for path in (tmp_path / "data").rglob("*"))

    repository.replays[(deferred.target_id, key)] = result.revisions[0]
    monkeypatch.setattr(
        service, "_prepare_source", lambda **_: pytest.fail("Retry must not render")
    )
    replay = service.save_pending_slot(**kwargs)
    assert replay.created is False and replay.revisions == result.revisions
    with pytest.raises(ImageGridReviewError, match="another command"):
        service.save_pending_slot(**{**kwargs, "corners": _cell_corners(4)})


def test_pending_slot_preview_renders_without_prediction_or_persistence(tmp_path: Path) -> None:
    predictor = RecordingSymbolPredictor()
    service, repository, contexts = _deferred_source(tmp_path, predictor=predictor)
    deferred = contexts[5]
    assert deferred.pending_geometry_id is not None

    preview = service.preview_pending_slot(
        game_id=deferred.game_id,
        import_job_id=deferred.import_job_id,
        pending_geometry_id=deferred.pending_geometry_id,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
    )

    assert preview.contact_sheet_png.startswith(b"\x89PNG")
    assert len(preview.cells) == 15
    assert predictor.calls == [] and repository.saved == []


def test_pending_slot_save_rejects_a_stale_revision(tmp_path: Path) -> None:
    service, _repository, contexts = _deferred_source(tmp_path)
    deferred = contexts[5]
    assert deferred.pending_geometry_id is not None

    with pytest.raises(ImageGridReviewError) as error:
        service.save_pending_slot(
            game_id=deferred.game_id,
            import_job_id=deferred.import_job_id,
            pending_geometry_id=deferred.pending_geometry_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=1,
            expected_resolution_revision=0,
            corners=_cell_corners(5),
            actor="reviewer-session:test",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
        )

    assert error.value.code == "IMAGE_GRID_REVIEW_REVISION_CONFLICT"


def test_partial_source_correction_accepts_only_one_deferred_slot(tmp_path: Path) -> None:
    service, _repository, contexts = _deferred_source(tmp_path)
    current = contexts[4]

    with pytest.raises(ImageGridReviewError) as error:
        service._prepare_source(  # noqa: SLF001 - guard of the partial source path
            game_id=current.game_id,
            import_job_id=current.import_job_id,
            commands=(
                VirtualGridGeometrySourceCommand(
                    review_item_id=current.review_item_id,
                    pending_geometry_id=None,
                    expected_geometry_revision=0,
                    expected_resolution_revision=0,
                    expected_source_checksum_sha256=current.source_checksum_sha256,
                    expected_source_width=current.oriented_width,
                    expected_source_height=current.oriented_height,
                    expected_grid_rows=3,
                    expected_grid_columns=5,
                    corners=_cell_corners(4),
                ),
            ),
            actor="reviewer-session:test",
            require_complete_source=False,
        )

    assert error.value.code == "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT"


def test_pending_slot_without_predictor_stays_unclassified(tmp_path: Path) -> None:
    service, repository, contexts = _deferred_source(tmp_path)
    deferred = contexts[5]
    assert deferred.pending_geometry_id is not None

    service.save_pending_slot(
        game_id=deferred.game_id,
        import_job_id=deferred.import_job_id,
        pending_geometry_id=deferred.pending_geometry_id,
        idempotency_key=uuid4(),
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
        actor="local-admin",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert repository.saved[0].slot_prediction is None


@pytest.mark.parametrize(
    ("pinned", "sequence", "expected"),
    ((0, None, 1), (3, None, 4), (0, 1, 2), (3, 1, 4), (1, 5, 6)),
)
def test_pending_slot_continues_the_sequence_revision(
    tmp_path: Path, pinned: int, sequence: int | None, expected: int
) -> None:
    """TASK-0702 handoff rule on the virtual path: max(pinned, current) + 1."""

    service, repository, contexts = _deferred_source(tmp_path)
    deferred = replace(contexts[5], geometry_revision=pinned, sequence_geometry_revision=sequence)
    assert deferred.pending_geometry_id is not None
    repository.contexts[deferred.target_id] = deferred

    service.save_pending_slot(
        game_id=deferred.game_id,
        import_job_id=deferred.import_job_id,
        pending_geometry_id=deferred.pending_geometry_id,
        idempotency_key=uuid4(),
        expected_geometry_revision=pinned,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
        actor="reviewer-session:test",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert deferred.next_geometry_revision == expected
    prepared = repository.saved[0]
    assert {cell.render_spec.get("geometryRevision") for cell in prepared.cells} == {expected}


def test_save_approves_operator_symbols_after_the_geometry_and_again_on_replay(
    tmp_path: Path, monkeypatch
) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)
    symbols = (
        VirtualGridCellSymbol(cell_index=3, symbol_id=uuid4()),
        VirtualGridCellSymbol(cell_index=7, symbol_id=uuid4()),
    )
    key = uuid4()
    kwargs = dict(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        idempotency_key=key,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
        actor="local-admin",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    first = service.save(**kwargs, cell_symbols=symbols)

    assert len(repository.saved) == 1
    assert repository.assigned == [(context.review_item_id, symbols, "local-admin")]

    # A lost response is retried with the same key: no second geometry, the
    # idempotent assignments run again.
    repository.replays[(context.target_id, key)] = first.revision
    monkeypatch.setattr(service, "_prepare", lambda **_: pytest.fail("Replay must not render"))
    replay = service.save(**kwargs, cell_symbols=symbols)
    assert not replay.created and len(repository.saved) == 1
    assert repository.assigned == [(context.review_item_id, symbols, "local-admin")] * 2

    # Without operator symbols the save never touches symbol decisions.
    service.save(**{**kwargs, "idempotency_key": key})
    assert len(repository.assigned) == 2


def test_save_rejects_two_operator_symbols_for_one_cell_before_any_write(tmp_path: Path) -> None:
    service, context = _fixture(tmp_path)
    repository = service._repository  # noqa: SLF001 - inspect the application port in a unit test
    assert isinstance(repository, MemoryVirtualGridGeometryRepository)

    with pytest.raises(ImageGridReviewError) as error:
        service.save(
            game_id=context.game_id,
            import_job_id=context.import_job_id,
            review_item_id=context.review_item_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            expected_source_checksum_sha256=context.source_checksum_sha256,
            expected_source_width=context.oriented_width,
            expected_source_height=context.oriented_height,
            expected_grid_rows=3,
            expected_grid_columns=5,
            corners=_corners(),
            actor="local-admin",
            created_at=datetime(2026, 10, 2, tzinfo=UTC),
            cell_symbols=(
                VirtualGridCellSymbol(cell_index=3, symbol_id=uuid4()),
                VirtualGridCellSymbol(cell_index=3, symbol_id=uuid4()),
            ),
        )

    assert error.value.code == "IMAGE_GRID_REVIEW_CELL_SYMBOLS_INVALID"
    assert repository.saved == [] and repository.assigned == []


def test_pending_slot_save_approves_operator_symbols_on_the_new_board(tmp_path: Path) -> None:
    service, repository, contexts = _deferred_source(tmp_path)
    deferred = contexts[5]
    assert deferred.pending_geometry_id is not None
    symbols = (VirtualGridCellSymbol(cell_index=0, symbol_id=uuid4()),)

    result = service.save_pending_slot(
        game_id=deferred.game_id,
        import_job_id=deferred.import_job_id,
        pending_geometry_id=deferred.pending_geometry_id,
        idempotency_key=uuid4(),
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_cell_corners(5),
        actor="reviewer-session:test",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        cell_symbols=symbols,
    )

    assert repository.assigned == [
        (result.revisions[0].review_item_id, symbols, "reviewer-session:test")
    ]
