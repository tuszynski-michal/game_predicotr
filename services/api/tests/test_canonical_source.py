"""Canonical bytes stay identical to the pre-extraction HEAD384 decoder."""

import hashlib
import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from game_predictor_api.domain import canonical_source as core
from game_predictor_worker.images import normalization as worker
from PIL import Image

# Captured from the committed HEAD384 loader with the synthetic JPEG below.
PIXEL_IDENTITIES = {
    ("RGB", None): "2ef181f9e1eaec9e54162fe7842ff0e69604f68875ded237b35f357b6def9d2b",
    ("RGB", 1): "2ef181f9e1eaec9e54162fe7842ff0e69604f68875ded237b35f357b6def9d2b",
    ("RGB", 2): "0587efd7e92c6b6bc9983b7798449b48e18eac2015ac1ce3943e763e0b9f812a",
    ("RGB", 3): "df3743a5ea889aed569608ae7b9aff7edb6a55841998f2ee2bf13a6268b2eeed",
    ("RGB", 4): "bbc94500933dca565fdd436d105cf2e0fa105b1719342e59f2576583f8b6c51c",
    ("RGB", 5): "d1d8bc3ce150183a6282fa10aed33e39126a97f61ca4cb18ab03c9c4f3aaddd1",
    ("RGB", 6): "9fdaa926d60cecaccd9e96fc228b76a0bc55f737d5c76bffe06c2eca28aee35c",
    ("RGB", 7): "9e82e7bac2641c635b5ef9aa7cce2f9ec4b28d1f458ae3767c8a8f744934fb47",
    ("RGB", 8): "11a57b893397cb765de17b5695e4a4d91e534cbb9e4afefe64707ce58616f402",
    ("L", None): "3cc51318de29da55c021b6959549e544325926c14c061cfb3ff74b609e2d0fa7",
    ("CMYK", None): "9c952bff262dbab32e0899e6ac70d70f2b3db5db2202b161e5625b19bf868963",
}


def jpeg(mode="RGB", orientation=None, *, format="JPEG"):
    image = Image.new("RGB", (4, 3))
    image.putdata([(i * 19 % 256, i * 37 % 256, i * 61 % 256) for i in range(12)])
    image = image.convert(mode)
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    output = io.BytesIO()
    image.save(output, format=format, quality=100, subsampling=0, exif=exif)
    return output.getvalue()


def decode(content, **options):
    return core.decode_canonical_source_bytes(
        content, expected_source_checksum_sha256=hashlib.sha256(content).hexdigest(), **options
    )


@pytest.mark.parametrize("mode,orientation", PIXEL_IDENTITIES)
def test_bytes_and_worker_preserve_exact_committed_identity(tmp_path, mode, orientation):
    content = jpeg(mode, orientation)
    pure = decode(content)
    path = tmp_path / "source.jpg"
    path.write_bytes(content)
    loaded = worker.CanonicalSourceLoader().load(
        path, expected_source_checksum_sha256=hashlib.sha256(content).hexdigest()
    )

    assert loaded.source == pure.source
    assert pure.source.normalized_pixel_checksum_sha256 == PIXEL_IDENTITIES[mode, orientation]
    assert pure.source.exif_orientation == orientation
    assert pure.source.normalization_adapter_version == worker.CANONICAL_SOURCE_LOADER_VERSION
    assert (pure.raw_width, pure.raw_height, pure.source_mode) == (4, 3, mode)
    assert pure.rgb.shape == ((4, 3, 3) if orientation in (5, 6, 7, 8) else (3, 4, 3))
    np.testing.assert_array_equal(loaded.rgb, pure.rgb)
    assert pure.rgb.dtype == np.uint8
    assert pure.rgb.flags.c_contiguous and not pure.rgb.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        pure.rgb[0, 0, 0] = 0


def test_worker_exports_keep_shared_class_and_exception_identity():
    for name in (
        "CanonicalSourceFrame",
        "CanonicalSourceLoadError",
        "rgb_pixel_checksum_sha256",
        "ORIENTATION_ACTIONS",
        "ORIENTATION_TAG",
        "MAX_SOURCE_PIXELS",
        "RGB_PIXEL_CHECKSUM_VERSION",
        "CANONICAL_SOURCE_LOADER_VERSION",
    ):
        assert getattr(worker, name) is getattr(core, name)


def test_loader_clear_releases_cache_and_preserves_version_override(tmp_path, monkeypatch):
    path = tmp_path / "source.jpg"
    content = jpeg()
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    loader = worker.CanonicalSourceLoader()
    loader.version = "custom-existing-adapter"
    reads = []
    read_bytes = Path.read_bytes

    def counted(candidate):
        reads.append(candidate)
        return read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", counted)
    first = loader.load(path, expected_source_checksum_sha256=expected)
    assert loader.load(path, expected_source_checksum_sha256=expected) is first
    loader.clear()
    third = loader.load(path, expected_source_checksum_sha256=expected)
    assert third is not first and len(reads) == 2
    assert third.source.normalization_adapter_version == "custom-existing-adapter"


@pytest.mark.parametrize(
    "content,options,code",
    [
        (b"not a JPEG", {}, "IMAGE_CANONICAL_SOURCE_DECODE_FAILED"),
        (jpeg(format="PNG"), {}, "IMAGE_CANONICAL_SOURCE_FORMAT_UNSUPPORTED"),
        (jpeg(orientation=9), {}, "IMAGE_CANONICAL_SOURCE_EXIF_ORIENTATION_INVALID"),
        (jpeg(), {"max_source_pixels": 11}, "IMAGE_CANONICAL_SOURCE_PIXEL_LIMIT"),
    ],
)
def test_stable_decode_failures(content, options, code):
    with pytest.raises(worker.CanonicalSourceLoadError) as failure:
        decode(content, **options)
    assert failure.value.code == code


def test_invalid_expected_checksum_precedes_file_access(tmp_path):
    with pytest.raises(core.CanonicalSourceLoadError) as failure:
        worker.CanonicalSourceLoader().load(
            tmp_path / "absent.jpg", expected_source_checksum_sha256="INVALID"
        )
    assert failure.value.code == "IMAGE_CANONICAL_SOURCE_CHECKSUM_INVALID"
    with pytest.raises(core.CanonicalSourceLoadError) as mismatch:
        core.decode_canonical_source_bytes(b"not decoded", expected_source_checksum_sha256="0" * 64)
    assert mismatch.value.code == "IMAGE_CANONICAL_SOURCE_CHECKSUM_MISMATCH"


def test_dimensioned_pixel_identity_and_frame_validation():
    rgb = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)
    assert core.rgb_pixel_checksum_sha256(rgb) == (
        "58d25c435a6b167d07adee5724723a3f3724042155ff5365bffdd3c17ac0986e"
    )
    assert core.rgb_pixel_checksum_sha256(rgb.reshape(1, 4, 3)) != (
        core.rgb_pixel_checksum_sha256(rgb)
    )
    flipped = rgb[:, ::-1]
    assert core.rgb_pixel_checksum_sha256(flipped) == core.rgb_pixel_checksum_sha256(
        np.ascontiguousarray(flipped)
    )
    frame = decode(jpeg())
    for pixels, code in (
        (frame.rgb.astype(np.float32), "IMAGE_CANONICAL_SOURCE_FRAME_INVALID"),
        (frame.rgb[:, :1], "IMAGE_CANONICAL_SOURCE_FRAME_INVALID"),
        (np.zeros_like(frame.rgb), "IMAGE_CANONICAL_SOURCE_PIXEL_CHECKSUM_MISMATCH"),
    ):
        with pytest.raises(core.CanonicalSourceLoadError) as failure:
            replace(frame, rgb=pixels)
        assert failure.value.code == code
