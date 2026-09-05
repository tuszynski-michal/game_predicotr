from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_api.application.image_import_geometry_guard_preview import (
    render_image_geometry_guard_preview,
)
from game_predictor_api.domain.jobs import JobError


def _jpeg() -> bytes:
    image = np.zeros((180, 300, 3), dtype=np.uint8)
    for row in range(3):
        for column in range(5):
            image[row * 60 : (row + 1) * 60, column * 60 : (column + 1) * 60] = (
                20 + column * 30,
                30 + row * 60,
                180,
            )
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    return encoded.tobytes()


def _quad() -> tuple[dict[str, int], ...]:
    return (
        {"x": 0, "y": 0},
        {"x": 299, "y": 0},
        {"x": 299, "y": 179},
        {"x": 0, "y": 179},
    )


def test_preview_renders_exactly_available_cells_without_persisting_files() -> None:
    width, height, cells = render_image_geometry_guard_preview(
        source_content=_jpeg(),
        symbol_grid_quad=_quad(),
        proposed_symbol_grid_quad=[
            {"x": float(point["x"]), "y": float(point["y"])} for point in _quad()
        ],
        unavailable_cell_indices=(0, 14),
    )

    assert (width, height) == (300, 180)
    assert len(cells) == 15
    assert cells[0].source_unavailable is True
    assert cells[0].current_data_url is None
    assert cells[1].current_data_url is not None
    assert cells[1].current_data_url.startswith("data:image/jpeg;base64,")
    assert cells[1].proposed_data_url is not None
    assert cells[14].proposed_data_url is None


def test_preview_rejects_geometry_outside_checksum_bound_source() -> None:
    invalid = list(_quad())
    invalid[1] = {"x": 500, "y": 0}

    with pytest.raises(JobError) as captured:
        render_image_geometry_guard_preview(
            source_content=_jpeg(),
            symbol_grid_quad=tuple(invalid),
            proposed_symbol_grid_quad=None,
            unavailable_cell_indices=(),
        )

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_PREVIEW_GEOMETRY_INVALID"
