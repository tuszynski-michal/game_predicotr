"""TASK-1045 (D-562): canonical frames rebuilt from an attested crop."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.canonical_source import (
    CanonicalSourceCrop,
    CanonicalSourceFrame,
    CanonicalSourceLoadError,
    require_inside_valid_box,
    rgb_pixel_checksum_sha256,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    VirtualCell,
    derive_virtual_cells,
)
from game_predictor_api.domain.source_crop import (
    PixelBox,
    ProtectedBox,
    SourceCropAttestation,
    compose_canvas,
    cropped_original_relative_paths,
    encode_attestation,
    oriented_to_raw_box,
)
from game_predictor_worker.images.normalization import (
    SOURCE_ORIGINAL_CROPPED,
    CanonicalSourceLoader,
    managed_original_is_cropped,
)
from game_predictor_worker.images.production_workflow import _refuse_cropped_original
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    VirtualCellExtractionError,
    VirtualCellRender,
    VirtualCellRenderer,
    render_persisted_virtual_cell_rgb,
)
from numpy.typing import NDArray
from PIL import Image
from test_virtual_cell_extraction import RULES_VERSION_ID, _frame_and_geometries

_TOOL = "libjpeg-turbo version 3.2.0 (build 20260630)"


def _jpeg(raw: NDArray[np.uint8], orientation: int | None) -> bytes:
    """4:4:4 quality 100: equal 8x8 input blocks give equal decoded blocks."""

    buffer = io.BytesIO()
    image = Image.fromarray(raw)
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    image.save(buffer, format="JPEG", quality=100, subsampling=0, exif=exif.tobytes())
    return buffer.getvalue()


def _decode(content: bytes) -> NDArray[np.uint8]:
    from PIL import ImageOps

    with Image.open(io.BytesIO(content)) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)


def _write_managed(
    tmp_path: Path, orientation: int | None
) -> tuple[Path, str, NDArray[np.uint8], SourceCropAttestation]:
    """Original (removed later) plus a block-aligned crop and its attestation."""

    rng = np.random.default_rng(5)
    raw = rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    original = _jpeg(raw, orientation)
    checksum = hashlib.sha256(original).hexdigest()
    oriented = _decode(original)
    height, width = oriented.shape[:2]
    crop_box = PixelBox(16, 24, 64 + 16, 24 + 40) if orientation != 6 else PixelBox(24, 16, 64, 96)
    raw_box = oriented_to_raw_box(
        crop_box, orientation=orientation, oriented_width=width, oriented_height=height
    )
    crop = _jpeg(raw[raw_box.top : raw_box.bottom, raw_box.left : raw_box.right], orientation)
    crop_rgb = _decode(crop)
    region = oriented[crop_box.top : crop_box.bottom, crop_box.left : crop_box.right]
    assert np.array_equal(crop_rgb, region)
    canvas = compose_canvas(crop_rgb, crop_box=crop_box, width=width, height=height)
    attestation = SourceCropAttestation(
        original_checksum_sha256=checksum,
        original_size_bytes=len(original) + len(crop),
        original_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(oriented),
        original_width=width,
        original_height=height,
        original_exif_orientation=orientation,
        crop_checksum_sha256=hashlib.sha256(crop).hexdigest(),
        crop_size_bytes=len(crop),
        crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(crop_rgb),
        canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
        crop_box=crop_box,
        raw_crop_box=raw_box,
        protected_box=ProtectedBox(
            crop_box.left + 12.0, crop_box.top + 12.0, crop_box.right - 12.0, crop_box.bottom - 12.0
        ),
        margin_px=0,
        imcu_width=8,
        imcu_height=8,
        edge_mismatch_pixels=0,
        tool_version=_TOOL,
    )
    data = tmp_path / "data"
    crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
    for relative, content in (
        (crop_relative, crop),
        (attestation_relative, encode_attestation(attestation)),
    ):
        target = data.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    original_path = data / "originals" / checksum[:2] / f"{checksum}.jpg"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(original)
    return original_path, checksum, oriented, attestation


@pytest.mark.parametrize("orientation", [None, 6])
def test_original_wins_and_a_removed_original_is_served_from_its_crop(
    tmp_path: Path, orientation: int | None
) -> None:
    path, checksum, oriented, attestation = _write_managed(tmp_path, orientation)
    loader = CanonicalSourceLoader(allow_crop=True)

    full = loader.load(path, expected_source_checksum_sha256=checksum)
    assert full.crop is None
    path.unlink()
    loader.clear()
    frame = loader.load(path, expected_source_checksum_sha256=checksum)

    assert frame.crop is not None
    assert frame.source == full.source
    assert (frame.raw_width, frame.raw_height) == (full.raw_width, full.raw_height)
    box = attestation.crop_box
    assert np.array_equal(
        frame.rgb[box.top : box.bottom, box.left : box.right],
        oriented[box.top : box.bottom, box.left : box.right],
    )
    assert int(frame.rgb.sum()) == int(frame.rgb[box.top : box.bottom, box.left : box.right].sum())
    assert frame.pixel_checksum_sha256 == attestation.canvas_pixel_checksum_sha256
    assert managed_original_is_cropped(path)


def test_whole_frame_consumers_refuse_a_crop_by_default(tmp_path: Path) -> None:
    path, checksum, _oriented, _attestation = _write_managed(tmp_path, None)
    path.unlink()

    with pytest.raises(CanonicalSourceLoadError) as error:
        CanonicalSourceLoader().load(path, expected_source_checksum_sha256=checksum)
    assert error.value.code == SOURCE_ORIGINAL_CROPPED
    with pytest.raises(Exception) as pipeline_error:
        _refuse_cropped_original(path)
    assert getattr(pipeline_error.value, "code", None) == SOURCE_ORIGINAL_CROPPED


def test_a_missing_original_without_crop_stays_not_found(tmp_path: Path) -> None:
    path, checksum, _oriented, _attestation = _write_managed(tmp_path, None)
    path.unlink()
    for sibling in (path.parents[2] / "originals-cropped").rglob("*"):
        if sibling.is_file():
            sibling.unlink()

    assert not managed_original_is_cropped(path)
    with pytest.raises(CanonicalSourceLoadError) as error:
        CanonicalSourceLoader(allow_crop=True).load(path, expected_source_checksum_sha256=checksum)
    assert error.value.code == "IMAGE_CANONICAL_SOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("crop", "SOURCE_CROP_CHECKSUM_MISMATCH"),
        ("attestation", "SOURCE_CROP_ATTESTATION_INVALID"),
    ],
)
def test_tampered_crop_files_fail_closed(tmp_path: Path, target: str, expected: str) -> None:
    path, checksum, _oriented, _attestation = _write_managed(tmp_path, None)
    path.unlink()
    crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
    data = path.parents[2]
    if target == "crop":
        crop_path = data.joinpath(*crop_relative.parts)
        crop_path.write_bytes(crop_path.read_bytes() + b"\0")
    else:
        attestation_path = data.joinpath(*attestation_relative.parts)
        document = json.loads(attestation_path.read_bytes())
        document["marginPx"] = 1
        attestation_path.write_bytes(json.dumps(document).encode())

    with pytest.raises(CanonicalSourceLoadError) as error:
        CanonicalSourceLoader(allow_crop=True).load(path, expected_source_checksum_sha256=checksum)
    assert error.value.code == expected


def _crop_frame(frame: CanonicalSourceFrame, box: PixelBox) -> CanonicalSourceFrame:
    width, height = frame.source.width, frame.source.height
    region = np.ascontiguousarray(frame.rgb[box.top : box.bottom, box.left : box.right])
    canvas = compose_canvas(region, crop_box=box, width=width, height=height)
    attestation = SourceCropAttestation(
        original_checksum_sha256=frame.source.source_checksum_sha256,
        original_size_bytes=2_000_000,
        original_normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        original_width=width,
        original_height=height,
        original_exif_orientation=None,
        crop_checksum_sha256="c" * 64,
        crop_size_bytes=1_000_000,
        crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(region),
        canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
        crop_box=box,
        raw_crop_box=box,
        protected_box=ProtectedBox(
            float(box.left), float(box.top), float(box.right), float(box.bottom)
        ),
        margin_px=0,
        imcu_width=8,
        imcu_height=8,
        edge_mismatch_pixels=0,
        tool_version=_TOOL,
    )
    return CanonicalSourceFrame(
        source=frame.source,
        raw_width=frame.raw_width,
        raw_height=frame.raw_height,
        source_mode=frame.source_mode,
        orientation_action=frame.orientation_action,
        rgb=canvas,
        crop=CanonicalSourceCrop(attestation),
    )


def test_cells_rendered_from_a_crop_equal_the_original_renders() -> None:
    frame, _v19, cells = _frame_and_geometries()
    cropped = _crop_frame(frame, PixelBox(56, 32, 840, 664))

    original = VirtualCellRenderer().render(frame, cells)
    from_crop = VirtualCellRenderer().render(cropped, cells)

    for left, right in zip(original, from_crop, strict=True):
        assert np.array_equal(left.rgb, right.rgb)
        assert left.render_spec_checksum_sha256 == right.render_spec_checksum_sha256
        assert left.rendered_pixel_checksum_sha256 == right.rendered_pixel_checksum_sha256


def test_a_cell_outside_the_crop_is_not_rendered_from_fill() -> None:
    frame, _v19, cells = _frame_and_geometries()
    cropped = _crop_frame(frame, PixelBox(200, 32, 840, 664))

    with pytest.raises(VirtualCellExtractionError) as error:
        VirtualCellRenderer().render(cropped, cells)
    assert error.value.code == "SOURCE_REGION_UNAVAILABLE"


def test_valid_box_keeps_clear_of_the_edge_ring_but_not_of_image_borders() -> None:
    frame, _v19, _cells = _frame_and_geometries()
    inner = _crop_frame(frame, PixelBox(56, 32, 840, 664))
    bordered = _crop_frame(frame, PixelBox(0, 0, 900, 664))

    require_inside_valid_box(frame, [(-5.0, -5.0)])
    require_inside_valid_box(inner, [(58.0, 34.0), (838.0, 662.0)])
    for point in ((57.5, 100.0), (100.0, 663.0)):
        with pytest.raises(CanonicalSourceLoadError):
            require_inside_valid_box(inner, [point])
    require_inside_valid_box(bordered, [(-3.0, -3.0), (903.0, 100.0)])
    with pytest.raises(CanonicalSourceLoadError):
        require_inside_valid_box(bordered, [(100.0, 663.5)])


def test_a_crop_frame_must_carry_the_attested_original_identity() -> None:
    frame, _v19, _cells = _frame_and_geometries()
    cropped = _crop_frame(frame, PixelBox(56, 32, 840, 664))
    assert cropped.crop is not None

    with pytest.raises(CanonicalSourceLoadError) as error:
        CanonicalSourceFrame(
            source=frame.source,
            raw_width=frame.raw_width,
            raw_height=frame.raw_height,
            source_mode=frame.source_mode,
            orientation_action=frame.orientation_action,
            rgb=frame.rgb,
            crop=cropped.crop,
        )
    assert error.value.code == "IMAGE_CANONICAL_SOURCE_PIXEL_CHECKSUM_MISMATCH"


def _persisted(frame: CanonicalSourceFrame, render: VirtualCellRender) -> NDArray[np.uint8]:
    return render_persisted_virtual_cell_rgb(
        frame,
        render_spec=render.render_spec,
        expected_render_spec_checksum_sha256=render.render_spec_checksum_sha256,
        expected_rendered_pixel_checksum_sha256=render.rendered_pixel_checksum_sha256,
        expected_cell_index=render.cell_index,
        expected_row_index=render.row_index,
        expected_column_index=render.column_index,
        expected_logical_cell_key_sha256=render.logical_cell_key_sha256,
        expected_logical_cell_key_v2_sha256=render.logical_cell_key_v2_sha256,
        expected_extractor_version=render.extractor_version,
    )


def test_a_persisted_cell_is_recreated_from_a_crop_only_inside_it() -> None:
    frame, _v19, cells = _frame_and_geometries()
    renders = VirtualCellRenderer().render(frame, cells)
    inside = _crop_frame(frame, PixelBox(56, 32, 840, 664))

    for render in renders:
        assert np.array_equal(_persisted(inside, render), render.rgb)

    with pytest.raises(VirtualCellExtractionError) as region_error:
        _persisted(_crop_frame(frame, PixelBox(400, 32, 840, 664)), renders[0])
    assert region_error.value.code == "SOURCE_REGION_UNAVAILABLE"


def test_a_fill_identical_to_the_lost_pixels_still_cannot_render_a_cell() -> None:
    frame, _v19, _cells = _frame_and_geometries()
    # The original is black left of x=400, exactly like the crop's fill, so a
    # warp from the canvas would reproduce cell 0's checksum: refuse first.
    rgb = frame.rgb.copy()
    rgb[:, :400] = 0
    source = replace(frame.source, normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb))
    dark = CanonicalSourceFrame(
        source=source,
        raw_width=frame.raw_width,
        raw_height=frame.raw_height,
        source_mode=frame.source_mode,
        orientation_action=frame.orientation_action,
        rgb=rgb,
    )
    renders = VirtualCellRenderer().render(dark, _cells_for(dark))
    cut = _crop_frame(dark, PixelBox(400, 32, 840, 664))

    with pytest.raises(VirtualCellExtractionError) as error:
        _persisted(cut, renders[0])
    assert error.value.code == "SOURCE_REGION_UNAVAILABLE"


def _cells_for(frame: CanonicalSourceFrame) -> tuple[VirtualCell, ...]:
    bounds = ((108.0, 82.0), (788.0, 116.0), (746.0, 610.0), (142.0, 574.0))
    geometry = VirtualBoardGeometry(
        source=frame.source,
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
    return derive_virtual_cells(
        geometry=geometry,
        configuration=DirectCellRenderConfiguration(
            extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version="spatial-symbol-cnn-rgb-input-v1",
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=64,
            output_height=64,
            padding_fraction=0.1,
        ),
    )


@pytest.mark.parametrize(
    ("orientation", "box"),
    [(1, PixelBox(56, 32, 840, 664)), (6, PixelBox(52, 32, 844, 664))],
)
def test_decoded_crop_renders_the_same_cells_as_its_original(
    tmp_path: Path, orientation: int, box: PixelBox
) -> None:
    oriented, _v19, _cells = _frame_and_geometries()
    raw = oriented.rgb if orientation == 1 else np.ascontiguousarray(np.rot90(oriented.rgb, k=1))
    original = _jpeg(raw, orientation)
    checksum = hashlib.sha256(original).hexdigest()
    path = tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    loader = CanonicalSourceLoader(allow_crop=True)
    full = loader.load(path, expected_source_checksum_sha256=checksum)
    width, height = full.source.width, full.source.height
    raw_box = oriented_to_raw_box(
        box, orientation=orientation, oriented_width=width, oriented_height=height
    )
    assert raw_box.left % 8 == 0 and raw_box.top % 8 == 0
    crop = _jpeg(
        np.ascontiguousarray(raw[raw_box.top : raw_box.bottom, raw_box.left : raw_box.right]),
        orientation,
    )
    crop_rgb = _decode(crop)
    canvas = compose_canvas(crop_rgb, crop_box=box, width=width, height=height)
    attestation = SourceCropAttestation(
        original_checksum_sha256=checksum,
        original_size_bytes=len(original),
        original_normalized_pixel_checksum_sha256=full.source.normalized_pixel_checksum_sha256,
        original_width=width,
        original_height=height,
        original_exif_orientation=orientation,
        crop_checksum_sha256=hashlib.sha256(crop).hexdigest(),
        crop_size_bytes=len(crop),
        crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(crop_rgb),
        canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
        crop_box=box,
        raw_crop_box=raw_box,
        protected_box=ProtectedBox(108.0, 82.0, 788.0, 610.0),
        margin_px=0,
        imcu_width=8,
        imcu_height=8,
        edge_mismatch_pixels=0,
        tool_version=_TOOL,
    )
    crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
    data = tmp_path / "data"
    data.joinpath(*crop_relative.parts).parent.mkdir(parents=True)
    data.joinpath(*crop_relative.parts).write_bytes(crop)
    data.joinpath(*attestation_relative.parts).write_bytes(encode_attestation(attestation))
    cells = _cells_for(full)
    expected = VirtualCellRenderer().render(full, cells)
    path.unlink()
    loader.clear()

    cropped = loader.load(path, expected_source_checksum_sha256=checksum)
    rendered = VirtualCellRenderer().render(cropped, cells)

    assert cropped.crop is not None
    for left, right in zip(expected, rendered, strict=True):
        assert np.array_equal(left.rgb, right.rgb)
        assert left.render_spec_checksum_sha256 == right.render_spec_checksum_sha256
