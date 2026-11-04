"""Purpose refinement of existing photo roles; no alternative source registry."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any

from .grid_correction_split import BUFFER_PHOTOS, CorrectionSplitSource, _prepare
from .grid_training_cohorts import GridCohortError, digest

PURPOSE_POLICY = "application-grid-corrections-v4"
PURPOSE_SNAPSHOT = "application-grid-snapshot-v4"
PURPOSE_SPLIT = "grid-correction-split-v4"
ASSESSMENT_POLICY = "human-labeled-targets-v1"


def constrain_validation_sources(
    sources: list[CorrectionSplitSource],
    assignments: dict[str, str],
) -> list[CorrectionSplitSource]:
    """Pin explicit components in the existing solver, without optimizing A/B."""
    _, components, _, _, _, _ = _prepare(tuple(sources))
    requested: dict[str, str] = {}
    ids = {source.source_id for source in sources}
    if not assignments.keys() <= ids:
        raise GridCohortError("GRID_VALIDATION_ASSIGNMENT_INVALID", "Unknown source.")
    for key, purpose in assignments.items():
        component = components.find(key)
        if purpose not in {"A", "B", "BUFFER"} or requested.get(component, purpose) != purpose:
            raise GridCohortError(
                "GRID_VALIDATION_COMPONENT_CONFLICT", "A component has one purpose."
            )
        requested[component] = purpose
    result = []
    for source in sources:
        choice = requested.get(components.find(source.source_id))
        if choice is None:
            result.append(source)
            continue
        if (
            source.frozen_role not in (None, "VALIDATION")
            or source.frozen_buffer
            or (choice == "BUFFER" and source.frozen_role is not None)
            or (choice != "BUFFER" and "VALIDATION" not in source.allowed_roles)
        ):
            raise GridCohortError(
                "GRID_VALIDATION_PURPOSE_CONFLICT", "An existing role is protected."
            )
        result.append(
            replace(
                source,
                frozen_role=None if choice == "BUFFER" else "VALIDATION",
                frozen_buffer=choice == "BUFFER",
            )
        )
    return result


def refine_validation_purposes(
    split: dict[str, Any],
    sources: list[CorrectionSplitSource],
    contexts: dict[str, dict[str, Any]],
    assignments: dict[str, str],
    *,
    full_training: bool,
) -> dict[str, Any]:
    """Explicit whole-component refinement, preserving all population and buffers.

    Omitted fresh validation components are A. An explicit BUFFER consumes a whole
    unprotected component; it never releases an existing role. No writes occur here.
    """
    copies, components, orders, _, _, _ = _prepare(tuple(sources))
    source_ids = {source.source_id for source in sources}
    if not assignments.keys() <= source_ids or set(assignments.values()) - {"A", "B", "BUFFER"}:
        raise GridCohortError("GRID_VALIDATION_ASSIGNMENT_INVALID", "Unknown source or purpose.")
    requested: dict[str, set[str]] = defaultdict(set)
    for source_id, purpose in assignments.items():
        requested[components.find(source_id)].add(purpose)
    if any(len(values) != 1 for values in requested.values()):
        raise GridCohortError("GRID_VALIDATION_COMPONENT_CONFLICT", "A component has one purpose.")
    pins = [dict(item) for item in split["sources"]]
    effective: dict[str, str | None] = {}
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for pin in pins:
        key = pin["sourceId"]
        context = contexts[key]
        choice = requested.get(components.find(key))
        role = pin["role"]
        prior = set(context.get("validationPurposes", []))
        if choice and role != "VALIDATION" and not (choice == {"BUFFER"} and role is None):
            raise GridCohortError(
                "GRID_VALIDATION_ASSIGNMENT_INVALID", "Only validation components can be refined."
            )
        purpose = next(iter(choice)) if choice else (next(iter(prior)) if len(prior) == 1 else "A")
        if role == "VALIDATION":
            if len(prior) > 1 or (prior and prior != {purpose}):
                raise GridCohortError(
                    "GRID_VALIDATION_PURPOSE_CONFLICT", "Prior purpose is protected."
                )
            if purpose in {"B", "BUFFER"} and context.get("selectionExposed"):
                raise GridCohortError(
                    "GRID_VALIDATION_SELECTION_EXPOSED", "Legacy selection is A-only."
                )
            if purpose == "B" and context.get("diagnosticExposed"):
                raise GridCohortError(
                    "GRID_VALIDATION_DIAGNOSTIC_EXPOSED", "Diagnostic controls are excluded."
                )
            if purpose == "BUFFER":
                pin.update(role=None, buffer=True, validationPurpose=None, eligibleBoards=0)
                role = None
            else:
                pin["validationPurpose"] = purpose
                count = pin.get("qualifiedBoards", pin["eligibleBoards"])
                excluded = full_training and purpose == "A" and count != 9
                pin.update(eligibleBoards=0 if excluded else count, detectorExcluded=excluded)
        else:
            pin["validationPurpose"] = None
        if role == "REGRESSION" and context.get("diagnosticExposed"):
            raise GridCohortError(
                "GRID_VALIDATION_DIAGNOSTIC_EXPOSED", "Diagnostic regression is excluded."
            )
        pin["purposeProofSha256"] = context["proofSha256"]
        effective[key] = f"VALIDATION-{purpose}" if role == "VALIDATION" else role
        if pin["representative"] and role and pin["eligibleBoards"]:
            label = effective[key]
            assert label is not None
            counts[label]["photos"] += 1
            counts[label]["boards"] += pin["eligibleBoards"]
            counts[label]["fullPhotos"] += int(pin["eligibleBoards"] == 9)
    # Known order counts unique photos, including unlabelled buffers. Unknown
    # imports were already unioned into an indivisible component by _prepare.
    by_photo: dict[str, str | None] = {}
    for source in sources:
        photo = copies.find(source.source_id)
        value = effective[source.source_id]
        if photo in by_photo and by_photo[photo] != value:
            raise GridCohortError("GRID_VALIDATION_COMPONENT_CONFLICT", "Copies differ in purpose.")
        by_photo[photo] = value
    for order in orders:
        previous: tuple[int, str] | None = None
        for index, photo in enumerate(order.photo_keys):
            role = by_photo[photo]
            if role is None:
                continue
            if previous and role != previous[1] and index - previous[0] - 1 < BUFFER_PHOTOS:
                raise GridCohortError(
                    "GRID_VALIDATION_BUFFER_REQUIRED", "Ten unique photos separate roles."
                )
            previous = index, role
    for role, photos, boards in (("TRAIN", 10, 30), ("VALIDATION-A", 5, 15), ("REGRESSION", 5, 15)):
        if counts[role]["photos"] < photos or counts[role]["boards"] < boards:
            raise GridCohortError(
                "GRID_COHORT_MINIMUM_NOT_MET", f"Existing minima are unmet for {role}."
            )
    result = {key: value for key, value in split.items() if key != "sha256"}
    result.update(
        schemaVersion=PURPOSE_SPLIT,
        solverVersion="explicit-validation-components-v1",
        sources=pins,
        validationAssignments=dict(sorted(assignments.items())),
        purposeCounts={key: dict(value) for key, value in sorted(counts.items())},
    )
    return {**result, "sha256": digest(result)}
