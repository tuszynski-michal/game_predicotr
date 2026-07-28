from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from game_predictor_worker.images.discovery import (
    ImageDiscoveryError,
    discover_images,
    known_checksums_from_manifest,
    select_unseen_images,
)


def _jpeg(width: int = 16, height: int = 12) -> bytes:
    payload = b"\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xc0" + (len(payload) + 2).to_bytes(2, "big") + payload + b"\xff\xd9"


def test_discovery_is_deterministic_and_read_only(tmp_path: Path) -> None:
    root = tmp_path / "source"
    nested = root / "nested"
    nested.mkdir(parents=True)
    first = root / "b.jpg"
    second = nested / "a.jpeg"
    first.write_bytes(_jpeg(20, 10))
    second.write_bytes(_jpeg(30, 15))
    (root / "README.md").write_text("not an image", encoding="utf-8")
    before = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }

    first_manifest = discover_images(root)
    second_manifest = discover_images(root)

    assert first_manifest.to_json_bytes() == second_manifest.to_json_bytes()
    assert first_manifest.source_file_count == 2
    assert first_manifest.ignored_file_count == 1
    assert not first_manifest.issues
    manifest_text = first_manifest.to_json_bytes().decode()
    assert str(root.resolve()) not in manifest_text
    assert '"sourceRoot": "."' in manifest_text
    assert {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    } == before


def test_duplicate_content_is_one_image_with_two_paths(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    content = _jpeg()
    (root / "one.jpg").write_bytes(content)
    (root / "two.jpeg").write_bytes(content)

    manifest = discover_images(root)

    assert len(manifest.images) == 1
    assert manifest.source_file_count == 2
    assert manifest.duplicate_file_count == 1
    assert [item.relative_path for item in manifest.images[0].files] == [
        "one.jpg",
        "two.jpeg",
    ]


def test_known_manifest_selects_only_unseen_content(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    first_content = _jpeg(10, 10)
    (root / "first.jpg").write_bytes(first_content)
    (root / "second.jpg").write_bytes(_jpeg(11, 10))
    known_path = tmp_path / "known.json"
    known_path.write_text(
        json.dumps(
            {
                "images": [
                    {"sha256": hashlib.sha256(first_content).hexdigest()},
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = discover_images(root)
    known = known_checksums_from_manifest(known_path)
    unseen = select_unseen_images(manifest, known)

    assert len(known) == 1
    assert len(unseen) == 1
    assert unseen[0].checksum_sha256 not in known


def test_corrupt_and_unsupported_images_have_stable_codes(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "corrupt.jpg").write_bytes(b"\xff\xd8broken")
    (root / "phone.heic").write_bytes(b"image")

    manifest = discover_images(root)

    assert [(issue.relative_path, issue.code) for issue in manifest.issues] == [
        ("corrupt.jpg", "IMAGE_SOURCE_CORRUPT"),
        ("phone.heic", "IMAGE_SOURCE_FORMAT_UNSUPPORTED"),
    ]


def test_extension_signature_mismatch_has_stable_code(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "not-jpeg.jpg").write_bytes(b"not a jpeg")

    manifest = discover_images(root)

    assert len(manifest.issues) == 1
    assert manifest.issues[0].code == "IMAGE_SOURCE_FORMAT_MISMATCH"


def test_missing_root_is_a_fatal_stable_error(tmp_path: Path) -> None:
    with pytest.raises(ImageDiscoveryError) as raised:
        discover_images(tmp_path / "missing")

    assert raised.value.code == "IMAGE_DISCOVERY_ROOT_NOT_FOUND"
