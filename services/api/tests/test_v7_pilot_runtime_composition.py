"""Explicit composition scope and kernel process fencing, without live services."""

from __future__ import annotations

import importlib
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.config import ApiSettings, ConfigurationError
from game_predictor_api.domain.v7_selection_delivery import V7DeliveryConflict
from game_predictor_worker.semi_automatic_selection import v7_pilot_configuration as artifacts
from test_v7_pilot_acceptance import acceptance

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
composition = importlib.import_module("scripts.v7_pilot_fixture_app")
entry = importlib.import_module("scripts.v7_pilot_runtime_entry")


def test_worker_readiness_uses_persisted_domain_lane_and_exact_token(monkeypatch):
    from contextlib import nullcontext

    from game_predictor_api.domain.worker_lanes import WorkerLaneName

    from scripts import prepare_v7_reviewed_pilot as prepare

    token = uuid4()
    calls = []

    class Connection:
        def execute(self, statement):
            return self

        def one(self):
            return prepare.DATABASE, prepare.ROLE

        def scalar(self, statement, parameters=None):
            if parameters is None:
                return prepare.HEAD
            calls.append((str(statement), parameters))
            return parameters == {"lane": "image_selection", "token": token}

    class Engine:
        def connect(self):
            return nullcontext(Connection())

        def dispose(self):
            pass

    monkeypatch.setattr(
        prepare, "_load", lambda: {"phase": "ready", "databaseUrl": "postgresql://localhost/pilot"}
    )
    monkeypatch.setattr(prepare, "_engine", lambda url: Engine())
    assert WorkerLaneName.IMAGE_SELECTION.value == "image_selection"
    assert entry.check_ready("worker", token)["ready"] is True
    assert entry.check_ready("worker", uuid4())["ready"] is False
    assert calls[0][1] == {"lane": WorkerLaneName.IMAGE_SELECTION.value, "token": token}
    assert "lane=:lane" in calls[0][0] and "heartbeat_at" in calls[0][0]


def test_default_operator_factory_has_native_picker_and_unmodified_transport(monkeypatch):
    from game_predictor_api import main

    calls = []

    async def normal_app(scope, receive, send):
        pass

    def create_app(settings, **kwargs):
        calls.append(kwargs)
        return normal_app

    scopes = []
    monkeypatch.setattr(main, "create_app", create_app)
    monkeypatch.setattr(composition, "_pilot_settings", lambda scope: scopes.append(scope))
    assert entry.api_factory("real_pilot").endswith(":create_operator_app")
    assert entry.api_factory("technical_fixture").endswith(":create_fixture_app")
    assert composition.create_operator_app() is normal_app
    fixture = composition.create_fixture_app()
    assert isinstance(fixture, composition.FixtureResponseLoss)
    assert fixture.app is normal_app
    assert scopes == ["real_pilot", "technical_fixture"]
    assert calls == [{}, {"local_source_picker": composition.fixture_picker}]


@pytest.mark.parametrize("scope", ["real_pilot", "technical_fixture"])
def test_scope_mismatch_fails_before_any_artifact_read(tmp_path, monkeypatch, scope):
    _, gate = acceptance(tmp_path)
    opposite = "technical_fixture" if scope == "real_pilot" else "real_pilot"
    gate = replace(gate, acceptance_receipt={"scope": opposite})

    def forbidden(*args):
        raise AssertionError("Scope mismatch must fail before immutable artifact IO.")

    monkeypatch.setattr(artifacts, "read_immutable_v7_geometry_profile", forbidden)
    with pytest.raises(V7DeliveryConflict) as error:
        artifacts.V7PilotArtifacts(tmp_path, tmp_path, acceptance_scope=scope).validate(gate)
    assert error.value.code == "V7_PILOT_ACCEPTANCE_SCOPE_MISMATCH"


def test_legacy_artifact_consumer_keeps_default_scope(tmp_path):
    assert artifacts.V7PilotArtifacts(tmp_path, tmp_path).acceptance_scope is None
    assert ApiSettings.from_environment({}).v7_pilot_acceptance_scope is None
    for scope in ("real_pilot", "technical_fixture"):
        settings = ApiSettings.from_environment({"GAME_PREDICTOR_V7_PILOT_ACCEPTANCE_SCOPE": scope})
        assert settings.v7_pilot_acceptance_scope == scope
    with pytest.raises(ConfigurationError):
        ApiSettings.from_environment({"GAME_PREDICTOR_V7_PILOT_ACCEPTANCE_SCOPE": "client-bypass"})


@pytest.mark.skipif(sys.platform != "win32", reason="Windows runtime process file lock")
def test_duplicate_entry_is_fenced_and_fresh_process_can_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, "RUNTIME", tmp_path)
    marker = tmp_path / "owned"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from pathlib import Path;import sys,time;"
            "from scripts import v7_pilot_runtime_entry as e;"
            "e.RUNTIME=Path(sys.argv[1]);"
            "lock=e._runtime_lock('probe');"
            "Path(sys.argv[2]).write_text('owned');time.sleep(3);lock.close()",
            str(tmp_path),
            str(marker),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(20):
            if marker.exists():
                break
            time.sleep(0.1)
        assert marker.exists()
        with pytest.raises(ValueError, match="already has a live"):
            entry._runtime_lock("probe")
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, (stdout, stderr)
        with entry._runtime_lock("probe"):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
