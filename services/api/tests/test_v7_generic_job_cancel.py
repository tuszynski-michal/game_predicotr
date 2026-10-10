from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.jobs import create_jobs_router
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.v7_selection_delivery import V7OutputDecision
from game_predictor_api.storage.job_repository import (
    SqlAlchemyJobRepository,
    job_record_from_domain,
)
from game_predictor_api.storage.models import (
    JobModel,
    SemiAutomaticImageSelectionRunModel,
    SemiAutomaticV7ActivationGateModel,
    V7OutputOperationModel,
)
from test_v7_selection_delivery_api import decision_body, delivery_fixture


@pytest.mark.parametrize("state", ["reserved", "recovery_required"])
def test_generic_cancel_uses_same_ordered_pending_guard(tmp_path, state):
    _selection_client, repository, service, run, manifest = delivery_fixture(tmp_path)
    decision = V7OutputDecision.from_payload(
        {
            **decision_body(run, manifest),
            "expectedTargetChecksumSha256": None,
            "expectedOwnerOperationId": None,
        }
    )
    service.acknowledge_v7_output(run.id, 1, decision)
    run = repository.runs[run.id]
    operation = repository.operations[decision.operation_id]
    operation_record = SimpleNamespace(
        id=operation.operation_id,
        run_id=run.id,
        range_id=operation.range_id,
        request_fingerprint=operation.request_fingerprint,
        request_payload=operation.request_payload,
        context_payload=operation.context_payload,
        decision_generation=0,
        reserved_revision=1,
        state=state,
        receipt=None,
        error_code="IO_RETRY" if state == "recovery_required" else None,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )

    class Session:
        def __init__(self):
            self.job = job_record_from_domain(run.job)
            self.pending = operation_record
            self.locks = []

        def get(self, _model, _id, **_kwargs):
            return self.job

        def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            if statement._for_update_arg is not None:
                self.locks.append(entity.__name__)
            if entity is SemiAutomaticV7ActivationGateModel:
                return SimpleNamespace(
                    pilot_status="blocked",
                    pilot_generation=0,
                    pilot_mode="semi_automatic",
                    pilot_geometry_family_id=None,
                    pilot_source_game_ref=None,
                    pilot_source_policy="exact_sources",
                    pilot_profile_fingerprint=None,
                    pilot_observer_fingerprint=None,
                    pilot_ocr_model_fingerprint=None,
                    pilot_source_bindings=[],
                    pilot_acceptance_receipt_fingerprint=None,
                    pilot_accepted_at=None,
                    pilot_accepted_by=None,
                )
            if entity is JobModel:
                return self.job
            if entity is V7OutputOperationModel:
                return self.pending
            if entity is SemiAutomaticImageSelectionRunModel:
                return run.id if statement._for_update_arg is None else run
            raise AssertionError(entity)

        def flush(self):
            pass

    session = Session()
    job_service = JobService(SqlAlchemyJobRepository(session), object())
    app = FastAPI()

    @app.exception_handler(JobError)
    def conflict(_request, error):
        return JSONResponse(status_code=409, content={"code": error.code})

    app.include_router(create_jobs_router(lambda: job_service))
    client = TestClient(app)
    response = client.post(f"/admin/jobs/{run.job.id}/cancel")
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "V7_OUTPUT_DECISION_PENDING"
    assert session.job.status.value == "created"
    assert session.locks == [
        "SemiAutomaticV7ActivationGateModel",
        "JobModel",
        "SemiAutomaticImageSelectionRunModel",
    ]
    session.pending = None
    response = client.post(f"/admin/jobs/{run.job.id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
