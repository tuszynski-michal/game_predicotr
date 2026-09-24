"""Board-panel candidates for the screen-layout v3 engine.

A 3 x 3 results screen always renders its boards on a saturated blue (bottom)
to green (top) background.  Panels are the non-background "holes" inside the
screen.  Detections are deliberately conservative; the layout model later
predicts every panel that is missed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Image = NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class PanelCandidate:
    """One panel quad (TL, TR, BR, BL) in working-image pixels."""

    quad: FloatArray
    width: float
    height: float
    center: FloatArray
    template_match: bool = False


def background_mask(bgr: Image) -> Image:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0].astype(np.int32)
    sat = hsv[..., 1].astype(np.int32)
    val = hsv[..., 2].astype(np.int32)
    blue = (hue >= 95) & (hue <= 135) & (sat >= 80) & (val >= 40)
    green = (hue >= 40) & (hue < 95) & (sat >= 60) & (val >= 35)
    mask = (blue | green).astype(np.uint8) * 255
    return np.asarray(
        cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        ),
        dtype=np.uint8,
    )


def order_quad(points: NDArray[Any]) -> FloatArray:
    """Return TL, TR, BR, BL (image y axis points down)."""

    quad = np.asarray(points, dtype=np.float64).reshape(4, 2)
    center = quad.mean(axis=0)
    angles = np.arctan2(quad[:, 1] - center[1], quad[:, 0] - center[0])
    quad = quad[np.argsort(angles)]
    start = int(np.argmin(quad.sum(axis=1)))
    return np.roll(quad, -start, axis=0)


def _quad_from_contour(contour: NDArray[np.int32]) -> FloatArray:
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for epsilon in np.linspace(0.01, 0.1, 30):
        approx = cv2.approxPolyDP(hull, float(epsilon) * perimeter, True)
        if len(approx) == 4:
            return order_quad(approx.reshape(4, 2))
    return order_quad(cv2.boxPoints(cv2.minAreaRect(contour)))


def _quad_size(quad: FloatArray) -> tuple[float, float]:
    width = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    height = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
    return float(width), float(height)


def screen_hull(bgr: Image) -> NDArray[np.int32] | None:
    """Convex hull of the thick screen-background regions (thin LED strips removed)."""

    height, width = bgr.shape[:2]
    mask = background_mask(bgr)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 80, 3),) * 2)
    thick = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(thick)
    keep = [k for k in range(1, count) if stats[k, cv2.CC_STAT_AREA] >= 0.004 * height * width]
    if not keep:
        return None
    points = np.column_stack(np.nonzero(np.isin(labels, keep)))[:, ::-1].astype(np.int32)
    return np.asarray(cv2.convexHull(points), dtype=np.int32)


def detect_panels(bgr: Image, hull: NDArray[np.int32]) -> list[PanelCandidate]:
    height, width = bgr.shape[:2]
    background = background_mask(bgr)
    screen = np.zeros_like(background)
    cv2.fillPoly(screen, [hull], 255)
    holes = cv2.bitwise_and(screen, cv2.bitwise_not(background))
    holes = cv2.morphologyEx(
        holes, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    opening = max(width // 90, 3)
    holes = cv2.morphologyEx(
        holes, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (opening, opening))
    )
    count, labels, stats, _ = cv2.connectedComponentsWithStats(holes)
    screen_area = float(cv2.contourArea(hull))
    raw: list[PanelCandidate] = []
    for k in range(1, count):
        area = float(stats[k, cv2.CC_STAT_AREA])
        if area < 0.008 * screen_area or area > 0.2 * screen_area:
            continue
        contours, _ = cv2.findContours(
            (labels == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        contour = max(contours, key=cv2.contourArea)
        quad = _quad_from_contour(contour)
        fill = area / max(float(cv2.contourArea(quad.astype(np.float32))), 1.0)
        panel_w, panel_h = _quad_size(quad)
        if (
            fill < 0.85
            or not cv2.isContourConvex(quad.astype(np.float32))
            or not 1.15 < panel_w / max(panel_h, 1.0) < 2.8
        ):
            continue
        raw.append(PanelCandidate(quad, panel_w, panel_h, quad.mean(axis=0)))
    return _consistent_sizes(raw)


def _consistent_sizes(panels: list[PanelCandidate]) -> list[PanelCandidate]:
    if len(panels) < 3:
        return panels
    median_w = float(np.median([p.width for p in panels]))
    median_h = float(np.median([p.height for p in panels]))
    sized = [
        p for p in panels if 0.7 < p.width / median_w < 1.4 and 0.7 < p.height / median_h < 1.4
    ]
    if len(sized) < 3:
        return sized
    aspects = np.array([p.width / p.height for p in sized])
    median_aspect = float(np.median(aspects))
    return [p for p, a in zip(sized, aspects, strict=True) if abs(a / median_aspect - 1) < 0.15]


def texture_map(bgr: Image) -> NDArray[np.float32]:
    lightness = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    mean = cv2.blur(lightness, (5, 5))
    std = np.sqrt(np.maximum(cv2.blur(lightness * lightness, (5, 5)) - mean * mean, 0))
    return (std > 10).astype(np.float32)


def quad_texture(texture: NDArray[np.float32], quad: FloatArray) -> float:
    """Textured fraction of the quad, scaled by the part of it inside the image."""

    mask = np.zeros(texture.shape, np.uint8)
    cv2.fillPoly(mask, [quad.astype(np.int32)], 1)
    area = float(cv2.contourArea(quad.astype(np.float32)))
    inside = float(mask.sum())
    if area <= 0 or inside <= 0:
        return 0.0
    return float((texture * mask).sum() / inside) * min(inside / area, 1.0)


def _edge_map(bgr: Image) -> NDArray[np.float32]:
    gray = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 1.5)
    magnitude = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    return np.asarray(cv2.GaussianBlur(magnitude, (0, 0), 2), dtype=np.float32)


def expand_by_template(
    bgr: Image, panels: list[PanelCandidate], hull: NDArray[np.int32]
) -> list[PanelCandidate]:
    """Find missed panels by matching a detected panel's edge patch (unverified matches)."""

    if not panels:
        return panels
    edges = _edge_map(bgr)
    texture = texture_map(bgr)
    reference_texture = float(np.median([quad_texture(texture, p.quad) for p in panels]))
    reference = sorted(panels, key=lambda p: p.width)[len(panels) // 2]
    x0, y0 = np.floor(reference.quad.min(axis=0)).astype(int)
    x1, y1 = np.ceil(reference.quad.max(axis=0)).astype(int)
    x0, y0 = max(int(x0), 0), max(int(y0), 0)
    x1, y1 = min(int(x1), edges.shape[1] - 1), min(int(y1), edges.shape[0] - 1)
    patch = edges[y0:y1, x0:x1]
    if patch.size == 0:
        return panels
    matches: list[tuple[float, float, tuple[int, int]]] = []
    for scale in (0.8, 0.9, 1.0, 1.1, 1.22):
        template = cv2.resize(patch, None, fx=scale, fy=scale)
        if template.shape[0] >= edges.shape[0] or template.shape[1] >= edges.shape[1]:
            continue
        response = cv2.matchTemplate(edges, template, cv2.TM_CCOEFF_NORMED)
        for _ in range(12):
            _, value, _, location = cv2.minMaxLoc(response)
            if value < 0.35:
                break
            matches.append((float(value), scale, (int(location[0]), int(location[1]))))
            cx, cy = location
            rw, rh = int(template.shape[1] * 0.6), int(template.shape[0] * 0.6)
            response[max(cy - rh, 0) : cy + rh, max(cx - rw, 0) : cx + rw] = -1
    out = list(panels)
    local_quad = reference.quad - np.array([x0, y0], dtype=np.float64)
    for _value, scale, (mx, my) in sorted(matches, reverse=True):
        quad = local_quad * scale + np.array([mx, my], dtype=np.float64)
        center = quad.mean(axis=0)
        if any(np.linalg.norm(center - o.center) < 0.5 * reference.width for o in out):
            continue
        if cv2.pointPolygonTest(hull, (float(center[0]), float(center[1])), False) < 0:
            continue
        if quad_texture(texture, quad) < 0.6 * reference_texture:
            continue
        out.append(
            PanelCandidate(
                quad,
                reference.width * scale,
                reference.height * scale,
                center,
                template_match=True,
            )
        )
    return out
