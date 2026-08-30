from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    NormalizedSourceImage,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    VirtualCell,
    canonical_json_bytes,
    derive_virtual_cells,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BoardCellGeometryEntry,
    BoardCellGeometryEvidence,
    derive_board_cell_quads,
)
from game_predictor_worker.images.board_cell_geometry_crops import (
    BoardCellGeometrySourceDirectCropper,
)
from game_predictor_worker.images.normalization import (
    CANONICAL_SOURCE_LOADER_VERSION,
    CanonicalSourceFrame,
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    CellExtractionVariant,
    VirtualCellExtractionError,
    VirtualCellRenderer,
    compare_cell_extraction_variants,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps

ORIENTATION_TAG = 274
COLORS = {
    "A": (250, 0, 0),
    "B": (0, 250, 0),
    "C": (0, 0, 250),
    "D": (250, 250, 0),
    "E": (250, 0, 250),
    "F": (0, 250, 250),
}
EXPECTED_LABELS = {
    1: (("A", "B", "C"), ("D", "E", "F")),
    2: (("C", "B", "A"), ("F", "E", "D")),
    3: (("F", "E", "D"), ("C", "B", "A")),
    4: (("D", "E", "F"), ("A", "B", "C")),
    5: (("A", "D"), ("B", "E"), ("C", "F")),
    6: (("D", "A"), ("E", "B"), ("F", "C")),
    7: (("F", "C"), ("E", "B"), ("D", "A")),
    8: (("C", "F"), ("B", "E"), ("A", "D")),
}
RULES_VERSION_ID = UUID("4e7b42a8-cac8-4e6f-b2c6-a0db53f0dd04")


def _write_pattern_jpeg(path: Path, orientation: int) -> str:
    image = Image.new("RGB", (30, 20))
    labels = (("A", "B", "C"), ("D", "E", "F"))
    for row, row_labels in enumerate(labels):
        for column, label in enumerate(row_labels):
            image.paste(
                COLORS[label],
                (column * 10, row * 10, (column + 1) * 10, (row + 1) * 10),
            )
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = orientation
    image.save(path, format="JPEG", quality=100, subsampling=0, exif=exif)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nearest_label(pixel: NDArray[np.uint8]) -> str:
    return min(
        COLORS,
        key=lambda label: sum(
            (int(component) - expected) ** 2
            for component, expected in zip(pixel, COLORS[label], strict=True)
        ),
    )


def _sample_labels(rgb: NDArray[np.uint8]) -> tuple[tuple[str, ...], ...]:
    rows = rgb.shape[0] // 10
    columns = rgb.shape[1] // 10
    return tuple(
        tuple(_nearest_label(rgb[row * 10 + 5, column * 10 + 5]) for column in range(columns))
        for row in range(rows)
    )


def test_canonical_source_loader_applies_each_exif_orientation_once(
    tmp_path: Path,
) -> None:
    expected_files: list[Path] = []
    for orientation in range(1, 9):
        source_path = tmp_path / f"orientation-{orientation}.jpg"
        expected_files.append(source_path)
        checksum = _write_pattern_jpeg(source_path, orientation)

        frame = CanonicalSourceLoader().load(
            source_path,
            expected_source_checksum_sha256=checksum,
        )

        expected = EXPECTED_LABELS[orientation]
        assert frame.source.exif_orientation == orientation
        assert frame.source.normalization_adapter_version == CANONICAL_SOURCE_LOADER_VERSION
        assert (frame.source.width, frame.source.height) == (
            len(expected[0]) * 10,
            len(expected) * 10,
        )
        assert _sample_labels(frame.rgb) == expected
        assert not frame.rgb.flags.writeable
    assert sorted(tmp_path.iterdir()) == expected_files


def test_canonical_source_loader_decodes_and_transposes_once_per_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.jpg"
    checksum = _write_pattern_jpeg(source_path, 6)
    original_open = Image.open
    original_transpose = ImageOps.exif_transpose
    open_count = 0
    transpose_count = 0

    def tracked_open(*args: object, **kwargs: object) -> Image.Image:
        nonlocal open_count
        open_count += 1
        return original_open(*args, **kwargs)

    def tracked_transpose(image: Image.Image) -> Image.Image:
        nonlocal transpose_count
        transpose_count += 1
        return original_transpose(image)

    monkeypatch.setattr(Image, "open", tracked_open)
    monkeypatch.setattr(ImageOps, "exif_transpose", tracked_transpose)
    loader = CanonicalSourceLoader()

    first = loader.load(source_path, expected_source_checksum_sha256=checksum)
    second = loader.load(source_path, expected_source_checksum_sha256=checksum)

    assert first is second
    assert open_count == 1
    assert transpose_count == 1
    assert first.source.normalized_pixel_checksum_sha256 == rgb_pixel_checksum_sha256(first.rgb)


def _canonical_board() -> NDArray[np.uint8]:
    board: NDArray[np.uint8] = np.zeros((300, 500, 3), dtype=np.uint8)
    for row in range(3):
        for column in range(5):
            y, x = np.indices((100, 100))
            base = row * 5 + column
            board[
                row * 100 : (row + 1) * 100,
                column * 100 : (column + 1) * 100,
            ] = np.stack(
                (
                    (x * 3 + base * 17) % 256,
                    (y * 5 + base * 29) % 256,
                    ((x + y) * 7 + base * 11) % 256,
                ),
                axis=2,
            ).astype(np.uint8)
    return board


def _frame_and_geometries() -> tuple[
    CanonicalSourceFrame,
    BoardCellGeometryEntry,
    tuple[VirtualCell, ...],
]:
    board = _canonical_board()
    source: NDArray[np.uint8] = np.full((700, 900, 3), 8, dtype=np.uint8)
    canonical = np.asarray(((0, 0), (500, 0), (500, 300), (0, 300)), dtype=np.float32)
    bounds = (
        (108.0, 82.0),
        (788.0, 116.0),
        (746.0, 610.0),
        (142.0, 574.0),
    )
    transform = cv2.getPerspectiveTransform(canonical, np.asarray(bounds, dtype=np.float32))
    warped = cv2.warpPerspective(board, transform, (900, 700), flags=cv2.INTER_LINEAR)
    support = cv2.warpPerspective(
        np.full(board.shape[:2], 255, dtype=np.uint8),
        transform,
        (900, 700),
        flags=cv2.INTER_NEAREST,
    )
    source[support > 0] = warped[support > 0]
    source_checksum = "a" * 64
    normalized = NormalizedSourceImage(
        source_checksum_sha256=source_checksum,
        normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(source),
        width=900,
        height=700,
        exif_orientation=None,
        normalization_adapter_version=CANONICAL_SOURCE_LOADER_VERSION,
    )
    frame = CanonicalSourceFrame(
        source=normalized,
        raw_width=900,
        raw_height=700,
        source_mode="RGB",
        orientation_action="none",
        rgb=source,
    )
    v19 = BoardCellGeometryEntry(
        source_order_index=0,
        image_id="synthetic-source",
        source_image_checksum_sha256=source_checksum,
        source_image_relative_path="synthetic.jpg",
        source_image_width=900,
        source_image_height=700,
        source_group="synthetic",
        condition_tags=("perspective",),
        sequence_number=1,
        position_index=0,
        lattice_bounds_quad=bounds,
        cells=derive_board_cell_quads(bounds, source_image_width=900, source_image_height=700),
        evidence=BoardCellGeometryEvidence(
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
        ),
    )
    virtual_geometry = VirtualBoardGeometry(
        source=normalized,
        source_occurrence=SourceOccurrence(
            import_job_id=UUID("20000000-0000-0000-0000-000000000001"),
            file_execution_key="e" * 64,
        ),
        slot=ActiveBoardSlot(range_start=1, range_end=1, position_index=0, sequence_number=1),
        topology=BoardTopology(rows=3, columns=5),
        topology_rules_version_id=RULES_VERSION_ID,
        geometry_revision=0,
        geometry_version="source-quad-perspective-grid-v1",
        engine_kind=GeometryEngineKind.LEGACY_V20,
        symbol_grid_quad=SourceQuad(
            corners=cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(SourcePoint(x=x, y=y) for x, y in bounds),
            )
        ),
    )
    cells = derive_virtual_cells(
        geometry=virtual_geometry,
        configuration=DirectCellRenderConfiguration(
            extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version="spatial-symbol-cnn-rgb-input-v1",
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=64,
            output_height=64,
            padding_fraction=0.1,
        ),
    )
    return frame, v19, cells


def test_virtual_renderer_has_exact_v19_pixel_parity_and_one_warp_per_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, v19_geometry, cells = _frame_and_geometries()
    legacy = BoardCellGeometrySourceDirectCropper(cell_output_size=64).crop(
        frame.rgb,
        v19_geometry,
    )
    original_warp = cv2.warpPerspective
    warp_count = 0

    def tracked_warp(*args: Any, **kwargs: Any) -> np.ndarray[Any, Any]:
        nonlocal warp_count
        warp_count += 1
        return cast(np.ndarray[Any, Any], original_warp(*args, **kwargs))

    monkeypatch.setattr(cv2, "warpPerspective", tracked_warp)
    rendered = VirtualCellRenderer().render(frame, cells)

    assert legacy.status == "cropped"
    assert len(rendered) == len(legacy.cells) == 15
    assert warp_count == 15
    for virtual, historical in zip(rendered, legacy.cells, strict=True):
        assert np.array_equal(virtual.rgb, historical.rgb)
        assert virtual.rendered_pixel_checksum_sha256 == rgb_pixel_checksum_sha256(historical.rgb)
        assert (
            virtual.render_spec_checksum_sha256
            == hashlib.sha256(canonical_json_bytes(virtual.render_spec)).hexdigest()
        )
        assert virtual.render_spec["logicalCellKeySha256"] == virtual.logical_cell_key_sha256
        assert virtual.render_spec["logicalCellKeyV1Sha256"] == virtual.logical_cell_key_sha256
        assert virtual.render_spec["logicalCellKeyV2Sha256"] == (virtual.logical_cell_key_v2_sha256)
        assert virtual.render_spec["sourceOccurrenceIdSha256"] == (
            cells[virtual.cell_index].geometry.source_occurrence.identity_sha256
        )
        assert not virtual.rgb.flags.writeable


def test_a_b_c_comparison_is_in_memory_and_pins_direct_variant() -> None:
    frame, _, cells = _frame_and_geometries()
    selected = cells[7]

    comparisons = compare_cell_extraction_variants(frame, selected)
    direct = VirtualCellRenderer().render(frame, (selected,))[0]

    assert tuple(item.variant for item in comparisons) == (
        CellExtractionVariant.NATIVE_BOUNDING_BOX,
        CellExtractionVariant.DIRECT_PERSPECTIVE_CELL,
        CellExtractionVariant.RECTIFIED_BOARD,
    )
    assert all(item.rgb.shape == (64, 64, 3) for item in comparisons)
    assert np.array_equal(comparisons[1].rgb, direct.rgb)
    assert comparisons[1].rendered_pixel_checksum_sha256 == (direct.rendered_pixel_checksum_sha256)
    assert comparisons[0].rendered_pixel_checksum_sha256 != (
        comparisons[1].rendered_pixel_checksum_sha256
    )


def test_virtual_renderer_rejects_drift_before_first_warp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, _, cells = _frame_and_geometries()
    foreign_source = NormalizedSourceImage(
        source_checksum_sha256="b" * 64,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        width=frame.source.width,
        height=frame.source.height,
        exif_orientation=None,
        normalization_adapter_version=CANONICAL_SOURCE_LOADER_VERSION,
    )
    foreign = derive_virtual_cells(
        geometry=VirtualBoardGeometry(
            source=foreign_source,
            source_occurrence=cells[0].geometry.source_occurrence,
            slot=cells[0].geometry.slot,
            topology=cells[0].geometry.topology,
            topology_rules_version_id=cells[0].geometry.topology_rules_version_id,
            geometry_revision=cells[0].geometry.geometry_revision,
            geometry_version=cells[0].geometry.geometry_version,
            engine_kind=cells[0].geometry.engine_kind,
            symbol_grid_quad=cells[0].geometry.symbol_grid_quad,
        ),
        configuration=cells[0].configuration,
    )

    def unexpected_warp(*_args: object, **_kwargs: object) -> np.ndarray[Any, Any]:
        raise AssertionError("source drift must fail before rasterization")

    monkeypatch.setattr(cv2, "warpPerspective", unexpected_warp)
    with pytest.raises(VirtualCellExtractionError) as raised:
        VirtualCellRenderer().render(frame, foreign)

    assert raised.value.code == "IMAGE_VIRTUAL_CELL_SOURCE_MISMATCH"
