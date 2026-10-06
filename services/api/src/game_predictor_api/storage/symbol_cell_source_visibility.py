"""Classify current cell footprints independently of assets and human labels."""

from collections.abc import Mapping
from typing import Literal, cast

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    SOURCE_SUPPORT_EPSILON,
    SourceImageBounds,
    SourceLatticeNodes,
    SourcePoint,
    SourceQuad,
    source_quad_intersects_image,
)

type SourceVisibility = Literal["full", "partial", "outside"]


def pinned_visibility_geometry(
    *,
    board: Mapping[str, object],
    source: Mapping[str, object],
    source_geometry: Mapping[str, object] | None,
    manual_geometry: Mapping[str, object] | None = None,
) -> Mapping[str, object] | None:
    """Select the adopted revision, never a later revision or a stale board copy."""
    if board.get("asset_mode") != "virtual_source":
        if int(cast(int, board.get("geometry_revision", 0))) > 0:
            if manual_geometry is None or manual_geometry.get("revision") != board.get(
                "geometry_revision"
            ):
                raise ValueError("Current manual geometry revision is missing.")
            geometry = manual_geometry.get("geometry")
        else:
            geometry = board.get("board_geometry")
        return geometry if isinstance(geometry, Mapping) else None
    if (
        source_geometry is None
        or str(source_geometry.get("id")) != str(board.get("source_geometry_revision_id"))
        or str(source_geometry.get("source_image_id")) != str(source.get("id"))
        or source_geometry.get("source_checksum_sha256") != source.get("checksum_sha256")
        or source_geometry.get("geometry_checksum_sha256") != board.get("geometry_checksum_sha256")
        or source_geometry.get("oriented_width") != source.get("oriented_width")
        or source_geometry.get("oriented_height") != source.get("oriented_height")
    ):
        raise ValueError("Pinned source geometry provenance disagrees with the current board.")
    values = source_geometry.get("board_geometries")
    position = board.get("position_index")
    if not isinstance(position, int) or not isinstance(values, list):
        raise ValueError("Pinned source geometry has no current board slot.")
    matches = [
        value
        for value in values
        if isinstance(value, Mapping) and value.get("positionIndex") == position
    ]
    if len(matches) != 1:
        raise ValueError("Pinned source geometry must contain exactly one current board slot.")
    value = dict(matches[0])
    if value.get("positionIndex") != position or value.get("sequenceNumber") != board.get(
        "sequence_number"
    ):
        raise ValueError("Pinned source geometry slot does not own the current sequence.")
    # Source revisions store finalQuad; the projection may contain the original
    # proposal's quad. Never merge those two different sources of geometry.
    value["latticeBoundsQuad"] = value.get("symbolGridQuad") or value.get("finalQuad")
    return value


def current_source_visibilities(
    *, geometry: Mapping[str, object], width: int, height: int, topology: BoardTopology
) -> tuple[SourceVisibility, ...]:
    """Prefer corrected cell footprints over the historical board outline."""
    source = SourceImageBounds(width, height)
    raw_cells = geometry.get("cells")
    footprints: dict[int, SourceQuad] = {}
    nodes = geometry.get("latticeNodes")
    if nodes is not None:
        if not isinstance(nodes, list) or not all(isinstance(point, Mapping) for point in nodes):
            raise ValueError("Current source lattice is malformed.")
        lattice = SourceLatticeNodes(
            tuple(SourcePoint(float(point["x"]), float(point["y"])) for point in nodes)
        )
        footprints = {
            index: lattice.cell_quad(
                topology=topology,
                row_index=index // topology.columns,
                column_index=index % topology.columns,
            )
            for index in range(topology.cell_count)
        }
    elif isinstance(raw_cells, list):
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
