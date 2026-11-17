"""Rebuildable counts fenced to an exact committed cohort revision and cursor."""

from collections.abc import Iterable, Mapping
from typing import Any

PROGRESS_KEY = "materializationProgressV1"
FIELDS = ("boards", "photos", "full")
Counts = dict[str, dict[str, int]]


def empty_counts(summary: Mapping[str, Any]) -> Counts:
    return {item["role"]: dict.fromkeys(FIELDS, 0) for item in summary["roles"]}


def add_sources(counts: Counts, sources: Iterable[Mapping[str, Any]]) -> None:
    for source in sources:
        if source["used"]:
            count = counts[source["role"]]
            count["boards"] += source["boards"]
            count["photos"] += 1
            count["full"] += source["full"]


def saved_counts(
    summary: Mapping[str, Any], revision: int, source_count: int, *, cursor: int | None = None
) -> Counts | None:
    progress = summary.get(PROGRESS_KEY)
    if (
        not isinstance(progress, dict)
        or type(progress.get("revision")) is not int
        or progress.get("revision") != revision
    ):
        return None
    through = progress.get("throughCursor")
    if type(through) is not int or not 0 <= through <= source_count:
        return None
    if cursor is not None and through != cursor:
        return None
    if through != source_count and through % 5:
        return None
    values = progress.get("counts")
    if not isinstance(values, dict) or set(values) != set(empty_counts(summary)):
        return None
    result = empty_counts(summary)
    for item in summary["roles"]:
        role = item["role"]
        count = values[role]
        if not isinstance(count, dict) or set(count) != set(FIELDS):
            return None
        limits = {
            "boards": item["eligibleBoards"],
            "photos": item["eligiblePhotos"],
            "full": item["eligibleFullPhotos"],
        }
        if (
            any(
                type(count[field]) is not int or not 0 <= count[field] <= limits[field]
                for field in FIELDS
            )
            or count["full"] > count["photos"]
        ):
            return None
        result[role] = dict(count)
    if sum(count["photos"] for count in result.values()) > through:
        return None
    return result
