from __future__ import annotations

from pathlib import Path

import cv2
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.rectification import BoardGeometry, PageGeometry
from game_predictor_worker.images.safe_context_crops import (
    CELL_OVERLAP_PX,
    GRID_OFFSET_Y_PX,
    PROJECTIVE_SOURCE_QUAD_SOURCE,
    ExpandedBoundingFrameCalibrator,
    ProjectiveExpandedFrameCalibrator,
    ProjectiveSafeContextBoardCellCropper,
    SafeContextBoardCellCropper,
)


def test_safe_context_uses_expanded_frame_and_overlapping_cells() -> None:
    root = Path(__file__).resolve().parents[3]
    calibrator = ExpandedBoundingFrameCalibrator.from_files(
        root / "ai_docs/quality/m5-corpus-manifest.json",
        root / "ai_docs/quality/m5-page-board-detection-report.json",
    )
    geometry = PageGeometry(
        status="detected",
        image_width=720,
        image_height=1280,
        boards=(
            BoardGeometry(
                position_index=0,
                quad=(
                    Point(127, 403),
                    Point(230, 406),
                    Point(231, 485),
                    Point(112, 483),
                ),
                bounding_box=(91, 401, 141, 86),
            ),
        ),
    )
    expanded = calibrator.calibrate("unused", geometry)

    assert expanded.boards[0].quad == (
        Point(74, 396),
        Point(248, 396),
        Point(248, 491),
        Point(74, 491),
    )

    source = cv2.imread(
        str(
            root
            / "artifacts/m5-normalization"
            / "image-normalization-v1"
            / "92"
            / "92cf1df591c082574088fb81ba6150f436f3dd2ebf381c9ad4c1fdeb8e59aec5"
            / "normalized.png"
        ),
        cv2.IMREAD_COLOR,
    )
    assert source is not None
    result = SafeContextBoardCellCropper().crop(
        cv2.cvtColor(source, cv2.COLOR_BGR2RGB),
        expanded,
    )

    assert result.status == "cropped"
    assert len(result.boards[0].cells) == 15
    assert result.boards[0].grid_contract.overlap_px == CELL_OVERLAP_PX
    assert result.boards[0].grid_contract.offset_y_px == GRID_OFFSET_Y_PX
    assert all(cell.rgb.shape == (90, 90, 3) for cell in result.boards[0].cells)


def test_sequence_29_projective_expansion_preserves_detector_perspective() -> None:
    root = Path(__file__).resolve().parents[3]
    calibrator = ProjectiveExpandedFrameCalibrator.from_files(
        root / "ai_docs/quality/m5-corpus-manifest.json",
        root / "ai_docs/quality/m5-page-board-detection-report.json",
    )
    geometry = PageGeometry(
        status="detected",
        image_width=960,
        image_height=1280,
        boards=(
            BoardGeometry(
                position_index=0,
                quad=(
                    Point(402, 336),
                    Point(652, 328),
                    Point(645, 448),
                    Point(410, 430),
                ),
                bounding_box=(390, 310, 267, 145),
            ),
        ),
    )

    expanded = calibrator.calibrate("unused", geometry)

    assert expanded.status == "detected"
    assert expanded.boards[0].quad == (
        Point(386, 329),
        Point(679, 317),
        Point(669, 459),
        Point(396, 436),
    )
    assert expanded.boards[0].source_quad_source == PROJECTIVE_SOURCE_QUAD_SOURCE
    top_left, top_right, bottom_right, bottom_left = expanded.boards[0].quad
    assert top_left.y != top_right.y
    assert bottom_left.y != bottom_right.y

    source = cv2.imread(
        str(root / "examples/imgs/5983122166590934320.jpg"),
        cv2.IMREAD_COLOR,
    )
    assert source is not None
    result = ProjectiveSafeContextBoardCellCropper().crop(
        cv2.cvtColor(source, cv2.COLOR_BGR2RGB),
        expanded,
    )

    assert result.status == "cropped"
    assert result.boards[0].source_quad == expanded.boards[0].quad
    assert len(result.boards[0].cells) == 15


def test_projective_expansion_fails_closed_at_image_boundary() -> None:
    root = Path(__file__).resolve().parents[3]
    calibrator = ProjectiveExpandedFrameCalibrator.from_files(
        root / "ai_docs/quality/m5-corpus-manifest.json",
        root / "ai_docs/quality/m5-page-board-detection-report.json",
    )
    geometry = PageGeometry(
        status="detected",
        image_width=200,
        image_height=200,
        boards=(
            BoardGeometry(
                position_index=0,
                quad=(
                    Point(0, 10),
                    Point(100, 10),
                    Point(100, 100),
                    Point(0, 100),
                ),
            ),
        ),
    )

    expanded = calibrator.calibrate("unused", geometry)

    assert expanded.status == "needs_review"
    assert expanded.boards == ()
    assert expanded.review_reasons == ("PROJECTIVE_FRAME_EXPANSION_INVALID",)
