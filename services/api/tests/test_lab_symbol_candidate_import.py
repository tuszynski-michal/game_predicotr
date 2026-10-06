from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.lab_symbol_candidate_import import (
    LabSymbolCandidateImportService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain import lab_symbol_candidate as lab
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobStatus,
    JobType,
    create_job,
    recover_expired_job,
    requeue_job,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from game_predictor_api.storage.job_repository import (
    SqlAlchemyJobRepository,
    job_record_from_domain,
    synchronize_lab_import_iteration,
)
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
    SqlAlchemyLabSymbolCandidateImportRepository,
)
from game_predictor_api.storage.lab_symbol_candidate_validation import require_iteration_candidate
from game_predictor_api.storage.models import (
    GameModel,
    GameSymbolModelActivationModel,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.imports.validation_dispatch import ValidationJobDispatchHandler
from game_predictor_worker.jobs.store import _synchronize_bulk_operation_recovery


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    model = b"qualified-export-registry-fixture"
    payload = {"classes": list(lab.MUMIE_CLASS_LABELS), "eligible": True}
    sha = lab.digest(payload)
    monkeypatch.setattr(lab, "MUMIE_ELIGIBILITY_ID", sha)
    monkeypatch.setattr(lab, "MUMIE_R2_ONNX_SHA256", hashlib.sha256(model).hexdigest())
    return lab.prepare_mumie_candidate(
        tmp_path,
        game_id=uuid4(),
        onnx_content=model,
        eligibility_content=lab.canonical({"payload": payload, "sha256": sha}),
    )


class Session:
    def __init__(self, responses, codes=lab.MUMIE_CLASS_CODES):
        self.responses = list(responses)
        self.codes = tuple(sorted(codes))
        self.added = []
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.responses.pop(0)

    def scalars(self, _statement):
        return self.codes

    def get(self, _model, _id):
        return self.added[0] if self.added else GameModel(id=_id)

    def add(self, record):
        self.added.append(record)

    def flush(self):
        pass


def _start(tmp_path, candidate, key=None):
    session = Session([GameModel(id=candidate.game_id), None, None, None, 0])
    value = SqlAlchemyLabSymbolCandidateImportRepository(session).start(
        game_id=candidate.game_id,
        fingerprint=candidate.fingerprint,
        idempotency_key=key or uuid4(),
        artifact_root=tmp_path,
    )
    return session, value


def test_import_is_validate_without_cohort_and_receipt_survives_drift(tmp_path, candidate):
    key = uuid4()
    session, (iteration, job, created) = _start(tmp_path, candidate, key)
    assert created and iteration.origin == "lab_import" and iteration.cohort_id is None
    assert job.job_type.value == "validate"
    assert iteration.last_completed_epoch == 0
    record = session.added[-1]
    receipt = job_record_from_domain(job)
    (tmp_path / candidate.manifest_relative_path).write_bytes(b"changed after lost response")
    replay = Session([GameModel(id=candidate.game_id), receipt, record], codes=())
    second = SqlAlchemyLabSymbolCandidateImportRepository(replay).start(
        game_id=candidate.game_id,
        fingerprint=candidate.fingerprint,
        idempotency_key=key,
        artifact_root=tmp_path,
    )
    assert second[0].id == iteration.id and second[1].id == job.id and not second[2]
    conflict = Session([GameModel(id=candidate.game_id), receipt])
    with pytest.raises(JobConflictError, match="another import"):
        SqlAlchemyLabSymbolCandidateImportRepository(conflict).start(
            game_id=candidate.game_id,
            fingerprint="a" * 64,
            idempotency_key=key,
            artifact_root=tmp_path,
        )


def test_catalog_and_game_mismatch_fail_before_registration(tmp_path, candidate):
    wrong = Session([GameModel(id=candidate.game_id), None], codes=("SIEDEM",))
    with pytest.raises(JobConflictError) as error:
        SqlAlchemyLabSymbolCandidateImportRepository(wrong).start(
            game_id=candidate.game_id,
            fingerprint=candidate.fingerprint,
            idempotency_key=uuid4(),
            artifact_root=tmp_path,
        )
    assert error.value.code == "SYMBOL_MODEL_CLASS_CATALOG_MISMATCH"
    assert not wrong.added
    service = LabSymbolCandidateImportService(
        SqlAlchemyLabSymbolCandidateImportRepository(Session([])), tmp_path
    )
    assert service.inventory(uuid4()) == ()


def test_ready_publication_is_fenced_and_runtime_uses_lab_contract(tmp_path, candidate):
    initial, (_, job, _) = _start(tmp_path, candidate)
    receipt = job_record_from_domain(job)
    receipt.status = JobStatus.PROCESSING
    receipt.lease_owner = "worker"
    receipt.lease_token = uuid4()
    receipt.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    record = initial.added[-1]
    publishing = Session([candidate.game_id, receipt, record])
    arguments = dict(
        game_id=candidate.game_id,
        job_id=job.id,
        lease_owner="worker",
        lease_token=receipt.lease_token,
        artifact_root=tmp_path,
    )
    SqlAlchemyLabSymbolCandidateImportRepository(publishing).publish(**arguments)
    assert record.status == "candidate_ready"
    assert require_iteration_candidate(publishing, tmp_path, record) == candidate
    receipt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(JobConflictError) as error:
        SqlAlchemyLabSymbolCandidateImportRepository(Session([candidate.game_id, receipt])).publish(
            **arguments
        )
    assert error.value.code == "LAB_IMPORT_LEASE_LOST"
    activation = GameSymbolModelActivationModel(model_iteration_id=record.id, action="activate")
    resolving = Session([activation])
    resolving.added = [record]
    snapshot = SqlAlchemySymbolModelSnapshotResolver(resolving, artifact_root=tmp_path).resolve(
        game_id=candidate.game_id,
    )
    assert snapshot.model_version == "lab-rgb-symbol-onnx-v1"
    assert snapshot.crop_size == 96 and snapshot.input_size == 64
    assert snapshot.crop_padding_fraction == 0.0
    (tmp_path / candidate.manifest_relative_path).parent.joinpath("origin.json").write_bytes(b"{}")
    with pytest.raises(JobConflictError):
        require_iteration_candidate(resolving, tmp_path, record)


def test_deactivation_never_falls_back_to_bootstrap(tmp_path):
    activation = GameSymbolModelActivationModel(model_iteration_id=None, action="deactivate")
    resolver = SqlAlchemySymbolModelSnapshotResolver(Session([activation]), artifact_root=tmp_path)
    with pytest.raises(JobConflictError) as error:
        resolver.resolve(game_id=uuid4())
    assert error.value.code == "SYMBOL_MODEL_ACTIVATION_REQUIRED"


def test_cancel_and_explicit_retry_project_lab_iteration_only(tmp_path, candidate, monkeypatch):
    initial, (_, job, _) = _start(tmp_path, candidate)
    record = initial.added[-1]
    monkeypatch.setattr(GameStorageRouter, "bind", lambda *args, **kwargs: None)
    cancelled = replace(job, status=JobStatus.CANCELLED)
    synchronize_lab_import_iteration(Session([record]), cancelled)
    assert record.status == "cancelled"
    receipt = job_record_from_domain(cancelled)
    persisted = Session([record])
    persisted.added = [receipt]
    resumed = requeue_job(cancelled)
    SqlAlchemyJobRepository(persisted).save_job(resumed)
    assert record.status == "created"
    ordinary = replace(job, input_payload={"schema_version": 1})
    untouched = Session([])
    synchronize_lab_import_iteration(untouched, ordinary)
    assert not untouched.statements


def test_worker_crash_cancel_and_expired_lease_projects_cancelled(tmp_path, candidate, monkeypatch):
    initial, (_, job, _) = _start(tmp_path, candidate)
    iteration = initial.added[-1]
    iteration.status = "evaluating"
    monkeypatch.setattr(GameStorageRouter, "bind", lambda *args, **kwargs: None)
    now = datetime.now(UTC)
    crashed = replace(
        job,
        status=JobStatus.PROCESSING,
        lease_owner="crashed-worker",
        lease_token=uuid4(),
        lease_expires_at=now - timedelta(seconds=1),
        heartbeat_at=now - timedelta(seconds=30),
        cancel_requested_at=now - timedelta(seconds=2),
    )
    recovered = recover_expired_job(crashed, recovered_at=now)
    assert recovered.status is JobStatus.CANCELLED
    _synchronize_bulk_operation_recovery(Session([iteration]), recovered)
    assert iteration.status == "cancelled"


@pytest.mark.parametrize(
    "kind",
    [
        "layout_import",
        "page_geometry_preflight",
        "image_geometry_guard_report_reconstruction",
        "grid_geometry_shadow_v3",
        "symbol_model_lab_import",
    ],
)
def test_lab_import_dispatch_preserves_existing_validation_consumers(kind):
    calls = []
    kinds = [
        "layout_import",
        "page_geometry_preflight",
        "image_geometry_guard_report_reconstruction",
        "grid_geometry_shadow_v3",
        "symbol_model_lab_import",
    ]
    handlers = [lambda context, job, name=name: calls.append(name) for name in kinds]
    dispatch = ValidationJobDispatchHandler(*handlers)
    dispatch(
        object(),
        create_job(
            JobType.VALIDATE,
            game_id=uuid4(),
            input_payload={
                "schema_version": 1,
                "validation_kind": kind,
            },
        ),
    )
    assert calls == [kind]


@pytest.mark.parametrize("invalid", ["owner", "token", "cancel", "status", "kind", "game"])
def test_publication_rejects_stale_lease_or_wrong_job(tmp_path, candidate, invalid):
    initial, (_, job, _) = _start(tmp_path, candidate)
    receipt = job_record_from_domain(job)
    receipt.status = JobStatus.PROCESSING
    receipt.lease_owner = "worker"
    receipt.lease_token = uuid4()
    token = receipt.lease_token
    receipt.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    if invalid == "owner":
        receipt.lease_owner = "other"
    if invalid == "token":
        receipt.lease_token = uuid4()
    if invalid == "cancel":
        receipt.cancel_requested_at = datetime.now(UTC)
    if invalid == "status":
        receipt.status = JobStatus.FAILED
    if invalid == "kind":
        receipt.input_payload = {"validation_kind": "layout_import"}
    session = Session(
        [None if invalid == "game" else candidate.game_id, receipt, initial.added[-1]]
    )
    with pytest.raises((JobConflictError, ValueError)):
        SqlAlchemyLabSymbolCandidateImportRepository(session).publish(
            game_id=candidate.game_id,
            job_id=job.id,
            lease_owner="worker",
            lease_token=token,
            artifact_root=tmp_path,
        )


def test_inventory_preview_import_http_pion(tmp_path, candidate):
    class Repository:
        def require_game(self, _game):
            pass

        def require_catalog(self, value):
            assert value.game_id == candidate.game_id

        def start(self, **kwargs):
            if not hasattr(self, "receipt"):
                self.receipt = _start(tmp_path, candidate, kwargs["idempotency_key"])[1]
                return self.receipt
            return self.receipt[0], self.receipt[1], False

    repository = Repository()
    settings = ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": "postgresql+psycopg://unused:unused@localhost:5432/unused",
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
        }
    )
    app = create_app(
        settings,
        lab_symbol_candidate_import_service_dependency=lambda: LabSymbolCandidateImportService(
            repository, tmp_path
        ),
    )
    url = f"/api/v1/admin/games/{candidate.game_id}/symbol-model-iterations"
    body = {"candidateFingerprint": candidate.fingerprint, "idempotencyKey": str(uuid4())}
    with TestClient(app) as client:
        inventory = client.get(url + "/imports/candidates")
        preview = client.get(url + f"/imports/{candidate.fingerprint}/preview")
        first = client.post(url + "/imports", json=body)
        second = client.post(url + "/imports", json=body)
        invalid = client.post(url + "/imports", json={**body, "systemPath": "C:/private"})
    assert (
        inventory.status_code
        == preview.status_code
        == first.status_code
        == second.status_code
        == 200
    )
    assert preview.json()["summary"]["populationAccuracy"] is None
    assert preview.json()["summary"]["humanSelectedControls"] == {"correct": 34, "total": 34}
    assert first.json()["iteration"]["origin"] == "lab_import"
    assert first.json()["iteration"]["epochCount"] == 0
    assert first.json()["iteration"]["cohortId"] is None
    assert first.json()["job"]["inputPayload"]["validationKind"] == "symbol_model_lab_import"
    assert first.json()["iteration"]["id"] == second.json()["iteration"]["id"]
    assert invalid.status_code == 422
