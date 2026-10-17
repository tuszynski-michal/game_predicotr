"""Canonical deployment order and capability-only CLI mode without DB operations."""

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _provision_script():
    spec = importlib.util.spec_from_file_location(
        "recording_deployment_provision_test", ROOT / "scripts/provision_database_roles.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_migrate_and_reset_keep_capability_upgrade_runtime_order():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    steps = package["scripts"]["db:migrate"].split(" && ")
    assert len(steps) == 3
    assert steps[0].endswith("scripts/provision_database_roles.py --recording-capability")
    assert steps[1].endswith("-m alembic upgrade head")
    assert steps[2].endswith("scripts/provision_database_roles.py")
    reset = (ROOT / "scripts/reset_local_admin_database.ps1").read_text(encoding="utf-8")
    capability = reset.index(
        "& $pythonPath scripts/provision_database_roles.py --recording-capability"
    )
    upgrade = reset.index("& $pythonPath -m alembic upgrade head")
    runtime = reset.index("& $pythonPath scripts/provision_database_roles.py\n")
    assert reset.index("if (-not $ConfirmReset)") < capability < upgrade < runtime
    assert reset.index("$databaseName -ne 'game_predictor'") < capability


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["--recording-capability"], ["capability"]),
        (["--recording-capability", "--check"], ["validate_capability"]),
        ([], ["runtime"]),
        (["--check"], ["check_runtime"]),
    ],
)
def test_provision_modes_are_separate_and_dispose_their_connection(
    monkeypatch, capsys, arguments, expected
):
    module = _provision_script()
    calls = []

    class Engine:
        @contextmanager
        def begin(self):
            yield object()

        connect = begin

        def dispose(self):
            calls.append("dispose")

    monkeypatch.setattr(module, "create_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(
        module.ApiSettings,
        "from_environment",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://runtime:unused@localhost/owned_dummy",
            owner_database_url="postgresql+psycopg://owner:unused@localhost/owned_dummy",
        ),
    )
    monkeypatch.setattr(
        module,
        "provision_recording_capability",
        lambda connection: calls.append("capability") or "owned_capability",
    )
    monkeypatch.setattr(
        module,
        "validate_recording_capability",
        lambda connection: calls.append("validate_capability") or "owned_capability",
    )
    report = SimpleNamespace(compliant=True, as_dict=lambda: {"compliant": True})
    monkeypatch.setattr(
        module,
        "provision_application_role",
        lambda connection, spec: calls.append("runtime") or report,
    )
    monkeypatch.setattr(
        module,
        "describe_application_role",
        lambda connection, role: calls.append("check_runtime") or report,
    )
    assert module.main(arguments) == 0
    assert calls == expected + ["dispose"]
    body = json.loads(capsys.readouterr().out)
    if "--recording-capability" in arguments:
        assert body["recordingCapability"] == "owned_capability"
        assert "compliant" not in body  # No premature runtime compliance claim.


def test_failed_capability_never_runs_runtime_provisioning(monkeypatch):
    module = _provision_script()
    calls = []

    class Engine:
        @contextmanager
        def begin(self):
            yield object()

        def dispose(self):
            calls.append("dispose")

    def refused(connection):
        raise module.DatabaseRoleError("RECORDING_CAPABILITY_REQUIRED", "Missing capability")

    monkeypatch.setattr(module, "create_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(
        module.ApiSettings,
        "from_environment",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://runtime:unused@localhost/owned_dummy",
            owner_database_url="postgresql+psycopg://owner:unused@localhost/owned_dummy",
        ),
    )
    monkeypatch.setattr(module, "provision_recording_capability", refused)
    monkeypatch.setattr(module, "provision_application_role", lambda *args: calls.append("runtime"))
    assert module.main(["--recording-capability"]) == 1
    assert calls == ["dispose"]
