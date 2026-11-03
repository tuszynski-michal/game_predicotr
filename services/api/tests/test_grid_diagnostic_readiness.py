from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage import grid_diagnostic_readiness as readiness

GAME = UUID(int=10)


def capture(source, labels):
    return {
        "sourceId": str(source),
        "source": {"checksum_sha256": "a" * 64, "normalized_pixel_checksum_sha256": "b" * 64},
        "captureSha256": "c" * 64,
        "positions": [
            {
                "label": {} if i < labels else None,
                "reason": None if i < labels else "HUMAN_APPROVAL_REQUIRED",
            }
            for i in range(9)
        ],
    }


@pytest.mark.parametrize("labels,full", [(0, False), (8, False), (9, True)])
def test_only_nine_qualified_labels_make_a_full_photo(labels, full):
    result = readiness.summarize_capture(capture(UUID(int=1), labels))
    assert result["fullyHumanAnnotated"] is full
    assert result["qualifiedHumanBoards"] == labels
    assert result["screenEligible"] is None
    assert result["usedForModelDesign"] is False


@pytest.fixture
def storage(monkeypatch):
    engine, connection, session = MagicMock(), MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    session.__enter__.return_value = session
    monkeypatch.setattr(readiness, "Session", lambda bind: session)
    monkeypatch.setattr(readiness.event, "listen", MagicMock())
    monkeypatch.setattr(readiness.event, "remove", MagicMock())
    router = MagicMock()
    monkeypatch.setattr(readiness, "GameStorageRouter", lambda: router)
    reader = MagicMock()
    reader.capture.side_effect = lambda game, source, ordinal, recording, mode: capture(source, 8)
    monkeypatch.setattr(readiness, "GridCohortEvidenceReader", lambda *args: reader)
    return SimpleNamespace(engine=engine, session=session, reader=reader, router=router)


def test_explicit_budget_has_cursor_without_claiming_full_population(storage, tmp_path):
    storage.session.execute.return_value.mappings.return_value = [
        {"source_image_id": UUID(int=i), "nominal_boards": 8} for i in (1, 2)
    ]
    result = readiness.read_readiness(storage.engine, GAME, tmp_path, max_sources=1)
    assert result["status"] == "partial" and not result["populationComplete"]
    assert result["nextSourceId"] == str(UUID(int=1))
    assert result["nominalHumanBoards"] == 8 and result["qualifiedHumanBoards"] == 8
    assert result["diagnosticUse"] == []
    assert storage.reader.capture.call_count == 1
    assert storage.reader.capture.call_args.args[3]["role"] is None
    assert storage.reader.capture.call_args.args[3]["qualification"] == "unresolved"
    sql = [str(call.args[0]) for call in storage.session.execute.call_args_list]
    assert "READ ONLY" in sql[0]
    storage.session.commit.assert_not_called()
    storage.session.rollback.assert_called_once()


def test_continuation_and_increased_budget_remain_explicit(storage, tmp_path):
    storage.session.execute.return_value.mappings.return_value = []
    result = readiness.read_readiness(
        storage.engine, GAME, tmp_path, max_sources=1000, after_source_id=UUID(int=7)
    )
    assert result["budget"]["maxSources"] == 1000
    assert result["status"] == "partial" and result["pageComplete"]
    assert not result["populationComplete"] and result["nextSourceId"] is None


def test_reader_failure_does_not_return_partial_success(storage, tmp_path):
    storage.session.execute.return_value.mappings.return_value = [
        {"source_image_id": UUID(int=1), "nominal_boards": 8}
    ]
    storage.reader.capture.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        readiness.read_readiness(storage.engine, GAME, tmp_path)
    storage.session.rollback.assert_called_once()


def test_budget_validation_precedes_connection(storage, tmp_path):
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        readiness.read_readiness(storage.engine, GAME, tmp_path, max_sources=0)
    storage.engine.connect.assert_not_called()


def test_retired_source_is_reported_and_cursor_advances_even_if_entire_page_rejected(
    storage, tmp_path
):
    storage.session.execute.return_value.mappings.return_value = [
        {"source_image_id": UUID(int=i), "nominal_boards": 8} for i in (1, 2)
    ]

    def read(game, source, ordinal, recording, mode):
        if source == UUID(int=1):
            raise GridCohortError("SOURCE_REPLACEMENT_RETIRED", "retired")
        return capture(source, 8)

    storage.reader.capture.side_effect = read
    first = readiness.read_readiness(storage.engine, GAME, tmp_path, max_sources=1)
    assert first["nextSourceId"] == str(UUID(int=1))
    assert first["sourceCount"] == 0 and first["selectedSourceCount"] == 1
    assert not first["populationComplete"] and first["nominalHumanBoards"] == 8
    result = readiness.read_readiness(storage.engine, GAME, tmp_path, max_sources=2)
    assert result["populationComplete"] and result["selectedSourceCount"] == 2
    assert result["sourceCount"] == 1 and result["nominalHumanBoards"] == 16
    assert result["qualifiedHumanBoards"] == 8
    assert result["rejectedSources"] == [
        {
            "sourceId": str(UUID(int=1)),
            "code": "SOURCE_REPLACEMENT_RETIRED",
            "nominalHumanBoards": 8,
        }
    ]


def test_unknown_domain_failure_is_not_reclassified_as_source_rejection(storage, tmp_path):
    storage.session.execute.return_value.mappings.return_value = [
        {"source_image_id": UUID(int=1), "nominal_boards": 8}
    ]
    storage.reader.capture.side_effect = GridCohortError("OTHER_INTEGRITY_FAILURE", "broken")
    with pytest.raises(GridCohortError, match="broken"):
        readiness.read_readiness(storage.engine, GAME, tmp_path)


def test_actual_listener_sets_remaining_timeout_and_rejects_expired_deadline(
    storage, monkeypatch, tmp_path
):
    clock = {"now": 0.0}
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock["now"])
    cursor = MagicMock()

    def route(*args, **kwargs):
        listener = readiness.event.listen.call_args.args[2]
        listener(None, cursor, "SELECT 1", None, None, False)
        cursor.execute.assert_called_with("SET LOCAL statement_timeout=8000")
        clock["now"] = 59.0
        listener(None, cursor, "SELECT 1", None, None, False)
        cursor.execute.assert_called_with("SET LOCAL statement_timeout=1000")
        clock["now"] = 60.0
        listener(None, cursor, "SELECT 1", None, None, False)

    storage.router.bind.side_effect = route
    with pytest.raises(TimeoutError, match="BUDGET_EXHAUSTED"):
        readiness.read_readiness(storage.engine, GAME, tmp_path)
    assert cursor.execute.call_count == 2
    storage.session.rollback.assert_called_once()
    readiness.event.remove.assert_called_once()


def test_deadline_expiring_during_capture_cannot_publish_success(storage, monkeypatch, tmp_path):
    clock = {"now": 0.0}
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock["now"])
    storage.session.execute.return_value.mappings.return_value = [
        {"source_image_id": UUID(int=1), "nominal_boards": 8}
    ]

    def late_capture(game, source, ordinal, recording, mode):
        clock["now"] = 61.0
        return capture(source, 8)

    storage.reader.capture.side_effect = late_capture
    with pytest.raises(TimeoutError, match="BUDGET_EXHAUSTED"):
        readiness.read_readiness(storage.engine, GAME, tmp_path)
    storage.session.rollback.assert_called_once()
