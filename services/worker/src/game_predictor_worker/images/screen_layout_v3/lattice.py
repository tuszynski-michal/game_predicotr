"""Rectification, cross-board alignment and 5 x 3 lattice search of the v3 engine.

Every board of one screen is rendered by the same game, so after rectifying
the nine panels the *fixed* parts (frames, reel separators, backgrounds) agree
between boards while the symbols differ.  The per-pixel spread across boards
therefore highlights exactly the symbol cells; the lattice is the 5 x 3 grid
that best explains that spread.  No per-game template is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .layout import Cell, ScreenModel
from .panels import FloatArray, Image

TILE_WIDTH = 400
TILE_MARGIN = 0.12
ECC_MIN_CORRELATION = 0.5
GRID_COLUMNS = 5
GRID_ROWS = 3
PANEL_TOLERANCE = 0.03


@dataclass(frozen=True, slots=True)
class Lattice:
    """Symbol lattice in tile pixels: origin, cell width and cell height."""

    x0: float
    y0: float
    cell_width: float
    cell_height: float
    score: float


def tile_shape(model: ScreenModel) -> tuple[int, int]:
    width = int(TILE_WIDTH * (1 + 2 * TILE_MARGIN))
    height = int(round(TILE_WIDTH * model.aspect) * (1 + 2 * TILE_MARGIN))
    return height, width


def tile_to_panel(model: ScreenModel, xy: FloatArray) -> tuple[FloatArray, FloatArray]:
    height, width = tile_shape(model)
    u = -TILE_MARGIN + xy[:, 0] / (width - 1) * (1 + 2 * TILE_MARGIN)
    v = -TILE_MARGIN + xy[:, 1] / (height - 1) * (1 + 2 * TILE_MARGIN)
    return u, v


def rectify(bgr: Image, model: ScreenModel, cell: Cell) -> Image:
    height, width = tile_shape(model)
    u = np.linspace(-TILE_MARGIN, 1 + TILE_MARGIN, width)
    v = np.linspace(-TILE_MARGIN, 1 + TILE_MARGIN, height)
    grid_u, grid_v = np.meshgrid(u, v)
    points = model.project(model.canonical(cell, grid_u.ravel(), grid_v.ravel()))
    maps = points.reshape(height, width, 2).astype(np.float32)
    return np.asarray(
        cv2.remap(
            bgr, maps[..., 0], maps[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
        ),
        dtype=np.uint8,
    )


def _gray(tile: Image) -> NDArray[np.float32]:
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return np.asarray(cv2.GaussianBlur(gray, (0, 0), 2), dtype=np.float32)


def ecc_correlation(
    template: NDArray[np.float32], tile: Image, motion: int
) -> tuple[float, NDArray[np.float32]]:
    warp = np.eye(3 if motion == cv2.MOTION_HOMOGRAPHY else 2, 3, dtype=np.float32)
    try:
        correlation, found = cv2.findTransformECC(
            template,
            _gray(tile),
            warp,
            motion,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5),
            cast(Any, None),
            5,
        )
    except cv2.error:
        return 0.0, warp
    return float(correlation), np.asarray(found, dtype=np.float32)


def median_template(tiles: list[Image]) -> NDArray[np.float32]:
    return np.asarray(np.median(np.stack([_gray(t) for t in tiles]), axis=0), dtype=np.float32)


@dataclass(frozen=True, slots=True)
class CongealedTiles:
    warps: list[NDArray[np.float32]]
    aligned: list[Image]
    correlations: list[float]

    @property
    def ok(self) -> list[bool]:
        return [c >= ECC_MIN_CORRELATION for c in self.correlations]


def congeal(tiles: list[Image], iterations: int = 3) -> CongealedTiles:
    """Align every tile to the running median of all aligned tiles (ECC homography)."""

    height, width = tiles[0].shape[:2]
    warps = [np.eye(3, dtype=np.float32) for _ in tiles]
    aligned = list(tiles)
    correlations = [1.0 for _ in tiles]
    for _ in range(iterations):
        usable = [t for t, c in zip(aligned, correlations, strict=True) if c >= ECC_MIN_CORRELATION]
        template = median_template(usable or aligned)
        for k, tile in enumerate(tiles):
            try:
                correlation, found = cv2.findTransformECC(
                    template,
                    _gray(tile),
                    warps[k].copy(),
                    cv2.MOTION_HOMOGRAPHY,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5),
                    cast(Any, None),
                    5,
                )
                warps[k] = np.asarray(found, dtype=np.float32)
                correlations[k] = float(correlation)
            except cv2.error:
                correlations[k] = 0.0
            aligned[k] = np.asarray(
                cv2.warpPerspective(
                    tile, warps[k], (width, height), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
                ),
                dtype=np.uint8,
            )
    return CongealedTiles(warps, aligned, correlations)


def spread_and_median(tiles: list[Image]) -> tuple[NDArray[np.float32], Image]:
    stack = np.stack([cv2.cvtColor(t, cv2.COLOR_BGR2LAB).astype(np.float32) for t in tiles])
    median = np.median(stack, axis=0)
    spread = np.median(np.abs(stack - median), axis=0).sum(axis=-1)
    median_bgr = cv2.cvtColor(median.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return np.asarray(cv2.GaussianBlur(spread, (0, 0), 2), dtype=np.float32), np.asarray(
        median_bgr, dtype=np.uint8
    )


def _integral(values: NDArray[np.floating]) -> NDArray[np.float64]:
    return np.asarray(cv2.integral(values.astype(np.float64)), dtype=np.float64)


def _rect_mean(
    integral: NDArray[np.float64],
    x0: NDArray[np.float64],
    y0: NDArray[np.float64],
    x1: NDArray[np.float64],
    y1: NDArray[np.float64],
) -> NDArray[np.float64]:
    max_y, max_x = integral.shape[0] - 1, integral.shape[1] - 1
    ix0 = np.clip(x0, 0, max_x).astype(int)
    ix1 = np.clip(x1, 0, max_x).astype(int)
    iy0 = np.clip(y0, 0, max_y).astype(int)
    iy1 = np.clip(y1, 0, max_y).astype(int)
    area = np.maximum((ix1 - ix0) * (iy1 - iy0), 1)
    total = integral[iy1, ix1] - integral[iy0, ix1] - integral[iy1, ix0] + integral[iy0, ix0]
    return np.asarray(total / area, dtype=np.float64)


def find_lattice(spread: NDArray[np.float32], median_bgr: Image) -> Lattice:
    """Coarse search at half resolution, then the +-1 cell phase check."""

    factor = 0.5
    small_spread = cv2.resize(spread, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    small_median = cv2.resize(median_bgr, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    found = _search(np.asarray(small_spread, np.float32), np.asarray(small_median, np.uint8))
    return Lattice(
        found.x0 / factor,
        found.y0 / factor,
        found.cell_width / factor,
        found.cell_height / factor,
        found.score,
    )


def _search(spread: NDArray[np.float32], median_bgr: Image) -> Lattice:
    height, width = spread.shape
    normalized = spread / (np.percentile(spread, 95) + 1e-6)
    gray = cv2.cvtColor(median_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    grad_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    grad_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    grad_x /= np.percentile(grad_x, 99) + 1e-6
    grad_y /= np.percentile(grad_y, 99) + 1e-6
    spread_i, grad_x_i, grad_y_i = _integral(normalized), _integral(grad_x), _integral(grad_y)
    lab = cv2.cvtColor(median_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_i = [_integral(lab[..., k]) for k in range(3)]
    cols, rows = GRID_COLUMNS, GRID_ROWS
    # The symbol grid lies inside the board panel (tile minus its margin, small tolerance).
    inset = TILE_MARGIN / (1 + 2 * TILE_MARGIN) - PANEL_TOLERANCE
    lo_x, hi_x = width * inset, width * (1 - inset)
    lo_y, hi_y = height * inset, height * (1 - inset)
    best: Lattice | None = None
    for cell_w in np.arange(width * 0.12, width * 0.2, 2.0):
        for x0 in np.arange(lo_x, hi_x - cols * cell_w, 2.0):
            for cell_h in np.arange(cell_w * 0.7, cell_w * 1.5, 2.0):
                if cell_h * rows > hi_y - lo_y:
                    break
                y0s = np.arange(lo_y, hi_y - rows * cell_h, 2.0)
                if len(y0s) == 0:
                    continue
                full = np.full_like(y0s, 0.0)
                core = np.zeros_like(y0s)
                line = np.zeros_like(y0s)
                edge = np.zeros_like(y0s)
                for j in range(cols):
                    for i in range(rows):
                        core += _rect_mean(
                            spread_i,
                            full + x0 + (j + 0.25) * cell_w,
                            y0s + (i + 0.25) * cell_h,
                            full + x0 + (j + 0.75) * cell_w,
                            y0s + (i + 0.75) * cell_h,
                        )
                for j in range(cols + 1):
                    lx = x0 + j * cell_w
                    t = max(2.0, cell_w * 0.06)
                    line += _rect_mean(
                        spread_i, full + lx - t, y0s, full + lx + t, y0s + rows * cell_h
                    )
                    edge += _rect_mean(
                        grad_x_i, full + lx - t, y0s, full + lx + t, y0s + rows * cell_h
                    )
                for i in range(rows + 1):
                    ly = y0s + i * cell_h
                    t = max(2.0, cell_h * 0.06)
                    line += _rect_mean(
                        spread_i, full + x0, ly - t, full + x0 + cols * cell_w, ly + t
                    )
                    edge += _rect_mean(
                        grad_y_i, full + x0, ly - t, full + x0 + cols * cell_w, ly + t
                    )
                score = (
                    core / (cols * rows) - line / (cols + rows + 2) + 0.5 * edge / (cols + rows + 2)
                )
                k = int(np.argmax(score))
                if best is None or float(score[k]) > best.score:
                    best = Lattice(
                        float(x0), float(y0s[k]), float(cell_w), float(cell_h), float(score[k])
                    )
    if best is None:
        raise ValueError("The tile is too small for a 5 x 3 lattice.")
    return _resolve_phase(best, lab_i, (lo_x, lo_y, hi_x, hi_y))


def _resolve_phase(
    best: Lattice,
    lab_i: list[NDArray[np.float64]],
    bounds: tuple[float, float, float, float],
) -> Lattice:
    """Choose between the lattice and its +-1 cell shifts by column/row appearance consistency."""

    cols, rows = GRID_COLUMNS, GRID_ROWS
    cw, ch = best.cell_width, best.cell_height
    lo_x, lo_y, hi_x, hi_y = bounds

    def one(integral: NDArray[np.float64], x0: float, y0: float, x1: float, y1: float) -> float:
        return float(
            _rect_mean(integral, np.array([x0]), np.array([y0]), np.array([x1]), np.array([y1]))[0]
        )

    def inconsistency(x0: float, y0: float) -> float:
        column_means = np.array(
            [
                [
                    one(lab_i[k], x0 + (j + 0.1) * cw, y0, x0 + (j + 0.9) * cw, y0 + rows * ch)
                    for k in range(3)
                ]
                for j in range(cols)
            ]
        )
        row_means = np.array(
            [
                [
                    one(lab_i[k], x0, y0 + (i + 0.1) * ch, x0 + cols * cw, y0 + (i + 0.9) * ch)
                    for k in range(3)
                ]
                for i in range(rows)
            ]
        )
        return float(
            np.linalg.norm(column_means - np.median(column_means, axis=0), axis=1).max()
            + np.linalg.norm(row_means - np.median(row_means, axis=0), axis=1).max()
        )

    options: list[tuple[float, float, float]] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x0, y0 = best.x0 + dx * cw, best.y0 + dy * ch
            if x0 < lo_x or y0 < lo_y or x0 + cols * cw > hi_x or y0 + rows * ch > hi_y:
                continue
            penalty = 0.0 if (dx, dy) == (0, 0) else 3.0
            options.append((inconsistency(x0, y0) + penalty, x0, y0))
    _, x0, y0 = min(options)
    return Lattice(x0, y0, cw, ch, best.score)


def lattice_points(lattice: Lattice) -> FloatArray:
    """(GRID_ROWS + 1) * (GRID_COLUMNS + 1) grid intersections in tile pixels, row-major."""

    return np.array(
        [
            [lattice.x0 + j * lattice.cell_width, lattice.y0 + i * lattice.cell_height]
            for i in range(GRID_ROWS + 1)
            for j in range(GRID_COLUMNS + 1)
        ],
        dtype=np.float64,
    )


def warp_points(warp: NDArray[np.float32], points: FloatArray) -> FloatArray:
    homogeneous = np.column_stack([points, np.ones(len(points))]) @ warp.astype(np.float64).T
    return np.asarray(homogeneous[:, :2] / homogeneous[:, 2:3], dtype=np.float64)
