"""Candidate-versus-base evaluation jobs, reports and cohort proofs (TASK-0997, D-559).

``create`` validates the candidate, its base and one frozen eligible cohort per game,
then queues one ``grid_model_evaluation`` job owned by the training game. The worker
measures, writes the v2 report and calls ``prove_cohort`` per game. ``prove_cohort``
is also the operator's currentness re-check: it reads the notice watermark first, then
the exact eligibility, binds the report to the game's cohort (replay on retry) and
appends a proof with the count read in step one. Each game uses its own transaction;
catalogue reads use a plain session.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.domain.grid_model_evaluation import (
    EVALUATION_KIND,
    PRODUCER,
    GridEvaluationReportError,
    require_report,
)
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.storage import grid_model_evaluation_repository as evidence
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import JobModel

EVALUATOR_ACTOR = PRODUCER
LIST_LIMIT = 200
_NAMESPACE = uuid5(NAMESPACE_URL, "https://game-predictor.local/grid-model-evaluation/v1")


def report_id_for(job_id: UUID) -> UUID:
    return uuid5(_NAMESPACE, f"report:{job_id}")


def binding_key(report_id: UUID, game_id: UUID) -> UUID:
    return uuid5(_NAMESPACE, f"binding:{report_id}:{game_id}")


def _error(code: str, message: str, status: int = 409) -> GridModelRegistryError:
    return GridModelRegistryError(code, message, status)


def bundle_sha256(manifest: Mapping[str, Any]) -> str:
    return str(next(file["sha256"] for file in manifest["files"] if file["name"] == "bundle.json"))


def candidate_parity(artifact_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Exported parity of the registered candidate bundle, bound to its pinned SHA."""
    path = artifact_root / manifest["managedDirectory"] / "bundle.json"
    try:
        content = path.read_bytes()
        bundle = json.loads(content)
    except (OSError, ValueError) as error:
        raise _error(
            "GRID_EVALUATION_CANDIDATE_UNAVAILABLE", "Candidate bundle is missing."
        ) from error
    if hashlib.sha256(content).hexdigest() != bundle_sha256(manifest):
        raise _error("GRID_EVALUATION_CANDIDATE_UNAVAILABLE", "Candidate bundle differs.")
    parity = bundle.get("parity") if isinstance(bundle, dict) else None
    return {
        "passed": isinstance(parity, dict) and parity.get("passed") is True,
        "bundleSha256": bundle_sha256(manifest),
    }


def prove_cohort(
    session_factory: sessionmaker[Session],
    artifact_root: Path,
    *,
    report_id: UUID,
    game_id: UUID,
    cohort_id: UUID,
    manifest_sha256: str,
    actor: str,
) -> dict[str, Any]:
    """Steps 1-4 of D-559 in one transaction of this game only.

    The proof also pins the game's active storage generation, so a later deletion or
    store change can never leave it current.
    """
    with game_storage_scope(game_id), session_factory() as session, session.begin():
        repository = SqlAlchemyGridTrainingCohortRepository(session, artifact_root)
        repository.bind(game_id)
        location = evidence.storage_location(session, game_id)
        if location is None or location["status"] != "active":
            raise GridCohortError(
                "GRID_EVALUATION_GAME_UNAVAILABLE", "The game store is not active.", 409
            )
        count = evidence.notice_count(session, game_id, cohort_id)
        service = GridTrainingCohortService(repository, artifact_root)
        eligibility = service.eligibility(game_id, cohort_id)
        row = repository.cohort(game_id, cohort_id)
        if row.status != "frozen" or row.manifest_sha256 != manifest_sha256:
            raise GridCohortError(
                "GRID_EVALUATION_COHORT_CHANGED", "The pinned frozen cohort differs."
            )
        if eligibility["qualification"] != "eligible":
            reasons = eligibility["reasons"]
            raise GridCohortError(
                reasons[0] if reasons else "GRID_EVALUATION_COHORT_NOT_ELIGIBLE",
                "The cohort no longer qualifies; no new proof is written.",
            )
        receipt = repository.recording_command(
            game_id,
            {
                "kind": "bind_existing_report",
                "idempotencyKey": str(binding_key(report_id, game_id)),
                "cohortId": str(cohort_id),
                "expectedRevision": row.revision,
                "manifestSha256": row.manifest_sha256,
                "reportId": str(report_id),
            },
            actor,
        )
        evidence.append_proof(
            session,
            report_id=report_id,
            game_id=game_id,
            cohort_id=cohort_id,
            manifest_sha256=manifest_sha256,
            count=count,
            storage_generation=int(location["generation"]),
            bind_receipt_sha256=descriptor_sha256(receipt),
            eligibility_sha256=descriptor_sha256(eligibility),
            actor=actor,
        )
        return {"gameId": str(game_id), "cohortId": str(cohort_id), "noticeCount": count}


class GridModelEvaluationService:
    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        *,
        prove: Callable[..., dict[str, Any]] = prove_cohort,
    ) -> None:
        self.engine, self.session_factory = engine, session_factory
        self.artifact_root, self.prove = artifact_root, prove

    # -- catalogue reads (plain session, no game route) --------------------------------

    def _registry(self, session: Session) -> GridModelRegistryService:
        return GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(self.artifact_root),
        )

    def _candidate(self, session: Session, version_id: UUID) -> tuple[dict[str, Any], str]:
        registry = self._registry(session)
        record = registry.repository.version(version_id)
        if record is None:
            raise _error("GRID_MODEL_VERSION_NOT_FOUND", "Version not found.", 404)
        view = registry.view(record, include_eligibility=False)
        manifest = view["manifest"]
        if (
            not view["available"]
            or manifest["admission"] != "not_evaluated"
            or manifest["baseVersionId"] is None
            or manifest["cohortId"] is None
        ):
            raise _error(
                "GRID_EVALUATION_CANDIDATE_UNAVAILABLE",
                "Only an available trained candidate with a base and cohort is evaluated.",
            )
        base = registry.repository.version(UUID(manifest["baseVersionId"]))
        if base is None or not registry.view(base, include_eligibility=False)["available"]:
            raise _error("GRID_EVALUATION_CANDIDATE_UNAVAILABLE", "The base model is unavailable.")
        return manifest, str(base.manifest_sha256)

    # -- per-game reads (one session and transaction per game) -------------------------

    def _cohort(
        self,
        game_id: UUID,
        cohort_id: UUID,
        manifest: Mapping[str, Any],
        *,
        correction: bool = False,
    ) -> str:
        with game_storage_scope(game_id), self.session_factory() as session, session.begin():
            service = GridTrainingCohortService(
                SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root),
                self.artifact_root,
            )
            header = service.get(game_id, cohort_id)
            if header["status"] != "frozen":
                raise GridCohortError("COHORT_NOT_FROZEN", "Only a frozen cohort is evaluated.")
            if str(header["familyId"]) != manifest["familyId"] or (
                not correction and str(header["baseVersionId"]) != manifest["baseVersionId"]
            ):
                raise GridCohortError(
                    "GRID_EVALUATION_COHORT_BASE_MISMATCH",
                    "Every cohort must share the candidate's family and base.",
                )
            if correction and str(header["baseVersionId"]) != manifest["baseVersionId"]:
                from .grid_correction_history import require_historical_cohort

                with Session(self.engine) as catalogue:
                    require_historical_cohort(
                        SqlAlchemyGridModelRegistryRepository(catalogue),
                        UUID(manifest["baseVersionId"]),
                        header,
                    )
            eligibility = service.eligibility(game_id, cohort_id)
            if eligibility["qualification"] != "eligible":
                reasons = eligibility["reasons"]
                raise GridCohortError(
                    reasons[0] if reasons else "GRID_EVALUATION_COHORT_NOT_ELIGIBLE",
                    "The cohort does not qualify for evaluation.",
                )
            return str(header["manifestSha256"])

    def create(self, command: Mapping[str, Any]) -> dict[str, Any]:
        key = UUID(str(command["idempotencyKey"]))
        version_id = UUID(str(command["versionId"]))
        requested = [
            (UUID(str(entry["gameId"])), UUID(str(entry["cohortId"])))
            for entry in command["cohorts"]
        ]
        if (
            not 1 <= len(requested) <= 100
            or len({game for game, _ in requested}) != len(requested)
            or len({cohort for _, cohort in requested}) != len(requested)
        ):
            raise _error("GRID_EVALUATION_SCOPE_INVALID", "Choose one distinct cohort per game.")
        with Session(self.engine) as session:
            # A replay returns the original job before any current-state check.
            existing = self._by_key(session, key)
            if existing is not None:
                return self._replay(
                    existing, version_id, requested, command.get("exclusions") or []
                )
            manifest, base_sha256 = self._candidate(session, version_id)
            family = evidence.family_games(session, UUID(manifest["familyId"]))
            trained = self._trained_cohorts(session, manifest)
            try:
                run = session.get(JobModel, UUID(str(manifest["provenance"]["runId"])))
            except (ValueError, KeyError, TypeError):
                run = None
            correction = (
                run is not None and run.input_payload.get("preset_id") == "grid-corrections-v1"
            )
            history = None
            if correction:
                from .grid_correction_history import verified_history

                history = verified_history(
                    SqlAlchemyGridModelRegistryRepository(session), UUID(manifest["baseVersionId"])
                )
        absent = sorted(trained - {(str(game), str(cohort)) for game, cohort in requested})
        if absent:
            error = _error(
                "GRID_EVALUATION_GAME_COHORT_REQUIRED",
                "A shared candidate is evaluated on every cohort it was trained on.",
            )
            error.details = {"cohorts": [{"gameId": g, "cohortId": c} for g, c in absent]}
            raise error
        training = [game for game, cohort in requested if str(cohort) == manifest["cohortId"]]
        if len(training) != 1:
            raise _error(
                "GRID_EVALUATION_GAME_COHORT_REQUIRED", "The training cohort must be evaluated."
            )
        scope = None
        if correction:
            from game_predictor_api.domain.grid_correction_evaluation import require_scope

            assert history is not None
            scope, required = require_scope(
                {
                    "currentGameId": str(training[0]),
                    "trainingGameIds": sorted({str(training[0]), *(game for game, _ in trained)}),
                    "priorVerifiedGameIds": history["gameIds"],
                    "priorScopeDocumented": history["documented"],
                    "exclusions": list(command.get("exclusions") or []),
                }
            )
            family = set(required)
            if {str(game) for game, _ in requested} - family:
                raise _error(
                    "GRID_EVALUATION_SCOPE_INVALID",
                    "Cohorts must exactly match the declared required scope.",
                )
        elif command.get("exclusions"):
            raise _error(
                "GRID_EVALUATION_SCOPE_INVALID", "Legacy evaluations cannot narrow their scope."
            )
        missing = sorted(family - {str(game) for game, _ in requested})
        if missing:
            error = _error(
                "GRID_EVALUATION_GAME_COHORT_REQUIRED",
                "Every game of the candidate's family needs a cohort.",
            )
            error.details = {"gameIds": missing}
            raise error
        parity = candidate_parity(self.artifact_root, manifest)
        if not parity["passed"]:
            raise _error("GRID_EVALUATION_CANDIDATE_UNAVAILABLE", "Candidate parity did not pass.")
        cohorts = []
        for game, cohort in sorted(requested, key=lambda item: str(item[0])):
            sha = self._cohort(game, cohort, manifest, correction=correction)
            cohorts.append({"game_id": str(game), "cohort_id": str(cohort), "manifest_sha256": sha})
        payload: dict[str, object] = {
            "schema_version": 1,
            "evaluation_kind": EVALUATION_KIND,
            "idempotency_key": str(key),
            "version_id": str(version_id),
            "manifest_sha256": descriptor_sha256(manifest),
            "base_version_id": manifest["baseVersionId"],
            "base_manifest_sha256": base_sha256,
            "family_id": manifest["familyId"],
            "training_game_id": str(training[0]),
            "cohorts": cohorts,
        }
        if correction:
            from game_predictor_api.domain.grid_correction_evaluation import (
                require_checkpoint_selection,
            )
            from game_predictor_api.domain.grid_correction_policy import CORRECTION_EVALUATION

            bundle = json.loads(
                (self.artifact_root / manifest["managedDirectory"] / "bundle.json").read_bytes()
            )
            selection = require_checkpoint_selection(
                bundle.get("provenance", {}).get("checkpointSelection")
            )
            payload.update(
                evaluation_kind=CORRECTION_EVALUATION, scope=scope, checkpoint_selection=selection
            )
        game = training[0]
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            jobs = SqlAlchemyJobRepository(session)
            if session.get_bind().dialect.name == "postgresql":
                # Serialize every create with one key until this transaction ends.
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
                    {"name": f"grid-model-evaluation:{key}"},
                )
            existing = self._by_key(session, key)
            if existing is not None:
                return self._replay(
                    existing, version_id, requested, command.get("exclusions") or []
                )
            job = create_job(JobType.GRID_MODEL_EVALUATION, game_id=game, input_payload=payload)
            same = jobs.get_job_by_input_key(job.input_key)
            return self.view(same if same is not None else jobs.add_job(job))

    def _replay(
        self,
        job: Job,
        version_id: UUID,
        requested: Sequence[tuple[UUID, UUID]],
        exclusions: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        payload: dict[str, Any] = dict(job.input_payload)
        if (
            payload["version_id"] != str(version_id)
            or {(entry["game_id"], entry["cohort_id"]) for entry in payload["cohorts"]}
            != {(str(game), str(cohort)) for game, cohort in requested}
            or payload.get("scope", {}).get("exclusions", []) != list(exclusions)
        ):
            raise _error(
                "GRID_EVALUATION_IDEMPOTENCY_CONFLICT", "The key was used for another scope."
            )
        return self.view(job)

    def create_assigned_comparison(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Separate apply evidence pins the actual assignment without rewriting ancestry."""
        key, version, game, cohort = (
            UUID(str(command[name]))
            for name in ("idempotencyKey", "versionId", "gameId", "cohortId")
        )
        with Session(self.engine) as session:
            existing = self._by_key(session, key)
            if existing is not None:
                if existing.input_payload.get("comparison_command") != dict(command):
                    raise _error(
                        "GRID_EVALUATION_IDEMPOTENCY_CONFLICT",
                        "The key was used for another comparison.",
                    )
                return self.view(existing)
            registry = SqlAlchemyGridModelRegistryRepository(session)
            manifest, training_base_sha = self._candidate(session, version)
            assignment, revision = registry.assignment(game)
            if assignment is None:
                raise _error(
                    "GRID_ASSIGNED_BASELINE_REQUIRED", "The game has no actual assigned model."
                )
            baseline = registry.version(assignment.version_id)
            if (
                baseline is None
                or not self._registry(session).view(baseline, include_eligibility=False)[
                    "available"
                ]
            ):
                raise _error(
                    "GRID_ASSIGNED_BASELINE_UNAVAILABLE",
                    "The actual assigned model is unavailable.",
                )
            baseline_id, baseline_sha = str(baseline.id), baseline.manifest_sha256
        sha = self._cohort(game, cohort, manifest, correction=True)
        if not candidate_parity(self.artifact_root, manifest)["passed"]:
            raise _error("GRID_EVALUATION_CANDIDATE_UNAVAILABLE", "Candidate parity did not pass.")
        payload: dict[str, Any] = {
            "schema_version": 1,
            "evaluation_kind": "grid-assigned-comparison-v1",
            "idempotency_key": str(key),
            "version_id": str(version),
            "manifest_sha256": descriptor_sha256(manifest),
            "base_version_id": manifest["baseVersionId"],
            "base_manifest_sha256": training_base_sha,
            "baseline_version_id": baseline_id,
            "baseline_manifest_sha256": baseline_sha,
            "assignment_revision": revision,
            "comparison_command": dict(command),
            "family_id": manifest["familyId"],
            "training_game_id": str(game),
            "cohorts": [{"game_id": str(game), "cohort_id": str(cohort), "manifest_sha256": sha}],
        }
        with game_storage_scope(game), self.session_factory() as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name,0))"),
                {"name": f"grid-model-evaluation:{key}"},
            )
            existing = self._by_key(session, key)
            if existing is not None:
                if existing.input_payload.get("comparison_command") != dict(command):
                    raise _error(
                        "GRID_EVALUATION_IDEMPOTENCY_CONFLICT",
                        "The key was used for another comparison.",
                    )
                return self.view(existing)
            registry = SqlAlchemyGridModelRegistryRepository(session)
            registry.lock()
            assignment, actual_revision = registry.assignment(game)
            if (
                assignment is None
                or actual_revision != revision
                or str(assignment.version_id) != baseline_id
            ):
                raise _error(
                    "GRID_ASSIGNED_BASELINE_CHANGED",
                    "The assignment changed before comparison was queued.",
                )
            return self.view(
                SqlAlchemyJobRepository(session).add_job(
                    create_job(JobType.GRID_MODEL_EVALUATION, game_id=game, input_payload=payload)
                )
            )

    @staticmethod
    def _trained_cohorts(session: Session, manifest: Mapping[str, Any]) -> set[tuple[str, str]]:
        """Primary and shared cohorts of the training run that produced the candidate."""
        try:
            run = session.get(JobModel, UUID(str(manifest["provenance"]["runId"])))
        except (KeyError, ValueError):
            return set()
        if run is None or run.job_type != JobType.GRID_TRAINING:
            return set()
        payload: dict[str, Any] = dict(run.input_payload)
        if payload.get("training_kind") != "grid-shared-training-run-v1":
            return set()
        return {(str(run.game_id), str(payload["cohort_id"]))} | {
            (str(pin["game_id"]), str(pin["cohort_id"])) for pin in payload["shared_cohorts"]
        }

    @staticmethod
    def _by_key(session: Session, key: UUID) -> Job | None:
        record = session.scalar(
            select(JobModel)
            .where(
                JobModel.job_type == JobType.GRID_MODEL_EVALUATION,
                func.jsonb_extract_path_text(JobModel.input_payload, "idempotency_key") == str(key),
            )
            .limit(1)
        )
        return None if record is None else job_from_record(record)

    def _jobs(self, session: Session, version_id: UUID) -> list[Job]:
        records = session.scalars(
            select(JobModel)
            .where(
                JobModel.job_type == JobType.GRID_MODEL_EVALUATION,
                func.jsonb_extract_path_text(JobModel.input_payload, "version_id")
                == str(version_id),
            )
            .order_by(JobModel.created_at.desc())
            .limit(LIST_LIMIT)
        )
        return [job_from_record(record) for record in records]

    def list(self, version_id: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            return {"items": [self.view(job) for job in self._jobs(session, version_id)]}

    def _job(self, session: Session, evaluation_id: UUID) -> Job:
        record = session.get(JobModel, evaluation_id)
        if record is None or record.job_type != JobType.GRID_MODEL_EVALUATION:
            raise _error("GRID_EVALUATION_NOT_FOUND", "Evaluation does not exist.", 404)
        return job_from_record(record)

    def get(self, evaluation_id: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            job = self._job(session, evaluation_id)
            view = self.view(job)
            row = evidence.report(session, report_id_for(job.id))
            if row is None:
                return view
            report = self._report(session, row, job=job)
            view["report"] = report
            view["currentness"] = evidence.cohort_currentness(
                session, row.id, report_cohorts(report)
            )
            return view

    def _report(self, session: Session, row: Any, *, job: Job | None = None) -> dict[str, Any]:
        registry = SqlAlchemyGridModelRegistryRepository(session)
        record = registry.version(row.version_id)
        if record is None:
            raise _error("GRID_MODEL_REGISTRY_CORRUPT", "Evaluated version is missing.")
        manifest = json.loads(record.manifest_json)
        base = registry.version(UUID(manifest["baseVersionId"]))
        if base is None or row.producer != PRODUCER:
            raise _error("GRID_MODEL_REGISTRY_CORRUPT", "Evaluated base or producer differs.")
        try:
            if (
                json.loads(row.report_json).get("schemaVersion")
                == "grid-model-assigned-comparison-v1"
            ):
                from game_predictor_api.domain.grid_assigned_comparison import (
                    require_report as assigned_report,
                )

                if job is None:
                    job = next(
                        (
                            item
                            for item in self._jobs(session, row.version_id)
                            if report_id_for(item.id) == row.id
                        ),
                        None,
                    )
                if (
                    job is None
                    or job.input_payload.get("evaluation_kind") != "grid-assigned-comparison-v1"
                ):
                    raise GridEvaluationReportError("The comparison job is unavailable.")
                pin: Any = job.input_payload
                baseline = registry.version(UUID(pin["baseline_version_id"]))
                if baseline is None or baseline.manifest_sha256 != pin["baseline_manifest_sha256"]:
                    raise GridEvaluationReportError("The pinned assigned baseline differs.")
                return assigned_report(
                    row.report_json,
                    manifest=manifest,
                    baseline_sha256=baseline.manifest_sha256,
                    expected_baseline_version_id=pin["baseline_version_id"],
                    expected_game_id=pin["training_game_id"],
                    expected_assignment_revision=pin["assignment_revision"],
                    expected_cohort=cohort_pins(pin)[0],
                )
            reader = require_report
            if json.loads(row.report_json).get("schemaVersion") == "grid-model-evaluation-read-v3":
                from game_predictor_api.domain.grid_correction_evaluation import (
                    require_report as correction_report,
                )

                reader = correction_report
            return reader(row.report_json, manifest=manifest, base_sha256=base.manifest_sha256)
        except GridEvaluationReportError as error:
            raise _error("GRID_MODEL_REGISTRY_CORRUPT", str(error)) from error

    def verify_currentness(self, report_id: UUID, actor: str) -> dict[str, Any]:
        """Operator re-check: every game is proven again in its own transaction."""
        if not actor or len(actor) > 64:
            raise _error("GRID_EVALUATION_ACTOR_REQUIRED", "A trusted actor is required.", 403)
        with Session(self.engine) as session:
            row = evidence.report(session, report_id)
            if row is None:
                raise _error("GRID_EVALUATION_NOT_FOUND", "Report does not exist.", 404)
            report = self._report(session, row)
        failures: list[dict[str, str]] = []
        for entry in report_cohorts(report):
            try:
                self.prove(
                    self.session_factory,
                    self.artifact_root,
                    report_id=report_id,
                    game_id=UUID(entry["gameId"]),
                    cohort_id=UUID(entry["cohortId"]),
                    manifest_sha256=entry["manifestSha256"],
                    actor=actor,
                )
            except GridCohortError as error:
                if error.status == 503:
                    raise
                failures.append({"gameId": entry["gameId"], "code": error.code})
        with Session(self.engine) as session:
            states = evidence.cohort_currentness(session, report_id, report_cohorts(report))
        return {"reportId": str(report_id), "currentness": states, "failures": failures}

    @staticmethod
    def view(job: Job) -> dict[str, Any]:
        payload: dict[str, Any] = dict(job.input_payload)
        state = job.checkpoint_payload if isinstance(job.checkpoint_payload, dict) else {}
        return {
            "evaluationId": str(job.id),
            "reportId": str(report_id_for(job.id)),
            "status": job.status.value,
            "stage": job.stage,
            "versionId": payload["version_id"],
            "baseVersionId": payload["base_version_id"],
            "trainingGameId": payload["training_game_id"],
            "cohorts": [
                {"gameId": entry["game_id"], "cohortId": entry["cohort_id"]}
                for entry in payload["cohorts"]
            ],
            "progressCurrent": job.progress_current,
            "progressTotal": job.progress_total,
            "verdict": state.get("verdict"),
            "cancelRequested": job.cancel_requested_at is not None,
            "errorCode": job.error_code,
            "createdAt": job.created_at.isoformat(),
            "updatedAt": job.updated_at.isoformat(),
            "report": None,
            "currentness": [],
            "assignedBaselineVersionId": payload.get("baseline_version_id"),
            "assignmentRevision": payload.get("assignment_revision"),
        }


def cohort_pins(payload: Mapping[str, Any]) -> Sequence[Mapping[str, str]]:
    return [
        {
            "gameId": entry["game_id"],
            "cohortId": entry["cohort_id"],
            "manifestSha256": entry["manifest_sha256"],
        }
        for entry in payload["cohorts"]
    ]


def report_cohorts(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return (
        [dict(report["cohort"])]
        if report.get("schemaVersion") == "grid-model-assigned-comparison-v1"
        else list(report["cohorts"])
    )
