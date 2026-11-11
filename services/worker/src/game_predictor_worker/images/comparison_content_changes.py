"""Describe paired, verified production-cell evidence without inventing ground truth."""

from collections.abc import Mapping
from typing import Any

_RANK = {"preserved": 0, "borderline": 1, "clipped": 2, "missing": 2}
_FLAGS = ("wrongCell", "tie", "foreignFullSymbol")


def content_change(crops: Mapping[str, Any]) -> dict[str, Any]:
    """Keep new damage visible even when another cell improves in the same board."""
    unresolved = {"state": "unresolved", "improvedCells": 0, "degradedCells": 0}
    if crops.get("state") != "available":
        return unresolved
    models = crops.get("models", {})
    indexes = []
    for name in ("base", "candidate"):
        model = models.get(name, {})
        cells = model.get("cells", [])
        if model.get("state") != "available" or model.get("matchAmbiguous") is not False:
            return unresolved
        if len(cells) != 15:
            return unresolved
        by_index = {cell.get("cellIndex"): cell for cell in cells}
        if set(by_index) != set(range(15)):
            return unresolved
        indexes.append(by_index)
    improved = degraded = 0
    unknown = False
    for index in range(15):
        before, after = indexes[0][index], indexes[1][index]
        if any(cell.get("contentState") != "visible" for cell in (before, after)):
            unknown = True
            continue
        assessments = [cell.get("assessment") for cell in (before, after)]
        if any(not isinstance(value, Mapping) for value in assessments):
            unknown = True
            continue
        old, new = assessments
        if any(value.get("finalContentState") not in _RANK for value in (old, new)):
            unknown = True
            continue
        if any(type(value.get(flag)) is not bool for value in (old, new) for flag in _FLAGS):
            unknown = True
            continue
        old_rank, new_rank = _RANK[old["finalContentState"]], _RANK[new["finalContentState"]]
        worsened = new_rank > old_rank or any(new[flag] and not old[flag] for flag in _FLAGS)
        better = new_rank < old_rank or any(old[flag] and not new[flag] for flag in _FLAGS)
        degraded += int(worsened)
        improved += int(better)
    return {
        "state": (
            "degraded"
            if degraded
            else "unresolved"
            if unknown
            else "improved"
            if improved
            else "unchanged"
        ),
        "improvedCells": improved,
        "degradedCells": degraded,
    }
