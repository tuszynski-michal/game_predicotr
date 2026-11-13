"""Symbol outline proposals derived from a human-approved board grid (D-608).

The operator draws the 3 x 5 grid on the symbol boundaries, so each grid cell is the
proposed outline of its symbol. The proposal is never a label by itself: it becomes a
content label only after the operator approves it through the ordinary content write.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from .grid_visibility_contract import CellContentReference

OUTLINE_PROPOSAL_VERSION: Final = "grid-cell-outline-proposal-v1"
LATTICE_COLUMNS: Final = 6
LATTICE_ROWS: Final = 4
BOARD_COLUMNS: Final = 5
CELL_COUNT: Final = 15


def outline_proposal_cells(
    nodes: Sequence[Mapping[str, Any]] | None, width: int, height: int
) -> tuple[CellContentReference, ...] | None:
    """Return 15 visible cells whose quads are the grid cells, or None for an unusable grid.

    Nodes are 24 lattice points in source pixels, row-major (4 rows x 6 columns). Points
    are clamped to the source frame; a cell that is not a convex quad makes the whole
    board unusable, because a partial proposal would hide a broken grid.
    """
    if nodes is None or len(nodes) != LATTICE_ROWS * LATTICE_COLUMNS:
        return None
    try:
        points = [
            (
                min(max(float(node["x"]), 0.0), float(width)),
                min(max(float(node["y"]), 0.0), float(height)),
            )
            for node in nodes
        ]
    except (KeyError, TypeError, ValueError):
        return None
    cells = []
    for index in range(CELL_COUNT):
        row, column = divmod(index, BOARD_COLUMNS)
        top = row * LATTICE_COLUMNS + column
        bottom = top + LATTICE_COLUMNS
        quad = (points[top], points[top + 1], points[bottom + 1], points[bottom])
        try:
            cells.append(CellContentReference(state="visible", quad=quad))
        except ValidationError:
            return None
    return tuple(cells)
