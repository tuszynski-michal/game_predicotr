"""Rank Mumie A2 automatic 3×5 lattices for human inspection."""

from dataclasses import dataclass
from enum import StrEnum
from math import hypot, isfinite, log
from statistics import median

from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceLatticeNodes,
    SourcePoint,
)

MUMIE_A2_GRID_REVIEW_CODE = "mumie-aktu2"
GRID_CUT_SUSPICION_THRESHOLD = 1.142

# Fitted on 598 before/after pairs, grouped by normalized source checksum.
_EDGE_SCALE = 0.06522734
_SPACING_SCALE = 0.05902060
_ASPECT_SCALE = 0.11071856
_TYPICAL_ASPECT = 1.56874043243


class GridCutReason(StrEnum):
    OPPOSITE_EDGES = "opposite_edges"
    BOARD_ASPECT = "board_aspect"
    LINE_SPACING = "line_spacing"


@dataclass(frozen=True, slots=True)
class GridCutSuspicion:
    score: float
    reason: GridCutReason
    node_indices: tuple[int, int] | None = None
    preferred_cell_indices: tuple[int, ...] = ()


def _point(value: object) -> SourcePoint:
    if not isinstance(value, dict):
        raise ValueError("Lattice points must be objects.")
    x, y = value.get("x"), value.get("y")
    if type(x) not in (float, int) or type(y) not in (float, int):
        raise ValueError("Lattice coordinates must be numeric.")
    return SourcePoint(float(x), float(y))


def _distance(nodes: tuple[SourcePoint, ...], i: int, j: int) -> float:
    return hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y)


def _horizontal_cells(row: int, column: int) -> tuple[int, ...]:
    return tuple(r * 5 + column for r in (row - 1, row) if 0 <= r < 3)


def _vertical_cells(column: int, row: int) -> tuple[int, ...]:
    return tuple(row * 5 + c for c in (column - 1, column) if 0 <= c < 5)


def assess_grid_cut(raw_nodes: object) -> GridCutSuspicion | None:
    """Return an unbounded score, or None for invalid persisted geometry."""

    if not isinstance(raw_nodes, list | tuple) or len(raw_nodes) != 24:
        return None
    try:
        nodes = SourceLatticeNodes(tuple(_point(point) for point in raw_nodes)).nodes
    except (ImageGeometryContractError, ValueError, OverflowError):
        return None

    widths = [_distance(nodes, row * 6, row * 6 + 5) for row in range(4)]
    heights = [_distance(nodes, column, 18 + column) for column in range(6)]
    if any(not isfinite(length) or length <= 0 for length in (*widths, *heights)):
        return None

    short_row = 0 if widths[0] <= widths[-1] else 3
    short_column = 0 if heights[0] <= heights[-1] else 5
    candidates = [
        GridCutSuspicion(
            abs(log(widths[0]) - log(widths[-1])) / _EDGE_SCALE,
            GridCutReason.OPPOSITE_EDGES,
            (6 * short_row, 6 * short_row + 5),
            tuple(range(5)) if short_row == 0 else tuple(range(10, 15)),
        ),
        GridCutSuspicion(
            abs(log(heights[0]) - log(heights[-1])) / _EDGE_SCALE,
            GridCutReason.OPPOSITE_EDGES,
            (short_column, 18 + short_column),
            (0, 5, 10) if short_column == 0 else (4, 9, 14),
        ),
        GridCutSuspicion(
            abs(
                log(sum(width / 4 for width in widths))
                - log(sum(height / 6 for height in heights))
                - log(_TYPICAL_ASPECT)
            )
            / _ASPECT_SCALE,
            GridCutReason.BOARD_ASPECT,
        ),
    ]

    for line_count, segment_count, line_step, segment_step, adjacent in (
        (4, 5, 6, 1, _horizontal_cells),
        (6, 3, 1, 6, _vertical_cells),
    ):
        for line in range(line_count):
            starts = [line * line_step + offset * segment_step for offset in range(segment_count)]
            lengths = [_distance(nodes, index, index + segment_step) for index in starts]
            if any(not isfinite(length) or length <= 0 for length in lengths):
                return None
            typical = median(lengths)
            for offset, (index, length) in enumerate(zip(starts, lengths, strict=True)):
                candidates.append(
                    GridCutSuspicion(
                        abs(log(length) - log(typical)) / _SPACING_SCALE,
                        GridCutReason.LINE_SPACING,
                        (index, index + segment_step),
                        adjacent(line, offset),
                    )
                )

    return max(candidates, key=lambda candidate: candidate.score)
