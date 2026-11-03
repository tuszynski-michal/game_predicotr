"""Freeze independent TEST families before choosing the remaining pilot labels."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from game_predictor_worker.symbols.readability_features import FrozenBase, ReadabilityError


def source_keys(row: Mapping[str, Any]) -> set[str]:
    keys = {
        "source:" + str(row["source_id"]),
        "sha:" + row["source_sha256"],
        "rgb:" + row["rendered_pixel_checksum_sha256"],
    }
    if row.get("recording_id"):
        keys.add("recording:" + row["recording_id"])
    return keys


def base_aliases(base: FrozenBase) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for member in base.members:
        family = "base:" + member["family"]
        for key in (
            "source:" + member["sourceId"],
            "sha:" + member["sourceSha256"],
            "rgb:" + member["rgbSha256"],
        ):
            aliases.setdefault(key, set()).add(family)
    return aliases


def freeze_pilot_selection(
    rows: Callable[[], Iterable[dict[str, Any]]],
    base: FrozenBase,
    base_recordings: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    """60/20/20 sample target; family protection always wins over quotas.

    Each iterator is metadata only, with stable source/import/class ordering.
    Labels do not exist yet. TEST is selected first, not recovered from an
    arbitrary 600-cell sample afterwards. Lack of eligible data is a STOP.
    """
    aliases = base_aliases(base)
    exposure: dict[str, set[str]] = {}
    for member in base.members:
        family = "base:" + member["family"]
        exposure.setdefault(family, set()).add(member["split"])
    selected: list[dict[str, Any]] = []
    assignments: dict[str, str] = {}
    selected_ids: set[str] = set()
    # TEST is frozen first. The remaining 480 are disjoint validation/TRAIN.
    for part, quota in (("test", 60), ("validation", 60), ("train", 180)):
        counts = {True: 0, False: 0}
        iterator = iter(rows())
        try:
            for row in iterator:
                historical = row.get("quality_issue") == "unreadable"
                if counts[historical] >= quota or row["cell_id"] in selected_ids:
                    continue
                keys = source_keys(row)
                families = set().union(*(aliases.get(key, set()) for key in keys))
                keys |= families
                seen = set().union(*(exposure.get(family, set()) for family in families))
                recording = row.get("recording_id")
                if isinstance(recording, str):
                    seen |= base_recordings.get(recording, set())
                if part == "test" and seen & {"train", "validation"}:
                    continue
                if part != "test" and seen & {"test", "regression"}:
                    continue
                if any(assignments.get(key, part) != part for key in keys):
                    continue
                for key in keys:
                    assignments[key] = part
                selected.append({**row, "head_split": part, "family_keys": sorted(keys)})
                selected_ids.add(row["cell_id"])
                counts[historical] += 1
                if counts == {True: quota, False: quota}:
                    break
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
        if counts != {True: quota, False: quota}:
            raise ReadabilityError(
                "READABILITY_PILOT_STOP", f"Insufficient independent {part} family strata."
            )
    return selected
