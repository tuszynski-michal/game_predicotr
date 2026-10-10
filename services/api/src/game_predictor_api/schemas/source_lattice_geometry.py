"""Shared additive OpenAPI contract for exact source-space lattice nodes."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, FiniteFloat, TypeAdapter

from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.schemas.catalog import ApiModel


class SourceLatticePoint(ApiModel):
    x: FiniteFloat = Field(strict=True)
    y: FiniteFloat = Field(strict=True)


SourceLatticeNodesPayload = Annotated[
    tuple[SourceLatticePoint, ...], Field(min_length=24, max_length=24)
]


def to_source_lattice_nodes(
    value: tuple[SourceLatticePoint, ...] | None,
) -> SourceLatticeNodes | None:
    return (
        None
        if value is None
        else SourceLatticeNodes(tuple(SourcePoint(point.x, point.y) for point in value))
    )


def lattice_nodes_payload(value: object) -> tuple[SourceLatticePoint, ...] | None:
    if value is None:
        return None
    parsed = TypeAdapter(SourceLatticeNodesPayload).validate_python(value)
    to_source_lattice_nodes(parsed)
    return parsed
