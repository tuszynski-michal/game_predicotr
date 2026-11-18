"""Parent checkpoints release the lane; runtime readiness never consumes a training budget."""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from game_predictor_api.application.grid_correction_learning import LEARNING_KIND
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.grid_preparation_progress import report_preparation
from game_predictor_worker.images.grid_correction_learning_handler import (
    GridCorrectionLearningJobHandler,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.training_core.grid_training_admission import RuntimeFacts


class Released(Exception):
    pass


class Context:
    def __init__(self, state=None):
        self.job = SimpleNamespace(
            job_type=JobType.GRID_CORRECTION_LEARNING,
            input_payload={"learning_kind": LEARNING_KIND},
            checkpoint_payload=state,
            progress_current=0,
        )
        self.stages = []

    def now(self):
        return datetime(2026, 11, 16, tzinfo=UTC)

    def checkpoint(self, **values):
        self.job.checkpoint_payload = values["checkpoint_payload"]
        self.stages.append(values["stage"])

    def wait_for_dependency(self, *, checkpoint_payload):
        self.job.checkpoint_payload = checkpoint_payload
        raise Released


def test_runtime_probe_is_persisted_then_restart_runs_one_step_and_releases():
    facts = RuntimeFacts(
        True,
        "2.12.1+cu130",
        "0.27.1+cu130",
        "13.0",
        "NVIDIA GeForce RTX 4050 Laptop GPU",
        6_439_305_216,
        6_200_000_000,
    )
    calls = []
    service = SimpleNamespace(
        advance=lambda job: (
            calls.append(job) or {**job.checkpoint_payload, "waitingForJobId": "child"},
            False,
        )
    )
    first = Context()
    handler = GridCorrectionLearningJobHandler(service, lambda: facts)
    with pytest.raises(Released):
        handler(first, first.job)
    assert not calls
    assert first.job.checkpoint_payload["schema_version"] == 1
    assert first.job.checkpoint_payload["runtimeReadiness"]["cuda_available"]
    restarted = Context(dict(first.job.checkpoint_payload))

    def no_probe():
        raise AssertionError("The durable readiness fact must be reused.")

    with pytest.raises(Released):
        GridCorrectionLearningJobHandler(service, no_probe)(restarted, restarted.job)
    assert len(calls) == 1
    assert restarted.job.checkpoint_payload["waitingForJobId"] == "child"


def test_failed_runtime_does_not_create_a_cohort_or_child():
    facts = RuntimeFacts(False, "2.12.1+cpu", "0.27.1", None, None, 0, 0)
    service = SimpleNamespace(advance=lambda job: pytest.fail("No child is admitted."))
    context = Context()
    with pytest.raises(JobHandlerError):
        GridCorrectionLearningJobHandler(service, lambda: facts)(context, context.job)


def test_background_step_keeps_latest_progress_instead_of_claim_snapshot():
    context = Context(
        {
            "preparedArtifact": {"path": "prepared.json"},
            "runtimeReadiness": {},
            "preparation": {"stage": "data_prepared", "current": 9, "lastProgressAt": "old"},
        }
    )
    context.job.input_payload["backgroundPreparation"] = True

    def advance(job):
        claimed = dict(job.checkpoint_payload)
        report_preparation("cohort_capture", 2, 10)
        return {**claimed, "cohortId": "same-cohort"}, False

    with pytest.raises(Released):
        GridCorrectionLearningJobHandler(
            SimpleNamespace(advance=advance), lambda: pytest.fail("No probe")
        )(context, context.job)
    saved = context.job.checkpoint_payload
    assert saved["cohortId"] == "same-cohort"
    assert saved["preparation"] == {
        "stage": "cohort_capture",
        "current": 2,
        "total": 10,
        "lastProgressAt": context.now().isoformat(),
    }


def test_retried_preparation_does_not_inherit_old_stall_clock(monkeypatch):
    from game_predictor_api.application import grid_learning_preparation

    context = Context(
        {
            "preparation": {
                "stage": "geometry_evidence",
                "current": 3,
                "lastProgressAt": "2000-01-01T00:00:00+00:00",
            }
        }
    )
    context.job.input_payload["backgroundPreparation"] = True

    @contextmanager
    def rejected(service, job):
        assert job.checkpoint_payload["preparation"] == {
            "stage": "preparing_data",
            "current": 0,
            "total": None,
        }
        raise GridCohortError("GRID_LEARNING_DEFAULT_CHANGED", "Changed default.")
        yield  # pragma: no cover - defines the context-manager protocol

    monkeypatch.setattr(grid_learning_preparation, "prepare", rejected)
    with pytest.raises(JobHandlerError, match="Changed default"):
        GridCorrectionLearningJobHandler(SimpleNamespace(), lambda: pytest.fail("No GPU probe"))(
            context, context.job
        )
