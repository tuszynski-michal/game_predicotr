from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection import (
    v7_partial_label_locator,
    v7_partial_lattice,
)
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
    V7DynamicGridLabelLocator,
    V7DynamicGridLabelLocatorConfig,
    _TextBox,
)
from game_predictor_worker.semi_automatic_selection.v7_partial_label_locator import (
    V7PartialGridLabelLocator,
)
from game_predictor_worker.semi_automatic_selection.v7_partial_lattice import find_partial_lattice


def partial_grid_rgb(
    positions: tuple[int, ...] = tuple(range(9)), *, inverted: bool = False
) -> np.ndarray:
    rgb = np.full((360, 560, 3), 235 if inverted else 18, dtype=np.uint8)
    transform = cv2.getPerspectiveTransform(
        np.asarray([[0, 0], [2, 0], [2, 2], [0, 2]], dtype=np.float32),
        np.asarray([[110, 104], [432, 86], [461, 272], [86, 294]], dtype=np.float32),
    )
    points = cv2.perspectiveTransform(
        np.asarray([[(column, row) for row in range(3) for column in range(3)]], dtype=np.float32),
        transform,
    )[0]
    for position in positions:
        x, y = points[position]
        cv2.putText(
            rgb,
            f"{position + 101:06d}",
            (round(x - 42), round(y + 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (12, 12, 12) if inverted else (248, 248, 248),
            2,
            cv2.LINE_AA,
        )
    return rgb


def boxes(
    positions: tuple[int, ...] = tuple(range(9)), *, dx: int = 0, dy: int = 0
) -> tuple[_TextBox, ...]:
    return tuple(
        _TextBox(
            95 + (position % 3) * 160 + dx,
            95 + (position // 3) * 90 + dy,
            105 + (position % 3) * 160 + dx,
            105 + (position // 3) * 90 + dy,
        )
        for position in positions
    )


@pytest.mark.parametrize("missing", [None, 0, 2, 6, 8])
@pytest.mark.parametrize("inverted", [False, True])
def test_partial_locator_preserves_every_observed_index_in_perspective(
    missing: int | None, inverted: bool
) -> None:
    positions = tuple(position for position in range(9) if position != missing)
    result = V7PartialGridLabelLocator().locate_with_diagnostics(
        partial_grid_rgb(positions, inverted=inverted)
    )
    assert result.reason_code is None
    assert tuple(crop.position_index for crop in result.crops) == positions
    assert all(crop.complete and crop.rgb.size for crop in result.crops)


def test_five_spanning_points_are_accepted_but_shifted_five_are_ambiguous() -> None:
    config = V7DynamicGridLabelLocatorConfig()
    result = find_partial_lattice(boxes((0, 2, 4, 6, 8)), (400, 600), config)
    assert result.lattice is not None, result.reason_code
    assert tuple(slot for slot, _ in result.lattice.assignments) == (0, 2, 4, 6, 8)
    shifted = find_partial_lattice(boxes((0, 1, 2, 3, 4), dy=40), (480, 600), config)
    assert shifted.lattice is None
    assert shifted.reason_code == "V7_LABEL_LATTICE_AMBIGUOUS"


def test_competing_lattices_and_duplicate_components_never_choose_iteration_order() -> None:
    config = V7DynamicGridLabelLocatorConfig()
    assert find_partial_lattice(boxes() + boxes(dx=20, dy=35), (400, 600), config).lattice is None
    assert find_partial_lattice(boxes() + boxes((4,)), (400, 600), config).lattice is None
    assert (
        find_partial_lattice(tuple(reversed(boxes() + boxes((4,)))), (400, 600), config).lattice
        is None
    )


def test_overflow_does_not_accept_a_good_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    config = V7DynamicGridLabelLocatorConfig()
    assert (
        find_partial_lattice(boxes() * 4, (400, 600), config).reason_code
        == "V7_LABEL_CANDIDATE_LIMIT"
    )
    monkeypatch.setattr(v7_partial_lattice, "MAXIMUM_PARTIAL_SEEDS", 1)
    assert (
        find_partial_lattice(boxes(), (400, 600), config).reason_code == "V7_LABEL_HYPOTHESIS_LIMIT"
    )


def test_photo_mask_never_leaks_and_strict_v2_still_requires_nine() -> None:
    locator = V7PartialGridLabelLocator()
    for positions in (tuple(range(9)), tuple(range(1, 9)), tuple(range(9))):
        assert (
            tuple(crop.position_index for crop in locator.locate(partial_grid_rgb(positions)))
            == positions
        )
    assert V7DynamicGridLabelLocator().locate(partial_grid_rgb(tuple(range(1, 9)))) == ()


def test_invalid_geometry_bounds_and_crop_containment_fail_closed() -> None:
    config = V7DynamicGridLabelLocatorConfig()
    assert find_partial_lattice(boxes((0, 1, 2, 3)), (400, 600), config).lattice is None
    assert (
        find_partial_lattice(
            tuple(_TextBox(x, 95, x + 10, 105) for x in range(50, 450, 50)), (400, 600), config
        ).lattice
        is None
    )
    assert V7PartialGridLabelLocator().locate(np.zeros((100, 30, 3), dtype=np.uint8)) == ()
    # Geometry can pass while the actual text does not fit the calibrated crop.
    result = V7PartialGridLabelLocator(
        replace(config, crop_width_spacing_ratio=0.2)
    ).locate_with_diagnostics(partial_grid_rgb())
    assert result.crops == ()
    assert result.reason_code == "V7_LABEL_CROP_INCOMPLETE"


def test_topology_rejects_mirror_fold_and_outside_viewport() -> None:
    centers = np.asarray([box.center for box in boxes()])
    assert v7_partial_lattice._validated_spacing(centers, (400, 600)) is not None
    assert v7_partial_lattice._validated_spacing(centers[::-1], (400, 600)) is None
    assert v7_partial_lattice._validated_spacing(centers - (200, 0), (400, 600)) is None


def test_five_real_components_produce_only_five_crops() -> None:
    positions = (0, 2, 4, 6, 8)
    crops = V7PartialGridLabelLocator().locate(partial_grid_rgb(positions))
    assert tuple(crop.position_index for crop in crops) == positions


def test_unrelated_text_component_does_not_shift_a_complete_lattice() -> None:
    candidates = boxes() + (_TextBox(530, 20, 540, 30),)
    result = find_partial_lattice(candidates, (400, 600), V7DynamicGridLabelLocatorConfig())
    assert result.lattice is not None
    assert result.lattice.assignments == tuple((index, index) for index in range(9))


def test_observed_crop_crossing_image_edge_is_not_clipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        v7_partial_label_locator, "_find_text_candidates", lambda rgb: boxes(dx=-60)
    )
    result = V7PartialGridLabelLocator().locate_with_diagnostics(
        np.zeros((400, 600, 3), dtype=np.uint8)
    )
    assert result.reason_code == "V7_LABEL_CROP_INCOMPLETE"
    assert result.crops == ()


def test_bad_residual_is_not_dropped_to_fewer_than_five_and_singular_fit_is_rejected() -> None:
    positions = (0, 2, 4, 6, 8)
    centers = np.asarray([box.center for box in boxes()], dtype=np.float64)
    observed = centers[list(positions)].copy()
    observed[2] += (25, 15)
    assert (
        v7_partial_lattice._fit_seed(
            observed,
            centers,
            90,
            (400, 600),
            V7DynamicGridLabelLocatorConfig(maximum_lattice_residual_ratio=0.01),
        )
        is None
    )
    collinear = np.asarray([(value, 0) for value in range(5)], dtype=np.float64)
    assert not v7_partial_lattice._has_projective_rank(collinear, collinear)


def test_initial_clutter_does_not_veto_other_mutually_nearest_pairs() -> None:
    cloud = boxes() + boxes((4,), dx=30)
    points = np.asarray([box.center for box in cloud])
    centers = points[:9]
    assert v7_partial_lattice._assign(points, centers, 90 * 0.65) == ()
    assert v7_partial_lattice._initial_assign(points, centers, 90) == tuple(
        (index, index) for index in range(9)
    )
    result = find_partial_lattice(cloud, (400, 600), V7DynamicGridLabelLocatorConfig())
    assert result.lattice is not None
    assert result.lattice.assignments == tuple((index, index) for index in range(9))


@pytest.mark.parametrize("gap_ratio,retained", [(0.5, False), (1.0, False), (1.001, True)])
@pytest.mark.parametrize("reverse", [False, True])
def test_initial_candidate_tie_boundary_is_not_resolved_by_order(
    gap_ratio: float, retained: bool, reverse: bool
) -> None:
    centers = np.asarray([box.center for box in boxes()], dtype=np.float64) - (100, 100)
    gap = 90 * v7_partial_lattice.INITIAL_ASSIGNMENT_TIE_SPACING_RATIO * gap_ratio
    points = np.vstack((centers, (gap, 0)))
    if reverse:
        points = points[::-1]
    pairs = v7_partial_lattice._initial_assign(points, centers, 90)
    assert (0 in dict(pairs)) is retained
    assert tuple(slot for slot, _ in pairs if slot != 0) == tuple(range(1, 9))
    assert all(np.array_equal(points[candidate], centers[slot]) for slot, candidate in pairs)


def test_initial_candidate_equidistant_from_two_slots_is_skipped() -> None:
    centers = np.asarray([box.center for box in boxes()], dtype=np.float64)
    points = np.vstack((centers[2:], (180, 100)))
    assert tuple(slot for slot, _ in v7_partial_lattice._initial_assign(points, centers, 160)) == (
        2,
        3,
        4,
        5,
        6,
        7,
        8,
    )


@pytest.mark.parametrize("duplicate", [(4,), (0, 1, 2, 3, 4), tuple(range(9))])
@pytest.mark.parametrize("reverse", [False, True])
def test_initial_and_final_collisions_preserve_competitive_viewport_veto(
    duplicate: tuple[int, ...], reverse: bool
) -> None:
    # The unrelated five-point grid alone is geometrically credible. Duplicates
    # must not erase the denser competing viewport, even with zero initial MNN.
    alias = boxes((0, 2, 4, 6, 8), dx=550)
    config = V7DynamicGridLabelLocatorConfig()
    assert find_partial_lattice(alias, (400, 1150), config).lattice is not None
    cloud = boxes() + boxes(duplicate) + alias
    if reverse:
        cloud = cloud[::-1]
    points = np.asarray([box.center for box in cloud])
    centers = np.asarray([box.center for box in boxes()])
    assignments = v7_partial_lattice._initial_assign(points, centers, 90)
    assert len(assignments) == 9 - len(duplicate)
    fitted = v7_partial_lattice._fit_seed(points, centers, 90, (400, 1150), config)
    assert isinstance(fitted, v7_partial_lattice._CollisionHypothesis)
    assert fitted.score_upper_bound == 1
    result = find_partial_lattice(cloud, (400, 1150), config)
    assert result.lattice is None
    assert result.reason_code == "V7_LABEL_LATTICE_AMBIGUOUS"


def test_initial_blocker_requires_strict_support_rank_and_valid_viewport() -> None:
    centers = np.asarray([box.center for box in boxes()])
    config = V7DynamicGridLabelLocatorConfig()
    for cloud, viewport in (
        (boxes((0, 1, 2, 3)) * 2, centers),
        (boxes() * 2, centers + (20, 0)),
        (boxes() * 2, centers[::-1]),
        (boxes() * 2, centers - (200, 0)),
    ):
        points = np.asarray([box.center for box in cloud])
        assert v7_partial_lattice._initial_collision(points, viewport, (400, 600), config) is None


def test_collision_veto_compares_viewports_without_counting_repeated_seeds() -> None:
    centers = tuple(box.center for box in boxes())
    lattice = v7_partial_lattice.PartialLattice(centers, tuple((i, i) for i in range(9)), 90, 0)
    equivalent = v7_partial_lattice._CollisionHypothesis(centers, 90, 1)
    assert v7_partial_lattice._select_lattice([lattice], [equivalent] * 20, 0.08).lattice == lattice
    shifted = v7_partial_lattice._CollisionHypothesis(tuple((x + 40, y) for x, y in centers), 90, 1)
    assert v7_partial_lattice._select_lattice([lattice], [shifted], 0.08).lattice is None
    weaker = replace(shifted, score_upper_bound=5 / 9)
    assert v7_partial_lattice._select_lattice([lattice], [weaker] * 20, 0.08).lattice == lattice


@pytest.mark.parametrize("case_index", [0, 1])
@pytest.mark.parametrize("reverse", [False, True])
def test_real_component_clouds_never_repeat_shifted_or_half_row_indices(
    case_index: int, reverse: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/v7_partial_real_components.json").read_text(
            encoding="utf-8"
        )
    )
    case = fixture["cases"][case_index]
    cloud = tuple(_TextBox(*box) for box in case["componentBoxes"])
    if reverse:
        cloud = cloud[::-1]
    config = V7DynamicGridLabelLocatorConfig(position_confidence=0.95)
    assert config.as_dict() == case["locatorConfig"]
    monkeypatch.setattr(v7_partial_label_locator, "_find_text_candidates", lambda _rgb: cloud)
    result = V7PartialGridLabelLocator(config).locate_with_diagnostics(
        np.zeros((*case["shape"], 3), dtype=np.uint8)
    )
    # B is practically recovered; A remains ambiguous rather than half-spacing.
    assert len(result.crops) == (9 if case_index == 0 else 0)
    if not result.crops:
        assert result.reason_code == "V7_LABEL_LATTICE_AMBIGUOUS"
        return
    lattice = find_partial_lattice(cloud, tuple(case["shape"]), config).lattice
    assert lattice is not None
    annotations = {
        entry["positionIndex"]: entry["centerPixels"] for entry in case["annotatedCenters"]
    }
    for crop, (slot, candidate) in zip(result.crops, lattice.assignments, strict=True):
        center, own = cloud[candidate].center, annotations[slot]
        assert min(annotations, key=lambda index: math.dist(center, annotations[index])) == slot
        assert math.dist(center, own) < lattice.spacing * config.maximum_lattice_residual_ratio
        left = round(center[0] - crop.rgb.shape[1] / 2)
        top = round(center[1] - crop.rgb.shape[0] / 2)
        assert left <= own[0] < left + crop.rgb.shape[1]
        assert top <= own[1] < top + crop.rgb.shape[0]
