"""Versioned float64 (Python double) metrics over two blind TRAIN/A passes."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from .grid_cell_content import (
    REPEATABILITY_VERSION,
    ContentError,
    ContentRevision,
    ContentTarget,
    require_reference,
)
from .grid_training_cohorts import digest
from .grid_visibility_contract import CellContentReference, Point


def nearest_rank_p95(values: Sequence[float]) -> float:
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("CONTENT_REPEATABILITY_VALUES_INVALID")
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def bbox_diagonal(points: Sequence[Point]) -> float:
    if not points or any(not math.isfinite(v) for point in points for v in point):
        raise ValueError("CONTENT_MEASUREMENT_GEOMETRY_INVALID")
    value = math.hypot(
        max(p[0] for p in points) - min(p[0] for p in points),
        max(p[1] for p in points) - min(p[1] for p in points),
    )
    if not math.isfinite(value) or value <= 0:
        raise ValueError("CONTENT_MEASUREMENT_GEOMETRY_INVALID")
    return value


def point_to_filled_quad(point: Point, quad: Sequence[Point]) -> float:
    if len(quad) != 4:
        raise ValueError("CONTENT_MEASUREMENT_QUAD_INVALID")
    CellContentReference(state="visible", quad=(quad[0], quad[1], quad[2], quad[3]))
    signs, distances = [], []
    for index, a in enumerate(quad):
        b = quad[(index + 1) % 4]
        dx, dy, px, py = b[0] - a[0], b[1] - a[1], point[0] - a[0], point[1] - a[1]
        signs.append(dx * py - dy * px)
        t = min(1.0, max(0.0, (px * dx + py * dy) / (dx * dx + dy * dy)))
        distances.append(math.hypot(px - t * dx, py - t * dy))
    return 0.0 if all(s >= 0 for s in signs) or all(s <= 0 for s in signs) else min(distances)


def symmetric_quad_hausdorff(first: Sequence[Point], second: Sequence[Point]) -> float:
    return max(
        max(point_to_filled_quad(p, second) for p in first),
        max(point_to_filled_quad(p, first) for p in second),
    )


def lattice_cell(nodes: Sequence[Point], index: int) -> tuple[Point, Point, Point, Point]:
    if len(nodes) != 24 or not 0 <= index < 15:
        raise ValueError("CONTENT_MEASUREMENT_GEOMETRY_INVALID")
    row, col = divmod(index, 5)
    start = row * 6 + col
    quad = (nodes[start], nodes[start + 1], nodes[start + 7], nodes[start + 6])
    CellContentReference(state="visible", quad=quad)
    return quad


def symmetric_board_nme(first: Sequence[Point], second: Sequence[Point]) -> float:
    if len(first) != 24 or len(second) != 24:
        raise ValueError("CONTENT_MEASUREMENT_GEOMETRY_INVALID")
    for nodes in (first, second):
        for index in range(15):
            lattice_cell(nodes, index)
    mean = sum(math.dist(a, b) for a, b in zip(first, second, strict=True)) / 24
    return max(min(1.0, mean / bbox_diagonal(first)), min(1.0, mean / bbox_diagonal(second)))


def repeatability_report(
    targets: Sequence[ContentTarget],
    first: Sequence[ContentRevision],
    second: Sequence[ContentRevision],
    required_games: Sequence[UUID],
) -> dict[str, Any]:
    """Fail closed on missing pairs, invalid geometry, non-blind or foreign membership."""
    keyed = {target.key: target for target in targets}
    if len(keyed) != len(targets) or any(t.role not in {"TRAIN", "A"} for t in targets):
        raise ContentError(
            "CONTENT_REPEATABILITY_SCOPE", "Blind repeatability uses unique TRAIN/A only."
        )
    pairs = []
    for pass_number, values in enumerate((first, second), 1):
        rows = {}
        for revision in values:
            ref = revision.reference
            key = str(ref.gameId), ref.sourceRepresentativeSha256, ref.positionIndex
            if key not in keyed or key in rows:
                raise ContentError(
                    "CONTENT_REPEATABILITY_MEMBERSHIP", "Unexpected or duplicate board."
                )
            require_reference(keyed[key], revision)
            if revision.origin != "manual_blind" or revision.passNumber != pass_number:
                raise ContentError(
                    "CONTENT_REPEATABILITY_BLIND_REQUIRED", "Two blind passes required."
                )
            rows[key] = revision
        pairs.append(rows)
    result: dict[str, Any] = {}
    all_ready = bool(required_games)
    for game in sorted({str(value) for value in required_games}):
        members = [t for t in targets if str(t.gameId) == game]
        cell_errors: list[float] = []
        photo_errors: dict[str, list[float]] = defaultdict(list)
        actors: set[str] = set()
        missing = invalid = unknown = differing_states = 0
        for target in members:
            a, b = (rows.get(target.key) for rows in pairs)
            if a is None or b is None:
                missing += 1
                continue
            if a.sessionId != b.sessionId:
                raise ContentError(
                    "CONTENT_REPEATABILITY_SESSION", "Passes belong to different sessions."
                )
            actors.update((a.actor, b.actor))
            assert a.measuredNodes is not None and b.measuredNodes is not None
            try:
                if any(
                    not 0 <= x <= target.source.width or not 0 <= y <= target.source.height
                    for nodes in (a.measuredNodes, b.measuredNodes)
                    for x, y in nodes
                ):
                    raise ValueError("CONTENT_MEASUREMENT_GEOMETRY_INVALID")
                nme = symmetric_board_nme(a.measuredNodes, b.measuredNodes)
            except ValueError:
                invalid += 1
                continue
            photo_errors[target.source.sourceRepresentativeSha256].append(nme)
            for index, (left, right) in enumerate(
                zip(a.reference.cells, b.reference.cells, strict=True)
            ):
                if left.state != right.state:
                    differing_states += 1
                if "unknown" in (left.state, right.state):
                    unknown += 1
                if left.state != "visible" or right.state != "visible":
                    continue
                assert left.quad is not None and right.quad is not None
                diagonal = min(
                    bbox_diagonal(lattice_cell(n, index))
                    for n in (a.measuredNodes, b.measuredNodes)
                )
                cell_errors.append(symmetric_quad_hausdorff(left.quad, right.quad) / diagonal)
        u = nearest_rank_p95(cell_errors) if cell_errors else None
        delta = (
            nearest_rank_p95([sum(values) / len(values) for values in photo_errors.values()])
            if photo_errors
            else None
        )
        reasons = []
        if len(members) < 30 or len(photo_errors) < 10:
            reasons.append("CONTENT_REPEATABILITY_SAMPLE_MISSING")
        if missing or invalid or u is None or delta is None:
            reasons.append("CONTENT_REPEATABILITY_INCOMPLETE")
        if differing_states:
            reasons.append("CONTENT_REPEATABILITY_STATES_DISAGREE")
        if members and unknown / (15 * len(members)) > 0.10:
            reasons.append("CONTENT_UNKNOWN_LIMIT")
        if u is not None and u > 0.02:
            reasons.append("CONTENT_U_LIMIT")
        if delta is not None and delta > 0.002:
            reasons.append("CONTENT_DELTA_LIMIT")
        all_ready = all_ready and not reasons
        result[game] = {
            "state": "ready" if not reasons else "not_evaluable",
            "reasonCodes": reasons,
            "boards": len(members),
            "photos": len(photo_errors),
            "visiblePairs": len(cell_errors),
            "missingPairs": missing,
            "invalidGeometryPairs": invalid,
            "unknownPairs": unknown,
            "stateDisagreements": differing_states,
            "u": u,
            "delta": delta,
            "actors": sorted(actors),
            "operatorScope": "intra_operator" if len(actors) == 1 else "multiple_operators",
        }
    body = {
        "version": REPEATABILITY_VERSION,
        "quantile": "nearest-rank-p95-v1",
        "state": "ready" if all_ready else "not_evaluable",
        "games": result,
        "targetSha256": digest(
            [t.model_dump(mode="json") for t in sorted(targets, key=lambda t: t.key)]
        ),
        "passSha256": [digest(sorted(r.sha256 for r in values)) for values in (first, second)],
    }
    return {**body, "sha256": digest(body)}
