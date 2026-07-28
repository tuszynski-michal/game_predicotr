from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import DETECTOR_VERSION, Point
from game_predictor_worker.images.rectification import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    BoardCropError,
    BoardGeometry,
    PageGeometry,
    PerspectiveBoardCellCropper,
    crop_detected_corpus,
)
from PIL import Image


def _canonical_board() -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    board = np.full((BOARD_HEIGHT, BOARD_WIDTH, 3), (25, 30, 45), dtype=np.uint8)
    board[:15, :] = (220, 20, 20)
    board[-15:, :] = (220, 20, 20)
    board[:, :25] = (220, 20, 20)
    board[:, -25:] = (220, 20, 20)
    colors: list[tuple[int, int, int]] = []
    for row in range(3):
        for column in range(5):
            color = (
                30 + row * 70,
                25 + column * 40,
                40 + (row * 5 + column) * 10,
            )
            colors.append(color)
            y0 = 15 + row * CELL_HEIGHT
            x0 = 25 + column * CELL_WIDTH
            board[y0 : y0 + CELL_HEIGHT, x0 : x0 + CELL_WIDTH] = color
    return board, colors


def _synthetic_page() -> tuple[np.ndarray, PageGeometry, list[tuple[int, int, int]]]:
    canonical, colors = _canonical_board()
    page = np.full((1200, 1900, 3), (15, 20, 80), dtype=np.uint8)
    source = np.array(
        [
            [0, 0],
            [BOARD_WIDTH - 1, 0],
            [BOARD_WIDTH - 1, BOARD_HEIGHT - 1],
            [0, BOARD_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    boards: list[BoardGeometry] = []
    for row in range(3):
        for column in range(3):
            left = 80 + column * 610
            top = 70 + row * 370
            quad = (
                Point(left + 15, top + 12),
                Point(left + 500, top),
                Point(left + 515, top + 292),
                Point(left, top + 305),
            )
            destination = np.array(
                [[point.x, point.y] for point in quad],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(source, destination)
            warped = cv2.warpPerspective(
                canonical,
                matrix,
                (page.shape[1], page.shape[0]),
            )
            mask = cv2.warpPerspective(
                np.full((BOARD_HEIGHT, BOARD_WIDTH), 255, dtype=np.uint8),
                matrix,
                (page.shape[1], page.shape[0]),
            )
            page[mask > 0] = warped[mask > 0]
            boards.append(
                BoardGeometry(
                    position_index=row * 3 + column,
                    quad=quad,
                )
            )
    return (
        page,
        PageGeometry(
            status="detected",
            image_width=page.shape[1],
            image_height=page.shape[0],
            boards=tuple(boards),
        ),
        colors,
    )


def _geometry_dict(geometry: PageGeometry) -> dict[str, object]:
    return {
        "boards": [
            {
                "positionIndex": board.position_index,
                "quad": [point.to_dict() for point in board.quad],
            }
            for board in geometry.boards
        ],
        "imageHeight": geometry.image_height,
        "imageWidth": geometry.image_width,
        "reviewReasons": list(geometry.review_reasons),
        "status": geometry.status,
    }


def test_perspective_crop_preserves_3x5_row_major_mapping() -> None:
    page, geometry, expected_colors = _synthetic_page()
    before = page.copy()

    result = PerspectiveBoardCellCropper().crop(page, geometry)

    assert result.status == "cropped"
    assert [board.position_index for board in result.boards] == list(range(9))
    assert np.array_equal(page, before)
    first = result.boards[0]
    assert first.board_rgb.shape == (BOARD_HEIGHT, BOARD_WIDTH, 3)
    assert first.grid_overlay_rgb.shape == (BOARD_HEIGHT, BOARD_WIDTH, 3)
    assert len(first.transform_matrix) == 3
    assert [(cell.row_index, cell.column_index) for cell in first.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    for cell, expected in zip(first.cells, expected_colors, strict=True):
        assert cell.rgb.shape == (CELL_HEIGHT, CELL_WIDTH, 3)
        center = cell.rgb[15:-15, 15:-15].mean(axis=(0, 1))
        assert np.max(np.abs(center - np.array(expected))) < 4


@pytest.mark.parametrize(
    ("geometry_transform", "reason"),
    [
        (
            lambda geometry: PageGeometry(
                status="needs_review",
                image_width=geometry.image_width,
                image_height=geometry.image_height,
                boards=(),
                review_reasons=("BOARD_CANDIDATE_COUNT",),
            ),
            "BOARD_CROP_UPSTREAM_NEEDS_REVIEW",
        ),
        (
            lambda geometry: PageGeometry(
                status="detected",
                image_width=geometry.image_width,
                image_height=geometry.image_height,
                boards=(),
            ),
            "BOARD_CROP_BOARD_COUNT",
        ),
        (
            lambda geometry: PageGeometry(
                status="detected",
                image_width=geometry.image_width,
                image_height=geometry.image_height,
                boards=(
                    BoardGeometry(position_index=1, quad=geometry.boards[0].quad),
                    *geometry.boards[1:],
                ),
            ),
            "BOARD_CROP_INDEX_SEQUENCE",
        ),
    ],
)
def test_incomplete_geometry_needs_review_without_partial_crops(
    geometry_transform: object,
    reason: str,
) -> None:
    page, geometry, _ = _synthetic_page()
    transform = geometry_transform
    assert callable(transform)

    result = PerspectiveBoardCellCropper().crop(page, transform(geometry))

    assert result.status == "needs_review"
    assert result.review_reasons == (reason,)
    assert not result.boards


def test_partial_final_page_crops_contiguous_boards() -> None:
    page, geometry, _ = _synthetic_page()
    partial = PageGeometry(
        status="detected",
        image_width=geometry.image_width,
        image_height=geometry.image_height,
        boards=geometry.boards[:5],
    )

    result = PerspectiveBoardCellCropper().crop(page, partial)

    assert result.status == "cropped"
    assert [board.position_index for board in result.boards] == list(range(5))
    assert all(len(board.cells) == 15 for board in result.boards)


@pytest.mark.parametrize(
    ("quad", "reason"),
    [
        (
            (
                Point(-1, 20),
                Point(200, 20),
                Point(200, 180),
                Point(20, 180),
            ),
            "BOARD_CROP_QUAD_OUT_OF_BOUNDS",
        ),
        (
            (
                Point(20, 20),
                Point(200, 180),
                Point(200, 20),
                Point(20, 180),
            ),
            "BOARD_CROP_QUAD_NOT_CONVEX",
        ),
        (
            (
                Point(20, 20),
                Point(22, 20),
                Point(22, 22),
                Point(20, 22),
            ),
            "BOARD_CROP_QUAD_DEGENERATE",
        ),
    ],
)
def test_invalid_quad_has_stable_review_reason(
    quad: tuple[Point, Point, Point, Point],
    reason: str,
) -> None:
    page, geometry, _ = _synthetic_page()
    boards = (
        BoardGeometry(position_index=0, quad=quad),
        *geometry.boards[1:],
    )

    result = PerspectiveBoardCellCropper().crop(
        page,
        PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=boards,
        ),
    )

    assert result.status == "needs_review"
    assert result.review_reasons == (reason,)
    assert not result.boards


def test_cropper_rejects_invalid_image_contract() -> None:
    _, geometry, _ = _synthetic_page()
    with pytest.raises(BoardCropError) as raised:
        PerspectiveBoardCellCropper().crop(
            np.zeros((20, 20), dtype=np.uint8),
            geometry,
        )

    assert raised.value.code == "BOARD_CROP_INVALID_IMAGE"


def _write_runner_inputs(
    root: Path,
) -> tuple[Path, Path, Path, np.ndarray]:
    page, geometry, _ = _synthetic_page()
    normalization_root = root / "normalization"
    normalized_relative = "image-normalization-v1/aa/source/normalized.png"
    normalized_path = normalization_root / Path(*PurePosixPath(normalized_relative).parts)
    normalized_path.parent.mkdir(parents=True)
    Image.fromarray(page).save(normalized_path, format="PNG")
    normalized_bytes = normalized_path.read_bytes()
    normalization = {
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
    normalization_path = root / "normalization-report.json"
    normalization_path.write_text(
        json.dumps(normalization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    detection = {
        "detections": [
            {
                "normalizedRelativePath": normalized_relative,
                "result": _geometry_dict(geometry),
                "sourceChecksumSha256": "a" * 64,
            }
        ],
        "detectorVersion": DETECTOR_VERSION,
        "normalizationReportSha256": hashlib.sha256(normalization_path.read_bytes()).hexdigest(),
        "status": "detected",
    }
    detection_path = root / "detection-report.json"
    detection_path.write_text(
        json.dumps(detection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalization_path, detection_path, normalization_root, page


def test_corpus_runner_writes_complete_immutable_artifacts(tmp_path: Path) -> None:
    normalization, detection, normalization_root, _ = _write_runner_inputs(tmp_path)
    artifact_root = tmp_path / "crops"

    first = crop_detected_corpus(
        normalization,
        detection,
        normalization_root,
        artifact_root,
    )
    payload = first.to_dict()
    first_board = first.images[0].boards[0]
    first_cell = first_board.cells[0]
    cell_path = artifact_root / Path(*PurePosixPath(first_cell.relative_path).parts)
    first_mtime = cell_path.stat().st_mtime_ns
    second = crop_detected_corpus(
        normalization,
        detection,
        normalization_root,
        artifact_root,
    )

    assert payload["status"] == "cropped"
    assert payload["boardCount"] == 9
    assert payload["cellCount"] == 135
    assert len(first.images[0].boards) == 9
    assert all(len(board.cells) == 15 for board in first.images[0].boards)
    assert first.to_json_bytes() == second.to_json_bytes()
    assert cell_path.stat().st_mtime_ns == first_mtime


def test_corpus_runner_blocks_normalized_checksum_drift(tmp_path: Path) -> None:
    normalization, detection, normalization_root, _ = _write_runner_inputs(tmp_path)
    normalized_path = next(normalization_root.rglob("normalized.png"))
    normalized_path.write_bytes(b"changed")

    with pytest.raises(BoardCropError) as raised:
        crop_detected_corpus(
            normalization,
            detection,
            normalization_root,
            tmp_path / "crops",
        )

    assert raised.value.code == "BOARD_CROP_NORMALIZED_CHECKSUM_MISMATCH"
