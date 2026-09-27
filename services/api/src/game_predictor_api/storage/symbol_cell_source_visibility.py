"""Classify current cell footprints independently of assets and human labels."""

from collections.abc import Mapping
from typing import Literal, cast

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    SOURCE_SUPPORT_EPSILON,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    source_quad_intersects_image,
)

type SourceVisibility = Literal["full", "partial", "outside"]


def current_source_visibilities(
    *, geometry: Mapping[str, object], width: int, height: int, topology: BoardTopology
) -> tuple[SourceVisibility, ...]:
    """Prefer corrected cell footprints over the historical board outline."""
    source = SourceImageBounds(width, height)
    raw_cells = geometry.get("cells")
    footprints: dict[int, SourceQuad] = {}
    if isinstance(raw_cells, list):
        for cell in raw_cells:
            if not isinstance(cell, Mapping):
                raise ValueError("Current cell geometry is malformed.")
            index = int(cell["rowIndex"]) * topology.columns + int(cell["columnIndex"])
            if index in footprints or not 0 <= index < topology.cell_count:
                raise ValueError("Current cell geometry has duplicate or invalid positions.")
            footprints[index] = _quad(cell["sourceQuad"])
    if len(footprints) != topology.cell_count:
        raw = geometry.get(
            "latticeBoundsQuad", geometry.get("symbolGridQuad", geometry.get("quad"))
        )
        grid = _quad(raw)
        grid_footprints = {
            index: grid.cell_quad(
                topology=topology,
                row_index=index // topology.columns,
                column_index=index % topology.columns,
            )
            for index in range(topology.cell_count)
        }
        if footprints:
            if any(
                _visibility(grid_footprints[index], source) != "outside"
                for index in range(topology.cell_count)
                if index not in footprints
            ):
                raise ValueError("Current source geometry is missing visible cell footprints.")
            footprints.update(
                {index: quad for index, quad in grid_footprints.items() if index not in footprints}
            )
        else:
            footprints = grid_footprints
    return tuple(_visibility(footprints[index], source) for index in range(topology.cell_count))


def qualification_visibilities(
    raw: Mapping[str, object] | None, count: int
) -> tuple[SourceVisibility | None, ...]:
    """Legacy masks are not proof of missing pixels; retain unknown until audit."""
    if raw is None:
        full: SourceVisibility = "full"
        return (full,) * count
    qualification = GeometryQualification.from_dict(raw)
    # Historical v3 used a corner-only test. It cannot prove zero source area.
    return tuple(
        None if index in qualification.unavailable_cell_indices else "full"
        for index in range(count)
    )


def _visibility(quad: SourceQuad, source: SourceImageBounds) -> SourceVisibility:
    if not source_quad_intersects_image(quad, source):
        return "outside"
    if any(
        point.x < -SOURCE_SUPPORT_EPSILON
        or point.x > source.width - 1 + SOURCE_SUPPORT_EPSILON
        or point.y < -SOURCE_SUPPORT_EPSILON
        or point.y > source.height - 1 + SOURCE_SUPPORT_EPSILON
        for point in quad.corners
    ):
        return "partial"
    return "full"


def _quad(raw: object) -> SourceQuad:
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise ValueError("Current source quad is missing or invalid.")
    points = tuple(SourcePoint(float(point["x"]), float(point["y"])) for point in raw)
    return SourceQuad(cast(tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint], points))
