from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.source_projective_lattice_crops import (
    BOUNDING_FALLBACK_CROPPER_VERSION,
    CELL_OUTPUT_SIZE,
    CROPPER_VERSION,
    build_bounding_fallback_source_projective_lattice_crops,
    build_source_projective_lattice_crops,
)


def _source_with_lattice_beyond_analysis_plane() -> np.ndarray:
    source = np.full((400, 500, 3), (24, 12, 20), dtype=np.uint8)
    colours = (
        (245, 205, 40),
        (245, 80, 35),
        (70, 120, 245),
        (225, 225, 70),
        (245, 150, 45),
    )
    for row, y in enumerate((80, 180, 280)):
        for column, x in enumerate((90, 170, 250, 330, 410)):
            cv2.circle(
                source,
                (x, y),
                24,
                colours[(row + column) % len(colours)],
                -1,
                cv2.LINE_AA,
            )
    return source


def test_source_aware_crop_recovers_real_pixels_beyond_analysis_plane() -> None:
    result = build_source_projective_lattice_crops(
        _source_with_lattice_beyond_analysis_plane(),
        (
            Point(0, 0),
            Point(499, 0),
            Point(499, 299),
            Point(0, 299),
        ),
    )

    assert result.status == "cropped"
    assert result.fallback_reason is None
    assert result.minimum_support_fraction == 1.0
    assert len(result.cells) == 15
    assert all(cell.support_fraction == 1.0 for cell in result.cells)
    assert all(
        cell.rgb.shape == (CELL_OUTPUT_SIZE, CELL_OUTPUT_SIZE, 3)
        for cell in result.cells
    )
    assert result.homography.virtual_grid_quad is not None
    assert result.homography.virtual_grid_quad[3][1] > 299
    assert result.to_dict()["cropperVersion"] == CROPPER_VERSION


def test_sequence_29_source_aware_crop_is_deterministic_and_supported() -> None:
    root = Path(__file__).resolve().parents[3]
    source_bgr = cv2.imread(
        str(root / "examples/imgs/5983122166590934320.jpg"),
        cv2.IMREAD_COLOR,
    )
    assert source_bgr is not None
    source_rgb = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB)
    analysis_quad = (
        Point(386, 329),
        Point(679, 317),
        Point(669, 459),
        Point(396, 436),
    )

    first = build_source_projective_lattice_crops(source_rgb, analysis_quad)
    second = build_source_projective_lattice_crops(source_rgb, analysis_quad)

    assert first.status == "cropped"
    assert first.minimum_support_fraction == 1.0
    assert len(first.cells) == 15
    assert first.to_dict() == second.to_dict()
    assert [
        np.array_equal(left.rgb, right.rgb)
        for left, right in zip(first.cells, second.cells, strict=True)
    ] == [True] * 15


def test_sequence_3_uses_bounded_analysis_fallback_after_locator_failure() -> None:
    root = Path(__file__).resolve().parents[3]
    source_bgr = cv2.imread(
        str(root / "examples/imgs/5983122166590934317.jpg"),
        cv2.IMREAD_COLOR,
    )
    assert source_bgr is not None
    source_rgb = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB)
    projective_analysis_quad = (
        Point(635, 406),
        Point(807, 405),
        Point(832, 529),
        Point(633, 469),
    )

    primary = build_source_projective_lattice_crops(
        source_rgb,
        projective_analysis_quad,
    )
    result = build_bounding_fallback_source_projective_lattice_crops(
        source_rgb,
        projective_analysis_quad,
        (633, 394, 174, 122),
    )

    assert primary.status == "fallback"
    assert primary.fallback_reason == "GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED"
    assert result.status == "cropped"
    assert result.minimum_support_fraction == 1.0
    assert len(result.cells) == 15
    assert result.analysis_frame_source == "detector-bounding-box-fallback"
    assert result.primary_fallback_reason == primary.fallback_reason
    assert result.to_dict()["cropperVersion"] == BOUNDING_FALLBACK_CROPPER_VERSION
