"""Shared worker/finalizer check of exact result-bound automatic features."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .full_board_calibration import FeatureVector, acceptance_reasons
from .grid_model_registry import descriptor_sha256 as digest


def calibrated_result_blockers(
    evidence: object,
    *,
    pin: object,
    proposal: Mapping[str, Any],
    detection: Mapping[str, Any] | None,
    available_source_box: Sequence[int] | None = None,
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
    variant = profile["version"] == "full-board-auto-profile-v3"
    if variant:
        expected |= {"variantKey", "variantProfileSha256", "inputVariantSha256"}
    if (
        evidence.keys() != expected
        or evidence["version"]
        != (
            "full-board-result-evidence-v3"
            if variant
            else "full-board-result-evidence-v2"
            if profile["version"] == "full-board-auto-profile-v2"
            else "full-board-result-evidence-v1"
        )
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
        configuration = profile.get("configuration")
        if variant:
            from .full_board_input_variant import require_runtime_input_variant
            from .full_board_variant_calibration_types import VariantAutomaticProfile

            stamp = require_runtime_input_variant(
                detection.get("inputVariant"),
                pin=pin,
                proposal=proposal,
                detection=detection,
                available_source_box=available_source_box,
            )
            if (
                stamp.sha256 != evidence["inputVariantSha256"]
                or stamp.variantKey != evidence["variantKey"]
            ):
                return ("COMPLETENESS_INPUT_VARIANT_CHANGED",)
            parsed = VariantAutomaticProfile.model_validate(profile)
            matches = [p for p in parsed.variants if p.variantKey == evidence["variantKey"]]
            if len(matches) != 1:
                return ("COMPLETENESS_VARIANT_UNQUALIFIED",)
            if matches[0].profile.sha256 != evidence["variantProfileSha256"]:
                return ("COMPLETENESS_VARIANT_PROFILE_CHANGED",)
            configuration = matches[0].profile.configuration
        return acceptance_reasons(FeatureVector.model_validate(evidence["features"]), configuration)
    except (KeyError, TypeError, ValueError):
        return ("COMPLETENESS_EVIDENCE_INVALID",)
