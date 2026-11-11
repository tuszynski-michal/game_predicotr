"""Persistent corrections workflow. Reads never advance it; workers perform one step.

Every child command has a deterministic key. A lost response or a restarted parent
therefore adopts the same cohort/run/evaluation, including the original GPU budget.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, Uuid, column, select, table, text
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
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
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
from game_predictor_api.storage.grid_training_cohort_repository import (
    CohortDeadline,
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.grid_training_run_jobs import SqlAlchemyGridTrainingRunJobs
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import JobModel

from .grid_correction_history import verified_publication_scope
from .grid_model_evaluation import GridModelEvaluationService
from .grid_model_registry import GridModelRegistryService
from .grid_training_cohorts import GridTrainingCohortService
from .grid_training_runs import GridTrainingRunService
from .shared_grid_model_candidate import SharedGridCandidateService

LEARNING_KIND = "grid-correction-learning-v1"
ACTIVE = {JobStatus.CREATED, JobStatus.PROCESSING}


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

    def ready(self, game: UUID, *, recommend_training_mode: bool = False) -> dict[str, Any]:
        points = self.preview(game, {"importJobIds": [], "exclusions": []})
        if not recommend_training_mode:
            return points
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
                sources = table(
                    "source_images", column("game_id", Uuid), column("import_job_id", Uuid)
                )
                imports = sorted(
                    str(value)
                    for value in session.scalars(
                        select(sources.c.import_job_id)
                        .where(sources.c.game_id == game)
                        .distinct()
                        .limit(101)
                    )
                )
            if not imports or len(imports) > 100:
                raise GridCohortError(
                    "GRID_LEARNING_IMPORT_SCOPE_INVALID",
                    "Choose between one and 100 complete imports.",
                )
            options: dict[str, Any] = {}
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
            return imports, prepare_split(repository, game, imports, CohortDeadline(), **options)

    def _preview(
        self, game: UUID, command: Mapping[str, Any]
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
                default = repository.default()
                if default is None:
                    raise GridCohortError(
                        "GRID_LEARNING_DEFAULT_REQUIRED", "Choose a global default first."
                    )
                registry = GridModelRegistryService(
                    repository, GridModelArtifactInspector(self.artifact_root)
                )
                record = repository.version(default.version_id)
                if record is None:
                    raise GridCohortError(
                        "GRID_LEARNING_BASE_MISSING", "The default model is missing."
                    )
                base = registry.view(record, include_eligibility=True)
                if not base["available"]:
                    raise GridCohortError(
                        "GRID_LEARNING_BASE_UNAVAILABLE", "The default artifacts are unavailable."
                    )
                manifest = base["manifest"]
                history = verified_publication_scope(repository, default.version_id)
                # The artifact inspector verifies every listed training artifact's bytes.
                training = manifest.get("trainingArtifacts") or []
                if not {"weights.pt", "checkpoint.pt", "bundle.json", "preset.json"} <= {
                    item["name"] for item in training
                }:
                    raise GridCohortError(
                        "GRID_LEARNING_TRAINING_ARTIFACTS_REQUIRED",
                        "The base needs its original training artifacts.",
                    )
                pins.update(
                    base=manifest,
                    baseSha256=base["manifestSha256"],
                    defaultRevision=default.revision,
                )
                view.update(
                    baseVersionId=str(default.version_id),
                    baseManifestSha256=base["manifestSha256"],
                    defaultRevision=default.revision,
                    priorScopeDocumented=history["documented"],
                    priorGameIds=history["gameIds"],
                )
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
                    **({"base": manifest} if experiment is not None else {}),
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
                baseline_preset_sha = next(
                    item["sha256"]
                    for item in manifest["trainingArtifacts"]
                    if item["name"] == "preset.json"
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
                    manifest,
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
                    preset, summed_counts(summaries), rescue_variant=command.get("rescueVariant")
                )
                view["cost"] = cost_view(cost)
                if not cost.within_budget or cost.planned_steps < 1:
                    blockers.append("GRID_RUN_COHORT_COST_EXCEEDS_BUDGET")
        except (GridCohortError, GridModelRegistryError) as error:
            blockers.append(error.code)
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
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"grid-learning:{game}:{key}"},
            )
            existing = self._by_key(session, game, key)
            if existing is not None:
                if existing.input_payload["command"] != original:
                    raise GridCohortError(
                        "GRID_LEARNING_IDEMPOTENCY_CONFLICT", "The key belongs to another command."
                    )
                return self.view(existing)
            view, pins = self._preview(game, command)
            if not view["canStart"]:
                raise GridCohortError(view["blockers"][0], "The learning preview has blockers.")
            if view["previewSha256"] != command["previewSha256"]:
                raise GridCohortError(
                    "GRID_LEARNING_PREVIEW_CHANGED", "Read and confirm a fresh preview."
                )
            # Serialize against set_default until the parent command is committed.
            catalogue = SqlAlchemyGridModelRegistryRepository(session)
            catalogue.lock()
            default = catalogue.default()
            if (
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
            return {"items": [self.view(job_from_record(row)) for row in rows]}

    def get(self, game: UUID, identifier: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self.view(self._job(session, game, identifier))

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
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            self._lock_step(session, identifier)
            job = self._job(session, game, identifier, lock=True)
            if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
                raise GridCohortError(
                    "GRID_LEARNING_NOT_RESUMABLE", "Only a failed or cancelled workflow resumes."
                )
            repository = SqlAlchemyJobRepository(session)
            from game_predictor_api.storage.sequence_ownership_lock import (
                acquire_sequence_ownership_lock,
            )
            from game_predictor_api.storage.source_replacement_guards import require_cohort_sources

            acquire_sequence_ownership_lock(session, game_id=game)
            cohort = (job.checkpoint_payload or {}).get("cohortId")
            if cohort is not None:
                self._cohorts(session).repository.bind(game)
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
        preview: Any = job.input_payload["preview"]
        return {
            **(
                {
                    "contentExperiment": preview["contentExperiment"],
                    "contentExperimentPlanSha256": state.get("contentExperimentPlanSha256"),
                }
                if preview.get("contentExperiment") is not None
                else {}
            ),
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
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            service = self._cohorts(session)
            service.repository.bind(game)
            from game_predictor_api.storage.grid_training_cohort_models import (
                GridTrainingCohortModel,
            )

            row = session.get(GridTrainingCohortModel, (game, cohort_id))
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
                    "familyId": pins["base"]["familyId"],
                    "baseVersionId": preview["baseVersionId"],
                    "selector": {"importJobIds": preview["importJobIds"]},
                    "recordings": [],
                    "policyVersion": correction_policy_for_mode(
                        preview.get("trainingMode", "grid-only")
                    ),
                }
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
                else:
                    body["cursor"] = (
                        header["nextCaptureCursor"]
                        if kind == "prepare-page"
                        else header["nextMaterializationCursor"]
                    )
                service.command(game, cohort_id, kind, body, actor)
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
