from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

import pytest
from game_predictor_worker.images.discovery import discover_images
from game_predictor_worker.images.normalization import (
    ImageNormalizationError,
    normalize_images,
)
from PIL import Image

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


def _write_pattern_jpeg(path: Path, orientation: int | None) -> None:
    image = Image.new("RGB", (30, 20))
    labels = (("A", "B", "C"), ("D", "E", "F"))
    for row, row_labels in enumerate(labels):
        for column, label in enumerate(row_labels):
            image.paste(
                COLORS[label],
                (column * 10, row * 10, (column + 1) * 10, (row + 1) * 10),
            )
    exif = Image.Exif()
    if orientation is not None:
        exif[ORIENTATION_TAG] = orientation
    image.save(path, format="JPEG", quality=100, subsampling=0, exif=exif)


def _source_and_manifest(
    tmp_path: Path,
    *,
    orientation: int | None,
) -> tuple[Path, Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    source_image = source / "pattern.jpg"
    _write_pattern_jpeg(source_image, orientation)
    manifest = discover_images(source)
    manifest_path = tmp_path / "discovery.json"
    manifest_path.write_bytes(manifest.to_json_bytes())
    checksum = hashlib.sha256(source_image.read_bytes()).hexdigest()
    return source, manifest_path, checksum


def _artifact_path(root: Path, relative_path: str) -> Path:
    return root / Path(*PurePosixPath(relative_path).parts)


def _nearest_label(pixel: tuple[int, ...]) -> str:
    rgb = pixel[:3]
    return min(
        COLORS,
        key=lambda label: sum(
            (component - expected) ** 2
            for component, expected in zip(rgb, COLORS[label], strict=True)
        ),
    )


def _sample_labels(image: Image.Image) -> tuple[tuple[str, ...], ...]:
    columns = image.width // 10
    rows = image.height // 10
    return tuple(
        tuple(
            _nearest_label(image.getpixel((column * 10 + 5, row * 10 + 5)))
            for column in range(columns)
        )
        for row in range(rows)
    )


@pytest.mark.parametrize("orientation", range(1, 9))
def test_all_exif_orientations_have_expected_pixels_and_dimensions(
    tmp_path: Path,
    orientation: int,
) -> None:
    source, manifest_path, source_checksum = _source_and_manifest(
        tmp_path,
        orientation=orientation,
    )
    artifact_root = tmp_path / "artifacts"

    report = normalize_images(source, manifest_path, artifact_root)

    assert not report.issues
    assert len(report.images) == 1
    result = report.images[0]
    assert result.exif_orientation == orientation
    assert result.source_checksum_sha256 == source_checksum
    expected = EXPECTED_LABELS[orientation]
    normalized_path = _artifact_path(artifact_root, result.normalized_relative_path)
    with Image.open(normalized_path) as normalized:
        normalized.load()
        assert normalized.mode == "RGB"
        assert normalized.size == (len(expected[0]) * 10, len(expected) * 10)
        assert _sample_labels(normalized) == expected
        assert normalized.getexif().get(ORIENTATION_TAG) is None


def test_missing_orientation_is_explicit_and_retry_is_idempotent(tmp_path: Path) -> None:
    source, manifest_path, source_checksum = _source_and_manifest(
        tmp_path,
        orientation=None,
    )
    artifact_root = tmp_path / "artifacts"
    source_path = source / "pattern.jpg"

    first = normalize_images(source, manifest_path, artifact_root)
    artifact_paths = [
        _artifact_path(artifact_root, first.images[0].normalized_relative_path),
        _artifact_path(artifact_root, first.images[0].diagnostic_relative_path),
    ]
    mtimes = [path.stat().st_mtime_ns for path in artifact_paths]
    second = normalize_images(source, manifest_path, artifact_root)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.images[0].exif_orientation is None
    assert first.images[0].orientation_action == "none"
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_checksum
    assert [path.stat().st_mtime_ns for path in artifact_paths] == mtimes


def test_source_manifest_drift_is_a_fatal_stable_error(tmp_path: Path) -> None:
    source, manifest_path, _ = _source_and_manifest(tmp_path, orientation=1)
    with (source / "pattern.jpg").open("ab") as target:
        target.write(b"changed")

    with pytest.raises(ImageNormalizationError) as raised:
        normalize_images(source, manifest_path, tmp_path / "artifacts")

    assert raised.value.code == "IMAGE_NORMALIZATION_SOURCE_MANIFEST_DRIFT"


def test_artifact_collision_is_reported_without_overwrite(tmp_path: Path) -> None:
    source, manifest_path, _ = _source_and_manifest(tmp_path, orientation=1)
    artifact_root = tmp_path / "artifacts"
    first = normalize_images(source, manifest_path, artifact_root)
    normalized_path = _artifact_path(artifact_root, first.images[0].normalized_relative_path)
    normalized_path.write_bytes(b"different")

    second = normalize_images(source, manifest_path, artifact_root)

    assert not second.images
    assert len(second.issues) == 1
    assert second.issues[0].code == "IMAGE_NORMALIZATION_ARTIFACT_COLLISION"
    assert normalized_path.read_bytes() == b"different"


def test_invalid_orientation_and_pixel_limit_have_stable_codes(tmp_path: Path) -> None:
    source, manifest_path, _ = _source_and_manifest(tmp_path, orientation=9)

    invalid_orientation = normalize_images(
        source,
        manifest_path,
        tmp_path / "orientation-artifacts",
    )
    pixel_limit = normalize_images(
        source,
        manifest_path,
        tmp_path / "limit-artifacts",
        max_source_pixels=1,
    )

    assert invalid_orientation.issues[0].code == ("IMAGE_NORMALIZATION_EXIF_ORIENTATION_INVALID")
    assert pixel_limit.issues[0].code == "IMAGE_NORMALIZATION_PIXEL_LIMIT"


def test_artifact_root_inside_source_is_rejected(tmp_path: Path) -> None:
    source, manifest_path, _ = _source_and_manifest(tmp_path, orientation=1)

    with pytest.raises(ImageNormalizationError) as raised:
        normalize_images(source, manifest_path, source / "working")

    assert raised.value.code == "IMAGE_NORMALIZATION_OUTPUT_IN_SOURCE"


def test_unresolved_discovery_issue_blocks_normalization(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "corrupt.jpg").write_bytes(b"\xff\xd8broken")
    manifest_path = tmp_path / "discovery.json"
    manifest_path.write_bytes(discover_images(source).to_json_bytes())

    with pytest.raises(ImageNormalizationError) as raised:
        normalize_images(source, manifest_path, tmp_path / "artifacts")

    assert raised.value.code == "IMAGE_NORMALIZATION_DISCOVERY_ISSUES"
