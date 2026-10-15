"""Focused provisioning tests; PostgreSQL privilege proofs use isolated DB fixtures."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from game_predictor_api.storage import source_recording_permissions as permissions
from game_predictor_api.storage.database_roles import ApplicationRoleReport, DatabaseRoleError
from sqlalchemy.engine import Connection


class _Result:
    def __init__(self, value: object = False) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value

    def one(self) -> object:
        return self.value

    def mappings(self) -> _Result:
        return self

    def all(self) -> object:
        return self.value

    def __iter__(self) -> Any:
        return iter(self.value if isinstance(self.value, list) else [])


class _Connection:
    def __init__(self, *, membership: bool = False) -> None:
        self.membership = membership
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: object = None) -> _Result:
        self.statements.append(str(statement))
        if "pg_auth_members" in str(statement):
            return _Result(self.membership)
        if "pg_attribute" in str(statement):
            return _Result([("id",), ("body",)])
        raise AssertionError(str(statement))

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


def _valid_role() -> dict[str, object]:
    return {
        "oid": 72,
        "rolcanlogin": False,
        "rolsuper": False,
        "rolbypassrls": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolinherit": False,
        "marker": json.dumps(
            {
                "kind": "game-predictor-recording-capability-v1",
                "databaseName": "own_test",
                "databaseOid": 42,
                "roleOid": 72,
                "nonce": "a" * 64,
            }
        ),
    }


@pytest.fixture
def identity(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    role = _valid_role()
    monkeypatch.setattr(permissions, "_identity", lambda connection: ("own_test", 42, "gp_rec_abc"))
    monkeypatch.setattr(permissions, "_role", lambda connection, name: role)
    return role


def test_validated_role_is_stable_and_does_not_change_cluster(identity: dict[str, object]) -> None:
    connection = _Connection()
    assert permissions.provision_recording_capability(cast(Connection, connection)) == "gp_rec_abc"
    assert not any("CREATE ROLE" in sql or "ALTER ROLE" in sql for sql in connection.statements)


def test_role_name_is_bound_to_both_database_name_and_oid() -> None:
    class IdentityConnection:
        def __init__(self, name: str, oid: int):
            self.value = name, oid

        def execute(self, statement: object) -> _Result:
            return _Result(self.value)

    first = permissions._identity(cast(Connection, IdentityConnection("own_test", 42)))[2]
    assert first.startswith("gp_rec_") and len(first) == 31
    assert first == permissions._identity(cast(Connection, IdentityConnection("own_test", 42)))[2]
    assert first != permissions._identity(cast(Connection, IdentityConnection("clone_test", 42)))[2]
    assert first != permissions._identity(cast(Connection, IdentityConnection("own_test", 43)))[2]


def test_explicit_creation_records_database_role_oid_and_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role = _valid_role()

    class CreationConnection(_Connection):
        created = False

        def execute(self, statement: object, parameters: object = None) -> _Result:
            if "quote_literal" in str(statement):
                assert isinstance(parameters, dict)
                return _Result("'" + str(parameters["value"]) + "'")
            return super().execute(statement, parameters)

        def exec_driver_sql(self, statement: str) -> None:
            super().exec_driver_sql(statement)
            if statement.startswith("CREATE ROLE"):
                self.created = True
            if statement.startswith("COMMENT ON ROLE"):
                role["marker"] = statement.split(" IS '", 1)[1][:-1]

    connection = CreationConnection()
    monkeypatch.setattr(permissions, "_identity", lambda connection: ("own_test", 42, "gp_rec_abc"))
    monkeypatch.setattr(
        permissions, "_role", lambda connection, name: role if connection.created else None
    )
    assert permissions.provision_recording_capability(cast(Connection, connection)) == "gp_rec_abc"
    marker = json.loads(str(role["marker"]))
    assert marker["databaseName"] == "own_test" and marker["databaseOid"] == 42
    assert marker["roleOid"] == 72 and len(marker["nonce"]) == 64
    assert connection.statements[0] == (
        'CREATE ROLE "gp_rec_abc" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB '
        "NOCREATEROLE NOREPLICATION NOINHERIT"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("roleOid", 73),
        ("databaseOid", 43),
        ("databaseName", "cloned_test"),
        ("nonce", "invalid"),
        ("kind", "unowned"),
    ],
)
def test_collision_never_alters_or_adopts_role(
    identity: dict[str, object],
    field: str,
    value: object,
) -> None:
    marker = json.loads(str(identity["marker"]))
    marker[field] = value
    identity["marker"] = json.dumps(marker)
    connection = _Connection()
    with pytest.raises(DatabaseRoleError, match="ownership marker"):
        permissions.provision_recording_capability(cast(Connection, connection))
    assert connection.statements == []


@pytest.mark.parametrize(
    "attribute",
    [
        "rolcanlogin",
        "rolsuper",
        "rolbypassrls",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
        "rolinherit",
    ],
)
def test_capability_attributes_fail_closed(identity: dict[str, object], attribute: str) -> None:
    identity[attribute] = True
    with pytest.raises(DatabaseRoleError) as caught:
        permissions.validate_recording_capability(cast(Connection, _Connection()))
    assert caught.value.code == "RECORDING_CAPABILITY_ATTRIBUTES"


def test_capability_membership_is_forbidden(identity: dict[str, object]) -> None:
    with pytest.raises(DatabaseRoleError) as caught:
        permissions.validate_recording_capability(cast(Connection, _Connection(membership=True)))
    assert caught.value.code == "RECORDING_CAPABILITY_MEMBERSHIP"


def test_missing_capability_requires_explicit_provision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "_identity", lambda connection: ("own_test", 42, "gp_rec_abc"))
    monkeypatch.setattr(permissions, "_role", lambda connection, name: None)
    with pytest.raises(DatabaseRoleError) as caught:
        permissions.validate_recording_capability(cast(Connection, _Connection()))
    assert caught.value.code == "RECORDING_CAPABILITY_REQUIRED"


def test_private_exclusions_preserve_unrelated_same_prefix_and_overloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(permissions, "_exists", lambda connection, name: True)
    monkeypatch.setattr(
        permissions, "validate_recording_capability", lambda connection: "gp_rec_abc"
    )
    monkeypatch.setattr(
        permissions,
        "_functions",
        lambda connection: [
            {"qualified_signature": signature, "safe": signature in permissions.SAFE_FUNCTIONS}
            for signature in permissions.RECORDING_FUNCTIONS
        ],
    )
    monkeypatch.setattr(permissions, "recording_permission_errors", lambda connection, role: ())
    connection = _Connection()
    permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    sql = "\n".join(connection.statements)
    for table in permissions.PRIVATE_TABLES:
        assert f'REVOKE ALL PRIVILEGES ON TABLE {table} FROM "runtime", PUBLIC' in sql
        assert f'REVOKE SELECT ("id", "body") ON TABLE {table}' in sql
        assert f'REVOKE REFERENCES ("id", "body") ON TABLE {table}' in sql
    assert "REVOKE ALL PRIVILEGES ON SEQUENCE public.recording_evidence_ordinal_seq" in sql
    grants = [statement for statement in connection.statements if statement.startswith("GRANT")]
    assert grants == [
        f'GRANT EXECUTE ON FUNCTION {signature} TO "runtime"'
        for signature in permissions.SAFE_FUNCTIONS
    ]
    assert "grid_model" not in sql
    assert "public.recording_custom" not in sql
    assert "public.recording_command(text)" not in sql
    assert "public.recording_proof_v1(text)" not in sql


def test_function_discovery_uses_only_exact_versioned_signature_allowlist() -> None:
    class CatalogConnection(_Connection):
        def execute(self, statement: object, parameters: object = None) -> _Result:
            sql = str(statement)
            assert isinstance(parameters, dict)
            assert parameters["recording_functions"] == list(permissions.RECORDING_FUNCTIONS)
            assert "p.oid=to_regprocedure(required.signature)" in sql
            assert "left(p.proname" not in sql and "p.proname IN" not in sql
            assert "public.recording_custom()" not in parameters["recording_functions"]
            assert "public.recording_command(text)" not in parameters["recording_functions"]
            return _Result([])

    assert permissions._functions(cast(Connection, CatalogConnection())) == []


def test_registry_compliance_requires_every_exact_private_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(permissions, "_exists", lambda connection, name: True)
    monkeypatch.setattr(
        permissions,
        "validate_recording_capability",
        lambda connection: "gp_rec_abc",
    )
    monkeypatch.setattr(permissions, "_functions", lambda connection: [])

    class RegistryConnection(_Connection):
        def execute(self, statement: object, parameters: object = None) -> _Result:
            assert "pg_catalog.pg_class" in str(statement)
            return _Result({"owner": "gp_rec_abc", "runtime_access": False, "public_access": False})

    errors = permissions.recording_permission_errors(
        cast(Connection, RegistryConnection()), "runtime"
    )
    assert errors == tuple(f"{signature}:missing" for signature in permissions.RECORDING_FUNCTIONS)


def test_pre_migration_database_preserves_existing_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "_exists", lambda connection, name: False)
    connection = _Connection()
    permissions.enforce_recording_permissions(cast(Connection, connection), "runtime")
    assert permissions.recording_permission_errors(cast(Connection, connection), "runtime") == ()
    assert connection.statements == []


def test_attestation_dependencies_grant_only_required_revision_and_family_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        permissions,
        "validate_recording_capability",
        lambda connection: "gp_rec_abc",
    )
    connection = _Connection()
    permissions.grant_recording_capability_dependencies(cast(Connection, connection))
    revision_grants = [
        sql for sql in connection.statements if "image_source_geometry_revisions" in sql
    ]
    assert revision_grants == [
        "GRANT SELECT (game_id,source_image_id,source_checksum_sha256,"
        "normalized_pixel_checksum_sha256,normalization_adapter_version,"
        "oriented_width,oriented_height) ON "
        'game_data_v2.image_source_geometry_revisions TO "gp_rec_abc"'
    ]
    assert [sql for sql in connection.statements if "grid_model_families" in sql] == [
        'GRANT SELECT (id) ON public.grid_model_families TO "gp_rec_abc"'
    ]
    assert not any("ALTER" in sql or "set_config" in sql for sql in connection.statements)


def test_registry_errors_participate_in_application_compliance() -> None:
    report = ApplicationRoleReport(
        role_name="runtime",
        database_name="own_test",
        owner_role="owner",
        exists=True,
        can_login=True,
        superuser=False,
        bypass_rls=False,
        create_db=False,
        create_role=False,
        replication=False,
        memberships=(),
        owned_relations=0,
        schemas_without_usage=(),
        tables_without_dml=(),
        writable_read_only_tables=(),
        sequences_without_usage=(),
    )
    assert report.compliant
    invalid = replace(report, recording_permission_errors=("private:runtime_access",))
    assert not invalid.compliant
    assert invalid.as_dict()["recordingPermissionErrors"] == ["private:runtime_access"]
