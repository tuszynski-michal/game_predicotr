"""TASK-0943: verify a custom-format backup on two disposable databases."""

import os
import re
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementSaveCommand,
    ManagementSearchCommand,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from test_management_stakes_postgres import _rules
from test_verified_cell_search_projection import _seed_pending_board

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires two disposable PostgreSQL databases.",
)

_SAFE_DATABASE = re.compile(r"^game_predictor_t0943_[0-9a-f]{12}_test$")


def _docker_postgres(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", "infra/docker/compose.yaml", "exec", "-T", "postgres", *args],
        check=True,
        timeout=30,
        capture_output=True,
        text=True,
    )


def _snapshot(engine) -> tuple[int, int, int, int, str]:
    with engine.connect() as connection:
        counts = tuple(
            int(connection.scalar(text(f"SELECT count(*) FROM public.{table}")))
            for table in (
                "management_points",
                "management_stake_slots",
                "management_operations",
                "management_journal",
            )
        )
        digest = str(
            connection.scalar(
                text(
                    "SELECT content_sha256 FROM public.management_result_versions "
                    "ORDER BY content_sha256 LIMIT 1"
                )
            )
        )
    return (*counts, digest)


def test_custom_format_backup_restores_saved_slot_receipt_history_and_frozen_result() -> None:
    with application_role_database("t0943source", ()) as db:
        seed = _seed_pending_board(
            create_session_factory(db.owner_engine), datetime.now(UTC), sibling_positions=(1, 2)
        )
        game = seed.game_id
        _rules(db.owner_engine, game)
        with Session(db.app_engine) as session, session.begin():
            metadata = SqlAlchemyManagementRepository(session)
            point = metadata.point(
                None,
                ManagementPointCommand(
                    operation_id=uuid4(),
                    expected_revision=0,
                    name="Punkt",
                    city="Miasto",
                    street="Ulica",
                ),
                "local-owner",
            )
            machine = metadata.machine(
                point.id,
                None,
                ManagementMachineCommand(operation_id=uuid4(), expected_revision=0, name="Maszyna"),
                "local-owner",
            )
            metadata.assignments(
                machine.id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=machine.revision, game_ids=[game]
                ),
                "local-owner",
            )
        with Session(db.app_engine) as session, session.begin():
            repository = SqlAlchemyManagementStakeRepository(session)
            search = repository.search(
                machine.id,
                game,
                ManagementSearchCommand(
                    operation_id=uuid4(),
                    stake_grosze=2000,
                    cells=({"cellIndex": 0, "symbolCode": "first"},),
                    limit=100,
                ),
                "local-owner",
            )
            repository.before_commit()
        with Session(db.app_engine) as session, session.begin():
            repository = SqlAlchemyManagementStakeRepository(session)
            repository.save(
                machine.id,
                game,
                2000,
                ManagementSaveCommand(
                    operation_id=uuid4(),
                    expected_revision=0,
                    search_context_id=search.search_context_id,
                    start_sequence_number=1,
                    spin_count=7,
                    pinned_spin_positions=(0, 3, 7),
                ),
                "local-owner",
            )
            repository.before_commit()
        expected = _snapshot(db.owner_engine)
        assert expected[:2] == (1, 1)
        assert expected[2] >= 5 and expected[3] >= 5 and len(expected[4]) == 64

        destination = f"game_predictor_t0943_{uuid4().hex[:12]}_test"
        assert _SAFE_DATABASE.fullmatch(destination)
        assert destination != db.owner_url.database
        dump = f"/tmp/management0943_{uuid4().hex}.dump"
        maintenance = create_engine(
            db.owner_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
        )
        restored = None
        try:
            with maintenance.connect() as connection:
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                        {"name": destination},
                    )
                    == 0
                )
                connection.exec_driver_sql(f'CREATE DATABASE "{destination}"')
            _docker_postgres(
                "pg_dump",
                "-U",
                db.owner_role,
                "-d",
                db.owner_url.database,
                "-Fc",
                "-f",
                dump,
            )
            _docker_postgres("pg_restore", "--list", dump)
            _docker_postgres(
                "pg_restore",
                "-U",
                db.owner_role,
                "-d",
                destination,
                "--exit-on-error",
                dump,
            )
            restored = create_engine(
                db.owner_url.set(database=destination),
                poolclass=NullPool,
                connect_args={"connect_timeout": 5},
            )
            assert _snapshot(restored) == expected
        finally:
            if restored is not None:
                restored.dispose()
            with maintenance.connect() as connection:
                if (
                    connection.scalar(
                        text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                        {"name": destination},
                    )
                    == 1
                ):
                    connection.exec_driver_sql(f'DROP DATABASE "{destination}"')
            maintenance.dispose()
            _docker_postgres("rm", "-f", dump)
