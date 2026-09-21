from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.shape_geometry_v2.core import (
    ShapeGeometryV2Error,
    ShapeGeometryV2ReasonCode,
    ShapeGeometryV2Status,
    detect_shape_geometry_v2,
)
from game_predictor_worker.images.shape_geometry_v2.corpus import canonical_json_bytes


def _framed_page(
    *,
    frame_color: tuple[int, int, int],
    with_grid: bool = True,
    left_margin: int = 100,
) -> np.ndarray:
    canonical_width, canonical_height = 900, 600
    page = np.zeros((canonical_height, canonical_width, 3), dtype=np.uint8)
    page[:, :] = (18, 21, 25)
    cv2.rectangle(
        page,
        (3, 3),
        (canonical_width - 4, canonical_height - 4),
        frame_color,
        thickness=12,
        lineType=cv2.LINE_AA,
    )
    if with_grid:
        for x in range(60, canonical_width, 60):
            cv2.line(
                page,
                (x, 5),
                (x, canonical_height - 6),
                frame_color,
                thickness=4,
                lineType=cv2.LINE_AA,
            )
        for y in range(67, canonical_height, 67):
            cv2.line(
                page,
                (5, y),
                (canonical_width - 6, y),
                frame_color,
                thickness=4,
                lineType=cv2.LINE_AA,
            )
    image = np.zeros((800, 1100, 3), dtype=np.uint8)
    destination = np.float32(
        (
            (left_margin, 108),
            (936, 132),
            (900, 682),
            (left_margin + 24, 650),
        )
    )
    matrix = cv2.getPerspectiveTransform(
        np.float32(((0, 0), (899, 0), (899, 599), (0, 599))),
        destination,
    )
    return cv2.warpPerspective(
        page,
        matrix,
        (1100, 800),
        dst=image,
        borderMode=cv2.BORDER_TRANSPARENT,
    )


@pytest.mark.parametrize("frame_color", [(235, 25, 20), (230, 180, 20)])
def test_core_proposes_full_grid_for_multiple_frame_colours(
    frame_color: tuple[int, int, int],
) -> None:
    result = detect_shape_geometry_v2(_framed_page(frame_color=frame_color))

    assert result.status is ShapeGeometryV2Status.PROPOSAL
    assert result.reason_codes == ()
    assert result.frame_quad is not None
    assert result.color_evidence is not None
    assert result.grid_evidence is not None
    assert result.grid_evidence.support >= 0.72
    assert len(result.boards) == 9
    assert [board.position_index for board in result.boards] == list(range(9))
    assert all(len(board.cell_quads) == 15 for board in result.boards)


def test_core_returns_stable_replay_payload() -> None:
    image = _framed_page(frame_color=(230, 180, 20))

    first = detect_shape_geometry_v2(image)
    second = detect_shape_geometry_v2(image.copy())

    assert canonical_json_bytes(first.as_dict()) == canonical_json_bytes(second.as_dict())


def test_core_keeps_canonical_grid_orientation_after_horizontal_flip() -> None:
    result = detect_shape_geometry_v2(cv2.flip(_framed_page(frame_color=(235, 25, 20)), 1))

    assert result.status is ShapeGeometryV2Status.PROPOSAL
    assert [board.position_index for board in result.boards] == list(range(9))


def test_core_keeps_derived_board_bounds_inside_the_frame_quad() -> None:
    result = detect_shape_geometry_v2(_framed_page(frame_color=(230, 180, 20)))

    assert result.status is ShapeGeometryV2Status.PROPOSAL
    assert result.frame_quad is not None
    assert np.allclose(result.boards[-1].board_quad[2], result.frame_quad[2], atol=0.001)


def test_core_ignores_an_ambiguous_small_contour_outside_the_page() -> None:
    image = _framed_page(frame_color=(230, 180, 20))
    cv2.fillConvexPoly(
        image,
        np.asarray(((1020, 50), (1060, 90), (1020, 130), (980, 90)), dtype=np.int32),
        (255, 255, 255),
    )

    result = detect_shape_geometry_v2(image)

    assert result.status is ShapeGeometryV2Status.PROPOSAL
    assert len(result.boards) == 9


def test_core_requires_structural_grid_evidence() -> None:
    result = detect_shape_geometry_v2(_framed_page(frame_color=(235, 25, 20), with_grid=False))

    assert result.status is ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW
    assert result.boards == ()
    assert ShapeGeometryV2ReasonCode.GRID_EVIDENCE_INSUFFICIENT in result.reason_codes


def test_core_requires_grid_evidence_for_each_board_slot() -> None:
    image = _framed_page(frame_color=(235, 25, 20))
    cv2.fillConvexPoly(
        image,
        np.asarray(((399, 299), (665, 307), (656, 490), (405, 481)), dtype=np.int32),
        (18, 21, 25),
    )

    result = detect_shape_geometry_v2(image)

    assert result.status is ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW
    assert result.boards == ()
    assert result.grid_evidence is not None
    assert result.grid_evidence.minimum_board_support < 0.90
    assert ShapeGeometryV2ReasonCode.GRID_EVIDENCE_INSUFFICIENT in result.reason_codes


def test_core_never_uses_colour_without_structural_frame_evidence() -> None:
    saturated = np.full((800, 1100, 3), (235, 25, 20), dtype=np.uint8)

    result = detect_shape_geometry_v2(saturated)

    assert result.status is ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW
    assert result.frame_quad is None
    assert result.color_evidence is None
    assert result.reason_codes == (ShapeGeometryV2ReasonCode.FRAME_EVIDENCE_INSUFFICIENT,)


def test_core_rejects_page_too_close_to_image_edge_as_incomplete() -> None:
    result = detect_shape_geometry_v2(
        _framed_page(frame_color=(230, 180, 20), left_margin=8)
    )

    assert result.status is ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW
    assert result.boards == ()
    assert ShapeGeometryV2ReasonCode.PAGE_INCOMPLETE in result.reason_codes


def test_core_rejects_invalid_rgb_input() -> None:
    with pytest.raises(ShapeGeometryV2Error) as invalid:
        detect_shape_geometry_v2(np.zeros((400, 600), dtype=np.uint8))
    assert invalid.value.code == "SHAPE_GEOMETRY_V2_INPUT_INVALID"
