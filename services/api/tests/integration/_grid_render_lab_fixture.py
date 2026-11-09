"""Synthetic model bytes, real verified import/activation/resolver in a disposable DB."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryService
from game_predictor_api.domain import lab_symbol_candidate as lab
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.symbol_model_registry import SymbolModelActivationAction
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
    SqlAlchemyLabSymbolCandidateImportRepository,
)
from game_predictor_api.storage.models import JobModel, SymbolModel
from game_predictor_api.storage.symbol_model_registry_repository import (
    SqlAlchemySymbolModelRegistryRepository,
)
from sqlalchemy import update
from sqlalchemy.orm import Session


def configure_lab_fixture(monkeypatch):
    model = b"task1172-qualified-model-fixture-no-inference"
    evidence = {"classes": list(lab.MUMIE_CLASS_LABELS), "eligible": True}
    checksum = lab.digest(evidence)
    monkeypatch.setattr(lab, "MUMIE_ELIGIBILITY_ID", checksum)
    monkeypatch.setattr(lab, "MUMIE_R2_ONNX_SHA256", hashlib.sha256(model).hexdigest())
    return model, evidence, checksum


def install_active_lab(db, root, game, factory, monkeypatch):
    model, evidence, checksum = configure_lab_fixture(monkeypatch)
    candidate = lab.prepare_mumie_candidate(
        root,
        game_id=game,
        onnx_content=model,
        eligibility_content=lab.canonical({"payload": evidence, "sha256": checksum}),
    )
    with Session(db.owner_engine) as session, session.begin():
        session.execute(
            update(SymbolModel).where(SymbolModel.game_id == game).values(status="archived")
        )
        for number, code in enumerate(lab.MUMIE_CLASS_CODES, 2):
            session.add(
                SymbolModel(
                    id=uuid4(),
                    game_id=game,
                    code=code,
                    name=code,
                    status="active",
                    mobile_code=number,
                    display_order=number,
                )
            )
    with factory.begin() as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
        iteration, job, _ = SqlAlchemyLabSymbolCandidateImportRepository(session).start(
            game_id=game,
            fingerprint=candidate.fingerprint,
            idempotency_key=uuid4(),
            artifact_root=root,
        )
        record = session.get(JobModel, job.id)
        record.status = JobStatus.PROCESSING
        record.execution_slot = 1
        record.lease_owner = "test-worker"
        record.lease_token = uuid4()
        record.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        record.heartbeat_at = datetime.now(UTC)
        session.flush()
        SqlAlchemyLabSymbolCandidateImportRepository(session).publish(
            game_id=game,
            job_id=job.id,
            lease_owner=record.lease_owner,
            lease_token=record.lease_token,
            artifact_root=root,
        )
        record.status = JobStatus.COMPLETED
        record.execution_slot = record.lease_owner = record.lease_token = (
            record.lease_expires_at
        ) = record.heartbeat_at = None
    with factory.begin() as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
        registry = SymbolModelRegistryService(
            SqlAlchemySymbolModelRegistryRepository(session, artifact_root=root)
        )
        preview = registry.preview(
            game_id=game,
            model_iteration_id=iteration.id,
            action=SymbolModelActivationAction.ACTIVATE,
        )
        registry.activate(
            game_id=game,
            model_iteration_id=iteration.id,
            expected_manifest_checksum_sha256=preview.candidate_manifest_checksum_sha256,
            expected_current_model_iteration_id=None,
            action=SymbolModelActivationAction.ACTIVATE,
            actor="test-owner",
            reason="task1172 test",
            idempotency_key=uuid4(),
        )
