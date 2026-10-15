"""Explicit per-database recording capability and durable runtime exclusions.

Role creation is an operator provisioning operation. Alembic only validates the
identity and installs objects; neither validation nor grant enforcement creates
or repairs a cluster-global role.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Final, NoReturn

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

PRIVATE_TABLES: Final = tuple(
    f"public.{name}"
    for name in (
        "recording_groups",
        "recording_occurrences",
        "recording_evidence",
        "recording_role_heads",
        "recording_commands",
    )
)
PRIVATE_SEQUENCES: Final = ("public.recording_evidence_ordinal_seq",)
SAFE_FUNCTIONS: Final = (
    "public.attest_own_source_ids(uuid,uuid[])",
    "public.recording_command(uuid,jsonb,text)",
    "public.resolve_own_groups(uuid,uuid[],uuid,integer,uuid)",
)
RECORDING_FUNCTIONS: Final = (
    *SAFE_FUNCTIONS,
    "public.recording_digest_v1(jsonb)",
    "public.recording_immutable_v1()",
    "public.recording_scope_v1(uuid)",
    "public.recording_closure_v1(uuid[])",
    "public.recording_proof_v1(uuid[])",
    "public.recording_group_view_v1(uuid,uuid,uuid)",
    "public.recording_invalidate_dependents_v1(uuid)",
)
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_MARKER_VERSION = "game-predictor-recording-capability-v1"


def _fail(code: str, message: str) -> NoReturn:
    # Avoid a module cycle: database_roles includes this compliance boundary.
    from game_predictor_api.storage.database_roles import DatabaseRoleError

    raise DatabaseRoleError(code, message)


def _quote(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        _fail("DATABASE_ROLE_IDENTIFIER_INVALID", "Invalid recording role identifier.")
    return f'"{value}"'


def _identity(connection: Connection) -> tuple[str, int, str]:
    name, oid = connection.execute(
        text("SELECT datname, oid FROM pg_catalog.pg_database WHERE datname=current_database()")
    ).one()
    digest = hashlib.sha256(f"{name}:{oid}".encode()).hexdigest()[:24]
    return str(name), int(oid), f"gp_rec_{digest}"


def _role(connection: Connection, name: str) -> RowMapping | None:
    return (
        connection.execute(
            text("""
        SELECT oid, rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
               rolreplication, rolinherit,
               pg_catalog.shobj_description(oid, 'pg_authid') AS marker
        FROM pg_catalog.pg_roles WHERE rolname=:role
    """),
            {"role": name},
        )
        .mappings()
        .one_or_none()
    )


def provision_recording_capability(connection: Connection) -> str:
    """Create a capability once; an existing identity must already be valid.

    The caller owns the transaction. Never ALTER, DROP or adopt a colliding role.
    The nonce and role OID form the ownership receipt stored in the role comment.
    """
    database, database_oid, role = _identity(connection)
    if _role(connection, role) is not None:
        return validate_recording_capability(connection)
    connection.exec_driver_sql(
        f"CREATE ROLE {_quote(role)} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOINHERIT"
    )
    row = _role(connection, role)
    assert row is not None
    marker = json.dumps(
        {
            "kind": _MARKER_VERSION,
            "databaseName": database,
            "databaseOid": database_oid,
            "roleOid": int(row["oid"]),
            "nonce": secrets.token_hex(32),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    literal = connection.execute(
        text("SELECT quote_literal(:value)"),
        {
            "value": marker,
        },
    ).scalar_one()
    connection.exec_driver_sql(f"COMMENT ON ROLE {_quote(role)} IS {literal}")
    return validate_recording_capability(connection)


def validate_recording_capability(connection: Connection) -> str:
    """Fail closed on missing, cloned, renamed, replaced or broadened capability."""
    database, database_oid, role = _identity(connection)
    row = _role(connection, role)
    if row is None:
        _fail(
            "RECORDING_CAPABILITY_REQUIRED",
            "Provision --recording-capability explicitly before the recording migration.",
        )
    assert row is not None
    try:
        marker = json.loads(str(row["marker"]))
    except (TypeError, ValueError):
        marker = None
    expected = {
        "kind": _MARKER_VERSION,
        "databaseName": database,
        "databaseOid": database_oid,
        "roleOid": int(row["oid"]),
    }
    if (
        not isinstance(marker, dict)
        or any(marker.get(key) != value for key, value in expected.items())
        or not isinstance(marker.get("nonce"), str)
        or re.fullmatch(r"[0-9a-f]{64}", marker.get("nonce", "")) is None
    ):
        _fail("RECORDING_CAPABILITY_IDENTITY", "Recording capability ownership marker differs.")
    if any(
        bool(row[name])
        for name in (
            "rolcanlogin",
            "rolsuper",
            "rolbypassrls",
            "rolcreatedb",
            "rolcreaterole",
            "rolreplication",
            "rolinherit",
        )
    ):
        _fail("RECORDING_CAPABILITY_ATTRIBUTES", "Recording capability attributes are unsafe.")
    if connection.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
                      WHERE member=:oid OR roleid=:oid)
    """),
        {"oid": row["oid"]},
    ).scalar_one():
        _fail("RECORDING_CAPABILITY_MEMBERSHIP", "Recording capability must have no memberships.")
    return role


def _exists(connection: Connection, name: str) -> bool:
    return (
        connection.execute(
            text("SELECT to_regclass(:name)"),
            {
                "name": name,
            },
        ).scalar_one_or_none()
        is not None
    )


def _functions(connection: Connection) -> list[RowMapping]:
    # Prefixes and overloads are not ownership evidence. Only these exact
    # versioned signatures belong to this registry and may have grants changed.
    return list(
        connection.execute(
            text("""
        SELECT p.oid, required.signature AS requested_signature,
               p.oid::regprocedure::text AS signature,
               format('%I.%I(%s)', n.nspname, p.proname,
                      pg_catalog.oidvectortypes(p.proargtypes)) AS qualified_signature,
               p.prosecdef, p.proconfig, owner.rolname AS owner,
               p.oid = ANY(ARRAY[to_regprocedure(:attest)::oid,
                   to_regprocedure(:command)::oid, to_regprocedure(:resolve)::oid]) AS safe,
               EXISTS(SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner)))
                      WHERE grantee=0 AND privilege_type='EXECUTE') AS public_execute
        FROM unnest(CAST(:recording_functions AS text[])) AS required(signature)
        JOIN pg_catalog.pg_proc p ON p.oid=to_regprocedure(required.signature)
        JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner
        ORDER BY p.oid
    """),
            {
                **dict(zip(("attest", "command", "resolve"), SAFE_FUNCTIONS, strict=True)),
                "recording_functions": list(RECORDING_FUNCTIONS),
            },
        )
        .mappings()
        .all()
    )


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    """Reapply exact private exclusions after broad/default grants or migration DDL."""
    quoted_role = _quote(application_role)
    if not any(_exists(connection, table) for table in PRIVATE_TABLES):
        return
    capability = validate_recording_capability(connection)
    if application_role == capability:
        _fail("RECORDING_RUNTIME_IS_CAPABILITY", "Runtime cannot use the recording capability.")
    for table in PRIVATE_TABLES:
        if not _exists(connection, table):
            continue
        connection.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM {quoted_role}, PUBLIC"
        )
        columns = connection.execute(
            text("""
            SELECT attname FROM pg_catalog.pg_attribute
            WHERE attrelid=to_regclass(:table) AND attnum>0 AND NOT attisdropped
            ORDER BY attnum
        """),
            {"table": table},
        )
        names = ", ".join(_quote(str(name)) for (name,) in columns)
        if names:
            for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                connection.exec_driver_sql(
                    f"REVOKE {privilege} ({names}) ON TABLE {table} FROM {quoted_role}, PUBLIC"
                )
    for sequence in PRIVATE_SEQUENCES:
        if _exists(connection, sequence):
            connection.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON SEQUENCE {sequence} FROM {quoted_role}, PUBLIC"
            )
    for function in _functions(connection):
        signature = str(function["qualified_signature"])
        connection.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM {quoted_role}, PUBLIC"
        )
        if function["safe"]:
            connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {signature} TO {quoted_role}")
    errors = recording_permission_errors(connection, application_role)
    if errors:
        _fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))


def grant_recording_capability_dependencies(connection: Connection) -> None:
    """Grant the exact existing-source and invalidation bridge dependencies.

    Called by migration after validation. Does not transfer ownership or change
    the current game GUC. Source SELECT remains subject to forced source RLS.
    """
    capability = _quote(validate_recording_capability(connection))
    connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public, game_data_v2 TO {capability}")
    for table in ("game_data_v2.source_images", "public.games", "public.game_storage_locations"):
        connection.exec_driver_sql(f"GRANT SELECT ON TABLE {table} TO {capability}")
    connection.exec_driver_sql(
        "GRANT SELECT (game_id,source_image_id,source_checksum_sha256,"
        "normalized_pixel_checksum_sha256,normalization_adapter_version,"
        "oriented_width,oriented_height) ON "
        f"game_data_v2.image_source_geometry_revisions TO {capability}"
    )
    connection.exec_driver_sql(f"GRANT SELECT (id) ON public.grid_model_families TO {capability}")
    connection.exec_driver_sql(
        f"GRANT EXECUTE ON FUNCTION game_data_v2.current_game_id_v1() TO {capability}"
    )
    connection.exec_driver_sql(
        f"GRANT SELECT (id) ON public.grid_model_evaluation_reports TO {capability}"
    )
    connection.exec_driver_sql(
        "GRANT INSERT (id,report_id,reason,actor) ON "
        f"public.grid_model_evaluation_invalidations TO {capability}"
    )


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    """Read-only effective runtime and PUBLIC compliance for this exact registry."""
    _quote(role)
    if not any(_exists(connection, table) for table in PRIVATE_TABLES):
        return ()
    from game_predictor_api.storage.database_roles import DatabaseRoleError

    try:
        capability = validate_recording_capability(connection)
    except DatabaseRoleError as error:
        return (error.code,)
    errors: list[str] = []
    for name in (*PRIVATE_TABLES, *PRIVATE_SEQUENCES):
        if not _exists(connection, name):
            errors.append(f"{name}:missing")
            continue
        row = (
            connection.execute(
                text("""
            SELECT owner.rolname AS owner,
               CASE WHEN c.relkind='S' THEN
                   has_sequence_privilege(:role,c.oid,'USAGE,SELECT,UPDATE')
               ELSE has_table_privilege(:role,c.oid,
                        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(:role,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')
               END AS runtime_access,
               EXISTS(SELECT 1 FROM aclexplode(COALESCE(c.relacl,
                    acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,
                               c.relowner))) WHERE grantee=0) OR
               EXISTS(SELECT 1 FROM pg_catalog.pg_attribute a,
                    LATERAL aclexplode(a.attacl) acl
                    WHERE a.attrelid=c.oid AND acl.grantee=0) AS public_access
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles owner ON owner.oid=c.relowner
            WHERE c.oid=to_regclass(:name)
        """),
                {"role": role, "name": name},
            )
            .mappings()
            .one()
        )
        if row["owner"] != capability:
            errors.append(f"{name}:owner")
        if row["runtime_access"]:
            errors.append(f"{name}:runtime_access")
        if row["public_access"]:
            errors.append(f"{name}:public_access")
    functions = _functions(connection)
    present_signatures = {str(row["requested_signature"]) for row in functions}
    for signature in RECORDING_FUNCTIONS:
        if signature not in present_signatures:
            errors.append(f"{signature}:missing")
    for function in functions:
        signature = str(function["qualified_signature"])
        if function["owner"] != capability:
            errors.append(f"{signature}:owner")
        if function["public_execute"]:
            errors.append(f"{signature}:public_execute")
        execute = connection.execute(
            text("SELECT has_function_privilege(:role,:oid,'EXECUTE')"),
            {"role": role, "oid": function["oid"]},
        ).scalar_one()
        if bool(execute) != bool(function["safe"]):
            errors.append(f"{signature}:runtime_execute")
        if function["safe"] and (
            not function["prosecdef"] or function["proconfig"] != ["search_path=pg_catalog"]
        ):
            errors.append(f"{signature}:security")
    return tuple(errors)
