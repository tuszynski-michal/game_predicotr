"""Provision or check the application database role (TASK-0795).

The role name and password come from ``GAME_PREDICTOR_DATABASE_URL`` (the
runtime URL of API and worker); the script connects with
``GAME_PREDICTOR_OWNER_DATABASE_URL`` (the schema owner) to the same database.
It is idempotent: it creates or aligns the role (``LOGIN NOSUPERUSER
NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT``, password as a
SCRAM verifier), grants DML on ``public`` and ``game_data_v2`` tables, sequence
usage and function execution, keeps ``alembic_version`` read-only and sets
default privileges for objects the owner creates later. It never changes the
owner role, data or schema objects.

When both URLs use the same user (rollback configuration) there is nothing to
provision and the script exits successfully.

Usage (repository root, PowerShell):

    .venv\\Scripts\\python.exe scripts/provision_database_roles.py           # provision
    .venv\\Scripts\\python.exe scripts/provision_database_roles.py --check   # read-only
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from game_predictor_api.config import ApiSettings, ConfigurationError
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    DatabaseRoleError,
    describe_application_role,
    provision_application_role,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report the role compliance; exit 1 when it is missing or not compliant.",
    )
    options = parser.parse_args(arguments)
    try:
        settings = ApiSettings.from_environment()
    except ConfigurationError as error:
        print(json.dumps({"status": "configuration_error", "message": str(error)}))
        return 2
    application_url = make_url(settings.database_url)
    owner_url = make_url(settings.owner_database_url)
    role_name = application_url.username
    if role_name is None or role_name == owner_url.username:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "GAME_PREDICTOR_DATABASE_URL uses the owner role; "
                    "nothing to provision (rollback configuration).",
                }
            )
        )
        return 0
    engine = create_engine(owner_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        if options.check:
            with engine.connect() as connection:
                report = describe_application_role(connection, role_name)
            print(json.dumps({"status": "checked", **report.as_dict()}, sort_keys=True))
            return 0 if report.compliant else 1
        with engine.begin() as connection:
            report = provision_application_role(
                connection,
                ApplicationRoleSpec(role_name=role_name, password=application_url.password),
            )
        print(json.dumps({"status": "provisioned", **report.as_dict()}, sort_keys=True))
        return 0
    except DatabaseRoleError as error:
        print(json.dumps({"status": "refused", "code": error.code, "details": error.details}))
        return 1
    except SQLAlchemyError as error:
        cause = getattr(error, "orig", None) or error
        message = str(cause).strip().splitlines()[0] if str(cause).strip() else ""
        print(
            json.dumps(
                {"status": "database_error", "error": type(cause).__name__, "message": message}
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
