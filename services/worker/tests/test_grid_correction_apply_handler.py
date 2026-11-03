"""Apply has no GPU probe; dispatcher and checkpoints preserve the durable parent identity."""

from types import SimpleNamespace

import pytest
from game_predictor_api.application.grid_correction_apply import APPLY_KIND
from game_predictor_api.application.grid_correction_learning import LEARNING_KIND
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import JobType
from game_predictor_worker.images.grid_correction_apply_handler import GridCorrectionApplyJobHandler
from game_predictor_worker.images.grid_correction_workflow_handler import (
    GridCorrectionWorkflowJobHandler,
)
from game_predictor_worker.jobs.runtime import JobHandlerError


class Released(Exception):
    pass


class Context:
    def __init__(self, state=None):
        self.job = SimpleNamespace(
            job_type=JobType.GRID_CORRECTION_LEARNING,
            input_payload={"learning_kind": APPLY_KIND},
            checkpoint_payload=state,
            progress_current=0,
        )
        self.stages = []

    def checkpoint(self, **values):
        self.job.checkpoint_payload = values["checkpoint_payload"]
        self.stages.append(values["stage"])

    def wait_for_dependency(self, *, checkpoint_payload):
        self.job.checkpoint_payload = checkpoint_payload
        raise Released


def test_wait_and_new_handler_resume_same_parent_state_without_probe():
    context = Context(
        {"steps": [{"kind": "publish", "status": "completed", "receipt": {"revision": 1}}]}
    )

    def waiting(job):
        return {**job.checkpoint_payload, "waitingForJobId": "original-comparison"}, False

    with pytest.raises(Released):
        GridCorrectionApplyJobHandler(SimpleNamespace(advance=waiting))(context, context.job)
    saved = context.job.checkpoint_payload
    assert saved["steps"][0]["receipt"] == {"revision": 1}
    assert saved["waitingForJobId"] == "original-comparison"
    restarted = Context(saved)
    GridCorrectionApplyJobHandler(
        SimpleNamespace(advance=lambda job: (job.checkpoint_payload, True))
    )(restarted, restarted.job)
    assert restarted.stages == ["applying", "completed"]


def test_typed_service_failure_reaches_job_runtime_without_rollback():
    def fail(job):
        raise GridCohortError("GRID_APPLY_DEFAULT_CHANGED", "Changed")

    context = Context({"steps": [{"kind": "publish", "status": "completed"}]})
    with pytest.raises(JobHandlerError) as error:
        GridCorrectionApplyJobHandler(SimpleNamespace(advance=fail))(context, context.job)
    assert error.value.code == "GRID_APPLY_DEFAULT_CHANGED"
    assert context.job.checkpoint_payload["steps"][0]["status"] == "completed"


def test_dispatcher_uses_closed_kind_and_never_passes_apply_to_learning():
    calls = []
    handler = GridCorrectionWorkflowJobHandler(
        lambda context, job: calls.append("learning"), lambda context, job: calls.append("apply")
    )
    context = Context()
    handler(context, context.job)
    context.job.input_payload["learning_kind"] = LEARNING_KIND
    handler(context, context.job)
    context.job.input_payload["learning_kind"] = "unsupported"
    with pytest.raises(JobHandlerError):
        handler(context, context.job)
    assert calls == ["apply", "learning"]
