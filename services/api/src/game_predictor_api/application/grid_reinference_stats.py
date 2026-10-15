"""Versioned observations of frozen membership and committed selected-cell effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from game_predictor_api.application.grid_reinference import conflict

STATS_POLICY = "grid-reinference-stats-v1"
SCOPE_FIELDS = (
    "sourceOccurrenceCount",
    "selectedSlotCount",
    "existingBoardCount",
    "deferredSlotCount",
    "existingCellCount",
    "availableCellCount",
    "potentialCellCount",
    "proposalOnlySlotCount",
    "protectedSlotCount",
    "automaticCandidateSlotCount",
)
EFFECT_FIELDS = (
    "recordedTargetCount",
    "automaticWrittenBoardCount",
    "createdBoardCount",
    "createdCellCount",
    "changedExistingPixelCellCount",
    "unchangedExistingPixelCellCount",
    "newlyRequiresReviewCellCount",
    "pixelComparisonUnavailableCellCount",
)


def stats_enabled(document: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    """Absence is historical, never an implicit upgrade to the current policy."""
    if "statsPolicy" not in document and "stats_policy" not in payload:
        return False
    if document.get("statsPolicy") != STATS_POLICY or payload.get("stats_policy") != STATS_POLICY:
        conflict(
            "PAYLOAD_INVALID", "The immutable statistics policy pins differ or are unsupported."
        )
    return True


def empty_scope() -> dict[str, Any]:
    return {"schemaVersion": "grid-reinference-scope-stats-v1", **dict.fromkeys(SCOPE_FIELDS, 0)}


def empty_effect() -> dict[str, Any]:
    return {
        "schemaVersion": "grid-reinference-effect-stats-v1",
        **dict.fromkeys(EFFECT_FIELDS, 0),
        "notRecordedTargetCount": 0,
    }


def refresh_effect_gap(document: dict[str, Any]) -> None:
    """Current frozen membership gap; never an additive per-target effect."""
    if document.get("statsPolicy") != STATS_POLICY or document.get("manifestSha256") is None:
        return
    target_count = document["targetCount"]
    recorded_count = document["effectStats"]["recordedTargetCount"]
    if not 0 <= recorded_count <= target_count:
        conflict("STATS_INVALID", "Recorded targets must belong to the frozen target population.")
    document["effectStats"]["notRecordedTargetCount"] = target_count - recorded_count


def add_counts(total: dict[str, Any], delta: Mapping[str, Any], fields: Sequence[str]) -> None:
    for key in fields:
        total[key] += delta[key]


def frozen_target_counts(
    snapshot: Mapping[str, Any], *, cell_capacity: int, protected: bool
) -> dict[str, Any]:
    result = empty_scope()
    result["selectedSlotCount"] = 1
    result["potentialCellCount"] = cell_capacity
    board = snapshot["board"]
    if board is None:
        result["deferredSlotCount"] = 1
    else:
        result["existingBoardCount"] = 1
        # Current, revision-bound rows only. The frozen snapshot retains other
        # rows for concurrency fences, but they are not current cell population.
        cells = {
            cell["id"]: cell
            for cell in snapshot["cells"]
            if cell["geometry_revision"] == board["geometry_revision"]
            and cell["source_geometry_revision_id"] == board["source_geometry_revision_id"]
        }
        result["existingCellCount"] = len(cells)
        result["availableCellCount"] = sum(cell["source_available"] for cell in cells.values())
    result[
        "protectedSlotCount"
        if protected
        else "proposalOnlySlotCount"
        if snapshot["kind"] == "grid_issue"
        else "automaticCandidateSlotCount"
    ] = 1
    return result


def cell_observation(cell: Any) -> dict[str, Any]:
    """Copy scalars before ORM write-through mutates the same identity map."""
    return {
        "pixels": cell.rendered_pixel_checksum_sha256,
        "available": cell.source_available,
        "verification": cell.verification_outcome,
        "review": cell.review_state,
    }


def cell_effects(
    before: Mapping[int, Mapping[str, Any]],
    after: Mapping[int, Mapping[str, Any]],
    *,
    created_board: bool,
) -> dict[str, Any]:
    result = empty_effect()
    result.update(
        recordedTargetCount=1, automaticWrittenBoardCount=1, createdBoardCount=int(created_board)
    )
    for index, current in after.items():
        old = before.get(index)
        if old is None:
            result["createdCellCount"] += 1
        elif old["pixels"] is None or current["pixels"] is None:
            result["pixelComparisonUnavailableCellCount"] += 1
        else:
            field = (
                "unchangedExistingPixelCellCount"
                if old["pixels"] == current["pixels"]
                else "changedExistingPixelCellCount"
            )
            result[field] += 1
        # A newly materialized cell enters ordinary review; this is recorded
        # independently of pixel changes and must not be summed with them.
        requires = current["available"] and (
            current["verification"] == "requires_review" or current["review"] == "pending"
        )
        previously_required = (
            old is not None
            and old["available"]
            and (old["verification"] == "requires_review" or old["review"] == "pending")
        )
        result["newlyRequiresReviewCellCount"] += int(requires and not previously_required)
    # A disappeared row has no new checksum and cannot prove changed pixels.
    result["pixelComparisonUnavailableCellCount"] += len(before.keys() - after.keys())
    return result
