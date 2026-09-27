"""Bounded operator commands report skipped blockers and resume count cursors."""

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from game_predictor_api.domain.partial_board_reconciliation import (
    PILOT_GAME_ID,
    PILOT_SEQUENCES,
    blocked_board,
    build_manifest,
    digest,
)
from game_predictor_api.storage.partial_board_reconciliation_repository import (
    PartialBoardReconciliationRepository,
)


def _ready(number):
    guard = {"sequence_number": number}
    return {
        "sequenceNumber": number,
        "status": "ready",
        "guard": guard,
        "guardSha256": digest(guard),
        "sourceVisibility": ["full"] * 15,
    }


def _cli():
    path = Path(__file__).resolve().parents[3] / "scripts/reconcile_partial_board_symbol_review.py"
    spec = importlib.util.spec_from_file_location("partial_reconciliation_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("ready_count", [0, 1, 8])
def test_apply_reports_all_blockers_and_limits_new_attempts(tmp_path, monkeypatch, ready_count):
    module = _cli()
    manifest = build_manifest(
        game_id=PILOT_GAME_ID,
        storage_generation=2,
        boards=[
            _ready(number)
            if index < ready_count
            else blocked_board(number, "OWNER", "Missing owner")
            for index, number in enumerate(PILOT_SEQUENCES)
        ],
    )
    path, output = tmp_path / "preview.json", tmp_path / "result.json"
    path.write_text(json.dumps(manifest), encoding="utf8")
    monkeypatch.setattr(
        module,
        "arguments",
        lambda: SimpleNamespace(
            command="apply",
            source_root=[tmp_path],
            preview=path,
            output=output,
            preview_sha256=manifest["previewSha256"],
            after_sequence=0,
            limit=5,
        ),
    )
    engine, sessions = Mock(), Mock()
    sessions.begin.side_effect = lambda: nullcontext(Mock())
    monkeypatch.setattr(module, "create_database_engine", lambda *_: engine)
    monkeypatch.setattr(module, "create_session_factory", lambda *_: sessions)
    calls = []

    class Repository:
        def __init__(self, *args, **kwargs):
            pass

        def apply_board(self, preview, number):
            calls.append(number)
            return {"sequenceNumber": number, "replayed": False}

    monkeypatch.setattr(module, "PartialBoardReconciliationRepository", Repository)
    assert module.main() == 2
    report = json.loads(output.read_text(encoding="utf8"))
    assert len(report["skippedBlocked"]) == 70 - ready_count
    assert report["skippedBlocked"][0]["code"] == "OWNER"
    assert calls == list(PILOT_SEQUENCES[: min(5, ready_count)])
    assert sessions.begin.call_count == min(5, ready_count)


def test_count_batch_resumes_persisted_cursor_without_start_or_reset(monkeypatch):
    manifest = build_manifest(
        game_id=PILOT_GAME_ID,
        storage_generation=2,
        boards=[_ready(number) for number in PILOT_SEQUENCES],
    )
    state = SimpleNamespace(
        status="rebuilding",
        count_projection_status="rebuilding",
        count_projection={},
        count_rebuild_cursor="saved-before-restart",
    )
    session = Mock()
    session.get.return_value = state
    repository = PartialBoardReconciliationRepository(session, source_roots=[])
    repository.router = Mock()
    repository._execute = Mock()
    repository._execute.return_value.all.return_value = [
        (row["sequenceNumber"], row["guardSha256"]) for row in manifest["boards"]
    ]
    rebuild = Mock()
    rebuild.rebuild_count_projection_next_batch.return_value = False
    monkeypatch.setattr(
        "game_predictor_api.storage.partial_board_reconciliation_repository.SqlAlchemyImageSymbolReviewRepository",
        lambda *_: rebuild,
    )
    result = repository.rebuild_counts_batch(manifest, batch_size=17)
    assert result == {"complete": False, "scannedBatch": True, "cursor": "saved-before-restart"}
    rebuild.start_count_rebuild.assert_not_called()
    rebuild.rebuild_count_projection_next_batch.assert_called_once_with(
        PILOT_GAME_ID, batch_size=17
    )


def test_ready_current_counts_do_not_scan_again(monkeypatch):
    manifest = build_manifest(
        game_id=PILOT_GAME_ID,
        storage_generation=2,
        boards=[_ready(number) for number in PILOT_SEQUENCES],
    )
    session = Mock()
    session.get.return_value = SimpleNamespace(
        status="ready",
        count_projection_status="ready",
        count_projection={"_semantics": {"version": 2}},
    )
    repository = PartialBoardReconciliationRepository(session, source_roots=[])
    repository.router = Mock()
    repository._execute = Mock()
    repository._execute.return_value.all.return_value = [
        (row["sequenceNumber"], row["guardSha256"]) for row in manifest["boards"]
    ]
    assert repository.rebuild_counts_batch(manifest)["scannedBatch"] is False
    session.get.return_value.status = "failed"
    with pytest.raises(ValueError, match="not ready"):
        repository.rebuild_counts_batch(manifest)
