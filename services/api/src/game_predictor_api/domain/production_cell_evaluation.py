"""Versioned per-instance production-content gate; historical gates remain immutable."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .grid_correction_evaluation import require_metrics
from .grid_model_evaluation import MAX_REPORT_BYTES, GridEvaluationReportError, verdict_of
from .grid_model_registry import canonical_json

RULE_VERSION = "production-cell-content-evaluation-v1"
REPORT_SCHEMA = "grid-model-evaluation-read-v6"
POLICY_VERSION = "production-cell-per-game-gate-v1"
REFERENCE_VERSION = "production-cell-evaluation-reference-v1"
BASE_VERSION_ID = "3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e"
ROLES: tuple[Literal["VALIDATION", "REGRESSION"], ...] = ("VALIDATION", "REGRESSION")
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0)]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

POLICY = {
    "ruleVersion": RULE_VERSION,
    "minimumFreshFullRegressionPhotos": 5,
    "maximumUnknownFraction": 0.1,
    "minimumCurrentUsableBoardGain": 1,
    "sourcePixelEpsilon": 1e-6,
    "uncertaintyVersion": "cell-content-repeatability-v1",
    "instanceOrder": ["preserved", "borderline", "clipped/missing"],
    "compensationAllowed": False,
    "baseVersionId": BASE_VERSION_ID,
}


class ClosedContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelContentCounts(ClosedContent):
    preserved: Count
    borderline: Count
    clipped: Count
    missing: Count
    wrongCells: Count
    ties: Count
    foreignSymbols: Count
    ambiguousBoards: Count
    usableBoards: Count


class ContentRoleEvidence(ClosedContent):
    state: Literal["ready", "not_evaluable"]
    reasonCodes: list[str]
    photos: Count
    fullPhotos: Count
    slots: Count
    visible: Count
    unknown: Count
    occluded: Count
    outOfFrame: Count
    referenceSha256: SHA
    base: ModelContentCounts
    candidate: ModelContentCounts
    degradedInstances: Count
    newWrongCells: Count
    newTies: Count
    newForeignSymbols: Count
    newMatchAmbiguities: Count

    @model_validator(mode="after")
    def counts(self) -> ContentRoleEvidence:
        if (
            self.fullPhotos > self.photos
            or self.visible + self.unknown + self.occluded + self.outOfFrame != self.slots
            or self.slots % 15
            or self.state == "ready"
            and (self.reasonCodes or self.slots == 0)
            or self.state == "not_evaluable"
            and not self.reasonCodes
        ):
            raise ValueError("CONTENT_COUNTS_INVALID")
        for value in (self.base, self.candidate):
            if (
                value.preserved + value.borderline + value.clipped + value.missing != self.visible
                or max(value.wrongCells, value.ties, value.foreignSymbols) > self.visible
                or max(value.usableBoards, value.ambiguousBoards) > self.slots // 15
                or value.usableBoards * 15 > value.preserved
            ):
                raise ValueError("CONTENT_COUNTS_INVALID")
        if (
            max(self.degradedInstances, self.newWrongCells, self.newTies, self.newForeignSymbols)
            > self.visible
            or self.newMatchAmbiguities > self.slots // 15
        ):
            raise ValueError("CONTENT_DEGRADATION_COUNTS_INVALID")
        if (
            self.newWrongCells > self.candidate.wrongCells
            or self.newTies > self.candidate.ties
            or self.newForeignSymbols > self.candidate.foreignSymbols
            or self.newMatchAmbiguities > self.candidate.ambiguousBoards
            or self.degradedInstances
            > self.candidate.borderline + self.candidate.clipped + self.candidate.missing
        ):
            raise ValueError("CONTENT_DEGRADATION_COUNTS_INVALID")
        return self


class ContentGameEvidence(ClosedContent):
    gameId: UUID
    state: Literal["ready", "not_evaluable"]
    reasonCodes: list[str]
    u: Unit | None
    delta: Unit | None
    measurementSha256: SHA | None
    classifierSnapshotSha256s: list[SHA]
    renderConfigurationSha256s: list[SHA]
    freshRegression: bool
    roles: dict[Literal["VALIDATION", "REGRESSION"], ContentRoleEvidence]

    @model_validator(mode="after")
    def evidence(self) -> ContentGameEvidence:
        if set(self.roles) != set(ROLES):
            raise ValueError("CONTENT_ROLE_SCOPE_INVALID")
        if self.state == "ready" and (
            self.reasonCodes
            or self.u is None
            or self.delta is None
            or self.u > 0.02
            or self.delta > 0.002
            or self.measurementSha256 is None
            or not self.classifierSnapshotSha256s
            or not self.renderConfigurationSha256s
        ):
            raise ValueError("CONTENT_UNCERTAINTY_EVIDENCE_INVALID")
        if self.state == "not_evaluable" and not self.reasonCodes:
            raise ValueError("CONTENT_UNCERTAINTY_REASON_REQUIRED")
        return self


def decide_game(
    *,
    training: bool,
    parity_passed: bool,
    roles: Mapping[str, Any],
    content: ContentGameEvidence,
    base_version_id: str,
) -> dict[str, Any]:
    """An improvement never cancels a new error of another labelled instance."""
    reasons = list(content.reasonCodes)
    if content.state != "ready":
        reasons.append("CONTENT_REFERENCE_NOT_EVALUABLE")
    if base_version_id != BASE_VERSION_ID:
        reasons.append("CONTENT_REQUIRED_BASE_MISSING")
    if not parity_passed:
        reasons.append("CANDIDATE_PARITY_FAILED")
    for role in ROLES:
        before, after = (require_metrics(roles[role][name]) for name in ("base", "candidate"))
        evidence = content.roles[role]
        if (
            any(
                before[k] != after[k]
                for k in ("photos", "full_photos", "partial_photos", "boards_expected")
            )
            or before["photos"] != roles[role]["photos"]
            or before["photos"] != evidence.photos
            or before["boards_expected"] * 15 != evidence.slots
            or evidence.fullPhotos > before["full_photos"]
            or evidence.base.usableBoards > before["boards_correct"]
            or evidence.candidate.usableBoards > after["boards_correct"]
            # D591's minimum population is REG-only. A keeps its measured,
            # nonempty denominator; cohort admission has separate requirements.
            or role == "REGRESSION"
            and (evidence.photos < 5 or before["boards_expected"] < 15)
        ):
            reasons.append("CONTENT_COVERAGE_INCOMPLETE:" + role)
        if evidence.state != "ready":
            reasons.extend(f"{code}:{role}" for code in evidence.reasonCodes)
        if evidence.slots == 0 or evidence.unknown * 10 > evidence.slots:
            reasons.append("CONTENT_UNKNOWN_LIMIT:" + role)
    if not content.freshRegression or content.roles["REGRESSION"].fullPhotos < 5:
        reasons.append("CONTENT_FRESH_REGRESSION_REQUIRED")
    if reasons:
        return {
            "validation": "not_evaluable",
            "regression": "not_evaluable",
            "coverage": "incomplete",
            "reasons": sorted(set(reasons)),
        }
    decisions = {}
    assert content.delta is not None
    for role in ROLES:
        before, after = (roles[role][name] for name in ("base", "candidate"))
        evidence = content.roles[role]
        start = len(reasons)
        for metric in (
            "boards_matched",
            "boards_correct",
            "board_correct_rate",
            "detection_recall",
        ):
            if after[metric] < before[metric]:
                reasons.append(f"{role}_REGRESSED:{metric}")
        if Decimal(str(after["normalized_error"])) > (
            Decimal(str(before["normalized_error"])) + Decimal(str(content.delta))
        ):
            reasons.append(f"{role}_REGRESSED:normalized_error")
        if before["full_photos"]:
            for metric in ("photo_complete_correct", "photo_complete_correct_rate"):
                if after[metric] < before[metric]:
                    reasons.append(f"{role}_REGRESSED:{metric}")
            for metric in ("false_boards", "duplicate_predictions"):
                if after[metric] > before[metric]:
                    reasons.append(f"{role}_REGRESSED:{metric}")
        for key in (
            "degradedInstances",
            "newWrongCells",
            "newTies",
            "newForeignSymbols",
            "newMatchAmbiguities",
        ):
            if getattr(evidence, key):
                reasons.append(f"{role}_REGRESSED:{key}")
        if (
            training
            and role == "REGRESSION"
            and (evidence.candidate.usableBoards < evidence.base.usableBoards + 1)
        ):
            reasons.append("CONTENT_CURRENT_USABLE_BOARD_GAIN_REQUIRED")
        decisions["validation" if role == "VALIDATION" else "regression"] = (
            "pass" if len(reasons) == start else "fail"
        )
    return {**decisions, "coverage": "complete", "reasons": sorted(set(reasons))}


def attach_content(quality: dict[str, Any], contents: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve the complete historical interpretation as an explicitly nested report."""
    if quality["schemaVersion"] not in {
        "grid-model-evaluation-read-v3",
        "grid-model-evaluation-read-v4",
        "grid-model-evaluation-read-v5",
    }:
        raise ValueError("CONTENT_RAW_REPORT_REQUIRED")
    parsed = [ContentGameEvidence.model_validate(item) for item in contents]
    if [str(item.gameId) for item in parsed] != quality["requiredGameIds"]:
        raise ValueError("CONTENT_REPORT_SCOPE_INVALID")
    games = [
        {
            **game,
            "targetMetric": "production_cell_content",
            **decide_game(
                training=game["gameId"] == quality["trainingGameId"],
                parity_passed=quality["parity"]["passed"],
                roles=game["roles"],
                content=content,
                base_version_id=quality["baseVersionId"],
            ),
        }
        for game, content in zip(quality["games"], parsed, strict=True)
    ]
    return {
        **quality,
        "schemaVersion": REPORT_SCHEMA,
        "ruleVersion": RULE_VERSION,
        "policyVersion": POLICY_VERSION,
        "policy": POLICY,
        "rawQuality": quality,
        "contentEvaluation": [c.model_dump(mode="json") for c in parsed],
        "games": games,
        "verdict": verdict_of(games),
    }


def require_report(
    report_json: str,
    *,
    manifest: Mapping[str, Any],
    base_sha256: str,
    allow_variant_calibration: bool = False,
) -> dict[str, Any]:
    from .full_board_calibration_report import require_report as calibrated_report
    from .grid_correction_evaluation import require_report as correction_report

    try:
        if len(report_json.encode("utf-8")) > MAX_REPORT_BYTES:
            raise ValueError("CONTENT_REPORT_SIZE_LIMIT")
        report = json.loads(report_json)
        if report["schemaVersion"] != REPORT_SCHEMA or canonical_json(report) != report_json:
            raise ValueError("CONTENT_REPORT_INVALID")
        quality = report["rawQuality"]
        reader = calibrated_report if quality["schemaVersion"].endswith("v5") else correction_report
        reader(
            canonical_json(quality),
            manifest=manifest,
            base_sha256=base_sha256,
            allow_content_selection=True,
            **(
                {"allow_variant_calibration": allow_variant_calibration}
                if reader is calibrated_report
                else {}
            ),
        )
        if attach_content(quality, report["contentEvaluation"]) != report:
            raise ValueError("CONTENT_REPORT_DECISION_CHANGED")
        return cast(dict[str, Any], report)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise GridEvaluationReportError(str(error)) from error
