from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.image_grid_review_repository import _pending_row_to_item
from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
    _reset_grid_issue_after_virtual_recrop,
)
from sqlalchemy.dialects import postgresql


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


def test_context_before_backfill_reads_only_immutable_observations() -> None:
    row = _complete_current_virtual_row(backfill_status="not_started")
    row[1].geometry_revision = 0
    session = Mock()
    session.scalars.side_effect = [
        (),
        tuple(
            SimpleNamespace(
                row_index=i // 5,
                column_index=i % 5,
                asset_mode="virtual_source",
                render_spec=_review_cell(i).render_spec,
            )
            for i in range(15)
        ),
    ]
    context = SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)
    assert context.geometry_revision == 0
    assert context.render_configuration.output_width == 64
    session.add.assert_not_called()
    session.flush.assert_not_called()


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
) -> None:
    session = Mock()
    session.scalars.return_value = tuple(_review_cell(index) for index in range(15))
    repository = SqlAlchemyVirtualGridGeometryRepository(session)

    context = repository._context_from_row(  # noqa: SLF001 - repository boundary regression
        _complete_current_virtual_row(backfill_status=backfill_status)
    )

    assert context.active_board_slots == (0,)
    assert context.position_index == 0
    assert context.topology.cell_count == 15


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
    session.scalar.return_value = SimpleNamespace(virtual_render_spec=_review_cell().render_spec)

    context = SqlAlchemyVirtualGridGeometryRepository(session)._context_from_row(row)

    assert context.position_index == 0
    assert context.topology.cell_count == 15
    assert context.render_configuration.output_width == 64
    sql = str(session.scalars.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "source_available IS true" in sql


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

    _reset_grid_issue_after_virtual_recrop(
        cell,
        active_symbol_ids_by_code={"cherry": predicted_symbol_id},
    )

    assert cell.review_state == "pending"
    assert cell.quality_issue is None
    assert cell.assignment_source == "model"
    assert cell.assigned_symbol_id == predicted_symbol_id


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


def _review_cell(index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        cell_index=index,
        geometry_revision=0,
        source_available=True,
        render_spec={
            "configuration": {
                "extractorVersion": "virtual-cell-renderer-v1",
                "preprocessingVersion": "rgb-v1",
                "interpolation": "bilinear-v1",
                "outputWidth": 64,
                "outputHeight": 64,
                "paddingFraction": 0.0,
            }
        },
    )
