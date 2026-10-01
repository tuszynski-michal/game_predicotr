"""Provisioning of the application database role (TASK-0795).

The schema owner (``GAME_PREDICTOR_OWNER_DATABASE_URL``) owns every object and
runs Alembic. API and worker runtime connect as a separate application role
that is ``NOSUPERUSER NOBYPASSRLS`` and owns nothing, so the forced
``game_data_v2`` row-level security policies really isolate games.

Roles are cluster-wide in PostgreSQL, therefore this module never runs from a
migration: migrations also run on disposable ``*_test`` databases of the same
cluster. The provisioning script and the PostgreSQL test fixtures call it with
an explicit role name. Grants are per database: the caller's owner connection
selects the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import Connection

APPLICATION_SCHEMAS: Final = ("public", "game_data_v2")
_ROLE_NAME: Final = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SCRAM_ITERATIONS: Final = 4096
# The application role may read the Alembic revision (startup head guard) but
# never move it.
_READ_ONLY_TABLES: Final = ("public.alembic_version",)


class DatabaseRoleError(RuntimeError):
    """Stable fail-closed provisioning failure."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class ApplicationRoleSpec:
    role_name: str
    password: str | None
    login: bool = True


@dataclass(frozen=True, slots=True)
class ApplicationRoleReport:
    role_name: str
    database_name: str
    owner_role: str
    exists: bool
    can_login: bool
    superuser: bool
    bypass_rls: bool
    create_db: bool
    create_role: bool
    replication: bool
    memberships: tuple[str, ...]
    owned_relations: int
    schemas_without_usage: tuple[str, ...]
    tables_without_dml: tuple[str, ...]
    writable_read_only_tables: tuple[str, ...]
    sequences_without_usage: tuple[str, ...]

    @property
    def compliant(self) -> bool:
        return (
            self.exists
            and not self.superuser
            and not self.bypass_rls
            and not self.create_db
            and not self.create_role
            and not self.replication
            and not self.memberships
            and self.owned_relations == 0
            and not self.schemas_without_usage
            and not self.tables_without_dml
            and not self.writable_read_only_tables
            and not self.sequences_without_usage
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "roleName": self.role_name,
            "databaseName": self.database_name,
            "ownerRole": self.owner_role,
            "exists": self.exists,
            "canLogin": self.can_login,
            "superuser": self.superuser,
            "bypassRls": self.bypass_rls,
            "createDb": self.create_db,
            "createRole": self.create_role,
            "replication": self.replication,
            "memberships": list(self.memberships),
            "ownedRelations": self.owned_relations,
            "schemasWithoutUsage": list(self.schemas_without_usage),
            "tablesWithoutDml": list(self.tables_without_dml),
            "writableReadOnlyTables": list(self.writable_read_only_tables),
            "sequencesWithoutUsage": list(self.sequences_without_usage),
            "compliant": self.compliant,
        }


def scram_sha256_verifier(password: str, *, salt: bytes | None = None) -> str:
    """Return a PostgreSQL SCRAM-SHA-256 verifier for ``password``.

    Sending the verifier instead of the plain password keeps the secret out of
    statement text and server logs.
    """

    if not password:
        raise DatabaseRoleError("DATABASE_ROLE_PASSWORD_REQUIRED", "A login role needs a password.")
    salt_bytes = secrets.token_bytes(16) if salt is None else salt
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, _SCRAM_ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def encode(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    return (
        f"SCRAM-SHA-256${_SCRAM_ITERATIONS}:{encode(salt_bytes)}"
        f"${encode(stored_key)}:{encode(server_key)}"
    )


def provision_application_role(
    connection: Connection, spec: ApplicationRoleSpec
) -> ApplicationRoleReport:
    """Create or align the application role and its grants in this database.

    Idempotent. Runs on the owner connection inside the caller's transaction
    (role DDL and GRANT are transactional in PostgreSQL). The owner must be a
    superuser or hold CREATEROLE; it always owns the schema objects.
    """

    role = _require_role_name(spec.role_name)
    owner = str(connection.execute(text("SELECT current_user")).scalar_one())
    if owner == role:
        raise DatabaseRoleError(
            "DATABASE_ROLE_IS_OWNER",
            "The application role must differ from the schema owner role.",
            details={"roleName": role},
        )
    if spec.login and spec.password is None:
        raise DatabaseRoleError("DATABASE_ROLE_PASSWORD_REQUIRED", "A login role needs a password.")
    attributes = (
        f"{'LOGIN' if spec.login else 'NOLOGIN'} NOSUPERUSER NOBYPASSRLS NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOINHERIT"
    )
    password_clause = ""
    if spec.password is not None:
        verifier = scram_sha256_verifier(spec.password)
        password_clause = f" PASSWORD {_literal(connection, verifier)}"
    exists = (
        connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
        ).one_or_none()
        is not None
    )
    statement = "ALTER ROLE" if exists else "CREATE ROLE"
    connection.exec_driver_sql(f"{statement} {_quote(role)} {attributes}{password_clause}")
    memberships = _memberships(connection, role)
    if memberships:
        raise DatabaseRoleError(
            "DATABASE_ROLE_HAS_MEMBERSHIPS",
            "The application role must not inherit or assume another role.",
            details={"roleName": role, "memberships": list(memberships)},
        )

    database = str(connection.execute(text("SELECT current_database()")).scalar_one())
    quoted_role = _quote(role)
    connection.exec_driver_sql(f"GRANT CONNECT ON DATABASE {_quote(database)} TO {quoted_role}")
    for schema in _existing_schemas(connection):
        quoted_schema = _quote(schema)
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role}")
        connection.exec_driver_sql(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "
            f"{quoted_schema} TO {quoted_role}"
        )
        connection.exec_driver_sql(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {quoted_schema} TO {quoted_role}"
        )
        connection.exec_driver_sql(
            f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {quoted_schema} TO {quoted_role}"
        )
    for table in _READ_ONLY_TABLES:
        if _relation_exists(connection, table):
            connection.exec_driver_sql(
                f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {quoted_role}"
            )
    # Objects created later by the owner (Alembic migrations, partitions of a
    # newly provisioned game, a fresh database's game_data_v2 schema) get the
    # same grants without re-running this function.
    default_privileges = f"ALTER DEFAULT PRIVILEGES FOR ROLE {_quote(owner)} GRANT"
    connection.exec_driver_sql(
        f"{default_privileges} SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted_role}"
    )
    connection.exec_driver_sql(f"{default_privileges} USAGE, SELECT ON SEQUENCES TO {quoted_role}")
    connection.exec_driver_sql(f"{default_privileges} EXECUTE ON FUNCTIONS TO {quoted_role}")
    connection.exec_driver_sql(f"{default_privileges} USAGE ON SCHEMAS TO {quoted_role}")
    report = describe_application_role(connection, role)
    if not report.compliant:
        raise DatabaseRoleError(
            "DATABASE_ROLE_NOT_COMPLIANT",
            "The provisioned application role does not meet the least-privilege contract.",
            details=report.as_dict(),
        )
    return report


def describe_application_role(connection: Connection, role_name: str) -> ApplicationRoleReport:
    """Read-only compliance report of the application role in this database."""

    role = _require_role_name(role_name)
    owner = str(connection.execute(text("SELECT current_user")).scalar_one())
    database = str(connection.execute(text("SELECT current_database()")).scalar_one())
    row = (
        connection.execute(
            text(
                """SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
                          rolreplication
                FROM pg_roles WHERE rolname = :role"""
            ),
            {"role": role},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return ApplicationRoleReport(
            role_name=role,
            database_name=database,
            owner_role=owner,
            exists=False,
            can_login=False,
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
    schemas = _existing_schemas(connection)
    owned = connection.execute(
        text(
            """SELECT count(*) FROM pg_class c
            JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = :role"""
        ),
        {"role": role},
    ).scalar_one()
    schemas_without_usage = tuple(
        schema
        for schema in schemas
        if not connection.execute(
            text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"),
            {"role": role, "schema": schema},
        ).scalar_one()
    )
    tables_without_dml = tuple(
        str(name)
        for (name,) in connection.execute(
            text(
                """SELECT format('%I.%I', n.nspname, c.relname)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(CAST(:schemas AS text[]))
                  AND c.relkind IN ('r', 'p') AND NOT c.relispartition
                  AND format('%I.%I', n.nspname, c.relname) <> ALL(CAST(:read_only AS text[]))
                  AND NOT (
                    has_table_privilege(:role, c.oid, 'SELECT')
                    AND has_table_privilege(:role, c.oid, 'INSERT')
                    AND has_table_privilege(:role, c.oid, 'UPDATE')
                    AND has_table_privilege(:role, c.oid, 'DELETE'))
                ORDER BY 1"""
            ),
            {"schemas": list(schemas), "role": role, "read_only": list(_READ_ONLY_TABLES)},
        )
    )
    writable_read_only_tables = tuple(
        table
        for table in _READ_ONLY_TABLES
        if _relation_exists(connection, table)
        and connection.execute(
            text(
                """SELECT has_table_privilege(:role, CAST(:table AS regclass), 'INSERT')
                       OR has_table_privilege(:role, CAST(:table AS regclass), 'UPDATE')
                       OR has_table_privilege(:role, CAST(:table AS regclass), 'DELETE')"""
            ),
            {"role": role, "table": table},
        ).scalar_one()
    )
    sequences_without_usage = tuple(
        str(name)
        for (name,) in connection.execute(
            text(
                """SELECT format('%I.%I', n.nspname, c.relname)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = ANY(CAST(:schemas AS text[])) AND c.relkind = 'S'
                  -- CASE keeps the planner from probing non-sequences first.
                  AND CASE WHEN c.relkind = 'S'
                      THEN NOT has_sequence_privilege(:role, c.oid, 'USAGE') ELSE false END
                ORDER BY 1"""
            ),
            {"schemas": list(schemas), "role": role},
        )
    )
    return ApplicationRoleReport(
        role_name=role,
        database_name=database,
        owner_role=owner,
        exists=True,
        can_login=bool(row["rolcanlogin"]),
        superuser=bool(row["rolsuper"]),
        bypass_rls=bool(row["rolbypassrls"]),
        create_db=bool(row["rolcreatedb"]),
        create_role=bool(row["rolcreaterole"]),
        replication=bool(row["rolreplication"]),
        memberships=_memberships(connection, role),
        owned_relations=int(owned),
        schemas_without_usage=schemas_without_usage,
        tables_without_dml=tables_without_dml,
        writable_read_only_tables=writable_read_only_tables,
        sequences_without_usage=sequences_without_usage,
    )


def _existing_schemas(connection: Connection) -> tuple[str, ...]:
    rows = connection.execute(
        text("SELECT nspname FROM pg_namespace WHERE nspname = ANY(CAST(:names AS text[]))"),
        {"names": list(APPLICATION_SCHEMAS)},
    ).all()
    present = {str(row[0]) for row in rows}
    return tuple(schema for schema in APPLICATION_SCHEMAS if schema in present)


def _memberships(connection: Connection, role: str) -> tuple[str, ...]:
    rows = connection.execute(
        text(
            """SELECT granted.rolname FROM pg_auth_members m
            JOIN pg_roles member ON member.oid = m.member
            JOIN pg_roles granted ON granted.oid = m.roleid
            WHERE member.rolname = :role ORDER BY 1"""
        ),
        {"role": role},
    ).all()
    return tuple(str(row[0]) for row in rows)


def _relation_exists(connection: Connection, qualified_name: str) -> bool:
    return (
        connection.execute(
            text("SELECT to_regclass(:name)"), {"name": qualified_name}
        ).scalar_one_or_none()
        is not None
    )


def _require_role_name(value: str) -> str:
    if _ROLE_NAME.fullmatch(value) is None:
        raise DatabaseRoleError(
            "DATABASE_ROLE_NAME_INVALID",
            "The role name must be a lower-case PostgreSQL identifier.",
            details={"roleName": value},
        )
    return value


def _quote(identifier: str) -> str:
    if _ROLE_NAME.fullmatch(identifier) is None:
        raise DatabaseRoleError(
            "DATABASE_ROLE_IDENTIFIER_INVALID",
            "A generated SQL identifier is invalid.",
            details={"identifier": identifier},
        )
    return f'"{identifier}"'


def _literal(connection: Connection, value: str) -> str:
    return str(
        connection.execute(text("SELECT quote_literal(:value)"), {"value": value}).scalar_one()
    )


__all__ = [
    "APPLICATION_SCHEMAS",
    "ApplicationRoleReport",
    "ApplicationRoleSpec",
    "DatabaseRoleError",
    "describe_application_role",
    "provision_application_role",
    "scram_sha256_verifier",
]
