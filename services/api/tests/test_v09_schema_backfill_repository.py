from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_symbol_reviews import approve_symbol_cell_review
from game_predictor_api.storage.image_symbol_review_repository import (
    _apply_symbol_cell_review_transition,
    _symbol_cell_review_from_model,
)
from game_predictor_api.storage.v09_schema_backfill_repository import (
    SqlAlchemyV09SchemaBackfillRepository,
    V09SchemaBackfillError,
)


def _sha(seed: int) -> str:
    return f"{seed:064x}"


def _board(*, geometry_revision: int = 0):
    return SimpleNamespace(
        id=uuid4(),
        grid_rows=None,
        grid_columns=None,
        geometry_revision=geometry_revision,
        approved_geometry_revision=None,
        geometry_approved_at=None,
        geometry_approved_by=None,
    )


def _cell(*, approved: bool, grid_issue: bool = False):
    return SimpleNamespace(
        has_grid_issue=grid_issue,
        quality_issue=None,
        review_state="approved" if approved else "pending",
        crop_sample_id=_sha(1),
        crop_checksum_sha256=_sha(2),
        geometry_revision=3,
        approved_crop_sample_id=None,
        approved_crop_checksum_sha256=None,
        approved_geometry_revision=None,
    )


def test_backfill_accepted_board_sets_topology_geometry_and_crop_provenance() -> None:
    session = MagicMock()
    approved = _cell(approved=True)
    grid_issue = _cell(approved=False, grid_issue=True)
    session.scalars.return_value.all.return_value = [approved, grid_issue]
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    board = _board(geometry_revision=3)
    resolved_at = datetime(2026, 8, 28, tzinfo=UTC)
    review_item = SimpleNamespace(
        status="corrected",
        resolved_by="owner",
        resolved_at=resolved_at,
    )

    changed, updated_cells = repository._backfill_board(
        game_id=uuid4(),
        board=board,
        review_item=review_item,
        topology=BoardTopology(rows=3, columns=5),
    )

    assert changed is True
    assert updated_cells == 2
    assert (board.grid_rows, board.grid_columns) == (3, 5)
    assert board.approved_geometry_revision == 3
    assert board.geometry_approved_by == "owner"
    assert approved.approved_crop_sample_id == approved.crop_sample_id
    assert approved.approved_crop_checksum_sha256 == approved.crop_checksum_sha256
    assert approved.approved_geometry_revision == approved.geometry_revision
    assert grid_issue.quality_issue == "grid_issue"

    changed_again, cells_again = repository._backfill_board(
        game_id=uuid4(),
        board=board,
        review_item=review_item,
        topology=BoardTopology(rows=3, columns=5),
    )

    assert changed_again is False
    assert cells_again == 0


def test_pipeline_pending_board_remains_unapproved() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = [_cell(approved=False)]
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    board = _board()

    changed, _updated_cells = repository._backfill_board(
        game_id=uuid4(),
        board=board,
        review_item=SimpleNamespace(status="pending", resolved_by=None, resolved_at=None),
        topology=BoardTopology(rows=3, columns=5),
    )

    assert changed is True
    assert board.approved_geometry_revision is None
    assert board.geometry_approved_by is None


def test_batch_preloads_cells_and_geometry_with_constant_query_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    game_id = uuid4()
    topology = BoardTopology(rows=3, columns=5)
    first = _board()
    second = _board()
    pending = SimpleNamespace(status="pending", resolved_by=None, resolved_at=None)
    session.execute.return_value.tuples.return_value = [(first, pending), (second, pending)]
    session.scalars.side_effect = [[], []]
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    monkeypatch.setattr(
        repository,
        "pin_existing_game_topology",
        MagicMock(return_value=(uuid4(), topology)),
    )

    step = repository.backfill_next_batch(game_id, batch_size=2)

    assert step.processed_board_count == 2
    assert step.updated_board_count == 2
    assert step.has_more is False
    assert session.scalars.call_count == 2


def test_manual_geometry_revision_is_approved_from_unambiguous_audit() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    corrected_at = datetime(2026, 8, 28, tzinfo=UTC)
    session.scalar.return_value = SimpleNamespace(
        corrected_by="operator",
        created_at=corrected_at,
    )
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    board = _board(geometry_revision=2)

    repository._backfill_board(
        game_id=uuid4(),
        board=board,
        review_item=SimpleNamespace(status="pending", resolved_by=None, resolved_at=None),
        topology=BoardTopology(rows=3, columns=5),
    )

    assert board.approved_geometry_revision == 2
    assert board.geometry_approved_at == corrected_at
    assert board.geometry_approved_by == "operator"


def test_conflicting_existing_topology_is_reported_without_repair() -> None:
    session = MagicMock()
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    board = _board()
    board.grid_rows = 2
    board.grid_columns = 4

    with pytest.raises(V09SchemaBackfillError) as error:
        repository._backfill_board(
            game_id=uuid4(),
            board=board,
            review_item=None,
            topology=BoardTopology(rows=3, columns=5),
        )

    assert error.value.code == "IMAGE_BOARD_TOPOLOGY_INCONSISTENT"
    assert (board.grid_rows, board.grid_columns) == (2, 4)


def test_pin_uses_latest_matching_rules_and_retry_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    game_id = uuid4()
    rules_id = uuid4()
    game = SimpleNamespace(id=game_id, board_topology_rules_version_id=None)
    rules = SimpleNamespace(id=rules_id, game_id=game_id, rows=3, columns=5)
    session.scalar.side_effect = [game, rules]
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    monkeypatch.setattr(repository, "_board_count", MagicMock(return_value=10))
    monkeypatch.setattr(
        repository,
        "_observed_legacy_topology",
        MagicMock(return_value=BoardTopology(rows=3, columns=5)),
    )

    selected_rules_id, topology = repository.pin_existing_game_topology(game_id)

    assert selected_rules_id == rules_id
    assert topology == BoardTopology(rows=3, columns=5)
    assert game.board_topology_rules_version_id == rules_id
    session.flush.assert_called_once()

    session.reset_mock()
    session.scalar.side_effect = [game]
    session.get.return_value = rules
    selected_again, topology_again = repository.pin_existing_game_topology(game_id)

    assert selected_again == rules_id
    assert topology_again == topology
    session.flush.assert_not_called()


def test_pin_fails_when_no_rules_version_matches_existing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    game_id = uuid4()
    session.scalar.side_effect = [
        SimpleNamespace(id=game_id, board_topology_rules_version_id=None),
        None,
    ]
    repository = SqlAlchemyV09SchemaBackfillRepository(session)
    monkeypatch.setattr(repository, "_board_count", MagicMock(return_value=1))
    monkeypatch.setattr(
        repository,
        "_observed_legacy_topology",
        MagicMock(return_value=BoardTopology(rows=3, columns=5)),
    )

    with pytest.raises(V09SchemaBackfillError) as error:
        repository.pin_existing_game_topology(game_id)

    assert error.value.code == "GAME_BOARD_TOPOLOGY_RULES_MISMATCH"


def test_symbol_review_dual_reads_legacy_grid_and_writes_v09_provenance() -> None:
    symbol_id = uuid4()
    cell = SimpleNamespace(
        id=uuid4(),
        cell_index=4,
        crop_sample_id=_sha(11),
        crop_relative_path="crops/cell-4.jpg",
        crop_checksum_sha256=_sha(12),
        geometry_revision=2,
        cropper_version="board-cell-crops-v18",
        prediction_symbol_code="cherries",
        assigned_symbol_id=symbol_id,
        review_state="pending",
        has_grid_issue=True,
        quality_issue=None,
        assignment_source="human",
        revision=5,
        approved_crop_sample_id=None,
        approved_crop_checksum_sha256=None,
        approved_geometry_revision=None,
        last_reviewed_by=None,
    )

    legacy_review = _symbol_cell_review_from_model(
        cell,
        symbol_code_by_id={symbol_id: "cherries"},
    )

    assert legacy_review.has_grid_issue is True
    assert legacy_review.quality_issue is not None
    assert legacy_review.quality_issue.value == "grid_issue"

    transition = approve_symbol_cell_review(
        legacy_review,
        active_symbol_codes=("cherries",),
    )
    _apply_symbol_cell_review_transition(
        cell,
        review=transition.review,
        symbol_id_by_code={"cherries": symbol_id},
        actor="operator",
    )

    assert cell.has_grid_issue is False
    assert cell.quality_issue is None
    assert cell.approved_crop_sample_id == cell.crop_sample_id
    assert cell.approved_crop_checksum_sha256 == cell.crop_checksum_sha256
    assert cell.approved_geometry_revision == cell.geometry_revision
    assert cell.last_reviewed_by == "operator"
