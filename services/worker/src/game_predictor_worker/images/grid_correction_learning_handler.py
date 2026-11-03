"""One durable parent step per claim; waiting never occupies a worker lane."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from game_predictor_api.application.grid_correction_learning import (
    LEARNING_KIND,
    GridCorrectionLearningService,
)
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobType

from ..jobs.runtime import JobExecutionContext, JobHandlerError
from ..training_core.grid_training_admission import PRESETS, RuntimeFacts, evaluate_admission


class GridCorrectionLearningJobHandler:
    def __init__(
        self, service: GridCorrectionLearningService, probe: Callable[[], RuntimeFacts]
    ) -> None:
        self.service, self.probe = service, probe

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if (
            job.job_type is not JobType.GRID_CORRECTION_LEARNING
            or job.input_payload.get("learning_kind") != LEARNING_KIND
        ):
            raise JobHandlerError("GRID_LEARNING_INPUT_INVALID", "Unsupported learning workflow.")
        state: dict[str, Any] = dict(job.checkpoint_payload or {})
        state.setdefault("schema_version", 1)
        context.checkpoint(
            checkpoint_payload=state,
            stage="learning",
            current=job.progress_current,
            total=None,
            success_count=0,
            failure_count=0,
            review_count=0,
        )
        # Probe is read-only and bounded in the same configured trainer interpreter.
        # The training child repeats admission and owns the only persistent GPU budget.
        if "runtimeReadiness" not in state:
            runtime = self.probe()
            preset = PRESETS["grid-corrections-v1"]
            admission = evaluate_admission(
                preset_id=preset.preset_id,
                preset_fingerprint=preset.fingerprint,
                purpose="smoke",
                runtime=runtime,
                lease_state="free",
            )
            if not admission.admitted:
                raise JobHandlerError(
                    admission.reasons[0], "The configured training runtime is not ready."
                )
            state["runtimeReadiness"] = asdict(runtime)
            context.wait_for_dependency(checkpoint_payload=state)
        try:
            state, finished = self.service.advance(context.job)
        except (GridCohortError, GridModelRegistryError) as error:
            raise JobHandlerError(error.code, error.message) from error
        context.checkpoint(
            checkpoint_payload=state,
            stage="completed" if finished else "learning",
            current=job.progress_current + 1,
            total=None,
            success_count=int(finished),
            failure_count=0,
            review_count=0,
        )
        if not finished:
            context.wait_for_dependency(checkpoint_payload=state)
