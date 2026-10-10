"""Frozen, per-game protection for pilot evaluation photographs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import cast

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.images.normalization import (
    MAX_SOURCE_PIXELS,
    ORIENTATION_TAG,
    rgb_pixel_checksum_sha256,
)

MUMIE_GAME_ID = "fea55cc1-ebf4-4cee-b3ab-a520017ed1be"
DESCRIPTOR_VERSION = "protected-source-exclusions-v1"
DESCRIPTOR_SHA256 = "25fedbdf124dfd1cf8038addb9f8a176817b2b2361cff62fe0f8f9a18f1d7812"
DESCRIPTOR_PATH = "training/fea55cc1ebf44ceeb3aba520017ed1be/protected-source-exclusions-v1.json"


class ProtectedSourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def managed_path(data_root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    resolved = data_root.joinpath(*path.parts).resolve()
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or not resolved.is_relative_to(data_root.resolve())
    ):
        raise ProtectedSourceError(
            "PROTECTED_SOURCE_PATH_INVALID", "Protected source path is outside managed storage."
        )
    if resolved.is_symlink() or not resolved.is_file():
        raise ProtectedSourceError(
            "PROTECTED_SOURCE_MISSING", "A required managed original is unavailable."
        )
    return resolved


def source_pixel_identity(data_root: Path, relative: str, checksum: str) -> str:
    try:
        # Hash and decode the same bytes, so replacement between reads cannot
        # attach another photograph's pixels to the frozen byte identity.
        content = managed_path(data_root, relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ProtectedSourceError(
                "PROTECTED_SOURCE_DRIFT", "A managed original has changed bytes."
            )
        with Image.open(BytesIO(content)) as source:
            orientation = source.getexif().get(ORIENTATION_TAG)
            if (
                source.format != "JPEG"
                or source.width * source.height > MAX_SOURCE_PIXELS
                or (
                    orientation is not None
                    and (
                        isinstance(orientation, bool)
                        or not isinstance(orientation, int)
                        or orientation not in range(1, 9)
                    )
                )
            ):
                raise ProtectedSourceError(
                    "PROTECTED_SOURCE_DRIFT", "A managed original has invalid image metadata."
                )
            source.load()
            pixels = np.array(
                ImageOps.exif_transpose(source).convert("RGB"), dtype=np.uint8, copy=True
            )
        return rgb_pixel_checksum_sha256(pixels)
    except (OSError, UnidentifiedImageError, ValueError) as error:
        if isinstance(error, ProtectedSourceError):
            raise
        raise ProtectedSourceError(
            "PROTECTED_SOURCE_DRIFT", "A managed original failed byte or decoded pixel validation."
        ) from error


@dataclass(frozen=True)
class ProtectedSources:
    byte_checksums: frozenset[str]
    pixel_checksums: frozenset[str]

    def excludes(self, checksum: str, pixels: str) -> bool:
        return checksum in self.byte_checksums or pixels in self.pixel_checksums

    def reference(self) -> dict[str, object]:
        return {
            "version": DESCRIPTOR_VERSION,
            "checksumSha256": DESCRIPTOR_SHA256,
            "relativePath": DESCRIPTOR_PATH,
            "sourceSplitGuarantee": "whole-photo",
            "recordingIdentityAvailable": False,
        }


def load_protected_sources(artifact_root: Path, game_id: str) -> ProtectedSources | None:
    if game_id != MUMIE_GAME_ID:
        return None
    data_root = artifact_root.resolve() / "data"
    try:
        envelope = json.loads(managed_path(data_root, DESCRIPTOR_PATH).read_text(encoding="utf-8"))
        payload = envelope["payload"]
        checksum = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if checksum != DESCRIPTOR_SHA256 or envelope["sha256"] != checksum:
            raise ProtectedSourceError(
                "PROTECTED_SOURCE_DESCRIPTOR_DRIFT", "The frozen exclusion descriptor has changed."
            )
        rows = cast(list[Mapping[str, str]], payload["rows"])
        for row in rows:
            pixels = source_pixel_identity(
                data_root, row["sourceRelativePath"], row["sourceByteSha256"]
            )
            if pixels != row["normalizedPixelChecksumSha256"]:
                raise ProtectedSourceError(
                    "PROTECTED_SOURCE_DRIFT", "A protected original has changed decoded pixels."
                )
        return ProtectedSources(
            frozenset(row["sourceByteSha256"] for row in rows),
            frozenset(row["normalizedPixelChecksumSha256"] for row in rows),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, ProtectedSourceError):
            raise
        raise ProtectedSourceError(
            "PROTECTED_SOURCE_DESCRIPTOR_INVALID",
            "The frozen exclusion descriptor is missing or invalid.",
        ) from error


def require_frozen_reference(protected: ProtectedSources, cohort: Mapping[str, object]) -> None:
    if cohort.get("protectedSourceExclusions") != protected.reference():
        raise ProtectedSourceError(
            "PROTECTED_SOURCE_COHORT_UNQUALIFIED",
            "New Mumie training requires a cohort frozen with the current exclusion descriptor.",
        )
