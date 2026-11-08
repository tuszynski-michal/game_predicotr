"""Separate A menus and B/REG qualifications for actual final raster variants."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from .full_board_calibration import (
    AssessedTarget,
    ReferenceTarget,
    assess_regression,
    make_plan,
    seal_b,
)
from .full_board_calibration_report import LIMITATIONS, AutomaticProfile
from .full_board_variant_calibration_types import (
    VariantAutomaticCalibration,
    VariantAutomaticProfile,
    VariantObservation,
    VariantPrepared,
    VariantReference,
    checked_body,
)
from .full_board_variant_context import VariantContext, require_variant_witness
from .grid_model_registry import descriptor_sha256 as digest

PLAN_VERSION = "full-board-variant-calibration-plan-v1"
SEALED_VERSION = "full-board-variant-calibration-sealed-v1"
RESULT_VERSION = "full-board-variant-calibration-result-v1"


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "sha256": digest(body)}


def _rows(
    values: Sequence[Mapping[str, Any]],
    *,
    selection: bool,
    game: UUID,
    contexts: Mapping[str, VariantContext],
) -> list[dict[str, Any]]:
    parsed: list[VariantReference | VariantObservation] = [
        (VariantReference if selection else VariantObservation).model_validate(row)
        for row in values
    ]
    identities = []
    result = []
    for row in parsed:
        source = row.sourceId if isinstance(row, VariantReference) else row.target.sourceId
        identities.append((str(source), row.target.positionIndex))
        if row.target.gameId != game:
            raise ValueError("VARIANT_OBSERVATION_GAME_CHANGED")
        if row.variantKey is not None:
            if row.variantKey not in contexts or row.witness is None:
                raise ValueError("VARIANT_CONTEXT_NOT_ALLOWED")
            require_variant_witness(
                row.witness.model_dump(mode="json"),
                contexts[row.variantKey].model_dump(mode="json"),
            )
        result.append(row.model_dump(mode="json"))
    if len(identities) != len(set(identities)):
        raise ValueError("VARIANT_TARGET_DUPLICATE")
    return [
        row for _, row in sorted(zip(identities, result, strict=True), key=lambda pair: pair[0])
    ]


def make_variant_plan(
    *,
    game_id: UUID,
    candidate_sha: str,
    baseline_sha: str,
    cohort_id: UUID,
    cohort_manifest_sha: str,
    role_proof_sha: str,
    reference_assessment_sha: str,
    b_assessment_sha: str,
    regression_assessment_sha: str,
    allowed_variants: Sequence[Mapping[str, Any]],
    selection_references: Sequence[Mapping[str, Any]],
    game_log_aspect_reference: float | None,
    b_targets: int,
    b_sources: int,
    regression_targets: int,
    regression_sources: int,
) -> dict[str, Any]:
    contexts = [VariantContext.model_validate(value) for value in allowed_variants]
    contexts.sort(key=lambda context: context.sha256)
    keys = [context.sha256 for context in contexts]
    if (
        not 1 <= len(keys) <= 2
        or len(keys) != len(set(keys))
        or len({c.routingSha256 for c in contexts}) != 1
        or any(c.candidateManifestSha256 != candidate_sha for c in contexts)
        or {c.stage for c in contexts} != ({"baseline", "wide"} if len(keys) == 2 else {"baseline"})
    ):
        raise ValueError("VARIANT_ALLOWED_CONTEXTS_INVALID")
    refs = _rows(
        selection_references, selection=True, game=game_id, contexts={c.sha256: c for c in contexts}
    )
    children: list[dict[str, Any]] = []
    for key in keys:
        plan = make_plan(
            [
                ReferenceTarget.model_validate(row["target"])
                for row in refs
                if row["variantKey"] == key
            ],
            game_id=game_id,
            candidate_sha=candidate_sha,
            baseline_sha=baseline_sha,
            routing_sha=key,
            role_proof_sha=role_proof_sha,
            b_assessment_sha=b_assessment_sha,
            regression_assessment_sha=regression_assessment_sha,
            feature_version="full-board-completeness-features-v2",
        )
        children.append(
            {
                "variantKey": key,
                "plan": plan.model_dump(mode="json"),
                "gameLogAspectReference": game_log_aspect_reference,
            }
        )
    configurations = sum(len(child["plan"]["menu"]) for child in children)
    body = {
        "version": PLAN_VERSION,
        "gameId": str(game_id),
        "candidateManifestSha256": candidate_sha,
        "baselineManifestSha256": baseline_sha,
        "cohortId": str(cohort_id),
        "cohortManifestSha256": cohort_manifest_sha,
        "roleProofSha256": role_proof_sha,
        "referenceAssessmentSha256": reference_assessment_sha,
        "bAssessmentSha256": b_assessment_sha,
        "regressionAssessmentSha256": regression_assessment_sha,
        "allowedVariants": [c.model_dump(mode="json") for c in contexts],
        "selectionReferences": refs,
        "children": children,
        "bTargets": b_targets,
        "bSources": b_sources,
        "regressionTargets": regression_targets,
        "regressionSources": regression_sources,
        "plannedConfigurations": configurations,
        "plannedComparisons": configurations * b_targets,
    }
    return VariantPrepared.model_validate(_seal(body)).model_dump(mode="json")


def require_variant_plan(value: Mapping[str, Any]) -> VariantPrepared:
    parsed = VariantPrepared.model_validate(value)
    aspects = {child.gameLogAspectReference for child in parsed.children}
    if len(aspects) != 1:
        raise ValueError("VARIANT_ASPECT_CHANGED")
    rebuilt = make_variant_plan(
        game_id=parsed.gameId,
        candidate_sha=parsed.candidateManifestSha256,
        baseline_sha=parsed.baselineManifestSha256,
        cohort_id=parsed.cohortId,
        cohort_manifest_sha=parsed.cohortManifestSha256,
        role_proof_sha=parsed.roleProofSha256,
        reference_assessment_sha=parsed.referenceAssessmentSha256,
        b_assessment_sha=parsed.bAssessmentSha256,
        regression_assessment_sha=parsed.regressionAssessmentSha256,
        allowed_variants=[c.model_dump(mode="json") for c in parsed.allowedVariants],
        selection_references=[r.model_dump(mode="json") for r in parsed.selectionReferences],
        game_log_aspect_reference=next(iter(aspects)),
        b_targets=parsed.bTargets,
        b_sources=parsed.bSources,
        regression_targets=parsed.regressionTargets,
        regression_sources=parsed.regressionSources,
    )
    if rebuilt != dict(value):
        raise ValueError("VARIANT_PLAN_CHANGED")
    return parsed


def seal_variant_b(
    prepared: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    plan = require_variant_plan(prepared)
    rows = _rows(
        observations,
        selection=False,
        game=plan.gameId,
        contexts={c.sha256: c for c in plan.allowedVariants},
    )
    if len(rows) != plan.bTargets:
        raise ValueError("VARIANT_B_TARGET_COUNT_CHANGED")
    children: list[dict[str, Any]] = [
        {
            "variantKey": child.variantKey,
            "sealed": seal_b(
                child.plan,
                [
                    AssessedTarget.model_validate(row["target"])
                    for row in rows
                    if row["variantKey"] == child.variantKey
                ],
                inactive_reference_axes=_inactive_axes(
                    prepared, rows, child.variantKey, child.plan.manualWhenApplicable
                ),
            ),
        }
        for child in plan.children
    ]
    return _seal(
        {
            "version": SEALED_VERSION,
            "planSha256": plan.sha256,
            "observations": rows,
            "children": children,
        }
    )


def _inactive_axes(
    prepared: Mapping[str, Any],
    b_rows: Sequence[Mapping[str, Any]],
    key: str,
    missing: Sequence[str],
) -> frozenset[str]:
    references = [r for r in prepared["selectionReferences"] if r["variantKey"] == key]
    observations = [r for r in b_rows if r["variantKey"] == key]
    return frozenset(
        axis
        for axis in missing
        if references
        and all(axis in r["target"]["features"].get("notApplicable", []) for r in references)
        and all(
            axis in r["target"]["candidateFeatures"].get("notApplicable", []) for r in observations
        )
    )


def assess_variant_regression(
    prepared: Mapping[str, Any],
    sealed: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    plan = require_variant_plan(prepared)
    checked_body(dict(sealed), {"planSha256", "observations", "children"}, SEALED_VERSION)
    if seal_variant_b(prepared, sealed["observations"]) != dict(sealed):
        raise ValueError("VARIANT_SEALED_CHANGED")
    rows = _rows(
        observations,
        selection=False,
        game=plan.gameId,
        contexts={c.sha256: c for c in plan.allowedVariants},
    )
    if len(rows) != plan.regressionTargets:
        raise ValueError("VARIANT_REG_TARGET_COUNT_CHANGED")
    used = sorted(
        {
            r["variantKey"]
            for r in [*prepared["selectionReferences"], *sealed["observations"], *rows]
            if r["variantKey"] is not None
        }
    )
    unresolved = any(
        r["variantKey"] is None
        for r in [*prepared["selectionReferences"], *sealed["observations"], *rows]
    )
    children: list[dict[str, Any]] = [
        {
            "variantKey": child.variantKey,
            "result": assess_regression(
                child.plan,
                state["sealed"],
                [
                    AssessedTarget.model_validate(r["target"])
                    for r in rows
                    if r["variantKey"] == child.variantKey
                ],
                inactive_reference_axes=_inactive_axes(
                    prepared,
                    sealed["observations"],
                    child.variantKey,
                    child.plan.manualWhenApplicable,
                ),
            ),
        }
        for child, state in zip(plan.children, sealed["children"], strict=True)
    ]
    reasons = ["VARIANT_BINDING_UNRESOLVED"] if unresolved else []
    if not used:
        reasons.append("VARIANT_NO_OBSERVATIONS")
    reasons.extend(
        "VARIANT_UNQUALIFIED:" + c["variantKey"]
        for c in children
        if c["variantKey"] in used and c["result"]["state"] != "qualified"
    )
    return _seal(
        {
            "version": RESULT_VERSION,
            "planSha256": plan.sha256,
            "sealedSha256": sealed["sha256"],
            "usedVariantKeys": used,
            "state": "unqualified" if reasons else "qualified",
            "reasonCodes": sorted(reasons),
            "children": children,
        }
    )


def _child_results(
    prepared: Mapping[str, Any], sealed: Mapping[str, Any], result: Mapping[str, Any]
) -> tuple[VariantPrepared, list[dict[str, Any]]]:
    plan = require_variant_plan(prepared)
    if seal_variant_b(prepared, sealed["observations"]) != dict(sealed):
        raise ValueError("VARIANT_SEALED_CHANGED")
    checked_body(
        dict(result),
        {"planSha256", "sealedSha256", "usedVariantKeys", "state", "reasonCodes", "children"},
        RESULT_VERSION,
    )
    if (
        result["planSha256"] != plan.sha256
        or result["sealedSha256"] != sealed["sha256"]
        or [r["variantKey"] for r in result["children"]] != [c.variantKey for c in plan.children]
    ):
        raise ValueError("VARIANT_RESULT_CHANGED")
    children = []
    for child, state, verdict in zip(
        plan.children, sealed["children"], result["children"], strict=True
    ):
        s, r = state["sealed"], verdict["result"]
        if r["planSha256"] != child.plan.sha256 or r["sealedSha256"] != s["sha256"]:
            raise ValueError("VARIANT_CHILD_RESULT_CHANGED")
        profile = None
        if r["state"] == "qualified":
            profile = _seal(
                {
                    "version": "full-board-auto-profile-v2",
                    "gameId": str(plan.gameId),
                    "candidateManifestSha256": plan.candidateManifestSha256,
                    "planSha256": child.plan.sha256,
                    "sealedSha256": s["sha256"],
                    "routingSha256": child.variantKey,
                    "configuration": s["configuration"],
                    "gameLogAspectReference": child.gameLogAspectReference,
                    "assessmentScope": "labelled_targets",
                }
            )
            AutomaticProfile.model_validate(profile)
        children.append(
            {
                "variantKey": child.variantKey,
                "state": r["state"],
                "reasonCodes": r["reasonCodes"],
                "b": s["b"],
                "regression": r["regression"],
                "profile": profile,
                "planSha256": child.plan.sha256,
                "sealedSha256": s["sha256"],
                "resultSha256": r["sha256"],
                "plannedConfigurations": len(child.plan.menu),
                "plannedComparisons": len(child.plan.menu) * plan.bTargets,
            }
        )
    return plan, children


def build_variant_profile(
    prepared: Mapping[str, Any], sealed: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any] | None:
    plan, children = _child_results(prepared, sealed, result)
    if result["state"] != "qualified":
        return None
    profile = _seal(
        {
            "version": "full-board-auto-profile-v3",
            "gameId": str(plan.gameId),
            "candidateManifestSha256": plan.candidateManifestSha256,
            "routingSha256": plan.allowedVariants[0].routingSha256,
            "variantPlanSha256": plan.sha256,
            "allowedVariants": prepared["allowedVariants"],
            "usedVariantKeys": result["usedVariantKeys"],
            "variants": [
                {"variantKey": c["variantKey"], "profile": c["profile"]}
                for c in children
                if c["variantKey"] in result["usedVariantKeys"]
            ],
            "assessmentScope": "labelled_targets",
        }
    )
    return VariantAutomaticProfile.model_validate(profile).model_dump(mode="json")


def build_variant_qualification(
    prepared: Mapping[str, Any],
    sealed: Mapping[str, Any],
    result: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    plan, children = _child_results(prepared, sealed, result)
    value = {
        "version": "full-board-calibration-qualification-v3",
        "gameId": str(plan.gameId),
        "state": result["state"],
        "reasonCodes": result["reasonCodes"],
        "allowedVariants": prepared["allowedVariants"],
        "usedVariantKeys": result["usedVariantKeys"],
        "variants": children,
        "profile": build_variant_profile(prepared, sealed, result),
        "evidence": dict(evidence),
        "plannedConfigurations": plan.plannedConfigurations,
        "plannedComparisons": plan.plannedComparisons,
        "roleProofSha256": plan.roleProofSha256,
        "limitations": LIMITATIONS,
    }
    return VariantAutomaticCalibration.model_validate(value).model_dump(mode="json")
