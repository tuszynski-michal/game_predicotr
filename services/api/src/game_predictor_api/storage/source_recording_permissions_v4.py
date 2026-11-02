"""Exact runtime grants for the additive photo-only registry capability."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from game_predictor_api.storage import source_recording_permissions as v1
from game_predictor_api.storage import source_recording_permissions_v3 as v3

PRIVATE_TABLES = (*v3.PRIVATE_TABLES, "public.recording_photo_uses")
PRIVATE_SEQUENCES = v3.PRIVATE_SEQUENCES
SAFE = ("public.recording_photo_context_v1(uuid,uuid[])",)
INTERNAL = (
    "public.recording_photo_cohort_v1(uuid,jsonb,text)",
    "public.recording_cohort_command_legacy_v3(uuid,jsonb,text)",
)


def recording_permission_errors(connection: Connection, role: str) -> tuple[str, ...]:
    errors = list(v3.recording_permission_errors(connection, role))
    if not v1._exists(connection, "public.recording_photo_uses"):
        return tuple(errors)
    capability = v1.validate_recording_capability(connection)
    for signature in (*SAFE, *INTERNAL):
        row = (
            connection.execute(
                text(
                    "SELECT p.prosecdef,p.proconfig,r.rolname owner, "
                    "has_function_privilege(:role,p.oid,'EXECUTE') permitted, "
                    "EXISTS(SELECT 1 FROM aclexplode("
                    "COALESCE(p.proacl,acldefault('f',p.proowner))) "
                    "WHERE grantee=0 AND privilege_type='EXECUTE') public_execute "
                    "FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner "
                    "WHERE p.oid=to_regprocedure(:signature)"
                ),
                {"role": role, "signature": signature},
            )
            .mappings()
            .one_or_none()
        )
        if (
            not row
            or row["owner"] != capability
            or not row["prosecdef"]
            or (
                row["public_execute"]
                or row["proconfig"] != ["search_path=pg_catalog"]
                or row["permitted"] != (signature in SAFE)
            )
        ):
            errors.append(f"{signature}:photo_permissions")
    if connection.scalar(
        text(
            "SELECT has_table_privilege(:role,'public.recording_photo_uses',"
            "'SELECT,INSERT,UPDATE,DELETE')"
        ),
        {"role": role},
    ):
        errors.append("recording_photo_uses:runtime_access")
    return tuple(errors)


def enforce_recording_permissions(connection: Connection, application_role: str) -> None:
    v3.enforce_recording_permissions(connection, application_role)
    if not v1._exists(connection, "public.recording_photo_uses"):
        return
    role = v1._quote(application_role)
    connection.exec_driver_sql(f"REVOKE ALL ON public.recording_photo_uses FROM {role}, PUBLIC")
    columns = connection.execute(
        text(
            "SELECT attname FROM pg_attribute WHERE attrelid="
            "'public.recording_photo_uses'::regclass AND attnum>0 AND NOT attisdropped"
        )
    ).scalars()
    names = ",".join(v1._quote(name) for name in columns)
    for permission in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
        connection.exec_driver_sql(
            f"REVOKE {permission} ({names}) ON public.recording_photo_uses FROM {role},PUBLIC"
        )
    for signature in (*SAFE, *INTERNAL):
        connection.exec_driver_sql(f"REVOKE ALL ON FUNCTION {signature} FROM {role},PUBLIC")
        if signature in SAFE:
            connection.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")
    errors = recording_permission_errors(connection, application_role)
    if errors:
        v1._fail("RECORDING_PERMISSION_NOT_COMPLIANT", "; ".join(errors))
