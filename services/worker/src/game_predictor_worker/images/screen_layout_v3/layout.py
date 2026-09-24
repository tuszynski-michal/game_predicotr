"""3 x 3 layout assignment and the smooth screen model of the v3 engine.

Canonical screen space measures panel widths: panel (column c, row r) spans
``X in [c * pitch_x, c * pitch_x + 1]`` and ``Y in [r * pitch_y, r * pitch_y + 1] * aspect``.
The screen model maps canonical points to image pixels with one homography
followed by one radial term about the image centre, which absorbs the
barrel distortion of wide-angle cameras and curved screens.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .panels import FloatArray, PanelCandidate

Cell = tuple[int, int]  # (column, row) of a board in the 3 x 3 layout
LAYOUT_SIZE = 3
_PARAM_COUNT = 12  # 8 homography, pitch_x, pitch_y, aspect, radial k1
OUTLIER_MIN_CELL_FRACTION = 0.08


@dataclass(frozen=True, slots=True)
class ScreenModel:
    params: FloatArray
    center: FloatArray
    scale: float

    @property
    def pitch_x(self) -> float:
        return float(self.params[8])

    @property
    def pitch_y(self) -> float:
        return float(self.params[9])

    @property
    def aspect(self) -> float:
        return float(self.params[10])

    def project(self, canonical: FloatArray) -> FloatArray:
        return project(self.params, canonical, self.center, self.scale)

    def canonical(self, cell: Cell, u: FloatArray, v: FloatArray) -> FloatArray:
        """Panel-local (u, v) in panel units -> canonical screen coordinates."""

        column, row = cell
        return np.column_stack([column * self.pitch_x + u, (row * self.pitch_y + v) * self.aspect])

    def panel_quad(self, cell: Cell) -> FloatArray:
        u = np.array([0.0, 1.0, 1.0, 0.0])
        v = np.array([0.0, 0.0, 1.0, 1.0])
        return self.project(self.canonical(cell, u, v))


def project(
    params: FloatArray, canonical: FloatArray, center: FloatArray, scale: float
) -> FloatArray:
    homography = np.append(params[:8], 1.0).reshape(3, 3)
    homogeneous = np.column_stack([canonical, np.ones(len(canonical))]) @ homography.T
    undistorted = homogeneous[:, :2] / homogeneous[:, 2:3]
    offset = (undistorted - center) / scale
    radius2 = (offset * offset).sum(axis=1, keepdims=True)
    return np.asarray(center + offset * scale * (1 + params[11] * radius2), dtype=np.float64)


def levenberg_marquardt(
    residual: Callable[[FloatArray], FloatArray], start: FloatArray, iterations: int = 60
) -> FloatArray:
    """Small dense LM with a forward-difference Jacobian (a dozen parameters)."""

    params = start.copy()
    damping = 1e-3
    current = residual(params)
    cost = float(current @ current)
    for _ in range(iterations):
        jacobian = np.zeros((len(current), len(params)))
        for k in range(len(params)):
            step = 1e-6 * max(1.0, abs(float(params[k])))
            shifted = params.copy()
            shifted[k] += step
            jacobian[:, k] = (residual(shifted) - current) / step
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ current
        improved = False
        delta: FloatArray = np.zeros_like(params)
        for _attempt in range(12):
            try:
                delta = np.asarray(
                    np.linalg.solve(normal + damping * np.diag(np.diag(normal) + 1e-12), -gradient),
                    dtype=np.float64,
                )
            except np.linalg.LinAlgError:
                damping *= 10
                continue
            candidate = params + delta
            candidate_residual = residual(candidate)
            candidate_cost = float(candidate_residual @ candidate_residual)
            if np.isfinite(candidate_cost) and candidate_cost < cost:
                params, current, cost = candidate, candidate_residual, candidate_cost
                damping /= 3
                improved = True
                break
            damping *= 5
        if not improved or float(np.linalg.norm(delta)) < 1e-10:
            break
    return params


def _panel_frames(panels: Sequence[PanelCandidate]) -> list[FloatArray]:
    frames = []
    for panel in panels:
        q = panel.quad
        ex = ((q[1] - q[0]) + (q[2] - q[3])) / 2
        ey = ((q[3] - q[0]) + (q[2] - q[1])) / 2
        frames.append(np.linalg.inv(np.column_stack([ex, ey])))
    return frames


def assign_cells(
    panels: Sequence[PanelCandidate],
) -> tuple[dict[int, Cell], float, float] | None:
    """Integer layout cells from pairwise offsets measured in each panel's own frame."""

    n = len(panels)
    if n < 3:
        return None
    frames = _panel_frames(panels)
    rel = np.array(
        [[frames[i] @ (panels[j].center - panels[i].center) for j in range(n)] for i in range(n)]
    )
    horizontal = [
        abs(rel[i, j, 0])
        for i in range(n)
        for j in range(n)
        if i != j and abs(rel[i, j, 1]) < 0.4 and 1.0 < abs(rel[i, j, 0]) < 1.9
    ]
    vertical = [
        abs(rel[i, j, 1])
        for i in range(n)
        for j in range(n)
        if i != j and abs(rel[i, j, 0]) < 0.4 and 1.0 < abs(rel[i, j, 1]) < 2.3
    ]
    pitch_x = float(np.median(horizontal)) if horizontal else 1.2
    pitch_y = float(np.median(vertical)) if vertical else 1.5
    best: tuple[tuple[int, int], dict[int, Cell]] | None = None
    for seed in range(n):
        coords: dict[int, Cell] = {seed: (0, 0)}
        stack = [seed]
        while stack:
            i = stack.pop()
            for j in range(n):
                if j in coords:
                    continue
                dc, dr = rel[i, j, 0] / pitch_x, rel[i, j, 1] / pitch_y
                if (
                    abs(dc - round(dc)) < 0.25
                    and abs(dr - round(dr)) < 0.25
                    and abs(round(dc)) <= 2
                    and abs(round(dr)) <= 2
                ):
                    cell = (coords[i][0] + round(dc), coords[i][1] + round(dr))
                    if cell in coords.values():
                        continue
                    coords[j] = cell
                    stack.append(j)
        window = _best_window(coords, panels)
        if window is None:
            continue
        real = sum(1 for k in window if not panels[k].template_match)
        key = (real, len(window))
        if best is None or key > best[0]:
            best = (key, window)
    if best is None:
        return None
    return best[1], pitch_x, pitch_y


def _best_window(
    coords: dict[int, Cell], panels: Sequence[PanelCandidate]
) -> dict[int, Cell] | None:
    cells = np.array(list(coords.values()))
    low, high = cells.min(axis=0), cells.max(axis=0)
    best: tuple[tuple[int, int], dict[int, Cell]] | None = None
    for wc in range(int(low[0]), max(int(low[0]), int(high[0]) - 2) + 1):
        for wr in range(int(low[1]), max(int(low[1]), int(high[1]) - 2) + 1):
            sub = {
                k: (v[0] - wc, v[1] - wr)
                for k, v in coords.items()
                if 0 <= v[0] - wc <= 2 and 0 <= v[1] - wr <= 2
            }
            real = sum(1 for k in sub if not panels[k].template_match)
            key = (real, len(sub))
            if real and (best is None or key > best[0]):
                best = (key, sub)
    if best is None:
        return None
    sub = best[1]
    minimum = np.array(list(sub.values())).min(axis=0)
    return {k: (v[0] - int(minimum[0]), v[1] - int(minimum[1])) for k, v in sub.items()}


def fit_panels(
    panels: Sequence[PanelCandidate],
    cells: dict[int, Cell],
    pitch_x: float,
    pitch_y: float,
    shape: tuple[int, ...],
) -> ScreenModel:
    height, width = shape[:2]
    center = np.array([width / 2, height / 2], dtype=np.float64)
    scale = float(np.hypot(width, height)) / 2
    corner_u = np.array([0.0, 1.0, 1.0, 0.0])
    corner_v = np.array([0.0, 0.0, 1.0, 1.0])
    index = [(cells[i], k) for i in cells for k in range(4)]
    observed = np.array([panels[i].quad[k] for i in cells for k in range(4)], dtype=np.float64)
    aspect = float(np.median([panels[i].height / panels[i].width for i in cells]))

    def canonical(params: FloatArray) -> FloatArray:
        px, py, a = params[8], params[9], params[10]
        return np.array(
            [(c * px + corner_u[k], (r * py + corner_v[k]) * a) for (c, r), k in index],
            dtype=np.float64,
        )

    start = np.zeros(_PARAM_COUNT)
    start[8:11] = [pitch_x, pitch_y, aspect]
    homography, _ = cv2.findHomography(
        canonical(start).astype(np.float32), observed.astype(np.float32)
    )
    if homography is None:
        homography = np.eye(3)
    start[:8] = (homography / homography[2, 2]).ravel()[:8]

    def residual(params: FloatArray) -> FloatArray:
        return (project(params, canonical(params), center, scale) - observed).ravel()

    return ScreenModel(levenberg_marquardt(residual, start), center, scale)


def grid_residuals(
    model: ScreenModel, grid_uv: tuple[FloatArray, FloatArray], measured: dict[Cell, FloatArray]
) -> dict[Cell, float]:
    u, v = grid_uv
    return {
        cell: float(
            np.linalg.norm(model.project(model.canonical(cell, u, v)) - points, axis=1).mean()
        )
        for cell, points in measured.items()
    }


def refit_to_grid(
    model: ScreenModel, grid_uv: tuple[FloatArray, FloatArray], measured: dict[Cell, FloatArray]
) -> tuple[ScreenModel, dict[Cell, float], list[Cell]]:
    """Refit homography, layout pitches and radial term to grid points; drop outlier boards."""

    aspect = float(model.params[10])  # gauge: the homography absorbs a vertical rescale
    u, v = grid_uv
    inliers = list(measured)
    params = model.params

    def full(p11: FloatArray) -> FloatArray:
        return np.concatenate([p11[:10], [aspect], p11[10:11]])

    for _ in range(3):
        cells = list(inliers)

        def residual(p11: FloatArray, cells: list[Cell] = cells) -> FloatArray:
            p = full(p11)
            return np.concatenate(
                [
                    (
                        project(
                            p,
                            ScreenModel(p, model.center, model.scale).canonical(c, u, v),
                            model.center,
                            model.scale,
                        )
                        - measured[c]
                    ).ravel()
                    for c in cells
                ]
            )

        p11 = levenberg_marquardt(residual, np.concatenate([params[:10], params[11:12]]), 40)
        params = full(p11)
        candidate = ScreenModel(params, model.center, model.scale)
        per_board = grid_residuals(candidate, grid_uv, measured)
        median = float(np.median([per_board[c] for c in inliers]))
        cell_px = float(
            np.median(
                [
                    np.linalg.norm(np.diff(measured[c].reshape(4, 6, 2), axis=1), axis=-1).mean()
                    for c in inliers
                ]
            )
        )
        keep = [
            c
            for c in inliers
            if per_board[c] <= max(3 * median, OUTLIER_MIN_CELL_FRACTION * cell_px)
        ]
        if len(keep) == len(inliers) or len(keep) < 3:
            break
        inliers = keep
    final = ScreenModel(params, model.center, model.scale)
    return final, grid_residuals(final, grid_uv, measured), inliers


def all_cells() -> list[Cell]:
    return [(c, r) for r in range(LAYOUT_SIZE) for c in range(LAYOUT_SIZE)]


def shift_cells(cells: dict[int, Cell], dc: int, dr: int) -> dict[int, Cell]:
    return {k: (v[0] + dc, v[1] + dr) for k, v in cells.items()}


def cell_span(cells: dict[int, Cell]) -> NDArray[np.int64]:
    return np.asarray(np.array(list(cells.values())).max(axis=0), dtype=np.int64)
