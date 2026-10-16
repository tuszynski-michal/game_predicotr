"""Disposable PostgreSQL DDL, application-role CAS and process-restart receipts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    historical_catalogue,
)
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job, start_job
from game_predictor_api.storage.database import assign_session_game
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_partition_lifecycle import (
    CREATE_TABLES,
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.grid_model_registry_models import (
    GameGridModelAssignmentEventModel,
    GridModelEvaluationInvalidationModel,
)
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from services.api.tests.integration.test_grid_model_registry_postgres import definition_sha256
from services.api.tests.test_grid_model_publication_and_activation import (
    execute,
    registry,
    seed_report,
)
from services.api.tests.test_grid_model_registry import candidate

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)


@pytest.fixture
def database() -> Iterator[tuple]:
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task0998_{token}_test", f"task0998_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    settings = {"connect_timeout": 5, "options": "-c statement_timeout=10000"}
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args=settings,
    )
    engine = create_engine(url.set(database=name), poolclass=NullPool, connect_args=settings)
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    receipt = {"database": name, "role": role, "operatorDatabaseChanged": False, "phase": "created"}
    destination = Path("artifacts/audits/TASK-0998_CORRECTION_PG_RECEIPT.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    owned = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        receipt["owner"] = connection.scalar(text("SELECT current_user"))
        owned.create_database(connection)
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    try:
        yield engine, config, role, receipt
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            assert owned.wait_for_owned_database_idle(connection) == 0
            owner = connection.scalar(
                text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:name"),
                {"name": name},
            )
            pids = list(
                connection.scalars(
                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"), {"name": name}
                )
            )
            receipt.update(ownerBeforeCleanup=owner, pidsBeforeCleanup=pids)
            destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            assert owner == receipt["owner"] and not pids, "Refuse unsafe disposable cleanup"
            owned.drop_database(connection)
            receipt["databaseRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
            )
            receipt["roleRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
            )
            receipt["phase"] = "cleaned"
        destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        maintenance.dispose()


def test_migration_parallel_cas_invalidation_restart_and_assignment_boundary(database, tmp_path):
    engine, config, role, receipt = database
    game, other = uuid4(), uuid4()
    baseline = historical_catalogue()[0]
    command.upgrade(config, "0156_grid_model_registry")
    with engine.begin() as connection:
        for game_id, code in ((game, "task0998"), (other, "task0998_other")):
            connection.execute(
                text("""INSERT INTO
public.games(id,code,name,status,shape_geometry_configuration)
VALUES(:id,:code,:code,'draft','neural_grid_v3')"""),
                {"id": game_id, "code": code},
            )
        # Seed only the historical fixture that migration0156 would have pinned.
        connection.execute(
            text("""INSERT INTO
public.game_grid_model_assignments(game_id,version_id,revision) VALUES(:game,:version,1)"""),
            {"game": game, "version": UUID(baseline["versionId"])},
        )
        connection.execute(
            text("""INSERT INTO public.game_grid_model_assignment_events
(game_id,id,idempotency_key,version_id,revision,kind)
VALUES(:game,:key,:key,:version,1,'historical_assignment')"""),
            {"game": game, "key": uuid4(), "version": UUID(baseline["versionId"])},
        )
        definitions = definition_sha256(connection)
        frozen = connection.execute(
            text(
                "SELECT id,manifest_json,manifest_sha256 "
                "FROM public.grid_model_versions ORDER BY id"
            )
        ).all()
        historical = connection.execute(
            text(
                "SELECT game_id,id,idempotency_key,version_id,revision,kind,created_at "
                "FROM public.game_grid_model_assignment_events"
            )
        ).all()
    command.upgrade(config, "0157_grid_model_publication")
    with engine.begin() as connection:
        assert definition_sha256(connection) == definitions
        assert (
            frozen
            == connection.execute(
                text(
                    "SELECT id,manifest_json,manifest_sha256 "
                    "FROM public.grid_model_versions ORDER BY id"
                )
            ).all()
        )
        assert (
            historical
            == connection.execute(
                text(
                    "SELECT game_id,id,idempotency_key,version_id,revision,kind,created_at "
                    "FROM public.game_grid_model_assignment_events"
                )
            ).all()
        )
        assert connection.scalar(text("SELECT count(*) FROM public.grid_model_publications")) == 0
        assert connection.scalar(text("SELECT count(*) FROM public.grid_model_default")) == 0
        OwnedRecordingCapability.for_engine(engine).create_runtime_role(connection, role)
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
        )
    # Exercise the immutable historical boundary before moving runtime to head.
    with pytest.raises(RuntimeError, match="GRID_MODEL_PUBLICATION_DOWNGRADE_REFUSED"):
        command.downgrade(config, "0156_grid_model_registry")
    OwnedRecordingCapability.for_engine(engine).provision()
    command.upgrade(config, "head")
    # Real worker completion reconciles the game's storage; provision the owned
    # catalog-only fixture games before exercising current runtime commands.
    for game_id in (game, other):
        with Session(engine) as session, session.begin():
            operation = GamePartitionLifecycleRepository(session).start_or_resume(
                game_id=game_id,
                kind=GamePartitionLifecycleKind.PROVISION,
            )
        for _ in range(len(CREATE_TABLES) + 2):
            with Session(engine) as session, session.begin():
                state = GamePartitionLifecycleRepository(session).run_next(operation.operation_id)
            if state.status == "done":
                break
        assert state.status == "done"
    with engine.begin() as connection:
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
        )
    factory = sessionmaker(engine)

    def assume_role(session, transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')

    event.listen(factory, "after_begin", assume_role)
    payload = candidate(tmp_path)
    payload["cohortId"] = str(uuid4())
    with factory() as session:
        assert session.execute(
            text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).one() == (False, False)
        service = registry(session, tmp_path)
        service.register(uuid4(), payload)
        evidence_id = seed_report(session, payload, [game])
        execute(service, "publish", baseline["versionId"])
        execute(service, "publish", payload["versionId"], evaluation=evidence_id)
        original_pin = (
            SqlAlchemyGridProfileSnapshotResolver(session, tmp_path)
            ._assigned_snapshot(session.get(GameModel, game))
            .to_payload()
        )
        started = start_job(
            create_job(
                JobType.VALIDATE,
                game_id=game,
                input_payload={
                    "schema_version": 2,
                    "validation_kind": "page_geometry_preflight",
                    "source_selection_id": str(uuid4()),
                    "neural_grid_proposal": original_pin,
                },
            ),
            worker_version="task0998-persisted-fixture",
            worker_id="fixture-no-worker-process",
            lease_token=uuid4(),
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        SqlAlchemyJobRepository(session).add_job(started)
        session.commit()

    barrier = Barrier(2)
    commands = [uuid4(), uuid4()]

    def activate(key):
        with factory() as session:
            service = registry(session, tmp_path)
            # Populate the identity map before the competing commit to test refresh.
            service.game_assignment(game)
            barrier.wait(timeout=10)
            try:
                result = execute(
                    service, "activate", payload["versionId"], game=game, expected=1, key=key
                )
                session.commit()
                return result
            except GridModelRegistryError as error:
                session.rollback()
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(activate, commands))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("GRID_MODEL_REVISION_CONFLICT") == 1
    winner = next(result for result in results if isinstance(result, dict))
    with factory() as session:
        service = registry(session, tmp_path)
        assert service.game_assignment(game)["revision"] == 2
        assert service.game_assignment(other)["version"] is None
        pinned = SqlAlchemyGridProfileSnapshotResolver(
            session, tmp_path
        ).resolve_neural_grid_proposal(game_id=game)
        persisted = SqlAlchemyJobRepository(session).get_job(started.id)
        assert persisted.status is JobStatus.PROCESSING
        assert persisted.input_key == started.input_key
        assert canonical_json(persisted.input_payload) == canonical_json(started.input_payload)
        assert persisted.input_payload["neural_grid_proposal"] == original_pin
        assert original_pin["catalogueManifest"]["versionId"] == baseline["versionId"]
        assert pinned["catalogueManifest"]["versionId"] == payload["versionId"]
        session.commit()
        assert started.lease_token is not None
        started = SqlAlchemyWorkerJobStore(factory).complete(
            started.id,
            lease_token=started.lease_token,
            completed_at=datetime.now(UTC),
        )
        assert started.status is JobStatus.COMPLETED
        candidate_job = create_job(
            JobType.VALIDATE,
            game_id=game,
            input_payload={
                "schema_version": 2,
                "validation_kind": "page_geometry_preflight",
                "source_selection_id": str(uuid4()),
                "neural_grid_proposal": pinned,
            },
        )
        SqlAlchemyJobRepository(session).add_job(candidate_job)
        execute(service, "set_default", payload["versionId"])
        session.add(
            GridModelEvaluationInvalidationModel(
                id=uuid4(),
                report_id=evidence_id,
                reason="test truth revoked",
                actor="server:test-fixture",
            )
        )
        session.commit()
    with factory() as session:
        service = registry(session, tmp_path)
        assert service.control.default_view()["reasonCode"] == "GRID_MODEL_EVALUATION_STALE"
        assert service.game_assignment(game)["version"]["eligible"] is False
        # Invalidation is not implicit deactivation. New preflight keeps assignment.
        after = SqlAlchemyGridProfileSnapshotResolver(
            session, tmp_path
        ).resolve_neural_grid_proposal(game_id=game)
        assert after == pinned
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"):
            execute(service, "activate", payload["versionId"], game=game, expected=2)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_STALE"):
            execute(service, "activate", payload["versionId"], game=other)
        assign_session_game(session, game)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_GAME_SCOPE_CONFLICT"):
            execute(service, "activate", baseline["versionId"], game=other)

    # Retry in a fresh interpreter after truth invalidation: no mutable head reset.
    program = """
import json, os
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector, SqlAlchemyGridModelRegistryRepository)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
url=make_url(os.environ['TASK0998_TEST_URL'])
assert url.database == os.environ['TASK0998_TEST_NAME']
assert url.database.startswith('game_predictor_task0998_')
engine=create_engine(url, connect_args={'connect_timeout':5,'options':'-c statement_timeout=10000'})
try:
    with Session(engine) as session:
        session.execute(text('SET LOCAL ROLE "' + os.environ['TASK0998_TEST_ROLE'] + '"'))
        service=GridModelRegistryService(SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(Path(os.environ['TASK0998_ARTIFACT_ROOT'])))
        original=json.loads(os.environ['TASK0998_RECEIPT'])
        result=service.control.execute(kind='activate', key=UUID(original['idempotencyKey']),
            expected_revision=original['expectedRevision'], version_id=UUID(original['versionId']),
            game_id=UUID(original['gameId']), actor=original['actor'])
        assert result==original
        assert service.game_assignment(UUID(original['gameId']))['revision']==3
        repository=SqlAlchemyJobRepository(session)
        for identity, expected in json.loads(os.environ['TASK0998_JOB_PINS']):
            job=repository.get_job(UUID(identity))
            assert job.input_payload['neural_grid_proposal']==expected
        print('receipt-recovered')
finally: engine.dispose()
"""
    environment = os.environ.copy()
    environment.update(
        TASK0998_TEST_URL=engine.url.render_as_string(hide_password=False),
        TASK0998_TEST_NAME=receipt["database"],
        TASK0998_TEST_ROLE=role,
        TASK0998_ARTIFACT_ROOT=str(tmp_path),
        TASK0998_RECEIPT=json.dumps(winner),
        TASK0998_JOB_PINS=json.dumps(
            [(str(started.id), original_pin), (str(candidate_job.id), pinned)]
        ),
        PYTHONPATH=os.pathsep.join(
            str(Path.cwd() / p)
            for p in ("services/api/src", "services/worker/src", "services/test_support")
        ),
    )
    with factory() as session:
        service = registry(session, tmp_path)
        execute(service, "rollback", baseline["versionId"], game=game, expected=2)
        session.commit()
        assert service.game_assignment(game)["revision"] == 3
        assert service.control.default_view()["version"]["manifest"] == payload
        assert (
            len(
                list(
                    session.scalars(
                        select(GameGridModelAssignmentEventModel).where(
                            GameGridModelAssignmentEventModel.game_id == game
                        )
                    )
                )
            )
            == 3
        )
    # A new session observes the persisted jobs after both real control commands.
    with factory() as session:
        jobs = SqlAlchemyJobRepository(session)
        for original in (started, candidate_job):
            stored = jobs.get_job(original.id)
            assert stored.status is original.status
            assert stored.input_key == original.input_key
            assert canonical_json(stored.input_payload) == canonical_json(original.input_payload)
        assert jobs.get_job(started.id).input_payload["neural_grid_proposal"] == original_pin
        assert jobs.get_job(candidate_job.id).input_payload["neural_grid_proposal"] == pinned
    result = subprocess.run(
        [sys.executable, "-c", program], env=environment, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "receipt-recovered"
    for sql in (
        "UPDATE public.grid_model_publications SET evidence_json='{}'",
        "DELETE FROM public.grid_model_evaluation_reports",
        "DELETE FROM public.grid_model_evaluation_invalidations",
        "DELETE FROM public.grid_model_control_events",
        "DELETE FROM public.game_grid_model_assignment_events",
    ):
        with pytest.raises(DBAPIError, match="GRID_MODEL_IMMUTABLE"), engine.begin() as connection:
            connection.execute(text(sql))
    receipt.update(
        gameDataDefinitionsBeforeSha256=definitions,
        gameDataDefinitionsAfterSha256=definitions,
        verified=[
            "0156_to_0157",
            "frozen_descriptors_and_historical_events_unchanged",
            "zero_implicit_publications_or_default",
            "application_NOBYPASSRLS",
            "concurrent_CAS_one_winner",
            "stale_identity_map_refresh",
            "fresh_interpreter_lost_response_retry",
            "persisted_processing_job_pin_survives_activate_and_rollback",
            "persisted_candidate_job_pin_survives_rollback_and_fresh_interpreter",
            "immutable_proof_and_control_history",
            "invalidation_blocks_commands_not_existing_assignment_preflight",
            "default_no_game_switch",
            "rollback_assignment_only",
            "cross_game_refused",
            "downgrade_refused",
        ],
    )
