"""Pure checkpoint and arm preference comparison for full-content export."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .grid_content_experiment import require_selection, selection_key


def _without_nme(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_nme(item) for key, item in value.items() if key != "normalized_error"}
    if isinstance(value, list):
        return [_without_nme(item) for item in value]
    return value


def selection_preserved(
    stored: Mapping[str, Any], replay: Mapping[str, Any], competitors: Sequence[Mapping[str, Any]]
) -> bool:
    """No changed A gate, per-game NME gate or recorded checkpoint/arm preference."""
    before, after = require_selection(stored), require_selection(replay)
    if (before["arm"], before["step"], before["gatePassed"]) != (
        after["arm"],
        after["step"],
        after["gatePassed"],
    ):
        return False
    if [g["gameId"] for g in before["games"]] != [g["gameId"] for g in after["games"]]:
        return False
    for left, right in zip(before["games"], after["games"], strict=True):
        if (
            left["content"] != right["content"]
            or left["auxiliary"] != right["auxiliary"]
            or _without_nme(left["quality"]) != _without_nme(right["quality"])
            or (left["u"], left["delta"]) != (right["u"], right["delta"])
        ):
            return False
        for value in (left, right):
            if value["measurementSha256"] != left["measurementSha256"]:
                return False
        if (
            left["quality"]["candidate"]["normalized_error"]
            <= left["quality"]["base"]["normalized_error"] + left["delta"]
        ) != (
            right["quality"]["candidate"]["normalized_error"]
            <= right["quality"]["base"]["normalized_error"] + right["delta"]
        ):
            return False
    old_key, new_key = selection_key(before), selection_key(after)
    for other in competitors:
        if (other["arm"], other["step"]) == (before["arm"], before["step"]):
            continue
        key = selection_key(other)
        if (old_key < key, old_key > key) != (new_key < key, new_key > key):
            return False
    return True
