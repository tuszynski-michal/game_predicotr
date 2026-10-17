"""Owned empty-registry reversibility, retained history and exact grant boundaries."""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.schema_readiness import EXPECTED_ALEMBIC_HEAD
from game_predictor_api.storage.source_recording_permissions import (
    PRIVATE_SEQUENCES,
    PRIVATE_TABLES,
    recording_permission_errors,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


def _config(database):
    result = Config(str(ALEMBIC_INI))
    result.set_main_option(
        "sqlalchemy.url",
        database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return result


def _sentinels(connection):
    connection.exec_driver_sql(
        "CREATE FUNCTION public.recording_custom() RETURNS integer LANGUAGE sql AS 'SELECT 7'"
    )
    connection.exec_driver_sql(
        "CREATE FUNCTION public.recording_command(text) RETURNS integer LANGUAGE sql AS 'SELECT 8'"
    )


def _sentinel_state(connection):
    return connection.execute(
        text("""
        SELECT p.oid,p.proowner,p.proacl,p.oid::regprocedure::text,
          EXISTS(SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner)))
                 WHERE grantee=0 AND privilege_type='EXECUTE')
        FROM pg_proc p WHERE p.oid=ANY(ARRAY[
          'public.recording_custom()'::regprocedure::oid,
          'public.recording_command(text)'::regprocedure::oid]) ORDER BY p.oid
    """)
    ).all()


def test_empty_downgrade_reupgrade_reprovision_keeps_private_boundary_and_sentinels():
    with application_role_database("t1002cycle", (), before_upgrade=_sentinels) as db:
        config = _config(db)
        with db.owner_engine.connect() as connection:
            sentinels = _sentinel_state(connection)
        assert all(row[-1] for row in sentinels)
        original = db.recording_capability
        assert original is not None and original.created_here
        command.downgrade(config, "0160_grid_geometry_proposals")
        with db.owner_engine.connect() as connection:
            for name in (*PRIVATE_TABLES, *PRIVATE_SEQUENCES):
                assert connection.scalar(text("SELECT to_regclass(:name)"), {"name": name}) is None
            assert (
                connection.scalar(
                    text("""SELECT count(*) FROM public.game_storage_table_manifest
                WHERE manifest_version='game-data-v2-manifest-v14'""")
                )
                == 0
            )
            assert _sentinel_state(connection) == sentinels
        command.upgrade(config, "head")
        with db.owner_engine.begin() as connection:
            report = provision_application_role(
                connection,
                ApplicationRoleSpec(
                    role_name=db.role,
                    password=db.app_url.password,
                ),
            )
            assert report.compliant and recording_permission_errors(connection, db.role) == ()
            assert _sentinel_state(connection) == sentinels
            assert (
                connection.scalar(
                    text("SELECT oid FROM pg_roles WHERE rolname=:name"),
                    {
                        "name": original.role,
                    },
                )
                == original.role_oid
            )
        # A new runtime process must still be denied after the full down/up and ALL grants.
        program = """
import sys
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError
engine=create_engine(sys.argv[1],connect_args={'connect_timeout':5})
try:
    with engine.connect() as connection:
        try:
            connection.execute(text('SELECT * FROM public.recording_evidence'))
        except DBAPIError as error:
            assert getattr(error.orig,'sqlstate',None)=='42501'
            connection.rollback()
        else:
            raise AssertionError('private registry reopened')
finally:
    engine.dispose()
print('private-denied')
"""
        result = subprocess.run(
            [sys.executable, "-c", program, db.app_url.render_as_string(hide_password=False)],
            capture_output=True,
            text=True,
            timeout=30,
            env=db.subprocess_environment(),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "private-denied"


@pytest.mark.parametrize("table", ["recording_groups", "recording_evidence", "recording_commands"])
def test_any_independent_registry_history_refuses_downgrade(table):
    with application_role_database("t1002history", ()) as db:
        with db.owner_engine.begin() as connection:
            if table == "recording_groups":
                connection.execute(
                    text("""INSERT INTO public.recording_groups
                    (id,origin,external_ref_sha256,origin_provider_sha256,revision,manifest_id,
                     manifest_sha256,expected_sources,page_count)
                    VALUES(:id,'LAB_DESCRIPTOR',:sha,:sha,1,:manifest,:sha,1,1)"""),
                    {
                        "id": uuid4(),
                        "manifest": uuid4(),
                        "sha": "a" * 64,
                    },
                )
            elif table == "recording_evidence":
                connection.execute(
                    text("""INSERT INTO public.recording_evidence
                    (id,kind,group_ids,payload,payload_sha256,actor)
                    VALUES(:id,'membership','{}','{}',public.recording_digest_v1('{}'),
                           'owned-test')"""),
                    {"id": uuid4()},
                )
            else:
                connection.execute(
                    text("""INSERT INTO public.recording_commands
                    (origin,external_ref_sha256,kind,idempotency_key,command_json,
                     command_sha256,actor,receipt)
                    VALUES('LAB_DESCRIPTOR',:sha,'owned-test',:key,'{}',:sha,'owned-test','{}')"""),
                    {
                        "sha": "a" * 64,
                        "key": uuid4(),
                    },
                )
        with pytest.raises(DBAPIError, match="RECORDING_DOWNGRADE_REFUSED"):
            command.downgrade(_config(db), "0160_grid_geometry_proposals")
        with db.owner_engine.connect() as connection:
            # The refused walk rolls back as one transaction: the current head stays.
            assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
                EXPECTED_ALEMBIC_HEAD
            )
            for name in PRIVATE_TABLES:
                assert connection.scalar(text("SELECT to_regclass(:name)"), {"name": name})
            assert connection.scalar(text(f"SELECT count(*) FROM public.{table}")) == 1


def test_missing_future_report_binding_raises_sql_22023_and_rolls_back_invalidation():
    """A malformed future producer binding gets the typed refusal, never partial history."""
    with application_role_database("t1002binding", ()) as db:
        group, resolution, change = uuid4(), uuid4(), uuid4()
        with db.owner_engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO public.recording_evidence
                (id,kind,group_ids,dependency_group_ids,payload,payload_sha256,proof_sha256,actor)
                VALUES(:id,'resolution',ARRAY[:group]::uuid[],ARRAY[:group]::uuid[],'{}',
                       public.recording_digest_v1('{}'),:proof,'owned-invalid-binding-test')"""),
                {"id": resolution, "group": group, "proof": "0" * 64},
            )
            connection.execute(
                text("""INSERT INTO public.recording_evidence
                (id,kind,group_ids,payload,payload_sha256,actor)
                VALUES(:id,'use',ARRAY[:group]::uuid[],jsonb_build_object(
                       'resolutionId',CAST(:resolution AS text),'reportId',CAST(:report AS text)),
                       public.recording_digest_v1('{}'),'owned-invalid-binding-test')"""),
                {"id": uuid4(), "group": group, "resolution": resolution, "report": uuid4()},
            )
            connection.execute(
                text("""INSERT INTO public.recording_evidence
                (id,kind,group_ids,payload,payload_sha256,actor)
                VALUES(:id,'membership',ARRAY[:group]::uuid[],'{}',
                       public.recording_digest_v1('{}'),'owned-invalid-binding-test')"""),
                {"id": change, "group": group},
            )
            with (
                pytest.raises(DBAPIError, match="RECORDING_BINDING_INVALID") as error,
                connection.begin_nested(),
            ):
                connection.execute(
                    text("SELECT public.recording_invalidate_dependents_v1(:id)"),
                    {"id": change},
                )
            assert error.value.orig.sqlstate == "22023"
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM public.recording_evidence WHERE kind='invalidation'")
                )
                == 0
            )
