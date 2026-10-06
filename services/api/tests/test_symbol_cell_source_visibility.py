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


def test_exact_lattice_interior_boundary_overrides_interpolated_outline():
    nodes = [{"x": 10 + column * 15, "y": 10 + row * 25} for row in range(4) for column in range(6)]
    nodes[2]["y"] = -5
    visibility = current_source_visibilities(
        geometry={"latticeBoundsQuad": _quad(10, 10, 85, 85), "latticeNodes": nodes},
        width=100,
        height=100,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
    )
    assert visibility == ("full", "partial", "partial") + ("full",) * 12


@pytest.mark.parametrize("nodes", [[], [{"x": 1, "y": 1}] * 24, "invalid"])
def test_invalid_current_lattice_never_falls_back_to_outline(nodes):
    with pytest.raises(ValueError):
        current_source_visibilities(
            geometry={"latticeBoundsQuad": _quad(10, 10, 85, 85), "latticeNodes": nodes},
            width=100,
            height=100,
            topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"geometry_engine_name": "neural_grid_v1"},
        {"approved_geometry_revision": 0},
        {"geometry_approved_by": None},
        {"geometry_approved_at": None},
        {"geometry_revision": 0},
        {"board_geometry": {"neuralProposalChecksumSha256": "a" * 64}},
    ],
)
def test_only_current_human_manual_lattice_can_cross_the_incomplete_source_gate(change):
    from game_predictor_api.storage.image_geometry_completeness_state_repository import (
        _manual_neural_lattice_approved,
    )

    nodes = [{"x": column * 10, "y": row * 10} for row in range(4) for column in range(6)]
    board = SimpleNamespace(
        asset_mode="virtual_source",
        geometry_engine_name="manual_v1",
        geometry_revision=1,
        approved_geometry_revision=1,
        geometry_approved_by="reviewer-operator",
        geometry_approved_at="now",
        board_geometry={"latticeNodes": nodes, "neuralProposalChecksumSha256": "a" * 64},
    )
    assert _manual_neural_lattice_approved(board)
    for key, value in change.items():
        setattr(board, key, value)
    assert not _manual_neural_lattice_approved(board)


def _coordinator(monkeypatch, *, asset_mode="virtual_source"):
    monkeypatch.setattr(
        "game_predictor_api.storage.image_symbol_review_repository._bind_game_store",
        lambda *_: None,
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
        import_job_id=uuid4(),
        width=100,
        height=100,
        oriented_width=100,
        oriented_height=100,
        geometry_completeness_status=None,
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


@pytest.mark.parametrize(
    "allow,status,failure,expected",
    [
        (True, "rebuilding", None, True),
        (False, "rebuilding", None, False),
        (True, "failed", None, False),
        (True, "rebuilding", "bad crop", False),
    ],
)
def test_manual_correction_keeps_global_readiness_fence(
    monkeypatch, allow, status, failure, expected
):
    from game_predictor_api.storage.image_symbol_review_repository import (
        SqlAlchemySymbolCellReviewMutationRepository,
    )
    from game_predictor_api.storage.models import GameModel

    monkeypatch.setattr(
        "game_predictor_api.storage.image_symbol_review_repository.symbol_cell_review_projection_is_available",
        lambda *_args, **_kwargs: False,
    )
    nodes = [{"x": column * 10, "y": row * 10} for row in range(4) for column in range(6)]
    board = SimpleNamespace(
        asset_mode="virtual_source",
        geometry_engine_name="manual_v1",
        geometry_revision=1,
        approved_geometry_revision=1,
        geometry_approved_by="reviewer-operator",
        geometry_approved_at="now",
        board_geometry={"latticeNodes": nodes, "neuralProposalChecksumSha256": "a" * 64},
    )
    state = SimpleNamespace(status=status, failure_message=failure)
    session = Mock()
    session.get.side_effect = (
        lambda model, *_args, **_kwargs: object() if model is GameModel else state
    )
    repository = SqlAlchemySymbolCellReviewMutationRepository(
        session,
        allow_current_manual_neural_board=allow,
    )
    if expected:
        assert repository._require_ready_state(uuid4(), current_board=board) is state
    else:
        with pytest.raises(SymbolCellReviewError) as error:
            repository._require_ready_state(uuid4(), current_board=board)
        assert error.value.code == "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE"
    assert state.status == status  # Never claim that game-wide backfill completed.


# D-467 S6 (TASK-0796): every board is ``virtual_source``.
@pytest.mark.parametrize("asset_mode", ["virtual_source"])
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


def test_mapper_refuses_a_non_virtual_board():
    """D-467 S6 (TASK-0796): the file-crop mapper is gone; no silent fallback."""

    from game_predictor_api.domain.image_reviews import ImageReviewConflictError
    from game_predictor_api.storage.current_board_cell_sources import NO_CELL_SOURCES
    from game_predictor_api.storage.image_review_repository import (
        materialize_current_image_review_cells,
    )

    board = SimpleNamespace(id=uuid4(), asset_mode="legacy_file", geometry_revision=1)
    with pytest.raises(ImageReviewConflictError) as refused:
        materialize_current_image_review_cells(
            item=SimpleNamespace(resolved_value=None),
            board=board,
            cell_sources=NO_CELL_SOURCES,
        )
    assert refused.value.code == "IMAGE_REVIEW_ASSET_MODE_UNSUPPORTED"
