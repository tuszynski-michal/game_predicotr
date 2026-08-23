from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from game_predictor_worker.images.manual_board_cell_geometry_preview import (
    MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_CELL_SIZE,
    MANUAL_BOARD_CELL_GEOMETRY_VERSION,
    ManualBoardCellGeometryPreviewer,
    ManualBoardCellGeometryPreviewError,
    manual_board_cell_geometry_decision_checksum,
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
        review_item_id="review-id",
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
        corrected_by="local-owner",
        expected_geometry_revision=2,
        expected_resolution_revision=4,
        command_checksum_sha256="d" * 64,
    )
    return preview, colors


def test_manual_v19_preview_contains_exactly_15_final_source_direct_crops(
    tmp_path: Path,
) -> None:
    preview, colors = _preview(tmp_path)

    assert preview.cropper_version == CROPPER_VERSION
    assert preview.manual_geometry_version == MANUAL_BOARD_CELL_GEOMETRY_VERSION
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
    assert preview.decision_checksum_sha256 == manual_board_cell_geometry_decision_checksum(
        review_item_id="review-id",
        source_order_index=10,
        source_image_id="source-id",
        source_image_checksum_sha256=preview.source_image_checksum_sha256,
        source_image_relative_path="sources/source.png",
        source_group="import-id",
        sequence_number=91,
        position_index=0,
        lattice_bounds_quad=preview.lattice_bounds_quad,
        corrected_by="local-owner",
        expected_geometry_revision=2,
        expected_resolution_revision=4,
        command_checksum_sha256="d" * 64,
        cropper_fingerprint_sha256=preview.cropper_fingerprint_sha256,
    )
    assert list(tmp_path.iterdir()) == [tmp_path / "source.png"]


def test_manual_v19_persistence_is_append_only_and_keeps_exact_preview_crops(
    tmp_path: Path,
) -> None:
    preview, _ = _preview(tmp_path)
    previewer = ManualBoardCellGeometryPreviewer()
    managed_root = tmp_path / "managed"

    with pytest.raises(ManualBoardCellGeometryPreviewError) as provenance_drift:
        previewer.persist(
            preview=replace(preview, corrected_by="different-owner"),
            managed_data_root=managed_root,
            revision=3,
        )
    assert provenance_drift.value.code == "BOARD_CELL_GEOMETRY_ARTIFACT_PROVENANCE_DRIFT"
    assert not managed_root.exists()

    artifacts = previewer.persist(
        preview=preview,
        managed_data_root=managed_root,
        revision=3,
    )

    assert artifacts.decision_checksum_sha256 == preview.decision_checksum_sha256
    assert artifacts.source_image_checksum_sha256 == preview.source_image_checksum_sha256
    assert artifacts.source_order_index == 10
    assert artifacts.position_index == 0
    assert artifacts.corrected_by == "local-owner"
    assert artifacts.manual_geometry_version == MANUAL_BOARD_CELL_GEOMETRY_VERSION
    assert len(artifacts.cells) == 15
    assert [(cell.row_index, cell.column_index) for cell in artifacts.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    for cell, expected in zip(artifacts.cells, preview.cells, strict=True):
        path = managed_root.joinpath(*Path(cell.relative_path).parts)
        assert path.read_bytes() == expected.png
        assert cell.checksum_sha256 == expected.checksum_sha256
        assert cell.source_quad == expected.source_quad
        assert cell.padded_source_quad == expected.padded_source_quad
    assert len(list(managed_root.rglob("*.png"))) == 15

    retried = previewer.persist(
        preview=preview,
        managed_data_root=managed_root,
        revision=3,
    )
    assert retried == artifacts
    assert len(list(managed_root.rglob("*.png"))) == 15


def test_manual_v19_decision_checksum_binds_actor_position_and_source(
    tmp_path: Path,
) -> None:
    preview, _ = _preview(tmp_path)
    common = {
        "review_item_id": preview.review_item_id,
        "source_order_index": preview.source_order_index,
        "source_image_id": preview.source_image_id,
        "source_image_checksum_sha256": preview.source_image_checksum_sha256,
        "source_image_relative_path": preview.source_image_relative_path,
        "source_group": preview.source_group,
        "sequence_number": preview.sequence_number,
        "position_index": preview.position_index,
        "lattice_bounds_quad": preview.lattice_bounds_quad,
        "corrected_by": preview.corrected_by,
        "expected_geometry_revision": preview.expected_geometry_revision,
        "expected_resolution_revision": preview.expected_resolution_revision,
        "command_checksum_sha256": preview.command_checksum_sha256,
        "cropper_fingerprint_sha256": preview.cropper_fingerprint_sha256,
    }

    assert manual_board_cell_geometry_decision_checksum(**common) == (
        preview.decision_checksum_sha256
    )
    assert (
        manual_board_cell_geometry_decision_checksum(**{**common, "corrected_by": "second-owner"})
        != preview.decision_checksum_sha256
    )
    assert (
        manual_board_cell_geometry_decision_checksum(**{**common, "position_index": 1})
        != preview.decision_checksum_sha256
    )
    assert (
        manual_board_cell_geometry_decision_checksum(
            **{**common, "source_image_checksum_sha256": "a" * 64}
        )
        != preview.decision_checksum_sha256
    )


def test_manual_v19_persistence_never_overwrites_a_drifted_revision_file(
    tmp_path: Path,
) -> None:
    preview, _ = _preview(tmp_path)
    previewer = ManualBoardCellGeometryPreviewer()
    managed_root = tmp_path / "managed"
    artifacts = previewer.persist(
        preview=preview,
        managed_data_root=managed_root,
        revision=1,
    )
    drifted = managed_root.joinpath(*Path(artifacts.cells[0].relative_path).parts)
    drifted.write_bytes(b"drifted")

    with pytest.raises(ManualBoardCellGeometryPreviewError) as collision:
        previewer.persist(
            preview=preview,
            managed_data_root=managed_root,
            revision=1,
        )

    assert collision.value.code == "BOARD_CELL_GEOMETRY_ARTIFACT_COLLISION"
    assert drifted.read_bytes() == b"drifted"


def test_manual_v19_preview_fails_closed_for_checksum_and_crossed_lattice(
    tmp_path: Path,
) -> None:
    source, checksum, _ = _source(tmp_path)
    previewer = ManualBoardCellGeometryPreviewer()
    common = {
        "source_path": source,
        "review_item_id": "review-id",
        "source_order_index": 0,
        "source_image_id": "source-id",
        "source_image_relative_path": "source.png",
        "source_group": "import-id",
        "sequence_number": 1,
        "position_index": 0,
        "corrected_by": "local-owner",
        "expected_geometry_revision": 0,
        "expected_resolution_revision": 0,
        "command_checksum_sha256": "a" * 64,
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


def test_manual_v19_persistence_isolates_concurrent_pending_commands(
    tmp_path: Path,
) -> None:
    preview, _ = _preview(tmp_path)
    previewer = ManualBoardCellGeometryPreviewer()
    managed_root = tmp_path / "managed"

    first = previewer.persist(
        preview=preview,
        managed_data_root=managed_root,
        revision=3,
        namespace_discriminator="a" * 64,
    )
    second = previewer.persist(
        preview=preview,
        managed_data_root=managed_root,
        revision=3,
        namespace_discriminator="b" * 64,
    )

    assert len(first.cells) == len(second.cells) == 15
    assert {cell.checksum_sha256 for cell in first.cells} == {
        cell.checksum_sha256 for cell in second.cells
    }
    assert {cell.relative_path for cell in first.cells}.isdisjoint(
        {cell.relative_path for cell in second.cells}
    )
    with pytest.raises(ManualBoardCellGeometryPreviewError) as invalid:
        previewer.persist(
            preview=preview,
            managed_data_root=managed_root,
            revision=3,
            namespace_discriminator="not-a-checksum",
        )
    assert invalid.value.code == "BOARD_CELL_GEOMETRY_ARTIFACT_NAMESPACE_INVALID"
