"""Geometry command ordering and immutable replay, without operator data."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.storage import virtual_grid_geometry_repository as virtual
from game_predictor_api.storage.grid_geometry_approvals import (
    SqlAlchemyGridGeometryApprovalRepository,
)
from game_predictor_api.storage.grid_geometry_proposals import (
    SqlAlchemyGridGeometryProposalRepository,
)
from game_predictor_api.storage.image_geometry_v2_repository import (
    SqlAlchemyImageSourceGeometryRepository,
)


def retired(*args, **kwargs):
    raise SourceReplacementError("SOURCE_REPLACEMENT_RETIRED", "SOURCE_REPLACEMENT_RETIRED")


@pytest.mark.parametrize("source_batch", [False, True])
def test_manual_retired_refuses_before_context_rows_and_superseded_branch(
    monkeypatch, source_batch
):
    session = Mock()
    session.scalar.return_value = None
    session.scalars.return_value = []
    repository = virtual.SqlAlchemyVirtualGridGeometryRepository(session)
    repository._raise_if_reverted_correction = Mock()
    repository._current_row = Mock(side_effect=AssertionError("must not lock/read mutable context"))
    monkeypatch.setattr(virtual, "authorize_working_source", retired)
    context = SimpleNamespace(
        game_id=uuid4(),
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        sequence_number=10,
        position_index=0,
    )
    prepared = SimpleNamespace(context=context)
    operation = repository.save_virtual_geometry_revision
    if source_batch:
        prepared = SimpleNamespace(entries=(prepared,))
        operation = repository.save_virtual_source_geometry_revision
    with pytest.raises(SourceReplacementError, match="SOURCE_REPLACEMENT_RETIRED"):
        operation(prepared=prepared, idempotency_key=uuid4(), created_at=datetime.now(UTC))
    repository._current_row.assert_not_called()
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_manual_exact_source_replay_uses_immutable_revisions_before_retired(monkeypatch):
    session = Mock()
    board = uuid4()
    record = SimpleNamespace(recognized_board_id=board, command_sha256="a" * 64)
    session.scalars.return_value = [record]
    repository = virtual.SqlAlchemyVirtualGridGeometryRepository(session)
    repository._raise_if_reverted_correction = Mock()
    monkeypatch.setattr(virtual, "authorize_working_source", retired)
    receipt = object()
    monkeypatch.setattr(virtual, "_revision_from_model", lambda value: receipt)
    entry = SimpleNamespace(
        context=SimpleNamespace(
            game_id=uuid4(), recognized_board_id=board, sequence_number=10, position_index=0
        ),
        command=SimpleNamespace(command_sha256="a" * 64),
    )
    result = repository.save_virtual_source_geometry_revision(
        prepared=SimpleNamespace(entries=(entry,)),
        idempotency_key=uuid4(),
        created_at=datetime.now(UTC),
    )
    assert result.revisions == (receipt,) and result.created is False
    session.add.assert_not_called()
    entry.command.command_sha256 = "b" * 64
    with pytest.raises(Exception, match="another source command"):
        repository.save_virtual_source_geometry_revision(
            prepared=SimpleNamespace(entries=(entry,)),
            idempotency_key=uuid4(),
            created_at=datetime.now(UTC),
        )


def test_only_verified_working_source_bypasses_current_guard(monkeypatch):
    session = Mock()
    repository = virtual.SqlAlchemyVirtualGridGeometryRepository(session)
    context = SimpleNamespace(
        game_id=uuid4(),
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        sequence_number=11,
        review_item_id=uuid4(),
    )
    binding = Mock(side_effect=SourceReplacementError("SOURCE_REPLACEMENT_RESERVED", "reserved"))
    monkeypatch.setattr(virtual, "require_sequence_binding", binding)
    monkeypatch.setattr(virtual, "authorize_working_source", lambda *args, **kwargs: None)
    with pytest.raises(SourceReplacementError):
        repository._require_working_geometry(context)
    monkeypatch.setattr(
        virtual,
        "authorize_working_source",
        lambda *args, **kwargs: SimpleNamespace(sequences=(11, 12)),
    )
    repository._require_working_geometry(context)
    assert binding.call_count == 1
    context.sequence_number = 13
    with pytest.raises(SourceReplacementError):
        repository._require_working_geometry(context)


def test_source_geometry_retired_precedes_payload_validation_and_row_lock(monkeypatch):
    from game_predictor_api.storage import source_replacement_guards

    monkeypatch.setattr(source_replacement_guards, "require_active_source", retired)
    session = Mock()
    repository = SqlAlchemyImageSourceGeometryRepository(session)
    repository._validate_input = Mock(side_effect=AssertionError("must not validate first"))
    with pytest.raises(SourceReplacementError):
        repository.append(SimpleNamespace(game_id=uuid4(), source_image_id=uuid4()))
    repository._validate_input.assert_not_called()
    session.add.assert_not_called()


def test_approval_retired_precedes_measurement_validation_but_exact_receipt_replays(
    monkeypatch, tmp_path
):
    from game_predictor_api.storage import grid_geometry_approvals as approvals

    session = Mock()
    session.get.return_value = None
    repository = SqlAlchemyGridGeometryApprovalRepository(session, tmp_path)
    repository.measurements = Mock()
    monkeypatch.setattr(approvals, "require_current_review", retired)
    game, job, review, key = uuid4(), uuid4(), uuid4(), uuid4()
    command = {"idempotencyKey": str(key)}
    with pytest.raises(SourceReplacementError):
        repository.approve(game, job, review, command, "actor")
    repository.measurements.header.assert_not_called()
    sha = approvals.digest(
        {"game": str(game), "job": str(job), "review": str(review), "command": command}
    )
    session.get.return_value = SimpleNamespace(
        command_sha256=sha,
        import_job_id=job,
        review_item_id=review,
        document={"receipt": {"ok": 1}},
    )
    assert repository.approve(game, job, review, command, "actor") == {"receipt": {"ok": 1}}


def test_proposal_retired_precedes_proposal_cas_without_mutating_it(monkeypatch, tmp_path):
    from game_predictor_api.storage import grid_geometry_proposals as proposals

    session = Mock()
    session.scalar.return_value = None
    repository = SqlAlchemyGridGeometryProposalRepository(session, tmp_path)
    repository.reinference = Mock()
    repository.geometry_repository = Mock()
    monkeypatch.setattr(proposals, "require_current_review", retired)
    with pytest.raises(SourceReplacementError):
        repository.command(
            uuid4(), uuid4(), uuid4(), uuid4(), "reject", {"idempotencyKey": str(uuid4())}, "actor"
        )
    repository.geometry_repository._ensure_projection_state.assert_not_called()
    session.add.assert_not_called()


def test_only_existing_receipt_reads_history_without_fast_document(monkeypatch):
    from test_virtual_grid_geometry_repository import _complete_current_virtual_row

    stored = _complete_current_virtual_row(backfill_status="complete")
    stored[1].sequence_number = stored[5].sequence_number
    row = (*stored[:5], None)  # current search projection removed by retirement
    session = Mock()
    session.scalar.return_value = uuid4()  # immutable revision exists for exact key
    session.execute.return_value.one_or_none.return_value = row
    repository = virtual.SqlAlchemyVirtualGridGeometryRepository(session)
    repository._context_from_row = lambda value: value
    monkeypatch.setattr(virtual, "admitted_source", retired)
    game, job, review = uuid4(), uuid4(), uuid4()
    result = repository.virtual_geometry_context(
        game_id=game,
        import_job_id=job,
        review_item_id=review,
        pending_geometry_id=None,
        replay_key=uuid4(),
    )
    assert result[:5] == stored[:5]
    assert result[5].sequence_number == stored[1].sequence_number
    session.add.assert_not_called()
    session.flush.assert_not_called()
    session.scalar.side_effect = [None, uuid4()]  # new key, then actual source lookup
    with pytest.raises(SourceReplacementError):
        repository.virtual_geometry_context(
            game_id=game,
            import_job_id=job,
            review_item_id=review,
            pending_geometry_id=None,
            replay_key=uuid4(),
        )
