"""Private release history and own-game incremental preview capability."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import source_recording_permissions as v1
from . import source_recording_permissions_v5 as v5

PRIVATE_TABLES = (*v5.PRIVATE_TABLES, "public.recording_photo_reservation_releases")
PRIVATE_SEQUENCES = v5.PRIVATE_SEQUENCES
SAFE = "public.recording_photo_context_v2(uuid,uuid[])"
INTERNAL = "public.recording_photo_context_data_v2(uuid,uuid[],boolean)"


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    errors = list(v5.recording_permission_errors(connection, role))
    if not v1._exists(connection, PRIVATE_TABLES[-1]):
        return tuple(errors)
    owner = v1.validate_recording_capability(connection)
    for signature in (SAFE, INTERNAL):
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
            errors.append(f"{signature}:incremental_permissions")
    if connection.scalar(
        text("SELECT has_table_privilege(:r,:t,'SELECT,INSERT,UPDATE,DELETE')"),
        {"r": role, "t": PRIVATE_TABLES[-1]},
    ):
        errors.append("recording_photo_reservation_releases:runtime_access")
    return tuple(errors)


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    v5.enforce_recording_permissions(connection, application_role)
    if not v1._exists(connection, PRIVATE_TABLES[-1]):
        return
    role = v1._quote(application_role)
    connection.exec_driver_sql(f"REVOKE ALL ON {PRIVATE_TABLES[-1]} FROM {role},PUBLIC")
    for signature in (SAFE, INTERNAL):
        connection.exec_driver_sql(f"REVOKE ALL ON FUNCTION {signature} FROM {role},PUBLIC")
    connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {SAFE} TO {role}")
    errors = recording_permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
