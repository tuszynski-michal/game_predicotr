"""0180 adds capability names and preserves immutable historical SQL bodies."""

import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from game_predictor_api.storage.source_recording_permissions_v7 import recording_permission_errors
from sqlalchemy import text
from test_recording_migration_lifecycle_postgres import _config

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


def definitions(connection):
    return dict(
        connection.execute(
            text(
                "SELECT proname,pg_get_functiondef(oid) FROM pg_proc "
                "WHERE pronamespace='public'::regnamespace AND proname IN "
                "('recording_cohort_command_v3','recording_photo_cohort_v1',"
                "'recording_correction_report_bind_v1')"
            )
        ).all()
    )


def test_additive_migration_preserves_old_bodies_permissions_and_history_guard():
    with application_role_database(
        "t1157migration", ("screen",), revision="0179_empty_replacement_search"
    ) as db:
        config = _config(db)
        with db.owner_engine.connect() as connection:
            old = definitions(connection)
        command.upgrade(config, "0180_screen_grid_corrections")
        with db.owner_engine.connect() as connection:
            assert definitions(connection) == old
            assert recording_permission_errors(connection, db.role) == ()
        command.downgrade(config, "0179_empty_replacement_search")
        with db.owner_engine.connect() as connection:
            assert definitions(connection) == old
            assert (
                connection.scalar(
                    text(
                        "SELECT to_regprocedure("
                        "'public.recording_cohort_command_v4(uuid,jsonb,text)')"
                    )
                )
                is None
            )
        command.upgrade(config, "0180_screen_grid_corrections")
        migration = (
            ScriptDirectory.from_config(config).get_revision("0180_screen_grid_corrections").module
        )
        with db.owner_engine.begin() as connection:
            with pytest.raises(RuntimeError, match="history prevents"), connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO game_data_v2.grid_training_cohorts"
                        "(game_id,id,status,document,created_by) "
                        "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1157')"
                    ),
                    {
                        "g": next(iter(db.games.values())),
                        "c": uuid4(),
                        "d": '{"policyVersion":"application-grid-corrections-v3"}',
                    },
                )
                with Operations.context(MigrationContext.configure(connection)):
                    migration.downgrade()
            assert recording_permission_errors(connection, db.role) == ()
