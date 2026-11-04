"""Metadata-only detector eligibility, using the split's exact copy representatives."""

from collections.abc import Mapping, Sequence
from typing import Any


def detector_readiness(
    counts: Sequence[int], sources: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    full = sum(count == 9 for count in counts)
    partial = sum(0 < count < 9 for count in counts)
    reasons = ["SCREEN_FULL_PHOTOS_REQUIRED"] if full < 15 else []
    roles = []
    for role, required in (("TRAIN", 10), ("VALIDATION", 5), ("REGRESSION", 0)):
        eligible = (
            None
            if sources is None
            else sum(
                item["role"] == role and item["representative"] and item["qualifiedBoards"] == 9
                for item in sources
            )
        )
        missing = None if eligible is None else max(0, required - eligible)
        if missing:
            reasons.append(f"SCREEN_FULL_{role}_REQUIRED")
        roles.append(
            {
                "role": role,
                "requiredFullPhotos": required,
                "eligibleFullPhotos": eligible,
                "missingFullPhotos": missing,
            }
        )
    return {
        "photos": len(counts),
        "fullPhotos": full,
        "partialPhotos": partial,
        "partialExcludedFromDetector": partial,
        "roles": roles,
        "reasonCodes": reasons,
    }
