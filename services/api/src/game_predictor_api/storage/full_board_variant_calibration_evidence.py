"""Replay variant partitions against trusted frozen sources and physical input witnesses."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from game_predictor_api.domain.full_board_assessment_reference import FrozenAssessmentReferences
from game_predictor_api.domain.full_board_calibration import AssessedTarget
from game_predictor_api.domain.full_board_variant_calibration import (
    assess_variant_regression,
    build_variant_profile,
    build_variant_qualification,
    require_variant_plan,
    seal_variant_b,
)
from game_predictor_api.domain.full_board_variant_calibration_types import (
    VariantAutomaticCalibration,
)
from game_predictor_api.domain.full_board_variant_context import require_variant_context
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.storage.grid_content_bundle import read_content_bundle_bytes


def variant_report_allowed(
    root: Path | None, manifest: Mapping[str, Any], report: Mapping[str, Any]
) -> bool:
    values = [
        value
        for value in report.get("automaticCalibration", []) or []
        if value.get("version") == "full-board-calibration-qualification-v3"
    ]
    if not values:
        return False
    if root is None or report.get("schemaVersion") != "grid-model-evaluation-read-v6":
        raise ValueError("VARIANT_CALIBRATION_CONTENT_DISPATCH_REQUIRED")
    from game_predictor_worker.images.full_board_variant_context import manifest_variant_contexts

    try:
        contexts = manifest_variant_contexts(root, manifest)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("VARIANT_FROZEN_CONTEXT_UNAVAILABLE") from error
    if any(value["allowedVariants"] != contexts for value in values):
        raise ValueError("VARIANT_FROZEN_CONTEXT_CHANGED")
    return True


def observation_verifier(
    snapshot: Any, expected_contexts: Sequence[Mapping[str, Any]]
) -> Callable[[str, Mapping[str, Any], Sequence[Mapping[str, Any]]], None]:
    from game_predictor_worker.images.full_board_variant_context import verify_variant_witness
    from game_predictor_worker.images.grid_cohort_dataset import (
        GridAssessmentDataset,
        GridBoardDataset,
    )

    contexts = sorted(
        [require_variant_context(c) for c in expected_contexts], key=lambda c: c["sha256"]
    )
    by_key = {c["sha256"]: c for c in contexts}
    populations = {
        "A": {s["sourceId"]: s for s, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()},
        "B": {s["sourceId"]: s for s, _ in GridAssessmentDataset(snapshot, "VALIDATION").indexed()},
        "REGRESSION": {
            s["sourceId"]: s for s, _ in GridAssessmentDataset(snapshot, "REGRESSION").indexed()
        },
    }

    def verify(role: str, prepared: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
        if prepared["allowedVariants"] != contexts:
            raise ValueError("VARIANT_FROZEN_CONTEXT_CHANGED")
        for row in rows:
            source_id = row["sourceId"] if role == "A" else row["target"]["sourceId"]
            source = populations[role][source_id]
            target = next(
                t for t in source["targets"] if t["positionIndex"] == row["target"]["positionIndex"]
            )
            if (
                row["target"]["sourceRepresentativeSha256"]
                != source["sourceIdentity"]["normalized_pixel_checksum_sha256"]
            ):
                raise ValueError("VARIANT_SOURCE_IDENTITY_CHANGED")
            if row["variantKey"] is None:
                continue
            verify_variant_witness(
                snapshot,
                source,
                target,
                row["witness"],
                by_key[row["variantKey"]],
                role="REGRESSION" if role == "REGRESSION" else "VALIDATION",
                validation_purpose=None if role == "REGRESSION" else role,
            )

    return verify


def require_variant_plan_scope(
    prepared: Mapping[str, Any], frozen: FrozenAssessmentReferences
) -> None:
    plan = require_variant_plan(prepared)
    if (
        plan.gameId != frozen.game_id
        or plan.cohortId != frozen.cohort_id
        or plan.cohortManifestSha256 != frozen.manifest_sha256
        or plan.roleProofSha256 != frozen.role_proof_sha256
        or plan.referenceAssessmentSha256 != frozen.references["A"]
        or plan.bAssessmentSha256 != frozen.references["B"]
        or plan.regressionAssessmentSha256 != frozen.references["REGRESSION"]
        or plan.bTargets != len(frozen.targets["B"])
        or plan.regressionTargets != len(frozen.targets["REGRESSION"])
        or plan.bSources != frozen.source_counts["B"]
        or plan.regressionSources != frozen.source_counts["REGRESSION"]
    ):
        raise ValueError("VARIANT_FROZEN_PLAN_CHANGED")
    actual = sorted(
        (str(r.sourceId), r.target.sourceRepresentativeSha256, r.target.positionIndex)
        for r in plan.selectionReferences
    )
    expected = sorted((source, sha, slot) for source, sha, slot, _ in frozen.targets["A"])
    if actual != expected:
        raise ValueError("VARIANT_FROZEN_A_TARGET_SET_CHANGED")
    if frozen.variant_observation_verifier is None:
        raise ValueError("VARIANT_TRUSTED_SOURCE_CONTEXT_REQUIRED")
    frozen.variant_observation_verifier("A", prepared, prepared["selectionReferences"])


def require_variant_calibration_evidence(
    root: Path,
    value: dict[str, Any],
    *,
    frozen: FrozenAssessmentReferences,
    candidate_sha: str,
    baseline_sha: str,
) -> dict[str, Any]:
    parsed = VariantAutomaticCalibration.model_validate(value)
    if parsed.evidence is None:
        raise ValueError("VARIANT_CALIBRATION_EVIDENCE_REQUIRED")
    path = (root / parsed.evidence.path).resolve()
    if not path.is_relative_to((root / "grid-model-evaluations").resolve()):
        raise ValueError("CALIBRATION_EVIDENCE_PATH_OR_SIZE")
    content = read_content_bundle_bytes(path, limit=96 * 1024 * 1024)
    if hashlib.sha256(content).hexdigest() != parsed.evidence.sha256:
        raise ValueError("CALIBRATION_EVIDENCE_CHECKSUM")
    envelope = json.loads(content)
    if set(envelope) != {"payload", "sha256"} or envelope["sha256"] != digest(envelope["payload"]):
        raise ValueError("CALIBRATION_EVIDENCE_CHECKSUM")
    body = envelope["payload"]
    if (
        set(body) != {"version", "plan", "b", "regressionTargets", "result", "profile"}
        or body["version"] != "full-board-variant-calibration-evidence-v1"
    ):
        raise ValueError("VARIANT_EVIDENCE_INVALID")
    prepared = body["plan"]
    require_variant_plan_scope(prepared, frozen)
    if (
        prepared["candidateManifestSha256"] != candidate_sha
        or prepared["baselineManifestSha256"] != baseline_sha
    ):
        raise ValueError("CALIBRATION_RECOGNITION_PLAN_CHANGED")
    seen_sources = []
    for role, rows in (("B", body["b"]["observations"]), ("REGRESSION", body["regressionTargets"])):
        targets = [AssessedTarget.model_validate(row["target"]) for row in rows]
        frozen.require_targets(role, targets)
        assert frozen.variant_observation_verifier is not None
        frozen.variant_observation_verifier(role, prepared, rows)
        seen_sources.append({target.sourceRepresentativeSha256 for target in targets})
    if seen_sources[0] & seen_sources[1]:
        raise ValueError("CALIBRATION_B_REG_ALIAS_CONFLICT")
    sealed = seal_variant_b(prepared, body["b"]["observations"])
    result = assess_variant_regression(prepared, sealed, body["regressionTargets"])
    profile = build_variant_profile(prepared, sealed, result)
    expected = build_variant_qualification(
        prepared, sealed, result, parsed.evidence.model_dump(mode="json")
    )
    if (
        body["b"] != sealed
        or body["result"] != result
        or body["profile"] != profile
        or expected != value
    ):
        raise ValueError("VARIANT_EVIDENCE_VERDICT_CHANGED")
    return value
