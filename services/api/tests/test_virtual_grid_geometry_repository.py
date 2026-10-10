from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.cell_render_specs import CellRenderSpecKey
from game_predictor_api.storage.image_grid_review_repository import _pending_row_to_item
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageBoardGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
    _recheck_after_virtual_recrop,
)
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize("lab", (False, True))
def test_deferred_render_configuration_uses_pinned_crop_contract(lab: bool) -> None:
    from dataclasses import replace

    from game_predictor_api.domain.symbol_model_snapshots import (
        LAB_RGB_SYMBOL_MODEL_VERSION,
        bootstrap_symbol_model_snapshot,
    )
    from game_predictor_worker.images.pipeline_contract import (
        VIRTUAL_CELL_RENDERER_VERSION,
        CellAssetRolloutMode,
        GeometryPipelineRolloutSnapshot,
        GeometryRolloutMode,
    )

    model = bootstrap_symbol_model_snapshot()
    if lab:
        model = replace(model, model_version=LAB_RGB_SYMBOL_MODEL_VERSION, crop_size=96)
    rollout = GeometryPipelineRolloutSnapshot(
        GeometryRolloutMode.STRUCTURED_DEFAULT,
        CellAssetRolloutMode.VIRTUAL_DEFAULT,
        1,
        "test-geometry",
        VIRTUAL_CELL_RENDERER_VERSION,
        "test-preprocess",
    )
    session = Mock()
    session.scalar.return_value = None
    job = SimpleNamespace(
        input_payload={
            "symbol_model": model.to_payload(),
            "image_geometry_rollout": rollout.to_payload(),
        }
    )
    configuration = SqlAlchemyVirtualGridGeometryRepository(session)._pending_render_configuration(
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        job=job,
    )
    assert configuration.output_width == configuration.output_height == (96 if lab else 64)
    assert configuration.padding_fraction == (0.0 if lab else 0.08)


@pytest.mark.parametrize(
    "existing", (None, SimpleNamespace(status="failed", failure_message="keep"))
)
def test_qualified_initializer_never_resets_existing_backfill(existing) -> None:
    session = Mock()
    session.get.return_value = existing
    SqlAlchemyVirtualGridGeometryRepository(session)._ensure_projection_state(uuid4())
    if existing is None:
        state = session.add.call_args.args[0]
        assert state.status == "rebuilding" and state.cell_count == 0
        assert state.last_review_item_id is None
    else:
        session.add.assert_not_called()
        assert existing.status == "failed" and existing.failure_message == "keep"
    assert session.scalar.call_count == 1  # game lock, no game-wide scan
    assert "with_for_update" not in session.get.call_args.kwargs


def _base_manifest(board_id: object, game_id: object, indices: range) -> BoardRenderManifestModel:
    return BoardRenderManifestModel(
        game_id=game_id,
        recognized_board_id=board_id,
        geometry_revision=0,
        asset_mode="virtual_source",
        source_geometry_revision_id=uuid4(),
        extractor_version="direct-perspective-cell-v2",
        cells={"cells": [{"cellIndex": i, "renderSpec": _RENDER_SPEC} for i in indices]},
        manifest_checksum_sha256="a" * 64,
    )


def test_context_before_backfill_reads_only_the_immutable_render_manifest() -> None:
    """D-467: before the first backfill the revision-0 specs come from the manifest."""

    row = _complete_current_virtual_row(backfill_status="not_started")
    row[1].geometry_revision = 0
    game_id = uuid4()
    row[5].game_id = game_id
    session = Mock()
    session.scalars.side_effect = [(), (_base_manifest(row[1].id, game_id, range(15)),)]
    context = SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)
    assert context.geometry_revision == 0
    assert context.render_configuration.output_width == 64
    manifest_query = str(
        session.scalars.call_args_list[1]
        .args[0]
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "board_render_manifests.game_id" in manifest_query
    assert "cell_observations" not in manifest_query
    session.add.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize("indices", (None, range(14)))
def test_context_before_backfill_without_a_complete_manifest_fails_closed(indices) -> None:
    row = _complete_current_virtual_row(backfill_status="not_started")
    row[1].geometry_revision = 0
    game_id = uuid4()
    row[5].game_id = game_id
    session = Mock()
    session.scalars.side_effect = [
        (),
        () if indices is None else (_base_manifest(row[1].id, game_id, indices),),
    ]
    with pytest.raises(ImageGridReviewError) as error:
        SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)
    assert error.value.code == "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE"


@pytest.mark.parametrize("state", (None, SimpleNamespace(failure_message="invalid crop")))
def test_qualified_pending_materialization_cannot_finish_without_projection(state) -> None:
    session = Mock()
    session.get.return_value = state
    target = uuid4()
    repository = SqlAlchemyVirtualGridGeometryRepository(session)
    with patch(
        "game_predictor_api.storage.virtual_grid_geometry_repository."
        "SymbolCellReviewWriteThroughCoordinator"
    ) as coordinator:
        coordinator.return_value.synchronize_after_geometry_change.return_value = False
        with pytest.raises(ImageGridReviewError) as raised:
            repository._synchronize_changed_source_items(
                game_id=uuid4(),
                changed_review_item_ids={target},
                qualified_review_item_ids={target},
                actor="operator",
            )
        assert raised.value.code == "IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE"
        coordinator.return_value.synchronize_after_cell_mutation.assert_not_called()


def test_legacy_pending_materialization_keeps_deferred_backfill() -> None:
    session = Mock()
    session.get.return_value = None
    with patch(
        "game_predictor_api.storage.virtual_grid_geometry_repository."
        "SymbolCellReviewWriteThroughCoordinator"
    ) as coordinator:
        coordinator.return_value.synchronize_after_geometry_change.return_value = False
        SqlAlchemyVirtualGridGeometryRepository(session)._synchronize_changed_source_items(
            game_id=uuid4(),
            changed_review_item_ids={uuid4()},
            qualified_review_item_ids=set(),
            actor="operator",
        )
        coordinator.return_value.synchronize_after_cell_mutation.assert_called_once()


@pytest.mark.parametrize("backfill_status", ("not_started", "rebuilding", "failed"))
def test_current_virtual_source_context_is_not_blocked_by_another_source_backfill(
    backfill_status: str,
    manifest_specs: list[tuple[object, tuple[CellRenderSpecKey, ...]]],
) -> None:
    session = Mock()
    session.scalars.return_value = tuple(_review_cell(index) for index in range(15))
    repository = SqlAlchemyVirtualGridGeometryRepository(session)
    row = _complete_current_virtual_row(backfill_status=backfill_status)

    context = repository._context_from_row(row)  # noqa: SLF001 - repository boundary regression

    assert context.active_board_slots == (0,)
    assert context.position_index == 0
    assert context.topology.cell_count == 15
    assert context.render_configuration.output_width == 64
    # D-467 S7: one batched manifest read keyed by the cells' render identity.
    assert len(manifest_specs) == 1
    game_id, keys = manifest_specs[0]
    assert game_id == cast(Any, row[4]).game_id
    assert keys == tuple(
        CellRenderSpecKey(_REVIEW_BOARD_ID, 0, index, _RENDER_SPEC_CHECKSUM) for index in range(15)
    )


def test_context_rejects_a_review_cell_without_virtual_render_identity(
    manifest_specs: list[tuple[object, tuple[CellRenderSpecKey, ...]]],
) -> None:
    session = Mock()
    cells = tuple(_review_cell(index) for index in range(15))
    cells[4].render_spec_checksum_sha256 = None
    session.scalars.return_value = cells
    with pytest.raises(ImageGridReviewError) as raised:
        SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(
            _complete_current_virtual_row(backfill_status="complete")
        )
    assert raised.value.code == "IMAGE_GRID_REVIEW_RENDER_CONFIGURATION_INVALID"
    assert manifest_specs == []


def test_current_virtual_source_context_still_rejects_incomplete_cell_projection() -> None:
    session = Mock()
    session.scalars.return_value = tuple(_review_cell(index) for index in range(14))
    repository = SqlAlchemyVirtualGridGeometryRepository(session)

    with pytest.raises(ImageGridReviewError, match="every review cell") as raised:
        repository._context_from_row(  # noqa: SLF001 - repository boundary regression
            _complete_current_virtual_row(backfill_status="not_started")
        )

    assert raised.value.code == "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE"


def test_virtual_geometry_crop_artifacts_none_binds_as_sql_null() -> None:
    column_type = ImageBoardGeometryRevisionModel.__table__.c.crop_artifacts.type
    processor = column_type.bind_processor(postgresql.dialect())

    assert column_type.none_as_null is True
    assert processor is not None
    assert processor(None) is None


@pytest.mark.parametrize("missing", ((0, 5, 10), tuple(range(15))))
@pytest.mark.usefixtures("manifest_specs")
def test_qualified_context_reopens_partial_and_fully_unavailable_boards(missing) -> None:
    row = _complete_current_virtual_row(backfill_status="not_started")
    board = row[1]
    board.geometry_qualification = GeometryQualification(
        "pending_partial",
        missing,
        True,
        "missing_pixels",
    ).to_dict()
    board.unavailable_cell_indices = list(missing)
    session = Mock()
    session.scalars.return_value = tuple(
        _review_cell(index) for index in range(15) if index not in missing
    )
    session.scalar.return_value = SimpleNamespace(virtual_render_spec=_RENDER_SPEC)

    context = SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)

    assert context.position_index == 0
    assert context.topology.cell_count == 15
    assert context.render_configuration.output_width == 64
    sql = str(session.scalars.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "source_available IS true" in sql


@pytest.mark.usefixtures("manifest_specs")
def test_qualified_context_only_excludes_fully_unavailable_cells_for_v3() -> None:
    row = _complete_current_virtual_row(backfill_status="not_started")
    board = row[1]
    declared = (0, 1, 5, 6, 10, 11)
    fully_unavailable = (0, 5, 10)
    board.geometry_qualification = GeometryQualification(
        completeness_status="pending_partial",
        unavailable_cell_indices=declared,
        exclude_from_geometry_training=True,
        exclusion_reason="missing_pixels",
        version="manual-geometry-qualification-v3",
        fully_unavailable_cell_indices=fully_unavailable,
    ).to_dict()
    board.unavailable_cell_indices = list(declared)
    session = Mock()
    # Partially visible cells (1, 6, 11) DO have a real review-cell row --
    # only the genuinely, fully unavailable ones (0, 5, 10) are absent.
    session.scalars.return_value = tuple(
        _review_cell(index) for index in range(15) if index not in fully_unavailable
    )
    session.scalar.return_value = SimpleNamespace(virtual_render_spec=_RENDER_SPEC)

    context = SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)

    assert context.position_index == 0
    assert context.topology.cell_count == 15


def test_context_rejects_stale_geometry_cells_even_if_count_matches() -> None:
    session = Mock()
    cells = tuple(_review_cell(index) for index in range(15))
    cells[0].geometry_revision = 99
    session.scalars.return_value = cells
    with pytest.raises(ImageGridReviewError, match="every review cell"):
        SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(
            _complete_current_virtual_row(backfill_status="complete"),
        )


def test_virtual_recrop_resets_grid_issue_to_pending_model_suggestion() -> None:
    predicted_symbol_id = uuid4()
    cell = SimpleNamespace(
        assigned_symbol_id=uuid4(),
        assignment_source="human",
        prediction_symbol_code="cherry",
        quality_issue="grid_issue",
        review_state="pending",
    )

    _recheck_after_virtual_recrop(
        cell,
        pixels_changed=True,
        active_symbol_ids_by_code={"cherry": predicted_symbol_id},
    )

    assert cell.review_state == "pending"
    assert cell.quality_issue is None
    assert cell.assignment_source == "model"
    assert cell.assigned_symbol_id == predicted_symbol_id


def test_virtual_recrop_resolves_a_grid_report_on_unchanged_pixels() -> None:
    human_symbol_id = uuid4()
    cell = SimpleNamespace(
        assigned_symbol_id=human_symbol_id,
        assignment_source="human",
        prediction_symbol_code="cherry",
        quality_issue="grid_issue",
        review_state="pending",
    )

    _recheck_after_virtual_recrop(cell, pixels_changed=False, active_symbol_ids_by_code={})

    # D-462 R5: the saved geometry resolves the report; the label waits.
    assert (cell.review_state, cell.quality_issue) == ("pending", None)
    assert (cell.assignment_source, cell.assigned_symbol_id) == ("human", human_symbol_id)


def _approved_virtual_cell(*, approved_pixels: str) -> SimpleNamespace:
    return SimpleNamespace(
        assigned_symbol_id=uuid4(),
        assignment_source="human",
        prediction_symbol_code="cherry",
        quality_issue="blurry",
        review_state="approved",
        asset_mode="virtual_source",
        crop_sample_id="s2",
        crop_checksum_sha256="c2",
        geometry_revision=2,
        source_geometry_revision_id=uuid4(),
        render_spec_checksum_sha256="r2",
        rendered_pixel_checksum_sha256="p2",
        approved_crop_sample_id="s1",
        approved_crop_checksum_sha256="c1",
        approved_geometry_revision=1,
        approved_asset_mode="virtual_source",
        approved_source_geometry_revision_id=uuid4(),
        approved_render_spec_checksum_sha256="r1",
        approved_rendered_pixel_checksum_sha256=approved_pixels,
    )


def test_virtual_recrop_rebinds_a_verification_of_identical_pixels() -> None:
    cell = _approved_virtual_cell(approved_pixels="p2")

    _recheck_after_virtual_recrop(cell, pixels_changed=False, active_symbol_ids_by_code={})

    # D-462 R6: same pixels keep the verification, bound to the new render.
    assert (cell.review_state, cell.quality_issue) == ("approved", "blurry")
    assert (cell.approved_crop_sample_id, cell.approved_geometry_revision) == ("s2", 2)
    assert cell.approved_rendered_pixel_checksum_sha256 == "p2"
    assert cell.approved_source_geometry_revision_id == cell.source_geometry_revision_id


def test_virtual_recrop_reopens_a_verification_of_other_pixels() -> None:
    cell = _approved_virtual_cell(approved_pixels="p1")
    symbol_id = cell.assigned_symbol_id

    _recheck_after_virtual_recrop(cell, pixels_changed=True, active_symbol_ids_by_code={})

    # Changed pixels need a new check; the label stays as a suggestion and the
    # old approval as history.
    assert (cell.review_state, cell.quality_issue) == ("pending", None)
    assert cell.assigned_symbol_id == symbol_id
    assert (cell.approved_crop_sample_id, cell.approved_rendered_pixel_checksum_sha256) == (
        "s1",
        "p1",
    )


def test_deferred_slot_is_exposed_as_required_manual_template() -> None:
    pending_id = uuid4()
    source_id = uuid4()
    item = _pending_row_to_item(
        (
            SimpleNamespace(
                id=pending_id,
                game_id=uuid4(),
                import_job_id=uuid4(),
                source_image_id=source_id,
                position_index=5,
                sequence_number=1239,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                reason_code="incomplete_lattice",
            ),
            SimpleNamespace(
                id=source_id,
                checksum_sha256="a" * 64,
                width=1080,
                height=1920,
                oriented_width=1080,
                oriented_height=1920,
            ),
            SimpleNamespace(
                board_geometries=[{} for _ in range(9)],
                engine_kind="structured",
                engine_version="v0.10",
            ),
        )
    )

    assert item.slot_id == pending_id
    assert item.review_item_id is None
    assert item.pending_geometry_id == pending_id
    assert item.position_index == 5
    assert item.sequence_number == 1239
    assert item.geometry["manualGeometryRequired"] is True
    assert len(item.geometry["manualTemplateQuad"]) == 4
    assert item.state.value == "needs_correction"


def test_deferred_automatic_partial_is_exposed_as_validation_grid() -> None:
    pending_id = uuid4()
    source_id = uuid4()
    proposal_quad = [
        {"x": -30, "y": 100},
        {"x": 300, "y": 100},
        {"x": 300, "y": 500},
        {"x": -30, "y": 500},
    ]
    board_geometries = [{} for _ in range(9)]
    board_geometries[5] = {
        "automaticPartialProposal": {"origin": "automatic_proposal"},
        "symbolGridQuad": proposal_quad,
    }

    item = _pending_row_to_item(
        (
            SimpleNamespace(
                id=pending_id,
                game_id=uuid4(),
                import_job_id=uuid4(),
                source_image_id=source_id,
                position_index=5,
                sequence_number=1239,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                reason_code="partial_lattice_requires_confirmation",
            ),
            SimpleNamespace(
                id=source_id,
                checksum_sha256="a" * 64,
                width=1080,
                height=1920,
                oriented_width=1080,
                oriented_height=1920,
            ),
            SimpleNamespace(
                board_geometries=board_geometries,
                engine_kind="structured",
                engine_version="v0.10",
            ),
        )
    )

    assert item.geometry["manualGeometryRequired"] is False
    assert item.geometry["sourceQuad"] == proposal_quad
    assert "manualTemplateQuad" not in item.geometry
    assert item.state.value == "needs_validation"


def test_deferred_proposal_metadata_without_grid_stays_manual() -> None:
    pending_id = uuid4()
    source_id = uuid4()
    board_geometries = [{} for _ in range(9)]
    board_geometries[0] = {
        "automaticPartialProposal": {"origin": "automatic_proposal"},
        "symbolGridQuad": None,
    }

    item = _pending_row_to_item(
        (
            SimpleNamespace(
                id=pending_id,
                game_id=uuid4(),
                import_job_id=uuid4(),
                source_image_id=source_id,
                position_index=0,
                sequence_number=1,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                reason_code="incomplete_lattice",
            ),
            SimpleNamespace(
                id=source_id,
                checksum_sha256="a" * 64,
                width=1080,
                height=1920,
                oriented_width=1080,
                oriented_height=1920,
            ),
            SimpleNamespace(
                board_geometries=board_geometries,
                engine_kind="structured",
                engine_version="v0.10",
            ),
        )
    )

    assert item.geometry["manualGeometryRequired"] is True
    assert len(item.geometry["manualTemplateQuad"]) == 4
    assert item.state.value == "needs_correction"


def _complete_current_virtual_row(*, backfill_status: str) -> tuple[object, ...]:
    game_id = uuid4()
    import_job_id = uuid4()
    source_geometry_id = uuid4()
    source_checksum = "a" * 64
    normalized_checksum = "b" * 64
    geometry_checksum = "c" * 64
    return (
        SimpleNamespace(id=uuid4(), resolution_revision=0),
        SimpleNamespace(
            id=uuid4(),
            asset_mode="virtual_source",
            source_geometry_revision_id=source_geometry_id,
            geometry_checksum_sha256=geometry_checksum,
            grid_rows=3,
            grid_columns=5,
            position_index=0,
            geometry_revision=0,
            geometry_qualification=None,
            unavailable_cell_indices=[],
            pipeline_fingerprint="d" * 64,
        ),
        SimpleNamespace(
            id=uuid4(),
            import_job_id=import_job_id,
            file_execution_key="f" * 64,
            relative_path="originals/current.jpg",
            checksum_sha256=source_checksum,
            raw_width=1080,
            raw_height=1920,
            oriented_width=1080,
            oriented_height=1920,
            exif_orientation=1,
            normalized_pixel_checksum_sha256=normalized_checksum,
            normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
        ),
        SimpleNamespace(
            id=source_geometry_id,
            revision=1,
            topology_rules_version_id=uuid4(),
            sequence_range_start=1,
            sequence_range_end=1,
            active_board_slots=[0],
            global_initialization=None,
            board_geometries=[{"positionIndex": 0, "sequenceNumber": 1}],
            geometry_checksum_sha256=geometry_checksum,
        ),
        SimpleNamespace(game_id=game_id, backfill_status=backfill_status),
        SimpleNamespace(sequence_number=1),
    )


_RENDER_SPEC: dict[str, object] = {
    "configuration": {
        "extractorVersion": "virtual-cell-renderer-v1",
        "preprocessingVersion": "rgb-v1",
        "interpolation": "bilinear-v1",
        "outputWidth": 64,
        "outputHeight": 64,
        "paddingFraction": 0.0,
    }
}
_RENDER_SPEC_CHECKSUM = sha256_canonical_json(_RENDER_SPEC)
_REVIEW_BOARD_ID = uuid4()


def _review_cell(index: int = 0) -> SimpleNamespace:
    # D-467 S7: a review cell carries only the render-spec checksum; the
    # specification is resolved from the board render manifest.
    return SimpleNamespace(
        cell_index=index,
        geometry_revision=0,
        source_available=True,
        asset_mode="virtual_source",
        recognized_board_id=_REVIEW_BOARD_ID,
        render_spec_checksum_sha256=_RENDER_SPEC_CHECKSUM,
    )


@pytest.fixture
def manifest_specs() -> Iterator[list[tuple[object, tuple[CellRenderSpecKey, ...]]]]:
    """Answer the batched manifest read with ``_RENDER_SPEC`` and record each call."""

    calls: list[tuple[object, tuple[CellRenderSpecKey, ...]]] = []

    def load(
        session: object, *, game_id: object, keys: Iterable[CellRenderSpecKey]
    ) -> dict[CellRenderSpecKey, Mapping[str, object]]:
        requested = tuple(keys)
        calls.append((game_id, requested))
        return {key: _RENDER_SPEC for key in requested}

    with patch(
        "game_predictor_api.storage.virtual_grid_geometry_repository.load_cell_render_specs",
        side_effect=load,
    ):
        yield calls


def _virtual_cell(index: int, *, symbol_id: object, **values: object) -> ImageSymbolReviewCellModel:
    cell = ImageSymbolReviewCellModel(
        id=uuid4(),
        cell_index=index,
        review_item_id=uuid4(),
        asset_mode="virtual_source",
        crop_sample_id=f"{index:064x}",
        crop_checksum_sha256=f"{100 + index:064x}",
        rendered_pixel_checksum_sha256=f"{200 + index:064x}",
        render_spec_checksum_sha256=f"{300 + index:064x}",
        geometry_revision=1,
        prediction_symbol_code="cherry",
        assigned_symbol_id=symbol_id,
        assignment_source="model",
        review_state="pending",
        quality_issue=None,
        revision=0,
        verification_outcome=None,
    )
    for key, value in values.items():
        setattr(cell, key, value)
    return cell


def _approved(index: int, symbol_id: object) -> dict[str, object]:
    return {
        "review_state": "approved",
        "assignment_source": "human",
        "approved_crop_sample_id": f"{index:064x}",
        "approved_crop_checksum_sha256": f"{100 + index:064x}",
        "approved_rendered_pixel_checksum_sha256": f"{200 + index:064x}",
        "approved_geometry_revision": 1,
        "approved_asset_mode": "virtual_source",
        "verification_outcome": "confirmed",
        "verified_symbol_id_v2": symbol_id,
    }


def test_manual_virtual_save_rechecks_changed_verifications_without_failing() -> None:
    """P0 regression (D-462 R5/R6): pending human suggestions persist."""

    symbol_id = uuid4()
    cells = [_virtual_cell(index, symbol_id=symbol_id) for index in range(15)]
    for index in (0, 1):
        for key, value in _approved(index, symbol_id).items():
            setattr(cells[index], key, value)
    cells[2].assignment_source = "human"
    cells[2].quality_issue = "grid_issue"
    cells[2].verification_outcome = "grid_issue"
    session = Mock()
    session.scalars.return_value = cells
    session.get.return_value = None
    session.execute.return_value = [(symbol_id, "cherry")]
    rendered = [
        SimpleNamespace(
            logical_cell_key=f"k{index}",
            logical_cell_key_v2=f"v{index}",
            render_identity_v2_sha256=f"{400 + index:064x}",
            render_spec={},
            render_spec_checksum_sha256=f"{500 + index:064x}",
            # Only cell 0 renders new pixels.
            rendered_pixel_checksum_sha256=f"{(900 if index == 0 else 200) + index:064x}",
            extractor_version="x",
            crop_sample_id=f"{600 + index:064x}",
            crop_checksum_sha256=f"{700 + index:064x}",
        )
        for index in range(15)
    ]
    context = SimpleNamespace(
        game_id=uuid4(),
        review_item_id=cells[0].review_item_id,
        recognized_board_id=uuid4(),
        topology=BoardTopology(rows=3, columns=5),
        pending_geometry_id=None,
    )
    prepared = SimpleNamespace(
        command=SimpleNamespace(geometry_qualification=None),
        cells=rendered,
        cropper_version="virtual-cropper",
    )

    with patch(
        "game_predictor_api.storage.virtual_grid_geometry_repository."
        "SqlAlchemyBoardSearchProjectionRepository"
    ):
        SqlAlchemyVirtualGridGeometryRepository(session)._replace_current_cells(
            context=cast(Any, context),
            revision_number=2,
            source_geometry_revision_id=uuid4(),
            prepared=cast(Any, prepared),
            actor="grid-reviewer",
            changed_at=datetime(2026, 9, 29, tzinfo=UTC),
        )

    changed, unchanged, reported = cells[0], cells[1], cells[2]
    assert (changed.review_state, changed.verification_outcome) == ("pending", "requires_review")
    assert changed.assigned_symbol_id == symbol_id
    assert changed.approved_rendered_pixel_checksum_sha256 == f"{200:064x}"
    assert (unchanged.review_state, unchanged.approved_geometry_revision) == ("approved", 2)
    assert unchanged.approved_crop_sample_id == unchanged.crop_sample_id
    assert (reported.quality_issue, reported.review_state) == (None, "pending")
    assert reported.verification_outcome == "requires_review"
    events = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ImageSymbolReviewEventModel)
    ]
    assert events[0].previous_approved_crop_checksum_sha256 == f"{100:064x}"


@pytest.mark.parametrize("qualification", [None, {"completenessStatus": "complete"}])
def test_every_manual_virtual_geometry_reopens_a_resolved_board(qualification: object) -> None:
    context = SimpleNamespace(
        game_id=uuid4(),
        import_job_id=uuid4(),
        review_item_id=uuid4(),
        pending_geometry_id=None,
    )
    prepared = SimpleNamespace(
        context=context,
        command=SimpleNamespace(
            geometry_qualification=qualification,
            command_sha256="a" * 64,
            corrected_by="grid-reviewer",
        ),
    )

    with patch(
        "game_predictor_api.storage.virtual_grid_geometry_repository."
        "SqlAlchemyOperationalImageReviewRepository"
    ) as operational:
        SqlAlchemyVirtualGridGeometryRepository(Mock())._reopen_resolved_revision(
            cast(Any, prepared), uuid4(), datetime(2026, 9, 29, tzinfo=UTC)
        )

    # D-462: a resolved layout must not survive pixels that just changed.
    operational.return_value.reopen_for_symbol_cell_issue.assert_called_once()


def test_pending_render_configuration_reads_a_current_manifest_not_cells() -> None:
    """D-467 S7: the pinned configuration comes from a current-revision manifest."""

    session = Mock()
    session.scalar.side_effect = [_RENDER_SPEC]
    configuration = SqlAlchemyVirtualGridGeometryRepository(session)._pending_render_configuration(
        source_image_id=uuid4(), import_job_id=uuid4(), job=Mock()
    )
    assert configuration.output_width == 64
    assert session.scalar.call_count == 1
    sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "board_render_manifests" in sql
    assert "image_symbol_review_cells" not in sql
    assert "recognized_boards.geometry_revision = board_render_manifests.geometry_revision" in sql
    assert "recognized_boards.source_image_id" in sql


def test_pending_render_configuration_falls_back_to_the_import_manifests() -> None:
    session = Mock()
    session.scalar.side_effect = [None, _RENDER_SPEC]
    configuration = SqlAlchemyVirtualGridGeometryRepository(session)._pending_render_configuration(
        source_image_id=uuid4(), import_job_id=uuid4(), job=Mock()
    )
    assert configuration.output_width == 64
    fallback = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "board_render_manifests" in fallback
    assert "source_images.import_job_id" in fallback
    assert "image_symbol_review_cells" not in fallback
