import pytest
from game_predictor_api.domain.grid_cut_suspicion import (
    GRID_CUT_SUSPICION_THRESHOLD,
    GridCutReason,
    assess_grid_cut,
)


def grid(x_scale=31.3748086486, y_scale=100 / 3, shift=0):
    return [
        {"x": shift + column * x_scale, "y": shift + row * y_scale}
        for row in range(4)
        for column in range(6)
    ]


def test_regular_grid_and_translation_have_the_same_score():
    normal = assess_grid_cut(grid())
    translated = assess_grid_cut(grid(shift=250))
    assert normal is not None and translated is not None
    assert normal.score < GRID_CUT_SUSPICION_THRESHOLD
    assert translated.score == pytest.approx(normal.score, abs=1e-12)


def test_mild_perspective_is_below_threshold():
    nodes = grid()
    for point in nodes:
        scale = 1 + 0.0002 * point["y"]
        point["x"] /= scale
        point["y"] /= scale
    result = assess_grid_cut(nodes)
    assert result is not None
    assert result.score < GRID_CUT_SUSPICION_THRESHOLD


def test_clipped_outer_edge_points_to_neighboring_cells():
    nodes = grid()
    center_x = nodes[5]["x"] / 2
    for index in range(6):
        nodes[index]["x"] = center_x + (nodes[index]["x"] - center_x) * 0.86
    result = assess_grid_cut(nodes)
    assert result is not None
    assert result.score > GRID_CUT_SUSPICION_THRESHOLD
    assert result.reason is GridCutReason.OPPOSITE_EDGES
    assert result.node_indices == (0, 5)
    assert result.preferred_cell_indices == (0, 1, 2, 3, 4)


def test_narrow_column_has_local_spacing_reason():
    nodes = grid()
    for row in range(4):
        nodes[row * 6 + 1]["x"] *= 0.65
    result = assess_grid_cut(nodes)
    assert result is not None
    assert result.score > GRID_CUT_SUSPICION_THRESHOLD
    assert result.reason is GridCutReason.LINE_SPACING
    assert result.node_indices == (0, 1)
    assert result.preferred_cell_indices == (0,)


def test_entire_board_can_have_a_bad_aspect_with_equal_spacing():
    result = assess_grid_cut(grid(x_scale=40))
    assert result is not None
    assert result.score > GRID_CUT_SUSPICION_THRESHOLD
    assert result.reason is GridCutReason.BOARD_ASPECT
    assert result.node_indices is None


@pytest.mark.parametrize(
    "nodes",
    [
        None,
        grid()[:-1],
        grid()[:1] * 24,
        [{"x": "1", "y": 2}, *grid()[1:]],
        [{"x": False, "y": 0}, *grid()[1:]],
        grid(x_scale=float("inf")),
    ],
)
def test_missing_or_invalid_geometry_has_no_score(nodes):
    assert assess_grid_cut(nodes) is None
