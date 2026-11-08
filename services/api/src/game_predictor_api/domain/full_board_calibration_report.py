"""Automatic qualification is additional evidence, independent of raw quality PASS."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .full_board_calibration import (
    ClosedCalibration,
    Finite,
    Sha,
    axes_for,
    qualification_reasons,
)
from .grid_model_registry import canonical_json, descriptor_sha256

REPORT_SCHEMA = "grid-model-evaluation-read-v5"


class CalibrationCounts(ClosedCalibration):
    scope: Literal["labelled_targets"]
    targets: int = Field(ge=0)
    sources: int = Field(ge=0)
    baselineBadSources: int = Field(ge=0)
    baselineGoodSources: int = Field(ge=0)
    stratumOverlapSources: int = Field(ge=0)
    stratumUnionSources: int = Field(ge=0)
    syntheticTargets: int = Field(ge=0)
    candidateBad: int = Field(ge=0)
    candidateCorrectAutomatic: int = Field(ge=0)
    candidateIncorrectAutomatic: int = Field(ge=0)
    acceptedCropped: int = Field(ge=0)
    acceptedUnknownCoverage: int = Field(ge=0)
    baselinePreT0CorrectAutomatic: int = Field(ge=0)
    baselineT0CorrectAutomatic: int = Field(ge=0)
    assessmentSha256: Sha

    @model_validator(mode="after")
    def counts(self) -> CalibrationCounts:
        if (
            self.sources > self.targets
            or self.stratumUnionSources > self.sources
            or self.baselineBadSources + self.baselineGoodSources - self.stratumOverlapSources
            != self.stratumUnionSources
            or self.stratumOverlapSources > min(self.baselineBadSources, self.baselineGoodSources)
            or self.candidateCorrectAutomatic + self.candidateIncorrectAutomatic > self.targets
            or self.candidateBad > self.targets
            or self.acceptedCropped + self.acceptedUnknownCoverage
            > self.candidateCorrectAutomatic + self.candidateIncorrectAutomatic
        ):
            raise ValueError("CALIBRATION_COUNTS_INVALID")
        return self


class AutomaticProfile(ClosedCalibration):
    version: Literal["full-board-auto-profile-v1", "full-board-auto-profile-v2"] = (
        "full-board-auto-profile-v1"
    )
    gameId: UUID
    candidateManifestSha256: Sha
    planSha256: Sha
    sealedSha256: Sha
    routingSha256: Sha
    configuration: dict[str, Finite | None]
    gameLogAspectReference: Finite | None
    assessmentScope: Literal["labelled_targets"] = "labelled_targets"
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> AutomaticProfile:
        if set(self.configuration) != set(
            axes_for(self.version)
        ) or self.sha256 != descriptor_sha256(self.model_dump(mode="json", exclude={"sha256"})):
            raise ValueError("CALIBRATION_PROFILE_INVALID")
        return self


class CalibrationArtifact(ClosedCalibration):
    path: str = Field(min_length=1, max_length=500)
    sha256: Sha


class AutomaticCalibration(ClosedCalibration):
    version: Literal[
        "full-board-calibration-qualification-v1", "full-board-calibration-qualification-v2"
    ] = "full-board-calibration-qualification-v1"
    gameId: UUID
    state: Literal["qualified", "unqualified"]
    reasonCodes: list[str]
    b: CalibrationCounts | None
    regression: CalibrationCounts | None
    profile: AutomaticProfile | None
    evidence: CalibrationArtifact | None
    plannedConfigurations: Annotated[int, Field(ge=0, le=256)]
    plannedComparisons: int = Field(ge=0)
    roleProofSha256: Sha | None
    limitations: list[str]

    @model_validator(mode="after")
    def verdict(self) -> AutomaticCalibration:
        if (
            self.profile is not None
            and self.profile.version.rsplit("-", 1)[1] != self.version.rsplit("-", 1)[1]
        ):
            raise ValueError("CALIBRATION_PROFILE_VERSION_MISMATCH")
        if self.state == "qualified":
            if (
                self.reasonCodes
                or self.b is None
                or self.regression is None
                or self.profile is None
                or self.evidence is None
                or self.roleProofSha256 is None
                or self.profile.gameId != self.gameId
                or not self.plannedConfigurations
            ):
                raise ValueError("CALIBRATION_QUALIFICATION_INCOMPLETE")
            if qualification_reasons(self.b.model_dump()) or qualification_reasons(
                self.regression.model_dump()
            ):
                raise ValueError("CALIBRATION_QUALIFICATION_FALSE")
        elif not self.reasonCodes or self.profile is not None:
            raise ValueError("CALIBRATION_UNQUALIFIED_PROFILE")
        return self


LIMITATIONS = [
    "Source overlap between baseline-good and baseline-bad strata is reported; "
    "60 independent photos are not claimed.",
    "Partial controls assess labelled targets only; whole-photo false-positive "
    "and duplicate claims require complete GT.",
    "Runtime input-support checks inspect fitted cells and cannot prove detection "
    "of every omitted row without GT.",
    "Known copy, session and ancestry protections are enforced; "
    "no statistical independence or probability is claimed.",
]


def unqualified(game_id: str, reason: str) -> dict[str, Any]:
    return AutomaticCalibration(
        gameId=UUID(game_id),
        state="unqualified",
        reasonCodes=[reason],
        b=None,
        regression=None,
        profile=None,
        evidence=None,
        plannedConfigurations=0,
        plannedComparisons=0,
        roleProofSha256=None,
        limitations=LIMITATIONS,
    ).model_dump(mode="json")


def attach_calibration(
    quality: dict[str, Any],
    calibrations: list[dict[str, Any]],
    *,
    allow_variant_calibration: bool = False,
) -> dict[str, Any]:
    if quality["schemaVersion"] not in (
        "grid-model-evaluation-read-v3",
        "grid-model-evaluation-read-v4",
    ):
        raise ValueError("CALIBRATION_RAW_REPORT_REQUIRED")
    parsed = [
        parse_calibration(value, allow_variant_calibration=allow_variant_calibration)
        for value in calibrations
    ]
    if [value["gameId"] for value in parsed] != quality["requiredGameIds"]:
        raise ValueError("CALIBRATION_REPORT_SCOPE_INVALID")
    if sum(value["plannedConfigurations"] for value in parsed) > sum(
        512 if value["version"] == "full-board-calibration-qualification-v3" else 256
        for value in parsed
    ):
        raise ValueError("CALIBRATION_MENU_BUDGET")
    return {
        **quality,
        "schemaVersion": REPORT_SCHEMA,
        "rawQualitySchemaVersion": quality["schemaVersion"],
        "automaticCalibration": parsed,
    }


def parse_calibration(
    value: Mapping[str, Any], *, allow_variant_calibration: bool = False
) -> dict[str, Any]:
    if value.get("version") == "full-board-calibration-qualification-v3":
        if not allow_variant_calibration:
            raise ValueError("VARIANT_CALIBRATION_CONTENT_DISPATCH_REQUIRED")
        from .full_board_variant_calibration_types import VariantAutomaticCalibration

        return VariantAutomaticCalibration.model_validate(value).model_dump(mode="json")
    return AutomaticCalibration.model_validate(value).model_dump(mode="json")


def require_report(
    report_json: str,
    *,
    manifest: Mapping[str, Any],
    base_sha256: str,
    allow_content_selection: bool = False,
    allow_variant_calibration: bool = False,
) -> dict[str, Any]:
    from .grid_correction_evaluation import require_report as require_quality
    from .grid_model_evaluation import MAX_REPORT_BYTES, GridEvaluationReportError

    try:
        if len(report_json.encode()) > MAX_REPORT_BYTES:
            raise ValueError("CALIBRATION_REPORT_TOO_LARGE")
        report = json.loads(report_json)
        if not isinstance(report, dict):
            raise ValueError("CALIBRATION_REPORT_INVALID")
        if report.get("schemaVersion") != REPORT_SCHEMA or canonical_json(report) != report_json:
            raise ValueError("CALIBRATION_REPORT_INVALID")
        quality = {
            key: value
            for key, value in report.items()
            if key not in {"rawQualitySchemaVersion", "automaticCalibration"}
        }
        quality["schemaVersion"] = report["rawQualitySchemaVersion"]
        require_quality(
            canonical_json(quality),
            manifest=manifest,
            base_sha256=base_sha256,
            allow_content_selection=allow_content_selection,
        )
        if (
            attach_calibration(
                quality,
                report["automaticCalibration"],
                allow_variant_calibration=allow_variant_calibration,
            )
            != report
        ):
            raise ValueError("CALIBRATION_REPORT_INVALID")
        for value in report["automaticCalibration"]:
            profile = value["profile"]
            if (
                profile is not None
                and profile["candidateManifestSha256"] != report["manifestSha256"]
            ):
                raise ValueError("CALIBRATION_REPORT_MODEL_MISMATCH")
        return report
    except (KeyError, TypeError, ValueError) as error:
        raise GridEvaluationReportError(str(error)) from error
