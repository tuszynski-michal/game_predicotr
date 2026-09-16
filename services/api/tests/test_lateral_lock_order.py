"""Exercise transaction entrypoints, not just the ownership helper in isolation."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from game_predictor_api.storage import lateral_reprocess_protection as protection
from game_predictor_api.storage import virtual_grid_geometry_repository as editor
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.pending_sequence_ownership import (
    create_owned_pending_review_item,
)
from game_predictor_worker.images import pipeline_store as worker
from game_predictor_worker.images.board_cell_geometry_deferred_writer import (
    BoardCellGeometryDeferredWriter,
)
from sqlalchemy.dialects import postgresql


class StopAtLock(RuntimeError):
    pass


def _session():
    session = MagicMock()
    session.__enter__.return_value = session
    return session


def test_worker_mixed_protected_and_auto_locks_all_sequences_before_source_and_state(monkeypatch):
    events = []
    session = _session()
    job = NS(
        id=uuid4(),
        game_id=uuid4(),
        input_payload={"image_geometry_rollout": {"lateralPartialGeometry": {}}},
    )
    source = NS(id=uuid4(), checksum_sha256="a" * 64)
    session.get.return_value = job
    candidate = NS(
        execution=NS(
            file_execution_key="e" * 64,
            source_checksum_sha256="a" * 64,
            pipeline_fingerprint="b" * 64,
        )
    )
    monkeypatch.setattr(
        worker, "_execution_context", lambda _: (job.id, uuid4(), datetime.now(UTC))
    )
    monkeypatch.setattr(worker, "_require_candidate_lease", lambda *a, **kw: events.append("lease"))
    monkeypatch.setattr(
        protection,
        "acquire_image_sequence_locks",
        lambda *a, **kw: events.append(("sequence", tuple(sorted(kw["sequence_numbers"])))),
    )

    def scalar(query):
        sql = str(query.compile(dialect=postgresql.dialect()))
        if "FROM source_images" in sql:
            assert "FOR UPDATE" in sql
            events.append("source")
            return source
        return None

    session.scalar.side_effect = scalar
    protected = (NS(id=uuid4(), resolution_revision=1), NS(approved_geometry_revision=1))
    session.execute.return_value.all.side_effect = [[protected], []]
    monkeypatch.setattr(worker, "_recognized_board_geometry", lambda **kw: {})
    monkeypatch.setattr(worker, "require_matching_symbol_cells", Mock())
    review_id = uuid4()
    monkeypatch.setattr(
        worker,
        "_upsert_review_item",
        lambda *a, **kw: (NS(id=review_id, status="pending"), {review_id}),
    )
    monkeypatch.setattr(worker, "_pending_board_geometry_count", lambda *a, **kw: 0)
    monkeypatch.setattr(worker, "_append_prediction_revision", Mock())
    monkeypatch.setattr(worker, "SqlAlchemyBoardSearchProjectionRepository", Mock())
    coordinator = Mock()
    coordinator.synchronize_after_prediction_refresh.side_effect = lambda **kw: events.append(
        "state"
    )
    monkeypatch.setattr(worker, "SymbolCellReviewWriteThroughCoordinator", lambda _: coordinator)
    boards = [{"positionIndex": index, "confidence": 0.99} for index in range(2)]
    crops = [
        {
            **board,
            "cells": [],
            "boardRelativePath": "board.jpg",
            "boardChecksumSha256": "c" * 64,
            "cropperVersion": "test",
        }
        for board in boards
    ]
    sequences = [
        {**board, "normalizedNumber": index + 1, "rawText": str(index + 1)}
        for index, board in enumerate(boards)
    ]
    stages = {
        "board_detection": NS(payload={"boards": boards}),
        "board_crops": NS(payload={"boards": crops}),
        "sequence_ocr": NS(payload={"boards": sequences}),
        "symbol_inference": NS(
            payload={
                "boards": [{**b, "cells": []} for b in boards],
                "modelVersion": "test",
                "inferenceMode": "unclassified",
            }
        ),
    }
    worker.SqlAlchemyImagePipelineStore(lambda: session).project_recognition(
        candidate, stage_results=stages
    )
    assert events[:3] == ["lease", ("sequence", (1, 2)), "source"]
    assert events[-1] == "state"
    created = [call.args[0] for call in session.add.call_args_list]
    assert len(created) == 1 and created[0].position_index == 1


def test_editor_entrypoint_reserves_sequence_before_source_row_query(monkeypatch):
    events = []
    session = Mock()
    context = NS(
        game_id=uuid4(),
        import_job_id=uuid4(),
        sequence_number=1,
        position_index=0,
        pending_geometry_id=None,
        review_item_id=uuid4(),
    )
    prepared = NS(entries=[NS(context=context, command=NS(geometry_qualification=None))])
    monkeypatch.setattr(
        editor, "acquire_image_sequence_locks", lambda *a, **kw: events.append("sequence")
    )

    def execute(query):
        sql = str(query.compile(dialect=postgresql.dialect()))
        assert "source_images" in sql and "FOR UPDATE" in sql
        events.append("source")
        raise StopAtLock

    session.execute.side_effect = execute
    with pytest.raises(StopAtLock):
        editor.SqlAlchemyVirtualGridGeometryRepository(
            session
        ).save_virtual_source_geometry_revision(
            prepared=prepared, idempotency_key=uuid4(), created_at=datetime.now(UTC)
        )
    assert events == ["sequence", "source"]


def test_symbol_mutation_locks_board_before_shared_state():
    events = []
    repository = SqlAlchemySymbolCellReviewMutationRepository(Mock())
    command = NS(game_id=uuid4(), cell_review_id=uuid4(), action="approve", target_symbol_id=None)
    repository._probe_board_cells = lambda _: [NS(review_item_id=uuid4(), sequence_number=1)]
    repository._acquire_board_locks = lambda **kw: events.append("sequence")
    repository._locked_current_rows = lambda _: events.append("source") or []

    def state(_):
        events.append("state")
        raise StopAtLock

    repository._require_ready_state = state
    with pytest.raises(StopAtLock):
        repository.apply_board_mutations((command,))
    assert events == ["sequence", "source", "state"]


def test_deferred_writer_acquires_sequence_before_pending_source_lock(monkeypatch):
    events = []
    session = _session()
    job = NS(
        game_id=uuid4(), input_payload={"image_geometry_rollout": {"lateralPartialGeometry": {}}}
    )
    context = NS(
        job_id=uuid4(),
        file_execution_key="e" * 64,
        source_checksum_sha256="a" * 64,
        source_relative_path="seq_1-9.jpg",
        pipeline_fingerprint="b" * 64,
    )
    source = NS(id=uuid4())
    session.get.return_value = job

    def scalar(query):
        sql = str(query.compile(dialect=postgresql.dialect()))
        if "FROM source_images" in sql:
            if "FOR UPDATE" in sql:
                events.append("source")
                raise StopAtLock
            return source
        return None

    session.scalar.side_effect = scalar
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(
        protection, "acquire_image_sequence_locks", lambda *a, **kw: events.append("sequence")
    )
    store = Mock()
    store.write.return_value = "manifest.json"
    with pytest.raises(StopAtLock):
        BoardCellGeometryDeferredWriter(lambda: session, store).defer(
            context,
            position_index=0,
            sequence_number=1,
            reason_code="estimator_rejected",
            processing_snapshot={
                "estimatorVersion": "test",
                "estimatorFingerprintSha256": "c" * 64,
                "cropperVersion": "test",
                "cropperFingerprintSha256": "d" * 64,
            },
        )
    assert events == ["sequence", "source"]


def test_pending_owner_does_not_lock_immutable_incumbent_job(monkeypatch):
    session = Mock()
    game_id = uuid4()
    import_job = NS(id=uuid4(), created_at=datetime.now(UTC))
    board = NS(id=uuid4(), sequence_number=1)
    session.scalar.return_value = None
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(
        "game_predictor_api.storage.pending_sequence_ownership.acquire_image_sequence_locks",
        Mock(),
    )

    create_owned_pending_review_item(
        session,
        board=board,
        game_id=game_id,
        import_job=import_job,
        snapshot={},
        created_at=datetime.now(UTC),
    )

    query = session.execute.call_args.args[0]
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF image_review_items, recognized_boards" in sql
    assert "FOR UPDATE OF jobs" not in sql
