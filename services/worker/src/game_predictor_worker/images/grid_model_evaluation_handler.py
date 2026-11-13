"""Durable ``grid_model_evaluation`` job: measure, report and prove (TASK-0997, D-559).

One unit is one (game, control role). Each unit loads the game's frozen snapshot,
runs the pinned base and candidate ONNX bundles on CPU on identical frames, writes a
per-photo detail file atomically and checkpoints its summary; a restart skips finished
units and rebuilds the byte-identical report. The report is written once under the
job's deterministic identity, then every game is proven in its own transaction.
Cancellation is honoured between photos. The trainer and its checkpoint selection are
not involved: this job only reads already exported models.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from game_predictor_api.application.grid_model_evaluation import (
    bundle_sha256,
    candidate_parity,
    cohort_pins,
    report_id_for,
)
from game_predictor_api.domain import grid_correction_evaluation as corrections
from game_predictor_api.domain.grid_correction_policy import CORRECTION_EVALUATION
from game_predictor_api.domain.grid_model_evaluation import (
    EVALUATION_KIND,
    MODES,
    ROLES,
    build_report,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.jobs import Job, JobType

from ..jobs.runtime import JobExecutionContext, JobHandlerError
from ..training_core.grid_correction_metrics import CorrectionControlPhoto
from ..training_core.grid_correction_metrics import measure_role as measure_corrections
from ..training_core.grid_evaluation import ControlPhoto, Engine, measure_role
from .grid_cohort_dataset import (
    GridAssessmentDataset,
    GridBoardDataset,
    GridCohortDatasetError,
    GridCohortSnapshot,
    frame_rgb_and_box,
    has_full_geometry,
)

STAGE = "grid_model_evaluation"
DETAIL_SCHEMA = "grid-model-evaluation-detail-v1"
DETAIL_MAX_BYTES = 96 * 1024 * 1024
_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "evaluation_kind",
        "idempotency_key",
        "version_id",
        "manifest_sha256",
        "base_version_id",
        "base_manifest_sha256",
        "family_id",
        "training_game_id",
        "cohorts",
    }
)


class GridModelEvaluationStore(Protocol):
    def catalogue(
        self, version_id: UUID, base_version_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any], str]: ...
    def cohort(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]: ...
    def eligibility(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]: ...
    def recordings(self, game_id: UUID, cohort_id: UUID) -> dict[str, str]: ...
    def historical_cohort(self, base_version_id: UUID, header: Mapping[str, Any]) -> None: ...
    def store_report(
        self, report_id: UUID, version_id: UUID, report_json: str, report_sha256: str
    ) -> None: ...
    def prove(
        self, report_id: UUID, game_id: UUID, cohort_id: UUID, manifest_sha256: str
    ) -> None: ...


def detail_path(job_id: UUID, game_id: str, role: str) -> str:
    return f"grid-model-evaluations/{job_id}/{game_id}-{role}.json"


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    try:
        with staging.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _payload(job: Job) -> dict[str, Any]:
    payload = job.input_payload
    cohorts = payload.get("cohorts")
    expected = _PAYLOAD_KEYS
    if payload.get("evaluation_kind") == CORRECTION_EVALUATION:
        expected = expected | {"scope", "checkpoint_selection"}
    elif payload.get("evaluation_kind") == "grid-assigned-comparison-v1":
        expected = expected | {
            "baseline_version_id",
            "baseline_manifest_sha256",
            "assignment_revision",
            "comparison_command",
        }
    if (
        job.job_type is not JobType.GRID_MODEL_EVALUATION
        or job.game_id is None
        or payload.keys() != expected
        or payload.get("schema_version") != 1
        or payload.get("evaluation_kind")
        not in {EVALUATION_KIND, CORRECTION_EVALUATION, "grid-assigned-comparison-v1"}
        or not isinstance(cohorts, list)
        or not 1 <= len(cohorts) <= 100
        or payload.get("training_game_id") != str(job.game_id)
        or any(
            not isinstance(entry, dict)
            or entry.keys() != {"game_id", "cohort_id", "manifest_sha256"}
            for entry in cohorts
        )
        or [entry["game_id"] for entry in cohorts]
        != sorted({entry["game_id"] for entry in cohorts})
        or str(job.game_id) not in {entry["game_id"] for entry in cohorts}
    ):
        raise JobHandlerError("GRID_EVALUATION_INPUT_INVALID", "Pinned evaluation input differs.")
    return dict(payload)


class GridModelEvaluationJobHandler:
    def __init__(
        self,
        store: GridModelEvaluationStore,
        artifact_root: Path,
        *,
        threads: int = 4,
        engine_factory: Any = None,
    ) -> None:
        from .grid_rescue_assessment import load_assessment_engine

        self.store, self.artifact_root, self.threads = store, artifact_root.resolve(), threads
        self.engine_factory = engine_factory or (
            lambda directory, sha: load_assessment_engine(directory, sha, self.threads)
        )

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        try:
            self._run(context, job)
        except (GridCohortDatasetError, GridModelRegistryError) as error:
            raise JobHandlerError(error.code, str(error)) from error
        except ValueError as error:
            if str(error) == "NEURAL_GRID_BUNDLE_CHECKSUM_MISMATCH":
                raise JobHandlerError(str(error), "A pinned model bundle differs.") from error
            raise

    # -- state ---------------------------------------------------------------------------

    @staticmethod
    def _state(job: Job) -> dict[str, Any]:
        state = job.checkpoint_payload
        if not state:
            return {
                "schema_version": 1,
                "units": {},
                "verdict": None,
                "reportSha256": None,
                "proven": [],
            }
        if (
            not isinstance(state, dict)
            or state.get("schema_version") != 1
            or not isinstance(state.get("units"), dict)
            or not isinstance(state.get("proven"), list)
        ):
            raise JobHandlerError("GRID_EVALUATION_STATE_INVALID", "Evaluation state differs.")
        return dict(state)

    @staticmethod
    def _persist(context: JobExecutionContext, state: dict[str, Any], games: int) -> None:
        done = len(state["units"]) + int(state["reportSha256"] is not None) + len(state["proven"])
        context.checkpoint(
            checkpoint_payload=state,
            stage=STAGE,
            current=done,
            total=games * len(ROLES) + 1 + games,
            success_count=done,
            failure_count=0,
            review_count=0,
        )

    # -- measurement ---------------------------------------------------------------------

    def _engines(
        self, manifest: Mapping[str, Any], base: Mapping[str, Any]
    ) -> tuple[Engine, Engine]:
        def load(item: Mapping[str, Any]) -> Engine:
            directory = self.artifact_root / item["managedDirectory"]
            checksum = bundle_sha256(item)
            return cast(Engine, self.engine_factory(directory, checksum))

        return load(base), load(manifest)

    def _snapshot(
        self,
        game: UUID,
        cohort: UUID,
        pinned_sha: str,
        manifest: Mapping[str, Any],
        *,
        correction: bool = False,
    ) -> tuple[GridCohortSnapshot, str]:
        header = self.store.cohort(game, cohort)
        eligibility = self.store.eligibility(game, cohort)
        if (
            header["status"] != "frozen"
            or header["manifestSha256"] != pinned_sha
            or str(header["familyId"]) != manifest["familyId"]
            or (not correction and str(header["baseVersionId"]) != manifest["baseVersionId"])
        ):
            raise JobHandlerError("GRID_EVALUATION_COHORT_CHANGED", "Pinned cohort differs.")
        if correction and str(header["baseVersionId"]) != manifest["baseVersionId"]:
            self.store.historical_cohort(UUID(manifest["baseVersionId"]), header)
        if eligibility["qualification"] != "eligible":
            reasons = list(eligibility["reasons"])
            raise JobHandlerError(
                reasons[0] if reasons else "GRID_EVALUATION_COHORT_NOT_ELIGIBLE",
                "The cohort no longer qualifies for evaluation.",
            )
        snapshot = GridCohortSnapshot(self.artifact_root, header["manifestPath"], pinned_sha)
        frozen = snapshot.manifest
        if (
            frozen["gameId"] != str(game)
            or frozen["cohortId"] != str(cohort)
            or frozen["mode"] not in MODES
        ):
            raise JobHandlerError("GRID_EVALUATION_COHORT_CHANGED", "Snapshot identity differs.")
        return snapshot, str(frozen["mode"])

    @staticmethod
    def _photos(
        snapshot: GridCohortSnapshot,
        role: str,
        groups: Mapping[str, str],
        *,
        correction: bool = False,
    ) -> list[ControlPhoto]:
        photos = []
        dataset = (
            GridAssessmentDataset(snapshot, role)
            if correction
            and role == "REGRESSION"
            and snapshot.manifest["policyVersion"]
            in ("application-grid-corrections-v3", "application-grid-corrections-v4")
            else GridBoardDataset(snapshot, role)
        )
        for source, targets in dataset.indexed():
            source_id = str(source["sourceId"])
            group = groups.get(source_id)
            if group is None:
                raise JobHandlerError(
                    "GRID_EVALUATION_RECORDING_UNRESOLVED", "A control photo has no recording."
                )

            def load(source: dict[str, Any] = source) -> Any:
                return snapshot.frame(source, role).rgb

            def load_with_support(source: dict[str, Any] = source) -> Any:
                return frame_rgb_and_box(snapshot.frame(source, role))

            arguments = (
                source_id,
                group,
                str(source["original"]["sha256"]),
                tuple(nodes for nodes, _ in targets),
                load,
            )
            photos.append(
                CorrectionControlPhoto(
                    *arguments,
                    full_geometry=has_full_geometry(source),
                    load_with_support=load_with_support,
                )
                if correction
                else ControlPhoto(*arguments)
            )
        return photos

    def _measure_unit(
        self,
        context: JobExecutionContext,
        job: Job,
        state: dict[str, Any],
        games: int,
        entry: Mapping[str, str],
        role: str,
        snapshot: GridCohortSnapshot,
        groups: Mapping[str, str],
        engines: tuple[Engine, Engine],
        calibration: Any = None,
        production_content: Any = None,
    ) -> dict[str, Any]:
        def before_photo(_index: int) -> None:
            context.heartbeat()
            if context.job.cancel_requested_at is not None:
                # The checkpoint transition finalizes the cancellation and stops the run.
                self._persist(context, state, games)

        correction = job.input_payload.get("evaluation_kind") != EVALUATION_KIND
        photos = self._photos(snapshot, role, groups, correction=correction)
        if correction:
            summary, rows = measure_corrections(
                [photo for photo in photos if isinstance(photo, CorrectionControlPhoto)],
                *engines,
                before_photo=before_photo,
                observation=None if calibration is None else calibration.observer(role),
                content_observation=None
                if production_content is None
                else production_content.observer(role),
                cell_cut=job.input_payload.get("evaluation_kind") == CORRECTION_EVALUATION,
            )
        else:
            summary, rows = measure_role(photos, *engines, before_photo=before_photo)
        relative = detail_path(job.id, entry["game_id"], role)
        content = (
            canonical_json(
                {
                    "schemaVersion": DETAIL_SCHEMA,
                    "jobId": str(job.id),
                    "gameId": entry["game_id"],
                    "cohortId": entry["cohort_id"],
                    "role": role,
                    "photos": rows,
                }
            )
            + "\n"
        ).encode("utf-8")
        _write_atomic(self.artifact_root / relative, content)
        return {
            **summary,
            "detail": {"path": relative, "sha256": hashlib.sha256(content).hexdigest()},
        }

    def _verify_details(
        self,
        job: Job,
        state: Mapping[str, Any],
        cohorts: list[dict[str, str]],
        *,
        load_documents: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Bound each file before reading; final all-game verification retains no documents."""
        documents = {}
        for entry in cohorts:
            for role in ROLES:
                detail = state["units"][f"{entry['game_id']}:{role}"]["detail"]
                path = self.artifact_root / detail_path(job.id, entry["game_id"], role)
                try:
                    with path.open("rb") as stream:
                        if os.fstat(stream.fileno()).st_size > DETAIL_MAX_BYTES:
                            raise JobHandlerError(
                                "GRID_EVALUATION_DETAIL_TOO_LARGE",
                                "A per-photo result exceeds the bounded detail size.",
                            )
                        if load_documents:
                            payload = stream.read(DETAIL_MAX_BYTES + 1)
                            size = len(payload)
                            actual = hashlib.sha256(payload).hexdigest()
                        else:
                            size = 0
                            checksum = hashlib.sha256()
                            while chunk := stream.read(min(65536, DETAIL_MAX_BYTES + 1 - size)):
                                size += len(chunk)
                                checksum.update(chunk)
                                if size > DETAIL_MAX_BYTES:
                                    break
                            actual = checksum.hexdigest()
                        if size > DETAIL_MAX_BYTES:
                            raise JobHandlerError(
                                "GRID_EVALUATION_DETAIL_TOO_LARGE",
                                "A per-photo result grew beyond the bounded detail size.",
                            )
                except OSError as error:
                    raise JobHandlerError(
                        "GRID_EVALUATION_DETAIL_CHANGED",
                        "A per-photo result file is missing or differs; evaluate again.",
                    ) from error
                if (
                    detail["path"] != detail_path(job.id, entry["game_id"], role)
                    or actual != detail["sha256"]
                ):
                    raise JobHandlerError(
                        "GRID_EVALUATION_DETAIL_CHANGED",
                        "A per-photo result file is missing or differs; evaluate again.",
                    )
                if load_documents:
                    documents[f"{entry['game_id']}:{role}"] = json.loads(payload)
        return documents

    # -- run -----------------------------------------------------------------------------

    def _run(self, context: JobExecutionContext, job: Job) -> None:
        payload = _payload(job)
        assigned = payload["evaluation_kind"] == "grid-assigned-comparison-v1"
        state = self._state(job)
        cohorts = payload["cohorts"]
        manifest, base, base_sha = self.store.catalogue(
            UUID(payload["version_id"]),
            UUID(payload["baseline_version_id"] if assigned else payload["base_version_id"]),
        )
        if (
            descriptor_sha256(manifest) != payload["manifest_sha256"]
            or base_sha
            != (
                payload["baseline_manifest_sha256"] if assigned else payload["base_manifest_sha256"]
            )
            or manifest["familyId"] != payload["family_id"]
            or manifest["baseVersionId"] != payload["base_version_id"]
        ):
            raise JobHandlerError("GRID_EVALUATION_MODEL_CHANGED", "Pinned models differ.")
        parity = candidate_parity(self.artifact_root, manifest)
        correction = payload["evaluation_kind"] == CORRECTION_EVALUATION
        content_selection = False
        if correction:
            import json

            bundle_path = self.artifact_root / manifest["managedDirectory"] / "bundle.json"
            if manifest["modelVersion"] == "neural-grid-v2":
                from game_predictor_api.storage.grid_content_bundle import read_content_bundle

                bundle = read_content_bundle(bundle_path)
            else:
                bundle = json.loads(bundle_path.read_bytes())
            if "contentExperiment" in bundle.get("provenance", {}):
                from game_predictor_api.domain.grid_content_experiment_evidence import (
                    require_content_experiment_evidence,
                )

                require_content_experiment_evidence(bundle)
                content_selection = True
            if (
                bundle.get("provenance", {}).get("checkpointSelection")
                != payload["checkpoint_selection"]
            ):
                raise JobHandlerError(
                    "GRID_EVALUATION_SELECTION_CHANGED", "Pinned checkpoint policy differs."
                )
        engines: tuple[Engine, Engine] | None = None
        modes: dict[str, str] = dict(state.get("modes", {}))
        calibration_results = dict(state.get("automaticCalibration", {}))
        content_results = dict(state.get("productionContent", {}))
        for entry in cohorts:
            pending = [role for role in ROLES if f"{entry['game_id']}:{role}" not in state["units"]]
            if not pending and (not correction or entry["game_id"] in calibration_results):
                continue
            game, cohort = UUID(entry["game_id"]), UUID(entry["cohort_id"])
            snapshot, mode = self._snapshot(
                game, cohort, entry["manifest_sha256"], manifest, correction=correction or assigned
            )
            groups = self.store.recordings(game, cohort)
            modes[entry["game_id"]] = mode
            state["modes"] = modes
            engines = engines or self._engines(manifest, base)
            from .production_cell_run import ProductionContentRun, content_enabled

            production_content = (
                ProductionContentRun(snapshot) if correction and content_enabled(snapshot) else None
            )
            calibration = None
            if (
                correction
                and snapshot.manifest["policyVersion"] == "application-grid-corrections-v4"
            ):
                from .full_board_calibration_run import FullBoardCalibrationRun
                from .full_board_variant_calibration_run import VariantCalibrationRun

                calibration_class = (
                    VariantCalibrationRun if content_selection else FullBoardCalibrationRun
                )
                calibration = calibration_class(
                    root=self.artifact_root,
                    job_id=job.id,
                    snapshot=snapshot,
                    candidate_sha=payload["manifest_sha256"],
                    baseline_sha=base_sha,
                    engines=engines,
                    write=_write_atomic,
                )
            for role in pending:
                if calibration is not None and role == "REGRESSION":
                    calibration.prepare_b(lambda _index: context.heartbeat())
                state["units"][f"{entry['game_id']}:{role}"] = self._measure_unit(
                    context,
                    job,
                    state,
                    len(cohorts),
                    entry,
                    role,
                    snapshot,
                    groups,
                    engines,
                    calibration,
                    production_content,
                )
                self._persist(context, state, len(cohorts))
            if production_content is not None:
                verified = self._verify_details(job, state, [entry], load_documents=True)
                content_results[entry["game_id"]] = production_content.finish(
                    self.artifact_root,
                    job.id,
                    verified_details={
                        role: verified[f"{entry['game_id']}:{role}"] for role in ROLES
                    },
                )
                state["productionContent"] = content_results
                self._persist(context, state, len(cohorts))
            if calibration is not None:
                calibration.prepare_b(lambda _index: context.heartbeat())
                calibration_results[entry["game_id"]] = calibration.finish()
                state["automaticCalibration"] = calibration_results
                self._persist(context, state, len(cohorts))
        self._verify_details(job, state, cohorts)
        if calibration_results:
            from game_predictor_api.storage.full_board_calibration_evidence import (
                require_calibration_evidence,
                snapshot_assessment_references,
            )

            from .full_board_variant_context import manifest_variant_contexts
            from .production_cell_input import manifest_input_context
            from .production_cell_run import content_enabled

            for value in calibration_results.values():
                pins = [entry for entry in cohorts if entry["game_id"] == value["gameId"]]
                if len(pins) != 1:
                    raise ValueError("CALIBRATION_FROZEN_COHORT_REQUIRED")
                pin = pins[0]
                frozen, _ = self._snapshot(
                    UUID(pin["game_id"]),
                    UUID(pin["cohort_id"]),
                    pin["manifest_sha256"],
                    manifest,
                    correction=True,
                )
                require_calibration_evidence(
                    self.artifact_root,
                    value,
                    frozen=snapshot_assessment_references(
                        frozen,
                        input_context=(
                            manifest_input_context(self.artifact_root, manifest)
                            if content_enabled(frozen)
                            else None
                        ),
                        variant_contexts=(
                            manifest_variant_contexts(self.artifact_root, manifest)
                            if content_selection
                            else None
                        ),
                    ),
                    candidate_sha=payload["manifest_sha256"],
                    baseline_sha=base_sha,
                )
        arguments = dict(
            manifest=manifest,
            base_manifest_sha256=base_sha,
            training_game_id=payload["training_game_id"],
            parity=parity,
            cohorts=cohort_pins(payload),
            measured={
                entry["game_id"]: {
                    "mode": modes[entry["game_id"]],
                    "roles": {role: state["units"][f"{entry['game_id']}:{role}"] for role in ROLES},
                }
                for entry in cohorts
            },
        )
        if assigned:
            from game_predictor_api.domain.grid_assigned_comparison import (
                build_report as assigned_report,
            )

            game_id = payload["training_game_id"]
            report = assigned_report(
                manifest=manifest,
                baseline_manifest_sha256=base_sha,
                baseline_version_id=payload["baseline_version_id"],
                game_id=game_id,
                assignment_revision=payload["assignment_revision"],
                cohort=cohort_pins(payload)[0],
                measured=arguments["measured"][game_id],
                parity=parity,
            )
        elif correction:
            report = corrections.build_report(
                **arguments,
                scope=payload["scope"],
                checkpoint_selection=payload["checkpoint_selection"],
                allow_content_selection=content_selection,
            )
        else:
            report = build_report(**arguments)
        if correction and calibration_results:
            from game_predictor_api.domain.full_board_calibration_report import (
                attach_calibration,
                unqualified,
            )

            report = attach_calibration(
                report,
                [
                    calibration_results.get(game)
                    or unqualified(game, "CALIBRATION_PURPOSE_COHORT_REQUIRED")
                    for game in report["requiredGameIds"]
                ],
                allow_variant_calibration=content_selection,
            )
        if correction and content_results:
            from game_predictor_api.domain.production_cell_evaluation import attach_content

            from .production_cell_run import unavailable_content

            report = attach_content(
                report,
                [
                    content_results.get(game["gameId"]) or unavailable_content(game)
                    for game in report["games"]
                ],
            )
        report_json = canonical_json(report)
        sha = descriptor_sha256(report)
        if state["reportSha256"] not in (None, sha):
            raise JobHandlerError("GRID_EVALUATION_REPORT_CONFLICT", "The rebuilt report differs.")
        report_id = report_id_for(job.id)
        self.store.store_report(report_id, UUID(payload["version_id"]), report_json, sha)
        if state["reportSha256"] is None:
            state["reportSha256"], state["verdict"] = sha, report["verdict"]
            self._persist(context, state, len(cohorts))
        for entry in cohorts:
            if entry["game_id"] in state["proven"]:
                continue
            self.store.prove(
                report_id,
                UUID(entry["game_id"]),
                UUID(entry["cohort_id"]),
                entry["manifest_sha256"],
            )
            state["proven"].append(entry["game_id"])
            self._persist(context, state, len(cohorts))


__all__ = ["GridModelEvaluationJobHandler", "GridModelEvaluationStore", "detail_path"]
