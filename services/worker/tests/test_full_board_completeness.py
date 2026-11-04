"""Deterministic geometric measurements, not an empirical calibration corpus."""

import numpy as np
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.images.full_board_completeness import (
    features,
    gt_cropped,
    log_aspect,
    missing_cell_area,
    perspective_neighbor_deviation,
)


def detection(x=10, y=10):
    quad = np.array([[x, y], [x + 50, y], [x + 50, y + 30], [x, y + 30]], np.float32)
    nodes = grid_from_quad(quad)
    return BoardDetection(1, quad, nodes.copy(), nodes, np.ones(24), np.ones(24), 0.0, 0.0, 24, [])


def test_top_row_outside_true_network_input_is_measured_even_for_valid_grid():
    item = detection()
    support = item.screen_quad.copy()
    support[:2, 1] += 10
    assert missing_cell_area(item.nodes, support, 100, 100) > 0.99
    assert (
        gt_cropped(item.nodes, item.nodes, real_input_support=support, width=100, height=100)
        is True
    )
    measured = features(
        item,
        width=100,
        height=100,
        real_input_support=support,
        game_log_aspect_reference=log_aspect(item.nodes),
        neighbor_deviation=None,
        neighbor_applicable=False,
    )
    assert "COMPLETENESS_PIXELS_MISSING" in measured.hardReasons


def test_unknown_reference_and_required_missing_rescue_are_not_agreement():
    item = detection()
    measured = features(
        item,
        width=100,
        height=100,
        real_input_support=None,
        game_log_aspect_reference=None,
        neighbor_deviation=None,
        neighbor_applicable=True,
        rescue_required=True,
    )
    assert measured.values["gameAspectDeviation"] is None
    assert measured.values["neighborDeviation"] is None
    assert "COMPLETENESS_RESCUE_REQUIRED" in measured.hardReasons
    assert "COMPLETENESS_PIXEL_SUPPORT_REQUIRED" in measured.hardReasons
    assert measured.notApplicable == ()


def test_equal_grid_projected_in_perspective_has_consistent_rectified_neighbors():
    import cv2

    matrix = np.array([[1.0, 0.15, 0.0], [0.1, 0.8, 0.0], [0.001, 0.0015, 1.0]])
    values = [detection(10 + c * 80, 10 + r * 60) for r in range(3) for c in range(3)]
    for item in values:
        item.nodes = cv2.perspectiveTransform(item.nodes[None], matrix)[0]
        item.screen_quad = item.nodes[[0, 5, 23, 18]]
    result = perspective_neighbor_deviation(values, dict(enumerate(range(9))))
    assert all(value is not None and value < 0.03 for value in result.values())
    assert perspective_neighbor_deviation(values[:1], {0: 0}) == {0: None}


def test_coverage_is_scale_invariant_and_exact_matching_support_not_cropped():
    item = detection()
    assert missing_cell_area(item.nodes, item.screen_quad, 100, 100) < 1e-6
    assert (
        gt_cropped(
            item.nodes, item.nodes, real_input_support=item.screen_quad, width=100, height=100
        )
        is False
    )
    support = item.screen_quad.copy()
    support[:2, 1] += 5
    a = missing_cell_area(item.nodes, support, 100, 100)
    b = missing_cell_area(item.nodes * 7, support * 7, 700, 700)
    assert abs(a - b) < 1e-6
