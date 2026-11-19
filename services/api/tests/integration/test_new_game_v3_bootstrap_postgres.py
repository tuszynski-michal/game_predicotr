"""Owned disposable PostgreSQL: first-commit atomicity, DDL resume and fresh-process retry."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.application.grid_correction_learning import (
    GridCorrectionLearningService,
    child_key,
)
from game_predictor_api.application.new_game_geometry import NewGameGeometryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration, GameStatus
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import GameStorageSession, create_owner_session_factory
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_create_receipts import SqlAlchemyGameCreateReceiptRepository
from game_predictor_api.storage.game_data_v2_manifest_v19 import VERSION
from game_predictor_api.storage.grid_private_learning import assignment_pin
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from game_predictor_api.storage.job_repository import job_record_from_domain
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from test_grid_model_publication_and_activation import execute, registry

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


@pytest.fixture
def database():
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task1004_{token}_test", f"task1004_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    connect_args = {"connect_timeout": 5, "options": "-c statement_timeout=15000"}
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args=connect_args,
    )
    engine = create_engine(url.set(database=name), poolclass=NullPool, connect_args=connect_args)
    receipt = {
        "database": name,
        "role": role,
        "operatorDatabaseChanged": False,
        "pythonPid": os.getpid(),
        "phase": "created",
    }
    destination = Path("artifacts/audits/TASK-1004_PG_RECEIPT.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    recording_capability_fixture = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        receipt["owner"] = connection.scalar(text("SELECT current_user"))
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        recording_capability_fixture.record_created_database(connection)
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    try:
        recording_capability_fixture.provision()
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        with engine.begin() as connection:
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
            )
        yield engine, role, receipt, url.set(database=name)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
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
            assert owner == receipt["owner"] and not pids, "Refuse unsafe fixture cleanup"
            recording_capability_fixture.assert_database_identity(connection)
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
            recording_capability_fixture.cleanup(connection)
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            receipt["databaseRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
            )
            receipt["roleRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
            )
            receipt["phase"] = "cleaned"
        destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        maintenance.dispose()


def shared_grid_catalog(database, tmp_path):
    engine, role, _, _ = database
    with engine.begin() as connection:
        assert not connection.scalar(text("SELECT bool_or(grid_model_private) FROM public.games"))
        first, second = uuid4(), uuid4()
        connection.execute(
            text("""INSERT INTO public.games (id, code, name, status, shape_geometry_configuration)
                VALUES (:first, 'legacy-mumie', 'Mumie', 'draft', 'grid_profile_mumie_v1'),
                       (:second, 'legacy-other', 'Other', 'draft', 'neural_grid_v3')"""),
            {"first": first, "second": second},
        )

    def new_session():
        session = Session(engine)
        session.execute(text(f'SET LOCAL ROLE "{role}"'))
        return session

    def service(session):
        return NewGameGeometryService(
            None, SqlAlchemyGameCreateReceiptRepository(session), registry(session, tmp_path)
        )

    with new_session() as session:
        create = service(session)
        baseline = create.registry.repository.versions()[0]
        execute(create.registry, "publish", str(baseline.id))
        execute(create.registry, "activate", str(baseline.id), game=first)
        baseline_id = baseline.id
        session.commit()

    return engine, new_session, service, first, second, baseline_id


def test_private_enrollment_preserves_import_waiting_for_review(database, tmp_path):
    _, new_session, service, first, _, baseline_id = shared_grid_catalog(database, tmp_path)
    with new_session() as session:
        imported = job_record_from_domain(
            create_job(
                JobType.IMPORT,
                game_id=first,
                input_payload={"schema_version": 1, "import_kind": "image_directory"},
            )
        )
        imported.stage = "image_pipeline:symbol_inference"
        session.add(imported)
        session.flush()
        repository = service(session).registry.repository
        assert repository.active_grid_operation(first) == imported.id
        processing = session.begin_nested()
        imported.status = JobStatus.PROCESSING
        imported.execution_slot = 1
        imported.lease_owner, imported.lease_token = "test-import-worker", uuid4()
        imported.heartbeat_at = imported.created_at
        imported.lease_expires_at = imported.created_at + timedelta(minutes=1)
        session.flush()
        assert repository.active_grid_operation(first) == imported.id
        processing.rollback()
        imported.status = JobStatus.WAITING_FOR_REVIEW
        for stage in (None, "image_pipeline:board_detection"):
            imported.stage = stage
            session.flush()
            assert repository.active_grid_operation(first) == imported.id
        for stage in (
            "image_pipeline:symbol_inference",
            "image_pipeline:manual_review",
            "image_pipeline:validation",
        ):
            imported.stage = stage
            session.flush()
            assert repository.active_grid_operation(first) is None
        imported_id = imported.id
        session.commit()
    with new_session() as session:
        result = service(session).enable_private_model(
            game_id=first, key=uuid4(), expected_revision=1, actor="local-owner"
        )
        assert result["versionId"] == str(baseline_id)
        session.commit()
    with new_session() as session:
        assert session.execute(
            text("SELECT status,stage FROM public.jobs WHERE id=:job"), {"job": imported_id}
        ).one() == ("waiting_for_review", "image_pipeline:validation")


def test_private_enrollment_fences_other_games_queued_and_historical_cohorts(database, tmp_path):
    engine, new_session, service, first, second, baseline_id = shared_grid_catalog(
        database, tmp_path
    )
    cohort_id = uuid4()

    def shared_job():
        return job_record_from_domain(
            create_job(
                JobType.GRID_TRAINING,
                game_id=second,
                input_payload={
                    "schema_version": 1,
                    "training_kind": "grid-shared-training-run-v1",
                    "idempotency_key": str(uuid4()),
                    "shared_cohorts": [
                        {"game_id": str(first).upper(), "cohort_id": str(cohort_id)}
                    ],
                },
            )
        )

    key = uuid4()

    def enable():
        with new_session() as session:
            result = service(session).enable_private_model(
                game_id=first, key=key, expected_revision=1, actor="local-owner"
            )
            session.commit()
        return result

    with new_session() as session, ThreadPoolExecutor(max_workers=1) as other:
        job = shared_job()
        session.add(job)
        session.flush()  # Holds the catalogue fence across job admission and commit.
        job_id = job.id
        waiting = other.submit(enable)
        session.commit()
        with pytest.raises(
            GridModelRegistryError, match="GRID_MODEL_PRIVATE_OPERATION_ACTIVE"
        ) as error:
            waiting.result(timeout=8)
        assert error.value.details == {"jobId": str(job_id)}

    with new_session() as session:
        session.execute(
            text("UPDATE public.jobs SET status='completed' WHERE id=:job"), {"job": job_id}
        )
        session.commit()
    result = enable()
    assert result["versionId"] == str(baseline_id) and result["revision"] == 2
    assert enable() == result  # New session after a simulated lost response.

    with new_session() as session:
        for operation in ("insert", "resume"):
            with (
                pytest.raises(DBAPIError, match="GRID_SHARED_PRIVATE_GAME"),
                session.begin_nested(),
            ):
                if operation == "insert":
                    session.add(shared_job())
                    session.flush()
                else:
                    session.execute(
                        text("UPDATE public.jobs SET status='created' WHERE id=:job"),
                        {"job": job_id},
                    )
        assert (
            session.scalar(text("SELECT status FROM public.jobs WHERE id=:job"), {"job": job_id})
            == JobStatus.COMPLETED.value
        )

    with engine.begin() as connection:
        private_version = uuid4()
        connection.execute(
            text("""INSERT INTO public.grid_model_versions
                (id, family_id, version, base_version_id, manifest_json, manifest_sha256)
                SELECT :private, CAST(:family AS uuid), 'v-test', id, manifest_json, manifest_sha256
                FROM public.grid_model_versions WHERE id=:base"""),
            {"private": private_version, "family": result["trainingFamilyId"], "base": baseline_id},
        )
        connection.execute(text("DELETE FROM public.games WHERE id=:game"), {"game": first})
        assert (
            connection.scalar(
                text("SELECT owner_game_id FROM public.grid_model_families WHERE id=:family"),
                {"family": result["trainingFamilyId"]},
            )
            == first
        )
        with (
            pytest.raises(DBAPIError, match="GRID_MODEL_PRIVATE_DEFAULT"),
            connection.begin_nested(),
        ):
            connection.execute(
                text("""INSERT INTO public.grid_model_default(id, version_id, revision)
                    VALUES ('geometry-v3', :private, 1)"""),
                {"private": private_version},
            )


def test_reservation_rollback_partition_restart_application_role_and_create_races(
    database, tmp_path
):
    engine, role, receipt, url = database
    factory = sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False)

    def assume_role(_session, _transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')

    event.listen(factory, "after_begin", assume_role)

    def service(session):
        catalog = SqlAlchemyCatalogRepository(
            session, partition_ddl_session_factory=create_owner_session_factory(engine)
        )
        return catalog, NewGameGeometryService(
            catalog, SqlAlchemyGameCreateReceiptRepository(session), registry(session, tmp_path)
        )

    fields = dict(
        code="reserved",
        name="Reserved",
        status=GameStatus.DRAFT,
        expected_layout_count=100,
        shape_geometry_configuration=GameShapeGeometryConfiguration.NEURAL_GRID_V3,
        super_game_kind="none",
    )
    with factory() as session:
        assert tuple(
            session.execute(
                text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            ).one()
        ) == (False, False)
        catalog, create = service(session)
        control = create.registry
        version = control.repository.versions()[0].id
        execute(control, "publish", str(version))
        execute(control, "set_default", str(version))
        session.commit()

        def fail(*_args):
            raise RuntimeError("before first commit")

        original_record = create.receipts.record

        def fail_after_record(*args):
            original_record(*args)
            fail()

        create.receipts.record = fail_after_record
        try:
            with pytest.raises(RuntimeError, match="before first commit"):
                create.create(
                    key=uuid4(),
                    fields=fields,
                    selection={
                        "mode": "fork",
                        "baseVersionId": str(version),
                        "familyCode": "rolled_back",
                        "familyLabel": "Rollback",
                    },
                )
        finally:
            create.receipts.record = original_record
            session.rollback()
    with engine.connect() as connection:
        for table in (
            "games",
            "game_storage_locations",
            "game_storage_lifecycle_operations",
            "game_create_receipts",
            "game_grid_model_assignments",
            "game_grid_model_assignment_events",
            "grid_model_family_forks",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM public.{table}")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.grid_model_families WHERE code='rolled_back'")
            )
            == 0
        )

    # R1 recovery qualifies a rejected command only after rollback and a fresh
    # real PostgreSQL advisory lock; all writes remain under the application role.
    from game_predictor_api.domain.catalog import CatalogConflictError

    rejected_key = uuid4()
    with factory() as session:
        catalog, _ = service(session)
        with pytest.raises(GridModelRegistryError) as rejected:
            catalog.add_game(
                **{**fields, "code": "rejected"},
                idempotency_key=rejected_key,
                grid_model={"mode": "published", "versionId": str(uuid4())},
            )
        assert rejected.value.details["createRecovery"] == {
            "schemaVersion": "game-create-recovery-v1",
            "idempotencyKey": str(rejected_key),
            "reservation": "not_created",
        }
        assert SqlAlchemyGameCreateReceiptRepository(session).receipt(rejected_key) is None
    receipt["rejectedCommandRecovery"] = "passed"

    key = uuid4()
    with factory() as session:
        catalog, create = service(session)
        original = catalog._run_partition_step
        steps = 0

        def interrupt(operation_id):
            nonlocal steps
            if steps == 2:
                raise RuntimeError("restart after checkpoint")
            steps += 1
            return original(operation_id)

        catalog._run_partition_step = interrupt
        with pytest.raises(RuntimeError, match="restart after checkpoint"):
            create.create(key=key, fields=fields, selection={"mode": "default"})
        session.rollback()
    with engine.connect() as connection:
        game_id = connection.scalar(text("SELECT id FROM public.games WHERE code='reserved'"))
        assert (
            connection.scalar(
                text("SELECT status FROM public.game_storage_locations WHERE game_id=:id"),
                {"id": game_id},
            )
            == "migrating"
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.game_grid_model_assignments WHERE game_id=:id"),
                {"id": game_id},
            )
            == 1
        )
        receipt["reservedGameId"] = str(game_id)

    with factory() as session:
        catalog, _ = service(session)
        before = SqlAlchemyGameCreateReceiptRepository(session).receipt(key).reservation_sha256
        with pytest.raises(GridModelRegistryError) as conflict:
            catalog.add_game(**{**fields, "name": "Changed command"}, idempotency_key=key)
        assert conflict.value.code == "GAME_CREATE_IDEMPOTENCY_CONFLICT"
        assert "createRecovery" not in conflict.value.details

        def storage_not_ready(_operation_id):
            raise CatalogConflictError("GAME_CREATE_STORAGE_NOT_READY", "Interrupted storage")

        catalog._run_partition_step = storage_not_ready
        with pytest.raises(CatalogConflictError) as interrupted:
            catalog.add_game(**fields, idempotency_key=key)
        assert "createRecovery" not in interrupted.value.details
        assert (
            SqlAlchemyGameCreateReceiptRepository(session).receipt(key).reservation_sha256 == before
        )
    receipt["existingReceiptRecoveryPreserved"] = "passed"

    child = r"""
import os, json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from game_predictor_api.storage.database import GameStorageSession,create_owner_session_factory
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.domain.catalog import GameStatus
url=make_url(os.environ['TASK1004_URL'])
assert url.database == os.environ['TASK1004_DB']
assert url.database.startswith('game_predictor_task1004_')
assert url.database.endswith('_test')
engine=create_engine(url,poolclass=NullPool,
    connect_args={'connect_timeout':5,'options':'-c statement_timeout=15000'})
factory=sessionmaker(bind=engine,class_=GameStorageSession,expire_on_commit=False)
def assume(session,transaction,connection):
    connection.exec_driver_sql('SET LOCAL ROLE "'+os.environ['TASK1004_ROLE']+'"')
event.listen(factory,'after_begin',assume)
with factory() as session:
 repo=SqlAlchemyCatalogRepository(session,partition_ddl_session_factory=create_owner_session_factory(engine))
 game=CatalogService(repo).create_game(idempotency_key=UUID(os.environ['TASK1004_KEY']),code='reserved',name='Reserved',status=GameStatus.DRAFT,expected_layout_count=100)
 session.commit()
 assert str(game.id)==os.environ['TASK1004_GAME'] and game.storage_write_available
 print(json.dumps({'gameId':str(game.id),'status':game.storage_status,'pid':os.getpid()}))
engine.dispose()
"""
    env = dict(
        os.environ,
        TASK1004_URL=url.render_as_string(hide_password=False),
        TASK1004_DB=receipt["database"],
        TASK1004_ROLE=role,
        TASK1004_KEY=str(key),
        TASK1004_GAME=str(game_id),
        PYTHONUTF8="1",
    )
    env["PYTHONPATH"] = os.pathsep.join(
        str(Path(p).resolve())
        for p in ("services/api/src", "services/worker/src", "services/test_support")
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", child],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=70,
    )
    assert completed.returncode == 0, completed.stderr
    receipt["freshProcess"] = json.loads(completed.stdout)
    with factory() as session:
        _, create = service(session)
        result = create.create(key=key, fields=fields, selection={"mode": "default"})
        assert result.id == game_id and result.storage_write_available
        with pytest.raises(GridModelRegistryError, match="IDEMPOTENCY_CONFLICT"):
            create.create(
                key=key, fields={**fields, "name": "Changed"}, selection={"mode": "default"}
            )
    race_key = uuid4()

    def race():
        with factory() as session:
            _, create = service(session)
            result = create.create(
                key=race_key, fields={**fields, "code": "race"}, selection={"mode": "default"}
            )
            session.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: race(), range(2)))
    assert len(set(outcomes)) == 1
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.game_create_receipts")) == 2
        assert (
            connection.scalar(text("SELECT count(*) FROM public.game_grid_model_assignment_events"))
            == 2
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.game_storage_lifecycle_operations "
                    "WHERE status<>'done'"
                )
            )
            == 0
        )
        assert set(
            connection.scalars(text("SELECT manifest_version FROM public.game_storage_locations"))
        ) == {VERSION}
    from game_predictor_api.domain.jobs import JobConflictError
    from game_predictor_api.storage.symbol_model_snapshot_resolver import (
        SqlAlchemySymbolModelSnapshotResolver,
    )

    with factory() as session:
        symbols = SqlAlchemySymbolModelSnapshotResolver(session, artifact_root=tmp_path)
        with pytest.raises(JobConflictError) as untrained:
            symbols.resolve(game_id=game_id)
        assert untrained.value.code == "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED"
        assert symbols.resolve_unclassified_cold_start(game_id=game_id) is None
    from game_predictor_api.application.catalog import CatalogService
    from game_predictor_api.domain.catalog import SymbolStatus

    for target, codes in ((outcomes[0], ("FOREIGN",)), (game_id, ("OWN_A", "OWN_B"))):
        with factory() as session:
            catalog_service = CatalogService(SqlAlchemyCatalogRepository(session))
            for index, code in enumerate(codes, 1):
                catalog_service.create_symbol(
                    target,
                    mobile_code=index,
                    code=code,
                    name=code,
                    image_path=None,
                    is_wildcard=False,
                    display_order=index,
                    status=SymbolStatus.ACTIVE,
                )
            session.commit()
    with factory() as session:
        symbols = SqlAlchemySymbolModelSnapshotResolver(session, artifact_root=tmp_path)
        cold_start = symbols.resolve_unclassified_cold_start(game_id=game_id)
        assert cold_start is not None and cold_start.class_codes == ("OWN_A", "OWN_B")
        assert cold_start.inference_mode == "unclassified" and cold_start.iteration_id is None
    receipt["emptyGameSymbolIsolation"] = "passed"
    receipt["reservationAtomicity"] = "passed"
    receipt["freshProcessResume"] = "passed"
    receipt["sameKeyConcurrency"] = "passed"


def test_private_freeze_releases_parent_registry_lock(database, tmp_path, monkeypatch):
    engine, new_session, create, game, _, _ = shared_grid_catalog(database, tmp_path)
    with new_session() as session:
        geometry = create(session)
        geometry.enable_private_model(
            game_id=game, key=uuid4(), expected_revision=1, actor="local-owner"
        )
        pin = assignment_pin(geometry.registry.repository, game)
        session.commit()
    document = {
        "privateLearning": pin,
        "photoSplit": {"sha256": "split"},
        "cropPolicyVersion": "full-cell-v2",
        "detectorReadiness": {},
    }

    class ParentSession(Session):
        def get(self, entity, ident, **kwargs):
            if entity is GridTrainingCohortModel:
                return SimpleNamespace(document=document)
            return super().get(entity, ident, **kwargs)

    learning = GridCorrectionLearningService(
        engine, sessionmaker(bind=engine, class_=ParentSession), tmp_path
    )
    header = {
        "status": "ready_to_freeze",
        "revision": 4,
        "previewSha256": "preview",
        "manifestSha256": "manifest",
    }
    calls = []

    def freeze(game_id, cohort_id, kind, body, actor):
        # A different PostgreSQL connection must be able to take the very same lock.
        with engine.begin() as db:
            assert db.scalar(text("SELECT pg_try_advisory_xact_lock(9910994)"))
        calls.append((kind, body))

    cohorts = SimpleNamespace(
        repository=SimpleNamespace(bind=lambda game_id: None),
        get=lambda game_id, cohort_id: header,
        command=freeze,
    )
    monkeypatch.setattr(learning, "_cohorts", lambda session: cohorts)
    job = SimpleNamespace(
        id=uuid4(),
        game_id=game,
        checkpoint_payload={},
        input_payload={
            "actor": "local-owner",
            "preview": {"detectorReadiness": {}},
            "pins": {"privateLearning": pin, "splitSha256": "split"},
        },
    )
    state, done = learning.advance(job)
    assert not done and state["cohortId"]
    assert calls == [
        (
            "freeze",
            {
                "expectedRevision": 4,
                "idempotencyKey": str(child_key(job.id, "freeze:4")),
                "expectedPreviewSha256": "preview",
                "expectedManifestSha256": "manifest",
            },
        )
    ]
