"""Immutable inputs and results for the opt-in geometry comparison workflow."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from game_predictor_api.domain.image_grid_reviews import ImageGridReviewListItem

GRID_SHADOW_VALIDATION_KIND = "grid_geometry_shadow_v3"
GRID_SHADOW_MAX_SOURCES = 20
GridShadowStatus = Literal["needs_review", "failed", "unsupported"]


class GridShadowError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def shadow_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def request_fingerprint(source_ids: tuple[UUID, ...]) -> str:
    if not 1 <= len(source_ids) <= GRID_SHADOW_MAX_SOURCES or len(set(source_ids)) != len(
        source_ids
    ):
        raise GridShadowError(
            "GRID_SHADOW_SOURCES_INVALID", "Select 1–20 unique source images.", status_code=422
        )
    return shadow_digest(sorted(str(value) for value in source_ids))


def validate_shadow_output(output: Mapping[str, object], source: Mapping[str, object]) -> None:
    """Reject impossible results before persistence; no renumbering or truncation."""
    slots = output.get("slots")
    active = source.get("active_board_slots")
    if (
        output.get("schemaVersion") != 1
        or output.get("status") not in {"needs_review", "failed", "unsupported"}
        or not isinstance(slots, list)
        or not isinstance(active, list)
        or len(slots) != len(active)
    ):
        raise GridShadowError(
            "GRID_SHADOW_OUTPUT_INVALID", "Output must preserve every pinned active slot."
        )
    start = int(str(source["sequence_range_start"]))
    for position, slot in zip(active, slots, strict=True):
        if (
            not isinstance(slot, dict)
            or slot.get("positionIndex") != position
            or slot.get("sequenceNumber") != start + int(str(position))
        ):
            raise GridShadowError(
                "GRID_SHADOW_OUTPUT_INVALID", "Output changed an attested slot or sequence number."
            )
        for key in ("baselineNodes24", "neuralNodes24"):
            nodes = slot.get(key)
            if nodes is None:
                continue
            if not isinstance(nodes, list) or len(nodes) != 24:
                raise GridShadowError(
                    "GRID_SHADOW_OUTPUT_INVALID", "A complete 5 × 3 grid requires 24 nodes."
                )
            for node in nodes:
                if not isinstance(node, dict) or any(
                    not isinstance(node.get(axis), int | float)
                    or isinstance(node.get(axis), bool)
                    or not math.isfinite(float(node[axis]))
                    for axis in ("x", "y")
                ):
                    raise GridShadowError(
                        "GRID_SHADOW_OUTPUT_INVALID", "Grid coordinates must be finite numbers."
                    )
        visibility = slot.get("cellVisibility")
        if (
            not isinstance(visibility, list)
            or len(visibility) != 15
            or any(value not in ("full", "partial", "outside", "unknown") for value in visibility)
        ):
            raise GridShadowError(
                "GRID_SHADOW_OUTPUT_INVALID", "Every logical cell needs an explicit visibility."
            )
        if slot.get("state") not in {"needs_review", "missing", "invalid"}:
            raise GridShadowError(
                "GRID_SHADOW_OUTPUT_INVALID", "A shadow grid is never accepted automatically."
            )
    shadow_digest(dict(output))


@dataclass(frozen=True, slots=True)
class GridShadowResult:
    id: UUID
    game_id: UUID
    job_id: UUID
    source_image_id: UUID
    source_checksum_sha256: str
    source_geometry_revision_id: UUID
    source_geometry_revision: int
    source_geometry_checksum_sha256: str
    source_width: int
    source_height: int
    model_profile: str
    model_version: str
    model_manifest_checksum_sha256: str
    source_binding: Mapping[str, object]
    model_binding: Mapping[str, object]
    status: GridShadowStatus
    reasons: tuple[str, ...]
    output: Mapping[str, object]
    output_checksum_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GridShadowResultView:
    result: GridShadowResult
    stale: bool
    review_items: tuple[ImageGridReviewListItem, ...]
    source_asset_review_item_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class GridShadowResultPage:
    items: tuple[GridShadowResultView, ...]
    next_cursor: str | None


__all__ = [
    "GRID_SHADOW_MAX_SOURCES",
    "GRID_SHADOW_VALIDATION_KIND",
    "GridShadowError",
    "GridShadowResult",
    "GridShadowResultPage",
    "GridShadowResultView",
    "request_fingerprint",
    "shadow_digest",
    "validate_shadow_output",
]
