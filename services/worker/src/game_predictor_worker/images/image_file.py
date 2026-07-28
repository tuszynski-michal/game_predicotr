"""Bounded, dependency-free helpers for source image files."""

from __future__ import annotations

import hashlib
from pathlib import Path

JPEG_START_OF_FRAME_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)


class ImageFileError(ValueError):
    """Stable low-level source image failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    """Return SHA-256 without materializing the whole file in memory."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ImageFileError("IMAGE_SOURCE_UNREADABLE", "Source image cannot be read.") from error
    return digest.hexdigest()


def read_jpeg_dimensions(path: Path) -> tuple[int, int]:
    """Read JPEG dimensions from a Start Of Frame marker."""

    try:
        with path.open("rb") as source:
            if source.read(2) != b"\xff\xd8":
                raise ImageFileError(
                    "IMAGE_SOURCE_FORMAT_MISMATCH",
                    "File extension declares JPEG but its signature does not.",
                )
            while True:
                marker_start = source.read(1)
                if not marker_start:
                    break
                if marker_start != b"\xff":
                    continue
                marker = source.read(1)
                while marker == b"\xff":
                    marker = source.read(1)
                if not marker:
                    break
                marker_value = marker[0]
                if marker_value in {0xD8, 0xD9}:
                    continue
                if marker_value == 0xDA:
                    break
                length_bytes = source.read(2)
                if len(length_bytes) != 2:
                    break
                segment_length = int.from_bytes(length_bytes, "big")
                if segment_length < 2:
                    break
                if marker_value in JPEG_START_OF_FRAME_MARKERS:
                    payload = source.read(segment_length - 2)
                    if len(payload) < 5:
                        break
                    height = int.from_bytes(payload[1:3], "big")
                    width = int.from_bytes(payload[3:5], "big")
                    if width > 0 and height > 0:
                        return width, height
                    break
                source.seek(segment_length - 2, 1)
    except ImageFileError:
        raise
    except OSError as error:
        raise ImageFileError("IMAGE_SOURCE_UNREADABLE", "Source image cannot be read.") from error
    raise ImageFileError("IMAGE_SOURCE_CORRUPT", "JPEG dimensions cannot be read.")
