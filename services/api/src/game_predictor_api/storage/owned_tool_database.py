"""Owned disposable PostgreSQL databases for acceptance and benchmark tools.

The owner is used only for lifecycle DDL and explicit role provisioning.
Application work receives a separate restricted login. No pre-existing
database or role is adopted, and cleanup never disconnects clients.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.pool import NullPool

from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.source_recording_permissions import provision_recording_capability


@dataclass(frozen=True)
class _RoleReceipt:
    name: str
    oid: int
    marker: str
    created_here: bool


class OwnedToolDatabase:
    """One UUID database and its exact capability/application-role receipts.

    Use as a context manager, or call ``create`` and ``close`` around clients
    whose engines must be disposed first. ``close(error)`` preserves an
    existing failure while recording a cleanup failure as an exception note.
    """

    def __init__(self, owner_url: str | URL, *, prefix: str, alembic_ini: Path) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,28}", prefix):
            raise ValueError("Disposable database prefix must contain at most 29 safe characters.")
        source = make_url(owner_url) if isinstance(owner_url, str) else owner_url
        if source.get_backend_name() != "postgresql":
            raise ValueError("Disposable tooling databases require PostgreSQL.")
        self.database_name = f"{prefix}_{uuid4().hex}"
        self.owner_url = source.set(database=self.database_name).update_query_dict(
            {"connect_timeout": "5"}
        )
        self.alembic_ini = alembic_ini
        self.created_here = False
        self._creation_attempted = False
        self._database_dropped_here = False
        self._cleanup_failed = False
        self.database_oid: int | None = None
        self.marker = f"game-predictor-owned-tool-v1:{uuid4().hex}"
        self._roles: list[_RoleReceipt] = []
        self._runtime_url: URL | None = None
        self._maintenance: Engine | None = None

    @property
    def runtime_url(self) -> URL:
        if self._runtime_url is None:
            raise RuntimeError("The disposable database is not provisioned.")
        return self._runtime_url

    def _engine(self, url: URL, *, maintenance: bool = False) -> Engine:
        return create_engine(
            url,
            poolclass=NullPool,
            isolation_level="AUTOCOMMIT" if maintenance else "READ COMMITTED",
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=120000 -c lock_timeout=5000",
            },
        )

    def create(self) -> OwnedToolDatabase:
        if self._creation_attempted or self._maintenance is not None or self.created_here:
            raise RuntimeError("Disposable database creation cannot be repeated.")
        self._creation_attempted = True
        self._maintenance = self._engine(self.owner_url.set(database="postgres"), maintenance=True)
        try:
            with self._maintenance.connect() as connection:
                if (
                    connection.execute(
                        text("SELECT 1 FROM pg_database WHERE datname=:name"),
                        {"name": self.database_name},
                    ).one_or_none()
                    is not None
                ):
                    raise RuntimeError("Refusing to adopt an existing disposable database.")
                connection.exec_driver_sql(f'CREATE DATABASE "{self.database_name}"')
                self.created_here = True
                self.database_oid = int(
                    connection.execute(
                        text("SELECT oid FROM pg_database WHERE datname=:name"),
                        {"name": self.database_name},
                    ).scalar_one()
                )
                connection.exec_driver_sql(
                    f'COMMENT ON DATABASE "{self.database_name}" IS '
                    f"{self._literal(connection, self.marker)}"
                )
            owner = self._engine(self.owner_url)
            try:
                with owner.begin() as connection:
                    self._assert_database(connection)
                    digest = hashlib.sha256(
                        f"{self.database_name}:{self.database_oid}".encode()
                    ).hexdigest()[:24]
                    self._require_absent_role(connection, f"gp_rec_{digest}")
                    role = provision_recording_capability(connection)
                    capability = self._receipt(connection, role)
                self._roles.append(capability)
                config = Config(str(self.alembic_ini))
                config.set_main_option(
                    "sqlalchemy.url",
                    self.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
                )
                command.upgrade(config, "head")
                runtime_role = f"gp_tool_{uuid4().hex}"
                password = secrets.token_urlsafe(32)
                with owner.begin() as connection:
                    self._assert_database(connection)
                    self._require_absent_role(connection, runtime_role)
                    # Establish successful CREATE ourselves before the canonical
                    # idempotent provisioner can align an existing role.
                    connection.exec_driver_sql(f'CREATE ROLE "{runtime_role}" NOLOGIN')
                    provision_application_role(
                        connection, ApplicationRoleSpec(runtime_role, password)
                    )
                    connection.exec_driver_sql(
                        f'COMMENT ON ROLE "{runtime_role}" IS '
                        f"{self._literal(connection, self.marker)}"
                    )
                    runtime = self._receipt(connection, runtime_role)
                self._roles.append(runtime)
                self._runtime_url = self.owner_url.set(username=runtime_role, password=password)
            finally:
                owner.dispose()
        except BaseException as error:
            self.close(error)
            raise
        return self

    @staticmethod
    def _literal(connection: Connection, value: str) -> str:
        return str(
            connection.execute(text("SELECT quote_literal(:value)"), {"value": value}).scalar_one()
        )

    @staticmethod
    def _require_absent_role(connection: Connection, role: str) -> None:
        if (
            connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
            ).one_or_none()
            is not None
        ):
            raise RuntimeError("Refusing to adopt an existing disposable role.")

    @staticmethod
    def _receipt(connection: Connection, role: str) -> _RoleReceipt:
        oid, marker = connection.execute(
            text(
                "SELECT oid, pg_catalog.shobj_description(oid,'pg_authid') "
                "FROM pg_roles WHERE rolname=:role"
            ),
            {"role": role},
        ).one()
        if marker is None:
            raise RuntimeError("Disposable role has no ownership marker.")
        return _RoleReceipt(role, int(oid), str(marker), True)

    def _assert_database(self, connection: Connection) -> None:
        row = connection.execute(
            text(
                "SELECT oid, pg_catalog.shobj_description(oid,'pg_database') "
                "FROM pg_database WHERE datname=:name"
            ),
            {"name": self.database_name},
        ).one_or_none()
        if (
            not self.created_here
            or self.database_oid is None
            or row is None
            or int(row[0]) != self.database_oid
            or row[1] != self.marker
        ):
            raise RuntimeError("Refusing cleanup/provisioning of a changed or unowned database.")

    def _cleanup(self, connection: Connection) -> None:
        if self.created_here:
            self._assert_database(connection)
            deadline = time.monotonic() + 5
            while True:
                self._assert_database(connection)
                active = int(
                    connection.execute(
                        text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                        {"name": self.database_name},
                    ).scalar_one()
                )
                if active == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Disposable database still has active connections; retained."
                    )
                time.sleep(0.1)
            self._assert_database(connection)
            connection.exec_driver_sql(f'DROP DATABASE "{self.database_name}"')
            self.created_here = False
            self._database_dropped_here = True
            self._runtime_url = None
        if not self._database_dropped_here:
            return
        while self._roles:
            receipt = self._roles[-1]
            self._drop_role(connection, receipt)
            self._roles.pop()

    def _drop_role(self, connection: Connection, receipt: _RoleReceipt) -> None:
        if not receipt.created_here:
            return
        if (
            connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname=:name OR oid=:oid"),
                {"name": self.database_name, "oid": self.database_oid},
            ).one_or_none()
            is not None
        ):
            raise RuntimeError("Disposable role cleanup requires its exact database to be gone.")
        row = connection.execute(
            text(
                "SELECT oid, pg_catalog.shobj_description(oid,'pg_authid') "
                "FROM pg_roles WHERE rolname=:role"
            ),
            {"role": receipt.name},
        ).one_or_none()
        if row is None:
            return
        if int(row[0]) != receipt.oid or row[1] != receipt.marker:
            raise RuntimeError("Refusing cleanup of a changed disposable role.")
        if connection.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_shdepend "
                "WHERE refclassid='pg_authid'::regclass AND refobjid=:oid) "
                "OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=:oid OR roleid=:oid)"
            ),
            {"oid": receipt.oid},
        ).scalar_one():
            raise RuntimeError("Disposable role still has dependencies or memberships; retained.")
        connection.exec_driver_sql(f'DROP ROLE "{receipt.name}"')

    def close(
        self,
        error: BaseException | None = None,
        *,
        retain: bool = False,
        retry_cleanup: bool = False,
    ) -> None:
        """Clean owned resources; an explicit later call may resume failed cleanup.

        Pending role receipts survive database removal. After failure, an
        explicit ``retry_cleanup=True`` is required. Retrying never recreates
        the database or adopts an identity; every remaining role is rechecked.
        """
        if self._cleanup_failed and not retry_cleanup:
            return
        owns_pending_resources = self.created_here or (
            self._database_dropped_here and bool(self._roles)
        )
        if self._maintenance is None and (retain or not owns_pending_resources):
            return
        try:
            self._cleanup_failed = False
            if self._maintenance is None:
                self._maintenance = self._engine(
                    self.owner_url.set(database="postgres"), maintenance=True
                )
            if not retain and owns_pending_resources:
                with self._maintenance.connect() as connection:
                    self._cleanup(connection)
        except BaseException as cleanup_error:
            self._cleanup_failed = True
            if error is None:
                raise
            error.add_note(f"Disposable database cleanup failed: {type(cleanup_error).__name__}")
        finally:
            if self._maintenance is not None:
                self._maintenance.dispose()
            self._maintenance = None

    def __enter__(self) -> OwnedToolDatabase:
        return self.create()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(exception)
