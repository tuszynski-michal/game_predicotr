"""Lifecycle contract of disposable tooling databases; no workloads are run."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from game_predictor_api.storage.owned_tool_database import OwnedToolDatabase, _RoleReceipt
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
RUNNERS = (
    "scripts/run_m4_import_acceptance.py",
    "scripts/prepare_m34_device_candidate.py",
    "scripts/run_concurrent_worker_lane_acceptance.py",
    "services/worker/src/game_predictor_worker/images/load_benchmark.py",
    "services/worker/src/game_predictor_worker/images/operations_benchmark.py",
)


@pytest.mark.parametrize("relative_path", RUNNERS)
def test_runners_use_owned_database_and_runtime_url(relative_path: str) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "OwnedToolDatabase" in source
    assert ".runtime_url" in source
    assert "WITH (FORCE)" not in source
    assert "DROP DATABASE" not in source
    assert "tests.integration" not in source
    if "SqlAlchemyCatalogRepository" in source:
        assert "partition_ddl_session_factory=" in source
        assert ".owner_url" in source


def _database() -> OwnedToolDatabase:
    return OwnedToolDatabase(
        make_url("postgresql+psycopg://owner:secret@localhost/operator"),
        prefix="game_predictor_tool_test",
        alembic_ini=ROOT / "alembic.ini",
    )


def _result(*, scalar: object = None, row: object = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = scalar
    result.one_or_none.return_value = row
    result.one.return_value = row
    return result


def test_uuid_database_and_unprovisioned_runtime() -> None:
    first, second = _database(), _database()
    assert first.database_name != second.database_name
    assert first.owner_url.database != "operator"
    with pytest.raises(RuntimeError, match="not provisioned"):
        _ = first.runtime_url


@pytest.mark.parametrize("collision", [False, True])
def test_create_failure_never_drops_unowned_database(collision: bool) -> None:
    database = _database()
    maintenance = MagicMock()
    connection = maintenance.connect.return_value.__enter__.return_value
    connection.execute.return_value = _result(row=(42,) if collision else None)
    original = RuntimeError("original CREATE failure")
    connection.exec_driver_sql.side_effect = original
    with (
        patch.object(database, "_engine", return_value=maintenance),
        pytest.raises(
            RuntimeError, match="existing disposable" if collision else "original CREATE"
        ) as captured,
    ):
        database.create()
    if not collision:
        assert captured.value is original
    assert not database.created_here
    assert all("DROP" not in str(call) for call in connection.exec_driver_sql.call_args_list)
    maintenance.dispose.assert_called_once()


def test_provisioning_order_and_separate_runtime_identity() -> None:
    database = _database()
    maintenance, owner = MagicMock(), MagicMock()
    maintenance_connection = maintenance.connect.return_value.__enter__.return_value
    maintenance_connection.execute.side_effect = [
        _result(row=None),
        _result(scalar=42),
        _result(scalar="'marker'"),
    ]
    owner_connection = owner.begin.return_value.__enter__.return_value
    owner_connection.execute.side_effect = [
        _result(row=(42, database.marker)),
        _result(row=None),
        _result(row=(50, "capability-marker")),
        _result(row=(42, database.marker)),
        _result(row=None),
        _result(scalar="'marker'"),
        _result(row=(51, database.marker)),
    ]
    phases: list[str] = []
    with (
        patch.object(database, "_engine", side_effect=[maintenance, owner]),
        patch(
            "game_predictor_api.storage.owned_tool_database.provision_recording_capability",
            side_effect=lambda connection: phases.append("capability") or "gp_rec_test",
        ),
        patch(
            "game_predictor_api.storage.owned_tool_database.command.upgrade",
            side_effect=lambda config, revision: phases.append("head"),
        ),
        patch(
            "game_predictor_api.storage.owned_tool_database.provision_application_role",
            side_effect=lambda connection, spec: phases.append("application"),
        ),
    ):
        database.create()
    assert phases == ["capability", "head", "application"]
    assert database.created_here and database.database_oid == 42
    assert database.runtime_url.username != database.owner_url.username
    assert database.runtime_url.password != database.owner_url.password
    assert database.runtime_url.database == database.owner_url.database
    assert all(receipt.created_here for receipt in database._roles)
    owner.dispose.assert_called_once()
    database.close(retain=True)


@pytest.mark.parametrize("oid,marker", [(43, "original"), (42, "changed")])
def test_database_cleanup_rejects_replaced_identity(oid: int, marker: str) -> None:
    database = _database()
    database.created_here, database.database_oid, database.marker = True, 42, "original"
    connection = MagicMock()
    connection.execute.return_value = _result(row=(oid, marker))
    with pytest.raises(RuntimeError, match="changed or unowned"):
        database._cleanup(connection)
    connection.exec_driver_sql.assert_not_called()


def test_busy_database_is_retained_without_terminating_clients() -> None:
    database = _database()
    database.created_here, database.database_oid = True, 42
    connection = MagicMock()
    connection.execute.side_effect = [
        _result(row=(42, database.marker)),
        _result(row=(42, database.marker)),
        _result(scalar=1),
    ]
    with (
        patch("game_predictor_api.storage.owned_tool_database.time.monotonic", side_effect=[0, 6]),
        pytest.raises(RuntimeError, match="active connections"),
    ):
        database._cleanup(connection)
    connection.exec_driver_sql.assert_not_called()


@pytest.mark.parametrize("failure", ["database", "oid", "marker", "dependency"])
def test_role_cleanup_never_drops_changed_or_used_role(failure: str) -> None:
    database = _database()
    database.database_oid = 42
    connection = MagicMock()
    connection.execute.side_effect = [
        _result(row=(42,) if failure == "database" else None),
        _result(
            row=(
                52 if failure == "oid" else 51,
                "changed" if failure == "marker" else "role-marker",
            )
        ),
        _result(scalar=failure == "dependency"),
    ]
    with pytest.raises(RuntimeError):
        database._drop_role(connection, _RoleReceipt("gp_tool_test", 51, "role-marker", True))
    connection.exec_driver_sql.assert_not_called()


def test_cleanup_failure_does_not_replace_original_failure() -> None:
    database = _database()
    database.created_here = True
    database._maintenance = MagicMock()
    original = RuntimeError("original CREATE failure")
    with patch.object(database, "_cleanup", side_effect=RuntimeError("cleanup failure")):
        database.close(original)
    assert original.__notes__ == ["Disposable database cleanup failed: RuntimeError"]


def test_explicit_close_resumes_only_pending_roles_after_database_drop() -> None:
    database = _database()
    database.created_here, database.database_oid = True, 42
    receipts = [
        _RoleReceipt("gp_rec_test", 50, "capability-marker", True),
        _RoleReceipt("gp_tool_test", 51, "runtime-marker", True),
    ]
    database._roles.extend(receipts)
    first_maintenance, second_maintenance = MagicMock(), MagicMock()
    database._maintenance = first_maintenance
    first = first_maintenance.connect.return_value.__enter__.return_value
    first.execute.side_effect = [
        _result(row=(42, database.marker)),
        _result(row=(42, database.marker)),
        _result(scalar=0),
        _result(row=(42, database.marker)),
    ]
    original = RuntimeError("original workload failure")
    with patch.object(database, "_drop_role", side_effect=RuntimeError("injected cleanup failure")):
        database.close(original)
    assert original.__notes__ == ["Disposable database cleanup failed: RuntimeError"]
    assert database._roles == receipts
    assert not database.created_here
    assert first.exec_driver_sql.call_args.args == (f'DROP DATABASE "{database.database_name}"',)
    with patch.object(database, "_engine") as unexpected:
        database.close(original)
        unexpected.assert_not_called()
    second = second_maintenance.connect.return_value.__enter__.return_value
    second.execute.side_effect = [
        _result(row=None),
        _result(row=(51, "runtime-marker")),
        _result(scalar=False),
        _result(row=None),
        _result(row=(50, "capability-marker")),
        _result(scalar=False),
    ]
    with patch.object(database, "_engine", return_value=second_maintenance):
        database.close(retry_cleanup=True)
    assert database._roles == []
    assert [call.args[0] for call in second.exec_driver_sql.call_args_list] == [
        'DROP ROLE "gp_tool_test"',
        'DROP ROLE "gp_rec_test"',
    ]
    first_maintenance.dispose.assert_called_once()
    second_maintenance.dispose.assert_called_once()


def test_explicit_close_can_recheck_previously_busy_owned_database() -> None:
    database = _database()
    database.created_here, database.database_oid = True, 42
    first_maintenance, second_maintenance = MagicMock(), MagicMock()
    database._maintenance = first_maintenance
    first = first_maintenance.connect.return_value.__enter__.return_value
    first.execute.side_effect = [
        _result(row=(42, database.marker)),
        _result(row=(42, database.marker)),
        _result(scalar=1),
    ]
    with (
        patch("game_predictor_api.storage.owned_tool_database.time.monotonic", side_effect=[0, 6]),
        pytest.raises(RuntimeError, match="active connections"),
    ):
        database.close()
    assert database.created_here
    first.exec_driver_sql.assert_not_called()
    with patch.object(database, "_engine") as unexpected:
        database.close()
        unexpected.assert_not_called()
    second = second_maintenance.connect.return_value.__enter__.return_value
    second.execute.side_effect = [
        _result(row=(42, database.marker)),
        _result(row=(42, database.marker)),
        _result(scalar=0),
        _result(row=(42, database.marker)),
    ]
    with patch.object(database, "_engine", return_value=second_maintenance):
        database.close(retry_cleanup=True)
    assert not database.created_here
    assert second.exec_driver_sql.call_args.args == (f'DROP DATABASE "{database.database_name}"',)
