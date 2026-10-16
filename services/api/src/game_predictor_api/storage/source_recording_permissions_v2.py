"""Current recording boundary: frozen v1 plus the exact Alembic0162 overload."""

from __future__ import annotations

from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from game_predictor_api.storage import source_recording_permissions as v1
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_SEQUENCES as PRIVATE_SEQUENCES,
)
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_TABLES as PRIVATE_TABLES,
)
from game_predictor_api.storage.source_recording_permissions import (
    grant_recording_capability_dependencies as grant_recording_capability_dependencies,
)
from game_predictor_api.storage.source_recording_permissions import (
    provision_recording_capability as provision_recording_capability,
)
from game_predictor_api.storage.source_recording_permissions import (
    validate_recording_capability as validate_recording_capability,
)

SOURCE_RECORDING_V2_FUNCTION: Final = (
    "public.resolve_own_groups(uuid,uuid[],uuid,integer,uuid,uuid)"
)


def _required(connection: Connection) -> bool:
    # This real schema marker already exists during upgrade, before Alembic
    # moves version_num. Do not infer installation from a function name prefix.
    if v1._exists(connection, "game_data_v2.grid_quality_measurements"):
        return True
    if (
        v1._exists(connection, "public.alembic_version")
        and connection.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM public.alembic_version "
                "WHERE version_num='0162_grid_quality_measurements')"
            )
        ).scalar_one()
    ):
        return True
    return bool(
        v1._exists(connection, "public.game_storage_locations")
        and connection.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM public.game_storage_locations "
                "WHERE manifest_version='game-data-v2-manifest-v15')"
            )
        ).scalar_one()
    )


def _function(connection: Connection) -> RowMapping | None:
    return (
        connection.execute(
            text("""
            SELECT p.oid, owner.rolname AS owner, p.prosecdef, p.proconfig,
              EXISTS(SELECT 1 FROM pg_catalog.aclexplode(
                COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner)))
                WHERE grantee=0 AND privilege_type='EXECUTE') AS public_execute
            FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner
            WHERE p.oid=pg_catalog.to_regprocedure(:signature)
            """),
            {"signature": SOURCE_RECORDING_V2_FUNCTION},
        )
        .mappings()
        .one_or_none()
    )


def _permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    v1._quote(role)
    function = _function(connection)
    if function is None:
        return (f"{SOURCE_RECORDING_V2_FUNCTION}:missing",) if _required(connection) else ()
    from game_predictor_api.storage.database_roles import DatabaseRoleError

    try:
        capability = validate_recording_capability(connection)
    except DatabaseRoleError as error:
        return (error.code,)
    errors: list[str] = []
    if role == capability:
        errors.append("RECORDING_RUNTIME_IS_CAPABILITY")
    if function["owner"] != capability:
        errors.append(f"{SOURCE_RECORDING_V2_FUNCTION}:owner")
    if function["public_execute"]:
        errors.append(f"{SOURCE_RECORDING_V2_FUNCTION}:public_execute")
    if not connection.execute(
        text("SELECT has_function_privilege(:role,:oid,'EXECUTE')"),
        {"role": role, "oid": function["oid"]},
    ).scalar_one():
        errors.append(f"{SOURCE_RECORDING_V2_FUNCTION}:runtime_execute")
    if not function["prosecdef"] or function["proconfig"] != ["search_path=pg_catalog"]:
        errors.append(f"{SOURCE_RECORDING_V2_FUNCTION}:security")
    return tuple(errors)


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    """Audit the union of the frozen registry and the one new exact signature."""
    return (
        *v1.recording_permission_errors(connection, role),
        *_permission_errors(connection, role),
    )


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    """Reapply both versions after broad/default grants without adopting objects."""
    v1.enforce_recording_permissions(connection, application_role)
    function = _function(connection)
    if function is not None:
        capability = validate_recording_capability(connection)
        if application_role == capability:
            v1._fail(
                "RECORDING_RUNTIME_IS_CAPABILITY", "Runtime cannot use the recording capability."
            )
        role = v1._quote(application_role)
        connection.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON FUNCTION {SOURCE_RECORDING_V2_FUNCTION} FROM {role}, PUBLIC"
        )
        connection.exec_driver_sql(
            f"GRANT EXECUTE ON FUNCTION {SOURCE_RECORDING_V2_FUNCTION} TO {role}"
        )
    errors = _permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
