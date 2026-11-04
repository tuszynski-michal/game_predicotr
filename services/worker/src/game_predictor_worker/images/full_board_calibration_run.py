"""Durable A/menu -> B/seal -> REG phases inside the existing evaluator job."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.full_board_assessment_reference import FrozenAssessmentReferences
from game_predictor_api.domain.full_board_calibration import (
    AssessedTarget,
    CalibrationPlan,
    ReferenceTarget,
    assess_regression,
    make_plan,
    seal_b,
)
from game_predictor_api.domain.full_board_calibration_report import (
    LIMITATIONS,
    AutomaticCalibration,
)
from game_predictor_api.domain.grid_model_registry import canonical_json
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest

from ..training_core.grid_correction_metrics import CorrectionControlPhoto, measure_role
from .full_board_calibration_observations import CalibrationObserver
from .full_board_completeness import calibration_routing_sha, log_aspect
from .grid_cohort_dataset import (
    GridAssessmentDataset,
    GridBoardDataset,
    GridCohortSnapshot,
    has_full_geometry,
)

MAX_EVIDENCE_BYTES = 96 * 1024 * 1024


class FullBoardCalibrationRun:
    def __init__(
        self,
        *,
        root: Path,
        job_id: UUID,
        snapshot: GridCohortSnapshot,
        candidate_sha: str,
        baseline_sha: str,
        engines: tuple[Any, Any],
        write: Callable[[Path, bytes], None],
    ) -> None:
        self.root, self.job_id, self.snapshot, self.write = root, job_id, snapshot, write
        self.game = str(snapshot.manifest["gameId"])
        self.engines, self.candidate_sha, self.baseline_sha = engines, candidate_sha, baseline_sha
        self.rows = {
            "A": GridBoardDataset(snapshot, "VALIDATION").indexed(),
            "B": GridAssessmentDataset(snapshot, "VALIDATION").indexed(),
            "REGRESSION": GridAssessmentDataset(snapshot, "REGRESSION").indexed(),
        }
        identities: dict[tuple[str, str], str] = {}
        components: dict[str, str] = {}
        pins = {item["sourceId"]: item for item in snapshot.manifest["photoSplit"]["sources"]}
        for role, rows in self.rows.items():
            for source, _ in rows:
                for key in ("checksum_sha256", "normalized_pixel_checksum_sha256"):
                    identity = key, source["sourceIdentity"][key]
                    if identities.get(identity, role) != role:
                        raise ValueError("CALIBRATION_ROLE_ALIAS_CONFLICT")
                    identities[identity] = role
                for component in pins[source["sourceId"]]["componentIds"]:
                    if components.get(component, role) != role:
                        raise ValueError("CALIBRATION_ROLE_COMPONENT_CONFLICT")
                    components[component] = role
        self.frozen = FrozenAssessmentReferences.from_sources(
            snapshot.manifest,
            snapshot.manifest_sha256,
            {role: [source for source, _ in rows] for role, rows in self.rows.items()},
        )
        self.references = self.frozen.references
        self.role_proof = self.frozen.role_proof_sha256
        aspects = [
            value
            for _, targets in self.rows["A"]
            for nodes, _ in targets
            if (value := log_aspect(nodes)) is not None
        ]
        self.aspect = float(np.median(aspects)) if aspects else None
        engine = engines[1]
        self.routing = getattr(engine, "routing", None)
        core = getattr(engine, "engine", engine)
        self.routing_sha = calibration_routing_sha(
            candidate_sha, core.settings.board, self.routing, getattr(engine, "path", None)
        )

    def observer(self, role: str) -> CalibrationObserver:
        key = "A" if role == "VALIDATION" else role
        return CalibrationObserver(
            game_id=self.game,
            sources={source["sourceId"]: source for source, _ in self.rows[key]},
            game_aspect=self.aspect,
            routing=self.routing,
        )

    def _path(self, phase: str) -> Path:
        return (
            self.root
            / "grid-model-evaluations"
            / str(self.job_id)
            / f"{self.game}-calibration-{phase}.json"
        )

    def _read(self, path: Path) -> dict[str, Any]:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("CALIBRATION_EVIDENCE_SIZE_LIMIT")
        value = json.loads(path.read_bytes())
        if value.get("sha256") != digest(value["payload"]):
            raise ValueError("CALIBRATION_EVIDENCE_CHECKSUM")
        payload = value["payload"]
        if not isinstance(payload, dict):
            raise ValueError("CALIBRATION_EVIDENCE_INVALID")
        return payload

    def _seal(self, phase: str, payload: dict[str, Any]) -> None:
        path = self._path(phase)
        if path.exists():
            if self._read(path) != payload:
                raise ValueError("CALIBRATION_PHASE_CONFLICT")
            return
        value = {"payload": payload, "sha256": digest(payload)}
        data = (canonical_json(value) + "\n").encode()
        if len(data) > MAX_EVIDENCE_BYTES:
            raise ValueError("CALIBRATION_EVIDENCE_SIZE_LIMIT")
        self.write(path, data)

    def _observations(self, role: str) -> list[AssessedTarget]:
        path = self.root / "grid-model-evaluations" / str(self.job_id) / f"{self.game}-{role}.json"
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("CALIBRATION_EVIDENCE_SIZE_LIMIT")
        document = json.loads(path.read_bytes())
        if document["gameId"] != self.game or document["jobId"] != str(self.job_id):
            raise ValueError("CALIBRATION_DETAIL_IDENTITY")
        observed = [
            AssessedTarget.model_validate(target)
            for row in document["photos"]
            for target in row["calibrationTargets"]
        ]
        self.frozen.require_targets("A" if role == "VALIDATION" else role, observed)
        return observed

    def prepare_b(self, before_photo: Callable[[int], None]) -> None:
        a = self._observations("VALIDATION")
        references = [
            ReferenceTarget(
                gameId=item.gameId,
                sourceRepresentativeSha256=item.sourceRepresentativeSha256,
                positionIndex=item.positionIndex,
                role="VALIDATION-A",
                humanGood=item.candidateGood,
                features=item.candidateFeatures,
            )
            for item in a
        ]
        plan = make_plan(
            references,
            game_id=UUID(self.game),
            candidate_sha=self.candidate_sha,
            baseline_sha=self.baseline_sha,
            routing_sha=self.routing_sha,
            role_proof_sha=self.role_proof,
            b_assessment_sha=self.references["B"],
            regression_assessment_sha=self.references["REGRESSION"],
        )
        planned_targets = sum(len(targets) for _, targets in self.rows["B"])
        # Durable before the first B image decode or NN call; no hidden truncation.
        self._seal(
            "plan",
            {
                "plan": plan.model_dump(mode="json"),
                "plannedConfigurations": len(plan.menu),
                "plannedComparisons": len(plan.menu) * planned_targets,
                "bTargets": planned_targets,
                "bSources": len(self.rows["B"]),
                "regressionTargets": len(self.frozen.targets["REGRESSION"]),
                "regressionSources": self.frozen.source_counts["REGRESSION"],
                "cohortId": str(self.frozen.cohort_id),
                "cohortManifestSha256": self.frozen.manifest_sha256,
                "gameLogAspectReference": self.aspect,
                "referenceAssessmentSha256": self.references["A"],
            },
        )
        if self._path("b").exists():
            self._require_b(plan)
            return
        photos = []
        for source, targets in self.rows["B"]:

            def load(source: dict[str, Any] = source) -> Any:
                return self.snapshot.frame(source, "VALIDATION", validation_purpose="B").rgb

            photos.append(
                CorrectionControlPhoto(
                    str(source["sourceId"]),
                    str(source["sourceId"]),
                    source["original"]["sha256"],
                    tuple(nodes for nodes, _ in targets),
                    load,
                    full_geometry=has_full_geometry(source),
                )
            )
        _, rows = measure_role(
            photos, *self.engines, before_photo=before_photo, observation=self.observer("B")
        )
        assessed = [
            AssessedTarget.model_validate(value)
            for row in rows
            for value in row["calibrationTargets"]
        ]
        self.frozen.require_targets("B", assessed)
        sealed = seal_b(plan, assessed)
        self._seal(
            "b",
            {
                "planSha256": plan.sha256,
                "targets": [item.model_dump(mode="json") for item in assessed],
                "sealed": sealed,
            },
        )

    def _require_b(self, plan: CalibrationPlan) -> dict[str, Any]:
        if self._require_plan(self._read(self._path("plan"))) != plan:
            raise ValueError("CALIBRATION_B_PLAN_CHANGED")
        body = self._read(self._path("b"))
        targets = [AssessedTarget.model_validate(value) for value in body["targets"]]
        self.frozen.require_targets("B", targets)
        if body["planSha256"] != plan.sha256 or seal_b(plan, targets) != body["sealed"]:
            raise ValueError("CALIBRATION_B_SEAL_CHANGED")
        return body

    def _require_plan(self, prepared: dict[str, Any]) -> CalibrationPlan:
        plan = self.frozen.require_plan(prepared)
        if (
            plan.candidateManifestSha256 != self.candidate_sha
            or plan.baselineManifestSha256 != self.baseline_sha
            or plan.routingSha256 != self.routing_sha
            or prepared["gameLogAspectReference"] != self.aspect
        ):
            raise ValueError("CALIBRATION_RECOGNITION_PLAN_CHANGED")
        return plan

    def finish(self) -> dict[str, Any]:
        prepared = self._read(self._path("plan"))
        plan = self._require_plan(prepared)
        b = self._require_b(plan)
        regression = self._observations("REGRESSION")
        if {item.sourceRepresentativeSha256 for item in regression} & {
            item["sourceRepresentativeSha256"] for item in b["targets"]
        }:
            raise ValueError("CALIBRATION_B_REG_ALIAS_CONFLICT")
        result = assess_regression(plan, b["sealed"], regression)
        profile = None
        if result["state"] == "qualified":
            profile = {
                "version": "full-board-auto-profile-v1",
                "gameId": self.game,
                "candidateManifestSha256": self.candidate_sha,
                "planSha256": plan.sha256,
                "sealedSha256": b["sealed"]["sha256"],
                "routingSha256": self.routing_sha,
                "configuration": b["sealed"]["configuration"],
                "gameLogAspectReference": self.aspect,
                "assessmentScope": "labelled_targets",
            }
            profile["sha256"] = digest(profile)
        self._seal(
            "final",
            {
                "plan": prepared,
                "b": b,
                "regressionTargets": [item.model_dump(mode="json") for item in regression],
                "result": result,
                "profile": profile,
                "roleProofSha256": self.role_proof,
            },
        )
        path = self._path("final")
        return AutomaticCalibration.model_validate(
            {
                "gameId": self.game,
                "state": result["state"],
                "reasonCodes": result["reasonCodes"],
                "b": b["sealed"]["b"],
                "regression": result["regression"],
                "profile": profile,
                "evidence": {
                    "path": path.relative_to(self.root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                },
                "plannedConfigurations": prepared["plannedConfigurations"],
                "plannedComparisons": prepared["plannedComparisons"],
                "roleProofSha256": self.role_proof,
                "limitations": LIMITATIONS,
            }
        ).model_dump(mode="json")
