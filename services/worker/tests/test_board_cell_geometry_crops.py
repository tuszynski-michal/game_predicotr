from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_contract import (
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    BoardCellQuad,
    derive_board_cell_quads,
    load_real_board_cell_geometry_corpus,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    BORDER_POLICY_VERSION,
    CROPPER_VERSION,
    FIXED_PADDING_CANONICAL_PX,
    FIXED_PADDING_FRACTION,
    INTERPOLATION_VERSION,
    PADDING_VERSION,
    BoardCellGeometryCropError,
    BoardCellGeometrySourceDirectCropper,
    cropper_fingerprint_sha256,
)
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = ROOT / "ai_docs" / "quality" / "board-cell-geometry-v19-real-corpus.json"


def _canonical_board() -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    board = np.zeros((300, 500, 3), dtype=np.uint8)
    colors: list[tuple[int, int, int]] = []
    for row in range(3):
        for column in range(5):
            color = (
                30 + row * 70,
                25 + column * 40,
                40 + (row * 5 + column) * 10,
            )
            colors.append(color)
            board[row * 100 : (row + 1) * 100, column * 100 : (column + 1) * 100] = color
    return board, colors


def _source_and_geometry() -> tuple[
    np.ndarray,
    BoardCellGeometryEntry,
    list[tuple[int, int, int]],
]:
    board, colors = _canonical_board()
    source = np.full((700, 900, 3), (8, 8, 12), dtype=np.uint8)
    canonical = np.asarray(((0, 0), (500, 0), (500, 300), (0, 300)), dtype=np.float32)
    bounds = (
        (108.0, 82.0),
        (788.0, 116.0),
        (746.0, 610.0),
        (142.0, 574.0),
    )
    transform = cv2.getPerspectiveTransform(canonical, np.asarray(bounds, dtype=np.float32))
    warped = cv2.warpPerspective(
        board,
        transform,
        (source.shape[1], source.shape[0]),
        flags=cv2.INTER_LINEAR,
    )
    support = cv2.warpPerspective(
        np.full(board.shape[:2], 255, dtype=np.uint8),
        transform,
        (source.shape[1], source.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    source[support > 0] = warped[support > 0]
    cells = derive_board_cell_quads(
        bounds,
        source_image_width=source.shape[1],
        source_image_height=source.shape[0],
    )
    evidence = BoardCellGeometryEvidence(
        kind="human_reviewed",
        estimator_version="test-owner-review-v1",
        thresholds_version="test-owner-review-thresholds-v1",
        locator_version=None,
        homography_version=None,
        candidate_center_count=0,
        reliable_center_count=0,
        inlier_count=0,
        inlier_slots=(),
        inlier_p95_residual_px=None,
        decision_checksum_sha256="d" * 64,
    )
    return (
        source,
        BoardCellGeometryEntry(
            source_order_index=0,
            image_id="synthetic-source",
            source_image_checksum_sha256="a" * 64,
            source_image_relative_path="synthetic.jpg",
            source_image_width=source.shape[1],
            source_image_height=source.shape[0],
            source_group="synthetic",
            condition_tags=("perspective",),
            sequence_number=1,
            position_index=0,
            lattice_bounds_quad=bounds,
            cells=cells,
            evidence=evidence,
        ),
        colors,
    )


def test_v19_cropper_projects_row_major_cells_from_source_in_one_resampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, geometry, colors = _source_and_geometry()
    before = source.copy()
    original_warp = cv2.warpPerspective
    warp_sizes: list[tuple[int, int]] = []

    def tracked_warp(*args: Any, **kwargs: Any) -> np.ndarray:
        size = args[2]
        assert isinstance(size, tuple)
        warp_sizes.append(size)
        return cast(np.ndarray, original_warp(*args, **kwargs))

    def unexpected_resize(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("v19 must not resize a materialized board or cell")

    monkeypatch.setattr(cv2, "warpPerspective", tracked_warp)
    monkeypatch.setattr(cv2, "resize", unexpected_resize)

    result = BoardCellGeometrySourceDirectCropper(cell_output_size=90).crop(source, geometry)

    assert result.status == "cropped"
    assert result.review_reasons == ()
    assert len(result.cells) == 15
    assert [(cell.row_index, cell.column_index) for cell in result.cells] == [
        (row, column) for row in range(3) for column in range(5)
    ]
    assert warp_sizes == [(90, 90)] * 15
    assert np.array_equal(source, before)
    for cell, expected in zip(result.cells, colors, strict=True):
        assert cell.rgb.shape == (90, 90, 3)
        center = cell.rgb[15:-15, 15:-15].mean(axis=(0, 1))
        assert np.max(np.abs(center - np.asarray(expected))) < 3


def test_v19_cropper_pins_padding_provenance_and_fingerprint() -> None:
    source, geometry, _ = _source_and_geometry()
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=64)

    first = cropper.crop(source, geometry)
    second = cropper.crop(source, geometry)
    payload = first.to_dict()

    assert payload["cropperVersion"] == CROPPER_VERSION
    assert payload["paddingVersion"] == PADDING_VERSION
    assert payload["interpolationVersion"] == INTERPOLATION_VERSION
    assert payload["borderPolicyVersion"] == BORDER_POLICY_VERSION
    assert payload["fixedPaddingCanonicalPx"] == FIXED_PADDING_CANONICAL_PX
    assert payload["fixedPaddingFraction"] == FIXED_PADDING_FRACTION
    assert payload["cellOutputSize"] == 64
    assert cropper.fingerprint_sha256 == cropper_fingerprint_sha256(cell_output_size=64)
    assert cropper.fingerprint_sha256 == (
        "49146bca0f232a8d8e5e744811577b9f9d01a3cf791d31894775dfb5a677195d"
    )
    assert cropper.fingerprint_sha256 != cropper_fingerprint_sha256(cell_output_size=90)
    assert first.to_dict() == second.to_dict()
    assert all(
        np.array_equal(left.rgb, right.rgb)
        for left, right in zip(first.cells, second.cells, strict=True)
    )


def test_v19_cropper_validates_all_cells_before_creating_any_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, geometry, _ = _source_and_geometry()
    last = geometry.cells[-1]
    changed_quad = (
        (last.quad[0][0] + 1.0, last.quad[0][1]),
        *last.quad[1:],
    )
    invalid = replace(
        geometry,
        cells=(
            *geometry.cells[:-1],
            BoardCellQuad(
                row_index=last.row_index,
                column_index=last.column_index,
                quad=changed_quad,
            ),
        ),
    )

    def unexpected_warp(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("invalid complete geometry must fail before rasterization")

    monkeypatch.setattr(cv2, "warpPerspective", unexpected_warp)

    result = BoardCellGeometrySourceDirectCropper(cell_output_size=90).crop(source, invalid)

    assert result.status == "needs_review"
    assert result.cells == ()
    assert result.review_reasons == ("BOARD_CELL_CROP_CELL_DERIVATION_MISMATCH",)


def test_v19_cropper_rejects_unverified_evidence_without_partial_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, geometry, _ = _source_and_geometry()
    invalid = replace(
        geometry,
        evidence=replace(
            geometry.evidence,
            kind="automatic",
            decision_checksum_sha256=None,
        ),
    )

    def unexpected_warp(*_args: object, **_kwargs: object) -> np.ndarray:
        raise AssertionError("unverified geometry must not reach rasterization")

    monkeypatch.setattr(cv2, "warpPerspective", unexpected_warp)

    result = BoardCellGeometrySourceDirectCropper(cell_output_size=90).crop(source, invalid)

    assert result.status == "needs_review"
    assert result.cells == ()
    assert result.review_reasons == ("BOARD_CELL_CROP_EVIDENCE_INVALID",)


def test_v19_cropper_rejects_dimension_drift_and_invalid_rgb() -> None:
    source, geometry, _ = _source_and_geometry()
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=90)

    drifted = cropper.crop(source[:-1], geometry)

    assert drifted.status == "needs_review"
    assert drifted.cells == ()
    assert drifted.review_reasons == ("BOARD_CELL_CROP_IMAGE_DIMENSIONS_MISMATCH",)
    with pytest.raises(BoardCellGeometryCropError) as raised:
        cropper.crop(np.zeros((20, 20), dtype=np.uint8), geometry)
    assert raised.value.code == "BOARD_CELL_CROP_INVALID_IMAGE"


def test_v19_real_geometry_corpus_produces_complete_supported_crops() -> None:
    representative = ROOT / "examples" / "imgs" / "5983122166590934317.jpg"
    if not representative.is_file():
        pytest.skip("The ignored local M5 source corpus is not present in this checkout.")
    manifest = load_real_board_cell_geometry_corpus(ROOT, DESCRIPTOR)
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=90)
    source_root = ROOT / "examples" / "imgs"

    for entry in manifest.entries:
        with Image.open(source_root / entry.source_image_relative_path) as image:
            source = np.asarray(image.convert("RGB"), dtype=np.uint8)
        result = cropper.crop(source, entry)

        assert result.status == "cropped", (entry.sequence_number, result.review_reasons)
        assert len(result.cells) == 15
        assert all(cell.rgb.shape == (90, 90, 3) for cell in result.cells)
        assert [(cell.row_index, cell.column_index) for cell in result.cells] == [
            (row, column) for row in range(3) for column in range(5)
        ]
