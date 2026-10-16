"""Exact ownership receipts for explicit disposable-fixture capability provisioning."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from game_predictor_api.storage.database_roles import DatabaseRoleError
from game_predictor_api.storage.source_recording_permissions import (
    provision_recording_capability,
    validate_recording_capability,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.pool import NullPool

RECORDING_REVISION = "0161_source_recording_groups"
ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"


@dataclass(frozen=True)
class RecordingCapabilityReceipt:
    role: str
    role_oid: int
    database: str
    database_oid: int
    marker: str
    created_here: bool


@dataclass(frozen=True)
class RuntimeRoleReceipt:
    role: str
    role_oid: int
    created_here: bool
    marker: str | None = None


def provision_recording_capability_receipt(connection: Connection) -> RecordingCapabilityReceipt:
    """Capture the exact identity; never claim a pre-existing role for cleanup."""
    created_here = False
    try:
        role = validate_recording_capability(connection)
    except DatabaseRoleError as error:
        if error.code != "RECORDING_CAPABILITY_REQUIRED":
            raise
        role = provision_recording_capability(connection)
        created_here = True
    database, database_oid, role_oid, marker = connection.execute(
        text("""
            SELECT d.datname, d.oid, r.oid, pg_catalog.shobj_description(r.oid,'pg_authid')
            FROM pg_catalog.pg_database d CROSS JOIN pg_catalog.pg_roles r
            WHERE d.datname=current_database() AND r.rolname=:role
        """),
        {"role": role},
    ).one()
    return RecordingCapabilityReceipt(
        role=role,
        role_oid=int(role_oid),
        database=str(database),
        database_oid=int(database_oid),
        marker=str(marker),
        created_here=created_here,
    )


def drop_recording_capability_receipt(
    connection: Connection,
    receipt: RecordingCapabilityReceipt,
) -> None:
    """After own database drop, remove only this fixture's unchanged unused role."""
    if not receipt.created_here:
        return
    assert re.fullmatch(r"gp_rec_[0-9a-f]{24}", receipt.role), receipt.role
    assert connection.execute(
        text(
            "SELECT NOT EXISTS(SELECT 1 FROM pg_catalog.pg_database "
            "WHERE datname=:name OR oid=:oid)"
        ),
        {"name": receipt.database, "oid": receipt.database_oid},
    ).scalar_one(), "Refusing capability cleanup before the exact fixture database is gone"
    row = connection.execute(
        text("""
        SELECT oid, pg_catalog.shobj_description(oid,'pg_authid')
        FROM pg_catalog.pg_roles WHERE rolname=:role
    """),
        {"role": receipt.role},
    ).one_or_none()
    if row is None:
        return
    assert int(row[0]) == receipt.role_oid and str(row[1]) == receipt.marker, (
        "Refusing to drop a changed or replaced recording capability"
    )
    assert not connection.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_shdepend
                      WHERE refclassid='pg_catalog.pg_authid'::regclass AND refobjid=:oid)
            OR EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=:oid OR roleid=:oid)
    """),
        {"oid": receipt.role_oid},
    ).scalar_one(), (
        "Refusing to drop a recording capability that still has dependencies or memberships"
    )
    connection.exec_driver_sql(f'DROP ROLE "{receipt.role}"')


class OwnedRecordingCapability:
    """One fixture owns the receipt through downgrade/re-upgrade and DB cleanup.

    Construction creates only the owned journal directory. Historical fixtures attach it to an
    engine without creating a role; only an explicit provision for a descendant
    of 0161 performs role DDL. Cleanup always follows the fixture's own DB drop.
    """

    def __init__(self, database_url: URL) -> None:
        assert database_url.database and re.fullmatch(
            r"(?:[a-z0-9_]+_test|game_predictor_task[0-9]+_[a-z0-9_]+)",
            database_url.database,
        ), "Only an explicitly disposable fixture database is allowed"
        self.database_url = database_url
        self.database_oid: int | None = None
        self.receipt: RecordingCapabilityReceipt | None = None
        self.runtime_role_receipt: RuntimeRoleReceipt | None = None
        self._journal_nonce = secrets.token_hex(16)
        artifacts = Path(__file__).resolve().parents[4] / "artifacts"
        configured = os.environ.get(
            "GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT",
            str(artifacts / "audits" / "TASK-1002_R2_FIX" / "resources"),
        )
        self.journal_root = Path(configured)
        assert (
            self.journal_root.is_absolute()
            and ".." not in self.journal_root.parts
            and self.journal_root.is_relative_to(artifacts)
            and self.journal_root.resolve().is_relative_to(artifacts.resolve())
        ), "Resource journal must be absolute and inside owned artifacts"
        current = self.journal_root
        while current != artifacts:
            assert not current.is_symlink() and not current.is_junction(), "Unsafe journal path"
            current = current.parent
        assert not artifacts.is_symlink() and not artifacts.is_junction(), "Unsafe artifact root"
        self.journal_root.mkdir(parents=True, exist_ok=True)

    def _journal(self, phase: str) -> None:
        assert self.database_oid is not None
        destination = self.journal_root / f"{self.database_url.database}-{self.database_oid}.json"
        assert not destination.is_symlink(), "Unsafe resource journal file"
        if destination.exists():
            assert destination.stat().st_size <= 65536
            previous = json.loads(destination.read_text(encoding="utf-8"))
            assert isinstance(previous, dict), "Invalid resource journal"
            assert previous.get("journalNonce") == self._journal_nonce, (
                "Resource journal is not ours"
            )
        capability, runtime = self.receipt, self.runtime_role_receipt
        payload = {
            "schemaVersion": "recording-test-resource-receipt-v1",
            "phase": phase,
            "journalNonce": self._journal_nonce,
            "databaseName": self.database_url.database,
            "databaseOid": self.database_oid,
            "databaseCreatedHere": True,
            "clusterHost": self.database_url.host,
            "clusterPort": self.database_url.port,
            "capabilityRole": None
            if capability is None
            else {
                "name": capability.role,
                "oid": capability.role_oid,
                "createdHere": capability.created_here,
                "marker": capability.marker,
            },
            "runtimeRole": None
            if runtime is None
            else {
                "name": runtime.role,
                "oid": runtime.role_oid,
                "createdHere": runtime.created_here,
                **({"marker": runtime.marker} if runtime.marker is not None else {}),
            },
        }
        temporary = destination.with_name(destination.name + "." + uuid4().hex + ".pending")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as target:
                json.dump(payload, target, sort_keys=True, indent=2)
                target.flush()
                os.fsync(target.fileno())
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    def record_created_database(self, maintenance: Connection) -> None:
        """Call only immediately after this fixture's successful CREATE DATABASE."""
        assert self.database_oid is None, "Fixture database creation was already recorded"
        self.database_oid = int(
            maintenance.execute(
                text("SELECT oid FROM pg_catalog.pg_database WHERE datname=:name"),
                {"name": self.database_url.database},
            ).scalar_one()
        )
        try:
            self._journal("database_created")
        except (OSError, ValueError, AssertionError) as error:
            try:
                self.assert_database_identity(maintenance)
                maintenance.exec_driver_sql(f'DROP DATABASE "{self.database_url.database}"')
            except Exception as cleanup_error:
                error.add_note(f"Own empty fixture database cleanup failed: {cleanup_error}")
            else:
                self.database_oid = None
            raise

    def create_database(self, maintenance: Connection) -> None:
        """Never adopt or remove a colliding database, including failed CREATE."""
        assert self.database_oid is None, "Fixture already owns a database"
        assert maintenance.scalar(
            text("SELECT NOT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)"),
            {"name": self.database_url.database},
        ), "Refusing to adopt an existing fixture database"
        maintenance.exec_driver_sql(f'CREATE DATABASE "{self.database_url.database}"')
        self.record_created_database(maintenance)

    def drop_database(self, maintenance: Connection) -> None:
        """Dispose clients first; retain exact identity and the final idle assertion."""
        self.assert_database_identity(maintenance)
        assert self.wait_for_owned_database_idle(maintenance) == 0, (
            "Refusing DROP while a fixture connection remains"
        )
        maintenance.exec_driver_sql(f'DROP DATABASE "{self.database_url.database}"')
        self.cleanup(maintenance)

    def create_runtime_role(self, connection: Connection, role: str) -> None:
        """Record a successful own role CREATE with an immutable cleanup marker."""
        assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role)
        assert connection.scalar(
            text("SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"),
            {"role": role},
        ), "Refusing to adopt an existing runtime role"
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
        marker = f"owned-fixture:{self.database_oid}:{self._journal_nonce}"
        connection.exec_driver_sql(f"COMMENT ON ROLE \"{role}\" IS '{marker}'")
        self.record_runtime_role(connection, role, created_here=True)
        assert self.runtime_role_receipt is not None
        self.runtime_role_receipt = replace(self.runtime_role_receipt, marker=marker)
        self._journal("runtime_precommit")

    @classmethod
    def for_engine(cls, engine: Engine) -> OwnedRecordingCapability:
        holder = getattr(engine, "_recording_capability_fixture", None)
        if holder is None:
            holder = cls(engine.url)
            engine._recording_capability_fixture = holder  # type: ignore[attr-defined]
        assert isinstance(holder, cls) and holder.database_url == engine.url
        return holder

    def provision(
        self, revision: str = "head", config: Config | None = None
    ) -> RecordingCapabilityReceipt | None:
        config = config or Config(str(ALEMBIC_INI))
        ancestors = {
            entry.revision
            for entry in ScriptDirectory.from_config(config).iterate_revisions(revision, "base")
        }
        if RECORDING_REVISION not in ancestors:
            return None
        assert self.database_oid is not None, "Fixture must record its own successful CREATE first"
        engine = create_engine(
            self.database_url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
        )
        try:
            with engine.begin() as connection:
                receipt = provision_recording_capability_receipt(connection)
                assert receipt.database_oid == self.database_oid, (
                    "Fixture database identity changed"
                )
                if self.receipt is None:
                    self.receipt = receipt
                else:
                    assert (receipt.role_oid, receipt.database_oid, receipt.marker) == (
                        self.receipt.role_oid,
                        self.receipt.database_oid,
                        self.receipt.marker,
                    ), "Fixture capability identity changed"
                self._journal("capability_precommit")
            self._journal("capability_ready")
            return self.receipt
        finally:
            engine.dispose()

    def assert_database_identity(self, maintenance: Connection) -> None:
        assert self.database_oid is not None, "Refusing DROP of an unowned or replaced fixture DB"
        oid = maintenance.execute(
            text("SELECT oid FROM pg_catalog.pg_database WHERE datname=:name"),
            {"name": self.database_url.database},
        ).scalar_one()
        assert int(oid) == self.database_oid, "Refusing DROP of a replaced fixture DB"

    def wait_for_owned_database_idle(self, maintenance: Connection) -> int:
        """Allow at most five seconds for already-disposed clients to disappear.

        Never terminate a backend. A still-active connection remains a nonzero
        result and the caller must keep its final zero-connections assertion.
        """
        deadline = time.monotonic() + 5.0
        while True:
            self.assert_database_identity(maintenance)
            active = int(
                maintenance.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                    {"name": self.database_url.database},
                ).scalar_one()
            )
            remaining = deadline - time.monotonic()
            if active == 0 or remaining <= 0:
                return active
            time.sleep(min(0.1, remaining))

    def cleanup(self, maintenance: Connection) -> None:
        assert self.database_oid is not None, "Unowned fixture cleanup is forbidden"
        assert maintenance.scalar(
            text("""SELECT NOT EXISTS(SELECT 1 FROM pg_database
            WHERE datname=:name OR oid=:oid)"""),
            {"name": self.database_url.database, "oid": self.database_oid},
        ), "Cleanup requires the exact owned database to be gone"
        runtime = self.runtime_role_receipt
        if runtime is not None and runtime.created_here:
            oid = maintenance.scalar(
                text("SELECT oid FROM pg_roles WHERE rolname=:name"), {"name": runtime.role}
            )
            if oid is not None:
                assert int(oid) == runtime.role_oid, "Refusing DROP of a replaced runtime role"
                if runtime.marker is not None:
                    assert (
                        maintenance.scalar(
                            text(
                                "SELECT pg_catalog.shobj_description(oid,'pg_authid') "
                                "FROM pg_roles WHERE rolname=:name"
                            ),
                            {"name": runtime.role},
                        )
                        == runtime.marker
                    ), "Refusing DROP of a changed runtime role marker"
                assert not maintenance.scalar(
                    text("""SELECT
                    EXISTS(SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass
                           AND refobjid=:oid) OR
                    EXISTS(SELECT 1 FROM pg_auth_members WHERE member=:oid OR roleid=:oid)"""),
                    {"oid": runtime.role_oid},
                ), "Runtime role is still used"
                assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", runtime.role)
                maintenance.exec_driver_sql(f'DROP ROLE "{runtime.role}"')
        if self.receipt is not None:
            drop_recording_capability_receipt(maintenance, self.receipt)
        if self.database_oid is not None:
            self._journal("cleaned")

    def record_runtime_role(
        self, connection: Connection, role: str, *, created_here: bool, committed: bool = False
    ) -> None:
        """Record only a fixture's explicitly successful CREATE ROLE, never adopt."""
        assert self.database_oid is not None
        oid = int(
            connection.execute(
                text("SELECT oid FROM pg_roles WHERE rolname=:name"), {"name": role}
            ).scalar_one()
        )
        marker = None if self.runtime_role_receipt is None else self.runtime_role_receipt.marker
        receipt = RuntimeRoleReceipt(role, oid, created_here, marker)
        if self.runtime_role_receipt is not None:
            assert self.runtime_role_receipt == receipt, "Runtime role identity changed"
        self.runtime_role_receipt = receipt
        self._journal("runtime_ready" if committed else "runtime_precommit")
