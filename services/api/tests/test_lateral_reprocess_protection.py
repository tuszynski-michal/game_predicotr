from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.storage import lateral_reprocess_protection as protection
from sqlalchemy.dialects import postgresql


def _job(enabled=True):
    return SimpleNamespace(
        id=uuid4(),
        game_id=uuid4(),
        input_payload={
            "image_geometry_rollout": {"lateralPartialGeometry": {}} if enabled else {},
        },
    )


def _owner():
    return (
        SimpleNamespace(id=uuid4(), resolution_revision=0),
        SimpleNamespace(
            approved_geometry_revision=None,
            geometry_engine_name="structured_opencv_v1",
            geometry_qualification=None,
            completeness_status="complete",
        ),
    )


def test_legacy_does_not_query_or_change_ownership():
    session = Mock()
    assert not protection.has_protected_lateral_owner(
        session, job=_job(False), sequence_number=1239, source_checksum_sha256="a" * 64
    )
    assert session.mock_calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved_geometry_revision", 0),
        ("geometry_engine_name", "manual_v1"),
        ("geometry_qualification", {"excludeFromGeometryTraining": True}),
        ("completeness_status", "pending_partial"),
    ],
)
def test_manual_change_committed_before_sequence_lock_is_respected(monkeypatch, field, value):
    review, board = _owner()
    session = Mock()
    session.execute.return_value.all.return_value = [(review, board)]
    session.scalar.return_value = None

    def acquire(*args, **kwargs):
        assert session.execute.call_count == 0
        # Simulate the editor committing while the worker waits for its sequence lock.
        setattr(board, field, value)

    monkeypatch.setattr(protection, "acquire_image_sequence_locks", acquire)
    assert protection.has_protected_lateral_owner(
        session, job=_job(), sequence_number=1239, source_checksum_sha256="a" * 64
    )
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql and "sequence_number" in sql
    session.add.assert_not_called()
    assert getattr(board, field) == value


@pytest.mark.parametrize("human_cell", [None, uuid4()])
def test_symbol_decision_protects_owner_but_unreviewed_auto_does_not(monkeypatch, human_cell):
    session = Mock()
    session.execute.return_value.all.return_value = [_owner()]
    session.scalar.return_value = human_cell
    monkeypatch.setattr(protection, "acquire_image_sequence_locks", Mock())
    assert protection.has_protected_lateral_owner(
        session, job=_job(), sequence_number=1, source_checksum_sha256="a" * 64
    ) == (human_cell is not None)
    sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "assignment_source" in sql and "review_state" in sql and "quality_issue" in sql
    session.add.assert_not_called()


def test_rejected_human_decision_is_protected_only_for_matching_source(monkeypatch):
    review, board = _owner()
    review.resolution_revision = 1
    session = Mock()
    session.execute.return_value.all.return_value = [(review, board)]
    monkeypatch.setattr(protection, "acquire_image_sequence_locks", Mock())
    assert protection.has_protected_lateral_owner(
        session, job=_job(), sequence_number=1, source_checksum_sha256="a" * 64
    )
    query = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "source_images.checksum_sha256" in str(query)
    assert "rejected" in query.params.values() and "a" * 64 in query.params.values()
