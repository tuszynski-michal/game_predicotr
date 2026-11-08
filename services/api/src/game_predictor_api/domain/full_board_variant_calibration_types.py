"""Closed additive contracts; legacy calibration documents keep their exact shapes."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .full_board_calibration import (
    AssessedTarget,
    CalibrationPlan,
    ClosedCalibration,
    Finite,
    ReferenceTarget,
    Sha,
)
from .full_board_calibration_report import AutomaticProfile, CalibrationArtifact, CalibrationCounts
from .full_board_variant_context import PairedWitness, VariantContext
from .grid_model_registry import descriptor_sha256 as digest


class VariantReference(ClosedCalibration):
    sourceId: UUID
    variantKey: Sha | None
    target: ReferenceTarget
    witness: PairedWitness | None
    reasonCode: str | None

    @model_validator(mode="after")
    def binding(self) -> VariantReference:
        _row_binding(
            self.variantKey, self.witness, self.reasonCode, str(self.sourceId), self.target
        )
        if self.target.role != "VALIDATION-A":
            raise ValueError("VARIANT_REFERENCE_ROLE_INVALID")
        return self


class VariantObservation(ClosedCalibration):
    variantKey: Sha | None
    target: AssessedTarget
    witness: PairedWitness | None
    reasonCode: str | None

    @model_validator(mode="after")
    def binding(self) -> VariantObservation:
        _row_binding(
            self.variantKey, self.witness, self.reasonCode, str(self.target.sourceId), self.target
        )
        return self


def _row_binding(
    key: str | None,
    witness: PairedWitness | None,
    reason: str | None,
    source: str,
    target: ReferenceTarget | AssessedTarget,
) -> None:
    if key is None:
        if witness is not None or not isinstance(reason, str) or not reason.strip():
            raise ValueError("VARIANT_UNRESOLVED_ROW_INVALID")
        return
    if witness is None or reason is not None:
        raise ValueError("VARIANT_KNOWN_ROW_INVALID")
    value = witness.model_dump(mode="json")
    if (
        value["variantKey"] != key
        or value["sourceId"] != source
        or value["sourceRepresentativeSha256"] != target.sourceRepresentativeSha256
        or value["positionIndex"] != target.positionIndex
    ):
        raise ValueError("VARIANT_WITNESS_TARGET_CHANGED")
    edge = target.inputEdgeReference
    if edge is not None and edge.variantSha256 != key:
        raise ValueError("VARIANT_INPUT_EDGE_CHANGED")
    features = target.features if isinstance(target, ReferenceTarget) else target.candidateFeatures
    if features.version != "full-board-completeness-features-v2":
        raise ValueError("VARIANT_FEATURE_VERSION_REQUIRED")
    proof = value["inputContentEvidence"]
    if (
        edge is not None
        and edge.referenceKind == "verified_content"
        and (
            edge.contentReferenceSha256 != proof.get("contentReferenceSha256")
            or edge.contentRevision != proof.get("contentReferenceRevision")
            or type(proof.get("inputCropped")) is not bool
            or edge.inputCropped != proof["inputCropped"]
        )
    ):
        raise ValueError("VARIANT_INPUT_EDGE_CONTENT_CHANGED")


class VariantPlanChild(ClosedCalibration):
    variantKey: Sha
    plan: CalibrationPlan
    gameLogAspectReference: Finite | None


class VariantPrepared(ClosedCalibration):
    version: Literal["full-board-variant-calibration-plan-v1"]
    gameId: UUID
    candidateManifestSha256: Sha
    baselineManifestSha256: Sha
    cohortId: UUID
    cohortManifestSha256: Sha
    roleProofSha256: Sha
    referenceAssessmentSha256: Sha
    bAssessmentSha256: Sha
    regressionAssessmentSha256: Sha
    allowedVariants: list[VariantContext] = Field(min_length=1, max_length=2)
    selectionReferences: list[VariantReference]
    children: list[VariantPlanChild] = Field(min_length=1, max_length=2)
    bTargets: int = Field(ge=0)
    bSources: int = Field(ge=0)
    regressionTargets: int = Field(ge=0)
    regressionSources: int = Field(ge=0)
    plannedConfigurations: int = Field(ge=1, le=512)
    plannedComparisons: int = Field(ge=0)
    sha256: Sha

    @model_validator(mode="after")
    def checksum(self) -> VariantPrepared:
        if digest(self.model_dump(mode="json", exclude={"sha256"})) != self.sha256:
            raise ValueError("VARIANT_PLAN_CHECKSUM")
        return self


class VariantProfileChild(ClosedCalibration):
    variantKey: Sha
    profile: AutomaticProfile


class VariantAutomaticProfile(ClosedCalibration):
    version: Literal["full-board-auto-profile-v3"]
    gameId: UUID
    candidateManifestSha256: Sha
    routingSha256: Sha
    variantPlanSha256: Sha
    allowedVariants: list[VariantContext] = Field(min_length=1, max_length=2)
    usedVariantKeys: list[Sha] = Field(min_length=1, max_length=2)
    variants: list[VariantProfileChild] = Field(min_length=1, max_length=2)
    assessmentScope: Literal["labelled_targets"]
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> VariantAutomaticProfile:
        keys = [item.sha256 for item in self.allowedVariants]
        if (
            keys != sorted(set(keys))
            or self.usedVariantKeys != sorted(set(self.usedVariantKeys))
            or not set(self.usedVariantKeys) <= set(keys)
            or [v.variantKey for v in self.variants] != self.usedVariantKeys
            or digest(self.model_dump(mode="json", exclude={"sha256"})) != self.sha256
        ):
            raise ValueError("VARIANT_PROFILE_INVALID")
        for context in self.allowedVariants:
            if (
                context.candidateManifestSha256 != self.candidateManifestSha256
                or context.routingSha256 != self.routingSha256
            ):
                raise ValueError("VARIANT_PROFILE_CONTEXT_CHANGED")
        for child in self.variants:
            if (
                child.profile.version != "full-board-auto-profile-v2"
                or child.profile.gameId != self.gameId
                or child.profile.candidateManifestSha256 != self.candidateManifestSha256
                or child.profile.routingSha256 != child.variantKey
            ):
                raise ValueError("VARIANT_PROFILE_CHILD_CHANGED")
        return self


class VariantQualificationChild(ClosedCalibration):
    variantKey: Sha
    state: Literal["qualified", "unqualified"]
    reasonCodes: list[str]
    b: CalibrationCounts | None
    regression: CalibrationCounts | None
    profile: AutomaticProfile | None
    planSha256: Sha
    sealedSha256: Sha
    resultSha256: Sha
    plannedConfigurations: int = Field(ge=1, le=256)
    plannedComparisons: int = Field(ge=0)

    @model_validator(mode="after")
    def verdict(self) -> VariantQualificationChild:
        from .full_board_calibration import qualification_reasons

        if self.state == "qualified":
            if (
                self.reasonCodes
                or self.b is None
                or self.regression is None
                or self.profile is None
                or qualification_reasons(self.b.model_dump())
                or qualification_reasons(self.regression.model_dump())
            ):
                raise ValueError("VARIANT_CHILD_FALSE_QUALIFICATION")
        elif not self.reasonCodes or self.profile is not None:
            raise ValueError("VARIANT_CHILD_UNQUALIFIED_PROFILE")
        if self.profile is not None and (
            self.profile.version != "full-board-auto-profile-v2"
            or self.profile.planSha256 != self.planSha256
            or self.profile.sealedSha256 != self.sealedSha256
            or self.profile.routingSha256 != self.variantKey
        ):
            raise ValueError("VARIANT_CHILD_PROFILE_CHANGED")
        return self


class VariantAutomaticCalibration(ClosedCalibration):
    version: Literal["full-board-calibration-qualification-v3"]
    gameId: UUID
    state: Literal["qualified", "unqualified"]
    reasonCodes: list[str]
    allowedVariants: list[VariantContext] = Field(min_length=1, max_length=2)
    usedVariantKeys: list[Sha] = Field(max_length=2)
    variants: list[VariantQualificationChild] = Field(min_length=1, max_length=2)
    profile: VariantAutomaticProfile | None
    evidence: CalibrationArtifact | None
    plannedConfigurations: int = Field(ge=1, le=512)
    plannedComparisons: int = Field(ge=0)
    roleProofSha256: Sha
    limitations: list[str]

    @model_validator(mode="after")
    def verdict(self) -> VariantAutomaticCalibration:
        keys = [c.sha256 for c in self.allowedVariants]
        children = {c.variantKey: c for c in self.variants}
        if (
            keys != sorted(set(keys))
            or [c.variantKey for c in self.variants] != keys
            or self.usedVariantKeys != sorted(set(self.usedVariantKeys))
            or not set(self.usedVariantKeys) <= set(keys)
            or sum(c.plannedConfigurations for c in self.variants) != self.plannedConfigurations
            or sum(c.plannedComparisons for c in self.variants) != self.plannedComparisons
        ):
            raise ValueError("VARIANT_QUALIFICATION_SCOPE_CHANGED")
        if self.state == "qualified":
            if (
                self.reasonCodes
                or not self.usedVariantKeys
                or self.evidence is None
                or self.profile is None
                or self.profile.gameId != self.gameId
                or self.profile.allowedVariants != self.allowedVariants
                or self.profile.usedVariantKeys != self.usedVariantKeys
                or any(children[k].state != "qualified" for k in self.usedVariantKeys)
            ):
                raise ValueError("VARIANT_FALSE_QUALIFICATION")
            if any(p.profile != children[p.variantKey].profile for p in self.profile.variants):
                raise ValueError("VARIANT_QUALIFIED_PROFILE_CHANGED")
        elif not self.reasonCodes or self.profile is not None:
            raise ValueError("VARIANT_UNQUALIFIED_PROFILE")
        return self


def checked_body(value: dict[str, Any], keys: set[str], version: str) -> dict[str, Any]:
    if (
        set(value) != keys | {"version", "sha256"}
        or value["version"] != version
        or value["sha256"] != digest({k: v for k, v in value.items() if k != "sha256"})
    ):
        raise ValueError("VARIANT_DOCUMENT_INVALID")
    return value
