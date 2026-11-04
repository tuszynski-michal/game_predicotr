"""Shared worker/finalizer check of exact result-bound automatic features."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .full_board_calibration import FeatureVector, acceptance_reasons
from .grid_model_registry import descriptor_sha256 as digest


def calibrated_result_blockers(
    evidence: object,
    *,
    pin: object,
    proposal: Mapping[str, Any],
    detection: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if not isinstance(pin, Mapping) or pin.get("contractVersion") != "neural-grid-operation-pin-v3":
        return ("NEURAL_GRID_OPERATION_POLICY_MISMATCH",)
    qualification = pin.get("automaticQualification")
    if not isinstance(qualification, Mapping) or qualification.get("state") != "qualified":
        return ("NEURAL_GRID_CALIBRATION_REQUIRED",)
    profile = qualification["profile"]
    if detection is None or not isinstance(evidence, Mapping):
        return ("COMPLETENESS_EVIDENCE_REQUIRED",)
    expected = {
        "version",
        "sourceSha256",
        "modelManifestSha256",
        "operationPinSha256",
        "profileSha256",
        "detectionId",
        "nodesSha256",
        "features",
        "sha256",
    }
    if (
        evidence.keys() != expected
        or evidence["version"] != "full-board-result-evidence-v1"
        or evidence["sourceSha256"] != proposal["sourceChecksumSha256"]
        or evidence["modelManifestSha256"] != pin["catalogueManifestSha256"]
        or evidence["operationPinSha256"] != pin["pinSha256"]
        or evidence["profileSha256"] != profile["sha256"]
        or evidence["detectionId"] != detection["detectionId"]
        or evidence["nodesSha256"] != digest(detection["latticeNodes"])
        or evidence["sha256"] != digest({k: v for k, v in evidence.items() if k != "sha256"})
    ):
        return ("COMPLETENESS_EVIDENCE_MISMATCH",)
    try:
        return acceptance_reasons(
            FeatureVector.model_validate(evidence["features"]), profile["configuration"]
        )
    except (KeyError, TypeError, ValueError):
        return ("COMPLETENESS_EVIDENCE_INVALID",)
