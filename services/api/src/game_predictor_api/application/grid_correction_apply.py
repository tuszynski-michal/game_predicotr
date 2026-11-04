"""Durable explicit apply: immutable preview pins and independently committed receipts.

Control commands retain their deterministic keys across crashes. The registry remains
the authority for publication, assignment CAS and current evidence; no rollback is
attempted when a later step fails.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, Uuid, column, select, table, text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.grid_correction_evaluation import PHOTO_ONLY_LIMITATIONS
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.grid_model_snapshots import uses_neural_grid
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job, requeue_job
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import JobModel

from .grid_correction_learning import GridCorrectionLearningService
from .grid_model_evaluation import GridModelEvaluationService, report_id_for
from .grid_model_registry import GridModelRegistryService

APPLY_KIND = "grid-correction-apply-v1"


def apply_key(identifier: UUID, kind: str, game: str | None = None) -> UUID:
    return uuid5(identifier, "grid-correction-apply:" + kind + (":" + game if game else ""))


def _error(code: str, message: str, status: int = 409) -> GridCohortError:
    return GridCohortError(code, message, status)


class GridCorrectionApplyService:
    def __init__(self, engine: Engine, session_factory: sessionmaker[Session], artifact_root: Path):
        self.engine, self.session_factory, self.artifact_root = (
            engine,
            session_factory,
            artifact_root,
        )
        self.evaluations = GridModelEvaluationService(engine, session_factory, artifact_root)

    def _registry(self, session: Session) -> GridModelRegistryService:
        return GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(self.artifact_root),
        )

    def _evidence(
        self, session: Session, registry: GridModelRegistryService, game: UUID, learning: UUID
    ) -> tuple[Job, dict[str, Any], dict[str, Any], Any]:
        parent = GridCorrectionLearningService._job(session, game, learning)
        state: Any = parent.checkpoint_payload or {}
        if parent.status != JobStatus.COMPLETED or not all(
            state.get(key) for key in ("candidateVersionId", "evaluationId", "reportId")
        ):
            raise _error(
                "GRID_APPLY_LEARNING_INCOMPLETE", "Complete the learning evaluation first."
            )
        evaluation = self.evaluations._job(session, UUID(state["evaluationId"]))
        if (
            evaluation.status != JobStatus.COMPLETED
            or str(report_id_for(evaluation.id)) != state["reportId"]
            or evaluation.input_payload.get("version_id") != state["candidateVersionId"]
        ):
            raise _error("GRID_APPLY_EVIDENCE_REQUIRED", "The original evaluation pins differ.")
        version = UUID(state["candidateVersionId"])
        view = registry.control._version(version)
        row, invalidated = registry.repository.evaluation(UUID(state["reportId"]))
        if row is None or invalidated:
            raise _error("GRID_MODEL_EVALUATION_STALE", "The original evidence is unavailable.")
        report = self.evaluations._report(session, row, job=evaluation)
        if report.get("schemaVersion") not in (
            "grid-model-evaluation-read-v3",
            "grid-model-evaluation-read-v4",
        ):
            raise _error(
                "GRID_APPLY_EVIDENCE_REQUIRED", "Photo-only correction evidence is required."
            )
        # This validates producer, checksum, recomputed gate and every current cohort.
        registry.control._evidence(view, UUID(state["reportId"]), None, publishing=True)
        return parent, view, report, row

    def _preview(
        self, session: Session, game: UUID, learning: UUID, additional: Sequence[UUID]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if len(additional) > 7 or len(set(additional)) != len(additional) or game in additional:
            raise _error("GRID_APPLY_SCOPE_INVALID", "Choose distinct additional games.", 422)
        parent = GridCorrectionLearningService._job(session, game, learning)
        state: Any = parent.checkpoint_payload or {}
        initial: Any = parent.input_payload["preview"]
        registry = self._registry(session)
        head = registry.repository.default()
        blockers: list[str] = []
        pins: dict[str, Any] = {}
        result: dict[str, Any] = {
            "gameId": str(game),
            "learningId": str(learning),
            "versionId": state.get("candidateVersionId"),
            "versionLabel": None,
            "baseVersionId": initial["baseVersionId"],
            "defaultRevision": 0 if head is None else head.revision,
            "defaultVersionId": None if head is None else str(head.version_id),
            "additionalGameIds": sorted(map(str, additional)),
            "requiredGameIds": [str(game)],
            "targets": [],
            "excludedGameIds": [entry["gameId"] for entry in initial["exclusions"]],
            "limitations": list(PHOTO_ONLY_LIMITATIONS),
            "evidenceLevel": "photo-only",
            "blockers": blockers,
            "canApply": False,
        }
        try:
            _, version, report, row = self._evidence(session, registry, game, learning)
            manifest = version["manifest"]
            result["versionLabel"] = manifest.get(
                "versionLabel", manifest.get("version", manifest["versionId"])
            )
            result["requiredGameIds"] = report["requiredGameIds"]
            if head is not None and str(head.version_id) == manifest["versionId"]:
                raise _error(
                    "GRID_APPLY_ALREADY_DEFAULT",
                    "The candidate is already the default; inspect or resume its apply history.",
                )
            if head is None or str(head.version_id) != initial["baseVersionId"]:
                raise _error(
                    "GRID_APPLY_DEFAULT_CHANGED",
                    "The learning base is no longer the global default; obtain fresh evidence.",
                )
            scope = {entry["gameId"]: entry for entry in report["cohorts"]}
            selected = [str(game), *result["additionalGameIds"]]
            if set(selected) - set(scope) or set(selected) & set(result["excludedGameIds"]):
                raise _error(
                    "GRID_APPLY_SCOPE_NOT_EVALUATED",
                    "Every selected game needs a pinned evaluated cohort.",
                )
            targets = []
            for target in selected:
                assignment, _ = registry.repository.assignment(UUID(target))
                games = table(
                    "games",
                    column("id", Uuid),
                    column("code"),
                    column("shape_geometry_configuration"),
                    schema="public",
                )
                catalogue_game = session.execute(
                    select(games).where(games.c.id == UUID(target))
                ).one()
                if catalogue_game.code == "7" or not uses_neural_grid(
                    catalogue_game.shape_geometry_configuration
                ):
                    raise _error("GRID_MODEL_GAME_INCOMPATIBLE", "A selected game is incompatible.")
                targets.append(
                    {
                        "gameId": target,
                        "gameLabel": str(catalogue_game.code),
                        "assignmentRevision": 0 if assignment is None else assignment.revision,
                        "assignedVersionId": None
                        if assignment is None
                        else str(assignment.version_id),
                        "requiresComparison": assignment is not None
                        and str(assignment.version_id) != initial["baseVersionId"],
                    }
                )
            result["targets"] = targets
            pins.update(
                versionId=manifest["versionId"],
                manifestSha256=version["manifestSha256"],
                reportId=str(row.id),
                reportSha256=row.report_sha256,
                evaluationId=state["evaluationId"],
                scope=report["scope"],
                cohorts=report["cohorts"],
            )
            self._publication_receipt(registry, pins, None)
            if self._active(session, game, learning) is not None:
                raise _error("GRID_APPLY_BUSY", "An apply operation is already active.")
        except (GridCohortError, GridModelRegistryError) as error:
            blockers.append(error.code)
        result["canApply"] = not blockers
        result["previewSha256"] = descriptor_sha256({"view": result, "pins": pins})
        return result, pins

    def preview(self, game: UUID, learning: UUID, additional: list[UUID]) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self._preview(session, game, learning, additional)[0]

    @staticmethod
    def _job(
        session: Session, game: UUID, learning: UUID, identifier: UUID, *, lock: bool = False
    ) -> Job:
        repository = SqlAlchemyJobRepository(session)
        job = repository.get_job_for_update(identifier) if lock else repository.get_job(identifier)
        if (
            job is None
            or job.job_type != JobType.GRID_CORRECTION_LEARNING
            or job.game_id != game
            or job.input_payload.get("learning_kind") != APPLY_KIND
            or job.input_payload.get("learning_id") != str(learning)
        ):
            raise _error("GRID_APPLY_NOT_FOUND", "Apply operation not found.", 404)
        return job

    @staticmethod
    def _by_key(session: Session, game: UUID, key: UUID) -> Job | None:
        row = session.scalar(
            select(JobModel).where(
                JobModel.game_id == game,
                JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
                JobModel.input_payload["learning_kind"].as_string() == APPLY_KIND,
                JobModel.input_payload["idempotency_key"].as_string() == str(key),
            )
        )
        return None if row is None else job_from_record(row)

    @staticmethod
    def _active(session: Session, game: UUID, learning: UUID) -> UUID | None:
        return session.scalar(
            select(JobModel.id)
            .where(
                JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
                JobModel.game_id == game,
                JobModel.input_payload["learning_kind"].as_string() == APPLY_KIND,
                JobModel.input_payload["learning_id"].as_string() == str(learning),
                JobModel.status.in_((JobStatus.CREATED, JobStatus.PROCESSING)),
            )
            .limit(1)
        )

    @staticmethod
    def _publication_receipt(
        registry: GridModelRegistryService, pins: Mapping[str, Any], key: UUID | None
    ) -> dict[str, Any] | None:
        """Adopt only the exact immutable publication proof; never publish twice.

        The deterministic receipt is checkpointed by the apply parent. A crash
        before that checkpoint can reconstruct it from the publication row.
        """
        publication = registry.repository.publication(UUID(pins["versionId"]))
        if publication is None:
            return None
        expected = {
            "kind": "evaluated_candidate",
            "evaluationId": pins["reportId"],
            "evaluationSha256": pins["reportSha256"],
            "manifestSha256": pins["manifestSha256"],
        }
        checksum = descriptor_sha256(expected)
        if (
            str(publication.evaluation_id) != pins["reportId"]
            or publication.evidence_json != canonical_json(expected)
            or publication.evidence_sha256 != checksum
        ):
            raise _error(
                "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT",
                "The candidate is published with different evidence.",
            )
        return {
            "kind": "already-published",
            "idempotencyKey": None if key is None else str(key),
            "gameId": None,
            "versionId": pins["versionId"],
            "evaluationId": pins["reportId"],
            "evaluationSha256": pins["reportSha256"],
            "manifestSha256": pins["manifestSha256"],
            "evidenceSha256": checksum,
        }

    @staticmethod
    def _steps(preview: Mapping[str, Any]) -> list[dict[str, Any]]:
        # Complete all assigned-baseline checks before changing any default or assignment.
        steps: list[dict[str, Any]] = []
        for target in preview["targets"]:
            if target["requiresComparison"]:
                steps.append(
                    {"kind": "comparison", "gameId": target["gameId"], "status": "pending"}
                )
        steps.extend(
            {"kind": kind, "gameId": None, "status": "pending"}
            for kind in ("publish", "set_default")
        )
        steps.extend(
            {"kind": "activate", "gameId": target["gameId"], "status": "pending"}
            for target in preview["targets"]
        )
        return steps

    def start(
        self, game: UUID, learning: UUID, command: Mapping[str, Any], actor: str
    ) -> dict[str, Any]:
        if command.get("confirmLimitedEvidence") is not True:
            raise _error(
                "GRID_APPLY_LIMITATIONS_CONFIRMATION_REQUIRED",
                "Confirm the photo-only evidence limitations.",
                422,
            )
        key, original = UUID(str(command["idempotencyKey"])), dict(command)
        with Session(self.engine) as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout='5s'"))
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"grid-correction-apply:{game}:{key}"},
            )
            existing = self._by_key(session, game, key)
            if existing is not None:
                if existing.input_payload["command"] != original or existing.input_payload[
                    "learning_id"
                ] != str(learning):
                    raise _error(
                        "GRID_APPLY_IDEMPOTENCY_CONFLICT",
                        "The key belongs to another apply command.",
                    )
                return self._view(session, existing)
            # Lock before rebuilding the preview so CAS covers the entire creation.
            self._registry(session).repository.lock()
            if self._active(session, game, learning) is not None:
                raise _error("GRID_APPLY_BUSY", "Resume the already active apply operation.")
            preview, pins = self._preview(
                session,
                game,
                learning,
                [UUID(str(item)) for item in command.get("additionalGameIds", [])],
            )
            if not preview["canApply"]:
                raise _error(preview["blockers"][0], "The apply preview has blockers.")
            if preview["previewSha256"] != command["previewSha256"]:
                raise _error(
                    "GRID_APPLY_PREVIEW_CHANGED", "Read and confirm a fresh apply preview."
                )
            payload = {
                "schema_version": 1,
                "learning_kind": APPLY_KIND,
                "idempotency_key": str(key),
                "learning_id": str(learning),
                "command": original,
                "preview": preview,
                "pins": pins,
                "actor": actor,
            }
            return self._view(
                session,
                SqlAlchemyJobRepository(session).add_job(
                    create_job(
                        JobType.GRID_CORRECTION_LEARNING, game_id=game, input_payload=payload
                    )
                ),
            )

    def list(self, game: UUID, learning: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            GridCorrectionLearningService._job(session, game, learning)
            rows = session.scalars(
                select(JobModel)
                .where(
                    JobModel.game_id == game,
                    JobModel.job_type == JobType.GRID_CORRECTION_LEARNING,
                    JobModel.input_payload["learning_kind"].as_string() == APPLY_KIND,
                    JobModel.input_payload["learning_id"].as_string() == str(learning),
                )
                .order_by(JobModel.created_at.desc())
                .limit(200)
            )
            return {"items": [self._view(session, job_from_record(row)) for row in rows]}

    def get(self, game: UUID, learning: UUID, identifier: UUID) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self._view(session, self._job(session, game, learning, identifier))

    def resume(self, game: UUID, learning: UUID, identifier: UUID, actor: str) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            GridCorrectionLearningService._lock_step(session, identifier)
            job = self._job(session, game, learning, identifier, lock=True)
            if job.status in {JobStatus.CREATED, JobStatus.PROCESSING, JobStatus.COMPLETED}:
                return self._view(session, job)
            if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
                raise _error(
                    "GRID_APPLY_NOT_RESUMABLE", "Only a failed or cancelled operation resumes."
                )
            registry = self._registry(session)
            registry.repository.lock()
            active = self._active(session, game, learning)
            if active is not None and active != job.id:
                raise _error("GRID_APPLY_BUSY", "Another apply operation is already active.")
            self._require_default(registry, job)
            # Keep child identity and comparison receipts after failure/restart.
            preview: Any = job.input_payload["preview"]
            for target in preview["targets"]:
                if not target["requiresComparison"]:
                    continue
                if (
                    registry.repository.control_receipt(
                        apply_key(job.id, "activate", target["gameId"]), UUID(target["gameId"])
                    )
                    is not None
                ):
                    continue
                self._require_assignment(registry, target)
                dependency = self.evaluations._by_key(
                    session, apply_key(job.id, "comparison", target["gameId"])
                )
                if dependency is not None and dependency.status in {
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                }:
                    SqlAlchemyJobRepository(session).save_job(requeue_job(dependency))
            return self._view(session, SqlAlchemyJobRepository(session).save_job(requeue_job(job)))

    def _view(self, session: Session, job: Job) -> dict[str, Any]:
        """Recover committed receipts in reads, even if a foreign head now blocks resume.

        The control transaction can commit immediately before the worker crashes.
        A GET must expose that partial success without advancing or writing the parent.
        """
        payload: Any = job.input_payload
        state: dict[str, Any] = dict(job.checkpoint_payload or {})
        steps = [dict(step) for step in state.get("steps", self._steps(payload["preview"]))]
        registry = self._registry(session)
        comparisons_complete = True
        for step in steps:
            if step["kind"] == "comparison":
                comparisons_complete = comparisons_complete and step["status"] == "completed"
                continue
            game = step["gameId"]
            receipt = registry.repository.control_receipt(
                apply_key(job.id, step["kind"], game), None if game is None else UUID(game)
            )
            if receipt is not None:
                value = json.loads(receipt.receipt_json)
                if (
                    value.get("versionId") != payload["preview"]["versionId"]
                    or value.get("kind") != step["kind"]
                    or value.get("gameId") != game
                ):
                    raise GridModelRegistryError(
                        "GRID_MODEL_REGISTRY_CORRUPT", "Apply receipt pins differ."
                    )
                step.update(status="completed", receipt=value)
            elif (
                step["kind"] == "publish" and step["status"] != "completed" and comparisons_complete
            ):
                try:
                    adopted = self._publication_receipt(
                        registry, payload["pins"], apply_key(job.id, "publish")
                    )
                except GridCohortError as error:
                    if error.code != "GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT":
                        raise
                    # A conflicting external publication blocks new commands,
                    # but must not hide this operation's earlier history.
                    continue
                if adopted is not None:
                    step.update(status="completed", receipt=adopted)
        state["steps"] = steps
        return self.view(replace(job, checkpoint_payload=state))

    @classmethod
    def view(cls, job: Job) -> dict[str, Any]:
        payload: Any = job.input_payload
        state: Any = job.checkpoint_payload or {}
        return {
            "applyId": str(job.id),
            "gameId": str(job.game_id),
            "learningId": payload["learning_id"],
            "versionId": payload["preview"]["versionId"],
            "status": job.status.value,
            "stage": job.stage,
            "errorCode": job.error_code,
            "steps": state.get("steps", cls._steps(payload["preview"])),
            "createdAt": job.created_at.isoformat(),
            "updatedAt": job.updated_at.isoformat(),
        }

    @staticmethod
    def _require_default(registry: GridModelRegistryService, job: Job) -> None:
        preview: Any = job.input_payload["preview"]
        head = registry.repository.default()
        own = registry.repository.control_receipt(apply_key(job.id, "set_default"), None)
        # Receipt lookup also recovers the commit/checkpoint crash gap.
        receipt = None if own is None else json.loads(own.receipt_json)
        revision = preview["defaultRevision"] if receipt is None else receipt["revision"]
        version = preview["defaultVersionId"] if receipt is None else preview["versionId"]
        if head is None or head.revision != revision or str(head.version_id) != version:
            raise _error(
                "GRID_APPLY_DEFAULT_CHANGED", "The global default changed; obtain a new preview."
            )

    @staticmethod
    def _require_assignment(registry: GridModelRegistryService, target: Mapping[str, Any]) -> None:
        assignment, _ = registry.repository.assignment(UUID(target["gameId"]))
        revision = 0 if assignment is None else assignment.revision
        version = None if assignment is None else str(assignment.version_id)
        if revision != target["assignmentRevision"] or version != target["assignedVersionId"]:
            raise _error(
                "GRID_APPLY_ASSIGNMENT_CHANGED",
                "A selected game's assignment changed; obtain a new preview.",
            )

    def _comparison(
        self, job: Job, target: Mapping[str, Any], pins: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload: Any = job.input_payload
        cohort = next(pin for pin in pins["cohorts"] if pin["gameId"] == target["gameId"])
        evaluation = self.evaluations.create_assigned_comparison(
            {
                "idempotencyKey": str(apply_key(job.id, "comparison", target["gameId"])),
                "versionId": payload["preview"]["versionId"],
                "gameId": target["gameId"],
                "cohortId": cohort["cohortId"],
            }
        )
        return evaluation

    def _require_comparison(
        self,
        session: Session,
        registry: GridModelRegistryService,
        identifier: UUID,
        target: Mapping[str, Any],
        pins: Mapping[str, Any],
    ) -> dict[str, Any]:
        child = self.evaluations._job(session, identifier)
        payload: Any = child.input_payload
        cohort = next(pin for pin in pins["cohorts"] if pin["gameId"] == target["gameId"])
        if (
            child.status != JobStatus.COMPLETED
            or payload.get("evaluation_kind") != "grid-assigned-comparison-v1"
            or payload.get("baseline_version_id") != target["assignedVersionId"]
            or payload.get("assignment_revision") != target["assignmentRevision"]
        ):
            raise _error(
                "GRID_APPLY_ASSIGNED_EVIDENCE_REQUIRED",
                "The actual-assigned comparison pins differ.",
            )
        row, invalidated = registry.repository.evaluation(report_id_for(identifier))
        if row is None or invalidated:
            raise _error("GRID_MODEL_EVALUATION_STALE", "The assigned comparison is unavailable.")
        report = self.evaluations._report(session, row, job=child)
        if (
            descriptor_sha256(report) != row.report_sha256
            or report["verdict"] != "PASS"
            or report["versionId"] != job_version_from_pin(pins, payload)
            or str(row.version_id) != pins["versionId"]
            or report["cohort"] != cohort
        ):
            raise _error(
                "GRID_APPLY_ASSIGNED_NONREGRESSION_REQUIRED",
                "The trusted assigned comparison must pass.",
            )
        registry.control._require_current(row.id, [cohort])
        return {
            "evaluationId": str(identifier),
            "reportId": str(row.id),
            "reportSha256": row.report_sha256,
        }

    def advance(self, job: Job) -> tuple[dict[str, Any], bool]:
        payload: Any = job.input_payload
        preview, pins = payload["preview"], payload["pins"]
        state: dict[str, Any] = dict(job.checkpoint_payload or {})
        state.setdefault("steps", self._steps(preview))
        state["steps"] = [dict(step) for step in state["steps"]]
        step = next((step for step in state["steps"] if step["status"] != "completed"), None)
        if step is None:
            state.pop("waitingForJobId", None)
            return state, True
        kind, target_game = step["kind"], step["gameId"]
        target = next((item for item in preview["targets"] if item["gameId"] == target_game), None)
        # Comparison creation has its own durable transaction and must never hold
        # the catalogue lock while awaiting its child. All mutations below recheck CAS.
        if kind == "comparison":
            assert target is not None
            with Session(self.engine) as session, session.begin():
                registry = self._registry(session)
                registry.repository.lock()
                self._require_default(registry, job)
                self._require_assignment(registry, target)
                self._publication_receipt(registry, pins, None)
            evaluation = self._comparison(job, target, pins)
            state["waitingForJobId"] = evaluation["evaluationId"]
            step["status"] = "waiting"
            if evaluation["status"] != "completed":
                if evaluation["status"] not in {"created", "processing"}:
                    raise _error(
                        evaluation.get("errorCode") or "GRID_APPLY_COMPARISON_BLOCKED",
                        "Resume the original comparison after failure.",
                    )
                return state, False
            with Session(self.engine) as session, session.begin():
                registry = self._registry(session)
                registry.repository.lock()
                self._require_default(registry, job)
                self._require_assignment(registry, target)
                step["receipt"] = self._require_comparison(
                    session, registry, UUID(evaluation["evaluationId"]), target, pins
                )
            step["status"] = "completed"
            state.pop("waitingForJobId", None)
            return state, False
        with Session(self.engine) as session, session.begin():
            registry = self._registry(session)
            registry.repository.lock()
            self._require_default(registry, job)
            # Revalidate the original immutable publication report, never replace it
            # with the independently produced actual-assigned report.
            _, version, report, row = self._evidence(
                session, registry, UUID(str(job.game_id)), UUID(payload["learning_id"])
            )
            if (
                version["manifestSha256"] != pins["manifestSha256"]
                or row.report_sha256 != pins["reportSha256"]
                or str(row.id) != pins["reportId"]
                or report["scope"] != pins["scope"]
                or report["cohorts"] != pins["cohorts"]
            ):
                raise _error(
                    "GRID_APPLY_EVIDENCE_CHANGED", "The pinned publication evidence changed."
                )
            key = apply_key(job.id, kind, target_game)
            prior = registry.repository.control_receipt(
                key, None if target_game is None else UUID(target_game)
            )
            publication = self._publication_receipt(registry, pins, key)
            if kind == "activate" and prior is None:
                assert target is not None
                self._require_assignment(registry, target)
                if target["requiresComparison"]:
                    comparison = next(
                        item
                        for item in state["steps"]
                        if item["kind"] == "comparison" and item["gameId"] == target_game
                    )
                    self._require_comparison(
                        session, registry, UUID(comparison["receipt"]["evaluationId"]), target, pins
                    )
            if kind == "publish":
                expected = 0
            elif kind == "set_default":
                expected = preview["defaultRevision"]
            else:
                assert target is not None
                expected = target["assignmentRevision"]
            if kind == "publish" and prior is None and publication is not None:
                step["receipt"] = publication
            else:
                step["receipt"] = registry.control.execute(
                    kind=kind,
                    key=key,
                    expected_revision=expected,
                    version_id=UUID(preview["versionId"]),
                    actor=payload["actor"],
                    game_id=None if target_game is None else UUID(target_game),
                    evaluation_id=UUID(pins["reportId"]) if kind == "publish" else None,
                )
        step["status"] = "completed"
        state.pop("waitingForJobId", None)
        return state, all(item["status"] == "completed" for item in state["steps"])


def job_version_from_pin(pins: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    """The comparison candidate descriptor must match the original apply pin."""
    if (
        payload.get("manifest_sha256") != pins["manifestSha256"]
        or payload.get("version_id") != pins["versionId"]
    ):
        raise _error("GRID_APPLY_ASSIGNED_EVIDENCE_REQUIRED", "The comparison candidate differs.")
    return str(pins["versionId"])
