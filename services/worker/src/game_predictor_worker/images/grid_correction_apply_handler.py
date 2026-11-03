"""One apply unit per lease; comparison children run after the parent releases its lane."""

from typing import Any

from game_predictor_api.application.grid_correction_apply import (
    APPLY_KIND,
    GridCorrectionApplyService,
)
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobType

from ..jobs.runtime import JobExecutionContext, JobHandlerError


class GridCorrectionApplyJobHandler:
    def __init__(self, service: GridCorrectionApplyService) -> None:
        self.service = service

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if (
            job.job_type is not JobType.GRID_CORRECTION_LEARNING
            or job.input_payload.get("learning_kind") != APPLY_KIND
        ):
            raise JobHandlerError("GRID_APPLY_INPUT_INVALID", "Unsupported apply workflow.")
        state: dict[str, Any] = dict(job.checkpoint_payload or {})
        state.setdefault("schema_version", 1)
        context.checkpoint(
            checkpoint_payload=state,
            stage="applying",
            current=job.progress_current,
            total=None,
            success_count=0,
            failure_count=0,
            review_count=0,
        )
        try:
            state, finished = self.service.advance(context.job)
        except (GridCohortError, GridModelRegistryError) as error:
            raise JobHandlerError(error.code, error.message) from error
        context.checkpoint(
            checkpoint_payload=state,
            stage="completed" if finished else "applying",
            current=job.progress_current + 1,
            total=None,
            success_count=sum(step["status"] == "completed" for step in state.get("steps", [])),
            failure_count=0,
            review_count=0,
        )
        if not finished:
            context.wait_for_dependency(checkpoint_payload=state)
