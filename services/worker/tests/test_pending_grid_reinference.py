from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import cv2
import numpy as np
import pytest
from game_predictor_api.storage.models import ImageReviewItemModel, RecognizedBoardModel
from game_predictor_worker.images.board_cell_geometry_activation import (
    BoardCellRecropSnapshotError,
    board_cell_recrop_snapshot,
    validate_board_cell_recrop_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceDirectCropper,
)
from game_predictor_worker.images.pending_grid_reinference import (
    PendingGridReinferenceHandler,
    _is_current_v19_geometry,
    _pending_projection_matches,
    _PendingBoardSnapshot,
    _V19NeedsReview,
)


def _canonical_board(*, missing_column: bool = False) -> np.ndarray:
    board: np.ndarray = np.full((300, 500, 3), (22, 11, 19), dtype=np.uint8)
    colours = (
        (245, 205, 40),
        (245, 80, 35),
        (70, 120, 245),
        (225, 225, 70),
        (245, 150, 45),
    )
    for row, y in enumerate((50, 150, 250)):
        for column, x in enumerate((50, 150, 250, 350, 450)):
            if missing_column and column == 4:
                continue
            cv2.circle(
                board,
                (x, y),
                24,
                colours[(row + column) % len(colours)],
                -1,
                cv2.LINE_AA,
            )
    return board


def _perspective_source(board: np.ndarray) -> tuple[np.ndarray, list[dict[str, int]]]:
    source: np.ndarray = np.full((700, 900, 3), (8, 8, 12), dtype=np.uint8)
    canonical = np.asarray(((0, 0), (499, 0), (499, 299), (0, 299)), dtype=np.float32)
    target = np.asarray(((108, 82), (788, 116), (746, 610), (142, 574)), dtype=np.float32)
    transform = cv2.getPerspectiveTransform(canonical, target)
    warped = cv2.warpPerspective(board, transform, (900, 700), flags=cv2.INTER_LINEAR)
    support = cv2.warpPerspective(
        np.full(board.shape[:2], 255, dtype=np.uint8),
        transform,
        (900, 700),
        flags=cv2.INTER_NEAREST,
    )
    source[support > 0] = warped[support > 0]
    return source, [{"x": int(x), "y": int(y)} for x, y in target]


def _source_snapshot(
    tmp_path: Path,
    *,
    missing_column: bool = False,
) -> tuple[_PendingBoardSnapshot, Path]:
    rgb, quad = _perspective_source(_canonical_board(missing_column=missing_column))
    relative = "sources/pending-v19.png"
    path = tmp_path / "data" / "sources" / "pending-v19.png"
    path.parent.mkdir(parents=True)
    assert cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    snapshot = _PendingBoardSnapshot(
        review_item_id=uuid4(),
        resolution_revision=0,
        recognized_board_id=uuid4(),
        geometry_revision=0,
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        source_order_index=7,
        sequence_number=64,
        position_index=0,
        board_geometry={
            "attestedRangeEnd": 72,
            "attestedRangeStart": 64,
            "displayAssetKind": "source_context",
            "quad": quad,
            "sequenceSource": "filename",
            "sourceContextBounds": {"height": 600, "width": 800, "x": 50, "y": 40},
        },
        board_relative_path="crops/legacy/source-context.png",
        board_checksum_sha256="b" * 64,
        source_relative_path=relative,
        source_checksum_sha256=checksum,
        source_width=900,
        source_height=700,
    )
    return snapshot, path


def _handler(tmp_path: Path) -> PendingGridReinferenceHandler:
    return PendingGridReinferenceHandler(cast(Any, None), tmp_path)


def test_v2_snapshot_is_pinned_to_the_accepted_estimator_cropper_and_audit() -> None:
    snapshot = board_cell_recrop_snapshot(cell_output_size=64)

    assert snapshot["geometryVersion"] == BOARD_CELL_GEOMETRY_VERSION
    assert snapshot["cropperVersion"] == CROPPER_VERSION
    assert len(str(snapshot["auditReportChecksumSha256"])) == 64
    assert validate_board_cell_recrop_snapshot(snapshot, cell_output_size=64) == snapshot

    changed = {**snapshot, "geometryVersion": "changed"}
    with pytest.raises(BoardCellRecropSnapshotError):
        validate_board_cell_recrop_snapshot(changed, cell_output_size=64)


def test_v2_prepares_exactly_15_source_direct_v19_crops_without_legacy_detector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, source_path = _source_snapshot(tmp_path)
    handler = _handler(tmp_path)
    monkeypatch.setattr(
        handler._detector,
        "detect",
        lambda *_args, **_kwargs: pytest.fail("legacy page detection must remain unused"),
    )
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=64)
    configuration = board_cell_recrop_snapshot(cell_output_size=64)

    prepared = handler._prepare_v19_refresh(
        snapshot,
        cropper=cropper,
        configuration_fingerprint=str(configuration["configurationFingerprintSha256"]),
    )

    assert source_path.read_bytes()
    assert len(prepared.cells) == 15
    assert [(cell.row_index, cell.column_index) for cell in prepared.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert prepared.geometry["geometryVersion"] == BOARD_CELL_GEOMETRY_VERSION
    assert prepared.geometry["cropperVersion"] == CROPPER_VERSION
    assert prepared.geometry["sequenceNumber"] == 64
    assert prepared.geometry["sequenceSource"] == "filename"
    assert prepared.geometry["source"] == "automatic"
    for cell in prepared.cells:
        decoded = cv2.imdecode(np.frombuffer(cell.png, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None
        assert decoded.shape[:2] == (64, 64)
        assert hashlib.sha256(cell.png).hexdigest() == cell.checksum_sha256
    assert not (tmp_path / "data" / "image-review-board-cell-geometry-v19").exists()


def test_v2_estimator_failure_remains_pending_for_manual_geometry_without_artifacts(
    tmp_path: Path,
) -> None:
    snapshot, _source_path = _source_snapshot(tmp_path, missing_column=True)
    handler = _handler(tmp_path)
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=64)
    configuration = board_cell_recrop_snapshot(cell_output_size=64)

    with pytest.raises(_V19NeedsReview):
        handler._prepare_v19_refresh(
            snapshot,
            cropper=cropper,
            configuration_fingerprint=str(configuration["configurationFingerprintSha256"]),
        )

    assert not (tmp_path / "data" / "image-review-board-cell-geometry-v19").exists()


@pytest.mark.parametrize("status", ["accepted", "corrected", "rejected"])
def test_v2_conditional_write_rejects_every_resolved_status(status: str) -> None:
    snapshot = _PendingBoardSnapshot(
        review_item_id=uuid4(),
        resolution_revision=3,
        recognized_board_id=uuid4(),
        geometry_revision=2,
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        source_order_index=0,
        sequence_number=1,
        position_index=0,
        board_geometry={"quad": []},
        board_relative_path="board.png",
        board_checksum_sha256="b" * 64,
        source_relative_path="source.jpg",
        source_checksum_sha256="a" * 64,
        source_width=100,
        source_height=100,
    )
    item = ImageReviewItemModel(
        id=snapshot.review_item_id,
        recognized_board_id=snapshot.recognized_board_id,
        status=status,
        snapshot={},
        resolution_revision=snapshot.resolution_revision,
    )
    board = RecognizedBoardModel(
        id=snapshot.recognized_board_id,
        source_image_id=snapshot.source_image_id,
        position_index=snapshot.position_index,
        sequence_number=snapshot.sequence_number,
        geometry_revision=snapshot.geometry_revision,
        board_geometry=snapshot.board_geometry,
        board_relative_path=snapshot.board_relative_path,
        board_checksum_sha256=snapshot.board_checksum_sha256,
    )

    assert not _pending_projection_matches(snapshot, item=item, board=board)


def test_v2_conditional_write_requires_unchanged_resolution_and_geometry_revisions() -> None:
    snapshot = _PendingBoardSnapshot(
        review_item_id=uuid4(),
        resolution_revision=3,
        recognized_board_id=uuid4(),
        geometry_revision=2,
        source_image_id=uuid4(),
        import_job_id=uuid4(),
        source_order_index=0,
        sequence_number=1,
        position_index=0,
        board_geometry={"quad": []},
        board_relative_path="board.png",
        board_checksum_sha256="b" * 64,
        source_relative_path="source.jpg",
        source_checksum_sha256="a" * 64,
        source_width=100,
        source_height=100,
    )
    item = ImageReviewItemModel(
        id=snapshot.review_item_id,
        recognized_board_id=snapshot.recognized_board_id,
        status="pending",
        snapshot={},
        resolution_revision=snapshot.resolution_revision,
    )
    board = RecognizedBoardModel(
        id=snapshot.recognized_board_id,
        source_image_id=snapshot.source_image_id,
        position_index=snapshot.position_index,
        sequence_number=snapshot.sequence_number,
        geometry_revision=snapshot.geometry_revision,
        board_geometry=snapshot.board_geometry,
        board_relative_path=snapshot.board_relative_path,
        board_checksum_sha256=snapshot.board_checksum_sha256,
    )

    assert _pending_projection_matches(snapshot, item=item, board=board)
    item.resolution_revision += 1
    assert not _pending_projection_matches(snapshot, item=item, board=board)
    item.resolution_revision -= 1
    board.geometry_revision += 1
    assert not _pending_projection_matches(snapshot, item=item, board=board)


def test_v2_does_not_rewrite_an_existing_matching_v19_revision() -> None:
    geometry = {
        "cropperFingerprintSha256": "historical-output-size-fingerprint",
        "cropperVersion": CROPPER_VERSION,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "source": "manual_override",
    }

    assert _is_current_v19_geometry(geometry)
