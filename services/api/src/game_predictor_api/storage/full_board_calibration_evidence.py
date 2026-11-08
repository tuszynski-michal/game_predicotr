"""Verify sidecar observations named by the existing evaluator report, without inference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.domain.full_board_assessment_reference import FrozenAssessmentReferences
from game_predictor_api.domain.full_board_calibration import (
    AssessedTarget,
    assess_regression,
    seal_b,
)
from game_predictor_api.domain.full_board_calibration_report import AutomaticCalibration
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest


def load_frozen_assessment(
    session: Session, root: Path, report: dict[str, Any], game: UUID
) -> FrozenAssessmentReferences:
    """Use the report's current DB-bound cohort pin, never a sidecar-supplied path."""
    from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot

    from .grid_training_cohort_models import GridTrainingCohortModel

    pins = [entry for entry in report["cohorts"] if entry["gameId"] == str(game)]
    if len(pins) != 1:
        raise ValueError("CALIBRATION_FROZEN_COHORT_REQUIRED")
    pin = pins[0]
    row = session.get(GridTrainingCohortModel, (game, UUID(pin["cohortId"])))
    if (
        row is None
        or row.status != "frozen"
        or row.manifest_path is None
        or row.manifest_sha256 != pin["manifestSha256"]
    ):
        raise ValueError("CALIBRATION_FROZEN_COHORT_CHANGED")
    snapshot = GridCohortSnapshot(root, row.manifest_path, pin["manifestSha256"])
    if snapshot.manifest["gameId"] != str(game) or snapshot.manifest["cohortId"] != pin["cohortId"]:
        raise ValueError("CALIBRATION_FROZEN_COHORT_CHANGED")
    return snapshot_assessment_references(snapshot)


def snapshot_assessment_references(snapshot: Any) -> FrozenAssessmentReferences:
    """Project exact metadata through the same strict dataset adapters as the worker."""
    from game_predictor_worker.images.grid_cohort_dataset import (
        GridAssessmentDataset,
        GridBoardDataset,
    )

    if snapshot.manifest["policyVersion"] != "application-grid-corrections-v4":
        raise ValueError("CALIBRATION_PURPOSE_COHORT_REQUIRED")
    return FrozenAssessmentReferences.from_sources(
        snapshot.manifest,
        snapshot.manifest_sha256,
        {
            "A": [source for source, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()],
            "B": [source for source, _ in GridAssessmentDataset(snapshot, "VALIDATION").indexed()],
            "REGRESSION": [
                source for source, _ in GridAssessmentDataset(snapshot, "REGRESSION").indexed()
            ],
        },
    )


def require_calibration_evidence(
    root: Path,
    value: dict[str, Any],
    *,
    frozen: FrozenAssessmentReferences,
    candidate_sha: str,
    baseline_sha: str,
) -> dict[str, Any]:
    parsed = AutomaticCalibration.model_validate(value)
    if parsed.evidence is None:
        if parsed.state == "qualified":
            raise ValueError("CALIBRATION_EVIDENCE_REQUIRED")
        return value
    path = (root / parsed.evidence.path).resolve()
    if (
        not path.is_relative_to((root / "grid-model-evaluations").resolve())
        or path.stat().st_size > 96 * 1024 * 1024
    ):
        raise ValueError("CALIBRATION_EVIDENCE_PATH_OR_SIZE")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != parsed.evidence.sha256:
        raise ValueError("CALIBRATION_EVIDENCE_CHECKSUM")
    envelope = json.loads(content)
    if set(envelope) != {"payload", "sha256"} or envelope["sha256"] != digest(envelope["payload"]):
        raise ValueError("CALIBRATION_EVIDENCE_CHECKSUM")
    body = envelope["payload"]
    plan = frozen.require_plan(body["plan"])
    if plan.candidateManifestSha256 != candidate_sha or plan.baselineManifestSha256 != baseline_sha:
        raise ValueError("CALIBRATION_RECOGNITION_PLAN_CHANGED")
    b = [AssessedTarget.model_validate(item) for item in body["b"]["targets"]]
    regression = [AssessedTarget.model_validate(item) for item in body["regressionTargets"]]
    frozen.require_targets("B", b)
    frozen.require_targets("REGRESSION", regression)
    if {item.sourceRepresentativeSha256 for item in b} & {
        item.sourceRepresentativeSha256 for item in regression
    }:
        raise ValueError("CALIBRATION_B_REG_ALIAS_CONFLICT")
    sealed = seal_b(plan, b)
    result = assess_regression(plan, sealed, regression)
    if (
        body["b"]["sealed"] != sealed
        or body["b"]["planSha256"] != plan.sha256
        or body["roleProofSha256"] != frozen.role_proof_sha256
        or body["result"] != result
        or result["state"] != parsed.state
        or result["reasonCodes"] != parsed.reasonCodes
        or sealed["b"] != (None if parsed.b is None else parsed.b.model_dump())
        or result["regression"]
        != (None if parsed.regression is None else parsed.regression.model_dump())
        or plan.roleProofSha256 != parsed.roleProofSha256
        or plan.gameId != parsed.gameId
        or len(plan.menu) != parsed.plannedConfigurations
        or body["plan"]["plannedComparisons"] != parsed.plannedComparisons
    ):
        raise ValueError("CALIBRATION_EVIDENCE_VERDICT_CHANGED")
    if parsed.profile is not None:
        profile = parsed.profile.model_dump(mode="json")
        expected = {
            "version": "full-board-auto-profile-v2"
            if plan.version.endswith("-v2")
            else "full-board-auto-profile-v1",
            "gameId": str(plan.gameId),
            "candidateManifestSha256": plan.candidateManifestSha256,
            "planSha256": plan.sha256,
            "sealedSha256": sealed["sha256"],
            "routingSha256": plan.routingSha256,
            "configuration": sealed["configuration"],
            "gameLogAspectReference": body["plan"]["gameLogAspectReference"],
            "assessmentScope": "labelled_targets",
        }
        expected["sha256"] = digest(expected)
        if profile != expected or body["profile"] != expected:
            raise ValueError("CALIBRATION_EVIDENCE_PROFILE_CHANGED")
    return value
