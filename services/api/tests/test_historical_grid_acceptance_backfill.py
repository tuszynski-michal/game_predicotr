"""Bounded preparation and explicit command contract, without operator data."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_reviews import create_image_reviews_router
from game_predictor_api.application.grid_engine_acceptance import HistoricalAcceptanceReport
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.schemas.grid_engine_acceptance import HistoricalAcceptanceConfirmCommand
from game_predictor_api.storage import historical_grid_evidence as evidence
from pydantic import ValidationError


def manifest(tmp_path: Path, *, count: int = 3):
    game_id, selection_id = str(uuid4()), str(uuid4())
    entries = {
        str(index): {
            "status": "review_required",
            "neuralProposal": {"name": "Żółć 🐈", "index": index},
            "neuralProposalBinding": {"index": index},
        }
        for index in range(count)
    }
    raw = json.dumps(
        {
            "gameId": game_id,
            "sourceSelectionId": selection_id,
            "entries": entries,
            "sourceManifestChecksumSha256": "f" * 64,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    (tmp_path / "data").mkdir()
    path = tmp_path / "data" / "manifest.json"
    path.write_bytes(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    payload = {
        "source_selection_id": selection_id,
        "source_manifest_sha256": "f" * 64,
        "page_geometry_manifest": {
            "relativePath": "data/manifest.json",
            "checksumSha256": checksum,
        },
    }
    return game_id, payload, path, checksum


def test_index_resumes_at_utf8_entry_boundary_and_publishes_after_sha(tmp_path, monkeypatch):
    game, payload, _path, checksum = manifest(tmp_path)
    monkeypatch.setattr(evidence, "MAX_ENTRIES_PER_STEP", 1)
    monkeypatch.setattr(evidence, "_CHUNK", 17)
    ready = tmp_path / "data" / "historical-grid-acceptance-index" / f"{checksum}.sqlite"
    # Each invocation creates a fresh parser and SQLite connection, like a cold process.
    for _ in range(4):
        with pytest.raises(evidence.HistoricalEvidenceUnavailable, match="PREPARING"):
            evidence.original_neural_evidence(tmp_path, payload, game_id=game, source_sha256="2")
        assert not ready.exists()
    proposal, binding = evidence.original_neural_evidence(
        tmp_path, payload, game_id=game, source_sha256="2"
    )
    assert proposal == {"name": "Żółć 🐈", "index": 2}
    assert binding == {"index": 2}
    assert ready.exists()
    monkeypatch.setattr(
        evidence, "_prepare_index", lambda *_: pytest.fail("Warm read must not scan again")
    )
    assert (
        evidence.original_neural_evidence(tmp_path, payload, game_id=game, source_sha256="0")[0][
            "index"
        ]
        == 0
    )


def test_failed_sha_never_publishes_partial_index_and_run_never_rebuilds(tmp_path):
    game, payload, path, checksum = manifest(tmp_path)
    path.write_bytes(path.read_bytes().replace("Żółć".encode(), "Łódź".encode()))
    with pytest.raises(evidence.HistoricalEvidenceUnavailable, match="PREPARING"):
        evidence.original_neural_evidence(tmp_path, payload, game_id=game, source_sha256="0")
    with pytest.raises(evidence.HistoricalEvidenceUnavailable, match="PROVENANCE_DRIFT"):
        evidence.original_neural_evidence(tmp_path, payload, game_id=game, source_sha256="0")
    assert not (
        tmp_path / "data" / "historical-grid-acceptance-index" / f"{checksum}.sqlite"
    ).exists()
    with pytest.raises(evidence.HistoricalEvidenceUnavailable, match="INDEX_UNAVAILABLE"):
        evidence.original_neural_evidence(
            tmp_path, payload, game_id=game, source_sha256="0", build=False
        )


def test_confirmation_requires_explicit_true():
    with pytest.raises(ValidationError):
        HistoricalAcceptanceConfirmCommand.model_validate(
            {"idempotencyKey": str(uuid4()), "confirmed": False}
        )


def test_existing_router_transports_frozen_operation_commands(tmp_path):
    game, operation, key = uuid4(), uuid4(), uuid4()
    calls = []
    report = HistoricalAcceptanceReport(
        game_id=game,
        operation_id=operation,
        phase="previewed",
        preparation_state=None,
        started_at=datetime.now(UTC),
        preview_cursor=1,
        run_cursor=0,
        source_count=1,
        revision_count=1,
        eligible_count=1,
        accepted_count=0,
        skipped_count=0,
        preview_reasons={},
        run_reasons={},
        items=(),
        next_item_cursor=None,
    )

    class RecordingService:
        def __getattr__(self, name):
            def invoke(*args):
                calls.append((name, args))
                return report

            return invoke

    service = SimpleNamespace(historical_acceptance=RecordingService())
    app = FastAPI()
    app.include_router(
        create_image_reviews_router(lambda: service, tmp_path, lambda: None, lambda: None)
    )
    client = TestClient(app)
    base = f"/admin/image-review-items/geometry-completeness/{game}/historical-acceptance"
    assert client.post(base, json={"idempotencyKey": str(key)}).status_code == 200
    assert (
        client.post(f"{base}/{operation}/preview-next", json={"expectedCursor": 0}).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/{operation}/confirm", json={"idempotencyKey": str(key), "confirmed": False}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/{operation}/confirm", json={"idempotencyKey": str(key), "confirmed": True}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/{operation}/run-next", json={"idempotencyKey": str(key), "expectedCursor": 0}
        ).status_code
        == 200
    )
    response = client.get(f"{base}/{operation}?afterOrdinal=25")
    assert response.status_code == 200
    assert response.json()["statusOnly"] is True
    assert response.json()["materializesNewCells"] is False
    assert calls == [
        ("create", (game, key)),
        ("preview_next", (game, operation, 0)),
        ("confirm", (game, operation, key)),
        ("run_next", (game, operation, 0, key)),
        ("report", (game, operation, 25)),
    ]


@pytest.mark.parametrize(
    "profile",
    [
        GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1,
        GameShapeGeometryConfiguration.GRID_PROFILE_777_V2,
    ],
)
def test_original_registered_versions_of_both_games_remain_pinned(profile):
    registered = grid_engine_profile_for(profile)
    for original in registered.versions:
        payload = NeuralGridSnapshot.for_game(500000, original).to_payload()
        replay = NeuralGridSnapshot.from_payload(payload)
        assert replay.version == original
        assert replay.to_payload() == payload
