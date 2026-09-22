from __future__ import annotations

import numpy as np
import pytest
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_worker.images.board_cell_geometry_estimator import BoardCellGeometryEstimate
from game_predictor_worker.images.contrast_frame_grid_v12 import (
    ContrastFrameGridV12Profile,
    ContrastFrameGridV12Registrar,
    _refine_frame_by_local_contrast,
    _select_edge,
    build_contrast_frame_grid_v12_profile,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_registration import PageRegistrationInitialization
from game_predictor_worker.images.partial_grid_learning import (
    build_partial_grid_training_profile,
)


def _frame_grid_sample() -> dict[str, object]:
    frames: list[list[dict[str, int]]] = []
    grids: list[list[dict[str, int]]] = []
    for row in range(3):
        for column in range(3):
            left, top = 20 + column * 120, 20 + row * 90
            right, bottom = left + 100, top + 70
            frames.append(
                [
                    {"x": left, "y": top},
                    {"x": right, "y": top},
                    {"x": right, "y": bottom},
                    {"x": left, "y": bottom},
                ]
            )
            grids.append(
                [
                    {"x": left + 8, "y": top + 12},
                    {"x": right - 6, "y": top + 12},
                    {"x": right - 6, "y": bottom - 4},
                    {"x": left + 8, "y": bottom - 4},
                ]
            )
    return {
        "a" * 64: {
            "boardFrameQuads": frames,
            "decisionChecksumSha256": "b" * 64,
            "imageHeight": 300,
            "imageWidth": 400,
            "overrideId": "manual-v12-sample",
            "revision": 1,
            "symbolGridQuads": grids,
        }
    }


def test_profile_learns_four_asymmetric_margins_from_one_game_only() -> None:
    payload = build_contrast_frame_grid_v12_profile(_frame_grid_sample())
    profile = ContrastFrameGridV12Profile.from_payload(payload)

    left, top, right, bottom = profile.margins()

    assert profile.available is True
    assert payload["sampleSourceCount"] == 1
    assert payload["sampleCount"] == 9
    assert left == pytest.approx(0.08)
    assert top == pytest.approx(12 / 70)
    assert right == pytest.approx(0.06)
    assert bottom == pytest.approx(4 / 70)


def test_empty_profile_requires_manual_pair_before_registration() -> None:
    profile = ContrastFrameGridV12Profile.from_payload(build_contrast_frame_grid_v12_profile({}))
    registrar = ContrastFrameGridV12Registrar(profile, load_anchor_rgb=lambda _checksum: None)

    evaluation = registrar.evaluate(
        np.zeros((300, 400, 3), dtype=np.uint8), active_board_slots=range(9)
    )

    assert evaluation.result is None
    assert evaluation.reason_code == "IMAGE_CONTRAST_FRAME_GRID_PROFILE_REQUIRED"


def test_full_profile_excludes_partial_and_operator_excluded_sources() -> None:
    sample = _frame_grid_sample()
    base = sample["a" * 64]
    assert isinstance(base, dict)
    complete = [GeometryQualification().to_dict() for _ in range(9)]
    partial = list(complete)
    partial[2] = GeometryQualification(
        "pending_partial",
        (0, 5, 10),
        True,
        "missing_pixels",
        True,
        "manual-geometry-qualification-v2",
    ).to_dict()
    excluded = list(complete)
    excluded[7] = GeometryQualification(
        exclude_from_geometry_training=True, exclusion_reason="manual_exclusion"
    ).to_dict()
    sample["b" * 64] = {**base, "slotQualifications": partial, "overrideId": "partial"}
    sample["c" * 64] = {**base, "slotQualifications": excluded, "overrideId": "excluded"}
    sample["d" * 64] = {**base, "slotQualifications": complete, "overrideId": "full"}

    profile = build_contrast_frame_grid_v12_profile(sample)

    assert profile["sampleSourceCount"] == 2
    assert [item["sourceChecksumSha256"] for item in profile["samples"]] == [
        "a" * 64,
        "d" * 64,
    ]
    partial_profile = build_partial_grid_training_profile(sample)
    assert partial_profile is not None
    assert partial_profile.source_count == 1


def test_local_frame_refinement_uses_blue_contrast_not_a_red_hue() -> None:
    rgb = np.full((320, 520, 3), (35, 35, 35), dtype=np.uint8)
    rgb[80:240, 150:370] = (20, 130, 220)
    rgb[86:234, 156:364] = (155, 155, 155)
    initial = (
        Point(162, 92),
        Point(358, 92),
        Point(358, 228),
        Point(162, 228),
    )

    refined = _refine_frame_by_local_contrast(rgb, initial)

    assert refined is not None
    quad, contrast = refined
    assert contrast >= 8.0
    assert max(abs(quad[index].x - (150, 370, 370, 150)[index]) for index in range(4)) <= 7
    assert max(abs(quad[index].y - (80, 80, 240, 240)[index]) for index in range(4)) <= 7


def test_equal_separated_contrast_edges_require_manual_correction() -> None:
    assert _select_edge(((70, 12.0), (82, 12.0), (76, 1.0))) is None


def test_evaluate_converts_float_estimator_quad_to_page_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = ContrastFrameGridV12Profile.from_payload(
        build_contrast_frame_grid_v12_profile(_frame_grid_sample())
    )
    rgb = np.full((300, 400, 3), (35, 35, 35), dtype=np.uint8)
    initial_quads = []
    for row in range(3):
        for column in range(3):
            left, top = 20 + column * 120, 20 + row * 90
            right, bottom = left + 100, top + 70
            rgb[top:bottom, left:right] = (20, 130, 220)
            rgb[top + 6 : bottom - 6, left + 6 : right - 6] = (155, 155, 155)
            initial_quads.append(
                (
                    Point(left + 2, top + 2),
                    Point(right - 2, top + 2),
                    Point(right - 2, bottom - 2),
                    Point(left + 2, bottom - 2),
                )
            )
    registrar = ContrastFrameGridV12Registrar(profile, load_anchor_rgb=lambda _checksum: rgb)
    initialization = PageRegistrationInitialization(
        anchor_source_checksum_sha256="a" * 64,
        active_board_slots=tuple(range(9)),
        initialization_quads=tuple(initial_quads),
        native_homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        inlier_count=12,
        inlier_ratio=0.9,
        p95_reprojection_error=1.0,
        feature_count=24,
    )
    monkeypatch.setattr(
        registrar._registrar, "initialize", lambda *_args, **_kwargs: initialization
    )

    def estimated_grid(_rgb: np.ndarray, frame: object) -> BoardCellGeometryEstimate:
        points = tuple(frame)
        return BoardCellGeometryEstimate(
            status="estimated",
            lattice_bounds_quad=(
                (points[0].x + 8.5, points[0].y + 10.5),
                (points[1].x - 6.5, points[1].y + 10.5),
                (points[2].x - 6.5, points[2].y - 4.5),
                (points[3].x + 8.5, points[3].y - 4.5),
            ),
            cells=(),
            evidence=None,
            candidate_center_count=0,
            assigned_candidate_count=0,
            reliable_center_count=0,
            inlier_slots=(),
            inlier_p95_residual_px=None,
            fallback_reason=None,
        )

    monkeypatch.setattr(
        "game_predictor_worker.images.contrast_frame_grid_v12.estimate_board_cell_geometry",
        estimated_grid,
    )

    evaluation = registrar.evaluate(rgb, active_board_slots=range(9))

    assert evaluation.reason_code is None
    assert evaluation.result is not None
    assert all(
        isinstance(point, Point) for quad in evaluation.result.symbol_grid_quads for point in quad
    )
