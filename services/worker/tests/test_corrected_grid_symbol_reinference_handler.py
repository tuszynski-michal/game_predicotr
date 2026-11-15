from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_worker.images.pending_symbol_reinference import (
    PendingSymbolReinferenceHandler,
    _corrected_grid_targets,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from sqlalchemy.dialects import postgresql
from test_pending_symbol_reinference import (
    _claimed_job,
    _DurableContext,
    _mock_handler,
    _rows,
)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        [{"review_item_id": "bad", "geometry_revision": 2}],
        [{"review_item_id": str(uuid4()), "geometry_revision": True}],
    ],
)
def test_invalid_scope_never_expands_to_entire_game(raw):
    with pytest.raises(JobHandlerError) as error:
        _corrected_grid_targets({"corrected_grid_targets": raw})
    assert error.value.code == "IMAGE_SYMBOL_REINFERENCE_SCOPE_INVALID"


def test_old_jobs_keep_the_global_scope():
    assert _corrected_grid_targets({"schema_version": 1}) is None


def test_scoped_worker_query_binds_the_saved_revision(tmp_path):
    session, factory = MagicMock(), MagicMock()
    session.execute.return_value.tuples.return_value.all.return_value = []
    factory.return_value.__enter__.return_value = session
    item = uuid4()
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    assert handler._pending_rows(uuid4(), corrected_grid_targets=((item, 4),)) == []
    query = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(item) in query
    assert "recognized_boards.geometry_revision) IN" in query
    assert "image_board_geometry_revisions" in query
    assert "source_available IS true" in query


def _scoped_handler(tmp_path, monkeypatch, *, rows=2):
    import game_predictor_worker.images.pending_symbol_reinference as module

    # These tests isolate inference/retry; source guard SQL is tested by the selector.
    monkeypatch.setattr(module, "require_current_review", lambda *args: None)
    current_rows = _rows(rows)
    for _, board, _ in current_rows:
        board.geometry_revision = 2
    handler, infer, session = _mock_handler(tmp_path, monkeypatch, current_rows)
    targets = [{"review_item_id": str(row[0].id), "geometry_revision": 2} for row in current_rows]
    job = replace(
        _claimed_job(), input_payload={"schema_version": 1, "corrected_grid_targets": targets}
    )
    selected_scopes = []

    def select_rows(game_id, *, corrected_grid_targets):
        selected_scopes.append(corrected_grid_targets)
        return current_rows

    monkeypatch.setattr(handler, "_pending_rows", select_rows)
    return handler, infer, session, job, selected_scopes


def test_frozen_scope_survives_lost_checkpoint_and_new_process_context(tmp_path, monkeypatch):
    from types import SimpleNamespace

    handler, infer, session, job, scopes = _scoped_handler(tmp_path, monkeypatch)
    session.scalar.side_effect = lambda *args: SimpleNamespace(
        geometry_revision=2, geometry_qualification=None
    )
    lost = _DurableContext(job, lose_response=True)
    with pytest.raises(ConnectionError):
        handler(lost, job)
    resumed = _DurableContext(lost.job)
    handler(resumed, resumed.job)
    assert scopes[0] == scopes[1] == _corrected_grid_targets(job.input_payload)
    assert infer.call_count == 2
    assert resumed.job.success_count == 2
    session.add.assert_not_called()  # existing model/crop receipts are reused


def test_geometry_changed_during_inference_is_skipped(tmp_path, monkeypatch):
    from types import SimpleNamespace

    handler, infer, session, job, _ = _scoped_handler(tmp_path, monkeypatch, rows=1)
    session.scalar.side_effect = [
        True,
        SimpleNamespace(),
        SimpleNamespace(geometry_revision=3, geometry_qualification=None),
    ]
    context = _DurableContext(job)
    handler(context, job)
    assert infer.call_count == 1
    assert context.job.success_count == 0
    assert context.job.checkpoint_payload["skippedConcurrentResolution"] == 1
    session.add.assert_not_called()


def test_source_replaced_during_inference_is_skipped(tmp_path, monkeypatch):
    handler, _, session, job, _ = _scoped_handler(tmp_path, monkeypatch, rows=1)
    session.scalar.side_effect = [False]
    context = _DurableContext(job)
    handler(context, job)
    assert context.job.success_count == 0
    assert context.job.checkpoint_payload["skippedConcurrentResolution"] == 1
    session.add.assert_not_called()


def test_snapshot_members_no_longer_eligible_count_as_skipped(tmp_path, monkeypatch):
    handler, infer, session, job, _ = _scoped_handler(tmp_path, monkeypatch, rows=1)
    monkeypatch.setattr(handler, "_pending_rows", lambda *args, **kwargs: [])
    context = _DurableContext(job)
    handler(context, job)
    assert context.job.progress_total == context.job.progress_current == 1
    assert context.job.success_count == 0
    assert context.job.checkpoint_payload["skippedConcurrentResolution"] == 1
    infer.assert_not_called()
    session.add.assert_not_called()


def test_retired_source_guard_is_a_skip_for_the_frozen_job(tmp_path, monkeypatch):
    import game_predictor_worker.images.pending_symbol_reinference as module
    from game_predictor_api.domain.source_replacement import SourceReplacementError

    handler, _, session, job, _ = _scoped_handler(tmp_path, monkeypatch, rows=1)
    session.scalar.side_effect = [True]

    def retired(*args):
        raise SourceReplacementError("SOURCE_REPLACEMENT_SOURCE_RETIRED", "retired")

    monkeypatch.setattr(module, "require_current_review", retired)
    context = _DurableContext(job)
    handler(context, job)
    assert context.job.success_count == 0
    assert context.job.checkpoint_payload["skippedConcurrentResolution"] == 1
    session.add.assert_not_called()
