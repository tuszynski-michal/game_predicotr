"""D-610 on real SQL: 0188 raises the six recording limits to 20 000 and reverts cleanly."""

import os

import pytest
from _application_role_database import application_role_database
from game_predictor_api.storage.source_recording_permissions_v12 import recording_permission_errors
from game_predictor_api.storage.source_recording_source_limit import (
    COHORT_FUNCTIONS,
    CONTEXT_FUNCTIONS,
)
from sqlalchemy import text
from test_grid_model_evaluation_bridge_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def limits(connection) -> list[tuple[int, int]]:
    result = []
    for signature in (*COHORT_FUNCTIONS, *CONTEXT_FUNCTIONS):
        definition = connection.scalar(
            text("SELECT pg_get_functiondef(to_regprocedure(:s))"), {"s": signature}
        )
        result.append((definition.count(">5000"), definition.count(">20000")))
    return result


def test_source_limit_migration_rewrites_only_limits_and_keeps_grants():
    from alembic import command

    with application_role_database(
        "t1204limit", ("source-limit",), revision="0188_grid_learning_source_limit"
    ) as db:
        config = _config(db)
        with db.owner_engine.connect() as connection:
            raised = limits(connection)
            assert raised == [(0, 1)] * 4 + [(0, 2)] * 2
            assert recording_permission_errors(connection, db.role) == ()
        command.downgrade(config, "0187_grid_gate_cell_cut")
        with db.owner_engine.connect() as connection:
            assert limits(connection) == [(1, 0)] * 4 + [(2, 0)] * 2
        command.upgrade(config, "head")
        with db.owner_engine.connect() as connection:
            assert limits(connection) == raised
            assert recording_permission_errors(connection, db.role) == ()
