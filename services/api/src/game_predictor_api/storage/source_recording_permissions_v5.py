"""The report-v3 binder is an internal capability, never an application grant."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import source_recording_permissions as v1
from . import source_recording_permissions_v4 as v4

PRIVATE_TABLES = v4.PRIVATE_TABLES
PRIVATE_SEQUENCES = v4.PRIVATE_SEQUENCES

SIGNATURE = "public.recording_correction_report_bind_v1(uuid,jsonb,text)"
VERSION_COLUMNS = ("id", "family_id", "base_version_id", "manifest_sha256")


def grant_recording_capability_dependencies(connection: Connection) -> None:
    capability = v1._quote(v1.validate_recording_capability(connection))
    connection.exec_driver_sql(
        f"GRANT SELECT ({','.join(VERSION_COLUMNS)}) ON public.grid_model_versions TO {capability}"
    )


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    errors = list(v4.recording_permission_errors(connection, role))
    if not connection.scalar(text("SELECT to_regprocedure(:s) IS NOT NULL"), {"s": SIGNATURE}):
        return tuple(errors)
    capability = v1.validate_recording_capability(connection)
    for column in VERSION_COLUMNS:
        if not connection.scalar(
            text("SELECT has_column_privilege(:r,'public.grid_model_versions',:c,'SELECT')"),
            {"r": capability, "c": column},
        ):
            errors.append(f"recording_correction_report_bind_v1:missing_column:{column}")
    row = (
        connection.execute(
            text("""SELECT p.prosecdef,p.proconfig,r.rolname owner,
      has_function_privilege(:role,p.oid,'EXECUTE') permitted,
      EXISTS(SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner)))
        WHERE grantee=0 AND privilege_type='EXECUTE') public_execute
      FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=to_regprocedure(:s)"""),
            {"role": role, "s": SIGNATURE},
        )
        .mappings()
        .one()
    )
    if (
        not row["prosecdef"]
        or row["proconfig"] != ["search_path=pg_catalog"]
        or row["owner"] != v1.validate_recording_capability(connection)
        or row["permitted"]
        or row["public_execute"]
    ):
        errors.append("recording_correction_report_bind_v1:permissions")
    return tuple(errors)


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    v4.enforce_recording_permissions(connection, application_role)
    if connection.scalar(text("SELECT to_regprocedure(:s) IS NOT NULL"), {"s": SIGNATURE}):
        grant_recording_capability_dependencies(connection)
        connection.exec_driver_sql(
            f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM {v1._quote(application_role)},PUBLIC"
        )
    errors = recording_permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
