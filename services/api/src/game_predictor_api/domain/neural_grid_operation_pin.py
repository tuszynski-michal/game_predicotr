"""Versioned operation capabilities and exact per-game evaluation pins.

Catalogue v1 used boardRows for the horizontal axis. Adapt that exact contract;
never rewrite its immutable descriptor or change proposal snapshot v1/v2 bytes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from .grid_engine_profiles import grid_engine_manifest
from .grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)
from .neural_grid_proposal import NeuralGridSnapshot

OPERATION_PIN_KEY = "neural_grid_operation_pin"
OPERATION_PIN_VERSION = "neural-grid-operation-pin-v1"
GAME_QUALIFICATION_POLICY = "neural-game-evaluation-v1"
CAPABILITY_PREFLIGHT_POLICY = "page-geometry-preflight-v14-neural-capabilities"
GAME_EVALUATION_REQUIRED = "NEURAL_GRID_GAME_EVALUATION_REQUIRED"
CALIBRATION_REQUIRED = "NEURAL_GRID_CALIBRATION_REQUIRED"
CALIBRATED_PIN_VERSION = "neural-grid-operation-pin-v3"
SYMBOL_REVIEW_PIN_VERSION = "neural-grid-operation-pin-v4"
_REVIEW_ONLY_QUALITY_BLOCKERS = frozenset(
    {
        GAME_EVALUATION_REQUIRED,
        CALIBRATION_REQUIRED,
        "NEURAL_GRID_GAME_EVALUATION_STALE",
        "NEURAL_GRID_CALIBRATION_STALE",
    }
)


def symbol_review_qualification_blockers(blockers: tuple[str, ...] | None) -> tuple[str, ...]:
    """Only evidence-of-quality gates are waived; technical failures remain fatal."""
    if blockers is None:
        return ("NEURAL_GRID_GAME_EVALUATION_UNCHECKED",)
    return tuple(code for code in blockers if code not in _REVIEW_ONLY_QUALITY_BLOCKERS)


_SHA = re.compile(r"[0-9a-f]{64}")
NEURAL_OPERATION_DERIVED_KEYS = frozenset(
    {
        OPERATION_PIN_KEY,
        "neural_grid_execution_policy_version",
        "v3_engine_acceptance_policy_version",
        "pipeline_fingerprint",
        "base_page_geometry_manifest",
    }
)


def neural_operation_request_identity(payload: Mapping[str, object]) -> dict[str, object]:
    """Exact stable input: only execution pins and derived server fields are removed."""
    return {
        key: value for key, value in payload.items() if key not in NEURAL_OPERATION_DERIVED_KEYS
    }


class NeuralOperationPinError(ValueError):
    code = "NEURAL_GRID_OPERATION_PIN_INVALID"


def snapshot_descriptor(snapshot: NeuralGridSnapshot) -> dict[str, Any]:
    if snapshot.version.catalogue_manifest_json is not None:
        return dict(json.loads(snapshot.version.catalogue_manifest_json))
    manifest = grid_engine_manifest(snapshot.version)
    matches = [item for item in historical_catalogue() if item["inferenceManifest"] == manifest]
    if len(matches) != 1:
        raise NeuralOperationPinError("The legacy model has no exact capability descriptor.")
    return matches[0]


def model_capabilities(snapshot: NeuralGridSnapshot) -> dict[str, object]:
    descriptor = snapshot_descriptor(snapshot)
    validate_manifest(descriptor)
    topology = descriptor["topology"]
    return {
        "contractVersion": "neural-grid-capabilities-v1",
        "catalogueManifestSha256": descriptor_sha256(descriptor),
        # Explicit adapter of grid-model-catalogue-v1 names only.
        "boardRows": topology["boardColumns"],
        "boardColumns": topology["boardRows"],
        "pageRows": topology["screenRows"],
        "pageColumns": topology["screenColumns"],
        "capabilities": list(descriptor["capabilities"]),
    }


def make_operation_pin(
    *,
    snapshot: NeuralGridSnapshot,
    game_id: str,
    rules_version_id: str,
    rows: int,
    columns: int,
    qualification: dict[str, object],
    rescue: dict[str, object] | None = None,
    automatic_qualification: dict[str, object] | None = None,
    for_symbol_review: bool = False,
) -> dict[str, object]:
    descriptor = snapshot_descriptor(snapshot)
    pin: dict[str, object] = {
        "contractVersion": CALIBRATED_PIN_VERSION
        if automatic_qualification is not None
        else OPERATION_PIN_VERSION
        if rescue is None
        else "neural-grid-operation-pin-v2",
        "gameId": game_id,
        "modelVersionId": descriptor["versionId"],
        "catalogueManifestSha256": descriptor_sha256(descriptor),
        "capabilities": model_capabilities(snapshot),
        "topologyRulesVersionId": rules_version_id,
        "boardRows": rows,
        "boardColumns": columns,
        "qualificationPolicyVersion": GAME_QUALIFICATION_POLICY,
        "qualification": qualification,
        **({"rescue": rescue} if rescue is not None else {}),
    }
    if automatic_qualification is not None:
        pin["contractVersion"] = CALIBRATED_PIN_VERSION
        profile = automatic_qualification.get("profile")
        pin["qualificationPolicyVersion"] = _calibration_policy(profile)
        pin["automaticQualification"] = automatic_qualification
        pin["rescue"] = rescue
    if for_symbol_review:
        if automatic_qualification is None:
            raise ValueError("Symbol review requires explicit qualification metadata.")
        pin["contractVersion"] = SYMBOL_REVIEW_PIN_VERSION
    pin["pinSha256"] = descriptor_sha256(pin)
    return require_operation_pin(pin, snapshot=snapshot, game_id=game_id)


def require_operation_pin(
    value: object,
    *,
    snapshot: NeuralGridSnapshot,
    game_id: str,
) -> dict[str, Any]:
    try:
        is_review = (
            isinstance(value, Mapping) and value.get("contractVersion") == SYMBOL_REVIEW_PIN_VERSION
        )
        is_calibrated = isinstance(value, Mapping) and value.get("contractVersion") in (
            CALIBRATED_PIN_VERSION,
            SYMBOL_REVIEW_PIN_VERSION,
        )
        is_rescue = (
            isinstance(value, Mapping)
            and value.get("contractVersion") == "neural-grid-operation-pin-v2"
        )
        if not isinstance(value, Mapping) or value.keys() != {
            "contractVersion",
            "gameId",
            "modelVersionId",
            "catalogueManifestSha256",
            "capabilities",
            "topologyRulesVersionId",
            "boardRows",
            "boardColumns",
            "qualificationPolicyVersion",
            "qualification",
            "pinSha256",
        } | (
            {"rescue", "automaticQualification"}
            if is_calibrated
            else {"rescue"}
            if is_rescue
            else set()
        ):
            raise ValueError("Operation pin fields differ.")
        pin = dict(value)
        snapshot.require_game(game_id)
        descriptor = snapshot_descriptor(snapshot)
        if (
            pin["contractVersion"]
            != (
                SYMBOL_REVIEW_PIN_VERSION
                if is_review
                else CALIBRATED_PIN_VERSION
                if is_calibrated
                else "neural-grid-operation-pin-v2"
                if is_rescue
                else OPERATION_PIN_VERSION
            )
            or pin["gameId"] != game_id
            or str(UUID(game_id)) != game_id
            or str(UUID(pin["topologyRulesVersionId"])) != pin["topologyRulesVersionId"]
            or pin["modelVersionId"] != descriptor["versionId"]
            or pin["catalogueManifestSha256"] != descriptor_sha256(descriptor)
            or canonical_json(pin["capabilities"]) != canonical_json(model_capabilities(snapshot))
            or type(pin["boardRows"]) is not int
            or pin["boardRows"] != 3
            or type(pin["boardColumns"]) is not int
            or pin["boardColumns"] != 5
            or pin["qualificationPolicyVersion"]
            != (
                (
                    _calibration_policy(pin["automaticQualification"].get("profile"))
                    if isinstance(pin.get("automaticQualification"), dict)
                    else "full-board-calibration-qualification-v1"
                )
                if is_calibrated
                else GAME_QUALIFICATION_POLICY
            )
            or pin["pinSha256"]
            != descriptor_sha256({k: v for k, v in pin.items() if k != "pinSha256"})
        ):
            raise ValueError("Unsupported topology or mismatched operation identity.")
        qualification = pin["qualification"]
        if not isinstance(qualification, dict):
            raise ValueError("Qualification must be an object.")
        if qualification.get("state") == "unqualified":
            if qualification != {"state": "unqualified", "reasonCodes": [GAME_EVALUATION_REQUIRED]}:
                raise ValueError("Unqualified evidence fields differ.")
        elif qualification.get("state") == "qualified":
            if (
                qualification.keys()
                != {
                    "state",
                    "reasonCodes",
                    "evaluationId",
                    "evaluationSha256",
                    "publicationEvidenceSha256",
                }
                or qualification["reasonCodes"] != []
            ):
                raise ValueError("Qualified evidence fields differ.")
            if str(UUID(qualification["evaluationId"])) != qualification["evaluationId"]:
                raise ValueError("Evaluation ID must be canonical.")
            for field in ("evaluationSha256", "publicationEvidenceSha256"):
                if (
                    not isinstance(qualification[field], str)
                    or _SHA.fullmatch(qualification[field]) is None
                ):
                    raise ValueError("Evaluation evidence requires SHA-256.")
        else:
            raise ValueError("Unknown qualification state.")
        if is_calibrated:
            require_automatic_qualification(
                pin["automaticQualification"],
                game_id=game_id,
                manifest_sha=pin["catalogueManifestSha256"],
            )
        if is_rescue or (is_calibrated and pin["rescue"] is not None):
            from .grid_rescue_policy import require_rescue_pin

            bundle_sha = next(
                item["sha256"] for item in descriptor["files"] if item["name"] == "bundle.json"
            )
            rescue = require_rescue_pin(pin["rescue"], bundle_sha=bundle_sha)
            if (
                qualification["state"] != "qualified"
                or rescue["publicationEvidenceSha256"] != qualification["publicationEvidenceSha256"]
            ):
                raise ValueError("Rescue qualification differs from the operation evidence.")
        return pin
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise NeuralOperationPinError(str(error)) from error


def operation_pin_blockers(
    value: object, *, model_snapshot: object, game_id: str, for_symbol_review: bool = False
) -> tuple[str, ...]:
    try:
        pin = require_operation_pin(
            value, snapshot=NeuralGridSnapshot.from_payload(model_snapshot), game_id=game_id
        )
    except ValueError:
        return (NeuralOperationPinError.code,)
    if for_symbol_review:
        return (
            ()
            if pin["contractVersion"] == SYMBOL_REVIEW_PIN_VERSION
            else ("NEURAL_GRID_OPERATION_POLICY_MISMATCH",)
        )
    if pin["qualification"]["state"] != "qualified":
        return (GAME_EVALUATION_REQUIRED,)
    if (
        pin["contractVersion"] in (CALIBRATED_PIN_VERSION, SYMBOL_REVIEW_PIN_VERSION)
        and pin["automaticQualification"]["state"] != "qualified"
    ):
        return (CALIBRATION_REQUIRED,)
    return ()


def _calibration_policy(profile: object) -> str:
    if isinstance(profile, dict):
        if profile.get("version") == "full-board-auto-profile-v3":
            return "full-board-calibration-qualification-v3"
        if profile.get("version") == "full-board-auto-profile-v2":
            return "full-board-calibration-qualification-v2"
    return "full-board-calibration-qualification-v1"


def require_automatic_qualification(
    value: object, *, game_id: str, manifest_sha: str
) -> dict[str, Any]:
    """A selected profile, never the 256-entry search menu, travels with an operation."""
    from .full_board_calibration import axes_for

    if isinstance(value, dict) and value == {
        "state": "unqualified",
        "reasonCodes": [CALIBRATION_REQUIRED],
    }:
        return dict(value)
    if (
        not isinstance(value, dict)
        or value.keys() != {"state", "reasonCodes", "reportId", "reportSha256", "profile"}
        or value["state"] != "qualified"
        or value["reasonCodes"] != []
    ):
        raise ValueError("NEURAL_GRID_CALIBRATION_PIN_INVALID")
    if str(UUID(value["reportId"])) != value["reportId"] or not _SHA.fullmatch(
        value["reportSha256"]
    ):
        raise ValueError("NEURAL_GRID_CALIBRATION_PIN_INVALID")
    profile = value["profile"]
    if isinstance(profile, dict) and profile.get("version") == "full-board-auto-profile-v3":
        from .full_board_variant_calibration_types import VariantAutomaticProfile

        parsed = VariantAutomaticProfile.model_validate(profile)
        if str(parsed.gameId) != game_id or parsed.candidateManifestSha256 != manifest_sha:
            raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
        return value
    if not isinstance(profile, dict) or profile.keys() != {
        "version",
        "gameId",
        "candidateManifestSha256",
        "planSha256",
        "sealedSha256",
        "routingSha256",
        "configuration",
        "gameLogAspectReference",
        "assessmentScope",
        "sha256",
    }:
        raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
    if (
        profile["version"] not in ("full-board-auto-profile-v1", "full-board-auto-profile-v2")
        or profile["gameId"] != game_id
        or profile["candidateManifestSha256"] != manifest_sha
        or profile["assessmentScope"] != "labelled_targets"
        or profile["sha256"]
        != descriptor_sha256({k: v for k, v in profile.items() if k != "sha256"})
    ):
        raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
    import math

    if not isinstance(profile["configuration"], dict) or set(profile["configuration"]) != set(
        axes_for(profile["version"])
    ):
        raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
    for number in [*profile["configuration"].values(), profile["gameLogAspectReference"]]:
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number)):
            raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
    for key in ("planSha256", "sealedSha256", "routingSha256"):
        if not isinstance(profile[key], str) or not _SHA.fullmatch(profile[key]):
            raise ValueError("NEURAL_GRID_CALIBRATION_PROFILE_INVALID")
    return value
