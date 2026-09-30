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
    return resolve_board_search_image(
        reference.relative_path,
        reference.checksum_sha256,
        artifact_root,
        code_prefix="BOARD_SEARCH_ARCHIVE_ASSET",
        subject="archived board image",
    )


def resolve_board_search_image(
    relative_path: str,
    checksum_sha256: str,
    artifact_root: Path,
    *,
    code_prefix: str,
    subject: str = "board image",
    verify_checksum: bool = True,
) -> BoardSearchArchiveAsset:
    """Resolve one checksum-bound image under `artifact_root/data`.

    `code_prefix` names the error family (`<prefix>_PATH_UNSAFE`,
    `_NOT_FOUND`, `_MEDIA_TYPE_UNSUPPORTED`, `_CHECKSUM_DRIFT`) and `subject`
    the noun used in messages.
    """

    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise BoardSearchError(
            f"{code_prefix}_PATH_UNSAFE",
            f"The {subject} path is unsafe.",
        )
    managed_root = artifact_root.resolve() / "data"
    candidate = managed_root.joinpath(*relative.parts).resolve()
    if (
        not candidate.is_relative_to(managed_root)
        or not candidate.is_file()
        or candidate.is_symlink()
    ):
        raise BoardSearchError(
            f"{code_prefix}_NOT_FOUND",
            f"The {subject} is unavailable.",
        )
    media_type, _encoding = mimetypes.guess_type(candidate.name)
    if media_type not in _IMAGE_MEDIA_TYPES:
        raise BoardSearchError(
            f"{code_prefix}_MEDIA_TYPE_UNSUPPORTED",
            f"The {subject} format is unsupported.",
        )
    if verify_checksum and _sha256(candidate) != checksum_sha256:
        raise BoardSearchError(
            f"{code_prefix}_CHECKSUM_DRIFT",
            f"The {subject} checksum differs from persistence.",
        )
    return BoardSearchArchiveAsset(path=candidate, media_type=media_type)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "BoardSearchArchiveAsset",
    "resolve_board_search_archive_asset",
    "resolve_board_search_image",
]
