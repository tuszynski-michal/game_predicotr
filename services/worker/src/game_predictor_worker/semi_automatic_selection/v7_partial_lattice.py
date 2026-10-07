"""Bounded, image-only hypotheses for incomplete oriented 3x3 label grids.

Missing slots are never observations. All viable anchor offsets are considered;
exhausting the search budget fails closed instead of trusting a search prefix.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import cv2
import numpy as np
from numpy.typing import NDArray

from .v7_label_locator import V7DynamicGridLabelLocatorConfig, _TextBox

V7_PARTIAL_LATTICE_VERSION = "v7-partial-lattice-v2"
MAXIMUM_PARTIAL_CANDIDATES = 32
MAXIMUM_PARTIAL_SEEDS = 8192
MAXIMUM_PARTIAL_REFITS = 2
# An affine seed may miss the opposite corner under perspective. This is only
# the initialization radius; acceptance still uses the profile's strict residual.
INITIAL_ASSIGNMENT_SPACING_RATIO = 0.65
INITIAL_ASSIGNMENT_TIE_SPACING_RATIO = 1e-6
MAXIMUM_AXIS_SLOPE_RATIO = 0.28
MINIMUM_PROJECTIVE_SINGULAR_RATIO = 1e-7
VIEWPORT_EQUIVALENCE_SPACING_RATIO = 0.03


def partial_lattice_policy() -> dict[str, object]:
    """Include every non-profile geometry policy in the adapter fingerprint."""
    return {
        "version": V7_PARTIAL_LATTICE_VERSION,
        "maximumCandidates": MAXIMUM_PARTIAL_CANDIDATES,
        "maximumSeeds": MAXIMUM_PARTIAL_SEEDS,
        "maximumRefits": MAXIMUM_PARTIAL_REFITS,
        "initialAssignmentSpacingRatio": INITIAL_ASSIGNMENT_SPACING_RATIO,
        "initialAssignment": "mutual_nearest_v1",
        "initialAssignmentTieSpacingRatio": INITIAL_ASSIGNMENT_TIE_SPACING_RATIO,
        "collisionHypotheses": "competitive_blocker_v1",
        "initialCollisionHypotheses": "competitive_seed_blocker_v1",
        "maximumAxisSlopeRatio": MAXIMUM_AXIS_SLOPE_RATIO,
        "minimumProjectiveSingularRatio": MINIMUM_PROJECTIVE_SINGULAR_RATIO,
        "viewportEquivalenceSpacingRatio": VIEWPORT_EQUIVALENCE_SPACING_RATIO,
        "minimumObservedPositions": 5,
        "minimumHorizontalImageRatio": 0.08,
        "minimumVerticalImageRatio": 0.05,
        "maximumHorizontalImageRatio": 0.6,
        "maximumVerticalImageRatio": 0.45,
    }


@dataclass(frozen=True, slots=True)
class PartialLattice:
    centers: tuple[tuple[float, float], ...]
    assignments: tuple[tuple[int, int], ...]
    spacing: float
    residual: float

    @property
    def score(self) -> float:
        return len(self.assignments) / 9 - self.residual


@dataclass(frozen=True, slots=True)
class PartialLatticeResult:
    lattice: PartialLattice | None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class _CollisionHypothesis:
    """A veto only: no ambiguous component is ever selected for a crop."""

    centers: tuple[tuple[float, float], ...]
    spacing: float
    score_upper_bound: float


_GRID = np.asarray([(column, row) for row in range(3) for column in range(3)], dtype=np.float64)


def find_partial_lattice(
    candidates: tuple[_TextBox, ...],
    shape: tuple[int, int],
    config: V7DynamicGridLabelLocatorConfig,
) -> PartialLatticeResult:
    if len(candidates) < 5:
        return PartialLatticeResult(None, "V7_LABEL_COMPONENTS_INSUFFICIENT")
    if len(candidates) > MAXIMUM_PARTIAL_CANDIDATES:
        return PartialLatticeResult(None, "V7_LABEL_CANDIDATE_LIMIT")
    points = np.asarray([box.center for box in candidates], dtype=np.float64)
    hypotheses: dict[tuple[tuple[int, int], ...], PartialLattice] = {}
    collisions: list[_CollisionHypothesis] = []
    seeds = 0
    height, width = shape
    for origin_index, origin in enumerate(points):
        for horizontal_index, vertical_index in product(range(len(points)), repeat=2):
            if len({origin_index, horizontal_index, vertical_index}) != 3:
                continue
            delta_h = points[horizontal_index] - origin
            delta_v = points[vertical_index] - origin
            if (
                abs(delta_h[1]) > np.linalg.norm(delta_h) * MAXIMUM_AXIS_SLOPE_RATIO
                or abs(delta_v[0]) > np.linalg.norm(delta_v) * MAXIMUM_AXIS_SLOPE_RATIO
            ):
                continue
            for column_step, row_step in product((-2, -1, 1, 2), repeat=2):
                horizontal, vertical = delta_h / column_step, delta_v / row_step
                if not _valid_axes(horizontal, vertical, height, width):
                    continue
                for row, column in product(range(3), repeat=2):
                    if not (0 <= column + column_step < 3 and 0 <= row + row_step < 3):
                        continue
                    seeds += 1
                    if seeds > MAXIMUM_PARTIAL_SEEDS:
                        return PartialLatticeResult(None, "V7_LABEL_HYPOTHESIS_LIMIT")
                    centers = (
                        origin
                        + (_GRID[:, 0:1] - column) * horizontal
                        + (_GRID[:, 1:2] - row) * vertical
                    )
                    spacing = min(
                        float(np.linalg.norm(horizontal)), float(np.linalg.norm(vertical))
                    )
                    fitted = _fit_seed(points, centers, spacing, shape, config)
                    if isinstance(fitted, _CollisionHypothesis):
                        collisions.append(fitted)
                    elif fitted is not None:
                        previous = hypotheses.get(fitted.assignments)
                        if previous is None or fitted.residual < previous.residual:
                            hypotheses[fitted.assignments] = fitted
    return _select_lattice(list(hypotheses.values()), collisions, config.minimum_lattice_margin)


def _select_lattice(
    hypotheses: list[PartialLattice], collisions: list[_CollisionHypothesis], margin: float
) -> PartialLatticeResult:
    if not hypotheses:
        reason = "V7_LABEL_LATTICE_AMBIGUOUS" if collisions else "V7_LABEL_LATTICE_UNRESOLVED"
        return PartialLatticeResult(None, reason)
    ordered = sorted(hypotheses, key=lambda value: (-value.score, value.assignments))
    best = ordered[0]
    for other in ordered[1:]:
        if best.score - other.score > margin:
            continue
        # Assignment identity alone is insufficient: unobserved slots may shift.
        if (
            other.assignments != best.assignments
            or np.max(np.linalg.norm(np.asarray(other.centers) - np.asarray(best.centers), axis=1))
            > min(best.spacing, other.spacing) * VIEWPORT_EQUIVALENCE_SPACING_RATIO
        ):
            return PartialLatticeResult(None, "V7_LABEL_LATTICE_AMBIGUOUS")
    # At most one collision record per bounded seed. Compare each once; repeated
    # generation of an equivalent viewport neither votes nor adds a penalty.
    for collision in collisions:
        if (
            best.score - collision.score_upper_bound <= margin
            and np.max(
                np.linalg.norm(np.asarray(collision.centers) - np.asarray(best.centers), axis=1)
            )
            > min(best.spacing, collision.spacing) * VIEWPORT_EQUIVALENCE_SPACING_RATIO
        ):
            return PartialLatticeResult(None, "V7_LABEL_LATTICE_AMBIGUOUS")
    return PartialLatticeResult(best)


def _valid_axes(
    horizontal: NDArray[np.float64], vertical: NDArray[np.float64], height: int, width: int
) -> bool:
    return bool(
        width * 0.08 < horizontal[0]
        and height * 0.05 < vertical[1]
        and np.linalg.norm(horizontal) <= width * 0.6
        and np.linalg.norm(vertical) <= height * 0.45
    )


def _initial_assign(
    points: NDArray[np.float64], centers: NDArray[np.float64], spacing: float
) -> tuple[tuple[int, int], ...]:
    distances = np.linalg.norm(centers[:, None, :] - points[None, :, :], axis=2)
    nearest_candidates = np.argmin(distances, axis=1)
    nearest_slots = np.argmin(distances, axis=0)
    slot_distances = np.sort(distances, axis=1)
    candidate_distances = np.sort(distances, axis=0)
    tie_tolerance = spacing * INITIAL_ASSIGNMENT_TIE_SPACING_RATIO
    return tuple(
        (slot, int(candidate))
        for slot, candidate in enumerate(nearest_candidates)
        if nearest_slots[candidate] == slot
        and distances[slot, candidate] <= spacing * INITIAL_ASSIGNMENT_SPACING_RATIO
        and slot_distances[slot, 1] - slot_distances[slot, 0] > tie_tolerance
        and candidate_distances[1, candidate] - candidate_distances[0, candidate] > tie_tolerance
    )


def _assign(
    points: NDArray[np.float64], centers: NDArray[np.float64], tolerance: float
) -> tuple[tuple[int, int], ...]:
    distances = np.linalg.norm(centers[:, None, :] - points[None, :, :], axis=2)
    eligible = distances <= tolerance
    # Do not resolve collisions by iteration order, candidate index or OCR text.
    if np.any(eligible.sum(axis=0) > 1) or np.any(eligible.sum(axis=1) > 1):
        return ()
    slots, candidates = np.nonzero(eligible)
    return tuple(
        (int(slot), int(candidate)) for slot, candidate in zip(slots, candidates, strict=True)
    )


def _fit_seed(
    points: NDArray[np.float64],
    centers: NDArray[np.float64],
    spacing: float,
    shape: tuple[int, int],
    config: V7DynamicGridLabelLocatorConfig,
) -> PartialLattice | _CollisionHypothesis | None:
    assignments = _initial_assign(points, centers, spacing)
    if len(assignments) < 5:
        # Dense ties can erase the entire correct viewport before any refit.
        # Retain strictly supported affine geometry without choosing a matching.
        return _initial_collision(points, centers, shape, config)
    for _ in range(MAXIMUM_PARTIAL_REFITS):
        positions = [slot for slot, _ in assignments]
        if not _spans_grid(positions):
            return None
        observed = points[[candidate for _, candidate in assignments]]
        local = _GRID[positions]
        if not _has_projective_rank(local, observed / max(shape)):
            return None
        transform, _mask = cv2.findHomography(local, observed, method=0)
        if transform is None or not np.isfinite(transform).all():
            return None
        denominator = _GRID @ transform[2, :2] + transform[2, 2]
        if np.any(np.abs(denominator) < 1e-9) or not (
            np.all(denominator > 0) or np.all(denominator < 0)
        ):
            return None
        centers = np.asarray(
            cv2.perspectiveTransform(_GRID.reshape(1, -1, 2), transform).reshape(9, 2),
            dtype=np.float64,
        )
        fitted_spacing = _validated_spacing(centers, shape)
        if fitted_spacing is None:
            return None
        spacing = fitted_spacing
        residual = float(np.max(np.linalg.norm(centers[positions] - observed, axis=1)) / spacing)
        eligible = (
            np.linalg.norm(centers[:, None, :] - points[None, :, :], axis=2)
            <= spacing * config.maximum_lattice_residual_ratio
        )
        if np.any(eligible.sum(axis=0) > 1) or np.any(eligible.sum(axis=1) > 1):
            if residual <= config.maximum_lattice_residual_ratio:
                return _CollisionHypothesis(
                    tuple((float(x), float(y)) for x, y in centers),
                    spacing,
                    float(np.count_nonzero(eligible.any(axis=1))) / 9,
                )
            return None
        updated = _assign(points, centers, spacing * config.maximum_lattice_residual_ratio)
        if updated == assignments:
            if residual > config.maximum_lattice_residual_ratio:
                return None
            return PartialLattice(
                tuple((float(x), float(y)) for x, y in centers), assignments, spacing, residual
            )
        assignments = updated
    return None


def _initial_collision(
    points: NDArray[np.float64],
    centers: NDArray[np.float64],
    shape: tuple[int, int],
    config: V7DynamicGridLabelLocatorConfig,
) -> _CollisionHypothesis | None:
    spacing = _validated_spacing(centers, shape)
    if spacing is None:
        return None
    eligible = (
        np.linalg.norm(centers[:, None, :] - points[None, :, :], axis=2)
        <= spacing * config.maximum_lattice_residual_ratio
    )
    positions = [int(slot) for slot in np.flatnonzero(eligible.any(axis=1))]
    if (
        not _spans_grid(positions)
        or not (np.any(eligible.sum(axis=0) > 1) or np.any(eligible.sum(axis=1) > 1))
        or not _has_projective_rank(_GRID[positions], centers[positions] / max(shape))
    ):
        return None
    return _CollisionHypothesis(
        tuple((float(x), float(y)) for x, y in centers), spacing, len(positions) / 9
    )


def _spans_grid(positions: list[int]) -> bool:
    return (
        len(positions) >= 5
        and len({slot // 3 for slot in positions}) >= 2
        and len({slot % 3 for slot in positions}) >= 2
    )


def _has_projective_rank(local: NDArray[np.float64], observed: NDArray[np.float64]) -> bool:
    rows: list[tuple[float, ...]] = []
    for (x, y), (u, v) in zip(local, observed, strict=True):
        rows.extend(
            ((-x, -y, -1, 0, 0, 0, x * u, y * u, u), (0, 0, 0, -x, -y, -1, x * v, y * v, v))
        )
    singular = np.linalg.svd(np.asarray(rows, dtype=np.float64), compute_uv=False)
    return bool(singular[-2] > singular[0] * MINIMUM_PROJECTIVE_SINGULAR_RATIO)


def _validated_spacing(centers: NDArray[np.float64], shape: tuple[int, int]) -> float | None:
    if not np.isfinite(centers).all():
        return None
    height, width = shape
    if np.any(centers < 0) or np.any(centers[:, 0] >= width) or np.any(centers[:, 1] >= height):
        return None
    grid = centers.reshape(3, 3, 2)
    horizontal, vertical = np.diff(grid, axis=1), np.diff(grid, axis=0)
    if np.any(horizontal[:, :, 0] <= 0) or np.any(vertical[:, :, 1] <= 0):
        return None
    for row, column in product(range(2), repeat=2):
        h, v = horizontal[row, column], vertical[row, column]
        if h[0] * v[1] - h[1] * v[0] <= 1e-6:
            return None
    distances = np.concatenate(
        (np.linalg.norm(horizontal, axis=2).ravel(), np.linalg.norm(vertical, axis=2).ravel())
    )
    spacing = float(np.min(distances))
    return spacing if spacing > 1 else None
