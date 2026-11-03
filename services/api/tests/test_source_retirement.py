"""Typed HTTP boundaries and canonical-free prior preservation."""

import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.source_replacement_retirement import (
    retirement_resolved_value,
    scope_digest,
)
from game_predictor_api.main import create_app
from game_predictor_api.schemas.source_replacement import SourceReplacementRequestExport
from test_cleanup_api import FakeCleanupService


def test_prior_is_complete_and_operational_revision_is_not_scope():
    prior = {
        "sequence_number": 12,
        "resolved_value": {"nested": [1, {"previous": "decision"}]},
        "revision": 6,
    }
    result = retirement_resolved_value(prior, batch="batch", entry="entry", source_sha256="a" * 64)
    assert result["previous"] == prior
    assert "canonicalReviewItemId" not in result
    assert scope_digest(
        {"id": "entry", "phase": "planned", "revision": 1, "boards": [prior]}
    ) == scope_digest({"id": "entry", "phase": "gap_open", "revision": 2, "boards": [prior]})
    assert scope_digest({"boards": [prior]}) != scope_digest({"boards": [{**prior, "revision": 7}]})


def test_export_fixture_and_retirement_command_use_one_http_contract():
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "packages/admin-api-client/test/fixtures/source-replacement-request-v1.json"
        ).read_text(encoding="utf-8")
    )
    parsed = SourceReplacementRequestExport.model_validate(fixture)
    assert parsed.model_dump(mode="json", by_alias=True) == fixture
    service = FakeCleanupService()
    plans = MagicMock()
    plans.replacement_request.return_value = fixture
    plans.retirement_command.return_value = {
        "game_id": fixture["gameId"],
        "batch_id": fixture["batchId"],
        "entry_id": fixture["entries"][0]["entryId"],
        "revision": 2,
        "phase": "gap_open",
        "scope_digest": fixture["entries"][0]["digest"],
        "createdDerivations": [
            {
                "id": str(uuid4()),
                "digest": "b" * 64,
                "job": {"job_type": "super_game_series_derive"},
                "payloadDigest": "c" * 64,
            }
        ],
    }
    service.replacement_plans = plans
    with TestClient(
        create_app(ApiSettings.from_environment({}), cleanup_service_dependency=lambda: service)
    ) as client:
        prefix = f"/api/v1/admin/games/{fixture['gameId']}/board-sources"
        response = client.get(
            prefix + f"/{fixture['batchId']}/replacement-request",
            params={"entryIds": fixture["entries"][0]["entryId"]},
        )
        assert response.status_code == 200, response.text
        assert response.json() == fixture
        command = {
            "mode": "replace_preserve_history",
            "action": "retire",
            "batchId": fixture["batchId"],
            "entryId": fixture["entries"][0]["entryId"],
            "expectedRevision": 1,
            "idempotencyKey": str(uuid4()),
            "confirmed": True,
            "previewToken": "a" * 64,
        }
        result = client.request("DELETE", prefix, json=command)
        assert result.status_code == 200, result.text
        assert result.json()["phase"] == "gap_open"
        assert plans.retirement_command.call_args.args[1].entry_id == parsed.entries[0].entry_id
        denied = client.request("DELETE", prefix, json={**command, "confirmed": False})
        assert denied.status_code == 422
        assert plans.retirement_command.call_count == 1
