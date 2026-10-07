"""Actual compiled DDL preserves old activation and refuses unsafe downgrade."""

import importlib
import importlib.util
import json
import sys
from contextlib import nullcontext
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def ddl(direction):
    path = (
        Path(__file__).resolve().parents[3]
        / "services/api/alembic/versions/0146_v7_operator_selected_sources.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0146", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        module.revision == "0146_v7_operator_sources"
        and module.down_revision == "0145_v7_pilot_acceptances"
    )
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        getattr(module, direction)()
    return output.getvalue()


def test_upgrade_is_explicit_public_and_does_not_activate_or_change_old_receipts():
    sql = " ".join(ddl("upgrade").split())
    assert "pilot_source_policy VARCHAR(40) DEFAULT 'exact_sources' NOT NULL" in sql
    assert "ALTER TABLE public.semi_automatic_selection_v7_activation_gate" in sql
    assert "pilot_source_game_ref IS NULL AND jsonb_array_length(pilot_source_bindings) = 0" in sql
    assert "pilot_acceptance_receipt_fingerprint IS NOT NULL" in sql
    assert "UPDATE " not in sql and "INSERT " not in sql and "DELETE " not in sql


def test_downgrade_refuses_active_operator_policy_before_dropping_column():
    sql = ddl("downgrade")
    guard, drop = sql.split("ALTER TABLE", 1)
    assert "WHERE pilot_status = 'active'" in guard
    assert "RAISE EXCEPTION 'Cannot downgrade an active operator-selected V7 gate'" in guard
    assert "pilot_source_game_ref IS NOT NULL" in drop
    assert "DROP COLUMN pilot_source_policy" in drop


def test_additive_migration_preserves_recorded_ready_role_ownership(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    prepare = importlib.import_module("scripts.prepare_v7_reviewed_pilot")
    settings = {
        "phase": "ready",
        "ownerDatabaseUrl": "postgresql://localhost/game_predictor_v7_pilot",
    }
    saved = tmp_path / "settings.json"
    calls = []
    engine = type(
        "Engine",
        (),
        {"connect": lambda _self: nullcontext(object()), "dispose": lambda _self: None},
    )()
    monkeypatch.setattr(prepare, "_load", lambda: settings)
    monkeypatch.setattr(prepare, "_engine", lambda _url: engine)
    monkeypatch.setattr(prepare, "_check_owner", lambda _connection, _settings: None)
    monkeypatch.setattr(prepare, "SETTINGS", saved)
    monkeypatch.setattr(prepare.command, "upgrade", lambda _config, head: calls.append(head))
    assert prepare.migrate()["head"] == "0147_merge_v7_main"
    assert calls == ["0147_merge_v7_main"]
    assert json.loads(saved.read_text())["phase"] == "ready"
