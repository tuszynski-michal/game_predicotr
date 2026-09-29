"""Source geometry, logical positions and no-asset transition regressions."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    source_quad_intersects_image,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
)
from game_predictor_api.storage.symbol_cell_source_visibility import current_source_visibilities
from test_qualified_cell_reconciliation import _cells, _install_pinned_geometry_records


def _quad(x0, y0, x1, y1):
    return [{"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1}, {"x": x0, "y": y1}]


@pytest.mark.parametrize(
    "rectangle, expected",
    [
        ((10, 10, 20, 20), True),
        ((-10, 30, 110, 40), True),
        ((-10, -10, 110, 110), True),
        ((-10, 0, 0.01, 5), True),
        ((-10, 0, 0, 5), False),
        ((100, 10, 110, 20), False),
    ],
)
def test_positive_area_intersection_including_all_corners_outside(rectangle, expected):
    quad = SourceQuad(tuple(SourcePoint(**point) for point in _quad(*rectangle)))
    assert source_quad_intersects_image(quad, SourceImageBounds(100, 100)) is expected


def test_corrected_footprints_override_old_board_outline():
    cells = [
        {"rowIndex": i // 5, "columnIndex": i % 5, "sourceQuad": _quad(10, 10, 20, 20)}
        for i in range(15)
    ]
    cells[0]["sourceQuad"] = _quad(-10, 30, 110, 40)
    cells[1]["sourceQuad"] = _quad(-20, 10, -10, 20)
    visibility = current_source_visibilities(
        geometry={"quad": _quad(1, 1, 99, 99), "cells": cells},
        width=100,
        height=100,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
    )
    assert visibility == ("partial", "outside") + ("full",) * 13


def _coordinator(monkeypatch, *, asset_mode="virtual_source"):
    monkeypatch.setattr(
        "game_predictor_api.storage.image_symbol_review_repository._uses_logical_current_cell_identity",
        lambda *_: True,
    )
    rows, events = [], []
    session = Mock()
    session.scalars.side_effect = lambda _: tuple(rows)
    symbol_id = uuid4()
    session.execute.return_value = [(symbol_id, "cherry")]

    def add(row):
        if isinstance(row, ImageSymbolReviewCellModel):
            row.id = uuid4()
            rows.append(row)
        elif isinstance(row, ImageSymbolReviewEventModel):
            events.append(row)
        else:
            raise AssertionError(type(row))

    session.add.side_effect = add
    board = SimpleNamespace(
        id=uuid4(),
        grid_rows=3,
        grid_columns=5,
        sequence_number=62287,
        asset_mode=asset_mode,
        source_geometry_revision_id=uuid4() if asset_mode == "virtual_source" else None,
        geometry_revision=1,
        completeness_status="pending_partial",
        unavailable_cell_indices=[0],
        geometry_qualification=GeometryQualification(
            "pending_partial",
            (0,),
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=(0,),
        ).to_dict(),
    )
    cells = [
        {"rowIndex": i // 5, "columnIndex": i % 5, "sourceQuad": _quad(10, 10, 20, 20)}
        for i in range(15)
    ]
    cells[0]["sourceQuad"] = _quad(-20, 10, -10, 20)
    board.board_geometry = {"cells": cells}
    item = SimpleNamespace(id=uuid4(), status="pending", resolved_value=None)
    source = SimpleNamespace(
        import_job_id=uuid4(), width=100, height=100, oriented_width=100, oriented_height=100
    )
    _install_pinned_geometry_records(session, board, source)
    coordinator = SymbolCellReviewWriteThroughCoordinator(session)
    coordinator._state_if_initialized = Mock(
        return_value=SimpleNamespace(failure_message=None, count_projection_status="unavailable")
    )
    coordinator._touch_catalog_revision = Mock()
    coordinator._refresh_search_projection = Mock()
    coordinator._review_row = Mock(return_value=(item, board, source, Mock(), Mock()))
    coordinator._current_cells = Mock(
        return_value=(_cells(1, (0,), asset_mode=asset_mode), "cropper-v1", None, None)
    )
    return (
        coordinator,
        board,
        rows,
        events,
        symbol_id,
        dict(game_id=uuid4(), review_item_id=item.id),
    )


@pytest.mark.parametrize("asset_mode", ["virtual_source", "legacy_file"])
def test_outside_position_retry_and_new_pixels_preserve_human_label(monkeypatch, asset_mode):
    coordinator, board, rows, events, symbol_id, args = _coordinator(
        monkeypatch, asset_mode=asset_mode
    )
    assert coordinator.synchronize_after_geometry_change(**args)
    # D-462 R8: changed cell rows refresh the board's search evidence.
    coordinator._refresh_search_projection.assert_called_with(args["review_item_id"])
    assert len(rows) == 15
    outside = next(row for row in rows if row.cell_index == 0)
    assert outside.source_visibility == "outside" and outside.crop_sample_id is None
    assert not coordinator.synchronize_for_backfill_reconciliation(**args)
    outside.assigned_symbol_id, outside.assignment_source = symbol_id, "human"
    outside.review_state, outside.quality_issue = "approved", "unreadable"
    outside.verification_outcome, outside.verified_symbol_id_v2 = "unreadable", None
    assert not coordinator.synchronize_for_backfill_reconciliation(**args)
    board.geometry_revision = 2
    board.board_geometry["cells"][0]["sourceQuad"] = _quad(10, 10, 20, 20)
    board.geometry_qualification = GeometryQualification().to_dict()
    board.unavailable_cell_indices = []
    board.completeness_status = "complete"
    coordinator._current_cells.return_value = (
        _cells(2, (), asset_mode=asset_mode),
        "cropper-v1",
        None,
        None,
    )
    assert coordinator.synchronize_after_geometry_change(**args)
    assert len(rows) == 15
    assert outside.source_available and outside.source_visibility == "full"
    # D-462 R6: new pixels need a new check; the human label stays as a
    # pending suggestion, while pixel-bound flags do not carry over.
    assert outside.assigned_symbol_id == symbol_id and outside.quality_issue is None
    assert outside.assignment_source == "human"
    assert outside.review_state == "pending" and outside.approved_crop_sample_id is None
    count = len(events)
    assert not coordinator.synchronize_for_backfill_reconciliation(**args)
    assert len(events) == count


def test_outside_grid_report_lasts_until_a_new_geometry(monkeypatch):
    coordinator, board, rows, _events, symbol_id, args = _coordinator(monkeypatch)
    assert coordinator.synchronize_after_geometry_change(**args)
    outside = next(row for row in rows if row.cell_index == 0)
    outside.assigned_symbol_id, outside.assignment_source = symbol_id, "human"
    outside.quality_issue, outside.verification_outcome = "grid_issue", "grid_issue"

    # R7: an unrelated synchronization keeps the report.
    coordinator.synchronize_for_backfill_reconciliation(**args)
    assert outside.quality_issue == "grid_issue"

    # R5: a newly saved geometry resolves it; the logical label stays.
    board.geometry_revision = 2
    coordinator._current_cells.return_value = (
        _cells(2, (0,), asset_mode="virtual_source"),
        "cropper-v1",
        None,
        None,
    )
    assert coordinator.synchronize_after_geometry_change(**args)
    assert outside.quality_issue is None and outside.review_state == "pending"
    assert outside.assigned_symbol_id == symbol_id


def test_projection_error_propagates_to_transaction_owner(monkeypatch):
    coordinator, _board, rows, _events, _symbol, args = _coordinator(monkeypatch)
    coordinator._current_cells.side_effect = ValueError("missing real source crop")
    with pytest.raises(SymbolCellReviewError, match="missing real source crop"):
        coordinator.synchronize_after_geometry_change(**args)
    assert rows == []


@pytest.mark.parametrize("sequence", [62287, 62404, 62440])
def test_legacy_full_crop_set_with_old_partial_mask_projects_all_positions(monkeypatch, sequence):
    coordinator, board, rows, _events, _symbol, args = _coordinator(
        monkeypatch, asset_mode="legacy_file"
    )
    board.sequence_number = sequence
    board.geometry_qualification = GeometryQualification(
        "pending_partial", (0,), True, "missing_pixels"
    ).to_dict()
    board.board_geometry["cells"][0]["sourceQuad"] = _quad(-2, 10, 20, 20)
    coordinator._current_cells.return_value = (
        _cells(1, (), asset_mode="legacy_file"),
        "cropper-v1",
        None,
        None,
    )
    assert coordinator.synchronize_after_geometry_change(**args)
    assert len(rows) == 15
    partial = next(row for row in rows if row.cell_index == 0)
    assert partial.source_visibility == "partial" and partial.assigned_symbol_id is None


def test_human_blurry_decision_survives_outside_and_two_recrops(monkeypatch):
    from game_predictor_api.domain.image_symbol_reviews import mark_symbol_cell_blurry
    from game_predictor_api.storage.image_symbol_review_repository import (
        _apply_symbol_cell_review_transition,
        _symbol_cell_review_from_model,
    )

    coordinator, board, rows, events, symbol_id, args = _coordinator(monkeypatch)
    coordinator.synchronize_after_geometry_change(**args)
    cell = next(row for row in rows if row.cell_index == 1)
    review = _symbol_cell_review_from_model(cell, symbol_code_by_id={symbol_id: "cherry"})
    transition = mark_symbol_cell_blurry(review, active_symbol_codes=("cherry",))
    _apply_symbol_cell_review_transition(
        cell, review=transition.review, symbol_id_by_code={"cherry": symbol_id}, actor="operator"
    )
    old_approval = cell.approved_crop_checksum_sha256
    board.geometry_revision = 2
    board.board_geometry["cells"][1]["sourceQuad"] = _quad(-20, 10, -10, 20)
    board.unavailable_cell_indices = [0, 1]
    board.geometry_qualification = GeometryQualification(
        "pending_partial",
        (0, 1),
        True,
        "missing_pixels",
        version="manual-geometry-qualification-v3",
        fully_unavailable_cell_indices=(0, 1),
    ).to_dict()
    coordinator._current_cells.return_value = (
        _cells(2, (0, 1), asset_mode="virtual_source"),
        "cropper-v1",
        None,
        None,
    )
    coordinator.synchronize_after_geometry_change(**args)
    assert cell.source_visibility == "outside" and cell.crop_sample_id is None
    assert cell.assigned_symbol_id == symbol_id and cell.review_state == "pending"
    assert cell.approved_crop_checksum_sha256 == old_approval
    for revision in (3, 4):
        board.geometry_revision = revision
        board.board_geometry["cells"][1]["sourceQuad"] = _quad(10, 10, 20, 20)
        board.unavailable_cell_indices = [0]
        board.geometry_qualification = GeometryQualification(
            "pending_partial",
            (0,),
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=(0,),
        ).to_dict()
        coordinator._current_cells.return_value = (
            _cells(revision, (0,), asset_mode="virtual_source"),
            "cropper-v1",
            None,
            None,
        )
        coordinator.synchronize_after_geometry_change(**args)
        assert cell.source_visibility == "full" and cell.review_state == "pending"
        # D-462 R6: the label survives as a suggestion; `blurry` described the
        # old pixels, and the old approval stays only as history.
        assert cell.assigned_symbol_id == symbol_id and cell.quality_issue is None
        assert cell.approved_crop_checksum_sha256 == old_approval
        _symbol_cell_review_from_model(cell, symbol_code_by_id={symbol_id: "cherry"})
        assert not coordinator.synchronize_for_backfill_reconciliation(**args)


def test_actual_legacy_mapper_accepts_sparse_real_crop_revision():
    from datetime import UTC, datetime

    from game_predictor_api.storage.image_review_repository import (
        materialize_current_image_review_cells,
    )

    missing = tuple(range(10, 15))
    board = SimpleNamespace(
        id=uuid4(),
        asset_mode="legacy_file",
        grid_rows=3,
        grid_columns=5,
        geometry_revision=1,
        geometry_qualification=GeometryQualification(
            "pending_partial",
            missing,
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=missing,
        ).to_dict(),
        source_image_id=uuid4(),
        board_geometry={},
        board_relative_path="source.png",
        board_checksum_sha256="a" * 64,
        sequence_number=62440,
        pipeline_fingerprint="test",
    )
    observations = [
        SimpleNamespace(
            id=uuid4(),
            row_index=i // 5,
            column_index=i % 5,
            crop_relative_path=f"crops/{i}.png",
            crop_checksum_sha256=f"{i:064x}",
            cropper_version="test",
            prediction={
                "symbolCode": "cherry",
                "confidence": 0.9,
                "alternatives": [{"symbolCode": "cherry", "confidence": 0.9}],
            },
        )
        for i in range(10)
    ]
    revision = SimpleNamespace(
        revision=1,
        cropper_version="test",
        crop_artifacts=[
            {
                "rowIndex": o.row_index,
                "columnIndex": o.column_index,
                "cropRelativePath": o.crop_relative_path,
                "cropChecksumSha256": o.crop_checksum_sha256,
            }
            for o in observations
        ],
    )
    item = SimpleNamespace(
        id=uuid4(),
        status="pending",
        resolved_value=None,
        resolved_by=None,
        resolved_at=None,
        resolution_revision=0,
        created_at=datetime.now(UTC),
    )
    source = SimpleNamespace(
        id=board.source_image_id,
        import_job_id=uuid4(),
        relative_path="source.png",
        checksum_sha256="b" * 64,
    )
    cells = materialize_current_image_review_cells(
        item=item,
        board=board,
        source=source,
        queue_item=SimpleNamespace(source_order_index=0, position_index=0),
        job=SimpleNamespace(game_id=uuid4()),
        observations=observations,
        geometry_revision=revision,
    )
    assert [cell.cell_index for cell in cells] == list(range(10))
    assert all(cell.crop_relative_path and cell.crop_checksum_sha256 for cell in cells)
