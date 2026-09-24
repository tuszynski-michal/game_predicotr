"""Screen-layout grid engine v3: RGB screen photo -> nine 5 x 3 symbol grids.

Pipeline (see ``ai_docs/architecture/GRID_ENGINE_V3_PROPOSAL.md``):

1. detect board panels as holes in the blue/green screen background;
2. assign detected panels to 3 x 3 layout cells and fit one smooth screen
   model (homography + radial term); ambiguous offsets are decided by how well
   the predicted panels align with the detected ones;
3. rectify all nine panels, align them to their running median (ECC) and find
   the 5 x 3 lattice from the cross-board spread of the aligned tiles;
4. refit the screen model to the lattice points of every board, rejecting
   boards that disagree with the consensus;
5. derive each board's grid from the model and classify it.

The engine is deterministic, has no per-game template and never writes data.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

import cv2
import numpy as np
from numpy.typing import NDArray

from .lattice import (
    GRID_COLUMNS,
    GRID_ROWS,
    congeal,
    ecc_correlation,
    find_lattice,
    lattice_points,
    median_template,
    rectify,
    spread_and_median,
    tile_to_panel,
    warp_points,
)
from .layout import (
    LAYOUT_SIZE,
    Cell,
    ScreenModel,
    all_cells,
    assign_cells,
    cell_span,
    fit_panels,
    refit_to_grid,
    shift_cells,
)
from .panels import (
    FloatArray,
    PanelCandidate,
    detect_panels,
    expand_by_template,
    screen_hull,
)

SCREEN_LAYOUT_V3_VERSION = "screen-layout-grid-v3-prototype-1"
WORKING_WIDTH = 1200
MIN_BOARD_ALIGNMENT = 0.6
MAX_RESIDUAL_CELL_FRACTION = 0.25
MIN_VISIBLE_CELL_FRACTION = 0.75
FULLY_VISIBLE = 0.98
MIN_MODEL_INLIERS_FOR_PREDICTED_BOARDS = 5
MAX_DISAGREEING_BOARDS = 3
GEOMETRY_REASONS = frozenset(
    {"BOARD_DISAGREES_WITH_SCREEN_MODEL", "BOARD_ALIGNMENT_LOW", "BOARD_NOT_ALIGNED"}
)


class BoardStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"


class ResultStatus(StrEnum):
    DETECTED = "detected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BoardGrid:
    """One board; points are grid intersections in source pixels, row-major 4 x 6."""

    position_index: int
    status: BoardStatus
    reason_codes: tuple[str, ...]
    points: FloatArray
    unavailable_cell_indices: tuple[int, ...]
    residual_px: float | None
    alignment: float
    model_inlier: bool

    @property
    def quad(self) -> FloatArray:
        p = self.points
        return np.array([p[0, 0], p[0, -1], p[-1, -1], p[-1, 0]], dtype=np.float64)

    def cell_quad(self, index: int) -> FloatArray:
        row, column = divmod(index, GRID_COLUMNS)
        p = self.points
        return np.array(
            [p[row, column], p[row, column + 1], p[row + 1, column + 1], p[row + 1, column]],
            dtype=np.float64,
        )


@dataclass(frozen=True, slots=True)
class ScreenLayoutResult:
    status: ResultStatus
    reason_code: str | None
    boards: tuple[BoardGrid, ...]
    metrics: dict[str, float] = field(default_factory=dict)
    version: str = SCREEN_LAYOUT_V3_VERSION


def _failed(reason: str, started: float) -> ScreenLayoutResult:
    return ScreenLayoutResult(
        ResultStatus.FAILED,
        reason,
        (),
        {"processingMs": (time.perf_counter() - started) * 1000},
    )


def _to_bgr(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("The screen-layout engine expects an RGB uint8 image.")
    return np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), dtype=np.uint8)


def detect_screen_layout_v3(rgb: NDArray[np.uint8]) -> ScreenLayoutResult:
    """Detect the nine board grids of one EXIF-normalized RGB screen photo."""

    started = time.perf_counter()
    source = _to_bgr(rgb)
    source_h, source_w = source.shape[:2]
    factor = WORKING_WIDTH / source_w
    work = np.asarray(
        cv2.resize(
            source, (WORKING_WIDTH, int(round(source_h * factor))), interpolation=cv2.INTER_AREA
        ),
        dtype=np.uint8,
    )
    hull = screen_hull(work)
    if hull is None:
        return _failed("SCREEN_BACKGROUND_NOT_FOUND", started)
    panels = detect_panels(work, hull)
    detected_panels = len(panels)
    if 1 <= len(panels) < 6:
        panels = expand_by_template(work, panels, hull)
    real = [p for p in panels if not p.template_match]
    if len(real) >= 3:
        panels = real
    assignment = assign_cells(panels)
    if assignment is None or len(assignment[0]) < 3:
        return _failed("LAYOUT_PANELS_INSUFFICIENT", started)
    cells, pitch_x, pitch_y = assignment
    model, hypothesis_score = _choose_offset(work, hull, panels, cells, pitch_x, pitch_y)

    lattice_score = 0.0
    residuals: dict[Cell, float] = {}
    inliers: list[Cell] = []
    alignment: dict[Cell, float] = {}
    grid_uv: tuple[FloatArray, FloatArray] | None = None
    final_measured: dict[Cell, FloatArray] = {}
    for _round in range(2):
        keys = all_cells()
        tiles = [rectify(work, model, cell) for cell in keys]
        congealed = congeal(tiles)
        usable = [t for t, ok in zip(congealed.aligned, congealed.ok, strict=True) if ok]
        if len(usable) < 3:
            return _failed("BOARD_ALIGNMENT_INSUFFICIENT", started)
        spread, median = spread_and_median(usable)
        lattice = find_lattice(spread, median)
        lattice_score = lattice.score
        tile_points = lattice_points(lattice)
        grid_uv = tile_to_panel(model, tile_points)
        measured: dict[Cell, FloatArray] = {}
        for k, cell in enumerate(keys):
            alignment[cell] = congealed.correlations[k]
            if not congealed.ok[k] or _panel_visibility(model, cell, work.shape) < FULLY_VISIBLE:
                continue
            u, v = tile_to_panel(model, warp_points(congealed.warps[k], tile_points))
            measured[cell] = model.project(model.canonical(cell, u, v))
        if len(measured) < 3:
            return _failed("BOARD_ALIGNMENT_INSUFFICIENT", started)
        final_measured = measured
        model, residuals, inliers = refit_to_grid(model, grid_uv, measured)
    assert grid_uv is not None

    classified = [
        _classify(
            model,
            cell,
            grid_uv,
            factor,
            (source_w, source_h),
            residuals,
            inliers,
            alignment,
            final_measured.get(cell),
        )
        for cell in all_cells()
    ]
    boards = tuple(_screen_consensus_gate(classified))
    return ScreenLayoutResult(
        ResultStatus.DETECTED,
        None,
        boards,
        {
            "detectedPanels": float(detected_panels),
            "hypothesisScore": hypothesis_score,
            "latticeScore": lattice_score,
            "modelInliers": float(len(inliers)),
            "radialK1": float(model.params[11]),
            "processingMs": (time.perf_counter() - started) * 1000,
        },
    )


def _choose_offset(
    work: NDArray[np.uint8],
    hull: NDArray[np.int32],
    panels: Sequence[PanelCandidate],
    cells: dict[int, Cell],
    pitch_x: float,
    pitch_y: float,
) -> tuple[ScreenModel, float]:
    """Place the detected block inside the 3 x 3 layout where the other panels align best."""

    span = cell_span(cells)
    real_keys = [k for k in cells if not panels[k].template_match]
    best: tuple[float, ScreenModel] | None = None
    for dc in range(LAYOUT_SIZE - int(span[0])):
        for dr in range(LAYOUT_SIZE - int(span[1])):
            shifted = shift_cells(cells, dc, dr)
            model = fit_panels(panels, shifted, pitch_x, pitch_y, work.shape)
            real_cells = {shifted[k] for k in real_keys}
            template = median_template([rectify(work, model, c) for c in real_cells])
            scores = [
                ecc_correlation(template, rectify(work, model, c), cv2.MOTION_AFFINE)[0]
                for c in all_cells()
                if c not in real_cells
            ]
            score = float(np.mean(scores)) if scores else 1.0
            # Panels predicted off the screen (cabinet, buttons) make the offset implausible.
            inside = [_hull_fraction(model.panel_quad(c), hull) for c in all_cells()]
            score *= float(np.mean(inside))
            if best is None or score > best[0]:
                best = (score, model)
    assert best is not None
    return best[1], best[0]


def _screen_consensus_gate(boards: list[BoardGrid]) -> list[BoardGrid]:
    """Too many geometric disagreements mean the whole screen fit is untrustworthy."""

    disagreeing = sum(1 for b in boards if GEOMETRY_REASONS.intersection(b.reason_codes))
    if disagreeing <= MAX_DISAGREEING_BOARDS:
        return boards
    return [
        replace(
            b,
            status=BoardStatus.NEEDS_REVIEW,
            reason_codes=(*b.reason_codes, "SCREEN_CONSENSUS_WEAK"),
        )
        for b in boards
    ]


def _hull_fraction(quad: FloatArray, hull: NDArray[np.int32]) -> float:
    area = abs(float(cv2.contourArea(quad.astype(np.float32))))
    if area <= 0:
        return 0.0
    inter, _ = cv2.intersectConvexConvex(quad.astype(np.float32), hull.astype(np.float32))
    return min(float(inter) / area, 1.0)


def _panel_visibility(model: ScreenModel, cell: Cell, shape: tuple[int, ...]) -> float:
    return _visible_fraction(model.panel_quad(cell), shape[1], shape[0])


def _visible_fraction(quad: FloatArray, width: int, height: int) -> float:
    area = abs(float(cv2.contourArea(quad.astype(np.float32))))
    if area <= 0:
        return 0.0
    frame = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    inter, _ = cv2.intersectConvexConvex(quad.astype(np.float32), frame)
    return float(inter) / area


def _classify(
    model: ScreenModel,
    cell: Cell,
    grid_uv: tuple[FloatArray, FloatArray],
    factor: float,
    size: tuple[int, int],
    residuals: dict[Cell, float],
    inliers: list[Cell],
    alignment: dict[Cell, float],
    measured: FloatArray | None,
) -> BoardGrid:
    width, height = size
    u, v = grid_uv
    # A board's own aligned measurement is locally more accurate than the smooth
    # screen model; the model supplies boards that could not be measured.
    source = (
        measured
        if measured is not None and alignment.get(cell, 0.0) >= MIN_BOARD_ALIGNMENT
        else model.project(model.canonical(cell, u, v))
    )
    points = (source / factor).reshape(GRID_ROWS + 1, GRID_COLUMNS + 1, 2)
    column, row = cell
    reasons: list[str] = []
    residual = residuals.get(cell)
    cell_px = float(np.linalg.norm(points[:, 1:] - points[:, :-1], axis=-1).mean())
    inlier = cell in inliers
    board_quad = np.array(
        [points[0, 0], points[0, -1], points[-1, -1], points[-1, 0]], dtype=np.float64
    )
    predicted_only = _visible_fraction(board_quad, width, height) < FULLY_VISIBLE
    if len(inliers) < MIN_MODEL_INLIERS_FOR_PREDICTED_BOARDS:
        reasons.append("SCREEN_MODEL_WEAK")
    if predicted_only:
        # Partly outside the photo: the grid comes from the other boards' consensus.
        if len(inliers) < MIN_MODEL_INLIERS_FOR_PREDICTED_BOARDS:
            reasons.append("SCREEN_MODEL_TOO_WEAK_FOR_CROPPED_BOARD")
    else:
        if residual is None:
            reasons.append("BOARD_NOT_ALIGNED")
        elif not inlier or residual / factor > MAX_RESIDUAL_CELL_FRACTION * cell_px:
            reasons.append("BOARD_DISAGREES_WITH_SCREEN_MODEL")
        if alignment.get(cell, 0.0) < MIN_BOARD_ALIGNMENT:
            reasons.append("BOARD_ALIGNMENT_LOW")

    unavailable: list[int] = []
    vertical_cut = False
    for index in range(GRID_ROWS * GRID_COLUMNS):
        r, c = divmod(index, GRID_COLUMNS)
        quad = np.array(
            [points[r, c], points[r, c + 1], points[r + 1, c + 1], points[r + 1, c]],
            dtype=np.float64,
        )
        if _visible_fraction(quad, width, height) < MIN_VISIBLE_CELL_FRACTION:
            unavailable.append(index)
            if quad[:, 1].min() < 0 or quad[:, 1].max() > height - 1:
                vertical_cut = True
    if vertical_cut:
        reasons.append("BOARD_CROPPED_VERTICALLY")
    missing_columns = sorted({i % GRID_COLUMNS for i in unavailable})
    if unavailable and not vertical_cut:
        whole = all(
            all(r * GRID_COLUMNS + c in unavailable for r in range(GRID_ROWS))
            for c in missing_columns
        )
        lateral = missing_columns == list(range(len(missing_columns))) or missing_columns == list(
            range(GRID_COLUMNS - len(missing_columns), GRID_COLUMNS)
        )
        if not whole or not lateral or len(missing_columns) == GRID_COLUMNS:
            reasons.append("BOARD_CROP_NOT_LATERAL")
    if reasons:
        status = BoardStatus.NEEDS_REVIEW
    elif unavailable:
        status = BoardStatus.PARTIAL
    else:
        status = BoardStatus.COMPLETE
    return BoardGrid(
        position_index=row * LAYOUT_SIZE + column,
        status=status,
        reason_codes=tuple(reasons),
        points=points,
        unavailable_cell_indices=tuple(unavailable),
        residual_px=None if residual is None else residual / factor,
        alignment=alignment.get(cell, 0.0),
        model_inlier=inlier,
    )
