"""Bounded immutable diagnostic artifacts; never mutate a cohort or model."""

from __future__ import annotations

import hashlib
import json
import os
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any

from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_training_cohorts import digest
from PIL import Image

MAX_METADATA = 32 * 1024 * 1024


def safe_path(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if (
        not relative
        or part.is_absolute()
        or "\\" in relative
        or any(p in (".", "..") for p in relative.split("/"))
    ):
        raise ValueError("CROP_COMPARISON_PATH_INVALID")
    original = root.absolute().joinpath(*part.parts)
    if any(p.is_symlink() or p.is_junction() for p in (original, *original.parents)):
        raise ValueError("CROP_COMPARISON_LINK_FORBIDDEN")
    if not original.resolve().is_relative_to(root.resolve()):
        raise ValueError("CROP_COMPARISON_PATH_INVALID")
    return original


def read_json(root: Path, relative: str, expected: str | None = None) -> dict[str, Any]:
    path = safe_path(root, relative)
    if path.stat().st_size > MAX_METADATA:
        raise ValueError("CROP_COMPARISON_METADATA_LIMIT")
    raw = path.read_bytes()
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("CROP_COMPARISON_FILE_CHANGED")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("CROP_COMPARISON_OBJECT_REQUIRED")
    return value


def sealed(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "sha256": digest(value)}


def checked(value: dict[str, Any], version: str) -> None:
    if value.get("schemaVersion") != version or value.get("sha256") != digest(
        {k: v for k, v in value.items() if k != "sha256"}
    ):
        raise ValueError("CROP_COMPARISON_DOCUMENT_CHANGED")


def write_bytes(root: Path, relative: str, raw: bytes) -> dict[str, Any]:
    path = safe_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("CROP_COMPARISON_REPLAY_CONFLICT")
    else:
        temporary = None
        try:
            with NamedTemporaryFile(
                dir=path.parent, prefix=path.name + ".", suffix=".pending", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows rename refuses an existing destination. POSIX rename
            # replaces it, so use an exclusive hard link there instead.
            try:
                if os.name == "nt":
                    os.rename(temporary, path)
                else:
                    os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise ValueError("CROP_COMPARISON_REPLAY_CONFLICT") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write_json(root: Path, relative: str, document: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(
        document, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()
    if len(raw) > MAX_METADATA:
        raise ValueError("CROP_COMPARISON_METADATA_LIMIT")
    return write_bytes(root, relative, raw)


def save_raster(root: Path, relative: str, raster: Any) -> dict[str, Any]:
    stream = BytesIO()
    Image.fromarray(raster.rgb).save(stream, format="PNG")
    return {
        **write_bytes(root, relative, stream.getvalue()),
        "pixelSha256": rgb_pixel_checksum_sha256(raster.rgb),
        "renderSpecSha256": raster.render_spec_checksum_sha256,
        "renderSpec": raster.render_spec,
    }
