from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_activation import (
    BoardCellRecropSnapshotError,
    board_cell_processing_snapshot,
    require_v20_supported_topology,
    validate_board_cell_processing_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    BoardCellTopology,
    derive_board_cell_quads,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    BoardCellGeometrySourceDirectCropper,
    cropper_fingerprint_sha256,
)


def _manual_geometry(topology: BoardCellTopology) -> tuple[np.ndarray, BoardCellGeometryEntry]:
    cell_size = 80
    margin = 40
    height = topology.rows * cell_size + margin * 2
    width = topology.columns * cell_size + margin * 2
    source = np.full((height, width, 3), 24, dtype=np.uint8)
    bounds = (
        (float(margin), float(margin)),
        (float(width - margin), float(margin)),
        (float(width - margin), float(height - margin)),
        (float(margin), float(height - margin)),
    )
    for index, (row, column) in enumerate(
        divmod(index, topology.columns) for index in range(topology.cell_count)
    ):
        source[
            margin + row * cell_size : margin + (row + 1) * cell_size,
            margin + column * cell_size : margin + (column + 1) * cell_size,
        ] = (20 + index * 3, 60 + index * 2, 90 + index)
    return source, BoardCellGeometryEntry(
        source_order_index=0,
        image_id="topology-source",
        source_image_checksum_sha256="a" * 64,
        source_image_relative_path="topology.png",
        source_image_width=width,
        source_image_height=height,
        source_group="tests",
        condition_tags=("manual-override",),
        sequence_number=1,
        position_index=0,
        lattice_bounds_quad=bounds,
        cells=derive_board_cell_quads(
            bounds,
            source_image_width=width,
            source_image_height=height,
            topology=topology,
        ),
        evidence=BoardCellGeometryEvidence(
            kind="manual_override",
            estimator_version="manual-test-v1",
            thresholds_version="manual-test-v1",
            locator_version=None,
            homography_version=None,
            candidate_center_count=0,
            reliable_center_count=0,
            inlier_count=0,
            inlier_slots=(),
            inlier_p95_residual_px=None,
            decision_checksum_sha256="b" * 64,
        ),
        topology=topology,
    )


@pytest.mark.parametrize(("rows", "columns"), [(2, 4), (4, 4)])
def test_manual_topology_derives_and_crops_complete_row_major_grid(
    rows: int,
    columns: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topology = BoardCellTopology(
        rows=rows,
        columns=columns,
        rules_version_id=str(uuid4()),
    )
    source, geometry = _manual_geometry(topology)
    original_warp = cv2.warpPerspective
    calls = 0

    def tracked_warp(*args: Any, **kwargs: Any) -> np.ndarray:
        nonlocal calls
        calls += 1
        return cast(np.ndarray, original_warp(*args, **kwargs))

    monkeypatch.setattr(cv2, "warpPerspective", tracked_warp)
    cropper = BoardCellGeometrySourceDirectCropper(
        cell_output_size=48,
        topology=topology,
    )
    result = cropper.crop(source, geometry)

    assert result.status == "cropped"
    assert len(result.cells) == rows * columns
    assert [(cell.row_index, cell.column_index) for cell in result.cells] == [
        (row, column) for row in range(rows) for column in range(columns)
    ]
    assert calls == rows * columns


def test_explicit_legacy_topology_changes_new_fingerprint_but_not_historical_one() -> None:
    historical = cropper_fingerprint_sha256(cell_output_size=64)
    pinned = BoardCellTopology(rows=3, columns=5, rules_version_id=str(uuid4()))

    assert historical == "49146bca0f232a8d8e5e744811577b9f9d01a3cf791d31894775dfb5a677195d"
    assert cropper_fingerprint_sha256(cell_output_size=64, topology=pinned) != historical


def test_v20_snapshot_accepts_pinned_3x5_and_rejects_other_topologies() -> None:
    supported = BoardCellTopology(rows=3, columns=5, rules_version_id=str(uuid4()))
    snapshot = board_cell_processing_snapshot(cell_output_size=64, topology=supported)

    assert validate_board_cell_processing_snapshot(snapshot, cell_output_size=64) == snapshot
    assert require_v20_supported_topology(snapshot) == supported

    unsupported = board_cell_processing_snapshot(
        cell_output_size=64,
        topology=BoardCellTopology(rows=2, columns=4, rules_version_id=str(uuid4())),
    )
    with pytest.raises(BoardCellRecropSnapshotError, match="IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"):
        require_v20_supported_topology(unsupported)
