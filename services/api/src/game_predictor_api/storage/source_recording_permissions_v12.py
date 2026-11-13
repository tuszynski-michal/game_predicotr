"""Gate v5 binding (D-609) uses the existing non-login recording capability."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import source_recording_permissions as v1
from . import source_recording_permissions_v11 as previous

SAFE = ("public.recording_cohort_command_v9(uuid,jsonb,text)",)
INTERNAL = ("public.recording_correction_report_bind_v7(uuid,jsonb,text)",)
PRIVATE_TABLES = previous.PRIVATE_TABLES
PRIVATE_SEQUENCES = previous.PRIVATE_SEQUENCES


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    errors = list(previous.recording_permission_errors(connection, role))
    if connection.scalar(text("SELECT to_regprocedure(:s)"), {"s": SAFE[0]}) is None:
        return tuple(errors)
    owner = v1.validate_recording_capability(connection)
    for signature in (*SAFE, *INTERNAL):
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
            or row["permitted"] != (signature in SAFE)
        ):
            errors.append(f"{signature}:gate_v5_permissions")
    return tuple(errors)


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    previous.enforce_recording_permissions(connection, application_role)
    if connection.scalar(text("SELECT to_regprocedure(:s)"), {"s": SAFE[0]}) is None:
        return
    role = v1._quote(application_role)
    for signature in (*SAFE, *INTERNAL):
        connection.exec_driver_sql(f"REVOKE ALL ON FUNCTION {signature} FROM {role},PUBLIC")
    for signature in SAFE:
        connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")
    errors = recording_permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
