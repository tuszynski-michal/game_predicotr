"""Fail-closed assets for one operational image review item."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from game_predictor_api.domain.board_cell_geometry_pending import ImageBoardGeometryPending
from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    ImageReviewItem,
    ImageReviewNotFoundError,
)

_IMAGE_MEDIA_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_HASH_CHUNK_BYTES: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class OperationalReviewAsset:
    path: Path
    media_type: str


def resolve_operational_source_asset(
    item: ImageReviewItem,
    artifact_root: Path,
) -> OperationalReviewAsset:
    return _resolve(
        artifact_root,
        item.source_relative_path,
        item.source_checksum_sha256,
        asset_kind="source",
    )


def resolve_pending_board_cell_source_asset(
    item: ImageBoardGeometryPending,
    artifact_root: Path,
) -> OperationalReviewAsset:
    return _resolve(
        artifact_root,
        item.source_relative_path,
        item.source_checksum_sha256,
        asset_kind="pending-board-cell-source",
    )


def resolve_operational_board_asset(
    item: ImageReviewItem,
    artifact_root: Path,
) -> OperationalReviewAsset:
    return _resolve(
        artifact_root,
        item.board_relative_path,
        item.board_checksum_sha256,
        asset_kind="board",
    )


def resolve_operational_cell_asset(
    item: ImageReviewItem,
    cell_index: int,
    artifact_root: Path,
) -> OperationalReviewAsset:
    if not 0 <= cell_index < IMAGE_REVIEW_CELL_COUNT:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_CELL_NOT_FOUND",
            "The requested operational review cell does not exist.",
            details={"cellIndex": cell_index},
        )
    cell = item.cells[cell_index]
    return _resolve(
        artifact_root,
        cell.crop_relative_path,
        cell.crop_checksum_sha256,
        asset_kind="cell",
    )


def _resolve(
    artifact_root: Path,
    relative_path: str,
    expected_sha256: str,
    *,
    asset_kind: str,
) -> OperationalReviewAsset:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_PATH_UNSAFE",
            "The stored operational review asset path is unsafe.",
            details={"assetKind": asset_kind},
        )
    managed_root = artifact_root.resolve() / "data"
    candidate = managed_root.joinpath(*relative.parts).resolve()
    if (
        not candidate.is_relative_to(managed_root)
        or not candidate.is_file()
        or candidate.is_symlink()
    ):
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_NOT_FOUND",
            "The local operational review image is unavailable.",
            details={"assetKind": asset_kind},
        )
    media_type, _encoding = mimetypes.guess_type(candidate.name)
    if media_type not in _IMAGE_MEDIA_TYPES:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_MEDIA_TYPE_UNSUPPORTED",
            "The operational review asset is not a supported image.",
            details={"assetKind": asset_kind},
        )
    if _sha256(candidate) != expected_sha256:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT",
            "The operational review asset checksum differs from persistence.",
            details={"assetKind": asset_kind},
        )
    return OperationalReviewAsset(candidate, media_type)


def _sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_BYTES):
            checksum.update(chunk)
    return checksum.hexdigest()


__all__ = [
    "OperationalReviewAsset",
    "resolve_operational_board_asset",
    "resolve_operational_cell_asset",
    "resolve_operational_source_asset",
    "resolve_pending_board_cell_source_asset",
]
