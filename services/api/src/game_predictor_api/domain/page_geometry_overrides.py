"""Immutable human corrections for an attested page geometry prefix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

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


__all__ = [
    "ImagePageGeometryOverride",
    "PageGeometryPoint",
    "PageGeometryQuad",
    "PageGeometryQuads",
]
