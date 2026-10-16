"""Ownership-receipt cleanup tests without any PostgreSQL connection."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import _application_role_database as fixture
import _recording_capability_fixture as capability_fixture
import pytest
from game_predictor_api.storage.database_roles import DatabaseRoleError
from sqlalchemy.engine import Connection, Engine, make_url

_ROLE = "gp_rec_" + "a" * 24


class _Result:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value

    def one(self) -> object:
        return self.value

    def one_or_none(self) -> object:
        return self.value


class _Connection:
    def __init__(self, *results: object) -> None:
        self.results = iter(results)
        self.drops: list[str] = []
        self.queries: list[str] = []

    def execute(self, statement: object, parameters: object = None) -> _Result:
        self.queries.append(str(statement))
        return _Result(next(self.results))

    def exec_driver_sql(self, statement: str) -> None:
        self.drops.append(statement)

    def scalar(self, statement: object, parameters: object = None) -> object:
        return self.execute(statement, parameters).scalar_one()


def _receipt() -> fixture.RecordingCapabilityReceipt:
    return fixture.RecordingCapabilityReceipt(
        role=_ROLE,
        role_oid=72,
        database="game_predictor_t1002_abcdefabcdef_test",
        database_oid=42,
        marker='{"nonce":"own-receipt"}',
        created_here=True,
    )


def test_cleanup_never_touches_preexisting_capability() -> None:
    connection = _Connection()
    capability_fixture.drop_recording_capability_receipt(
        cast(Connection, connection),
        replace(_receipt(), created_here=False),
    )
    assert connection.queries == connection.drops == []


def test_cleanup_requires_original_database_already_dropped() -> None:
    connection = _Connection(False)
    with pytest.raises(AssertionError, match="exact fixture database"):
        capability_fixture.drop_recording_capability_receipt(
            cast(Connection, connection), _receipt()
        )
    assert not connection.drops


@pytest.mark.parametrize("oid,marker", [(73, '{"nonce":"own-receipt"}'), (72, "replaced")])
def test_cleanup_preserves_replaced_or_modified_role(oid: int, marker: str) -> None:
    connection = _Connection(True, (oid, marker))
    with pytest.raises(AssertionError, match="changed or replaced"):
        capability_fixture.drop_recording_capability_receipt(
            cast(Connection, connection), _receipt()
        )
    assert not connection.drops


def test_cleanup_preserves_role_with_remaining_dependencies_or_memberships() -> None:
    connection = _Connection(True, (72, _receipt().marker), True)
    with pytest.raises(AssertionError, match="dependencies or memberships"):
        capability_fixture.drop_recording_capability_receipt(
            cast(Connection, connection), _receipt()
        )
    assert not connection.drops


def test_cleanup_drops_only_exact_unused_created_here_role() -> None:
    connection = _Connection(True, (72, _receipt().marker), False)
    capability_fixture.drop_recording_capability_receipt(cast(Connection, connection), _receipt())
    assert connection.drops == [f'DROP ROLE "{_ROLE}"']


def test_provisioning_records_preexisting_identity_without_cleanup_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capability_fixture, "validate_recording_capability", lambda connection: _ROLE
    )
    monkeypatch.setattr(
        capability_fixture,
        "provision_recording_capability",
        lambda connection: pytest.fail(
            "Pre-existing capability must never be reprovisioned or adopted",
        ),
    )
    connection = _Connection((_receipt().database, 42, 72, _receipt().marker))
    receipt = capability_fixture.provision_recording_capability_receipt(
        cast(Connection, connection)
    )
    assert receipt == replace(_receipt(), created_here=False)


def test_provisioning_creates_only_missing_capability_and_records_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(connection: Connection) -> str:
        raise DatabaseRoleError("RECORDING_CAPABILITY_REQUIRED", "missing")

    calls: list[str] = []
    monkeypatch.setattr(capability_fixture, "validate_recording_capability", missing)
    monkeypatch.setattr(
        capability_fixture,
        "provision_recording_capability",
        lambda connection: (calls.append("created") or _ROLE),
    )
    connection = _Connection((_receipt().database, 42, 72, _receipt().marker))
    assert (
        capability_fixture.provision_recording_capability_receipt(cast(Connection, connection))
        == _receipt()
    )
    assert calls == ["created"]


def test_provisioning_refuses_collision_without_adoption(monkeypatch: pytest.MonkeyPatch) -> None:
    def collision(connection: Connection) -> str:
        raise DatabaseRoleError("RECORDING_CAPABILITY_IDENTITY", "collision")

    monkeypatch.setattr(capability_fixture, "validate_recording_capability", collision)
    monkeypatch.setattr(
        capability_fixture,
        "provision_recording_capability",
        lambda connection: pytest.fail(
            "A colliding role must never be modified",
        ),
    )
    connection = _Connection()
    with pytest.raises(DatabaseRoleError, match="collision"):
        capability_fixture.provision_recording_capability_receipt(cast(Connection, connection))
    assert not connection.queries and not connection.drops


def test_game_provisioning_uses_patched_manifest_bound_and_reports_last_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Context:
        def __enter__(self) -> Context:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def begin(self) -> Context:
            return self

        def execute(self, *args: object) -> None:
            pass

    class Repository:
        steps = 0

        def start_or_resume(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(operation_id="own-operation")

        def run_next(self, operation: object) -> SimpleNamespace:
            self.steps += 1
            return SimpleNamespace(status="running", step=self.steps)

    repository = Repository()
    monkeypatch.setattr(fixture.game_partition_lifecycle, "CREATE_TABLES", ("historical-table",))
    monkeypatch.setattr(fixture, "Session", lambda engine: Context())
    monkeypatch.setattr(fixture, "GamePartitionLifecycleRepository", lambda session: repository)
    with pytest.raises(AssertionError, match="last receipt:.*step=3"):
        fixture.provision_game(cast(Engine, Context()), "own-game")
    assert repository.steps == 3


def test_historical_fixture_holder_never_provisions_cluster_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capability_fixture.ScriptDirectory,
        "from_config",
        lambda config: SimpleNamespace(
            iterate_revisions=lambda revision, base: [
                SimpleNamespace(revision="0160_grid_geometry_proposals")
            ]
        ),
    )
    monkeypatch.setattr(
        capability_fixture,
        "create_engine",
        lambda *args, **kwargs: pytest.fail(
            "Historical fixture must not open a capability provisioning connection"
        ),
    )
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    assert holder.provision("0160_grid_geometry_proposals") is None
    assert holder.receipt is None


def test_cleanup_identity_guard_rejects_replaced_database() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    holder.receipt = _receipt()
    holder.database_oid = 42
    with pytest.raises(AssertionError, match="replaced fixture"):
        holder.assert_database_identity(cast(Connection, _Connection(43)))


def test_cleanup_without_successful_create_receipt_never_touches_existing_database() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    connection = _Connection()
    with pytest.raises(AssertionError, match="unowned"):
        holder.assert_database_identity(cast(Connection, connection))
    assert connection.queries == connection.drops == []


def test_database_collision_is_rejected_before_create_or_cleanup() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    connection = _Connection(False)
    with pytest.raises(AssertionError, match="adopt an existing"):
        holder.create_database(cast(Connection, connection))
    assert holder.database_oid is None and not connection.drops


def test_failed_create_keeps_original_error_without_an_ownership_receipt() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )

    class RefusingConnection(_Connection):
        def exec_driver_sql(self, statement: str) -> None:
            assert statement.startswith("CREATE DATABASE")
            raise RuntimeError("original CREATE refusal")

    connection = RefusingConnection(True)
    with pytest.raises(RuntimeError, match="original CREATE refusal"):
        holder.create_database(cast(Connection, connection))
    assert holder.database_oid is None and not connection.drops


@pytest.mark.parametrize(
    "module_name,fixture_name",
    [
        ("test_postgres_baseline", "isolated_database"),
        ("test_image_batch_store", "isolated_image_batch_database"),
        ("test_symbol_review_query_cancellation", "_own_empty_database"),
    ],
)
def test_fixture_failed_create_does_not_reconnect_or_mask_original_error(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    fixture_name: str,
) -> None:
    import importlib

    module = importlib.import_module(module_name)

    class Engine:
        connects = 0
        disposed = False

        def connect(self):
            self.connects += 1
            assert self.connects == 1, "Cleanup must not reconnect after failed CREATE"
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def dispose(self):
            self.disposed = True

    engine = Engine()

    original_error = RuntimeError("original fixture CREATE refusal")

    def failed_create(connection):
        raise original_error

    owned = SimpleNamespace(database_oid=None, create_database=failed_create)
    monkeypatch.setattr(module, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(module, "OwnedRecordingCapability", lambda url: owned)
    monkeypatch.setattr(
        module,
        "_database_url",
        lambda name: make_url("postgresql+psycopg://owner@localhost/owned_test").set(database=name),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="original fixture CREATE refusal") as caught:
        next(getattr(module, fixture_name).__wrapped__())
    assert caught.value is original_error
    assert engine.connects == 1 and engine.disposed


@pytest.mark.parametrize("failure_phase", ["create", "body", None])
@pytest.mark.parametrize("cleanup_stage", ["drop", "dispose"])
def test_cancellation_fixture_preserves_original_error_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str | None,
    cleanup_stage: str,
) -> None:
    import test_symbol_review_query_cancellation as cancellation

    original_error = RuntimeError(f"original fixture {failure_phase} failure")
    cleanup_error = RuntimeError(f"owned {cleanup_stage} refusal")
    drops: list[object] = []

    class Engine:
        connects = 0
        disposed = False

        def connect(self):
            self.connects += 1
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def dispose(self):
            self.disposed = True
            if cleanup_stage == "dispose":
                raise cleanup_error

    engine = Engine()
    owned = SimpleNamespace(database_oid=None)

    def create_database(connection):
        # Setup can fail after successful CREATE has established an ownership receipt.
        owned.database_oid = 42
        if failure_phase == "create":
            raise original_error

    def drop_database(connection):
        drops.append(connection)
        if cleanup_stage == "drop":
            raise cleanup_error

    owned.create_database = create_database
    owned.drop_database = drop_database
    monkeypatch.setattr(cancellation, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(cancellation, "OwnedRecordingCapability", lambda url: owned)
    monkeypatch.setattr(
        cancellation,
        "ApiSettings",
        SimpleNamespace(
            from_environment=lambda: SimpleNamespace(
                owner_database_url="postgresql+psycopg://owner@localhost/owned_test"
            )
        ),
    )
    expected_error = cleanup_error if failure_phase is None else original_error
    with pytest.raises(RuntimeError) as caught, cancellation._own_empty_database():
        if failure_phase == "body":
            raise original_error
    assert caught.value is expected_error
    if failure_phase is not None:
        assert any(str(cleanup_error) in note for note in original_error.__notes__)
    assert drops == [engine]
    assert engine.connects == 2 and engine.disposed


def test_cleanup_evidence_io_cannot_mask_original_test_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_source_recording_groups_postgres import _write_cleanup_evidence

    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_EVIDENCE_ROOT", "relative-unowned")
    with pytest.raises(ValueError, match="original test error"):
        try:
            raise ValueError("original test error")
        finally:
            with pytest.warns(pytest.PytestWarning, match="Cleanup evidence not saved"):
                _write_cleanup_evidence({"databaseRemaining": 0})


def test_resource_journal_records_exact_identities_without_credentials(tmp_path: Path) -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner:never-save-secret@localhost/owned_test")
    )
    holder.journal_root = tmp_path
    holder.record_created_database(cast(Connection, _Connection(42)))
    path = tmp_path / "owned_test-42.json"
    created = json.loads(path.read_text(encoding="utf-8"))
    assert created["databaseOid"] == 42 and created["databaseCreatedHere"] is True
    assert created["phase"] == "database_created" and created["capabilityRole"] is None
    holder.receipt = replace(_receipt(), database="owned_test")
    holder.record_runtime_role(
        cast(Connection, _Connection(73)), "runtime", created_here=True, committed=True
    )
    serialized = path.read_text(encoding="utf-8")
    completed = json.loads(serialized)
    assert completed["capabilityRole"] == {
        "name": _ROLE,
        "oid": 72,
        "createdHere": True,
        "marker": _receipt().marker,
    }
    assert completed["runtimeRole"] == {"name": "runtime", "oid": 73, "createdHere": True}
    assert completed["phase"] == "runtime_ready"
    assert "never-save-secret" not in serialized and "postgresql" not in serialized
    assert list(tmp_path.glob("*.pending")) == []


def test_cleanup_never_drops_replaced_runtime_role() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    holder.database_oid = 42
    holder.runtime_role_receipt = capability_fixture.RuntimeRoleReceipt("runtime", 73, True)
    connection = _Connection(True, 74)
    with pytest.raises(AssertionError, match="replaced runtime role"):
        holder.cleanup(cast(Connection, connection))
    assert connection.drops == []


def test_failed_journal_removes_only_just_created_empty_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )

    def inaccessible(phase: str) -> None:
        raise OSError("owned journal unavailable")

    monkeypatch.setattr(holder, "_journal", inaccessible)
    connection = _Connection(42, 42)
    with pytest.raises(OSError, match="owned journal unavailable"):
        holder.record_created_database(cast(Connection, connection))
    assert connection.drops == ['DROP DATABASE "owned_test"']


def test_owned_idle_wait_rechecks_oid_and_does_not_terminate_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    holder.database_oid = 42
    connection = _Connection(42, 1, 42, 0)
    sleeps: list[float] = []
    monkeypatch.setattr(capability_fixture.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(capability_fixture.time, "sleep", sleeps.append)
    assert holder.wait_for_owned_database_idle(cast(Connection, connection)) == 0
    assert sleeps == [0.1]
    assert connection.drops == []
    assert sum("SELECT oid" in query for query in connection.queries) == 2


def test_owned_idle_wait_returns_nonzero_after_five_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    holder.database_oid = 42
    connection = _Connection(42, 1)
    clock = iter((10.0, 15.0))
    monkeypatch.setattr(capability_fixture.time, "monotonic", lambda: next(clock))
    assert holder.wait_for_owned_database_idle(cast(Connection, connection)) == 1
    assert connection.drops == []


def test_owned_idle_wait_refuses_replaced_database() -> None:
    holder = capability_fixture.OwnedRecordingCapability(
        make_url("postgresql+psycopg://owner@localhost/owned_test")
    )
    holder.database_oid = 42
    connection = _Connection(99)
    with pytest.raises(AssertionError, match="replaced fixture DB"):
        holder.wait_for_owned_database_idle(cast(Connection, connection))
    assert connection.drops == []
    assert len(connection.queries) == 1
