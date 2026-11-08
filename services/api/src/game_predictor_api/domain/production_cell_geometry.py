"""Pure source-pixel geometry for production content; no raster or label inference.

Python floats are IEEE float64. Callers supply the actual quantized warp footprint,
intersected with attested pixel support, and the same uncertainty for both models.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal, TypedDict

SOURCE_EPSILON = 1e-6  # source pixels, never a dimensionless coverage tolerance
Point = tuple[float, float]
Polygon = tuple[Point, ...]
PolygonInput = Sequence[Sequence[float]]


class ContentAssessment(TypedDict):
    state: Literal["preserved", "borderline", "clipped", "missing"]
    coverage: float | None
    reason: str | None


class CellAssignment(TypedDict):
    wrongCell: bool
    tie: bool
    foreignFullSymbol: bool


class CoverageMatrix(TypedDict):
    coverage: list[list[float | None]]
    cells: list[CellAssignment]


def _area(polygon: Polygon) -> float:
    if len(polygon) < 3:
        return 0.0
    # Translate before the cross products: large source offsets must not cancel
    # the small area of a symbol near the bottom/right of an image.
    x, y = polygon[0]
    return (
        math.fsum(
            (a[0] - x) * (b[1] - y) - (a[1] - y) * (b[0] - x)
            for a, b in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
        )
        / 2
    )


def _edges(polygon: Polygon) -> list[tuple[Point, Point]]:
    result = []
    for a, b in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        result.append((a, (-dy / length, dx / length)))
    return result


def _distance(point: Point, anchor: Point, normal: Point) -> float:
    return (point[0] - anchor[0]) * normal[0] + (point[1] - anchor[1]) * normal[1]


def _polygon(value: PolygonInput | None, *, quad: bool = False) -> Polygon | None:
    if value is None:
        return None
    try:
        if any(len(point) != 2 for point in value):
            return None
        points = tuple((float(point[0]), float(point[1])) for point in value)
    except (TypeError, ValueError, OverflowError):
        return None
    if quad and len(points) != 4:
        return None
    if not quad and len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3 or any(not math.isfinite(v) for point in points for v in point):
        return None
    if not quad:
        # Clipping may repeat a corner or leave an epsilon-length edge. Removing
        # that numerical edge must not discard the rest of a real support polygon.
        clean = [points[0]]
        for point in points[1:]:
            if math.dist(point, clean[-1]) > SOURCE_EPSILON:
                clean.append(point)
        if len(clean) > 1 and math.dist(clean[-1], clean[0]) <= SOURCE_EPSILON:
            clean.pop()
        points = tuple(clean)
        if len(points) < 3:
            return None
    lengths = [math.dist(a, b) for a, b in zip(points, (*points[1:], points[0]), strict=True)]
    if any(not math.isfinite(length) or length <= SOURCE_EPSILON for length in lengths):
        return None
    try:
        area = _area(points)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(area) or abs(area) <= SOURCE_EPSILON**2:
        return None
    if area < 0:
        points = tuple(reversed(points))
    if quad and any(
        _distance(points[(index + 2) % 4], anchor, normal) <= 0
        for index, (anchor, normal) in enumerate(_edges(points))
    ):
        return None
    # Test every vertex against every oriented edge; a bow-tie or non-convex
    # ordering cannot become valid merely through a positive shoelace area.
    if any(
        _distance(point, anchor, normal) < -SOURCE_EPSILON
        for anchor, normal in _edges(points)
        for point in points
    ):
        return None
    return points


def _clip(polygon: Polygon, anchor: Point, normal: Point, inset: float = 0.0) -> Polygon:
    if not polygon:
        return ()
    result: list[Point] = []
    previous = polygon[-1]
    before = _distance(previous, anchor, normal) - inset
    for point in polygon:
        after = _distance(point, anchor, normal) - inset
        if (before >= 0) != (after >= 0):
            t = before / (before - after)
            result.append(
                (
                    previous[0] + t * (point[0] - previous[0]),
                    previous[1] + t * (point[1] - previous[1]),
                )
            )
        if after >= 0:
            result.append(point)
        previous, before = point, after
    clean: list[Point] = []
    for point in result:
        if not clean or point != clean[-1]:
            clean.append(point)
    if len(clean) > 1 and clean[0] == clean[-1]:
        clean.pop()
    return tuple(clean)


def _intersection(first: Polygon, second: Polygon) -> Polygon:
    result = first
    for anchor, normal in _edges(second):
        result = _clip(result, anchor, normal)
        if len(result) < 3:
            return ()
    return result


def intersect_support(first: PolygonInput, second: PolygonInput) -> list[list[float]]:
    """Intersect convex supports in source XY; absent/invalid/zero-area returns []."""
    a, b = _polygon(first), _polygon(second)
    if a is None or b is None:
        return []
    result = _polygon(_intersection(a, b))
    if result is None:
        return []
    return [[x, y] for x, y in result]


def _contained(content: Polygon, support: Polygon, dilation: float = 0.0) -> bool:
    # For convex support, disk dilation fits exactly iff every support half-plane
    # leaves radius u around every content vertex. No miter approximation is used.
    return all(
        _distance(point, anchor, normal) >= dilation - SOURCE_EPSILON
        for anchor, normal in _edges(support)
        for point in content
    )


def _overlap(content: Polygon, support: Polygon) -> float:
    return min(_area(content), max(0.0, _area(_intersection(content, support))))


def assess_content(
    content_quad: PolygonInput,
    support_polygon: PolygonInput | None,
    uncertainty_pixels: float,
) -> ContentAssessment:
    """Classify a visible reference; missing geometry is never a zero-error result."""
    content = _polygon(content_quad, quad=True)
    if content is None:
        return {"state": "missing", "coverage": None, "reason": "CONTENT_REFERENCE_INVALID"}
    if not math.isfinite(uncertainty_pixels) or uncertainty_pixels < 0:
        return {"state": "missing", "coverage": None, "reason": "CONTENT_UNCERTAINTY_INVALID"}
    if support_polygon is None:
        return {"state": "missing", "coverage": None, "reason": "CONTENT_SUPPORT_MISSING"}
    support = _polygon(support_polygon)
    if support is None:
        return {
            "state": "missing",
            "coverage": None,
            "reason": "CONTENT_SUPPORT_EMPTY"
            if len(support_polygon) == 0
            else "CONTENT_SUPPORT_INVALID",
        }
    coverage = _overlap(content, support) / _area(content)
    eroded = content
    for anchor, normal in _edges(content):
        eroded = _clip(eroded, anchor, normal, uncertainty_pixels)
    if _polygon(eroded) is None:
        return {"state": "borderline", "coverage": coverage, "reason": "CONTENT_EROSION_EMPTY"}
    if _contained(content, support, uncertainty_pixels):
        return {"state": "preserved", "coverage": coverage, "reason": None}
    if not _contained(eroded, support):
        return {"state": "clipped", "coverage": coverage, "reason": "CONTENT_CLIPPED"}
    return {"state": "borderline", "coverage": coverage, "reason": "CONTENT_UNCERTAINTY_BORDERLINE"}


def _area_tolerance(content: Polygon) -> float:
    # Area of an epsilon-wide boundary band [px²], used for comparisons of areas.
    # Two independently computed intersections may each contribute that error.
    perimeter = math.fsum(
        math.dist(a, b) for a, b in zip(content, (*content[1:], content[0]), strict=True)
    )
    return 2 * SOURCE_EPSILON * perimeter + math.pi * SOURCE_EPSILON**2


def coverage_matrix(
    content_quads: Sequence[PolygonInput],
    crop_supports: Sequence[PolygonInput | None],
    proper_crop_indices: Sequence[int | None],
) -> CoverageMatrix:
    """One source-wide matrix, including crops of other boards/unmatched detections.

    Row i describes content i. Its foreignFullSymbol flag concerns its proper
    crop containing a different reference, not this content appearing elsewhere.
    """
    if len(proper_crop_indices) != len(content_quads) or any(
        index is not None and (type(index) is not int or not 0 <= index < len(crop_supports))
        for index in proper_crop_indices
    ):
        raise ValueError("CONTENT_PROPER_CROP_MAPPING_INVALID")
    contents = [_polygon(value, quad=True) for value in content_quads]
    supports = [_polygon(value) for value in crop_supports]
    matrix: list[list[float | None]] = []
    cells: list[CellAssignment] = []
    for i, (content, proper) in enumerate(zip(contents, proper_crop_indices, strict=True)):
        overlaps = [
            None if content is None or support is None else _overlap(content, support)
            for support in supports
        ]
        matrix.append(
            [
                None if area is None or content is None else area / _area(content)
                for area in overlaps
            ]
        )
        flags: CellAssignment = {"wrongCell": False, "tie": False, "foreignFullSymbol": False}
        if content is not None and proper is not None and supports[proper] is not None:
            own = overlaps[proper]
            assert own is not None
            tolerance = _area_tolerance(content)
            maximum = max(area for area in overlaps if area is not None)
            flags["wrongCell"] = any(
                area is not None and j != proper and area > own + tolerance
                for j, area in enumerate(overlaps)
            )
            flags["tie"] = (
                maximum > tolerance
                and sum(area is not None and abs(area - maximum) <= tolerance for area in overlaps)
                > 1
            )
            support = supports[proper]
            assert support is not None
            flags["foreignFullSymbol"] = any(
                other is not None and j != i and _contained(other, support)
                for j, other in enumerate(contents)
            )
        cells.append(flags)
    return {"coverage": matrix, "cells": cells}
