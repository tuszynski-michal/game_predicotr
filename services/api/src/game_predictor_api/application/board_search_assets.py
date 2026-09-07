"""Fail-closed filesystem resolution for frozen board-search assets."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from game_predictor_api.domain.board_search import (
    BoardSearchArchiveAssetReference,
    BoardSearchError,
)

_IMAGE_MEDIA_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_HASH_CHUNK_BYTES: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class BoardSearchArchiveAsset:
    path: Path
    media_type: str


def resolve_board_search_archive_asset(
    reference: BoardSearchArchiveAssetReference,
    artifact_root: Path,
) -> BoardSearchArchiveAsset:
    relative = PurePosixPath(reference.relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in reference.relative_path:
        raise BoardSearchError(
            "BOARD_SEARCH_ARCHIVE_ASSET_PATH_UNSAFE",
            "The archived board image path is unsafe.",
        )
    managed_root = artifact_root.resolve() / "data"
    candidate = managed_root.joinpath(*relative.parts).resolve()
    if (
        not candidate.is_relative_to(managed_root)
        or not candidate.is_file()
        or candidate.is_symlink()
    ):
        raise BoardSearchError(
            "BOARD_SEARCH_ARCHIVE_ASSET_NOT_FOUND",
            "The archived board image is unavailable.",
        )
    media_type, _encoding = mimetypes.guess_type(candidate.name)
    if media_type not in _IMAGE_MEDIA_TYPES:
        raise BoardSearchError(
            "BOARD_SEARCH_ARCHIVE_ASSET_MEDIA_TYPE_UNSUPPORTED",
            "The archived board image format is unsupported.",
        )
    if _sha256(candidate) != reference.checksum_sha256:
        raise BoardSearchError(
            "BOARD_SEARCH_ARCHIVE_ASSET_CHECKSUM_DRIFT",
            "The archived board image checksum differs from persistence.",
        )
    return BoardSearchArchiveAsset(path=candidate, media_type=media_type)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["BoardSearchArchiveAsset", "resolve_board_search_archive_asset"]
