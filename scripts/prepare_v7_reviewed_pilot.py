"""Create/check only the task-owned, empty V7 pilot database and new runtime role.

Run each invocation with an external <=120 second process timeout. This tool
never copies domain data, changes the source database or activates the gate.
Secrets stay in the narrowly ignored task runtime configuration.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    describe_application_role,
    provision_application_role,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

DATABASE = "game_predictor_v7_pilot"
ROLE = "game_predictor_v7_pilot_app"
HEAD = "0147_merge_v7_main"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".claude" / "v7-pilot-runtime"
SETTINGS = RUNTIME / "settings.json"


def _engine(url: URL, *, autocommit: bool = False) -> Engine:
    if url.host not in ("localhost", "127.0.0.1", "::1") or url.query:
        raise ValueError("Pilot connections require a direct local URL without query overrides.")
    return create_engine(
        url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT" if autocommit else "READ COMMITTED",
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000 -c lock_timeout=3000",
        },
    )


def _load() -> dict[str, object]:
    value = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("task") != "TASK-0853"
        or value.get("worktree") != str(ROOT)
    ):
        raise ValueError("Pilot settings belong to another task/worktree.")
    owner = make_url(str(value["ownerDatabaseUrl"]))
    app = make_url(str(value["databaseUrl"]))
    _require_local_urls(owner, app)
    if (
        owner.database != DATABASE
        or app.database != DATABASE
        or app.username != ROLE
        or owner.username == ROLE
        or (owner.host, owner.port) != (app.host, app.port)
        or owner.host not in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("Pilot URLs must exclusively select the exact isolated database/role.")
    return value


def _require_local_urls(owner: URL, runtime: URL) -> None:
    if (
        owner.query
        or runtime.query
        or owner.host not in ("localhost", "127.0.0.1", "::1")
        or runtime.host not in ("localhost", "127.0.0.1", "::1")
        or (owner.host, owner.port, owner.database)
        != (runtime.host, runtime.port, runtime.database)
    ):
        raise ValueError("Pilot bootstrap requires matching direct local URLs without queries.")


def bootstrap() -> dict[str, object]:
    if SETTINGS.exists():
        raise ValueError(
            "Settings already exist: use migrate/provision/check for an owned bootstrap."
        )
    subprocess.run(["git", "check-ignore", "-q", str(SETTINGS)], cwd=ROOT, timeout=10, check=True)
    source_settings = ApiSettings.from_environment()
    owner_source = make_url(source_settings.owner_database_url)
    runtime_source = make_url(source_settings.database_url)
    _require_local_urls(owner_source, runtime_source)
    if owner_source.host not in ("localhost", "127.0.0.1", "::1") or (
        owner_source.host,
        owner_source.port,
        owner_source.database,
    ) != (runtime_source.host, runtime_source.port, runtime_source.database):
        raise ValueError("Bootstrap requires matching local owner/runtime source targets.")
    if owner_source.username == ROLE:
        raise ValueError("Existing owner cannot be the new runtime role.")
    admin = _engine(owner_source.set(database="postgres"), autocommit=True)
    try:
        with admin.connect() as connection:
            if connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)"),
                {"name": DATABASE},
            ):
                raise ValueError("Proposed pilot database already exists; refuse adoption.")
            if connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:name)"), {"name": ROLE}
            ):
                raise ValueError("Proposed new application role already exists; refuse ALTER ROLE.")
            owner = str(connection.scalar(text("SELECT current_user")))
            quote = connection.dialect.identifier_preparer.quote
            owner_url = owner_source.set(database=DATABASE)
            app_url = owner_url.set(username=ROLE, password=secrets.token_urlsafe(32))
            value = {
                "task": "TASK-0853",
                "worktree": str(ROOT),
                "bootstrapId": str(uuid4()),
                "databaseName": DATABASE,
                "roleName": ROLE,
                "ownerRole": owner,
                "ownerDatabaseUrl": owner_url.render_as_string(hide_password=False),
                "databaseUrl": app_url.render_as_string(hide_password=False),
                "phase": "creation_planned",
                "head": HEAD,
            }
            RUNTIME.mkdir(parents=True, exist_ok=True)
            with SETTINGS.open("x", encoding="utf-8") as output:
                json.dump(value, output, indent=2)
            # Names were rechecked immediately before this sole cluster-level DDL.
            connection.exec_driver_sql(f"CREATE DATABASE {quote(DATABASE)} OWNER {quote(owner)}")
            value["phase"] = "database_created"
            SETTINGS.write_text(json.dumps(value, indent=2), encoding="utf-8")
            return {
                "status": "created_empty_database",
                "database": DATABASE,
                "owner": owner,
                "newRole": ROLE,
            }
    finally:
        admin.dispose()


def migrate() -> dict[str, object]:
    value = _load()
    url = make_url(str(value["ownerDatabaseUrl"]))
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            _check_owner(connection, value)
            # An interrupted migration may resume only in this recorded new database.
            if value["phase"] not in ("database_created", "schema_migrated", "ready"):
                raise ValueError("Database creation ownership was not durably confirmed.")
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, HEAD)
        # A recorded ready runtime already owns its role. An additive upgrade must
        # not reclassify that role as one that appeared before provisioning.
        if value["phase"] != "ready":
            value["phase"] = "schema_migrated"
        SETTINGS.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return {"status": "migrated", "database": DATABASE, "head": HEAD}
    finally:
        engine.dispose()


def _check_owner(connection: Connection, value: dict[str, object]) -> None:
    current = connection.execute(
        text(
            "SELECT current_database(), current_user, pg_get_userbyid(datdba) "
            "FROM pg_database WHERE datname=current_database()"
        )
    ).one()
    if tuple(current) != (DATABASE, value["ownerRole"], value["ownerRole"]):
        raise ValueError("Current database/owner differs from the recorded isolated bootstrap.")


def provision() -> dict[str, object]:
    value = _load()
    owner_url = make_url(str(value["ownerDatabaseUrl"]))
    app_url = make_url(str(value["databaseUrl"]))
    engine = _engine(owner_url)
    try:
        with engine.begin() as connection:
            _check_owner(connection, value)
            if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != HEAD:
                raise ValueError("Isolated schema must be migrated before provisioning.")
            exists = connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:name)"), {"name": ROLE}
            )
            if exists and value["phase"] != "ready":
                raise ValueError("New role appeared before task provisioning; refuse ALTER ROLE.")
            report = provision_application_role(
                connection, ApplicationRoleSpec(ROLE, app_url.password)
            )
        value["phase"] = "ready"
        SETTINGS.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return {"status": "provisioned_new_runtime_role", **report.as_dict()}
    finally:
        engine.dispose()


def check() -> dict[str, object]:
    value = _load()
    engine = _engine(make_url(str(value["ownerDatabaseUrl"])))
    runtime = _engine(make_url(str(value["databaseUrl"])))
    try:
        with engine.connect() as connection:
            _check_owner(connection, value)
            report = describe_application_role(connection, ROLE)
            head = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
        with runtime.begin() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()
            connection.exec_driver_sql(
                "SELECT singleton FROM public.semi_automatic_selection_v7_activation_gate FOR SHARE"
            )
            connection.exec_driver_sql(
                "SELECT singleton FROM public.semi_automatic_selection_v7_activation_gate "
                "FOR UPDATE"
            )
            privileges = {
                str(name): bool(granted)
                for name, granted in connection.execute(
                    text(
                        "SELECT attname, has_column_privilege(current_user, attrelid, "
                        "attname, 'UPDATE') FROM pg_attribute WHERE "
                        "attrelid='public.semi_automatic_selection_v7_activation_gate'::regclass "
                        "AND attnum>0 AND NOT attisdropped"
                    )
                )
            }
            if {name for name, granted in privileges.items() if granted} != {"singleton"}:
                raise ValueError("Runtime can mutate gate authorization columns or cannot lock.")
        denials: dict[str, str] = {}
        for name, statement, expected in (
            (
                "gate_status",
                "UPDATE public.semi_automatic_selection_v7_activation_gate "
                "SET pilot_status='active'",
                "42501",
            ),
            (
                "gate_generation",
                "UPDATE public.semi_automatic_selection_v7_activation_gate "
                "SET pilot_generation=999",
                "42501",
            ),
            (
                "singleton_constraint",
                "UPDATE public.semi_automatic_selection_v7_activation_gate SET singleton=FALSE",
                "23514",
            ),
            (
                "receipt_insert",
                "INSERT INTO public.semi_automatic_selection_v7_pilot_acceptances DEFAULT VALUES",
                "42501",
            ),
            (
                "receipt_update",
                "UPDATE public.semi_automatic_selection_v7_pilot_acceptances "
                "SET resulting_generation=999",
                "42501",
            ),
            (
                "receipt_delete",
                "DELETE FROM public.semi_automatic_selection_v7_pilot_acceptances",
                "42501",
            ),
            (
                "receipt_truncate",
                "TRUNCATE public.semi_automatic_selection_v7_pilot_acceptances",
                "42501",
            ),
        ):
            try:
                with runtime.connect() as connection, connection.begin():
                    connection.exec_driver_sql(statement)
                    # Always roll back, including an unexpected privilege success.
                    connection.rollback()
            except DBAPIError as error:
                actual = str(getattr(error.orig, "sqlstate", "unknown"))
                if actual != expected:
                    raise ValueError("Unexpected SQLSTATE in the isolated denial proof.") from None
                denials[name] = actual
            else:
                raise ValueError("Runtime unexpectedly passed a protected mutation.")
        if head != HEAD or not report.compliant or tuple(identity) != (DATABASE, ROLE):
            raise ValueError("Isolated runtime identity/head/grants are not compliant.")
        return {
            "status": "checked",
            "head": head,
            "lockingSelects": "passed",
            "gateUpdateColumns": ["singleton"],
            "protectedMutationDenials": denials,
            **report.as_dict(),
        }
    finally:
        engine.dispose()
        runtime.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=("bootstrap", "migrate", "provision", "check"))
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                {
                    "bootstrap": bootstrap,
                    "migrate": migrate,
                    "provision": provision,
                    "check": check,
                }[args.operation](),
                sort_keys=True,
            )
        )
    except Exception as error:
        # Never echo SQL URLs, passwords, statements or driver error text.
        diagnostic = {"status": "refused", "errorType": type(error).__name__}
        if isinstance(error, DBAPIError):
            diagnostic["sqlState"] = str(getattr(error.orig, "sqlstate", "unknown"))
            if args.operation == "migrate":
                # DDL-only primary diagnostics contain object identities, not URLs.
                diagnostic["migrationMessage"] = str(
                    getattr(getattr(error.orig, "diag", None), "message_primary", "")
                )[:500]
        print(json.dumps(diagnostic))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
