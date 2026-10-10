"""TASK-0797: migration 0138 makes the RLS policy function parallel safe.

Runs on a disposable ``*_test`` database with a test-scoped LOGIN application
role (``_application_role_database``). It checks the function attributes, the
unchanged error contract (no ``NULL`` for a missing game), that a policy
filtered query of the application role gets a ``Gather`` plan whose workers
evaluate the policy, that downgrade restores the previous function, and that
the approved-cell CHECK no longer has the ``legacy_file`` branch.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
from _application_role_database import (
    ALEMBIC_INI,
    ApplicationRoleDatabase,
    application_role_database,
)
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_HEAD = "0138_rls_policy_function_parallel_safe"
_PREVIOUS = "0137_prediction_revisions_slim"
_TABLE = "game_data_v2.image_geometry_rollout_states"


@pytest.fixture(scope="module")
def database() -> Iterator[ApplicationRoleDatabase]:
    with application_role_database("t0797rls", ("t0797-rls-a", "t0797-rls-b")) as created:
        yield created


def _config(database: ApplicationRoleDatabase) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _function_attributes(database: ApplicationRoleDatabase) -> tuple[str, str]:
    with database.owner_engine.connect() as connection:
        row = connection.execute(
            text(
                """SELECT p.proparallel, p.provolatile FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'game_data_v2' AND p.proname = 'current_game_id_v1'"""
            )
        ).one()
    return str(row[0]), str(row[1])


def _forced_parallel_plan(database: ApplicationRoleDatabase, game_id: UUID) -> str:
    with database.app_engine.connect() as connection, connection.begin():
        _bind(connection, game_id)
        # Force a Gather whenever the plan is parallel safe.
        connection.exec_driver_sql("SET LOCAL debug_parallel_query = on")
        connection.exec_driver_sql("SET LOCAL parallel_setup_cost = 0")
        connection.exec_driver_sql("SET LOCAL parallel_tuple_cost = 0")
        rows = connection.exec_driver_sql(
            f"EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT game_id FROM {_TABLE}"
        ).all()
    return "\n".join(str(row[0]) for row in rows)


def _bind(connection: Connection, game_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('game_predictor.game_id', :game, true)"), {"game": str(game_id)}
    )


def _policy_value(database: ApplicationRoleDatabase, raw: str | None) -> object:
    with database.app_engine.connect() as connection, connection.begin():
        if raw is not None:
            connection.execute(
                text("SELECT set_config('game_predictor.game_id', :raw, true)"), {"raw": raw}
            )
        return connection.exec_driver_sql("SELECT game_data_v2.current_game_id_v1()").scalar_one()


def test_policy_function_is_parallel_safe_and_keeps_its_error_contract(
    database: ApplicationRoleDatabase,
) -> None:
    game_a = database.games["t0797-rls-a"]
    assert _function_attributes(database) == ("s", "s")
    assert _policy_value(database, str(game_a)) == game_a
    assert _policy_value(database, "{" + str(game_a).upper() + "}") == game_a
    assert _policy_value(database, game_a.hex) == game_a
    for raw, message in (
        (None, "GAME_STORAGE_SCOPE_REQUIRED"),
        ("   ", "GAME_STORAGE_SCOPE_REQUIRED"),
        ("not-a-game", "GAME_STORAGE_SCOPE_INVALID"),
        (str(game_a) + "0", "GAME_STORAGE_SCOPE_INVALID"),
    ):
        with pytest.raises(DBAPIError) as error:
            _policy_value(database, raw)
        assert cast("str | None", getattr(error.value.orig, "sqlstate", None)) == "42501"
        assert message in str(error.value.orig)


def test_application_role_query_runs_the_policy_in_parallel_workers(
    database: ApplicationRoleDatabase,
) -> None:
    game_a = database.games["t0797-rls-a"]
    plan = _forced_parallel_plan(database, game_a)
    assert "Gather" in plan, plan
    assert "Workers Launched" in plan, plan
    # The policy filter still applies inside the workers: one row of game A.
    assert "rows=1" in plan, plan


def test_downgrade_restores_the_previous_function_and_upgrade_returns(
    database: ApplicationRoleDatabase,
) -> None:
    game_a = database.games["t0797-rls-a"]
    # Migrations 0148-0150 refuse a downgrade, so a real downgrade from head cannot
    # reach 0138. 0138 is the only revision undone here and nothing later touches
    # the objects it changes, so the version row is stamped to 0138 first and back
    # to head afterwards.
    command.stamp(_config(database), _HEAD)
    command.downgrade(_config(database), _PREVIOUS)
    try:
        assert _function_attributes(database) == ("u", "s")
        assert "Gather" not in _forced_parallel_plan(database, game_a)
        with database.owner_engine.connect() as connection:
            old_check = str(
                connection.execute(
                    text(
                        """SELECT pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE conname = 'ck_image_symbol_review_cells_approved_provenance'
                          AND conrelid = 'game_data_v2.image_symbol_review_cells'::regclass"""
                    )
                ).scalar_one()
            )
        assert "legacy_file" in old_check
    finally:
        command.upgrade(_config(database), _HEAD)
        command.stamp(_config(database), "head")
    assert _function_attributes(database) == ("s", "s")


def test_approved_provenance_check_has_no_legacy_file_branch(
    database: ApplicationRoleDatabase,
) -> None:
    with database.owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT c.relname, pg_get_constraintdef(k.oid), k.convalidated
                FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE k.conname = 'ck_image_symbol_review_cells_approved_provenance'
                  AND n.nspname = 'game_data_v2'"""
            )
        ).all()
    parent = [row for row in rows if row[0] == "image_symbol_review_cells"]
    assert len(parent) == 1
    definition = str(parent[0][1])
    assert "legacy_file" not in definition
    assert "virtual_source" in definition
    # Every per-game partition carries the same narrowed constraint.
    assert {str(row[1]) for row in rows} == {definition}
    # Validation is the runbook step (``VALIDATE CONSTRAINT``), as in 0135/0136.
    with database.owner_engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE game_data_v2.image_symbol_review_cells "
            "VALIDATE CONSTRAINT ck_image_symbol_review_cells_approved_provenance"
        )
