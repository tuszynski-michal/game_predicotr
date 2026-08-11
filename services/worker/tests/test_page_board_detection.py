from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import (
    BoardDetection,
    ClassicalPageBoardDetector,
    GeometryDetectionError,
    _positive_integral,
    _refinement_window_densities,
    detect_normalized_corpus,
)
from PIL import Image


def _grid_image(
    *,
    missing: tuple[int, int] | None = None,
    extra: bool = False,
    shifted: tuple[int, int] | None = None,
) -> np.ndarray:
    image = np.full((640, 680, 3), (20, 30, 180), dtype=np.uint8)
    for row in range(3):
        for column in range(3):
            if missing == (row, column):
                continue
            shift_x = 30 if shifted == (row, column) else 0
            left = 60 + column * 200 + shift_x
            top = 60 + row * 150
            cv2.rectangle(
                image,
                (left, top),
                (left + 140, top + 80),
                (235, 25, 20),
                10,
            )
    if extra:
        cv2.rectangle(
            image,
            (260, 520),
            (400, 600),
            (235, 25, 20),
            10,
        )
    return image


def _center(board: BoardDetection) -> tuple[float, float]:
    x, y, width, height = board.bounding_box
    return x + width / 2, y + height / 2


def _partial_grid_image(board_count: int) -> np.ndarray:
    image = np.full((640, 680, 3), (20, 30, 180), dtype=np.uint8)
    for position in range(board_count):
        row, column = divmod(position, 3)
        left = 60 + column * 200
        top = 60 + row * 150
        cv2.rectangle(
            image,
            (left, top),
            (left + 140, top + 80),
            (235, 25, 20),
            10,
        )
    return image


def _fragment_grid_image(positions: set[int]) -> np.ndarray:
    image = np.full((640, 680, 3), (20, 30, 180), dtype=np.uint8)
    for position in sorted(positions):
        row, column = divmod(position, 3)
        left = 60 + column * 200
        top = 60 + row * 100
        cv2.rectangle(image, (left, top), (left + 140, top + 80), (235, 25, 20), 10)
    return image


@pytest.mark.parametrize(
    ("x", "y", "width", "height"),
    (
        (0, 0, 31, 27),
        (7, 11, 42, 35),
        (19, 23, 60, 44),
    ),
)
def test_integral_refinement_density_matches_boolean_mask_scan(
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    random = np.random.default_rng(20260808)
    mask = np.asarray(random.random((73, 91)) > 0.72, dtype=np.uint8) * 255
    roi = mask[y : y + height, x : x + width]
    border_y = max(2, height // 10)
    border_x = max(2, width // 16)
    border = np.zeros(roi.shape, dtype=np.bool_)
    border[:border_y, :] = True
    border[-border_y:, :] = True
    border[:, :border_x] = True
    border[:, -border_x:] = True

    actual = _refinement_window_densities(
        _positive_integral(mask),
        x=x,
        y=y,
        width=width,
        height=height,
    )

    assert actual == (
        float(np.mean(roi[border] > 0)),
        float(np.mean(roi[~border] > 0)),
    )


def test_synthetic_grid_returns_nine_boards_in_row_major_order() -> None:
    detector = ClassicalPageBoardDetector()
    image = _grid_image()
    before = image.copy()

    result = detector.detect(image)

    assert result.status == "detected"
    assert result.page_quad is not None
    assert result.candidate_count == 9
    assert [board.position_index for board in result.boards] == list(range(9))
    centers = [_center(board) for board in result.boards]
    assert centers[0][0] < centers[1][0] < centers[2][0]
    assert centers[0][1] < centers[3][1] < centers[6][1]
    assert all(len(board.quad) == 4 for board in result.boards)
    assert np.array_equal(image, before)
    assert result.to_dict() == detector.detect(image).to_dict()


@pytest.mark.parametrize(
    ("image", "reason"),
    [
        (_grid_image(missing=(1, 1)), "BOARD_CANDIDATE_COUNT"),
        (_grid_image(extra=True), "BOARD_CANDIDATE_COUNT"),
        (_grid_image(shifted=(1, 1)), "BOARD_GRID_COLUMN_ALIGNMENT"),
    ],
)
def test_unsupported_or_irregular_grid_needs_review(
    image: np.ndarray,
    reason: str,
) -> None:
    result = ClassicalPageBoardDetector().detect(image)

    assert result.status == "needs_review"
    assert reason in result.review_reasons
    assert not result.boards
    assert result.page_quad is None


def test_detector_rejects_invalid_image_contract() -> None:
    with pytest.raises(GeometryDetectionError) as raised:
        ClassicalPageBoardDetector().detect(np.zeros((20, 20), dtype=np.uint8))

    assert raised.value.code == "PAGE_DETECTOR_INVALID_IMAGE"


def test_explicit_partial_final_page_returns_contiguous_positions() -> None:
    result = ClassicalPageBoardDetector().detect(
        _partial_grid_image(5),
        expected_board_count=5,
        allow_grid_recovery=True,
    )

    assert result.status == "detected"
    assert [board.position_index for board in result.boards] == list(range(5))


def test_grid_recovery_does_not_invent_truly_missing_board() -> None:
    result = ClassicalPageBoardDetector().detect(
        _grid_image(missing=(1, 1)),
        expected_board_count=9,
        allow_grid_recovery=True,
    )

    assert result.status == "needs_review"
    assert result.review_reasons == ("BOARD_CANDIDATE_COUNT",)


def test_explicit_occlusion_recovery_fits_missing_cell_from_visible_grid() -> None:
    result = ClassicalPageBoardDetector().detect(
        _grid_image(missing=(1, 1)),
        expected_board_count=9,
        allow_grid_recovery=True,
        allow_occluded_grid_recovery=True,
    )

    assert result.status == "detected"
    assert [board.position_index for board in result.boards] == list(range(9))
    assert result.boards[4].refined_from_grid is True


def test_partial_grid_recovery_preserves_a_bounded_l_shape_hypothesis() -> None:
    image = _fragment_grid_image({1, 4, 6, 7})
    detector = ClassicalPageBoardDetector()

    historical = detector.detect(
        image,
        allow_grid_recovery=True,
        allow_occluded_grid_recovery=True,
    )
    recovered = detector.detect(
        image,
        allow_grid_recovery=True,
        allow_occluded_grid_recovery=True,
        allow_partial_grid_recovery=True,
    )

    assert historical.status == "needs_review"
    assert recovered.status == "detected"
    assert recovered.layout_hypotheses
    assert len(recovered.layout_hypotheses) <= 24
    assert [board.position_index for board in recovered.boards] == list(range(9))
    assert {
        board.position_index for board in recovered.boards if board.red_border_score >= 0.20
    } == {1, 4, 6, 7}


def test_corpus_runner_verifies_input_and_reuses_identical_overlay(
    tmp_path: Path,
) -> None:
    normalization_root = tmp_path / "normalization"
    normalized_relative = "image-normalization-v1/aa/source/normalized.png"
    normalized_path = normalization_root / Path(*PurePosixPath(normalized_relative).parts)
    normalized_path.parent.mkdir(parents=True)
    Image.fromarray(_grid_image()).save(normalized_path, format="PNG")
    normalized_bytes = normalized_path.read_bytes()
    normalization_report = {
        "images": [
            {
                "normalizedChecksumSha256": hashlib.sha256(normalized_bytes).hexdigest(),
                "normalizedRelativePath": normalized_relative,
                "sourceChecksumSha256": "a" * 64,
            }
        ],
        "normalizationVersion": "image-normalization-v1",
        "status": "clean",
    }
    report_path = tmp_path / "normalization-report.json"
    report_path.write_text(
        json.dumps(normalization_report, sort_keys=True),
        encoding="utf-8",
    )
    artifact_root = tmp_path / "geometry"

    first = detect_normalized_corpus(
        report_path,
        normalization_root,
        artifact_root,
    )
    overlay_relative = first.detections[0].overlay_relative_path
    overlay_path = artifact_root / Path(*PurePosixPath(overlay_relative).parts)
    first_mtime = overlay_path.stat().st_mtime_ns
    second = detect_normalized_corpus(
        report_path,
        normalization_root,
        artifact_root,
    )

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.detections[0].result.status == "detected"
    assert overlay_path.stat().st_mtime_ns == first_mtime


def test_corpus_runner_blocks_normalized_checksum_drift(tmp_path: Path) -> None:
    normalization_root = tmp_path / "normalization"
    normalized_path = normalization_root / "normalized.png"
    normalization_root.mkdir()
    normalized_path.write_bytes(b"not expected")
    report_path = tmp_path / "normalization-report.json"
    report_path.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "normalizedChecksumSha256": "0" * 64,
                        "normalizedRelativePath": "normalized.png",
                        "sourceChecksumSha256": "a" * 64,
                    }
                ],
                "normalizationVersion": "image-normalization-v1",
                "status": "clean",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(GeometryDetectionError) as raised:
        detect_normalized_corpus(
            report_path,
            normalization_root,
            tmp_path / "geometry",
        )

    assert raised.value.code == "PAGE_DETECTION_NORMALIZED_CHECKSUM_MISMATCH"
