"""Current registry compliance includes only the two exact v3 cohort entries."""

from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from game_predictor_api.storage import source_recording_permissions as v1
from game_predictor_api.storage import source_recording_permissions_v2 as v2
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_SEQUENCES as PRIVATE_SEQUENCES,
)
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_TABLES as PRIVATE_TABLES,
)
from game_predictor_api.storage.source_recording_permissions import (
    provision_recording_capability as provision_recording_capability,
)
from game_predictor_api.storage.source_recording_permissions import (
    validate_recording_capability as validate_recording_capability,
)

SOURCE_RECORDING_V3_FUNCTIONS: Final = (
    "public.recording_cohort_page_v3(uuid,uuid,uuid,integer)",
    "public.recording_cohort_command_v3(uuid,jsonb,text)",
)
COHORT_HELPER_FUNCTIONS: Final = (
    "game_data_v2.grid_cohort_immutable_v1()",
    "game_data_v2.grid_cohort_notice_v1()",
)
CAPABILITY_COLUMNS: Final = {
    "game_data_v2.grid_training_cohorts": (
        "game_id",
        "id",
        "revision",
        "status",
        "document",
        "manifest_sha256",
    ),
    "game_data_v2.grid_training_cohort_members": (
        "game_id",
        "cohort_id",
        "source_id",
        "role",
        "frozen",
        "live_source_image_id",
    ),
    "public.grid_model_evaluation_reports": (
        "id",
        "version_id",
        "producer",
        "report_json",
        "report_sha256",
    ),
}


def _functions(connection: Connection) -> list[RowMapping]:
    return list(
        connection.execute(
            text("""
      SELECT required.signature,p.oid,owner.rolname AS owner,p.prosecdef,p.proconfig,
        EXISTS(SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,
          pg_catalog.acldefault('f',p.proowner))) WHERE grantee=0
          AND privilege_type='EXECUTE') AS public_execute
      FROM pg_catalog.unnest(CAST(:signatures AS text[])) required(signature)
      JOIN pg_catalog.pg_proc p ON p.oid=pg_catalog.to_regprocedure(required.signature)
      JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner
    """),
            {"signatures": list((*SOURCE_RECORDING_V3_FUNCTIONS, *COHORT_HELPER_FUNCTIONS))},
        ).mappings()
    )


def grant_recording_capability_dependencies(connection: Connection) -> None:
    v1.grant_recording_capability_dependencies(connection)
    capability = v1._quote(validate_recording_capability(connection))
    if v1._exists(connection, "game_data_v2.grid_training_cohorts"):
        for table, columns in CAPABILITY_COLUMNS.items():
            connection.exec_driver_sql(
                f"GRANT SELECT ({','.join(columns)}) ON TABLE {table} TO {capability}"
            )


def _errors(connection: Connection, role: str) -> tuple[str, ...]:
    required = v1._exists(connection, "game_data_v2.grid_training_cohorts")
    functions = _functions(connection)
    if not required and not functions:
        return ()
    from game_predictor_api.storage.database_roles import DatabaseRoleError

    try:
        capability = validate_recording_capability(connection)
    except DatabaseRoleError as error:
        return (error.code,)
    errors: list[str] = []
    if role == capability:
        errors.append("RECORDING_RUNTIME_IS_CAPABILITY")
    present = {row["signature"] for row in functions}
    for signature in (*SOURCE_RECORDING_V3_FUNCTIONS, *COHORT_HELPER_FUNCTIONS):
        if signature not in present:
            errors.append(f"{signature}:missing")
    for row in functions:
        signature = row["signature"]
        safe = signature in SOURCE_RECORDING_V3_FUNCTIONS
        if safe and row["owner"] != capability:
            errors.append(f"{signature}:owner")
        if row["public_execute"]:
            errors.append(f"{signature}:public_execute")
        if (safe and not row["prosecdef"]) or row["proconfig"] != ["search_path=pg_catalog"]:
            errors.append(f"{signature}:security")
        if (
            bool(
                connection.execute(
                    text("SELECT has_function_privilege(:role,:oid,'EXECUTE')"),
                    {"role": role, "oid": row["oid"]},
                ).scalar_one()
            )
            != safe
        ):
            errors.append(f"{signature}:runtime_execute")
    for table, columns in CAPABILITY_COLUMNS.items():
        if not v1._exists(connection, table):
            errors.append(f"{table}:missing")
            continue
        for column in columns:
            if not connection.execute(
                text("SELECT has_column_privilege(:role,:table,:column,'SELECT')"),
                {"role": capability, "table": table, "column": column},
            ).scalar_one():
                errors.append(f"{table}.{column}:capability_select")
    return tuple(errors)


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    return (*v2.recording_permission_errors(connection, role), *_errors(connection, role))


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    if v1._exists(connection, "game_data_v2.grid_training_cohorts") and (
        application_role == validate_recording_capability(connection)
    ):
        v1._fail("RECORDING_RUNTIME_IS_CAPABILITY", "Runtime cannot use the recording capability.")
    v2.enforce_recording_permissions(connection, application_role)
    if v1._exists(connection, "game_data_v2.grid_training_cohorts"):
        grant_recording_capability_dependencies(connection)
    role = v1._quote(application_role)
    for row in _functions(connection):
        signature = row["signature"]
        connection.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM {role}, PUBLIC"
        )
        if signature in SOURCE_RECORDING_V3_FUNCTIONS:
            connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")
    errors = _errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
