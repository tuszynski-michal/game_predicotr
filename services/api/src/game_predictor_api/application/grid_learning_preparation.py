"""Durable, idempotent admission before expensive correction-data preparation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cohort_asset_retention import acquire_cohort_asset_guard
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.grid_preparation_progress import PREPARATION_WORKER_CAPABILITY
from game_predictor_api.storage.grid_private_learning import assignment_pin, require_learning_pin
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import GameModel, JobModel, WorkerLaneRuntimeModel

if TYPE_CHECKING:
    from .grid_correction_learning import GridCorrectionLearningService


def acquire_learning_game_lock(session: Any, game: UUID) -> None:
    try:
        session.execute(text("SET LOCAL lock_timeout='5s'"))
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"grid-learning-background:{game}"},
        )
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "55P03":
            raise GridCohortError(
                "GRID_LEARNING_BUSY", "The workflow is committing a command; retry shortly."
            ) from error
        raise


def require_no_active_learning(session: Any, game: UUID, excluding: UUID | None = None) -> None:
    from .grid_correction_learning import LEARNING_KIND

    query = select(JobModel.id).where(
        JobModel.game_id == game,
        JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
        JobModel.input_payload["learning_kind"].as_string() == LEARNING_KIND,
        JobModel.status.in_([JobStatus.CREATED, JobStatus.PROCESSING]),
    )
    if excluding is not None:
        query = query.where(JobModel.id != excluding)
    if session.scalar(query.limit(1)) is not None:
        raise GridCohortError("GRID_LEARNING_ALREADY_ACTIVE", "A learning job is already active.")


def require_preparation_worker(session: Any) -> None:
    worker = session.get(WorkerLaneRuntimeModel, WorkerLaneName.GENERAL)
    if worker is None or PREPARATION_WORKER_CAPABILITY not in worker.worker_version:
        raise GridCohortError(
            "GRID_LEARNING_WORKER_UPDATE_REQUIRED",
            "Restart the general worker with background preparation support.",
        )


def enqueue(
    service: GridCorrectionLearningService, game: UUID, command: dict[str, Any], actor: str
) -> dict[str, Any]:
    from .grid_correction_learning import LEARNING_KIND

    key = UUID(command["idempotencyKey"])
    with game_storage_scope(game), service.session_factory() as session, session.begin():
        SqlAlchemyGridTrainingCohortRepository(session, service.artifact_root).bind(
            game, write=True
        )
        acquire_learning_game_lock(session, game)
        existing = service._by_key(session, game, key)
        if existing is not None:
            if existing.input_payload["command"] != command:
                raise GridCohortError(
                    "GRID_LEARNING_IDEMPOTENCY_CONFLICT", "The key belongs to another command."
                )
            return service.view(existing)
        require_no_active_learning(session, game)
        catalogue = SqlAlchemyGridModelRegistryRepository(session)
        catalogue.lock()
        pin = assignment_pin(catalogue, game)
        if pin is not None and command.get("learningScope") != "private_game":
            raise GridCohortError(
                "GRID_LEARNING_PRIVATE_SCOPE_REQUIRED", "Choose private learning for this game."
            )
        if pin is None and command.get("learningScope") == "private_game":
            raise GridCohortError("GRID_LEARNING_SCOPE_CHANGED", "The game is shared.")
        if pin and (command.get("historicalCohorts") or command.get("exclusions")):
            raise GridCohortError(
                "GRID_LEARNING_PRIVATE_COHORTS_INVALID",
                "Private learning uses only this game's data.",
            )
        require_preparation_worker(session)
        default = None if pin else catalogue.default()
        if pin is not None:
            base_id = pin["baseVersionId"]
        elif default is not None:
            base_id = str(default.version_id)
        else:
            raise GridCohortError(
                "GRID_LEARNING_DEFAULT_REQUIRED", "Choose a global default first."
            )
        preview = {
            **(
                {
                    "learningScope": "private_game",
                    "gameName": session.scalar(select(GameModel.name).where(GameModel.id == game)),
                    **pin,
                }
                if pin
                else {}
            ),
            "baseVersionId": base_id,
            "defaultRevision": default.revision if default else None,
            "previewSha256": descriptor_sha256(command),
            "requiredGameIds": [str(game)],
            "exclusions": command.get("exclusions", []),
        }
        payload = {
            "schema_version": 1,
            "learning_kind": LEARNING_KIND,
            "idempotency_key": str(key),
            "command": command,
            "preview": preview,
            "actor": actor,
            "backgroundPreparation": True,
            **({"pins": {"privateLearning": pin}} if pin else {}),
        }
        job = create_job(JobType.GRID_CORRECTION_LEARNING, game_id=game, input_payload=payload)
        job = replace(job, stage="preparing_data")
        return service.view(SqlAlchemyJobRepository(session).add_job(job))


def load_prepared(service: GridCorrectionLearningService, job: Job) -> dict[str, Any] | None:
    artifact = (job.checkpoint_payload or {}).get("preparedArtifact")
    if not isinstance(artifact, dict):
        return None
    return GridCohortArtifactStore(service.artifact_root).read_json(
        artifact["path"], artifact["sha256"]
    )


@contextmanager
def prepare(service: GridCorrectionLearningService, job: Job) -> Iterator[dict[str, Any]]:
    assert job.game_id is not None
    command: Any = job.input_payload["command"]
    options = {
        k: v
        for k, v in command.items()
        if k not in {"idempotencyKey", "previewSha256", "prepareInBackground", "preparationOnly"}
    }
    preview, pins = service._preview(job.game_id, options)
    expected_pin = job.input_payload.get("pins", {}).get("privateLearning")
    if pins.get("privateLearning") != expected_pin:
        raise GridCohortError(
            "GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED",
            "The private assignment changed during preparation.",
        )
    if not preview["canStart"]:
        raise GridCohortError(preview["blockers"][0], "Correction data preparation is blocked.")
    initial: Any = job.input_payload["preview"]
    if (preview["baseVersionId"], preview["defaultRevision"]) != (
        initial["baseVersionId"],
        initial["defaultRevision"],
    ):
        raise GridCohortError(
            "GRID_LEARNING_DEFAULT_CHANGED", "The default changed during preparation."
        )
    # Automatic v4 choices are part of the prepared command, not an implicit legacy fallback.
    options.update(
        importJobIds=preview["importJobIds"],
        **(
            {"validationAssignments": preview["validationAssignments"]}
            if preview.get("policyVersion")
            else {}
        ),
    )
    # Keep GC excluded through the caller's durable preparedArtifact checkpoint,
    # including reuse of an identical file whose mtime is already old.
    with game_storage_scope(job.game_id), service.session_factory() as session, session.begin():
        if expected_pin:
            catalogue = SqlAlchemyGridModelRegistryRepository(session)
            catalogue.lock()
            require_learning_pin(catalogue, job.game_id, expected_pin)
        acquire_cohort_asset_guard(session, job.game_id, job.id)
        yield GridCohortArtifactStore(service.artifact_root).publish_json(
            job.game_id, job.id, {"preview": preview, "pins": pins, "options": options}
        )


def readiness(service: GridCorrectionLearningService, game: UUID) -> dict[str, Any]:
    """Navigation/admission metadata only; no implicit preparation on page load."""
    from game_predictor_worker.training_core.grid_training_admission import PRESETS, WORKER_CHECKS

    preset = PRESETS["grid-corrections-v1"]
    with game_storage_scope(game), service.session_factory() as session:
        SqlAlchemyGridTrainingCohortRepository(session, service.artifact_root).bind(game)
        registry = SqlAlchemyGridModelRegistryRepository(session)
        private = registry.game_grid_model_private(game)
        default = None if private else registry.default()
        blockers = [] if private or default else ["GRID_LEARNING_DEFAULT_REQUIRED"]
        pin = None
        if private:
            try:
                pin = assignment_pin(registry, game)
            except GridCohortError as error:
                blockers.append(error.code)
        try:
            require_preparation_worker(session)
        except GridCohortError as error:
            blockers.append(error.code)
        view = {
            "trainingMode": "grid-only",
            "preparationRequired": True,
            "gameId": str(game),
            "baseVersionId": str(default.version_id) if default else None,
            "baseManifestSha256": None,
            "defaultRevision": default.revision if default else None,
            "importJobIds": [],
            "roleCounts": [],
            "dataAvailability": None,
            "bufferPhotos": 0,
            "priorScopeDocumented": False,
            "priorGameIds": [],
            "historicalCohorts": [],
            "exclusions": [],
            "requiredGameIds": [str(game)],
            "presetId": preset.preset_id,
            "presetFingerprint": preset.fingerprint,
            "cost": None,
            "blockers": blockers,
            "pendingWorkerChecks": list(WORKER_CHECKS),
            "canStart": False,
            "evidenceLevel": "photo-only",
            "limitations": ["Correction data has not been prepared for this selection."],
        }
        if private:
            view.update(
                learningScope="private_game",
                gameName=session.scalar(select(GameModel.name).where(GameModel.id == game)),
            )
            if pin:
                view.update(pin)
        return {**view, "previewSha256": descriptor_sha256(view)}
