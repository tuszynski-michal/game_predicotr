from __future__ import annotations

from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_worker.images.selective_board_review import (
    integer_review_draft,
    projected_review_draft,
)


def _quad(left: float, top: float, right: float, bottom: float) -> SourceQuad:
    return SourceQuad(
        corners=(
            SourcePoint(left, top),
            SourcePoint(right, top),
            SourcePoint(right, bottom),
            SourcePoint(left, bottom),
        )
    )


def test_neighbor_projection_uses_seven_grids_without_accepting_target() -> None:
    neighbors = tuple(
        (
            _quad(index * 100, 0, index * 100 + 90, 90),
            _quad(index * 100 + 5, 5, index * 100 + 85, 85),
        )
        for index in range(7)
    )
    draft = projected_review_draft(_quad(10, 100, 100, 190), neighbors, width=900, height=300)
    assert draft is not None
    assert [(round(point.x), round(point.y)) for point in draft.corners] == [
        (15, 105),
        (95, 105),
        (95, 185),
        (15, 185),
    ]
    assert (
        projected_review_draft(_quad(10, 100, 100, 190), neighbors[:6], width=900, height=300)
        is None
    )


def test_neighbor_projection_rejects_out_of_source_draft() -> None:
    neighbors = tuple(
        (
            _quad(index * 100, 0, index * 100 + 90, 90),
            _quad(index * 100 + 5, 5, index * 100 + 85, 85),
        )
        for index in range(7)
    )
    assert (
        projected_review_draft(_quad(850, 100, 940, 190), neighbors, width=900, height=300) is None
    )


def test_review_draft_has_integer_handles_and_rejects_out_of_bounds() -> None:
    draft = [
        {"x": 10.4, "y": 20.6},
        {"x": 90.1, "y": 20.2},
        {"x": 89.6, "y": 79.7},
        {"x": 10.2, "y": 80.1},
    ]
    assert integer_review_draft(draft, width=100, height=100) == [
        {"x": 10, "y": 21},
        {"x": 90, "y": 20},
        {"x": 90, "y": 80},
        {"x": 10, "y": 80},
    ]
    draft[0]["x"] = -2.0
    assert integer_review_draft(draft, width=100, height=100) is None
