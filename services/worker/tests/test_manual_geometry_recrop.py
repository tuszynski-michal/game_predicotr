from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.manual_geometry_recrop import (
    ManualGeometryRecropper,
)
from game_predictor_worker.images.rectification import BoardCropError


def _source(path: Path) -> tuple[Path, str]:
    rgb = np.zeros((420, 720, 3), dtype=np.uint8)
    for row in range(3):
        for column in range(5):
            color = (
                30 + row * 60,
                30 + column * 35,
                220 - row * 40,
            )
            cv2.rectangle(
                rgb,
                (110 + column * 100, 70 + row * 90),
                (205 + column * 100, 155 + row * 90),
                color,
                -1,
            )
    encoded, buffer = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert encoded
    content = bytes(buffer)
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_manual_geometry_recrop_previews_and_persists_fifteen_cells(
    tmp_path: Path,
) -> None:
    source, checksum = _source(tmp_path / "source.png")
    recropper = ManualGeometryRecropper()

    preview = recropper.preview(
        source_path=source,
        expected_source_sha256=checksum,
        corners=(
            Point(100, 60),
            Point(620, 65),
            Point(625, 345),
            Point(95, 340),
        ),
    )

    assert preview.image_width == 720
    assert preview.image_height == 420
    assert len(preview.cells) == 15
    assert [(cell.row_index, cell.column_index) for cell in preview.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert hashlib.sha256(preview.board_png).hexdigest() == preview.board_checksum_sha256

    artifacts = recropper.persist(
        preview=preview,
        managed_data_root=tmp_path / "data",
        review_item_id="review-1",
        revision=1,
    )
    retry = recropper.persist(
        preview=preview,
        managed_data_root=tmp_path / "data",
        review_item_id="review-1",
        revision=1,
    )

    assert artifacts == retry
    assert len(artifacts.cells) == 15
    assert (tmp_path / "data" / Path(artifacts.board_relative_path)).is_file()
    assert all((tmp_path / "data" / Path(cell.relative_path)).is_file() for cell in artifacts.cells)


def test_manual_geometry_recrop_rejects_out_of_bounds_corner(tmp_path: Path) -> None:
    source, checksum = _source(tmp_path / "source.png")

    with pytest.raises(BoardCropError) as error:
        ManualGeometryRecropper().preview(
            source_path=source,
            expected_source_sha256=checksum,
            corners=(
                Point(-1, 60),
                Point(620, 65),
                Point(625, 345),
                Point(95, 340),
            ),
        )

    assert error.value.code == "MANUAL_GEOMETRY_OUT_OF_BOUNDS"
