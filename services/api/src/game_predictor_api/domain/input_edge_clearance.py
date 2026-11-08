"""A-only suspicion threshold. This is not proof that all content is present."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputEdgeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["VALIDATION-A"] = "VALIDATION-A"
    sourceRepresentativeSha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    variantSha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    clearance: Annotated[float, Field(allow_inf_nan=False)] | None
    inputCropped: bool | None
    synthetic: bool = False
    referenceKind: Literal["geometry_proxy", "verified_content"] = "geometry_proxy"
    contentReferenceSha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    contentRevision: Annotated[int, Field(strict=True, ge=1)] | None = None

    @model_validator(mode="after")
    def content_proof(self) -> InputEdgeReference:
        if self.referenceKind == "verified_content" and (
            self.contentReferenceSha256 is None or self.contentRevision is None
        ):
            raise ValueError("INPUT_EDGE_CONTENT_REFERENCE_REQUIRED")
        if self.referenceKind == "geometry_proxy" and (
            self.contentReferenceSha256 is not None or self.contentRevision is not None
        ):
            raise ValueError("INPUT_EDGE_PROXY_CANNOT_CLAIM_CONTENT")
        return self


def select_input_edge_threshold(
    references: Sequence[InputEdgeReference],
    variant_sha: str,
) -> tuple[float | None, dict[str, int]]:
    """Missed cuts, unnecessary rescue, lower threshold; suspect iff value < threshold."""
    unique: dict[tuple[str, int], InputEdgeReference] = {}
    for item in references:
        if item.variantSha256 != variant_sha:
            raise ValueError("INPUT_EDGE_VARIANT_MISMATCH")
        key = item.sourceRepresentativeSha256, item.positionIndex
        if key in unique and unique[key] != item:
            raise ValueError("INPUT_EDGE_REFERENCE_ALIAS_CONFLICT")
        unique[key] = item
    measured = [
        item
        for item in unique.values()
        if not item.synthetic
        and item.clearance is not None
        and item.inputCropped is not None
        and item.referenceKind == "verified_content"
        and item.contentReferenceSha256 is not None
    ]
    bad = [item for item in measured if item.inputCropped]
    counts = {
        "nTargets": len(measured),
        "nSources": len({x.sourceRepresentativeSha256 for x in measured}),
        "cutTargets": len(bad),
        "cutSources": len({x.sourceRepresentativeSha256 for x in bad}),
    }
    if counts["cutTargets"] < 5 or counts["cutSources"] < 3:
        return None, counts
    values = sorted({float(item.clearance) for item in measured if item.clearance is not None})
    candidates = sorted(set(values + [math.nextafter(x, math.inf) for x in values]))
    candidates = [x for x in candidates if math.isfinite(x)]

    def rank(threshold: float) -> tuple[int, int, float]:
        return (
            sum(item.clearance >= threshold for item in bad if item.clearance is not None),
            sum(
                item.clearance < threshold
                for item in measured
                if not item.inputCropped and item.clearance is not None
            ),
            threshold,
        )

    return min(candidates, key=rank), counts
