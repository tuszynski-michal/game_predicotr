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
from game_predictor_api.domain.grid_correction_policy import CORRECTION_POLICY, CORRECTION_PRESET
from game_predictor_api.domain.grid_correction_split import correction_data_availability
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

from .grid_correction_history import verified_history
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
        self, engine: Engine, session_factory: sessionmaker[Session], artifact_root: Path
    ) -> None:
        self.engine, self.session_factory, self.artifact_root = (
            engine,
            session_factory,
            artifact_root,
        )
        self.evaluations = GridModelEvaluationService(engine, session_factory, artifact_root)

    def _cohorts(self, session: Session) -> GridTrainingCohortService:
        return GridTrainingCohortService(
            SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root), self.artifact_root
        )

    def ready(self, game: UUID) -> dict[str, Any]:
        return self.preview(game, {"importJobIds": [], "exclusions": []})

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

        preset = PRESETS[CORRECTION_PRESET]
        blockers: list[str] = []
        pins: dict[str, Any] = {}
        view: dict[str, Any] = {
            "gameId": str(game),
            "baseVersionId": None,
            "baseManifestSha256": None,
            "defaultRevision": None,
            "importJobIds": [],
            "roleCounts": [],
            "dataAvailability": None,
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
        try:
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
                history = verified_history(repository, default.version_id)
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
            if set(required) - {str(game), *(pin["gameId"] for pin in historic)}:
                raise GridCohortError(
                    "GRID_LEARNING_HISTORY_COHORT_REQUIRED",
                    "A required historical game has no pinned cohort.",
                )
            if len(historic) > 7:
                raise GridCohortError(
                    "GRID_SHARED_SCOPE_INVALID", "The approved shared-run limit is eight games."
                )
            view.update(historicalCohorts=historic, requiredGameIds=required)
            pins.update(scope=scope, historicalCohorts=historic)
            with game_storage_scope(game), self.session_factory() as session:
                cohort_repository = SqlAlchemyGridTrainingCohortRepository(
                    session, self.artifact_root
                )
                cohort_repository.bind(game)
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
                view["importJobIds"] = imports
                split = prepare_split(cohort_repository, game, imports, CohortDeadline())
            pins["splitSha256"] = split["sha256"]
            representatives = [item for item in split["sources"] if item["representative"]]
            view.update(
                dataAvailability=correction_data_availability(
                    sum(item["eligibleBoards"] > 0 for item in representatives),
                    sum(item["eligibleBoards"] for item in representatives),
                    "ready",
                ),
                roleCounts=split["roleCounts"],
                bufferPhotos=sum(bool(item["buffer"]) for item in split["sources"]),
            )
            summaries = [
                {
                    "mode": "grid-only",
                    "summary": {
                        "roles": [
                            {
                                "role": item["role"],
                                "eligibleBoards": item["boards"],
                                "eligiblePhotos": item["photos"],
                                "eligibleFullPhotos": 0,
                            }
                            for item in split["roleCounts"]
                        ]
                    },
                }
            ]
            shared = SharedGridCandidateService(self.session_factory, self.artifact_root)
            for pin in historic:
                header, eligibility, _ = shared._cohort(UUID(pin["gameId"]), UUID(pin["cohortId"]))
                if (
                    header["manifestSha256"] != pin["manifestSha256"]
                    or header["status"] != "frozen"
                    or header["mode"] != "grid-only"
                    or header["familyId"] != manifest["familyId"]
                    or eligibility["qualification"] != "eligible"
                ):
                    raise GridCohortError(
                        "GRID_LEARNING_HISTORY_UNAVAILABLE",
                        "A required historical cohort is unavailable or incompatible.",
                    )
                summaries.append(header)
            cost = estimate_cohort_cost(preset, summed_counts(summaries))
            view["cost"] = cost_view(cost)
            if not cost.within_budget or cost.planned_steps < 1:
                blockers.append("GRID_RUN_COHORT_COST_EXCEEDS_BUDGET")
        except (GridCohortError, GridModelRegistryError) as error:
            blockers.append(error.code)
            if isinstance(error, GridCorrectionSplitPreparationError):
                view["dataAvailability"] = error.data_availability
        except ValueError as error:
            # Pure scope validation failures are input errors, never undocumented narrowing.
            raise GridCohortError("GRID_LEARNING_SCOPE_INVALID", str(error), 422) from error
        view["canStart"] = not blockers
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
        cohort_id = uuid5(game, "grid-cohort:" + str(child_key(job.id, "cohort")))
        state["cohortId"] = str(cohort_id)
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            service = self._cohorts(session)
            service.repository.bind(game)
            from game_predictor_api.storage.grid_training_cohort_models import (
                GridTrainingCohortModel,
            )

            row = session.get(GridTrainingCohortModel, (game, cohort_id))
            if row is None:
                command = {
                    "idempotencyKey": str(child_key(job.id, "cohort")),
                    "mode": "grid-only",
                    "familyId": pins["base"]["familyId"],
                    "baseVersionId": preview["baseVersionId"],
                    "selector": {"importJobIds": preview["importJobIds"]},
                    "recordings": [],
                    "policyVersion": CORRECTION_POLICY,
                }
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
