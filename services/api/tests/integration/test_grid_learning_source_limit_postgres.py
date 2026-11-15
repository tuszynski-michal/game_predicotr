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
        command.upgrade(config, "0188_grid_learning_source_limit")
        with db.owner_engine.connect() as connection:
            assert limits(connection) == raised
            assert recording_permission_errors(connection, db.role) == ()


def test_no_source_cap_migration_keeps_all_other_guards_owner_and_grants():
    from alembic import command

    signatures = (*COHORT_FUNCTIONS, *CONTEXT_FUNCTIONS)

    def snapshot(connection):
        return {
            signature: connection.execute(
                text("""SELECT pg_get_functiondef(p.oid),p.proowner,p.proacl,p.proconfig
                  FROM pg_proc p WHERE p.oid=to_regprocedure(:s)"""),
                {"s": signature},
            ).one()
            for signature in signatures
        }

    with application_role_database(
        "t1212cap", ("source-cap",), revision="0188_grid_learning_source_limit"
    ) as db:
        config = _config(db)
        with db.owner_engine.connect() as connection:
            before = snapshot(connection)
        command.upgrade(config, "0189_grid_learning_no_source_cap")
        with db.owner_engine.connect() as connection:
            after = snapshot(connection)
            for signature in signatures:
                assert before[signature][1:] == after[signature][1:]
                if signature in COHORT_FUNCTIONS:
                    expected = before[signature][0].replace(
                        "jsonb_array_length(plan->'sources')>20000",
                        "false /* source count uncapped */",
                    )
                else:
                    expected = before[signature][0].replace(
                        "cardinality(next_bytes)>20000 OR cardinality(next_pixels)>20000",
                        "false /* identity count uncapped */",
                    )
                assert after[signature][0] == expected
            assert recording_permission_errors(connection, db.role) == ()
        command.downgrade(config, "0188_grid_learning_source_limit")
        with db.owner_engine.connect() as connection:
            assert snapshot(connection) == before
