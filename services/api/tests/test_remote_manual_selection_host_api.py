from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
)
from game_predictor_api.main import create_app

NOW = datetime(2026, 8, 23, 20, tzinfo=UTC)
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows host path boundary")


def _client(tmp_path: Path, selected: Path | None) -> TestClient:
    service = RemoteManualSelectionHostService(
        lambda: selected,
        clock=lambda: NOW,
        capability_ttl=timedelta(minutes=5),
    )
    return TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            remote_manual_selection_host_service_dependency=lambda: service,
        )
    )


def test_local_base_picker_returns_opaque_capability_without_path(tmp_path: Path) -> None:
    base = tmp_path / "private-base"
    base.mkdir()
    client = _client(tmp_path, base)

    with client:
        response = client.post("/api/v1/admin/remote-manual-selections/base-capabilities")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "selected"
    assert payload["displayName"] == "private-base"
    assert len(payload["baseCapability"]) >= 32
    assert payload["expiresAt"] == "2026-08-23T20:05:00Z"
    encoded = response.text.lower()
    assert "private-base" in encoded
    assert str(base).lower().replace("\\", "\\\\") not in encoded
    assert "path" not in payload


def test_local_base_picker_cancel_has_no_capability(tmp_path: Path) -> None:
    client = _client(tmp_path, None)

    with client:
        response = client.post("/api/v1/admin/remote-manual-selections/base-capabilities")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "cancelled",
        "baseCapability": None,
        "displayName": None,
        "expiresAt": None,
    }


def test_local_base_picker_conflict_is_stable_and_does_not_leak_path(tmp_path: Path) -> None:
    def conflict() -> Path | None:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_BASE_PICKER_ALREADY_OPEN",
            "A host base selection window is already open.",
        )

    service = RemoteManualSelectionHostService(conflict, clock=lambda: NOW)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
            ),
            remote_manual_selection_host_service_dependency=lambda: service,
        )
    )

    with client:
        response = client.post("/api/v1/admin/remote-manual-selections/base-capabilities")

    assert response.status_code == 409
    assert response.json() == {
        "code": "REMOTE_SELECTION_BASE_PICKER_ALREADY_OPEN",
        "message": "A host base selection window is already open.",
        "details": {},
    }
    assert str(tmp_path).lower() not in response.text.lower()
