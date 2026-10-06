from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.symbols import lab_candidate_import
from test_job_runtime import MemoryWorkerJobStore, MutableClock


@pytest.mark.parametrize("resume", [False, True])
def test_lab_import_checkpoints_pass_real_worker_contract_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, resume: bool
) -> None:
    publications = []

    class Sessions:
        @contextmanager
        def begin(self):
            yield object()

    class Repository:
        def __init__(self, session):
            pass

        def publish(self, **arguments):
            publications.append(arguments)

    monkeypatch.setattr(
        lab_candidate_import, "SqlAlchemyLabSymbolCandidateImportRepository", Repository
    )
    clock = MutableClock()
    job = create_job(
        job_type=JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={"schema_version": 1, "validation_kind": "symbol_model_lab_import"},
        created_at=clock(),
    )
    if resume:
        job = replace(
            job,
            checkpoint_payload={"schema_version": 1, "workflow": "symbol_model_lab_import"},
            stage="lab_candidate_validation",
        )
    store = MemoryWorkerJobStore([job])
    worker = LocalJobWorker(
        store,
        handlers={
            JobType.VALIDATE: lab_candidate_import.LabSymbolCandidateImportHandler(
                Sessions(), tmp_path
            )
        },
        worker_id="lab-import-regression",
        worker_version="test",
        clock=clock,
    )

    assert worker.run_once() is JobExecutionResult.COMPLETED
    completed = store.jobs[job.id]
    assert completed.status is JobStatus.COMPLETED
    assert completed.checkpoint_payload["schema_version"] == 1
    assert completed.checkpoint_payload["candidateReady"] is True
    assert completed.stage == "lab_candidate_ready"
    assert len(publications) == 2
    assert publications[0]["status"] == "evaluating"
    assert "status" not in publications[1]
    assert {row["job_id"] for row in publications} == {job.id}
