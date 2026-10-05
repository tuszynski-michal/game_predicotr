"""Opt-in disposable PostgreSQL checks of parent and direct child RLS.

Execution requires explicit approval and opt-in. The existing fixture
creates a separate *_test database and expiring test role; no operator game
database is migrated or populated. Running this test is an explicit operation.
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Queue
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from _virtual_board_fixtures import ensure_source_geometry
from alembic import command
from alembic.config import Config
from game_predictor_api.domain.grid_shadow import shadow_digest
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_shadow import SqlAlchemyGridShadowRepository
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import ImageFileExecutionModel, JobModel, SourceImageModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_GRID_SHADOW_POSTGRES_TESTS") != "1",
    reason="Requires explicit opt-in to disposable grid-shadow PostgreSQL tests.",
)


def _seed_comparison(database, game_id, *, publish=True):
    """Create genuine FK-bound inputs and publish/recover through the real repository."""
    with Session(database.owner_engine) as session, session.begin():
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        import_job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "label": str(game_id),
                },
            )
        )
        sha = shadow_digest(str(game_id))
        execution = shadow_digest(["execution", str(game_id)])
        session.add(
            ImageFileExecutionModel(
                file_execution_key=execution,
                source_checksum_sha256=sha,
                pipeline_fingerprint=sha,
                checkpoint_payload={},
                status="completed",
            )
        )
        session.flush()
        source = SourceImageModel(
            import_job_id=import_job.id,
            file_execution_key=execution,
            relative_path=f"{game_id}/seq_1-9.jpg",
            checksum_sha256=sha,
            width=100,
            height=100,
            status="completed",
        )
        session.add(source)
        session.flush()
        ensure_source_geometry(
            session,
            game_id=game_id,
            source=source,
            sequence_range_start=1,
            created_at=datetime.now(UTC),
        )
        repository = SqlAlchemyGridShadowRepository(session)
        pinned = repository.pin_source(game_id, source.id)
        model = {
            "profile": "grid_profile_mumie_v1",
            "version": "v1",
            "manifest_checksum_sha256": sha,
        }
        shadow_job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.VALIDATE,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "validation_kind": "grid_geometry_shadow_v3",
                    "request_id": str(uuid4()),
                    "sources": [pinned],
                    "model": model,
                },
            )
        )
        job = session.get(JobModel, shadow_job.id)
        assert job is not None
        job.status = JobStatus.PROCESSING
        job.execution_slot = 1
        job.lease_owner = "test-worker"
        job.lease_token = uuid4()
        job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        job.heartbeat_at = datetime.now(UTC)
        session.flush()
        output = {
            "schemaVersion": 1,
            "status": "needs_review",
            "reasons": [],
            "slots": [
                {
                    "positionIndex": position,
                    "sequenceNumber": position + 1,
                    "baselineNodes24": None,
                    "neuralNodes24": None,
                    "state": "missing",
                    "reasonCodes": [],
                    "cellVisibility": ["unknown"] * 15,
                }
                for position in range(9)
            ],
            "unassignedDetections": [],
        }
        args = {
            "game_id": game_id,
            "job_id": job.id,
            "lease_owner": job.lease_owner,
            "lease_token": job.lease_token,
            "pinned_source": pinned,
            "model": model,
            "output": output,
        }
        if not publish:
            return args
        first = repository.publish_result(**args)
        assert repository.publish_result(**args).id == first.id
        job.status = JobStatus.COMPLETED
        job.execution_slot = job.lease_owner = job.lease_token = job.lease_expires_at = (
            job.heartbeat_at
        ) = None
        result_id = first.id
    with Session(database.owner_engine) as session, session.begin():
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        recovered = SqlAlchemyGridShadowRepository(session).get_result(game_id, result_id)
        assert recovered is not None and recovered.id == result_id
    return result_id


def test_committed_comparison_recovers_in_a_new_python_process() -> None:
    with application_role_database("t0805", ("process-recovery",)) as database:
        game_id = database.games["process-recovery"]
        result_id = _seed_comparison(database, game_id)
        with Session(database.owner_engine) as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            persisted = SqlAlchemyGridShadowRepository(session).get_result(game_id, result_id)
            assert persisted is not None
            expected = {"id": str(result_id), "sha": persisted.output_checksum_sha256}
        # Credentials travel only through stdin; the subprocess emits identity/checksum only.
        code = """
import json, sys
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_shadow import SqlAlchemyGridShadowRepository
request = json.load(sys.stdin)
engine = create_engine(request['url'], poolclass=NullPool,
    connect_args={'connect_timeout': 5, 'options': '-c statement_timeout=5000'})
try:
    with Session(engine) as session, session.begin():
        game_id = UUID(request['game_id'])
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        result = SqlAlchemyGridShadowRepository(session).get_result(
            game_id, UUID(request['result_id']))
        assert result is not None
        print(json.dumps({'id': str(result.id), 'sha': result.output_checksum_sha256}))
except Exception:
    print('SHADOW_PROCESS_RECOVERY_FAILED', file=sys.stderr)
    sys.exit(1)
finally:
    engine.dispose()
"""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
        response = subprocess.run(
            [sys.executable, "-c", code],
            input=json.dumps(
                {
                    "url": database.app_url.render_as_string(hide_password=False),
                    "game_id": str(game_id),
                    "result_id": str(result_id),
                }
            ),
            env=env,
            cwd=str(Path(__file__).resolve().parents[4]),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert response.returncode == 0, "New-process shadow recovery failed"
        assert json.loads(response.stdout) == expected


def test_publisher_waits_for_game_before_acquiring_source_during_reset() -> None:
    with application_role_database("t0805", ("lock-order",)) as database:
        game_id = database.games["lock-order"]
        args = _seed_comparison(database, game_id, publish=False)
        backend_pid = Queue()

        def publish():
            with Session(database.owner_engine) as session, session.begin():
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
                backend_pid.put(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
                return SqlAlchemyGridShadowRepository(session).publish_result(**args)

        executor = ThreadPoolExecutor(max_workers=1)
        holder = Session(database.owner_engine)
        future = None
        result = None
        try:
            holder.begin()
            holder.execute(text("SET LOCAL statement_timeout = '5s'"))
            GameStorageRouter().bind(holder, game_id, intent=GameStorageIntent.WRITE)
            holder.execute(
                text("SELECT id FROM public.games WHERE id=:id FOR UPDATE"), {"id": game_id}
            )
            future = executor.submit(publish)
            pid = backend_pid.get(timeout=2)
            deadline = time.monotonic() + 2
            waiting_query = None
            with database.owner_engine.connect() as observer:
                observer.execute(text("SET LOCAL statement_timeout = '2s'"))
                while time.monotonic() < deadline:
                    row = observer.execute(
                        text("""SELECT wait_event_type, query FROM pg_stat_activity
                        WHERE pid=:pid"""),
                        {"pid": pid},
                    ).first()
                    if row is not None and row.wait_event_type == "Lock":
                        waiting_query = row.query
                        break
                    # pg_stat_activity snapshots are transaction-local cached.
                    observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    time.sleep(0.025)
            assert waiting_query is not None, "Publisher did not reach the bounded game wait"
            assert "FOR KEY SHARE" in waiting_query and "games" in waiting_query
            # The earlier source->implicit game FK order would already own this source.
            holder.execute(
                text("SELECT id FROM source_images WHERE id=:id FOR UPDATE NOWAIT"),
                {"id": args["pinned_source"]["source_image_id"]},
            )
        finally:
            # Release both locks before joining the blocked publisher, including assertion failures.
            holder.rollback()
            holder.close()
            try:
                if future is not None:
                    result = future.result(timeout=8)
            finally:
                executor.shutdown(wait=True, cancel_futures=True)
        assert result is not None
        assert result.game_id == game_id
        assert result.output_checksum_sha256 == shadow_digest(args["output"])


def test_new_games_receive_manifest_v5_parent_and_child_policy() -> None:
    with application_role_database("t0805", ("shadow-a", "shadow-b")) as database:
        a, b = database.games["shadow-a"], database.games["shadow-b"]
        parent = "image_geometry_shadow_results"
        children = tuple(partition_name(value, parent) for value in (a, b))
        ids = {a: _seed_comparison(database, a), b: _seed_comparison(database, b)}
        with database.owner_engine.connect() as connection:
            versions = (
                connection.execute(
                    text("SELECT manifest_version FROM public.game_storage_locations")
                )
                .scalars()
                .all()
            )
            assert versions == ["game-data-v2-manifest-v5"] * 2
            policies = connection.execute(
                text("""SELECT c.relname, c.relrowsecurity,
                c.relforcerowsecurity, count(p.oid) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_policy p ON p.polrelid = c.oid
                WHERE n.nspname = 'game_data_v2' AND c.relname = ANY(:names)
                GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"""),
                {"names": [parent, *children]},
            ).all()
            assert len(policies) == 3
            assert all(row[1:] == (True, True, 1) for row in policies)
        for scope in (a, b):
            with database.app_engine.begin() as connection:
                if scope is not None:
                    connection.execute(
                        text("SELECT set_config('game_predictor.game_id',:id,true)"),
                        {"id": str(scope)},
                    )
                for table in (parent, *children):
                    rows = connection.execute(
                        text(f"SELECT game_id,id FROM game_data_v2.{table}")
                    ).all()
                    expected = (
                        []
                        if table in children and table != partition_name(scope, parent)
                        else [(scope, ids[scope])]
                    )
                    assert rows == expected
        for table in (parent, *children):
            with database.app_engine.connect() as connection:
                with pytest.raises(DBAPIError) as denied:
                    connection.execute(text(f"SELECT id FROM game_data_v2.{table}"))
                assert getattr(denied.value.orig, "sqlstate", None) == "42501"
        with database.app_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('game_predictor.game_id',:id,true)"), {"id": str(a)}
            )
            plan = str(
                connection.execute(
                    text(
                        f"EXPLAIN (COSTS OFF) SELECT id FROM game_data_v2.{parent} "
                        "WHERE game_id=:id"
                    ),
                    {"id": a},
                ).all()
            )
            assert children[0] in plan and children[1] not in plan
        # A cross-game write must fail with RLS before any FK lookup, both
        # through the parent and through an explicitly addressed child.
        for table in (parent, children[1]):
            with database.app_engine.begin() as connection:
                connection.execute(
                    text("SELECT set_config('game_predictor.game_id',:game_id,true)"),
                    {"game_id": str(a)},
                )
                with pytest.raises(DBAPIError) as denied:
                    connection.execute(
                        text(f"""INSERT INTO game_data_v2.{table}
                        (game_id,id,job_id,source_image_id,source_checksum_sha256,
                        source_geometry_revision_id,source_geometry_revision,
                        source_geometry_checksum_sha256,source_width,source_height,
                        model_profile,model_version,model_manifest_checksum_sha256,
                        source_binding,model_binding,binding_checksum_sha256,
                        status,reasons,output,output_checksum_sha256)
                        VALUES(:game_id,:id,:job_id,:source_id,:sha,:revision_id,1,:sha,
                        100,100,'grid_profile_mumie_v1','v1',:sha,'{{}}','{{}}',:sha,
                        'needs_review','[]','{{}}',:sha)"""),
                        {
                            "game_id": b,
                            "id": uuid4(),
                            "job_id": uuid4(),
                            "source_id": uuid4(),
                            "revision_id": uuid4(),
                            "sha": "a" * 64,
                        },
                    )
                assert getattr(denied.value.orig, "sqlstate", None) == "42501"


def test_existing_games_upgrade_and_nonempty_downgrade_refusal() -> None:
    with application_role_database("t0805", ("existing-shadow",)) as database:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.downgrade(config, "0140_grid_engine_profiles")
        with database.owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT manifest_version FROM public.game_storage_locations")
                ).scalar_one()
                == "game-data-v2-manifest-v4"
            )
        command.upgrade(config, "0142_grid_geometry_shadow_results")
        game_id = database.games["existing-shadow"]
        child = partition_name(game_id, "image_geometry_shadow_results")
        with database.owner_engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE relname=:child"
                ),
                {"child": child},
            ).scalar_one()
        result_id = _seed_comparison(database, game_id)
        with pytest.raises(DBAPIError, match="GRID_SHADOW_DOWNGRADE_NOT_EMPTY"):
            command.downgrade(config, "0140_grid_engine_profiles")
        with database.owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalar_one()
                == "0142_grid_geometry_shadow_results"
            )
        with Session(database.owner_engine) as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            assert (
                SqlAlchemyGridShadowRepository(session).get_result(game_id, result_id) is not None
            )
