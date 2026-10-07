"""Bulk creation must flush board references before taking catalog state."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkExplicitTarget,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
)
from game_predictor_api.storage import image_symbol_review_bulk_operation_repository as bulk


def _request():
    return SymbolCellReviewBulkRequest(
        action=SymbolCellReviewAction.REASSIGN,
        target_symbol_id=uuid4(),
        explicit_targets=(
            SymbolCellReviewBulkExplicitTarget(
                cell_review_id=uuid4(),
                expected_revision=1,
                expected_geometry_revision=1,
                expected_crop_sample_id="a" * 64,
                expected_crop_checksum_sha256="b" * 64,
            ),
        ),
        filter_selection=None,
        actor="local-admin",
    )


@pytest.mark.parametrize("late_conflict", [False, True])
def test_start_flushes_references_then_revalidates_before_return(monkeypatch, late_conflict):
    events = []
    session = MagicMock()
    session.scalar.return_value = None
    session.flush.side_effect = lambda: events.append("flush-targets")
    request = _request()
    state = SimpleNamespace(catalog_revision=1)

    def ready(_session, *, game_id, for_update):
        events.append("lock-state" if for_update else "read-state")
        return state

    monkeypatch.setattr(bulk, "_require_ready_state", ready)
    monkeypatch.setattr(bulk, "_require_active_symbols", lambda *_a, **_k: None)
    monkeypatch.setattr(bulk, "_operation_from_model", lambda model: model)
    monkeypatch.setattr(bulk.SqlAlchemyJobRepository, "add_job", lambda _self, job: job)
    repository = bulk.SqlAlchemySymbolCellReviewBulkOperationRepository(session)

    def counts(**_kwargs):
        events.append("validate")
        if late_conflict and "lock-state" in events:
            raise SymbolCellReviewError("SYMBOL_CELL_REVIEW_BULK_TARGET_STALE", "Changed.")
        return 1, 1

    monkeypatch.setattr(repository, "_preview_counts", counts)
    target = request.explicit_targets[0]
    monkeypatch.setattr(
        repository,
        "_snapshot_explicit_targets",
        lambda **_kwargs: (
            bulk._FrozenTarget(
                cell_review_id=target.cell_review_id,
                review_item_id=uuid4(),
                recognized_board_id=uuid4(),
                sequence_number=1,
                cell_index=0,
                expected_revision=1,
                expected_geometry_revision=1,
                expected_crop_sample_id="a" * 64,
                expected_crop_checksum_sha256="b" * 64,
            ),
        ),
    )
    if late_conflict:
        with pytest.raises(SymbolCellReviewError, match="Changed"):
            repository.start(game_id=uuid4(), request=request, idempotency_key=uuid4())
    else:
        operation, created = repository.start(
            game_id=uuid4(), request=request, idempotency_key=uuid4()
        )
        assert created and operation.target_count == 1
    assert events == ["read-state", "validate", "flush-targets", "lock-state", "validate"]
    session.commit.assert_not_called()


def test_locked_state_and_target_reads_refresh_identity_map(monkeypatch):
    session = MagicMock()
    session.get.return_value = SimpleNamespace()
    session.scalar.return_value = SimpleNamespace(status="ready", catalog_revision=2)
    monkeypatch.setattr(bulk, "symbol_cell_review_projection_is_available", lambda *_a, **_k: True)
    bulk._require_ready_state(session, game_id=uuid4(), for_update=True)
    statement = session.scalar.call_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    assert statement._for_update_arg is not None

    monkeypatch.setattr(bulk, "_bind_game_store", lambda *_a: None)
    session.scalars.return_value = []
    repository = bulk.SqlAlchemySymbolCellReviewBulkOperationRepository(session)
    with pytest.raises(SymbolCellReviewError):
        repository._snapshot_explicit_targets(game_id=uuid4(), request=_request())
    assert session.scalars.call_args.args[0].get_execution_options()["populate_existing"] is True


def test_idempotent_replay_does_not_wait_on_catalog_lock(monkeypatch):
    session = MagicMock()
    request = _request()
    existing = SimpleNamespace(command_sha256=request.command_sha256)
    session.scalar.return_value = existing
    ready = MagicMock(return_value=SimpleNamespace(status="ready"))
    monkeypatch.setattr(bulk, "_require_ready_state", ready)
    monkeypatch.setattr(bulk, "_operation_from_model", lambda model: model)
    repository = bulk.SqlAlchemySymbolCellReviewBulkOperationRepository(session)
    game_id = uuid4()
    operation, created = repository.start(game_id=game_id, request=request, idempotency_key=uuid4())
    assert operation is existing and created is False
    ready.assert_called_once_with(session, game_id=game_id, for_update=False)
    session.flush.assert_not_called()
