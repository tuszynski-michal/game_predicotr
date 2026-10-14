from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobType, checkpoint_job, create_job, start_job
from game_predictor_api.storage.board_render_manifest_reader import CurrentBoardRenderManifest
from game_predictor_worker.images.pending_symbol_reinference import (
    PendingSymbolReinferenceHandler,
    _available_indices,
    _checkpoint_payload,
    _resume_cursor,
    _virtual_records,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from sqlalchemy.dialects import postgresql


def test_explicit_reinference_includes_qualified_pending_from_completed_import(tmp_path):
    session = MagicMock()
    session.execute.return_value.tuples.return_value.all.return_value = []
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    assert handler._pending_rows(uuid4()) == []
    query = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "geometry_qualification IS NOT NULL" in query
    assert "completed" in query and "waiting_for_review" in query
    assert "image_symbol_review_cells.review_state = 'pending'" in query
    assert "image_review_items.status IN ('pending', 'accepted', 'corrected')" in query
    assert "image_board_search_fast_documents" not in query


def test_pending_symbol_checkpoint_uses_the_runtime_schema() -> None:
    payload = _checkpoint_payload(processed=7, skipped=2)

    assert payload == {
        "schema_version": 1,
        "kind": "pending-symbol-reinference-v1",
        "processed": 7,
        "skippedConcurrentResolution": 2,
    }


def _claimed_job(*, current=0, succeeded=0, total=None, payload=None):
    now = datetime.now(UTC)
    job = create_job(
        JobType.IMAGE_SYMBOL_REINFERENCE,
        game_id=uuid4(),
        input_payload={"schema_version": 1},
    )
    job = start_job(
        job,
        worker_version="test",
        worker_id="test",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(minutes=5),
    )
    return replace(
        job,
        progress_current=current,
        success_count=succeeded,
        progress_total=total,
        checkpoint_payload=payload,
    )


class _DurableContext:
    def __init__(self, job, *, lose_response=False):
        self.job = job
        self.lose_response = lose_response

    def checkpoint(self, **values):
        self.job = checkpoint_job(self.job, lease_token=self.job.lease_token, **values)
        if self.lose_response:
            raise ConnectionError("checkpoint committed; response lost")


def _mock_handler(tmp_path, monkeypatch, rows):
    import game_predictor_worker.images.pending_symbol_reinference as module

    monkeypatch.setattr(module, "_snapshot_from_payload", lambda _: MagicMock())
    monkeypatch.setattr(module, "_model_path", lambda *args: tmp_path / "model.onnx")
    monkeypatch.setattr(module, "LocalSymbolOnnxAdapter", MagicMock())
    monkeypatch.setattr(module, "symbol_onnx_variant_arguments", lambda _: {})
    session = MagicMock()
    session.scalar.side_effect = lambda query: SimpleNamespace(
        id=uuid4(), geometry_revision=0, geometry_qualification=None
    )
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    monkeypatch.setattr(handler, "_pending_rows", lambda _: rows)
    infer = MagicMock(return_value=([], "a" * 64))
    monkeypatch.setattr(handler, "_infer_board", infer)
    return handler, infer, session


def _rows(count):
    from uuid import UUID

    return [
        (
            SimpleNamespace(id=UUID(int=i + 1), created_at=datetime(2026, 10, 13, tzinfo=UTC)),
            SimpleNamespace(
                id=uuid4(),
                geometry_revision=0,
                geometry_qualification=None,
                asset_mode="virtual_source",
            ),
            SimpleNamespace(id=UUID(int=1), import_job_id=uuid4()),
        )
        for i in range(count)
    ]


def test_restart_after_lost_checkpoint_response_skips_committed_prefix(tmp_path, monkeypatch):
    rows = _rows(3)
    handler, infer, session = _mock_handler(tmp_path, monkeypatch, rows)
    context = _DurableContext(_claimed_job(), lose_response=True)
    with pytest.raises(ConnectionError):
        handler(context, context.job)
    assert context.job.progress_current == 1
    assert _resume_cursor(context.job.checkpoint_payload) is not None
    context = _DurableContext(context.job)
    # An earlier row disappearing must not shift a positional resume offset.
    monkeypatch.setattr(handler, "_pending_rows", lambda _: rows[1:])
    handler(context, context.job)
    assert context.job.progress_current == context.job.progress_total == 3
    assert context.job.success_count == 3
    assert infer.call_count == 3
    # All revisions already existed; retry must not create duplicates.
    session.add.assert_not_called()


@pytest.mark.parametrize("remaining", [0, 1, 3])
def test_legacy_retry_retains_high_water_counters(tmp_path, monkeypatch, remaining):
    handler, _, _ = _mock_handler(tmp_path, monkeypatch, _rows(remaining))
    context = _DurableContext(
        _claimed_job(
            current=2,
            succeeded=2,
            total=3,
            payload=_checkpoint_payload(processed=2, skipped=0),
        )
    )
    handler(context, context.job)
    assert context.job.progress_current == max(2, remaining)
    assert context.job.success_count == max(2, remaining)
    assert context.job.progress_total == 3


def test_cursor_retry_with_no_remaining_rows_retains_totals(tmp_path, monkeypatch):
    row = _rows(1)[0]
    cursor = (row[2].id, row[0].created_at, row[0].id)
    handler, infer, _ = _mock_handler(tmp_path, monkeypatch, [row])
    context = _DurableContext(
        _claimed_job(
            current=7,
            succeeded=5,
            total=10,
            payload=_checkpoint_payload(processed=5, skipped=2, cursor=cursor),
        )
    )
    handler(context, context.job)
    assert context.job.progress_current == 7
    assert context.job.success_count == 5
    assert context.job.progress_total == 10
    infer.assert_not_called()


def test_prediction_committed_before_checkpoint_loss_is_replayed_idempotently(
    tmp_path, monkeypatch
):
    rows = _rows(2)
    handler, infer, session = _mock_handler(tmp_path, monkeypatch, rows)
    job = _claimed_job()
    lost = MagicMock()
    lost.checkpoint.side_effect = ConnectionError("response lost before checkpoint commit")
    with pytest.raises(ConnectionError):
        handler(lost, job)
    context = _DurableContext(job)
    handler(context, job)
    assert context.job.progress_current == context.job.success_count == 2
    assert infer.call_count == 3
    session.add.assert_not_called()


def test_cursor_resume_preserves_previous_skips_on_concurrent_geometry_change(
    tmp_path, monkeypatch
):
    rows = _rows(2)
    first = rows[0]
    cursor = (first[2].id, first[0].created_at, first[0].id)
    handler, infer, session = _mock_handler(tmp_path, monkeypatch, rows)
    session.scalar.side_effect = [
        SimpleNamespace(),
        SimpleNamespace(geometry_revision=1, geometry_qualification=None),
    ]
    job = _claimed_job(
        current=2,
        succeeded=1,
        total=3,
        payload=_checkpoint_payload(processed=1, skipped=1, cursor=cursor),
    )
    context = _DurableContext(job)
    handler(context, job)
    assert context.job.progress_current == 3
    assert context.job.success_count == 1
    assert context.job.checkpoint_payload["skippedConcurrentResolution"] == 2
    assert infer.call_count == 1
    session.add.assert_not_called()


def test_cursor_without_timezone_is_refused():
    with pytest.raises(JobHandlerError):
        _resume_cursor(
            {
                "kind": "pending-symbol-reinference-v2",
                "cursor": [str(uuid4()), "2026-10-13T12:00:00", str(uuid4())],
            }
        )


def test_invalid_resume_cursor_is_refused(tmp_path, monkeypatch):
    handler, infer, session = _mock_handler(tmp_path, monkeypatch, [])
    job = _claimed_job(payload={"kind": "pending-symbol-reinference-v2", "cursor": ["bad"]})
    with pytest.raises(JobHandlerError) as error:
        handler(_DurableContext(job), job)
    assert error.value.code == "IMAGE_SYMBOL_REINFERENCE_CHECKPOINT_INVALID"
    infer.assert_not_called()
    session.add.assert_not_called()


def test_qualified_reinference_keeps_empty_slot_without_fake_records():
    qualification = GeometryQualification(
        "pending_partial", tuple(range(15)), True, "missing_pixels"
    )
    indices = _available_indices(qualification.to_dict())
    assert indices == ()
    # TASK-0757 rule: a board without renderable cells has no manifest.
    assert _virtual_records(render_manifest=None, expected_indices=indices) == []
    with pytest.raises(JobHandlerError):
        _virtual_records(render_manifest=None)


def test_qualified_reinference_rejects_wrong_positions_with_same_count():
    cells = [
        {
            "cellIndex": i,
            "renderSpec": {"rowIndex": i // 5, "columnIndex": i % 5},
            "logicalCellKeySha256": "a" * 64,
            "logicalCellKeyV2Sha256": "b" * 64,
            "renderedPixelChecksumSha256": "c" * 64,
            "renderSpecChecksumSha256": "d" * 64,
            "extractorVersion": "renderer",
        }
        for i in range(1, 15)
    ]
    manifest = _manifest(cells)
    assert (
        len(_virtual_records(render_manifest=manifest, expected_indices=tuple(range(1, 15)))) == 14
    )
    with pytest.raises(JobHandlerError):
        _virtual_records(render_manifest=manifest, expected_indices=tuple(range(14)))


def test_non_virtual_board_is_refused_without_reading_records(tmp_path):
    """D-467 S6 (TASK-0796): only ``virtual_source`` boards have cells to re-infer."""

    factory = MagicMock()
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    with pytest.raises(JobHandlerError) as error:
        handler._infer_board(
            uuid4(),
            0,
            source=MagicMock(),
            snapshot=MagicMock(),
            adapter=MagicMock(),
            source_loader=MagicMock(),
            asset_mode="none",
            game_id=uuid4(),
        )
    assert error.value.code == "IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED"
    factory.assert_not_called()


def _manifest(cells, *, extractor_version="renderer"):
    return CurrentBoardRenderManifest(
        recognized_board_id=uuid4(),
        geometry_revision=2,
        source_geometry_revision_id=uuid4(),
        extractor_version=extractor_version,
        manifest_checksum_sha256="e" * 64,
        cells=tuple(cells),
    )
