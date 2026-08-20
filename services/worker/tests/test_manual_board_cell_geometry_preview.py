from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
    ManualBoardCellGeometryPreviewer,
    ManualBoardCellGeometryPreviewError,
)


def _source(tmp_path: Path) -> tuple[Path, str, list[tuple[int, int, int]]]:
    rgb = np.full((420, 620, 3), 7, dtype=np.uint8)
    colors: list[tuple[int, int, int]] = []
    for row in range(3):
        for column in range(5):
            color = (30 + row * 60, 25 + column * 35, 45 + (row * 5 + column) * 8)
            colors.append(color)
            rgb[
                50 + row * 100 : 50 + (row + 1) * 100,
                60 + column * 100 : 60 + (column + 1) * 100,
            ] = color
    encoded, payload = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert encoded
    content = bytes(payload)
    source = tmp_path / "source.png"
    source.write_bytes(content)
    return source, hashlib.sha256(content).hexdigest(), colors


def _preview(tmp_path: Path):
    source, checksum, colors = _source(tmp_path)
    preview = ManualBoardCellGeometryPreviewer().preview(
        source_path=source,
        expected_source_sha256=checksum,
        source_order_index=10,
        source_image_id="source-id",
        source_image_relative_path="sources/source.png",
        source_group="import-id",
        sequence_number=91,
        position_index=0,
        lattice_bounds_quad=(
            (60.0, 50.0),
            (560.0, 50.0),
            (560.0, 350.0),
            (60.0, 350.0),
        ),
        decision_checksum_sha256="d" * 64,
    )
    return preview, colors


def test_manual_v19_preview_contains_exactly_15_final_source_direct_crops(
    tmp_path: Path,
) -> None:
    preview, colors = _preview(tmp_path)

    assert preview.cropper_version == CROPPER_VERSION
    assert len(preview.cells) == 15
    assert [(cell.row_index, cell.column_index) for cell in preview.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    sheet = cv2.imdecode(np.frombuffer(preview.contact_sheet_png, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert sheet is not None
    assert sheet.shape[:2] == (
        3 * MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
        5 * MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
    )
    sheet_rgb = cv2.cvtColor(sheet, cv2.COLOR_BGR2RGB)
    for index, expected in enumerate(colors):
        row, column = divmod(index, 5)
        size = MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE
        tile = sheet_rgb[row * size : (row + 1) * size, column * size : (column + 1) * size]
        assert np.max(np.abs(tile.mean(axis=(0, 1)) - np.asarray(expected))) < 2
    assert (
        preview.contact_sheet_checksum_sha256
        == hashlib.sha256(preview.contact_sheet_png).hexdigest()
    )
    assert all(
        cell.checksum_sha256 == hashlib.sha256(cell.png).hexdigest() for cell in preview.cells
    )
    assert list(tmp_path.iterdir()) == [tmp_path / "source.png"]


def test_manual_v19_preview_fails_closed_for_checksum_and_crossed_lattice(
    tmp_path: Path,
) -> None:
    source, checksum, _ = _source(tmp_path)
    previewer = ManualBoardCellGeometryPreviewer()
    common = {
        "source_path": source,
        "source_order_index": 0,
        "source_image_id": "source-id",
        "source_image_relative_path": "source.png",
        "source_group": "import-id",
        "sequence_number": 1,
        "position_index": 0,
        "decision_checksum_sha256": "a" * 64,
    }

    with pytest.raises(ManualBoardCellGeometryPreviewError) as drifted:
        previewer.preview(
            **common,
            expected_source_sha256="0" * 64,
            lattice_bounds_quad=((60.0, 50.0), (560.0, 50.0), (560.0, 350.0), (60.0, 350.0)),
        )
    assert drifted.value.code == "BOARD_CELL_GEOMETRY_PREVIEW_SOURCE_CHECKSUM_DRIFT"

    with pytest.raises(ManualBoardCellGeometryPreviewError) as crossed:
        previewer.preview(
            **common,
            expected_source_sha256=checksum,
            lattice_bounds_quad=((60.0, 50.0), (560.0, 350.0), (560.0, 50.0), (60.0, 350.0)),
        )
    assert crossed.value.code == "BOARD_CELL_GEOMETRY_QUAD_INVALID"
