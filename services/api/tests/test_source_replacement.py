from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.source_replacement import (
    manifest_csv,
    preview_document,
    qualification,
)
from game_predictor_api.domain.symbol_readability import crop_identity
from game_predictor_api.main import create_app
from test_cleanup_api import FakeCleanupService


def test_decisive_chronology_ignores_run_age_and_pending():
    current = {"cell_id": "a", "source_id": "b", "quality_issue": "unreadable"}
    identity = crop_identity(current)
    decisions = [
        {"identity": identity, "state": "unreadable", "ordinal": 1, "run_id": "new"},
        {"identity": identity, "state": "readable", "ordinal": 2, "run_id": "old"},
        {"identity": identity, "state": "pending", "ordinal": 3, "run_id": "new"},
        {"identity": identity, "state": "skipped", "ordinal": 4, "run_id": "new"},
    ]
    assert qualification(current, decisions, [])["state"] == "readable"
    changed = {**current, "crop_checksum_sha256": "changed", "quality_issue": None}
    assert qualification(changed, decisions, [])["state"] is None


@pytest.mark.parametrize(
    "states,expected,blocked",
    [
        ([], "unreadable", False),
        (["readable"], "readable", False),
        (["unreadable", "readable"], None, True),
        (["unreadable"] * 2, "unreadable", False),
    ],
)
def test_legacy_requires_consensus_and_keeps_all_proofs(states, expected, blocked):
    current = {"cell_id": "cell", "quality_issue": "unreadable"}
    rows = [
        dict(
            run_id=str(i),
            state=state,
            identity=crop_identity(current),
            ever_labelled=True,
            revision=3,
        )
        for i, state in enumerate(states)
    ]
    result = qualification(current, [], rows)
    assert result["state"] == expected
    assert bool(result["blocker"]) == blocked
    assert len(result["proof"]) == len(rows)


def test_preview_binds_exact_revision_not_only_counts_and_csv():
    entry = {
        "source_ids": ["source"],
        "source_sha256": "a" * 64,
        "boards": [dict(id="board", sequence_number=8, geometry_revision=1)],
        "sequence_numbers": [8, 9],
        "reasons": [],
    }
    before = preview_document("game", ["source"], [entry])
    entry["boards"][0]["geometry_revision"] = 2
    after = preview_document("game", ["source"], [entry])
    assert before["preview_token"] != after["preview_token"]
    assert ",8,board," in manifest_csv(after)
    assert ",9,,," in manifest_csv(after)
    assert not after["retirement_available"]


def test_existing_api_dispatches_new_mode_without_destructive_service():
    service = FakeCleanupService()
    source = uuid4()
    document = preview_document(str(service.game_id), [str(source)], [])

    class Plans:
        def preview(self, game, ids):
            assert game == service.game_id and ids == [source]
            return document

        def create(self, game, request):
            assert request.expected_revision == 0
            return {**document, "id": str(uuid4()), "status": "planned", "revision": 1}

    service.replacement_plans = Plans()
    with TestClient(
        create_app(ApiSettings.from_environment({}), cleanup_service_dependency=lambda: service)
    ) as client:
        prefix = f"/api/v1/admin/games/{service.game_id}"
        response = client.post(
            prefix + "/board-source-cleanup-preview",
            json={"mode": "replace_preserve_history", "sourceIds": [str(source)]},
        )
        assert response.status_code == 200, response.text
        command = dict(
            mode="replace_preserve_history",
            sourceIds=[str(source)],
            previewToken=response.json()["previewToken"],
            expectedRevision=0,
            idempotencyKey=str(uuid4()),
        )
        saved = client.post(prefix + "/board-sources", json=command)
        assert saved.status_code == 200 and saved.json()["status"] == "planned"
        forbidden = client.request("DELETE", prefix + "/board-sources", json=command)
        assert forbidden.status_code == 409
        assert forbidden.json()["code"] == "SOURCE_REPLACEMENT_RETIREMENT_NOT_READY"
        assert service.last_command is None


@pytest.mark.parametrize("state", ["pending", "skipped"])
def test_non_decisive_command_keeps_unordered_pre_ledger_proofs(state):
    current = {"cell_id": "cell", "quality_issue": "unreadable"}
    identity = crop_identity(current)
    readable = dict(
        run_id="r1", revision=7, state="readable", identity=identity, ever_labelled=True
    )
    unreadable = {**readable, "run_id": "r2", "state": "unreadable"}
    decisions = [dict(identity=identity, state=state, ordinal=1, prior_quality_judgment=readable)]
    result = qualification(current, decisions, [])
    assert result["state"] == "readable" and result["proof"] == [readable]
    result = qualification(current, decisions, [unreadable])
    assert result["blocker"] == "SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS"
    assert result["state"] is None and len(result["proof"]) == 2
    # Capturing the contradictory legacy state later does not make it newer.
    decisions.append(
        dict(identity=identity, state=state, ordinal=2, prior_quality_judgment=unreadable)
    )
    assert (
        qualification(current, decisions, [])["blocker"] == "SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS"
    )
    changed = {**current, "crop_checksum_sha256": "new-pixels", "quality_issue": None}
    assert qualification(changed, decisions, [unreadable])["state"] is None
    decisions.append(dict(identity=identity, state="readable", ordinal=3))
    assert qualification(current, decisions, [unreadable])["state"] == "readable"


def test_default_cleanup_dependency_preserves_empty_body_422_and_skips_recovery_for_plan(
    monkeypatch,
):
    import importlib
    from unittest.mock import MagicMock

    main = importlib.import_module("game_predictor_api.main")
    storage = importlib.import_module("game_predictor_api.storage.source_replacement")
    session = MagicMock()
    session.__enter__.return_value = session
    repository = MagicMock()
    repository.completed_board_source_quarantine_keys.return_value = ()
    artifacts = MagicMock()
    monkeypatch.setattr(main, "create_session_factory", lambda engine: lambda: session)
    monkeypatch.setattr(main, "SqlAlchemyCleanupRepository", lambda *args: repository)
    monkeypatch.setattr(main, "ManagedCleanupArtifactStore", lambda root, **kwargs: artifacts)
    game, source = uuid4(), uuid4()
    plans = MagicMock()
    plans.preview.return_value = preview_document(str(game), [str(source)], [])
    monkeypatch.setattr(storage, "SourceReplacementRepository", lambda session: plans)
    with TestClient(create_app(ApiSettings.from_environment({}))) as client:
        prefix = f"/api/v1/admin/games/{game}"
        for method, path in [
            ("POST", "/board-source-cleanup-preview"),
            ("DELETE", "/board-sources"),
        ]:
            response = client.request(method, prefix + path)
            assert response.status_code == 422, response.text
        assert artifacts.recover.call_count == 2
        response = client.post(
            prefix + "/board-source-cleanup-preview",
            json={"mode": "replace_preserve_history", "sourceIds": [str(source)]},
        )
        assert response.status_code == 200, response.text
        assert artifacts.recover.call_count == 2
