"""Small actual-role tooling provision/cleanup proof; no acceptance workloads."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database_roles import describe_application_role
from game_predictor_api.storage.owned_tool_database import OwnedToolDatabase
from game_predictor_api.storage.source_recording_permissions import validate_recording_capability
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned UUID PostgreSQL resources only",
)


def test_actual_tool_provisioning_fresh_runtime_and_exact_cleanup() -> None:
    database = OwnedToolDatabase(
        ApiSettings.from_environment().owner_database_url,
        prefix="game_predictor_tool_test",
        alembic_ini=ROOT / "alembic.ini",
    )
    names: list[str] = []
    oid: int | None = None
    with database:
        oid = database.database_oid
        owner = create_engine(database.owner_url, poolclass=NullPool)
        runtime = create_engine(database.runtime_url, poolclass=NullPool)
        try:
            with owner.connect() as connection:
                capability = validate_recording_capability(connection)
                names = [capability, str(database.runtime_url.username)]
                assert describe_application_role(connection, names[1]).compliant
            with runtime.connect() as connection:
                assert connection.execute(text("SELECT current_user")).scalar_one() == names[1]
                with pytest.raises(DBAPIError) as captured:
                    connection.execute(text("SELECT * FROM public.recording_groups"))
                assert getattr(captured.value.orig, "sqlstate", None) == "42501"
            environment = os.environ.copy()
            environment["TASK1018_RUNTIME_URL"] = database.runtime_url.render_as_string(
                hide_password=False
            )
            # Use environment, not argv or logs, for the transient login secret.
            restarted = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    """
import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
engine = create_engine(os.environ['TASK1018_RUNTIME_URL'], poolclass=NullPool)
try:
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT NOT rolsuper AND NOT rolbypassrls '
            'FROM pg_roles WHERE rolname=current_user'))
finally:
    engine.dispose()
""",
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            assert restarted.returncode == 0, "Fresh runtime process failed; output withheld."
        finally:
            runtime.dispose()
            owner.dispose()
    maintenance = create_engine(
        database.owner_url.set(database="postgres"),
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    try:
        with maintenance.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname=:name OR oid=:oid"),
                    {"name": database.database_name, "oid": oid},
                ).one_or_none()
                is None
            )
            for role in names:
                assert (
                    connection.execute(
                        text("SELECT 1 FROM pg_roles WHERE rolname=:role"),
                        {"role": role},
                    ).one_or_none()
                    is None
                )
    finally:
        maintenance.dispose()
    evidence = ROOT / "artifacts" / "audits" / "TASK-1018-TOOLING" / "cleanup.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "database": database.database_name,
                "databaseOid": oid,
                "roles": names,
                "freshRuntimeProcessPassed": True,
                "databaseRemaining": 0,
                "rolesRemaining": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
