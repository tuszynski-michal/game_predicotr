"""Versioned dispatcher for the shared durable correction job type."""

from collections.abc import Callable

from game_predictor_api.application.grid_correction_apply import APPLY_KIND
from game_predictor_api.application.grid_correction_learning import LEARNING_KIND
from game_predictor_api.domain.jobs import Job, JobType

from ..jobs.runtime import JobExecutionContext, JobHandlerError


class GridCorrectionWorkflowJobHandler:
    def __init__(
        self,
        learning: Callable[[JobExecutionContext, Job], None],
        apply: Callable[[JobExecutionContext, Job], None],
    ):
        self.handlers = {LEARNING_KIND: learning, APPLY_KIND: apply}

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        kind = job.input_payload.get("learning_kind")
        handler = self.handlers.get(str(kind))
        if job.job_type is not JobType.GRID_CORRECTION_LEARNING or handler is None:
            raise JobHandlerError("GRID_LEARNING_INPUT_INVALID", "Unsupported correction workflow.")
        handler(context, job)
