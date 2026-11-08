"""Small deterministic source-space cases; these do not qualify a real model."""

import math

import pytest
from game_predictor_api.domain.production_cell_geometry import (
    assess_content,
    coverage_matrix,
    intersect_support,
)


def box(left, top, right, bottom):
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


@pytest.mark.parametrize(
    ("support", "uncertainty", "state", "reason"),
    [
        (box(1, 1, 9, 9), 0.5, "preserved", None),
        (box(2, 2, 8, 8), 0, "preserved", None),
        (box(2, 2, 8, 8), 0.5, "borderline", "CONTENT_UNCERTAINTY_BORDERLINE"),
        (box(2.2, 1, 9, 9), 0.5, "borderline", "CONTENT_UNCERTAINTY_BORDERLINE"),
        (box(3, 1, 9, 9), 0.5, "clipped", "CONTENT_CLIPPED"),
        (box(20, 20, 30, 30), 0.5, "clipped", "CONTENT_CLIPPED"),
        (None, 0, "missing", "CONTENT_SUPPORT_MISSING"),
        ([], 0, "missing", "CONTENT_SUPPORT_EMPTY"),
        ([[0, 0], [4, 0], [1, 1], [4, 4]], 0, "missing", "CONTENT_SUPPORT_INVALID"),
    ],
)
def test_content_uses_dilated_and_eroded_reference(support, uncertainty, state, reason):
    result = assess_content(box(2, 2, 8, 8), support, uncertainty)
    assert result["state"] == state and result["reason"] == reason
    if state == "missing":
        assert result["coverage"] is None
    else:
        assert result["coverage"] is not None and 0 <= result["coverage"] <= 1


def test_empty_erosion_is_borderline_even_inside_large_support():
    result = assess_content(box(0, 0, 1, 1), box(-10, -10, 10, 10), 0.5)
    assert result == {"state": "borderline", "coverage": 1.0, "reason": "CONTENT_EROSION_EMPTY"}


@pytest.mark.parametrize(
    "quad",
    [
        [[0, 0], [1, 1], [0, 1], [1, 0]],  # crossed
        [[0, 0], [1, 0], [2, 0], [3, 0]],  # degenerate
        [[0, 0], [1, 0], [2, 0], [0, 2]],  # three collinear quad vertices
        [[0, 0], [1, 0], [1, 1], [math.nan, 1]],
        [[0, 0], [1, 0], [1, 1]],
    ],
)
def test_invalid_reference_is_explicit_missing_without_fake_zero(quad):
    assert assess_content(quad, box(-10, -10, 10, 10), 0) == {
        "state": "missing",
        "coverage": None,
        "reason": "CONTENT_REFERENCE_INVALID",
    }


@pytest.mark.parametrize("uncertainty", [-1, math.nan, math.inf])
def test_invalid_uncertainty_does_not_become_zero(uncertainty):
    assert (
        assess_content(box(0, 0, 10, 10), box(0, 0, 10, 10), uncertainty)["reason"]
        == "CONTENT_UNCERTAINTY_INVALID"
    )


def test_convex_intersection_handles_eight_vertices_and_both_windings():
    first = box(-1, -1, 1, 1)
    second = [[0, -1.5], [1.5, 0], [0, 1.5], [-1.5, 0]]
    result = intersect_support(first, second)
    assert len(result) == 8
    area = (
        abs(
            sum(
                a[0] * b[1] - a[1] * b[0]
                for a, b in zip(result, result[1:] + result[:1], strict=True)
            )
        )
        / 2
    )
    assert area == pytest.approx(3.5)
    assert assess_content(first, result, 0)["coverage"] == pytest.approx(3.5 / 4)
    assert assess_content(list(reversed(first)), list(reversed(result)), 0)[
        "coverage"
    ] == pytest.approx(3.5 / 4)
    assert intersect_support(first, box(2, 2, 3, 3)) == []
    assert intersect_support(first, box(1, -1, 2, 1)) == []  # touching edge has no real area
    assert intersect_support(first, [[0, 0], [1, 1]]) == []


def test_euclidean_dilation_does_not_add_false_miter_at_acute_perspective_corner():
    trapezoid = [[0, 0], [10, 0], [0.5, 2], [0, 2]]
    assert assess_content(trapezoid, box(-0.2, -0.2, 10.2, 2.2), 0.1)["state"] == "preserved"


def test_epsilon_length_clip_edge_does_not_discard_real_support():
    content = box(0, 0, 10, 10)
    support = [[0.5e-6, 0], [20, 0], [20, 20], [0, 20], [0, 0.5e-6]]
    actual = intersect_support(content, support)
    assert len(actual) >= 3
    assert assess_content(content, actual, 0)["state"] == "preserved"


def test_pixel_epsilon_is_not_an_area_ratio_or_relative_coordinate_tolerance():
    content = box(0, 0, 10, 10)
    assert assess_content(content, box(0.5e-6, 0, 10, 10), 0)["state"] == "preserved"
    assert assess_content(content, box(2e-6, 0, 10, 10), 0)["state"] == "clipped"

    def moved(points):
        return [[x + 1e7, y + 1e7] for x, y in points]

    assert assess_content(moved(content), moved(box(1, 0, 10, 10)), 0)["coverage"] == pytest.approx(
        0.9
    )
    assert assess_content(moved(content), moved(box(1, 0, 10, 10)), 0)["state"] == "clipped"


def test_shifted_row_or_column_detects_wrong_cell_and_foreign_full_symbol():
    labels = [box(0, 0, 10, 10), box(10, 0, 20, 10)]
    result = coverage_matrix(labels, list(reversed(labels)), [0, 1])
    assert result["coverage"] == [[0.0, 1.0], [1.0, 0.0]]
    assert all(
        row == {"wrongCell": True, "tie": False, "foreignFullSymbol": True}
        for row in result["cells"]
    )


def test_source_wide_matrix_catches_foreign_symbol_from_another_board():
    labels = [box(0, 0, 10, 10), box(100, 0, 110, 10)]
    result = coverage_matrix(labels, [box(-1, -1, 111, 11), labels[1]], [0, 1])
    assert result["cells"][0] == {"wrongCell": False, "tie": False, "foreignFullSymbol": True}
    assert result["cells"][1] == {"wrongCell": False, "tie": True, "foreignFullSymbol": False}


def test_positive_tie_in_foreign_crops_but_no_ambiguity_between_zeros():
    content = box(0, 0, 10, 10)
    result = coverage_matrix([content], [box(0, 0, 5, 10), content, content], [0])
    assert result["cells"][0] == {"wrongCell": True, "tie": True, "foreignFullSymbol": False}
    empty = coverage_matrix([content], [box(20, 0, 30, 10), box(40, 0, 50, 10)], [0])
    assert empty["coverage"] == [[0.0, 0.0]]
    assert not any(empty["cells"][0].values())


def test_missing_proper_crop_and_invalid_geometry_never_produce_assignment_proof():
    content = box(0, 0, 10, 10)
    result = coverage_matrix([content, [[0, 0]]], [content, None], [None, 1])
    assert result["coverage"] == [[1.0, None], [None, None]]
    assert not any(flag for cell in result["cells"] for flag in cell.values())
    with pytest.raises(ValueError, match="PROPER_CROP_MAPPING_INVALID"):
        coverage_matrix([content], [content], [2])
    with pytest.raises(ValueError, match="PROPER_CROP_MAPPING_INVALID"):
        coverage_matrix([content], [content], [])


def test_matrix_area_tolerance_has_pixel_squared_units_at_small_and_large_scales():
    small = box(0, 0, 0.01, 0.01)
    near = coverage_matrix([small], [box(0, 0, 0.005, 0.01), box(0, 0, 0.0050001, 0.01)], [0])
    assert near["cells"][0]["tie"] and not near["cells"][0]["wrongCell"]
    large = box(0, 0, 10000, 10000)
    distinct = coverage_matrix([large], [box(0, 0, 5000, 10000), box(0, 0, 5000.0001, 10000)], [0])
    assert distinct["cells"][0]["wrongCell"] and not distinct["cells"][0]["tie"]
