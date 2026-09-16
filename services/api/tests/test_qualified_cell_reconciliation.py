"""In-memory transaction boundary regressions; never connect to operator data."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_reviews import ImageReviewCell
from game_predictor_api.domain.image_symbol_reviews import approve_symbol_cell_review
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    _apply_symbol_cell_review_transition,
    _symbol_cell_review_from_model,
)
from game_predictor_api.storage.models import (
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
)


def _cells(revision, missing):
    return tuple(
        ImageReviewCell(
            observation_id=uuid4(),
            cell_index=index,
            row_index=index // 5,
            column_index=index % 5,
            crop_sample_id=f"{1000 + revision * 100 + index:064x}",
            crop_checksum_sha256=f"{2000 + revision * 100 + index:064x}",
            crop_relative_path=f"crops/{revision}-{index}.jpg",
            predicted_symbol_code="cherry",
            current_symbol_code="cherry",
            confidence=0.9,
            alternatives=(),
        )
        for index in range(15)
        if index not in missing
    )


def test_qualified_reconciliation_keeps_ids_history_and_never_transfers_pixel_approval():
    game_id, review_id, board_id, symbol_id = (uuid4() for _ in range(4))
    rows, events = [], []
    session = Mock()
    session.scalars.side_effect = lambda _query: tuple(rows)
    session.execute.return_value = [(symbol_id, "cherry")]

    def add(value):
        if isinstance(value, ImageSymbolReviewCellModel):
            value.id = uuid4()
            rows.append(value)
        elif isinstance(value, ImageSymbolReviewEventModel):
            events.append(value)
        else:
            raise AssertionError(type(value))

    session.add.side_effect = add
    board = SimpleNamespace(
        id=board_id,
        grid_rows=3,
        grid_columns=5,
        sequence_number=1,
        geometry_revision=0,
        geometry_qualification=None,
        unavailable_cell_indices=[],
        completeness_status="complete",
    )
    coordinator = SymbolCellReviewWriteThroughCoordinator(session)
    coordinator._state_if_initialized = Mock(return_value=SimpleNamespace(failure_message=None))
    coordinator._touch_catalog_revision = Mock()
    coordinator._review_row = Mock(
        return_value=(
            SimpleNamespace(id=review_id, status="pending", resolved_value=None),
            board,
            SimpleNamespace(import_job_id=uuid4()),
            Mock(),
            Mock(),
        )
    )
    coordinator._current_cells = Mock(return_value=(_cells(0, ()), "cropper-v1", None, None))
    assert coordinator.synchronize_after_prediction_refresh(
        game_id=game_id, review_item_id=review_id
    )
    original_ids = [row.id for row in rows]
    for row in rows:
        approved = approve_symbol_cell_review(
            _symbol_cell_review_from_model(row, symbol_code_by_id={symbol_id: "cherry"}),
            active_symbol_codes=("cherry",),
        ).review
        _apply_symbol_cell_review_transition(
            row, review=approved, symbol_id_by_code={"cherry": symbol_id}, actor="operator"
        )
    frozen = [
        (row.id, row.approved_crop_checksum_sha256, row.approved_geometry_revision) for row in rows
    ]

    for revision, missing in enumerate(((0,), tuple(range(15)), (1,)), start=1):
        board.geometry_revision = revision
        board.completeness_status = "pending_partial"
        board.unavailable_cell_indices = list(missing)
        board.geometry_qualification = GeometryQualification(
            "pending_partial", missing, True, "missing_pixels"
        ).to_dict()
        coordinator._current_cells.return_value = (
            _cells(revision, missing),
            "cropper-v1",
            None,
            None,
        )
        assert coordinator.synchronize_after_geometry_change(
            game_id=game_id, review_item_id=review_id
        )
        assert len(rows) == 15 and [row.id for row in rows] == original_ids
        assert [row.cell_index for row in rows if row.source_available] == [
            i for i in range(15) if i not in missing
        ]
        assert [
            (row.id, row.approved_crop_checksum_sha256, row.approved_geometry_revision)
            for row in rows
        ] == frozen
        assert all(
            row.review_state == "pending" and row.geometry_revision == revision
            for row in rows
            if row.source_available
        )
        event_count = len(events)
        assert not coordinator.synchronize_for_backfill_reconciliation(
            game_id=game_id, review_item_id=review_id
        )
        assert len(events) == event_count
    # No SQL DELETE or FK row replacement is used by any qualified transition.
    assert all("DELETE" not in str(call.args[0]).upper() for call in session.execute.call_args_list)
