from __future__ import annotations

from pathlib import Path

from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.rectification import BoardGeometry, PageGeometry
from game_predictor_worker.images.symbol_grid_overrides import (
    OVERRIDE_SET_VERSION,
    ReviewedSymbolGridOverrides,
)
from game_predictor_worker.images.symbol_grid_refinement import (
    MANUAL_SOURCE_QUAD_SOURCE,
)


def test_real_review_applies_only_six_exact_observation_overrides() -> None:
    root = Path(__file__).resolve().parents[3]
    overrides = ReviewedSymbolGridOverrides.from_files(
        root / "artifacts/m5-symbol-grid-fallback-review/reviewed-geometry.json",
        root / "ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json",
    )

    assert overrides.profile_set_version == OVERRIDE_SET_VERSION
    assert overrides.override_count == 6

    source = "5f8905f9e0435ae28ea3c90810816d223def815a94592e9a04e7bb05957d5a0e"
    geometry = PageGeometry(
        status="detected",
        image_width=960,
        image_height=1280,
        boards=(
            BoardGeometry(
                position_index=0,
                quad=(Point(1, 1), Point(2, 1), Point(2, 2), Point(1, 2)),
            ),
            BoardGeometry(
                position_index=1,
                quad=(
                    Point(401, 314),
                    Point(594, 322),
                    Point(582, 413),
                    Point(410, 375),
                ),
            ),
        ),
    )

    calibrated = overrides.calibrate(source, geometry)

    assert calibrated.boards[0] == geometry.boards[0]
    assert calibrated.boards[1].quad != geometry.boards[1].quad
    assert calibrated.boards[1].source_quad_source == MANUAL_SOURCE_QUAD_SOURCE
    assert calibrated.boards[1].symbol_refinement is not None
    assert calibrated.boards[1].symbol_refinement.status == "manual_override"
    assert calibrated.boards[1].calibration_anchor_sequence_numbers == (11,)
