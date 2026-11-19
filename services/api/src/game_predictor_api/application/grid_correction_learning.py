"""Persistent corrections workflow. Reads never advance it; workers perform one step.

Every child command has a deterministic key. A lost response or a restarted parent
therefore adopts the same cohort/run/evaluation, including the original GPU budget.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.grid_correction_evaluation import (
    PHOTO_ONLY_LIMITATIONS,
    require_scope,
)
from game_predictor_api.domain.grid_correction_policy import (
    CORRECTION_PRESET,
    SCREEN_CORRECTION_POLICY,
    SCREEN_CORRECTION_PRESET,
    correction_policy_for_mode,
)
from game_predictor_api.domain.grid_correction_progress import correction_progress_counts
from game_predictor_api.domain.grid_correction_split import correction_data_availability
from game_predictor_api.domain.grid_detector_readiness import detector_readiness
from game_predictor_api.domain.grid_learning_candidate_status import candidate_status
from game_predictor_api.domain.grid_learning_sample_view import learning_test_sample
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.grid_training_cohorts import (
    LEARNING_SPLIT_SECONDS,
    GridCohortError,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_correction_split import (
    GridCorrectionSplitPreparationError,
    prepare_split,
)
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_preparation_progress import preparation_deadline
from game_predictor_api.storage.grid_private_learning import (
    assignment_pin,
    require_learning_pin,
    weight_initialization,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.grid_training_run_jobs import SqlAlchemyGridTrainingRunJobs
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import GameModel, JobModel

from .grid_correction_history import verified_publication_scope
from .grid_model_evaluation import GridModelEvaluationService, report_id_for
from .grid_model_registry import GridModelRegistryService
from .grid_training_cohorts import GridTrainingCohortService
from .grid_training_runs import GridTrainingRunService
from .shared_grid_model_candidate import SharedGridCandidateService

LEARNING_KIND = "grid-correction-learning-v1"
ACTIVE = {JobStatus.CREATED, JobStatus.PROCESSING}


def labelled_import_scope(session: Session, game: UUID) -> list[str]:
    """Default scope: imports with a human geometry label or earlier cohort members.

    Imports without either add only unlabelled population, yet count towards the
    split's population limit and solver budget (D-606). Earlier member imports
    stay in scope, so the incremental split keeps every prior role.
    """
    return sorted(
        str(value)
        for value in session.scalars(
            text("""
      SELECT DISTINCT s.import_job_id FROM source_images s
      WHERE s.game_id=:game AND (
       EXISTS(SELECT 1 FROM recognized_boards b WHERE b.game_id=s.game_id
        AND b.source_image_id=s.id AND b.approved_geometry_revision=b.geometry_revision
        AND b.geometry_approved_by IS NOT NULL AND b.geometry_approved_at IS NOT NULL
        AND b.geometry_approved_by NOT LIKE 'system:%'
        AND b.geometry_approved_by NOT LIKE 'worker:%')
       OR EXISTS(SELECT 1 FROM grid_training_cohort_members m
        WHERE m.game_id=s.game_id AND m.source_id=s.id))
      LIMIT 101"""),
            {"game": game},
        )
    )


def child_key(parent: UUID, kind: str) -> UUID:
    return uuid5(parent, "grid-correction-learning:" + kind)


class GridCorrectionLearningService:
    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        *,
        provider_index_sha256: str | None = None,
    ) -> None:
        self.engine, self.session_factory, self.artifact_root = (
            engine,
            session_factory,
            artifact_root,
        )
        self.evaluations = GridModelEvaluationService(engine, session_factory, artifact_root)
        self.provider_index_sha256 = provider_index_sha256

    def _cohorts(self, session: Session) -> GridTrainingCohortService:
        return GridTrainingCohortService(
            SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root),
            self.artifact_root,
            self.provider_index_sha256,
        )

    def ready(
        self, game: UUID, *, recommend_training_mode: bool = False, lightweight: bool = False
    ) -> dict[str, Any]:
        if lightweight:
            from .grid_learning_preparation import readiness as preparation_readiness

            return preparation_readiness(self, game)
        points = self.preview(game, {"importJobIds": [], "exclusions": []})
        if not recommend_training_mode:
            return points
        if points.get("weightInitialization") == "from_scratch":
            return {
                **points,
                "trainingRecommendation": {
                    "mode": "screen+grid",
                    "reasonCodes": points["blockers"] or ["GRID_LEARNING_RECOMMENDED_DETECTOR"],
                },
            }
        chosen = points
        reasons = ["GRID_LEARNING_RECOMMENDED_POINTS"]
        readiness = points.get("detectorReadiness")
        # Preserve partial TRAIN corrections: the screen trainer must not turn
        # their unlabelled boards into background or silently omit their labels.
        partial_train = points.get("partialTrainingPhotos", 0)
        if partial_train:
            reasons.append("GRID_LEARNING_PARTIAL_TRAIN_PRESENT")
        elif readiness is not None and not readiness["reasonCodes"]:
            screen = self.preview(
                game, {"trainingMode": "screen+grid", "importJobIds": [], "exclusions": []}
            )
            if screen["canStart"]:
                chosen, reasons = screen, ["GRID_LEARNING_RECOMMENDED_DETECTOR"]
            else:
                reasons.extend(screen["blockers"])
        else:
            reasons.extend((readiness or {}).get("reasonCodes", []))
        return {
            **chosen,
            "trainingRecommendation": {"mode": chosen["trainingMode"], "reasonCodes": reasons},
        }

    def _split(
        self,
        game: UUID,
        command: Mapping[str, Any],
        policy: str,
        mode: str,
        components: list[dict[str, Any]] | None = None,
        base: Mapping[str, Any] | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        with game_storage_scope(game), self.session_factory() as session:
            repository = SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root)
            repository.bind(game)
            imports = sorted({str(value) for value in command.get("importJobIds") or []})
            if not imports:
                imports = labelled_import_scope(session, game)
            if not imports and command.get("weightInitialization") == "from_scratch":
                raise GridCohortError(
                    "SCREEN_FULL_PHOTOS_REQUIRED",
                    "No labelled imports qualify for the independent detector.",
                )
            if not imports or len(imports) > 100:
                raise GridCohortError(
                    "GRID_LEARNING_IMPORT_SCOPE_INVALID",
                    "Choose between one and 100 complete imports.",
                )
            options: dict[str, Any] = {}
            if command.get("weightInitialization") == "from_scratch":
                options["private_from_scratch"] = True
            if policy == "application-grid-corrections-v4":
                options.update(
                    policy=policy,
                    mode=mode,
                    validation_assignments=command["validationAssignments"],
                    validation_components=components,
                )
            elif policy == SCREEN_CORRECTION_POLICY:
                options["policy"] = policy
            if command.get("contentExperiment") is not None:
                from game_predictor_api.storage.grid_content_sampling import (
                    resolve_content_sampling,
                )

                if base is None or self.provider_index_sha256 is None:
                    raise GridCohortError(
                        "CONTENT_BANK_ANCESTRY_UNRESOLVED", "Trusted ancestry is required."
                    )
                options["content_sampling"] = resolve_content_sampling(
                    repository,
                    game,
                    UUID(base["versionId"]),
                    UUID(base["familyId"]),
                    self.provider_index_sha256,
                )
            return imports, prepare_split(
                repository, game, imports, preparation_deadline(LEARNING_SPLIT_SECONDS), **options
            )

    def _preview(
        self, game: UUID, command: Mapping[str, Any], *, legacy_private: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from game_predictor_worker.training_core.grid_training_admission import (
            PRESETS,
            WORKER_CHECKS,
            cost_view,
            estimate_cohort_cost,
            summed_counts,
        )

        mode = str(command.get("trainingMode", "grid-only"))
        policy = command.get("policyVersion") or correction_policy_for_mode(mode)
        purpose_aware = policy == "application-grid-corrections-v4"
        experiment = command.get("contentExperiment")
        if experiment is not None and (
            experiment != "full-symbol-content-experiment-v1"
            or mode != "screen+grid"
            or not purpose_aware
            or command.get("rescueVariant") is not None
        ):
            raise GridCohortError(
                "CONTENT_EXPERIMENT_MODE_INVALID",
                "Explicit content screen/v4 mode is required.",
                422,
            )
        if policy not in (correction_policy_for_mode(mode), "application-grid-corrections-v4"):
            raise ValueError("Unsupported explicit correction policy.")
        if purpose_aware and not isinstance(command.get("validationAssignments"), dict):
            raise ValueError("The explicit v4 policy requires validation assignments.")
        screen = mode == "screen+grid"
        preset = PRESETS[SCREEN_CORRECTION_PRESET if screen else CORRECTION_PRESET]
        blockers: list[str] = []
        pins: dict[str, Any] = {}
        view: dict[str, Any] = {
            "trainingMode": mode,
            "detectorReadiness": None,
            "rescueVariant": command.get("rescueVariant"),
            "rescueRecipeSha256": None,
            "gameId": str(game),
            "baseVersionId": None,
            "baseManifestSha256": None,
            "defaultRevision": None,
            "importJobIds": [],
            "roleCounts": [],
            "dataAvailability": None,
            "progressCounts": None,
            "bufferPhotos": 0,
            "priorScopeDocumented": False,
            "priorGameIds": [],
            "historicalCohorts": [],
            "exclusions": list(command.get("exclusions") or []),
            "requiredGameIds": [str(game)],
            "presetId": preset.preset_id,
            "presetFingerprint": preset.fingerprint,
            "cost": None,
            "blockers": blockers,
            "pendingWorkerChecks": list(WORKER_CHECKS),
            "canStart": False,
            "evidenceLevel": "photo-only",
            "limitations": list(PHOTO_ONLY_LIMITATIONS),
        }
        if purpose_aware:
            view.update(
                policyVersion=policy,
                validationAssignments=dict(sorted(command["validationAssignments"].items())),
                validationComponents=[],
            )
            pins.update(
                policyVersion=policy,
                trainingMode=mode,
                validationAssignments=view["validationAssignments"],
            )
        if experiment is not None:
            view.update(
                contentExperiment=experiment,
                contentExperimentReadiness={
                    "state": "blocked",
                    "reasonCodes": [],
                    "games": [],
                    "inputsSha256": None,
                },
            )
            view["pendingWorkerChecks"].extend(
                ["CONTENT_BANK_MEASUREMENT", "EXPERIMENT_ARM_FEASIBILITY"]
            )
            pins.update(
                contentExperiment=experiment,
                providerIndexSha256=self.provider_index_sha256,
                contentSamplingPolicy="full-symbol-content-sampling-v1",
            )
        try:
            if experiment is not None and self.provider_index_sha256 is None:
                raise GridCohortError(
                    "CONTENT_BANK_ANCESTRY_UNRESOLVED", "Trusted ancestry providers are required."
                )
            with Session(self.engine) as session:
                repository = SqlAlchemyGridModelRegistryRepository(session)
                private = repository.game_grid_model_private(game)
                if private:
                    view.update(
                        learningScope="private_game",
                        gameName=session.scalar(select(GameModel.name).where(GameModel.id == game)),
                    )
                if command.get("learningScope") not in (
                    None,
                    "private_game" if private else "shared",
                ):
                    raise GridCohortError(
                        "GRID_LEARNING_SCOPE_CHANGED",
                        "Choose the learning scope shown for this game.",
                    )
                private_pin = assignment_pin(repository, game) if private else None
                default = None if private else repository.default()
                if private_pin is None and default is None:
                    raise GridCohortError(
                        "GRID_LEARNING_DEFAULT_REQUIRED", "Choose a global default first."
                    )
                registry = GridModelRegistryService(
                    repository, GridModelArtifactInspector(self.artifact_root)
                )
                if private_pin is not None:
                    base_id = UUID(private_pin["baseVersionId"])
                    default_revision = None
                    view.update(
                        assignmentRevision=private_pin["assignmentRevision"],
                        targetFamilyId=private_pin["targetFamilyId"],
                        baseVersionId=private_pin["baseVersionId"],
                    )
                    pins["privateLearning"] = private_pin
                    if not legacy_private:
                        initialization = weight_initialization(repository, game, private_pin)
                        pins["weightInitialization"] = view["weightInitialization"] = initialization
                        if initialization == "from_scratch":
                            if (
                                command.get("trainingMode", "screen+grid") != "screen+grid"
                                or experiment is not None
                                or command.get("rescueVariant") is not None
                            ):
                                raise GridCohortError(
                                    "GRID_LEARNING_PRIVATE_SCREEN_REQUIRED",
                                    "First train the whole detector and grid on full photos.",
                                )
                            # V4 retains partial TRAIN labels for the grid.
                            mode, screen, purpose_aware = "screen+grid", True, True
                            preset = PRESETS[SCREEN_CORRECTION_PRESET]
                            policy = "application-grid-corrections-v4"
                            assignments = dict(
                                sorted((command.get("validationAssignments") or {}).items())
                            )
                            view.update(
                                trainingMode=mode,
                                presetId=preset.preset_id,
                                presetFingerprint=preset.fingerprint,
                                policyVersion=policy,
                                validationAssignments=assignments,
                                validationComponents=[],
                            )
                            pins.update(
                                policyVersion=policy,
                                trainingMode=mode,
                                validationAssignments=assignments,
                            )
                            command = {
                                **command,
                                "validationAssignments": assignments,
                                "weightInitialization": initialization,
                            }
                    if command.get("historicalCohorts") or command.get("exclusions"):
                        raise GridCohortError(
                            "GRID_LEARNING_PRIVATE_COHORTS_INVALID",
                            "Private learning takes only this game's cohort.",
                        )
                else:
                    assert default is not None
                    base_id, default_revision = default.version_id, default.revision
                record = repository.version(base_id)
                if record is None:
                    raise GridCohortError(
                        "GRID_LEARNING_BASE_MISSING", "The default model is missing."
                    )
                cold = pins.get("weightInitialization") == "from_scratch"
                base = (
                    registry.view(record, include_eligibility=False, inference_only=True)
                    if cold
                    else registry.view(record, include_eligibility=True)
                )
                if not base["available"]:
                    raise GridCohortError(
                        "GRID_LEARNING_BASE_UNAVAILABLE", "The default artifacts are unavailable."
                    )
                manifest = base["manifest"]
                history = verified_publication_scope(repository, base_id)
                if private:
                    # A fork imports weights and ancestry exclusions but no foreign photos.
                    history = {
                        **history,
                        "gameIds": [g for g in history["gameIds"] if g == str(game)],
                        "cohorts": [],
                    }
                else:
                    excluded_games = {str(item["gameId"]) for item in view["exclusions"]}
                    other_games = [
                        UUID(prior) for prior in history["gameIds"] if prior not in excluded_games
                    ]
                    if other_games and session.scalar(
                        select(GameModel.id)
                        .where(
                            GameModel.id.in_(other_games), GameModel.grid_model_private.is_(True)
                        )
                        .limit(1)
                    ):
                        view.update(
                            priorGameIds=history["gameIds"],
                            priorScopeDocumented=history["documented"],
                        )
                        raise GridCohortError(
                            "GRID_LEARNING_PRIVATE_HISTORY_EXCLUDED",
                            "Explicitly exclude private games from the shared workflow.",
                        )
                # The artifact inspector verifies every listed training artifact's bytes.
                training = manifest.get("trainingArtifacts") or []
                if not cold and not {
                    "weights.pt",
                    "checkpoint.pt",
                    "bundle.json",
                    "preset.json",
                } <= {item["name"] for item in training}:
                    raise GridCohortError(
                        "GRID_LEARNING_TRAINING_ARTIFACTS_REQUIRED",
                        "The base needs its original training artifacts.",
                    )
                pins.update(
                    base=manifest,
                    baseSha256=base["manifestSha256"],
                    defaultRevision=default_revision,
                )
                view.update(
                    baseVersionId=str(base_id),
                    baseManifestSha256=base["manifestSha256"],
                    defaultRevision=default_revision,
                    priorScopeDocumented=history["documented"],
                    priorGameIds=history["gameIds"],
                )
            lineage_root = {
                "versionId": manifest["versionId"],
                "familyId": view.get("targetFamilyId") or manifest["familyId"],
            }
            excluded = {str(item["gameId"]) for item in view["exclusions"]}
            historic = [
                pin
                for pin in history["cohorts"]
                if pin["gameId"] != str(game) and pin["gameId"] not in excluded
            ]
            scope, required = require_scope(
                {
                    "currentGameId": str(game),
                    "trainingGameIds": sorted({str(game), *(pin["gameId"] for pin in historic)}),
                    "priorVerifiedGameIds": history["gameIds"],
                    "priorScopeDocumented": history["documented"],
                    "exclusions": view["exclusions"],
                }
            )
            if purpose_aware:
                # Retain required-game navigation even when current data lacks
                # minima; project choices before historical-cohort admission.
                view.update(historicalCohorts=historic, requiredGameIds=required)
                imports, split = self._split(
                    game,
                    command,
                    policy,
                    mode,
                    view["validationComponents"],
                    **({"base": lineage_root} if experiment is not None else {}),
                )
                view["importJobIds"] = imports
            if set(required) - {str(game), *(pin["gameId"] for pin in historic)}:
                raise GridCohortError(
                    "GRID_LEARNING_HISTORY_COHORT_REQUIRED",
                    "A required historical game has no pinned cohort.",
                )
            if len(historic) > 7:
                raise GridCohortError(
                    "GRID_SHARED_SCOPE_INVALID", "The approved shared-run limit is eight games."
                )
            if command.get("historicalCohorts"):
                from .grid_correction_history import select_historical_cohorts

                if not (screen or purpose_aware):
                    raise ValueError(
                        "Historical cohort choices require the screen correction policy."
                    )
                historic = select_historical_cohorts(
                    historic,
                    command["historicalCohorts"],
                    current_game=str(game),
                    required_games=required,
                )
            view.update(historicalCohorts=historic, requiredGameIds=required)
            pins.update(scope=scope, historicalCohorts=historic)
            if not purpose_aware:
                imports, split = self._split(game, command, policy, mode)
                view["importJobIds"] = imports
            pins["splitSha256"] = split["sha256"]
            if split.get("learningMaterial") is not None:
                view["learningMaterial"] = split["learningMaterial"]
            sample = learning_test_sample(split.get("contentSampling"))
            if sample is not None:
                view["testSample"] = sample
            representatives = [item for item in split["sources"] if item["representative"]]
            detector_sources = [
                {
                    **item,
                    "qualifiedBoards": item.get("qualifiedBoards", item["eligibleBoards"]),
                    "role": item.get("role"),
                }
                for item in representatives
            ]
            view.update(
                detectorReadiness=split.get("detectorReadiness")
                or detector_readiness(
                    [item["qualifiedBoards"] for item in detector_sources], detector_sources
                ),
                partialTrainingPhotos=sum(
                    item["role"] == "TRAIN" and 0 < item["qualifiedBoards"] < 9
                    for item in detector_sources
                ),
                dataAvailability=correction_data_availability(
                    sum(
                        item.get("qualifiedBoards", item["eligibleBoards"]) > 0
                        for item in representatives
                    ),
                    sum(
                        item.get("qualifiedBoards", item["eligibleBoards"])
                        for item in representatives
                    ),
                    "ready",
                ),
                roleCounts=split["roleCounts"],
                bufferPhotos=sum(bool(item["buffer"]) for item in representatives),
                progressCounts=correction_progress_counts(split),
            )
            if purpose_aware:
                purposes = {
                    key: split["purposeCounts"].get(
                        "VALIDATION-" + key, {"boards": 0, "photos": 0, "fullPhotos": 0}
                    )
                    for key in ("A", "B")
                }
                view["validationPurposeCounts"] = purposes
                view["roleCounts"] = [
                    {**item, "photos": purposes["A"]["photos"], "boards": purposes["A"]["boards"]}
                    if item["role"] == "VALIDATION"
                    else item
                    for item in view["roleCounts"]
                ]
                view["progressCounts"]["validation"] = {
                    k: purposes["A"][k] for k in ("photos", "boards")
                }
                if view["detectorReadiness"] is not None:
                    readiness = view["detectorReadiness"]
                    full_a = purposes["A"]["fullPhotos"]
                    view["detectorReadiness"] = {
                        **readiness,
                        "roles": [
                            {
                                **item,
                                "eligibleFullPhotos": full_a,
                                "missingFullPhotos": max(0, item["requiredFullPhotos"] - full_a),
                            }
                            if item["role"] == "VALIDATION"
                            else item
                            for item in readiness["roles"]
                        ],
                        "reasonCodes": sorted(
                            set(readiness["reasonCodes"])
                            | ({"SCREEN_FULL_VALIDATION_REQUIRED"} if full_a < 5 else set())
                        ),
                    }
            if cold and view["detectorReadiness"]["reasonCodes"]:
                blockers.extend(view["detectorReadiness"]["reasonCodes"])
            summaries: list[dict[str, Any]] = [
                {
                    "mode": mode,
                    "summary": {
                        "roles": [
                            {
                                "role": item["role"],
                                "eligibleBoards": item["boards"],
                                "eligiblePhotos": item["photos"],
                                "eligibleFullPhotos": sum(
                                    p["role"] == item["role"] and p["eligibleBoards"] == 9
                                    for p in representatives
                                )
                                if screen
                                else 0,
                            }
                            for item in view["roleCounts"]
                        ]
                    },
                }
            ]
            if purpose_aware:
                summaries[0]["policyVersion"] = policy
                summaries[0]["summary"]["validationPurposes"] = purposes
            shared = SharedGridCandidateService(self.session_factory, self.artifact_root)
            selection_parts = [(str(game), split)]
            historical_currentness = []
            for pin in historic:
                header, eligibility, _ = shared._cohort(UUID(pin["gameId"]), UUID(pin["cohortId"]))
                if (
                    header["manifestSha256"] != pin["manifestSha256"]
                    or header["status"] != "frozen"
                    or header["mode"] != mode
                    or header["familyId"] != manifest["familyId"]
                    or eligibility["qualification"] != "eligible"
                ):
                    raise GridCohortError(
                        "SCREEN_HISTORY_COHORT_REQUIRED"
                        if screen
                        else "GRID_LEARNING_HISTORY_UNAVAILABLE",
                        "A required historical cohort is unavailable or incompatible.",
                    )
                if str(header["baseVersionId"]) != manifest["versionId"]:
                    from .grid_correction_history import require_historical_cohort

                    with Session(self.engine) as history_session:
                        require_historical_cohort(
                            SqlAlchemyGridModelRegistryRepository(history_session),
                            UUID(manifest["versionId"]),
                            dict(header),
                        )
                historical_currentness.append(
                    {
                        "gameId": pin["gameId"],
                        "cohortId": pin["cohortId"],
                        "eligibility": eligibility,
                    }
                )
                summaries.append(header)
                if screen or purpose_aware:
                    from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot

                    if header.get("policyVersion") != policy:
                        raise GridCohortError(
                            "SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED",
                            "Choose a new screen correction cohort with "
                            "frozen validation selection evidence.",
                        )
                    historical_snapshot = GridCohortSnapshot(
                        self.artifact_root, header["manifestPath"], header["manifestSha256"]
                    )
                    historical_split = historical_snapshot.manifest.get("photoSplit")
                    if purpose_aware and (
                        historical_snapshot.manifest.get("gameId") != pin["gameId"]
                        or historical_snapshot.manifest.get("cohortId") != pin["cohortId"]
                        or historical_snapshot.manifest.get("familyId") != header["familyId"]
                        or historical_snapshot.manifest.get("mode") != mode
                        or historical_snapshot.manifest.get("policyVersion") != policy
                        or historical_snapshot.manifest.get("base", {}).get("versionId")
                        != str(header["baseVersionId"])
                    ):
                        raise GridCohortError(
                            "SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED",
                            "Historical v4 snapshot identity differs from the pinned cohort.",
                        )
                    if not isinstance(historical_split, dict) or historical_split.get(
                        "schemaVersion"
                    ) != (
                        "grid-correction-split-v4" if purpose_aware else "grid-correction-split-v3"
                    ):
                        raise GridCohortError(
                            "SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED",
                            "The historical cohort has no compatible "
                            "frozen validation selection input.",
                        )
                    selection_parts.append((pin["gameId"], historical_split))
            if purpose_aware:
                pins["historicalCurrentness"] = historical_currentness
            if screen and experiment is None:
                from game_predictor_worker.training_core.grid_rescue_training import (
                    rescue_recipe,
                    selection_input,
                )

                selection = selection_input(selection_parts)
                from game_predictor_api.domain.grid_rescue_policy import (
                    PRIVATE_GRID_RECIPE_FINGERPRINT,
                )

                baseline_preset_sha = (
                    PRIVATE_GRID_RECIPE_FINGERPRINT
                    if cold
                    else next(
                        item["sha256"]
                        for item in manifest["trainingArtifacts"]
                        if item["name"] == "preset.json"
                    )
                )
                recipe = rescue_recipe(baseline_preset_sha, command.get("rescueVariant"), selection)
                pins.update(selectionInput=selection, rescueRecipe=recipe)
                pins["historicalCurrentness"] = historical_currentness
                view["rescueRecipeSha256"] = recipe["sha256"]
            if experiment is not None:
                from game_predictor_api.storage.grid_content_experiment_inputs import (
                    read_experiment_inputs,
                )

                inputs = read_experiment_inputs(
                    self.session_factory,
                    self.artifact_root,
                    lineage_root,
                    pins["baseSha256"],
                    selection_parts,
                    self.provider_index_sha256,
                )
                pins["contentExperimentInputs"] = inputs
                view["contentExperimentReadiness"].update(
                    inputsSha256=inputs["sha256"],
                    games=[
                        {
                            "gameId": p["gameId"],
                            "bankEligiblePhotos": len(p["sources"]),
                            "excludedPhotos": len(p["excluded"]),
                        }
                        for p in inputs["trainEligibility"]["games"]
                    ],
                )
            else:
                cost = estimate_cohort_cost(
                    preset,
                    summed_counts(summaries),
                    rescue_variant=command.get("rescueVariant"),
                    include_partial_training_photos=cold,
                )
                view["cost"] = cost_view(cost)
                if not cost.within_budget or cost.planned_steps < 1:
                    blockers.append("GRID_RUN_COHORT_COST_EXCEEDS_BUDGET")
        except (GridCohortError, GridModelRegistryError) as error:
            blockers.append(error.code)
            if (
                view.get("weightInitialization") == "from_scratch"
                and error.code == "SCREEN_FULL_PHOTOS_REQUIRED"
            ):
                view["detectorReadiness"] = detector_readiness([])
            material = getattr(error, "learning_material", None)
            if material is not None:
                view["learningMaterial"] = material
            sample = learning_test_sample(getattr(error, "report", None))
            if sample is not None:
                view["testSample"] = sample
            if isinstance(error, GridCorrectionSplitPreparationError):
                view["dataAvailability"] = error.data_availability
                view["detectorReadiness"] = error.detector_readiness
        except ValueError as error:
            # Pure scope validation failures are input errors, never undocumented narrowing.
            raise GridCohortError("GRID_LEARNING_SCOPE_INVALID", str(error), 422) from error
        view["canStart"] = not blockers
        if experiment is not None:
            view["contentExperimentReadiness"].update(
                state="metadata_ready" if not blockers else "blocked", reasonCodes=list(blockers)
            )
        view["previewSha256"] = descriptor_sha256({"view": view, "pins": pins})
        return view, pins

    def preview(self, game: UUID, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._preview(game, command)[0]

    @staticmethod
    def _by_key(session: Session, game: UUID, key: UUID) -> Job | None:
        row = session.scalar(
            select(JobModel).where(
                JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
                JobModel.input_payload["learning_kind"].as_string() == LEARNING_KIND,
                JobModel.game_id == game,
                JobModel.input_payload["idempotency_key"].as_string() == str(key),
            )
        )
        return None if row is None else job_from_record(row)

    @staticmethod
    def _job(session: Session, game: UUID, identifier: UUID, *, lock: bool = False) -> Job:
        repository = SqlAlchemyJobRepository(session)
        job = repository.get_job_for_update(identifier) if lock else repository.get_job(identifier)
        if (
            job is None
            or job.game_id != game
            or job.job_type != JobType.GRID_CORRECTION_LEARNING
            or job.input_payload.get("learning_kind") != LEARNING_KIND
        ):
            raise GridCohortError("GRID_LEARNING_NOT_FOUND", "Learning workflow not found.", 404)
        return job

    def start(self, game: UUID, command: Mapping[str, Any], actor: str) -> dict[str, Any]:
        from .grid_learning_preparation import (
            acquire_learning_game_lock,
            require_no_active_learning,
        )

        if command.get("prepareInBackground"):
            from .grid_learning_preparation import enqueue

            return enqueue(self, game, dict(command), actor)
        key = UUID(str(command["idempotencyKey"]))
        original = dict(command)
        # Additive defaults do not change an immutable pre-T3 command's identity.
        for field, default_value in (
            ("trainingMode", "grid-only"),
            ("rescueVariant", None),
            ("historicalCohorts", []),
            ("policyVersion", None),
            ("validationAssignments", None),
            ("contentExperiment", None),
        ):
            if (
                field == "trainingMode"
                and original.get("policyVersion") == "application-grid-corrections-v4"
            ):
                continue
            if original.get(field, default_value) == default_value:
                original.pop(field, None)
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            acquire_learning_game_lock(session, game)
            existing = self._by_key(session, game, key)
            if existing is not None:
                if existing.input_payload["command"] != original:
                    raise GridCohortError(
                        "GRID_LEARNING_IDEMPOTENCY_CONFLICT", "The key belongs to another command."
                    )
                return self.view(existing)
            require_no_active_learning(session, game)
            view, pins = self._preview(game, command)
            if (
                view.get("learningScope") == "private_game"
                and command.get("learningScope") != "private_game"
            ):
                raise GridCohortError(
                    "GRID_LEARNING_PRIVATE_SCOPE_REQUIRED",
                    "Confirm private learning for this game.",
                )
            if not view["canStart"]:
                raise GridCohortError(view["blockers"][0], "The learning preview has blockers.")
            if view["previewSha256"] != command["previewSha256"]:
                raise GridCohortError(
                    "GRID_LEARNING_PREVIEW_CHANGED", "Read and confirm a fresh preview."
                )
            # Serialize against set_default until the parent command is committed.
            catalogue = SqlAlchemyGridModelRegistryRepository(session)
            catalogue.lock()
            require_learning_pin(catalogue, game, pins.get("privateLearning"))
            default = None if "privateLearning" in pins else catalogue.default()
            if "privateLearning" not in pins and (
                default is None
                or default.revision != pins["defaultRevision"]
                or str(default.version_id) != view["baseVersionId"]
            ):
                raise GridCohortError(
                    "GRID_LEARNING_DEFAULT_CHANGED", "The global default changed."
                )
            payload = {
                "schema_version": 1,
                "learning_kind": LEARNING_KIND,
                "idempotency_key": str(key),
                "command": original,
                "preview": view,
                "pins": pins,
                "actor": actor,
            }
            return self.view(
                SqlAlchemyJobRepository(session).add_job(
                    create_job(
                        JobType.GRID_CORRECTION_LEARNING, game_id=game, input_payload=payload
                    )
                )
            )

    def list(self, game: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(JobModel)
                .where(
                    JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
                    JobModel.game_id == game,
                    JobModel.input_payload["learning_kind"].as_string() == LEARNING_KIND,
                )
                .order_by(JobModel.created_at.desc())
                .limit(200)
            )
            views = [self.view(job_from_record(row)) for row in rows]
            self._attach_candidates(session, game, views)
            return {"items": views}

    def get(self, game: UUID, identifier: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            job = self._job(session, game, identifier)
            view = self.view(job)
            if job.status == JobStatus.WAITING_FOR_REVIEW and (job.checkpoint_payload or {}).get(
                "preparedArtifact"
            ):
                from .grid_learning_preparation import load_prepared

                prepared = load_prepared(self, job)
                if prepared is not None:
                    view["preparedPreview"] = prepared["preview"]
            self._attach_candidates(session, game, [view])
            return view

    def _attach_candidates(
        self, session: Session, game: UUID, views: Sequence[dict[str, Any]]
    ) -> None:
        """Read-only current state of each candidate (TASK-1189); pins stay unchanged."""
        if not any(view.get("candidateVersionId") for view in views):
            return
        registry = SqlAlchemyGridModelRegistryRepository(session)
        head = registry.default()
        assignment, _ = registry.assignment(game)
        default_version = None if head is None else str(head.version_id)
        assigned_version = None if assignment is None else str(assignment.version_id)
        evaluations: dict[str, Sequence[dict[str, Any]]] = {}
        for view in views:
            version = view.get("candidateVersionId")
            if not version:
                continue
            if version not in evaluations:
                evaluations[version] = self._candidate_evaluations(session, registry, version)
            view["candidate"] = candidate_status(
                candidate_version_id=str(version),
                learning_evaluation_id=view.get("evaluationId"),
                default_version_id=default_version,
                assigned_version_id=assigned_version,
                evaluations=evaluations[version],
            )

    def _candidate_evaluations(
        self, session: Session, registry: SqlAlchemyGridModelRegistryRepository, version: str
    ) -> Sequence[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for job in self.evaluations._jobs(session, UUID(version)):
            if (
                job.status != JobStatus.COMPLETED
                or job.input_payload.get("evaluation_kind") == "grid-assigned-comparison-v1"
            ):
                continue
            row, invalidated = registry.evaluation(report_id_for(job.id))
            if row is None or invalidated:
                continue
            report = json.loads(row.report_json)
            if report.get("verdict") not in {"PASS", "REVISE", "NOT_EVALUABLE"}:
                continue
            result.append(
                {
                    "evaluationId": str(job.id),
                    "reportId": str(row.id),
                    "verdict": report["verdict"],
                    "policyVersion": str(report.get("policyVersion", "")),
                    "createdAt": job.created_at.isoformat(),
                }
            )
            # Newest first; only the latest is shown.
            break
        return result

    def _children(self, session: Session, job: Job) -> Sequence[Job]:
        keys = [str(child_key(job.id, kind)) for kind in ("training", "evaluation")]
        rows = session.scalars(
            select(JobModel)
            .where(
                JobModel.game_id == job.game_id,
                JobModel.job_type.in_([JobType.GRID_TRAINING, JobType.GRID_MODEL_EVALUATION]),
                JobModel.input_payload["idempotency_key"].as_string().in_(keys),
            )
            .with_for_update()
        )
        return [job_from_record(row) for row in rows]

    def cancel(self, game: UUID, identifier: UUID, actor: str) -> dict[str, Any]:
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            self._lock_step(session, identifier)
            job = self._job(session, game, identifier, lock=True)
            repository = SqlAlchemyJobRepository(session)
            for child in self._children(session, job):
                if child.status in ACTIVE or child.status == JobStatus.WAITING_FOR_REVIEW:
                    repository.save_job(request_job_cancellation(child))
            if job.status in {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}:
                return self.view(job)
            return self.view(repository.save_job(request_job_cancellation(job)))

    def resume(self, game: UUID, identifier: UUID, actor: str) -> dict[str, Any]:
        from .grid_learning_preparation import (
            acquire_learning_game_lock,
            require_no_active_learning,
        )

        with game_storage_scope(game), self.session_factory() as session, session.begin():
            acquire_learning_game_lock(session, game)
            self._lock_step(session, identifier)
            job = self._job(session, game, identifier, lock=True)
            prepared_review = (
                job.status == JobStatus.WAITING_FOR_REVIEW
                and job.input_payload.get("backgroundPreparation")
                and (job.checkpoint_payload or {}).get("preparedArtifact") is not None
            )
            if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED} and not prepared_review:
                raise GridCohortError(
                    "GRID_LEARNING_NOT_RESUMABLE", "Only a failed or cancelled workflow resumes."
                )
            require_no_active_learning(session, game, excluding=identifier)
            catalogue = SqlAlchemyGridModelRegistryRepository(session)
            catalogue.lock()
            require_learning_pin(
                catalogue, game, job.input_payload.get("pins", {}).get("privateLearning")
            )
            repository = SqlAlchemyJobRepository(session)
            from game_predictor_api.storage.sequence_ownership_lock import (
                acquire_sequence_ownership_lock,
            )
            from game_predictor_api.storage.source_replacement_guards import require_cohort_sources

            acquire_sequence_ownership_lock(session, game_id=game)
            cohort = (job.checkpoint_payload or {}).get("cohortId")
            if cohort is not None or job.input_payload.get("pins", {}).get("privateLearning"):
                self._cohorts(session).repository.bind(game, write=True)
            if cohort is not None:
                require_cohort_sources(session, game, UUID(str(cohort)))
            children = self._children(session, job)
            if any(
                child.status in ACTIVE and child.cancel_requested_at is not None
                for child in children
            ):
                raise GridCohortError(
                    "GRID_LEARNING_CANCELLATION_PENDING",
                    "Wait for the original child to acknowledge cancellation before resuming.",
                )
            for child in children:
                if child.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                    repository.save_job(requeue_job(child))
            if prepared_review:
                job = replace(
                    job,
                    checkpoint_payload={
                        **(job.checkpoint_payload or {}),
                        "trainingAuthorized": True,
                    },
                )
            return self.view(repository.save_job(requeue_job(job)))

    def evaluation(self, game: UUID, identifier: UUID) -> dict[str, Any]:
        view = self.get(game, identifier)
        if view["evaluationId"] is None:
            raise GridCohortError(
                "GRID_LEARNING_EVALUATION_PENDING", "Evaluation has not been created."
            )
        return self.evaluations.get(UUID(view["evaluationId"]))

    @staticmethod
    def view(job: Job) -> dict[str, Any]:
        state: Any = job.checkpoint_payload or {}
        preview: Any = state.get("preparedSummary") or job.input_payload["preview"]
        return {
            **(
                {"commandKey": job.input_payload["idempotency_key"]}
                if job.input_payload.get("idempotency_key")
                else {}
            ),
            **(
                {
                    "preparation": {
                        **state.get(
                            "preparation", {"stage": "queued", "current": 0, "total": None}
                        ),
                        "heartbeatAt": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
                        "stalled": (
                            job.status == JobStatus.PROCESSING
                            and job.stage
                            in {
                                "preparing_data",
                                "source_inventory",
                                "recording_context",
                                "geometry_evidence",
                                "cohort_capture",
                                "cohort_materialization",
                                "freeze_inputs",
                                "freeze_members",
                            }
                            and bool(state.get("preparation", {}).get("lastProgressAt"))
                            and (
                                datetime.now(UTC)
                                - datetime.fromisoformat(state["preparation"]["lastProgressAt"])
                            ).total_seconds()
                            > 300
                        ),
                    }
                }
                if job.input_payload.get("backgroundPreparation")
                else {}
            ),
            **(
                {
                    "contentExperiment": preview["contentExperiment"],
                    "contentExperimentPlanSha256": state.get("contentExperimentPlanSha256"),
                }
                if preview.get("contentExperiment") is not None
                else {}
            ),
            **{
                key: preview[key]
                for key in (
                    "learningScope",
                    "targetFamilyId",
                    "assignmentRevision",
                    "gameName",
                    "weightInitialization",
                )
                if key in preview
            },
            "learningId": str(job.id),
            "gameId": str(job.game_id),
            "status": job.status.value,
            "stage": job.stage,
            "baseVersionId": preview["baseVersionId"],
            "defaultRevision": preview["defaultRevision"],
            **{
                key: state.get(key)
                for key in (
                    "cohortId",
                    "trainingRunId",
                    "candidateVersionId",
                    "evaluationId",
                    "reportId",
                    "verdict",
                )
            },
            "previewSha256": preview["previewSha256"],
            "requiredGameIds": preview["requiredGameIds"],
            "exclusions": preview["exclusions"],
            "cancelRequested": job.cancel_requested_at is not None,
            "errorCode": job.error_code,
            "createdAt": job.created_at.isoformat(),
            "updatedAt": job.updated_at.isoformat(),
        }

    def advance(self, job: Job) -> tuple[dict[str, Any], bool]:
        """One committed unit, followed by lease release in the worker context."""
        assert job.game_id is not None
        game, actor = job.game_id, str(job.input_payload["actor"])
        payload: Any = job.input_payload
        state: dict[str, Any] = dict(job.checkpoint_payload or {})
        if payload.get("backgroundPreparation"):
            from .grid_learning_preparation import load_prepared

            prepared = load_prepared(self, job)
            if prepared is None:
                raise GridCohortError("GRID_LEARNING_PREPARATION_REQUIRED", "Prepare data first.")
            payload = {**payload, "preview": prepared["preview"], "pins": prepared["pins"]}
        pins, preview = payload["pins"], payload["preview"]
        if (
            pins.get("contentExperiment") is not None
            and pins.get("providerIndexSha256") != self.provider_index_sha256
        ):
            raise GridCohortError(
                "CONTENT_EXPERIMENT_PROVIDER_CHANGED", "The pinned provider index changed."
            )
        cohort_id = uuid5(game, "grid-cohort:" + str(child_key(job.id, "cohort")))
        state["cohortId"] = str(cohort_id)
        freeze_body: dict[str, Any] | None = None
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            if "privateLearning" in pins:
                catalogue = SqlAlchemyGridModelRegistryRepository(session)
                catalogue.lock()
                require_learning_pin(catalogue, game, pins["privateLearning"])
            service = self._cohorts(session)
            service.repository.bind(game)
            from game_predictor_api.storage.grid_training_cohort_models import (
                GridTrainingCohortModel,
            )

            row = session.get(GridTrainingCohortModel, (game, cohort_id))
            if (
                row is not None
                and "privateLearning" in pins
                and (
                    row.document.get("privateLearning") != pins["privateLearning"]
                    or row.document.get("weightInitialization") != pins.get("weightInitialization")
                    or row.document["photoSplit"]["sha256"] != pins["splitSha256"]
                    or row.document.get("cropPolicyVersion") != "full-cell-v2"
                    or row.document.get("detectorReadiness") != preview["detectorReadiness"]
                )
            ):
                raise GridCohortError(
                    "GRID_LEARNING_PRIVATE_COHORTS_INVALID",
                    "The prepared evidence differs from its private learning operation.",
                )
            if (
                row is not None
                and pins.get("policyVersion") == "application-grid-corrections-v4"
                and (
                    row.document.get("policyVersion") != pins["policyVersion"]
                    or row.document.get("mode") != pins["trainingMode"]
                    or row.document["photoSplit"]["sha256"] != pins["splitSha256"]
                    or row.document["photoSplit"].get("validationAssignments")
                    != pins["validationAssignments"]
                )
            ):
                raise GridCohortError(
                    "GRID_LEARNING_PREVIEW_CHANGED",
                    "The existing cohort differs from the pinned v4 selection.",
                )
            if row is None:
                command = {
                    "idempotencyKey": str(child_key(job.id, "cohort")),
                    "mode": preview.get("trainingMode", "grid-only"),
                    "familyId": preview.get("targetFamilyId") or pins["base"]["familyId"],
                    "baseVersionId": preview["baseVersionId"],
                    "selector": {"importJobIds": preview["importJobIds"]},
                    "recordings": [],
                    "policyVersion": correction_policy_for_mode(
                        preview.get("trainingMode", "grid-only")
                    ),
                }
                if "privateLearning" in pins:
                    command.update(
                        privateLearning=pins["privateLearning"],
                        cropPolicyVersion="full-cell-v2",
                        **(
                            {"weightInitialization": pins["weightInitialization"]}
                            if "weightInitialization" in pins
                            else {}
                        ),
                        detectorReadiness=preview["detectorReadiness"],
                    )
                if pins.get("policyVersion") == "application-grid-corrections-v4":
                    command.update(
                        policyVersion=pins["policyVersion"],
                        mode=pins["trainingMode"],
                        validationAssignments=pins["validationAssignments"],
                    )
                if pins.get("contentExperiment") is not None:
                    command["contentSamplingPolicy"] = pins["contentSamplingPolicy"]
                service.prepare(game, command, actor)
                row = service.repository.cohort(game, cohort_id)
                if row.document["photoSplit"]["sha256"] != pins["splitSha256"]:
                    raise GridCohortError(
                        "GRID_LEARNING_PREVIEW_CHANGED", "The split changed before capture."
                    )
                return state, False
            header = service.get(game, cohort_id)
            if header["status"] != "frozen":
                kind = {
                    "preparing": "prepare-page",
                    "preview_ready": "materialize-page",
                    "materializing": "materialize-page",
                    "ready_to_freeze": "freeze",
                }.get(header["status"])
                if kind is None:
                    raise GridCohortError(
                        "GRID_LEARNING_COHORT_BLOCKED", "The pinned cohort cannot continue."
                    )
                body = {
                    "idempotencyKey": str(child_key(job.id, f"{kind}:{header['revision']}")),
                    "expectedRevision": header["revision"],
                }
                if kind == "freeze":
                    body.update(
                        expectedPreviewSha256=header["previewSha256"],
                        expectedManifestSha256=header["manifestSha256"],
                    )
                    freeze_body = body
                else:
                    body["cursor"] = (
                        header["nextCaptureCursor"]
                        if kind == "prepare-page"
                        else header["nextMaterializationCursor"]
                    )
                    if kind == "materialize-page":
                        service.command(
                            game, cohort_id, kind, body, actor, materialization_pages=20
                        )
                    else:
                        service.command(game, cohort_id, kind, body, actor)
                    return state, False
        if freeze_body is not None:
            # Freeze acquires the registry lock on its own READ COMMITTED connection.
            # Release the parent's transaction before entering that boundary.
            with game_storage_scope(game), self.session_factory() as session:
                self._cohorts(session).command(game, cohort_id, "freeze", freeze_body, actor)
            return state, False
        # Separate advisory lock serializes child creation and cancellation without
        # blocking the parent's independent lease heartbeat transaction.
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            self._lock_step(session, job.id)
            latest = self._job(session, game, job.id)
            if latest.cancel_requested_at is not None:
                return state, False
            training = GridTrainingRunService(
                self._cohorts(session),
                SqlAlchemyGridTrainingRunJobs(session),
                SharedGridCandidateService(self.session_factory, self.artifact_root),
            )
            experiment_arguments = {}
            if pins.get("contentExperiment") is not None:
                from game_predictor_worker.training_core.grid_content_experiment import build_plan

                from game_predictor_api.domain.grid_content_experiment_inputs import require_inputs

                inputs = pins["contentExperimentInputs"]
                plan = build_plan(
                    base_version_id=preview["baseVersionId"],
                    base_manifest_sha256=pins["baseSha256"],
                    base_weights_sha256=next(
                        a["sha256"]
                        for a in pins["base"]["trainingArtifacts"]
                        if a["name"] == "weights.pt"
                    ),
                    cohorts=[
                        {
                            "gameId": str(game),
                            "cohortId": str(cohort_id),
                            "manifestSha256": header["manifestSha256"],
                        },
                        *pins["historicalCohorts"],
                    ],
                    train_eligibility_sha256=inputs["trainEligibility"]["sha256"],
                    selection_roster_sha256=inputs["selectionRoster"]["sha256"],
                    calibration_roster_sha256=inputs["calibrationRoster"]["sha256"],
                    regression_roster_sha256=inputs["regressionRoster"]["sha256"],
                    r3_admission_policy="human-labels-conditional-v1",
                    crop_policy_version="full-cell-v2",
                    export_evaluation_policy="full-a-content-v1",
                )
                require_inputs(inputs, plan)
                state["contentExperimentPlanSha256"] = plan["sha256"]
                experiment_arguments = {
                    "content_experiment": plan,
                    "content_experiment_inputs": inputs,
                }
            run = training.create(
                game,
                {
                    "idempotencyKey": str(child_key(job.id, "training")),
                    "cohortId": str(cohort_id),
                    "presetId": preview["presetId"],
                    "presetFingerprint": preview["presetFingerprint"],
                    "sharedCohorts": [
                        {"gameId": item["gameId"], "cohortId": item["cohortId"]}
                        for item in pins["historicalCohorts"]
                    ],
                },
                **({"correction_recipe": pins["rescueRecipe"]} if "rescueRecipe" in pins else {}),
                **(
                    {"private_learning": pins["privateLearning"]}
                    if "privateLearning" in pins
                    else {}
                ),
                **(
                    {"weight_initialization": pins["weightInitialization"]}
                    if "weightInitialization" in pins
                    else {}
                ),
                **experiment_arguments,
            )
        state["trainingRunId"] = run["runId"]
        if run["status"] != "completed":
            return self._waiting(state, run["runId"], run["status"], run.get("errorCode")), False
        if run["candidateVersionId"] is None:
            raise GridCohortError(
                "GRID_LEARNING_CANDIDATE_MISSING", "The completed run has no candidate."
            )
        state["candidateVersionId"] = run["candidateVersionId"]
        with Session(self.engine) as session, session.begin():
            self._lock_step(session, job.id)
            latest = self._job(session, game, job.id)
            if latest.cancel_requested_at is not None:
                return state, False
            evaluation = self.evaluations.create(
                {
                    "idempotencyKey": str(child_key(job.id, "evaluation")),
                    "versionId": run["candidateVersionId"],
                    "exclusions": preview["exclusions"],
                    "cohorts": [
                        {"gameId": str(game), "cohortId": str(cohort_id)},
                        *[
                            {"gameId": item["gameId"], "cohortId": item["cohortId"]}
                            for item in pins["historicalCohorts"]
                        ],
                    ],
                }
            )
        state.update(evaluationId=evaluation["evaluationId"], reportId=evaluation["reportId"])
        if evaluation["status"] != "completed":
            return self._waiting(
                state, evaluation["evaluationId"], evaluation["status"], evaluation.get("errorCode")
            ), False
        state.pop("waitingForJobId", None)
        state["verdict"] = evaluation["verdict"]
        return state, True

    @staticmethod
    def _lock_step(session: Session, identifier: UUID) -> None:
        try:
            session.execute(text("SET LOCAL lock_timeout='5s'"))
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"grid-learning-step:{identifier}"},
            )
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == "55P03":
                raise GridCohortError(
                    "GRID_LEARNING_BUSY",
                    "The workflow is committing a step; retry shortly.",
                ) from error
            raise

    @staticmethod
    def _waiting(
        state: dict[str, Any], identifier: str, status: str, code: str | None
    ) -> dict[str, Any]:
        if status not in {"created", "processing"}:
            raise GridCohortError(
                code or "GRID_LEARNING_CHILD_BLOCKED",
                "The original child needs attention; resume reuses its identity and budget.",
            )
        return {**state, "waitingForJobId": identifier}
