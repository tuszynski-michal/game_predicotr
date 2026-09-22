"""Immutable human corrections for an attested page geometry prefix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from game_predictor_api.domain.geometry_qualification import GeometryQualification

type PageGeometryPoint = dict[str, int]
type PageGeometryQuad = tuple[
    PageGeometryPoint,
    PageGeometryPoint,
    PageGeometryPoint,
    PageGeometryPoint,
]
type PageGeometryQuads = tuple[PageGeometryQuad, ...]


@dataclass(frozen=True, slots=True)
class ImagePageGeometryOverride:
    id: UUID
    game_id: UUID
    source_checksum_sha256: str
    image_width: int
    image_height: int
    final_quads: PageGeometryQuads
    revision: int
    actor: str
    decision_checksum_sha256: str
    created_at: datetime
    slot_qualifications: tuple[GeometryQualification, ...] | None = None
    board_frame_quads: PageGeometryQuads | None = None
    symbol_grid_quads: PageGeometryQuads | None = None


@dataclass(frozen=True, slots=True)
class ImagePageSourceExclusion:
    """One checksum-bound source intentionally omitted from a browser import."""

    id: UUID
    game_id: UUID
    browser_selection_id: UUID
    geometry_preflight_job_id: UUID
    source_manifest_checksum_sha256: str
    geometry_manifest_checksum_sha256: str
    source_checksum_sha256: str
    source_relative_path: str
    actor: str
    decision_checksum_sha256: str
    created_at: datetime


__all__ = [
    "ImagePageGeometryOverride",
    "ImagePageSourceExclusion",
    "PageGeometryPoint",
    "PageGeometryQuad",
    "PageGeometryQuads",
]
