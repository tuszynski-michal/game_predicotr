"""Screen correction command is public to runtime; its implementation remains private."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import source_recording_permissions as v1
from . import source_recording_permissions_v6 as v6

SAFE = "public.recording_cohort_command_v4(uuid,jsonb,text)"
INTERNAL = (
    "public.recording_photo_cohort_v2(uuid,jsonb,text)",
    "public.recording_correction_report_bind_v2(uuid,jsonb,text)",
)
PRIVATE_TABLES = v6.PRIVATE_TABLES
PRIVATE_SEQUENCES = v6.PRIVATE_SEQUENCES


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    errors = list(v6.recording_permission_errors(connection, role))
    if connection.scalar(text("SELECT to_regprocedure(:s)"), {"s": SAFE}) is None:
        return tuple(errors)
    owner = v1.validate_recording_capability(connection)
    for signature in (SAFE, *INTERNAL):
        row = (
            connection.execute(
                text("""SELECT p.prosecdef,p.proconfig,r.rolname owner,
        has_function_privilege(:role,p.oid,'EXECUTE') permitted,
        EXISTS(SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner)))
        WHERE grantee=0 AND privilege_type='EXECUTE') public_execute
        FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=to_regprocedure(:s)"""),
                {"role": role, "s": signature},
            )
            .mappings()
            .one_or_none()
        )
        if (
            not row
            or row["owner"] != owner
            or not row["prosecdef"]
            or row["proconfig"] != ["search_path=pg_catalog"]
            or row["public_execute"]
            or row["permitted"] != (signature == SAFE)
        ):
            errors.append(f"{signature}:screen_permissions")
    return tuple(errors)


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    v6.enforce_recording_permissions(connection, application_role)
    if connection.scalar(text("SELECT to_regprocedure(:s)"), {"s": SAFE}) is None:
        return
    role = v1._quote(application_role)
    for signature in (SAFE, *INTERNAL):
        connection.exec_driver_sql(f"REVOKE ALL ON FUNCTION {signature} FROM {role},PUBLIC")
    connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {SAFE} TO {role}")
    errors = recording_permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
