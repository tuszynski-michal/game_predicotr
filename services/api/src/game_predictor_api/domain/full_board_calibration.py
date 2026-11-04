"""Deterministic numeric calibration after recognition; never selects a model/path."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .grid_training_cohorts import digest

AXES = (
    "peak",
    "visibility",
    "detectorIou",
    "fitResidual",
    "detectorCornerError",
    "gameAspectDeviation",
    "neighborDeviation",
    "rescueDisagreement",
)
MINIMUM_AXES = frozenset(AXES[:3])
QUANTILE_VERSION: Final = "nearest-rank-human-good-source-dedup-v1"
OUTCOME_VERSION: Final = "full-board-reference-outcome-v1"
CALIBRATION_VERSION = "full-board-calibration-v1"
FEATURE_VERSION: Final = "full-board-completeness-features-v1"
MAX_CONFIGURATIONS = 256
MIN_STRATUM_SOURCES = 30
COVERAGE_EPSILON = 1e-6
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class ClosedCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeatureVector(ClosedCalibration):
    version: Literal["full-board-completeness-features-v1"] = FEATURE_VERSION
    values: dict[str, Finite | None]
    notApplicable: tuple[str, ...] = ()
    hardReasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def closed_axes(self) -> FeatureVector:
        if set(self.values) != set(AXES) or set(self.notApplicable) - {
            "rescueDisagreement",
            "neighborDeviation",
        }:
            raise ValueError("CALIBRATION_FEATURE_AXES_INVALID")
        if len(set(self.notApplicable)) != len(self.notApplicable):
            raise ValueError("CALIBRATION_FEATURE_STATE_INVALID")
        if any(self.values[key] is not None for key in self.notApplicable):
            raise ValueError("CALIBRATION_FEATURE_STATE_INVALID")
        return self


class ReferenceTarget(ClosedCalibration):
    gameId: UUID
    sourceRepresentativeSha256: Sha
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    role: Literal["TRAIN", "VALIDATION-A"]
    humanGood: bool
    features: FeatureVector


class CalibrationPlan(ClosedCalibration):
    version: Literal["full-board-calibration-plan-v1"] = "full-board-calibration-plan-v1"
    gameId: UUID
    candidateManifestSha256: Sha
    baselineManifestSha256: Sha
    routingSha256: Sha
    referenceSha256: Sha
    roleProofSha256: Sha
    bAssessmentSha256: Sha
    regressionAssessmentSha256: Sha
    outcomeVersion: Literal["full-board-reference-outcome-v1"] = OUTCOME_VERSION
    quantileVersion: Literal["nearest-rank-human-good-source-dedup-v1"] = QUANTILE_VERSION
    menu: tuple[dict[str, Finite | None], ...]
    manualWhenApplicable: tuple[str, ...]
    axisCounts: dict[str, dict[str, int]]
    referenceTargets: int
    referenceSources: int
    tieBreak: Literal["correct-desc-incorrect-asc-canonical-v1"] = (
        "correct-desc-incorrect-asc-canonical-v1"
    )
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> CalibrationPlan:
        if not 1 <= len(self.menu) <= MAX_CONFIGURATIONS:
            raise ValueError("CALIBRATION_MENU_BUDGET")
        if set(self.manualWhenApplicable) - set(AXES) or set(self.axisCounts) != set(AXES):
            raise ValueError("CALIBRATION_PLAN_AXES_INVALID")
        for config in self.menu:
            if set(config) != set(AXES) or {
                key for key, value in config.items() if value is None
            } != set(self.manualWhenApplicable):
                raise ValueError("CALIBRATION_PLAN_AXES_INVALID")
        if list(self.menu) != sorted(self.menu, key=digest) or len(
            {digest(c) for c in self.menu}
        ) != len(self.menu):
            raise ValueError("CALIBRATION_MENU_ORDER_INVALID")
        if digest(self.model_dump(mode="json", exclude={"sha256"})) != self.sha256:
            raise ValueError("CALIBRATION_PLAN_CHECKSUM")
        return self


def make_plan(
    references: Sequence[ReferenceTarget],
    *,
    game_id: UUID,
    candidate_sha: str,
    baseline_sha: str,
    routing_sha: str,
    role_proof_sha: str,
    b_assessment_sha: str,
    regression_assessment_sha: str,
) -> CalibrationPlan:
    """At most 2**8 configurations PER GAME. No inference or B access here.

    Repeated copies are one exact source/target. Conflicting duplicate evidence
    fails instead of allowing input order to choose a reference.
    """
    unique: dict[tuple[str, int], ReferenceTarget] = {}
    for target in references:
        if target.gameId != game_id:
            raise ValueError("CALIBRATION_REFERENCE_GAME_MISMATCH")
        key = target.sourceRepresentativeSha256, target.positionIndex
        old = unique.get(key)
        if old is not None and old != target:
            raise ValueError("CALIBRATION_REFERENCE_ALIAS_CONFLICT")
        unique[key] = target
    ordered = [unique[key] for key in sorted(unique)]
    levels: list[Sequence[float | None]] = []
    counts: dict[str, dict[str, int]] = {}
    missing = []
    for axis in AXES:
        measured = [
            item
            for item in ordered
            if item.humanGood
            and not item.features.hardReasons
            and item.features.values[axis] is not None
        ]
        values = sorted(float(item.features.values[axis]) for item in measured)  # type: ignore[arg-type]
        counts[axis] = {
            "nTargets": len(values),
            "nSources": len({item.sourceRepresentativeSha256 for item in measured}),
        }
        if not values:
            levels.append([None])
            missing.append(axis)
            continue
        percentiles = (1, 5) if axis in MINIMUM_AXES else (95, 99)
        levels.append(
            sorted(
                {
                    values[max(0, math.ceil(percent * len(values) / 100) - 1)]
                    for percent in percentiles
                }
            )
        )
    menu = sorted(
        (dict(zip(AXES, values, strict=True)) for values in itertools.product(*levels)), key=digest
    )
    payload = {
        "version": "full-board-calibration-plan-v1",
        "gameId": str(game_id),
        "candidateManifestSha256": candidate_sha,
        "baselineManifestSha256": baseline_sha,
        "routingSha256": routing_sha,
        "referenceSha256": digest([item.model_dump(mode="json") for item in ordered]),
        "roleProofSha256": role_proof_sha,
        "bAssessmentSha256": b_assessment_sha,
        "regressionAssessmentSha256": regression_assessment_sha,
        "outcomeVersion": OUTCOME_VERSION,
        "quantileVersion": QUANTILE_VERSION,
        "menu": menu,
        "manualWhenApplicable": missing,
        "axisCounts": counts,
        "referenceTargets": len(ordered),
        "referenceSources": len({item.sourceRepresentativeSha256 for item in ordered}),
        "tieBreak": "correct-desc-incorrect-asc-canonical-v1",
    }
    return CalibrationPlan.model_validate({**payload, "sha256": digest(payload)})


def acceptance_reasons(
    features: FeatureVector, config: Mapping[str, float | None]
) -> tuple[str, ...]:
    if set(config) != set(AXES):
        raise ValueError("CALIBRATION_CONFIG_AXES_INVALID")
    reasons = set(features.hardReasons)
    for axis in AXES:
        if axis in features.notApplicable:
            continue
        value, threshold = features.values[axis], config[axis]
        if value is None or threshold is None:
            reasons.add("COMPLETENESS_REFERENCE_MISSING:" + axis)
        elif value < threshold if axis in MINIMUM_AXES else value > threshold:
            reasons.add("COMPLETENESS_THRESHOLD:" + axis)
    return tuple(sorted(reasons))


class AssessedTarget(ClosedCalibration):
    gameId: UUID
    sourceId: UUID
    sourceRepresentativeSha256: Sha
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    groundTruthSha256: Sha
    baselineGood: bool
    candidateGood: bool
    candidateCropped: bool | None
    baselinePreT0Accepted: bool
    baselineT0Accepted: bool
    candidateFeatures: FeatureVector
    synthetic: bool = False


def _targets(plan: CalibrationPlan, targets: Sequence[AssessedTarget]) -> list[AssessedTarget]:
    unique: dict[tuple[str, int], AssessedTarget] = {}
    for target in targets:
        if target.gameId != plan.gameId:
            raise ValueError("CALIBRATION_ASSESSMENT_GAME_MISMATCH")
        key = target.sourceRepresentativeSha256, target.positionIndex
        old = unique.get(key)
        if old is not None and old.model_dump(exclude={"sourceId"}) != target.model_dump(
            exclude={"sourceId"}
        ):
            raise ValueError("CALIBRATION_ASSESSMENT_ALIAS_CONFLICT")
        unique[key] = target if old is None or target.sourceId.int < old.sourceId.int else old
    return [unique[key] for key in sorted(unique)]


def measure_targets(
    plan: CalibrationPlan, targets: Sequence[AssessedTarget], config: Mapping[str, float | None]
) -> dict[str, Any]:
    items = _targets(plan, targets)
    bad = {
        item.sourceRepresentativeSha256
        for item in items
        if not item.synthetic and not item.baselineGood
    }
    good = {
        item.sourceRepresentativeSha256
        for item in items
        if not item.synthetic and item.baselineGood
    }
    accepted = [item for item in items if not acceptance_reasons(item.candidateFeatures, config)]
    return {
        "scope": "labelled_targets",
        "targets": len(items),
        "sources": len({item.sourceRepresentativeSha256 for item in items}),
        "baselineBadSources": len(bad),
        "baselineGoodSources": len(good),
        "stratumOverlapSources": len(bad & good),
        "stratumUnionSources": len(bad | good),
        "syntheticTargets": sum(item.synthetic for item in items),
        "candidateBad": sum(not item.candidateGood for item in items),
        "candidateCorrectAutomatic": sum(item.candidateGood for item in accepted),
        "candidateIncorrectAutomatic": sum(not item.candidateGood for item in accepted),
        "acceptedCropped": sum(item.candidateCropped is True for item in accepted),
        "acceptedUnknownCoverage": sum(item.candidateCropped is None for item in accepted),
        "baselinePreT0CorrectAutomatic": sum(
            item.baselineGood and item.baselinePreT0Accepted for item in items
        ),
        "baselineT0CorrectAutomatic": sum(
            item.baselineGood and item.baselineT0Accepted for item in items
        ),
        "assessmentSha256": digest([item.model_dump(mode="json") for item in items]),
    }


def qualification_reasons(measured: Mapping[str, Any]) -> list[str]:
    reasons = []
    for field in ("baselineBadSources", "baselineGoodSources"):
        if int(measured[field]) < MIN_STRATUM_SOURCES:
            reasons.append("CALIBRATION_MINIMUM:" + field)
    if measured["syntheticTargets"]:
        reasons.append("CALIBRATION_SYNTHETIC_CONTROL")
    if measured["acceptedCropped"]:
        reasons.append("CALIBRATION_ACCEPTED_CROP")
    if measured["acceptedUnknownCoverage"]:
        reasons.append("CALIBRATION_COVERAGE_UNKNOWN")
    if int(measured["candidateCorrectAutomatic"]) <= int(measured["baselineT0CorrectAutomatic"]):
        reasons.append("CALIBRATION_NO_AUTOMATIC_GAIN")
    return reasons


def seal_b(plan: CalibrationPlan, targets: Sequence[AssessedTarget]) -> dict[str, Any]:
    """One numeric sweep after B observations, no model calls or REG access."""
    candidates = []
    for index, config in enumerate(plan.menu):
        measured = measure_targets(plan, targets, config)
        if not measured["acceptedCropped"] and not measured["acceptedUnknownCoverage"]:
            candidates.append(
                (
                    (
                        -int(measured["candidateCorrectAutomatic"]),
                        int(measured["candidateIncorrectAutomatic"]),
                        index,
                    ),
                    measured,
                )
            )
    choice = min(candidates, default=None, key=lambda item: item[0])
    chosen_index = choice[0][2] if choice is not None else None
    chosen_measurement = choice[1] if choice is not None else None
    payload: dict[str, Any] = {
        "version": "full-board-calibration-sealed-v1",
        "gameId": str(plan.gameId),
        "planSha256": plan.sha256,
        "configurationIndex": chosen_index,
        "configuration": plan.menu[chosen_index] if chosen_index is not None else None,
        "b": chosen_measurement,
        "reasonCodes": qualification_reasons(chosen_measurement)
        if chosen_measurement
        else ["CALIBRATION_NO_SAFE_CONFIGURATION"],
        "comparisons": len(plan.menu),
    }
    return {**payload, "sha256": digest(payload)}


def assess_regression(
    plan: CalibrationPlan, sealed: dict[str, Any], targets: Sequence[AssessedTarget]
) -> dict[str, Any]:
    if (
        sealed.get("sha256")
        != digest({key: value for key, value in sealed.items() if key != "sha256"})
        or sealed.get("planSha256") != plan.sha256
        or sealed.get("gameId") != str(plan.gameId)
    ):
        raise ValueError("CALIBRATION_SEALED_CHECKSUM")
    index = sealed.get("configurationIndex")
    if index is None:
        measured = None
        reasons = list(sealed["reasonCodes"])
    else:
        if (
            type(index) is not int
            or not 0 <= index < len(plan.menu)
            or sealed.get("configuration") != plan.menu[index]
        ):
            raise ValueError("CALIBRATION_SEALED_CONFIGURATION")
        measured = measure_targets(plan, targets, plan.menu[index])
        reasons = list(sealed["reasonCodes"]) + qualification_reasons(measured)
    payload: dict[str, Any] = {
        "version": CALIBRATION_VERSION,
        "gameId": str(plan.gameId),
        "planSha256": plan.sha256,
        "sealedSha256": sealed["sha256"],
        "state": "unqualified" if reasons else "qualified",
        "reasonCodes": sorted(set(reasons)),
        "regression": measured,
        "assessmentScope": "labelled_targets",
        "wholePhotoClaims": False,
    }
    return {**payload, "sha256": digest(payload)}
