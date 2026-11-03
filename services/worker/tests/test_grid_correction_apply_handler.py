"""Apply has no GPU probe; dispatcher and checkpoints preserve the durable parent identity."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.application.grid_correction_apply import APPLY_KIND
from game_predictor_api.application.grid_correction_learning import LEARNING_KIND
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import (
    JobStatus,
    JobType,
    checkpoint_job,
    create_job,
    defer_job_for_dependency,
    fail_job,
    requeue_job,
    start_job,
)
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
            success_count=0,
            failure_count=0,
            review_count=0,
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


class CheckedContext:
    """Use the production monotonicity and lease checks, unlike the display fake."""

    def __init__(self, job):
        self.job = job

    def checkpoint(self, **values):
        self.job = checkpoint_job(self.job, lease_token=self.job.lease_token, **values)

    def wait_for_dependency(self, *, checkpoint_payload):
        assert checkpoint_payload == self.job.checkpoint_payload
        self.job = defer_job_for_dependency(
            self.job, lease_token=self.job.lease_token, checkpoint_payload=checkpoint_payload
        )
        raise Released


def processing_job(state, *, successes=0, failures=0, reviews=0):
    job = create_job(
        JobType.GRID_CORRECTION_LEARNING,
        game_id=uuid4(),
        input_payload={"schema_version": 1, "learning_kind": APPLY_KIND},
    )
    return claim(
        replace(
            job,
            checkpoint_payload=state,
            success_count=successes,
            failure_count=failures,
            review_count=reviews,
        )
    )


def claim(job):
    return start_job(
        job,
        worker_version="test1152",
        worker_id="fresh-handler",
        lease_token=uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_three_steps_keep_counters_across_fresh_handlers_and_restored_checkpoints():
    state = {
        "schema_version": 1,
        "steps": [
            {"kind": kind, "status": "pending"} for kind in ("publish", "set_default", "activate")
        ],
    }
    job = processing_job(state)
    original_id = job.id

    def advance(current):
        saved = json.loads(json.dumps(current.checkpoint_payload))
        step = next(step for step in saved["steps"] if step["status"] == "pending")
        step.update(status="completed", receipt={"identity": step["kind"]})
        return saved, all(step["status"] == "completed" for step in saved["steps"])

    for completed in range(1, 4):
        if completed == 2:
            running = claim(job)
            failed = fail_job(
                running,
                lease_token=running.lease_token,
                error_code="TEST_RESTART",
                error_message="Simulated worker failure",
            )
            job = requeue_job(failed)
            assert job.success_count == 1
        context = CheckedContext(claim(job) if job.status is JobStatus.CREATED else job)
        handler = GridCorrectionApplyJobHandler(SimpleNamespace(advance=advance))
        if completed < 3:
            with pytest.raises(Released):
                handler(context, context.job)
        else:
            handler(context, context.job)
        job = replace(
            context.job, checkpoint_payload=json.loads(json.dumps(context.job.checkpoint_payload))
        )
        assert job.id == original_id
        assert job.progress_current == completed
        assert job.success_count == completed
        assert [
            step["receipt"]["identity"] for step in job.checkpoint_payload["steps"][:completed]
        ] == ["publish", "set_default", "activate"][:completed]
    assert job.stage == "completed"


@pytest.mark.parametrize("failures,reviews", [(0, 0), (2, 3)])
@pytest.mark.parametrize("comparison_wait", [False, True])
def test_waiting_lease_preserves_existing_counters_and_receipts(failures, reviews, comparison_wait):
    state = {
        "schema_version": 1,
        "steps": [{"kind": "publish", "status": "completed", "receipt": {"identity": "original"}}],
    }
    if comparison_wait:
        state["steps"].append({"kind": "comparison", "status": "waiting"})
        state["waitingForJobId"] = str(uuid4())
    job = processing_job(state, successes=1, failures=failures, reviews=reviews)
    for _ in range(2):
        context = CheckedContext(claim(job) if job.status is JobStatus.CREATED else job)
        with pytest.raises(Released):
            GridCorrectionApplyJobHandler(
                SimpleNamespace(advance=lambda current: (current.checkpoint_payload, False))
            )(context, context.job)
        job = context.job
        assert (job.success_count, job.failure_count, job.review_count) == (1, failures, reviews)
        assert job.checkpoint_payload == state
