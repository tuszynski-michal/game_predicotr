"""One durable parent step per claim; waiting never occupies a worker lane."""

from collections.abc import Callable
from dataclasses import asdict
from time import monotonic
from typing import Any

from game_predictor_api.application.grid_correction_learning import (
    LEARNING_KIND,
    GridCorrectionLearningService,
)
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.grid_preparation_progress import preparation_progress

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
        background = job.input_payload.get("backgroundPreparation") is True
        context.checkpoint(
            checkpoint_payload=state,
            stage="preparing_data"
            if background and not state.get("preparedArtifact")
            else "learning",
            current=job.progress_current,
            total=None,
            success_count=0,
            failure_count=0,
            review_count=0,
        )
        # Probe is read-only and bounded in the same configured trainer interpreter.
        # The training child repeats admission and owns the only persistent GPU budget.
        command: Any = job.input_payload.get("command") or {}
        training_admitted = not command.get("preparationOnly") or state.get("trainingAuthorized")
        if "runtimeReadiness" not in state and (
            not background or (state.get("preparedArtifact") and training_admitted)
        ):
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
        last_saved = 0.0

        def progress(stage: str, current: int, total: int | None) -> None:
            nonlocal last_saved
            now = monotonic()
            if now - last_saved < 5 and state.get("preparation", {}).get("stage") == stage:
                return
            last_saved = now
            state["preparation"] = {
                "stage": stage,
                "current": current,
                "total": total,
                "lastProgressAt": context.now().isoformat(),
            }
            context.checkpoint(
                checkpoint_payload=state,
                stage=stage,
                current=context.job.progress_current + 1,
                total=None,
                success_count=0,
                failure_count=0,
                review_count=0,
            )

        try:
            if background and not state.get("preparedArtifact"):
                from game_predictor_api.application.grid_learning_preparation import prepare
                from game_predictor_api.storage.grid_training_cohort_artifacts import (
                    GridCohortArtifactStore,
                )

                with preparation_progress(progress):
                    artifact = prepare(self.service, context.job)
                prepared = GridCohortArtifactStore(self.service.artifact_root).read_json(
                    artifact["path"], artifact["sha256"]
                )
                state["preparedArtifact"] = artifact
                state["preparedSummary"] = {
                    k: v for k, v in prepared["preview"].items() if k != "validationComponents"
                }
                completed_total = state.get("preparation", {}).get("total")
                state["preparation"] = {
                    "stage": "data_prepared",
                    "current": completed_total or 0,
                    "total": completed_total,
                    "lastProgressAt": context.now().isoformat(),
                }
                context.checkpoint(
                    checkpoint_payload=state,
                    stage="data_prepared",
                    current=context.job.progress_current + 1,
                    total=None,
                    success_count=0,
                    failure_count=0,
                    review_count=0,
                )
                command = job.input_payload["command"]
                if command.get("preparationOnly"):
                    context.wait_for_review()
                context.wait_for_dependency(checkpoint_payload=state)
            command = job.input_payload.get("command") or {}
            if (
                background
                and command.get("preparationOnly")
                and not state.get("trainingAuthorized")
            ):
                context.wait_for_review()
            if background:
                with preparation_progress(progress):
                    state, finished = self.service.advance(context.job)
            else:
                state, finished = self.service.advance(context.job)
        except (GridCohortError, GridModelRegistryError) as error:
            raise JobHandlerError(error.code, error.message) from error
        context.checkpoint(
            checkpoint_payload=state,
            stage="completed" if finished else "learning",
            current=context.job.progress_current + 1,
            total=None,
            success_count=int(finished),
            failure_count=0,
            review_count=0,
        )
        if not finished:
            context.wait_for_dependency(checkpoint_payload=state)
