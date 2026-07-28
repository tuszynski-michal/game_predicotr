"""Deterministic, read-only discovery of local source images."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from game_predictor_worker.images.image_file import (
    ImageFileError,
    read_jpeg_dimensions,
    sha256_file,
)

DISCOVERY_VERSION = "image-discovery-v1"
SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg"})
IMAGE_LIKE_EXTENSIONS = frozenset(
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ImageDiscoveryError(ValueError):
    """Stable fatal error for the discovery operation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceFile:
    relative_path: str
    size_bytes: int
    modified_at_ns: int

    def to_dict(self) -> dict[str, object]:
        return {
            "modifiedAtNs": self.modified_at_ns,
            "relativePath": self.relative_path,
            "sizeBytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class SourceImage:
    checksum_sha256: str
    width: int
    height: int
    files: tuple[SourceFile, ...]

    @property
    def content_id(self) -> str:
        return f"sha256:{self.checksum_sha256}"

    def to_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "contentId": self.content_id,
            "files": [item.to_dict() for item in self.files],
            "height": self.height,
            "mediaType": "image/jpeg",
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryIssue:
    code: str
    relative_path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "relativePath": self.relative_path,
        }


@dataclass(frozen=True, slots=True)
class SourceManifest:
    images: tuple[SourceImage, ...]
    issues: tuple[DiscoveryIssue, ...]
    ignored_file_count: int

    @property
    def source_file_count(self) -> int:
        return sum(len(image.files) for image in self.images)

    @property
    def duplicate_file_count(self) -> int:
        return self.source_file_count - len(self.images)

    def to_dict(self) -> dict[str, object]:
        return {
            "discoveryVersion": DISCOVERY_VERSION,
            "duplicateFileCount": self.duplicate_file_count,
            "ignoredFileCount": self.ignored_file_count,
            "images": [image.to_dict() for image in self.images],
            "issueCount": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
            "schemaVersion": 1,
            "sourceFileCount": self.source_file_count,
            "sourceRoot": ".",
            "supportedMediaTypes": ["image/jpeg"],
            "uniqueImageCount": len(self.images),
        }

    def to_json_bytes(self) -> bytes:
        text = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"{text}\n".encode()


def _relative_posix(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ImageDiscoveryError(
            "IMAGE_SOURCE_PATH_ESCAPE",
            "Source image path escapes the configured root.",
        ) from error
    return relative.as_posix()


def _issue(code: str, relative_path: str, message: str) -> DiscoveryIssue:
    return DiscoveryIssue(code=code, relative_path=relative_path, message=message)


def _discover_supported_file(
    root: Path,
    path: Path,
    relative_path: str,
) -> tuple[str, int, int, int, int] | DiscoveryIssue:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return _issue(
            "IMAGE_SOURCE_UNREADABLE",
            relative_path,
            "Source image cannot be resolved or read.",
        )
    if not resolved.is_relative_to(root):
        return _issue(
            "IMAGE_SOURCE_PATH_ESCAPE",
            relative_path,
            "Source image path escapes the configured root.",
        )
    try:
        stat = path.stat()
    except OSError:
        return _issue(
            "IMAGE_SOURCE_UNREADABLE",
            relative_path,
            "Source image metadata cannot be read.",
        )
    if not path.is_file():
        return _issue(
            "IMAGE_SOURCE_UNREADABLE",
            relative_path,
            "Source image is not a regular file.",
        )
    try:
        width, height = read_jpeg_dimensions(path)
        checksum = sha256_file(path)
    except ImageFileError as error:
        return _issue(error.code, relative_path, str(error))
    return checksum, stat.st_size, stat.st_mtime_ns, width, height


def discover_images(source_root: Path) -> SourceManifest:
    """Scan a folder without writing to it and return a deterministic manifest."""

    try:
        root = source_root.resolve(strict=True)
    except OSError as error:
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_ROOT_NOT_FOUND",
            "Source image root does not exist or cannot be resolved.",
        ) from error
    if not root.is_dir():
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_ROOT_NOT_DIRECTORY",
            "Source image root must be a directory.",
        )

    grouped_files: dict[str, list[SourceFile]] = {}
    dimensions_by_checksum: dict[str, tuple[int, int]] = {}
    issues: list[DiscoveryIssue] = []
    ignored_file_count = 0

    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names.sort(key=lambda value: (value.casefold(), value))
        file_names.sort(key=lambda value: (value.casefold(), value))
        current = Path(current_root)
        for file_name in file_names:
            path = current / file_name
            relative_path = _relative_posix(root, path)
            extension = path.suffix.casefold()
            if extension in IMAGE_LIKE_EXTENSIONS:
                issues.append(
                    _issue(
                        "IMAGE_SOURCE_FORMAT_UNSUPPORTED",
                        relative_path,
                        f"Image extension {extension} is not supported by {DISCOVERY_VERSION}.",
                    )
                )
                continue
            if extension not in SUPPORTED_EXTENSIONS:
                ignored_file_count += 1
                continue
            discovered = _discover_supported_file(root, path, relative_path)
            if isinstance(discovered, DiscoveryIssue):
                issues.append(discovered)
                continue
            checksum, size_bytes, modified_at_ns, width, height = discovered
            grouped_files.setdefault(checksum, []).append(
                SourceFile(
                    relative_path=relative_path,
                    size_bytes=size_bytes,
                    modified_at_ns=modified_at_ns,
                )
            )
            dimensions_by_checksum.setdefault(checksum, (width, height))

    images = tuple(
        SourceImage(
            checksum_sha256=checksum,
            width=dimensions_by_checksum[checksum][0],
            height=dimensions_by_checksum[checksum][1],
            files=tuple(
                sorted(
                    files,
                    key=lambda item: (item.relative_path.casefold(), item.relative_path),
                )
            ),
        )
        for checksum, files in sorted(grouped_files.items())
    )
    return SourceManifest(
        images=images,
        issues=tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.relative_path.casefold(),
                    item.relative_path,
                    item.code,
                ),
            )
        ),
        ignored_file_count=ignored_file_count,
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_KNOWN_MANIFEST_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_KNOWN_MANIFEST_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def known_checksums_from_manifest(path: Path) -> frozenset[str]:
    """Read checksums from either discovery-v1 or the M5 corpus manifest."""

    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ImageDiscoveryError(
            "IMAGE_DISCOVERY_KNOWN_MANIFEST_INVALID",
            "Known manifest cannot be read as JSON.",
        ) from error
    manifest = _mapping(value, "manifest")
    checksums: set[str] = set()
    for index, image_value in enumerate(_sequence(manifest.get("images"), "manifest.images")):
        image = _mapping(image_value, f"manifest.images[{index}]")
        checksum_value = image.get("checksumSha256", image.get("sha256"))
        if not isinstance(checksum_value, str) or not SHA256_PATTERN.fullmatch(checksum_value):
            raise ImageDiscoveryError(
                "IMAGE_DISCOVERY_KNOWN_MANIFEST_INVALID",
                f"manifest.images[{index}] has no valid SHA-256.",
            )
        checksums.add(checksum_value)
    return frozenset(checksums)


def select_unseen_images(
    manifest: SourceManifest,
    known_checksums: Iterable[str],
) -> tuple[SourceImage, ...]:
    """Select content that has not already been processed."""

    known = frozenset(known_checksums)
    return tuple(image for image in manifest.images if image.checksum_sha256 not in known)
