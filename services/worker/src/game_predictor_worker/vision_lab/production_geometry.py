"""Pure derivation of 5 x 3 grid nodes and label levels of production boards (TASK-0800).

The read-only production export (``scripts/vision_lab_geometry_export.py``) hands
this module plain stored values: board quads, render-manifest cell quads and
approval/authorship facts. Nothing here reads a database, an image or the
network, and nothing here imports production storage (D-447).

Node convention
---------------
A board is a ``rows x columns`` lattice of cells (3 x 5 for 777), so it has
``(rows + 1) * (columns + 1)`` nodes (24). Nodes are listed row-major: node
``row * (columns + 1) + column`` is the corner shared by the cells around
lattice position ``(row, column)``. A quad is ordered top-left, top-right,
bottom-right, bottom-left, and the lattice node ``(row, column)`` is the
projective image of the unit-square point ``(column / columns, row / rows)``.
That is exactly how the production renderer derives the source quad of every
virtual cell from the board's symbol-grid quad, so a node set derived here must
reproduce the stored render-manifest quads of all 15 cells.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceLatticeNodes,
    SourcePoint,
)

Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]

GRID_ROWS: Final = 3
GRID_COLUMNS: Final = 5
NODE_COUNT: Final = (GRID_ROWS + 1) * (GRID_COLUMNS + 1)
CELL_COUNT: Final = GRID_ROWS * GRID_COLUMNS
COORDINATE_SPACE: Final = "exif-normalized-rgb-pixels-v1"
# Largest accepted distance between a derived cell corner and the stored
# render-manifest corner. The renderer evaluates the same projective formula
# on the stored quad, so a matching quad reproduces the manifest to float noise;
# 0.01 px leaves room for the 4-decimal rounding of stored coordinates only.
NODE_TOLERANCE_PX: Final = 0.01
_CROSS_EPSILON: Final = 1e-8
_DENOMINATOR_EPSILON: Final = 1e-12

# Page layout of the attested sequence: boards are numbered row-major on a 3 x 3
# page (slot semantics ``attested-sequence-row-major-page-3x3-v1``).
PAGE_COLUMNS: Final = 3

LABEL_LEVEL_GOLD: Final = "G"
LABEL_LEVEL_SILVER: Final = "S"
LABEL_LEVEL_BRONZE: Final = "B"
LABEL_LEVEL_UNCLASSIFIED: Final = "U"

# Actors that stand for a person working in the Reviewer or the local admin.
HUMAN_ACTORS: Final = frozenset({"reviewer-operator", "local-admin"})
# System approvals, each with the basis the label level reports.
SYSTEM_APPROVAL_BASES: Final[Mapping[str, str]] = {
    "system:grid-reverify-777-v1": "system_reverify",
    "system:import-qualified-manual-geometry": "system_import_qualified_manual_geometry",
}
LEGACY_CONVERSION_ACTOR: Final = "system:legacy-board-conversion-v1"
ENGINE_PIPELINE_ACTOR_PREFIX: Final = "system:image-pipeline"

EXCLUSION_TOPOLOGY_NOT_5X3: Final = "TOPOLOGY_NOT_5X3"
EXCLUSION_POSITION_OUTSIDE_SLOTS: Final = "POSITION_OUTSIDE_ACTIVE_SLOTS"
EXCLUSION_MANIFEST_MISSING: Final = "RENDER_MANIFEST_MISSING"
EXCLUSION_MANIFEST_MALFORMED: Final = "RENDER_MANIFEST_MALFORMED"
EXCLUSION_QUAD_MISSING: Final = "BOARD_QUAD_MISSING"
EXCLUSION_QUAD_DEGENERATE: Final = "BOARD_QUAD_DEGENERATE"
EXCLUSION_NODES_MISMATCH: Final = "NODES_DO_NOT_MATCH_RENDER_MANIFEST"
EXCLUSION_CELLS_MISSING: Final = "MANIFEST_CELLS_MISSING_WITHOUT_UNAVAILABLE_MASK"
EXCLUSION_INTEGRITY: Final = "BOARD_INTEGRITY_ERROR"
EXCLUSION_HUMAN_APPROVAL_REQUIRED: Final = "NEURAL_GEOMETRY_HUMAN_APPROVAL_REQUIRED"


class ProductionGeometryError(ValueError):
    """A stored geometry cannot be turned into a consistent node set."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def parse_quad(value: object) -> Quad | None:
    """Four finite ``{x, y}`` points of a stored JSON quad, or ``None``.

    Never invents a quad: anything but four numeric, finite points yields ``None``.
    """

    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[Point] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        x = item.get("x")
        y = item.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int | float)
            or not isinstance(y, int | float)
            or not math.isfinite(x)
            or not math.isfinite(y)
        ):
            return None
        points.append((float(x), float(y)))
    return (points[0], points[1], points[2], points[3])


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


def require_valid_quad(quad: Quad) -> None:
    """The quad must be convex, non-self-intersecting and non-degenerate."""

    crosses = [_cross(quad[i], quad[(i + 1) % 4], quad[(i + 2) % 4]) for i in range(4)]
    if any(abs(value) <= _CROSS_EPSILON for value in crosses):
        raise ProductionGeometryError(EXCLUSION_QUAD_DEGENERATE, "the quad has a zero-area corner")
    if not (all(value > 0 for value in crosses) or all(value < 0 for value in crosses)):
        raise ProductionGeometryError(EXCLUSION_QUAD_DEGENERATE, "the quad is not convex")


def project_unit_square_to_quad(quad: Quad, u: float, v: float) -> Point:
    """Square-to-quad projective mapping used by the production cell renderer.

    The affine branch handles parallelograms; the general branch keeps the grid
    lines of a photographed screen straight.
    """

    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    dx1 = x1 - x2
    dx2 = x3 - x2
    dx3 = x0 - x1 + x2 - x3
    dy1 = y1 - y2
    dy2 = y3 - y2
    dy3 = y0 - y1 + y2 - y3
    denominator = dx1 * dy2 - dx2 * dy1
    if abs(denominator) <= _DENOMINATOR_EPSILON:
        g = 0.0
        h = 0.0
    else:
        g = (dx3 * dy2 - dx2 * dy3) / denominator
        h = (dx1 * dy3 - dx3 * dy1) / denominator
    a = x1 - x0 + g * x1
    b = x3 - x0 + h * x3
    d = y1 - y0 + g * y1
    e = y3 - y0 + h * y3
    scale = g * u + h * v + 1.0
    if abs(scale) <= _DENOMINATOR_EPSILON:
        raise ProductionGeometryError(
            EXCLUSION_QUAD_DEGENERATE, "the quad cannot be mapped from the canonical grid"
        )
    return ((a * u + b * v + x0) / scale, (d * u + e * v + y0) / scale)


def derive_grid_nodes(
    quad: Quad, rows: int = GRID_ROWS, columns: int = GRID_COLUMNS
) -> tuple[Point, ...]:
    """The ``(rows + 1) * (columns + 1)`` lattice nodes of ``quad``, row-major."""

    require_valid_quad(quad)
    return tuple(
        project_unit_square_to_quad(quad, column / columns, row / rows)
        for row in range(rows + 1)
        for column in range(columns + 1)
    )


def cell_quads_from_nodes(
    nodes: Sequence[Point], rows: int = GRID_ROWS, columns: int = GRID_COLUMNS
) -> tuple[Quad, ...]:
    """Row-major cell quads (top-left, top-right, bottom-right, bottom-left)."""

    if len(nodes) != (rows + 1) * (columns + 1):
        raise ProductionGeometryError(EXCLUSION_NODES_MISMATCH, "the node count is invalid")
    stride = columns + 1
    return tuple(
        (
            nodes[row * stride + column],
            nodes[row * stride + column + 1],
            nodes[(row + 1) * stride + column + 1],
            nodes[(row + 1) * stride + column],
        )
        for row in range(rows)
        for column in range(columns)
    )


def max_manifest_deviation(
    nodes: Sequence[Point],
    manifest_cells: Mapping[int, Quad],
    rows: int = GRID_ROWS,
    columns: int = GRID_COLUMNS,
) -> float:
    """Largest corner distance (px) between derived cell quads and manifest quads."""

    derived = cell_quads_from_nodes(nodes, rows, columns)
    worst = 0.0
    for index, stored in manifest_cells.items():
        if not 0 <= index < len(derived):
            raise ProductionGeometryError(
                EXCLUSION_NODES_MISMATCH, f"the manifest cell index {index} is outside the grid"
            )
        for expected, actual in zip(derived[index], stored, strict=True):
            worst = max(worst, math.hypot(expected[0] - actual[0], expected[1] - actual[1]))
    return worst


@dataclass(frozen=True, slots=True)
class QuadCandidate:
    """One stored quad that may be the grid quad the manifest was rendered from."""

    source: str
    quad: Quad


@dataclass(frozen=True, slots=True)
class DerivedNodes:
    quad_source: str
    quad: Quad
    nodes: tuple[Point, ...]
    max_deviation_px: float
    manifest_cell_indices: tuple[int, ...]
    missing_cell_indices: tuple[int, ...]


def derive_consistent_lattice_nodes(
    value: object,
    manifest_cells: Mapping[int, Quad],
    unavailable_cell_indices: Iterable[int] = (),
) -> DerivedNodes:
    """Validate the persisted exact lattice against the current rendered cells.

    Never reconstruct a damaged or absent interior from the outer quad. Every
    numeric value is retained without coordinate rounding or interpolation.
    """

    if not isinstance(value, list) or len(value) != NODE_COUNT:
        raise ProductionGeometryError(EXCLUSION_NODES_MISMATCH, "the exact lattice is incomplete")
    points: list[SourcePoint] = []
    try:
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ProductionGeometryError(
                    EXCLUSION_NODES_MISMATCH, "a lattice point is invalid"
                )
            x, y = raw.get("x"), raw.get("y")
            if (
                isinstance(x, bool)
                or isinstance(y, bool)
                or not isinstance(x, int | float)
                or not isinstance(y, int | float)
            ):
                raise ProductionGeometryError(
                    EXCLUSION_NODES_MISMATCH, "a lattice coordinate is invalid"
                )
            points.append(SourcePoint(float(x), float(y)))
        lattice = SourceLatticeNodes(tuple(points))
    except ImageGeometryContractError as error:
        raise ProductionGeometryError(EXCLUSION_NODES_MISMATCH, str(error)) from error
    nodes = tuple((point.x, point.y) for point in lattice.nodes)
    if not manifest_cells:
        raise ProductionGeometryError(EXCLUSION_MANIFEST_MALFORMED, "the manifest has no cells")
    present = tuple(sorted(manifest_cells))
    missing = tuple(index for index in range(CELL_COUNT) if index not in manifest_cells)
    if not set(missing) <= set(unavailable_cell_indices):
        raise ProductionGeometryError(
            EXCLUSION_CELLS_MISSING, "an available lattice cell has no manifest"
        )
    deviation = max_manifest_deviation(nodes, manifest_cells)
    # Both representations persist the same numeric nodes, without projection
    # or rounding. JSON round-trips preserve these doubles; legacy tolerance
    # would conceal a changed cell quad and must not apply to this path.
    if deviation != 0.0:
        raise ProductionGeometryError(
            EXCLUSION_NODES_MISMATCH, "exact nodes differ from rendered cells"
        )
    quad: Quad = (nodes[0], nodes[5], nodes[23], nodes[18])
    return DerivedNodes("persisted_exact_lattice_v1", quad, nodes, deviation, present, missing)


def derive_consistent_nodes(
    candidates: Iterable[QuadCandidate],
    manifest_cells: Mapping[int, Quad],
    unavailable_cell_indices: Iterable[int] = (),
    rows: int = GRID_ROWS,
    columns: int = GRID_COLUMNS,
    tolerance_px: float = NODE_TOLERANCE_PX,
) -> DerivedNodes:
    """Nodes of the first stored quad that reproduces every manifest cell quad.

    The render manifest is the ground truth of the grid the cells were cut from.
    A candidate is accepted only when the nodes it yields reproduce all manifest
    cells within ``tolerance_px``; the accepted candidate's origin is returned.
    Cells absent from the manifest must be listed in ``unavailable_cell_indices``
    (the renderer skips cells without real pixels); any other gap fails.
    """

    if not manifest_cells:
        raise ProductionGeometryError(EXCLUSION_MANIFEST_MALFORMED, "the manifest has no cells")
    present = tuple(sorted(manifest_cells))
    missing = tuple(index for index in range(rows * columns) if index not in manifest_cells)
    if not set(missing) <= set(unavailable_cell_indices):
        raise ProductionGeometryError(
            EXCLUSION_CELLS_MISSING,
            f"manifest cells {missing} are absent but not in the unavailable mask",
        )
    saw_candidate = False
    degenerate: ProductionGeometryError | None = None
    closest: float | None = None
    for candidate in candidates:
        saw_candidate = True
        try:
            nodes = derive_grid_nodes(candidate.quad, rows, columns)
        except ProductionGeometryError as error:
            degenerate = error
            continue
        deviation = max_manifest_deviation(nodes, manifest_cells, rows, columns)
        if deviation <= tolerance_px:
            return DerivedNodes(
                candidate.source, candidate.quad, nodes, deviation, present, missing
            )
        closest = deviation if closest is None else min(closest, deviation)
    if not saw_candidate:
        raise ProductionGeometryError(EXCLUSION_QUAD_MISSING, "the board has no stored grid quad")
    if closest is None and degenerate is not None:
        raise degenerate
    raise ProductionGeometryError(
        EXCLUSION_NODES_MISMATCH,
        f"no stored quad reproduces the manifest cells (closest deviation {closest:.4f} px)",
    )


def quad_area(quad: Quad) -> float:
    """Unsigned shoelace area of a quad."""

    total = 0.0
    for index in range(4):
        x0, y0 = quad[index]
        x1, y1 = quad[(index + 1) % 4]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _edge(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _angle_deviation_deg(previous: Point, corner: Point, following: Point) -> float:
    ux, uy = previous[0] - corner[0], previous[1] - corner[1]
    vx, vy = following[0] - corner[0], following[1] - corner[1]
    norm = math.hypot(ux, uy) * math.hypot(vx, vy)
    if norm == 0:
        return 90.0
    cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / norm))
    return abs(math.degrees(math.acos(cosine)) - 90.0)


def quad_difficulty(quad: Quad) -> dict[str, float]:
    """Geometry-only difficulty metrics of a board quad (no pixels needed).

    ``edgeRatioHorizontal``/``edgeRatioVertical`` are the longer over the shorter
    of the two opposite edges (1.0 = parallel-equal, larger = perspective);
    ``maxAngleDeviationDeg`` is the largest corner deviation from 90 degrees.
    """

    top = _edge(quad[0], quad[1])
    bottom = _edge(quad[3], quad[2])
    left = _edge(quad[0], quad[3])
    right = _edge(quad[1], quad[2])

    def ratio(first: float, second: float) -> float:
        low, high = sorted((first, second))
        return high / low if low > 0 else float("inf")

    deviations = [
        _angle_deviation_deg(quad[(i - 1) % 4], quad[i], quad[(i + 1) % 4]) for i in range(4)
    ]
    return {
        "areaPx": quad_area(quad),
        "edgeRatioHorizontal": ratio(top, bottom),
        "edgeRatioVertical": ratio(left, right),
        "maxAngleDeviationDeg": max(deviations),
    }


def nodes_outside_image(nodes: Sequence[Point], width: int, height: int) -> int:
    """Nodes beyond the pixel-centre bounds of the oriented image."""

    return sum(1 for x, y in nodes if x < 0 or y < 0 or x > width - 1 or y > height - 1)


def page_position(position_index: int) -> dict[str, int | bool]:
    """Row and column of a board slot on the 3 x 3 page, and whether it is outer."""

    row, column = divmod(position_index, PAGE_COLUMNS)
    return {
        "pageRow": row,
        "pageColumn": column,
        "outerColumn": column in (0, PAGE_COLUMNS - 1),
        "outerRow": row in (0, PAGE_COLUMNS - 1),
    }


@dataclass(frozen=True, slots=True)
class LabelFacts:
    """Stored facts that decide the label level of one live board."""

    geometry_revision: int
    approved_geometry_revision: int | None
    approved_by: str | None
    # (revision, corrected_by) of the board's saved geometry revisions, ascending.
    revision_authors: Sequence[tuple[int, str]]
    source_geometry_source: str | None
    source_status: str | None
    source_created_by: str | None


@dataclass(frozen=True, slots=True)
class LabelLevel:
    level: str
    basis: str
    approval_actor: str | None


def classify_label_level(facts: LabelFacts) -> LabelLevel:
    """Label level G/S/B or the explicit unclassified category U (plan table, D-480).

    G: the current geometry is approved by a person (Reviewer, ``local-admin``), or
    the current revision was saved by such a person, or it is the legacy-conversion
    carry-over of a revision a person saved earlier (no approval is recorded for
    these; the basis says so).
    S: the current geometry is approved by a known system actor.
    B: engine geometry nobody approved, in an accepted source revision.
    U: anything else, with the reason as basis. Nothing is guessed.
    """

    approved_current = (
        facts.approved_geometry_revision is not None
        and facts.approved_geometry_revision == facts.geometry_revision
    )
    if approved_current:
        actor = facts.approved_by
        if actor in HUMAN_ACTORS:
            return LabelLevel(LABEL_LEVEL_GOLD, "human_approval", actor)
        if actor is not None and actor in SYSTEM_APPROVAL_BASES:
            return LabelLevel(LABEL_LEVEL_SILVER, SYSTEM_APPROVAL_BASES[actor], actor)
        if actor is not None and actor.startswith("system:"):
            return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "unknown_system_approver", actor)
        return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "unknown_approver", actor)
    authors = dict(facts.revision_authors)
    current_author = authors.get(facts.geometry_revision)
    if current_author in HUMAN_ACTORS:
        return LabelLevel(LABEL_LEVEL_GOLD, "human_saved_revision_unapproved", current_author)
    if current_author == LEGACY_CONVERSION_ACTOR:
        earlier = [
            author
            for revision, author in sorted(facts.revision_authors)
            if revision < facts.geometry_revision and author in HUMAN_ACTORS
        ]
        if earlier:
            return LabelLevel(
                LABEL_LEVEL_GOLD, "human_saved_revision_via_legacy_conversion", earlier[-1]
            )
        return LabelLevel(
            LABEL_LEVEL_UNCLASSIFIED, "legacy_conversion_without_human_revision", None
        )
    if current_author is not None:
        return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "unknown_revision_author", current_author)
    if facts.approved_geometry_revision is not None:
        # Approved an older revision of a board that has since changed.
        return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "approval_of_older_revision", facts.approved_by)
    if facts.geometry_revision == 0 and facts.source_geometry_source == "auto":
        creator = facts.source_created_by or ""
        if creator.startswith(ENGINE_PIPELINE_ACTOR_PREFIX) and facts.source_status == "accepted":
            return LabelLevel(LABEL_LEVEL_BRONZE, "engine_accepted_unapproved", None)
        return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "engine_geometry_not_accepted", None)
    if facts.geometry_revision == 0 and facts.source_geometry_source == "manual":
        return LabelLevel(
            LABEL_LEVEL_UNCLASSIFIED, "manual_source_geometry_without_authorship", None
        )
    return LabelLevel(LABEL_LEVEL_UNCLASSIFIED, "unrecognized_lineage", None)


# --- original production engine output (TASK-0804) --------------------------------------------

# The production engine whose original (pre-correction) output TASK-0804 measures.
ORIGINAL_ENGINE_KIND: Final = "structured_opencv_v1"
ORIGINAL_GEOMETRY_SOURCE: Final = "auto"
MANUAL_GEOMETRY_SOURCE: Final = "manual"
ORIGINAL_MISSING_NO_AUTOMATIC_REVISION: Final = "PRODUCTION_ORIGINAL_NO_AUTOMATIC_REVISION"
ORIGINAL_MISSING_IMAGE_NOT_FOUND: Final = "PRODUCTION_ORIGINAL_IMAGE_NOT_FOUND"
ORIGINAL_MISSING_SOURCE_MISMATCH: Final = "PRODUCTION_ORIGINAL_SOURCE_MISMATCH"
ORIGINAL_BOARD_WITHOUT_GRID: Final = "PRODUCTION_ORIGINAL_BOARD_WITHOUT_GRID"


@dataclass(frozen=True, slots=True)
class RevisionFacts:
    """Lineage facts of one source-geometry revision of an image."""

    revision: int
    geometry_source: str
    engine_kind: str


@dataclass(frozen=True, slots=True)
class OriginalSelection:
    """Which revision is the original production output, and why (or why there is none)."""

    original_revision: int | None
    first_manual_revision: int | None
    missing_reason: str | None


def select_production_original(revisions: Iterable[RevisionFacts]) -> OriginalSelection:
    """The last automatic ``structured_opencv_v1`` revision before the first manual one.

    The production engine writes automatic revisions; a reverification or a person
    writes a later ``manual`` revision and leaves the earlier ones in place. The
    original output is the newest automatic engine revision older than the first
    manual revision (every automatic revision when there is no manual one). An image
    whose lineage has no such revision (for example the pipeline asked for manual
    geometry right away) has no original output; that is reported, never guessed.
    """

    ordered = sorted(revisions, key=lambda item: item.revision)
    manual = [r.revision for r in ordered if r.geometry_source == MANUAL_GEOMETRY_SOURCE]
    first_manual = manual[0] if manual else None
    automatic = [
        r.revision
        for r in ordered
        if r.geometry_source == ORIGINAL_GEOMETRY_SOURCE
        and r.engine_kind == ORIGINAL_ENGINE_KIND
        and (first_manual is None or r.revision < first_manual)
    ]
    if not automatic:
        return OriginalSelection(None, first_manual, ORIGINAL_MISSING_NO_AUTOMATIC_REVISION)
    return OriginalSelection(automatic[-1], first_manual, None)


def original_board_nodes(
    entry: Mapping[str, object],
) -> tuple[tuple[Point, ...] | None, str | None]:
    """24 nodes of one board entry of an engine revision, or ``None`` with the reason.

    The engine's ``symbolGridQuad`` is the grid its cells were rendered from (the TASK-0800
    export reproduced every engine-revision manifest from it at 0.0 px). A board the engine
    left for manual review has no grid quad; that is an explicit missing board.
    """

    quad = parse_quad(entry.get("symbolGridQuad"))
    if quad is None:
        return None, ORIGINAL_BOARD_WITHOUT_GRID
    try:
        return derive_grid_nodes(quad), None
    except ProductionGeometryError as error:
        return None, error.code
