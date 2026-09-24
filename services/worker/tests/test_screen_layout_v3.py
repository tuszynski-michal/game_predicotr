from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.screen_layout_v3 import (
    BoardGrid,
    BoardStatus,
    ResultStatus,
    detect_screen_layout_v3,
)
from game_predictor_worker.images.screen_layout_v3.engine import _screen_consensus_gate
from numpy.typing import NDArray

CANVAS = (1600, 1100)  # width, height of the flat "screen photo" before perspective
CELL = 56
GAP_X = 70
GAP_Y = 90
PANEL_PAD = 14
ORIGIN = (170, 150)
SYMBOL_COLOURS = [
    (40, 40, 230),
    (40, 200, 240),
    (60, 200, 60),
    (220, 80, 200),
    (240, 240, 240),
    (30, 140, 255),
]


def _board_origin(column: int, row: int) -> tuple[int, int]:
    board_w = 5 * CELL + 2 * PANEL_PAD
    board_h = 3 * CELL + 2 * PANEL_PAD
    return (
        ORIGIN[0] + column * (board_w + GAP_X) + PANEL_PAD,
        ORIGIN[1] + row * (board_h + GAP_Y) + PANEL_PAD,
    )


def _flat_screen(seed: int = 7) -> tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]]:
    rng = np.random.default_rng(seed)
    width, height = CANVAS
    image = np.zeros((height, width, 3), np.uint8)
    image[:] = (25, 20, 20)
    cv2.rectangle(image, (110, 90), (width - 110, height - 110), (200, 40, 20), -1)  # BGR blue
    truth: dict[int, NDArray[np.float64]] = {}
    for row in range(3):
        for column in range(3):
            gx, gy = _board_origin(column, row)
            cv2.rectangle(
                image,
                (gx - PANEL_PAD, gy - PANEL_PAD),
                (gx + 5 * CELL + PANEL_PAD, gy + 3 * CELL + PANEL_PAD),
                (30, 60, 200),
                -1,
            )
            cv2.rectangle(image, (gx, gy), (gx + 5 * CELL, gy + 3 * CELL), (25, 25, 30), -1)
            for c in range(1, 5):
                cv2.line(
                    image, (gx + c * CELL, gy), (gx + c * CELL, gy + 3 * CELL), (40, 90, 200), 2
                )
            for r in range(3):
                for c in range(5):
                    colour = SYMBOL_COLOURS[int(rng.integers(len(SYMBOL_COLOURS)))]
                    center = (gx + c * CELL + CELL // 2, gy + r * CELL + CELL // 2)
                    if rng.random() < 0.5:
                        cv2.circle(image, center, int(CELL * 0.33), colour, -1)
                    else:
                        half = int(CELL * 0.3)
                        cv2.rectangle(
                            image,
                            (center[0] - half, center[1] - half),
                            (center[0] + half, center[1] + half),
                            colour,
                            -1,
                        )
            cv2.putText(
                image,
                f"{1000 + row * 3 + column}",
                (gx + CELL, gy + 3 * CELL + PANEL_PAD + 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (255, 255, 255),
                3,
            )
            truth[row * 3 + column] = np.array(
                [
                    [gx, gy],
                    [gx + 5 * CELL, gy],
                    [gx + 5 * CELL, gy + 3 * CELL],
                    [gx, gy + 3 * CELL],
                ],
                dtype=np.float64,
            )
    return image, truth


def _perspective(
    image: NDArray[np.uint8], truth: dict[int, NDArray[np.float64]]
) -> tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]]:
    height, width = image.shape[:2]
    source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    target = np.float32([[60, 40], [width - 20, 0], [width - 90, height - 10], [30, height - 60]])
    matrix = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(image, matrix, (width, height))
    moved = {
        k: cv2.perspectiveTransform(q.reshape(-1, 1, 2), matrix).reshape(-1, 2).astype(np.float64)
        for k, q in truth.items()
    }
    return np.asarray(warped, np.uint8), moved


def _rgb(bgr: NDArray[np.uint8]) -> NDArray[np.uint8]:
    return np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), np.uint8)


@pytest.fixture(scope="module")
def screen() -> tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]]:
    flat, truth = _flat_screen()
    return _perspective(flat, truth)


def test_detects_all_nine_grids_without_template(
    screen: tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]],
) -> None:
    image, truth = screen
    result = detect_screen_layout_v3(_rgb(image))

    assert result.status is ResultStatus.DETECTED
    assert [b.position_index for b in result.boards] == list(range(9))
    for board in result.boards:
        error = np.linalg.norm(board.quad - truth[board.position_index], axis=1).max()
        assert error < 0.12 * CELL, (board.position_index, error)
        assert board.status is BoardStatus.COMPLETE, board.reason_codes


def test_lateral_crop_marks_whole_columns_unavailable(
    screen: tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]],
) -> None:
    image, truth = screen
    cut = int(truth[2][1, 0] - 1.5 * CELL)  # right edge inside the last two columns of board 3
    result = detect_screen_layout_v3(_rgb(np.ascontiguousarray(image[:, :cut])))

    assert result.status is ResultStatus.DETECTED
    right = {b.position_index: b for b in result.boards if b.position_index in (2, 5, 8)}
    board = right[2]
    assert board.status is BoardStatus.PARTIAL, board.reason_codes
    missing_columns = {i % 5 for i in board.unavailable_cell_indices}
    assert missing_columns and max(missing_columns) == 4
    assert all(
        r * 5 + c in board.unavailable_cell_indices for c in missing_columns for r in range(3)
    )
    for other in result.boards:
        if other.position_index % 3 != 2:
            assert other.status is BoardStatus.COMPLETE, (other.position_index, other.reason_codes)


def test_vertical_crop_is_never_accepted(
    screen: tuple[NDArray[np.uint8], dict[int, NDArray[np.float64]]],
) -> None:
    image, truth = screen
    cut = int(truth[1][0, 1] + 1.5 * CELL)  # top edge inside the first two rows of the top boards
    result = detect_screen_layout_v3(_rgb(np.ascontiguousarray(image[cut:])))

    assert result.status is ResultStatus.DETECTED
    top = [b for b in result.boards if b.position_index < 3]
    assert all(b.status is BoardStatus.NEEDS_REVIEW for b in top)
    assert all("BOARD_CROPPED_VERTICALLY" in b.reason_codes for b in top)


def test_rejects_non_rgb_input() -> None:
    with pytest.raises(ValueError):
        detect_screen_layout_v3(np.zeros((10, 10), np.uint8))


def _board(index: int, reasons: tuple[str, ...]) -> BoardGrid:
    status = BoardStatus.NEEDS_REVIEW if reasons else BoardStatus.COMPLETE
    return BoardGrid(index, status, reasons, np.zeros((4, 6, 2)), (), 1.0, 0.9, True)


def test_consensus_gate_keeps_boards_when_few_disagree() -> None:
    boards = [_board(i, ("BOARD_DISAGREES_WITH_SCREEN_MODEL",) if i < 3 else ()) for i in range(9)]
    gated = _screen_consensus_gate(boards)
    assert [b.status for b in gated] == [b.status for b in boards]


def test_consensus_gate_rejects_whole_screen_when_many_disagree() -> None:
    boards = [_board(i, ("BOARD_ALIGNMENT_LOW",) if i < 4 else ()) for i in range(9)]
    gated = _screen_consensus_gate(boards)
    assert all(b.status is BoardStatus.NEEDS_REVIEW for b in gated)
    assert all("SCREEN_CONSENSUS_WEAK" in b.reason_codes for b in gated)


def test_crop_reasons_do_not_count_as_disagreement() -> None:
    boards = [_board(i, ("BOARD_CROPPED_VERTICALLY",) if i < 5 else ()) for i in range(9)]
    gated = _screen_consensus_gate(boards)
    assert sum(b.status is BoardStatus.COMPLETE for b in gated) == 4
