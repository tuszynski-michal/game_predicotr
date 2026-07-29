"""Fail-closed resolution of image assets belonging to one review item."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from game_predictor_api.domain.reviews import (
    REVIEW_ITEM_CELL_COUNT,
    ReviewItem,
    ReviewNotFoundError,
)

_IMAGE_MEDIA_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_HASH_CHUNK_BYTES: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ReviewImageAsset:
    path: Path
    media_type: str


def resolve_review_board_asset(
    item: ReviewItem,
    crop_root: Path,
) -> ReviewImageAsset:
    return _resolve_relative_image(
        crop_root,
        item.board_relative_path,
        asset_kind="board",
    )


def resolve_review_cell_asset(
    item: ReviewItem,
    cell_index: int,
    crop_root: Path,
) -> ReviewImageAsset:
    if not 0 <= cell_index < REVIEW_ITEM_CELL_COUNT:
        raise ReviewNotFoundError(
            "REVIEW_CELL_NOT_FOUND",
            "The requested review cell does not exist.",
            details={"cellIndex": cell_index},
        )
    cells = item.prediction_snapshot.get("cells")
    if not isinstance(cells, list | tuple) or len(cells) != REVIEW_ITEM_CELL_COUNT:
        raise ReviewNotFoundError(
            "REVIEW_ASSET_METADATA_INVALID",
            "The immutable review item has no valid cell asset metadata.",
        )
    cell = cells[cell_index]
    if not isinstance(cell, dict):
        raise ReviewNotFoundError(
            "REVIEW_ASSET_METADATA_INVALID",
            "The immutable review cell has no valid asset metadata.",
        )
    path = cell.get("cropRelativePath")
    if not isinstance(path, str):
        raise ReviewNotFoundError(
            "REVIEW_ASSET_METADATA_INVALID",
            "The immutable review cell has no crop path.",
        )
    return _resolve_relative_image(crop_root, path, asset_kind="cell")


def resolve_review_source_asset(
    item: ReviewItem,
    source_root: Path,
) -> ReviewImageAsset:
    root = source_root.resolve()
    matches: list[ReviewImageAsset] = []
    if root.is_dir():
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            media_type = _image_media_type(candidate)
            if media_type is None:
                continue
            if _sha256(candidate) == item.source_image_checksum_sha256:
                matches.append(ReviewImageAsset(candidate.resolve(), media_type))
                if len(matches) > 1:
                    break
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ReviewNotFoundError(
            "REVIEW_SOURCE_ASSET_AMBIGUOUS",
            "More than one local source image has the expected checksum.",
            details={"sourceImageId": item.source_image_id},
        )
    raise ReviewNotFoundError(
        "REVIEW_ASSET_NOT_FOUND",
        "The checksum-bound local source image is unavailable.",
        details={"sourceImageId": item.source_image_id},
    )


def _resolve_relative_image(
    root: Path,
    relative_path: str,
    *,
    asset_kind: str,
) -> ReviewImageAsset:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise ReviewNotFoundError(
            "REVIEW_ASSET_PATH_UNSAFE",
            "The stored review asset path is unsafe.",
            details={"assetKind": asset_kind},
        )
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
        raise ReviewNotFoundError(
            "REVIEW_ASSET_NOT_FOUND",
            "The local review image is unavailable.",
            details={"assetKind": asset_kind},
        )
    media_type = _image_media_type(candidate)
    if media_type is None:
        raise ReviewNotFoundError(
            "REVIEW_ASSET_MEDIA_TYPE_UNSUPPORTED",
            "The local review asset is not a supported image.",
            details={"assetKind": asset_kind},
        )
    return ReviewImageAsset(candidate, media_type)


def _image_media_type(path: Path) -> str | None:
    media_type, _encoding = mimetypes.guess_type(path.name)
    return media_type if media_type in _IMAGE_MEDIA_TYPES else None


def _sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_BYTES):
            checksum.update(chunk)
    return checksum.hexdigest()


__all__ = [
    "ReviewImageAsset",
    "resolve_review_board_asset",
    "resolve_review_cell_asset",
    "resolve_review_source_asset",
]
