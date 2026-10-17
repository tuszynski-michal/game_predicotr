from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from game_predictor_api.domain.source_crop import (
    PixelBox,
    ProtectedBox,
    SourceCropAttestation,
    SourceCropError,
    align_raw_box,
    compose_canvas,
    cropped_original_relative_paths,
    cropped_sibling_paths,
    decode_attestation,
    encode_attestation,
    imcu_from_sampling_factors,
    imcu_size,
    is_crop_beneficial,
    oriented_to_raw_box,
    plan_source_crop,
    protected_box_from_points,
    protected_points_from_geometry,
    raw_dimensions,
    raw_to_oriented_box,
    verify_crop_pixels,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps
from PIL.JpegImagePlugin import JpegImageFile

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def _oriented(raw: NDArray[np.uint8], orientation: int) -> NDArray[np.uint8]:
    image = Image.fromarray(raw)
    image.getexif()[0x0112] = orientation
    return np.asarray(ImageOps.exif_transpose(image))


def test_p1_example_aligns_to_the_420_imcu_grid() -> None:
    plan = plan_source_crop(
        [(93.2, 30.0), (725.0, 428.0)],
        oriented_width=1080,
        oriented_height=589,
        orientation=1,
        imcu=imcu_size(2, 2),
    )

    assert plan.raw_box == PixelBox(32, 0, 784, 480)
    assert plan.oriented_box == PixelBox(32, 0, 784, 480)
    assert plan.oriented_box.contains(PixelBox(43, 0, 775, 478))


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_box_mapping_matches_exif_transpose(orientation: int) -> None:
    rng = np.random.default_rng(orientation)
    raw = rng.integers(0, 256, size=(37, 53, 3), dtype=np.uint8)
    oriented = _oriented(raw, orientation)
    height, width = oriented.shape[:2]
    assert raw_dimensions(width, height, orientation) == (53, 37)
    box = PixelBox(3, 5, min(width, 21), min(height, 17))

    raw_box = oriented_to_raw_box(
        box, orientation=orientation, oriented_width=width, oriented_height=height
    )
    raw_region = raw[raw_box.top : raw_box.bottom, raw_box.left : raw_box.right]
    expected = oriented[box.top : box.bottom, box.left : box.right]

    assert np.array_equal(_oriented(np.ascontiguousarray(raw_region), orientation), expected)
    assert raw_to_oriented_box(raw_box, orientation=orientation, raw_width=53, raw_height=37) == box


def test_orientation_six_plan_with_offset_contains_margin_box() -> None:
    plan = plan_source_crop(
        [(100.0, 220.0), (300.0, 410.0)],
        oriented_width=600,
        oriented_height=800,
        orientation=6,
        imcu=(16, 16),
    )

    assert plan.oriented_box.contains(PixelBox(50, 170, 350, 460))
    assert plan.raw_box.left % 16 == 0 and plan.raw_box.top % 16 == 0
    assert raw_to_oriented_box(plan.raw_box, orientation=6, raw_width=800, raw_height=600) == (
        plan.oriented_box
    )


def test_margin_is_clamped_to_the_image_border() -> None:
    plan = plan_source_crop(
        [(-4.0, 10.0), (1079.5, 588.0)],
        oriented_width=1080,
        oriented_height=589,
        orientation=None,
        imcu=(8, 8),
    )

    assert plan.oriented_box == PixelBox(0, 0, 1080, 589)
    assert plan.protected_box.left == 0.0


@pytest.mark.parametrize("orientation", [2, 4, 5, 7])
def test_mirrored_orientations_are_rejected(orientation: int) -> None:
    with pytest.raises(SourceCropError) as error:
        plan_source_crop(
            [(1.0, 1.0), (5.0, 5.0)],
            oriented_width=10,
            oriented_height=10,
            orientation=orientation,
            imcu=(8, 8),
        )
    assert error.value.code == "SOURCE_CROP_ORIENTATION_UNSUPPORTED"


@pytest.mark.parametrize(
    ("imcu", "expected"),
    [((8, 8), PixelBox(40, 0, 776, 480)), ((16, 8), PixelBox(32, 0, 784, 480))],
)
def test_alignment_for_each_imcu(imcu: tuple[int, int], expected: PixelBox) -> None:
    assert align_raw_box(PixelBox(43, 0, 775, 478), imcu=imcu, raw_width=1080, raw_height=589) == (
        expected
    )


def test_sampling_factors_outside_the_supported_set_are_rejected() -> None:
    with pytest.raises(SourceCropError) as error:
        imcu_size(4, 1)
    assert error.value.code == "SOURCE_CROP_SAMPLING_UNSUPPORTED"


def test_empty_protected_set_is_rejected() -> None:
    with pytest.raises(SourceCropError) as error:
        plan_source_crop([], oriented_width=10, oriented_height=10, orientation=1, imcu=(8, 8))
    assert error.value.code == "SOURCE_CROP_NOTHING_PROTECTED"


def test_crop_must_save_five_percent() -> None:
    assert is_crop_beneficial(original_size_bytes=1000, crop_size_bytes=950)
    assert not is_crop_beneficial(original_size_bytes=1000, crop_size_bytes=951)


def _region_pair() -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    rng = np.random.default_rng(7)
    region = rng.integers(0, 256, size=(100, 120, 3), dtype=np.uint8)
    return region, region.copy()


def test_verification_accepts_mismatches_on_the_edge_ring_only() -> None:
    region, crop = _region_pair()
    crop[0, 5] ^= 1
    crop[99, 7] ^= 1
    crop[50, 0] ^= 1
    crop[50, 119] ^= 1

    verdict = verify_crop_pixels(
        region,
        crop,
        crop_box=PixelBox(32, 16, 152, 116),
        image_width=1080,
        image_height=589,
        protected=ProtectedBox(82.0, 66.0, 102.0, 66.0),
    )

    assert verdict.edge_mismatch_pixels == 4


def test_verification_rejects_an_inner_mismatch() -> None:
    region, crop = _region_pair()
    crop[1, 1] ^= 1

    with pytest.raises(SourceCropError) as error:
        verify_crop_pixels(
            region,
            crop,
            crop_box=PixelBox(32, 16, 152, 116),
            image_width=1080,
            image_height=589,
            protected=ProtectedBox(82.0, 66.0, 102.0, 66.0),
        )
    assert error.value.code == "SOURCE_CROP_VERIFICATION_FAILED"


def test_verification_treats_image_borders_as_exact() -> None:
    region, crop = _region_pair()
    crop[0, 60] ^= 1

    with pytest.raises(SourceCropError):
        verify_crop_pixels(
            region,
            crop,
            crop_box=PixelBox(32, 0, 152, 100),
            image_width=1080,
            image_height=589,
            protected=ProtectedBox(82.0, 30.0, 102.0, 60.0),
        )


def test_verification_rejects_protected_quads_near_the_ring() -> None:
    region, crop = _region_pair()

    with pytest.raises(SourceCropError) as error:
        verify_crop_pixels(
            region,
            crop,
            crop_box=PixelBox(32, 16, 152, 116),
            image_width=1080,
            image_height=589,
            protected=ProtectedBox(36.0, 66.0, 102.0, 66.0),
        )
    assert error.value.code == "SOURCE_CROP_VERIFICATION_FAILED"


def test_canvas_pastes_the_crop_at_its_box() -> None:
    crop = np.full((2, 3, 3), 200, dtype=np.uint8)
    canvas = compose_canvas(crop, crop_box=PixelBox(1, 2, 4, 4), width=5, height=6)

    assert canvas.shape == (6, 5, 3)
    assert int(canvas[2:4, 1:4].min()) == 200
    assert int(canvas.sum()) == 200 * crop.size


def _attestation(**changes: object) -> SourceCropAttestation:
    values: dict[str, object] = {
        "original_checksum_sha256": SHA_A,
        "original_size_bytes": 257_965,
        "original_normalized_pixel_checksum_sha256": SHA_B,
        "original_width": 600,
        "original_height": 800,
        "original_exif_orientation": 6,
        "crop_checksum_sha256": SHA_C,
        "crop_size_bytes": 190_000,
        "crop_normalized_pixel_checksum_sha256": SHA_D,
        "canvas_pixel_checksum_sha256": SHA_E,
        "crop_box": PixelBox(48, 160, 352, 464),
        "raw_crop_box": PixelBox(160, 248, 464, 552),
        "protected_box": ProtectedBox(100.0, 220.0, 300.0, 410.0),
        "margin_px": 50,
        "imcu_width": 16,
        "imcu_height": 8,
        "edge_mismatch_pixels": 3,
        "tool_version": "libjpeg-turbo version 3.2.0 (build 20260630)",
    }
    values.update(changes)
    return SourceCropAttestation(**values)  # type: ignore[arg-type]


def test_attestation_round_trips() -> None:
    attestation = _attestation()

    document = encode_attestation(attestation)

    assert decode_attestation(document, expected_original_checksum_sha256=SHA_A) == attestation
    assert document == encode_attestation(
        decode_attestation(document, expected_original_checksum_sha256=SHA_A)
    )


def test_attestation_rejects_edited_content() -> None:
    parsed = json.loads(encode_attestation(_attestation()))
    parsed["crop"]["box"] = [0, 160, 352, 464]

    with pytest.raises(SourceCropError) as error:
        decode_attestation(json.dumps(parsed).encode(), expected_original_checksum_sha256=SHA_A)
    assert error.value.code == "SOURCE_CROP_ATTESTATION_INVALID"


def test_attestation_rejects_a_different_original() -> None:
    with pytest.raises(SourceCropError):
        decode_attestation(
            encode_attestation(_attestation()), expected_original_checksum_sha256=SHA_B
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_crop_box": PixelBox(160, 248, 464, 560)},
        {"crop_size_bytes": 300_000},
        {"protected_box": ProtectedBox(10.0, 220.0, 300.0, 410.0)},
        {"imcu_width": 32},
    ],
)
def test_attestation_rejects_inconsistent_fields(changes: dict[str, object]) -> None:
    with pytest.raises(SourceCropError):
        _attestation(**changes)


def test_cropped_paths_follow_the_content_address() -> None:
    crop, attestation = cropped_original_relative_paths(SHA_A)
    assert crop.as_posix() == f"originals-cropped/aa/{SHA_A}.jpg"
    assert attestation.as_posix() == f"originals-cropped/aa/{SHA_A}.json"

    siblings = cropped_sibling_paths(Path("D:/root/data/originals/aa") / f"{SHA_A}.jpg", SHA_A)
    assert siblings == (
        Path("D:/root/data/originals-cropped/aa") / f"{SHA_A}.jpg",
        Path("D:/root/data/originals-cropped/aa") / f"{SHA_A}.json",
    )
    assert cropped_sibling_paths(Path("D:/elsewhere") / f"{SHA_A}.jpg", SHA_A) is None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _resealed(document: dict[str, object]) -> bytes:
    body = {key: value for key, value in document.items() if key != "attestationSha256"}
    body["attestationSha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    return _canonical(body)


def test_attestation_bytes_are_stable_for_integer_protected_coordinates() -> None:
    attestation = _attestation(protected_box=ProtectedBox(100, 220, 300, 410))

    document = encode_attestation(attestation)
    decoded = decode_attestation(document, expected_original_checksum_sha256=SHA_A)

    assert encode_attestation(decoded) == document
    assert decoded.protected_box.as_list() == [100.0, 220.0, 300.0, 410.0]


def test_attestation_rejects_unaligned_right_and_bottom_edges() -> None:
    with pytest.raises(SourceCropError):
        _attestation(
            crop_box=PixelBox(47, 160, 352, 464), raw_crop_box=PixelBox(160, 248, 464, 553)
        )


def test_attestation_accepts_edges_on_the_image_border() -> None:
    # Orientation 6: the oriented left edge is the stored bottom edge.
    attestation = _attestation(
        original_width=601,
        crop_box=PixelBox(0, 160, 353, 464),
        raw_crop_box=PixelBox(160, 248, 464, 601),
    )
    assert attestation.raw_crop_box.bottom == 601
    with pytest.raises(SourceCropError):
        _attestation(
            original_width=602,
            crop_box=PixelBox(1, 160, 354, 464),
            raw_crop_box=PixelBox(160, 248, 464, 601),
        )


def test_attestation_rejects_an_insufficient_margin() -> None:
    with pytest.raises(SourceCropError):
        _attestation(protected_box=ProtectedBox(60.0, 220.0, 300.0, 410.0))


@pytest.mark.parametrize("imcu", [[0, 8], [8, 0]])
def test_decoding_a_sealed_document_with_zero_imcu_fails_closed(imcu: list[int]) -> None:
    parsed = json.loads(encode_attestation(_attestation()))
    parsed["crop"]["imcu"] = imcu

    with pytest.raises(SourceCropError) as error:
        decode_attestation(_resealed(parsed), expected_original_checksum_sha256=SHA_A)
    assert error.value.code == "SOURCE_CROP_ATTESTATION_INVALID"


def test_progressive_jpeg_plans_from_its_sampling_factors() -> None:
    rng = np.random.default_rng(11)
    pixels = rng.integers(0, 256, size=(589, 1080, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="JPEG", progressive=True, subsampling=2, quality=90)

    with Image.open(io.BytesIO(buffer.getvalue())) as image:
        assert isinstance(image, JpegImageFile)
        assert image.info.get("progressive") or image.info.get("progression")
        factors = [(int(h), int(v)) for _, h, v, _ in image.layer]
        width, height = image.size

    imcu = imcu_from_sampling_factors(factors)
    plan = plan_source_crop(
        [(93.2, 30.0), (725.0, 428.0)],
        oriented_width=width,
        oriented_height=height,
        orientation=None,
        imcu=imcu,
    )

    assert imcu == (16, 16)
    assert plan.raw_box == PixelBox(32, 0, 784, 480)


def test_protected_points_walk_every_known_geometry_shape() -> None:
    board_geometry = {
        "finalQuad": [
            {"x": 10, "y": 20},
            {"x": 30, "y": 20},
            {"x": 30, "y": 40},
            {"x": 10, "y": 40},
        ]
    }
    render_spec = {
        "cells": [
            {
                "sourceQuad": [[11, 21], [12, 21], [12, 22], [11, 22]],
                "paddedSourceQuad": [[5, 6], [7, 6], [7, 8], [5, 8]],
            },
        ],
        "meta": {"unrelated": [1, 2, 3, 4]},
    }
    corners = [[100.5, 1], [101, 1], [101, 2], [100.5, 2]]

    points = protected_points_from_geometry([board_geometry, render_spec, corners, None])

    assert (5.0, 6.0) in points and (100.5, 2.0) in points and (30.0, 40.0) in points
    assert len(points) == 16
    assert protected_box_from_points(points) == ProtectedBox(5.0, 1.0, 101.0, 40.0)


def test_malformed_named_quad_is_an_error() -> None:
    with pytest.raises(SourceCropError) as error:
        protected_points_from_geometry({"paddedSourceQuad": [[1, 2], [3, 4], [5, 6]]})
    assert error.value.code == "SOURCE_CROP_POINT_INVALID"
