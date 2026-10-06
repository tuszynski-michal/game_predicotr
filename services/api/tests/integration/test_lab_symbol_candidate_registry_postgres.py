"""TASK-0881: disposable database only; migration, RLS and process recovery."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryService
from game_predictor_api.domain import lab_symbol_candidate as lab
from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType, create_job
from game_predictor_api.domain.symbol_model_registry import SymbolModelActivationAction
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.job_repository import job_record_from_domain
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
    SqlAlchemyLabSymbolCandidateImportRepository,
)
from game_predictor_api.storage.models import JobModel, SymbolModel, SymbolModelIterationModel
from game_predictor_api.storage.symbol_model_registry_repository import (
    SqlAlchemySymbolModelRegistryRepository,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL tests only.",
)


def test_migration_preserves_legacy_import_recovery_and_deactivation(tmp_path, monkeypatch):
    with application_role_database("t0881", ("mumie-pilot", "legacy777")) as database:
        assert database.owner_url.database.endswith("_test")
        assert database.owner_url.database != "game_predictor"
        game_id = database.games["mumie-pilot"]
        legacy_game = database.games["legacy777"]
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url",
            database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.downgrade(config, "0143_merge_share_grid_shadow")
        legacy_job = create_job(
            JobType.VALIDATE,
            game_id=legacy_game,
            input_payload={
                "schema_version": 1,
                "dataset_version_id": str(uuid4()),
            },
        )
        cohort_id, iteration_id = uuid4(), uuid4()
        with Session(database.owner_engine) as session, session.begin():
            session.add(job_record_from_domain(legacy_job))
            session.flush()
            session.execute(
                text("""INSERT INTO game_data_v2.verified_training_cohorts
                (id,game_id,iteration_number,manifest_schema_version,dataset_kind,
                 manifest_checksum_sha256,idempotency_key,command_sha256,
                 resolved_layout_count,cell_sample_count,source_image_count,pending_item_count,
                 rejected_item_count,incomplete_item_count,artifact_relative_path,created_by)
                VALUES (:id,:game,1,1,'verified-training-cohort-v1',:sha,:key,:sha,
                        1,15,1,0,0,0,'test/cohort.json','test-owner')"""),
                {"id": cohort_id, "game": legacy_game, "sha": "a" * 64, "key": uuid4()},
            )
            session.execute(
                text("""INSERT INTO game_data_v2.symbol_model_iterations
                (id,game_id,cohort_id,job_id,iteration_number,status,configuration_fingerprint,
                 configuration_payload,gate_metrics,rejection_reasons,last_completed_epoch,partial_metrics)
                VALUES (:id,:game,:cohort,:job,1,'created',:sha,'{}','{}','{}',0,'{}')"""),
                {
                    "id": iteration_id,
                    "game": legacy_game,
                    "cohort": cohort_id,
                    "job": legacy_job.id,
                    "sha": "b" * 64,
                },
            )
        command.upgrade(config, "0144_lab_symbol_candidate_registry")
        with database.owner_engine.connect() as connection:
            legacy = connection.execute(
                text(
                    "SELECT cohort_id,origin,origin_fingerprint "
                    "FROM game_data_v2.symbol_model_iterations "
                    "WHERE game_id=:game AND id=:id"
                ),
                {"game": legacy_game, "id": iteration_id},
            ).one()
            assert legacy == (cohort_id, "production_training", None)
        with pytest.raises(IntegrityError), database.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE game_data_v2.symbol_model_iterations SET cohort_id=NULL "
                    "WHERE game_id=:game AND id=:id"
                ),
                {"game": legacy_game, "id": iteration_id},
            )
        model = b"qualified-import-postgres-fixture"
        evidence = {"classes": list(lab.MUMIE_CLASS_LABELS), "eligible": True}
        checksum = lab.digest(evidence)
        monkeypatch.setattr(lab, "MUMIE_ELIGIBILITY_ID", checksum)
        monkeypatch.setattr(lab, "MUMIE_R2_ONNX_SHA256", hashlib.sha256(model).hexdigest())
        candidate = lab.prepare_mumie_candidate(
            tmp_path,
            game_id=game_id,
            onnx_content=model,
            eligibility_content=lab.canonical({"payload": evidence, "sha256": checksum}),
        )
        with Session(database.owner_engine) as session, session.begin():
            for number, code in enumerate(lab.MUMIE_CLASS_CODES, 1):
                session.add(
                    SymbolModel(
                        id=uuid4(),
                        game_id=game_id,
                        code=code,
                        name=code,
                        status="active",
                        mobile_code=number,
                        display_order=number,
                    )
                )
        sessions = create_session_factory(database.app_engine)
        key = uuid4()
        with sessions() as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
            iteration, job, created = SqlAlchemyLabSymbolCandidateImportRepository(session).start(
                game_id=game_id,
                fingerprint=candidate.fingerprint,
                idempotency_key=key,
                artifact_root=tmp_path,
            )
            assert created and iteration.cohort_id is None
        with sessions() as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
            record = session.get(JobModel, job.id)
            record.status = JobStatus.PROCESSING
            record.execution_slot = 1
            record.lease_owner = "test-worker"
            record.lease_token = uuid4()
            record.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
            record.heartbeat_at = datetime.now(UTC)
            session.flush()
            SqlAlchemyLabSymbolCandidateImportRepository(session).publish(
                game_id=game_id,
                job_id=job.id,
                lease_owner=record.lease_owner,
                lease_token=record.lease_token,
                artifact_root=tmp_path,
            )
            record.status = JobStatus.COMPLETED
            record.execution_slot = record.lease_owner = record.lease_token = (
                record.lease_expires_at
            ) = record.heartbeat_at = None
        script = """
import json,sys
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import GameStorageRouter,GameStorageIntent
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
 SqlAlchemyLabSymbolCandidateImportRepository,
)
data=json.loads(sys.stdin.read())
engine=create_engine(data['url'],connect_args={'connect_timeout':5})
try:
 with create_session_factory(engine)() as session,session.begin():
  game=UUID(data['game'])
  GameStorageRouter().bind(session,game,intent=GameStorageIntent.WRITE)
  iteration,job,created=SqlAlchemyLabSymbolCandidateImportRepository(session).start(
   game_id=game,fingerprint=data['fingerprint'],idempotency_key=UUID(data['key']),
   artifact_root=Path(data['root']))
  print(json.dumps({'iteration':str(iteration.id),'job':str(job.id),'created':created}))
finally:
 engine.dispose()
"""
        # Only receipt replay runs in the cold process; the fixture's test model
        # qualification is intentionally local and no credentials are printed.
        process = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps(
                {
                    "url": database.app_url.render_as_string(hide_password=False),
                    "game": str(game_id),
                    "fingerprint": candidate.fingerprint,
                    "key": str(key),
                    "root": str(tmp_path),
                }
            ),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert process.returncode == 0, "New-process receipt recovery failed."
        assert json.loads(process.stdout) == {
            "iteration": str(iteration.id),
            "job": str(job.id),
            "created": False,
        }
        with sessions() as session, session.begin():
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
            registry = SymbolModelRegistryService(
                SqlAlchemySymbolModelRegistryRepository(session, artifact_root=tmp_path)
            )
            preview = registry.preview(
                game_id=game_id,
                model_iteration_id=iteration.id,
                action=SymbolModelActivationAction.ACTIVATE,
            )
            activation, _ = registry.activate(
                game_id=game_id,
                model_iteration_id=iteration.id,
                expected_manifest_checksum_sha256=preview.candidate_manifest_checksum_sha256,
                expected_current_model_iteration_id=None,
                action=SymbolModelActivationAction.ACTIVATE,
                actor="test-owner",
                reason="pilot acceptance",
                idempotency_key=uuid4(),
            )
            snapshot = SqlAlchemySymbolModelSnapshotResolver(
                session, artifact_root=tmp_path
            ).resolve(game_id=game_id)
            assert snapshot.crop_size == 96 and snapshot.input_size == 64
            deactivation_key = uuid4()
            arguments = dict(
                game_id=game_id,
                model_iteration_id=None,
                expected_manifest_checksum_sha256=None,
                expected_current_model_iteration_id=iteration.id,
                action=SymbolModelActivationAction.DEACTIVATE,
                actor="test-owner",
                reason="disable pilot",
                idempotency_key=deactivation_key,
            )
            disabled, created = registry.activate(**arguments)
            assert created and disabled.model_iteration_id is None
            assert registry.activate(**arguments) == (disabled, False)
            with pytest.raises(JobConflictError) as error:
                SqlAlchemySymbolModelSnapshotResolver(session, artifact_root=tmp_path).resolve(
                    game_id=game_id
                )
            assert error.value.code == "SYMBOL_MODEL_ACTIVATION_REQUIRED"
        with pytest.raises(Exception, match="LAB_SYMBOL_REGISTRY_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0143_merge_share_grid_shadow")
        with (
            pytest.raises(DBAPIError, match="GAME_STORAGE_SCOPE_REQUIRED"),
            database.app_engine.connect() as connection,
        ):
            connection.scalar(text("SELECT count(*) FROM game_data_v2.symbol_model_iterations"))
        with sessions() as session, session.begin():
            GameStorageRouter().bind(session, legacy_game, intent=GameStorageIntent.READ)
            assert (
                session.get(
                    SymbolModelIterationModel,
                    iteration.id,
                )
                is None
            )
