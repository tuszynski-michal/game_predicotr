"""Fail-closed assets for one operational image review item."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final
from uuid import uuid4

from game_predictor_api.domain.board_cell_geometry_pending import ImageBoardGeometryPending
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewSourceAsset
from game_predictor_api.domain.image_reviews import (
    IMAGE_REVIEW_CELL_COUNT,
    ImageReviewItem,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.source_crop import attestation_sha256, encode_attestation
from game_predictor_api.storage.image_geometry_completeness_repository import (
    GeometrySourceImageAsset,
)

LOGGER = logging.getLogger(__name__)
_IMAGE_MEDIA_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_HASH_CHUNK_BYTES: Final = 1024 * 1024
# Asset kinds that serve a managed original (D-562 serves its crop canvas).
_SOURCE_ASSET_KINDS: Final = frozenset(
    {"source", "grid-review-source", "geometry-completeness-source", "pending-board-cell-source"}
)
SOURCE_FRAME_PREVIEW_DIRECTORY: Final = Path("working", "source-frame-previews")


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


def resolve_grid_review_source_asset(
    item: ImageGridReviewSourceAsset,
    artifact_root: Path,
) -> OperationalReviewAsset:
    return _resolve(
        artifact_root,
        item.source_relative_path,
        item.source_checksum_sha256,
        asset_kind="grid-review-source",
    )


def resolve_geometry_completeness_source_asset(
    asset: GeometrySourceImageAsset,
    artifact_root: Path,
) -> OperationalReviewAsset:
    return _resolve(
        artifact_root,
        asset.relative_path,
        asset.checksum_sha256,
        asset_kind="geometry-completeness-source",
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
    cell = next((value for value in item.cells if value.cell_index == cell_index), None)
    if cell is None:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_CELL_NOT_FOUND",
            "The requested operational review cell has no image.",
            details={"cellIndex": cell_index},
        )
    if cell.crop_relative_path is None:
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_VIRTUAL_ASSET_UNAVAILABLE",
            "Virtual cell assets must be rendered through the structured asset endpoint.",
        )
    return _resolve(
        artifact_root,
        cell.crop_relative_path,
        cell.crop_checksum_sha256,
        asset_kind="cell",
    )


def resolve_grid_review_source_path(
    item: ImageGridReviewSourceAsset,
    artifact_root: Path,
) -> Path:
    """Managed original path for a canonical loader (never the served preview).

    D-562: when the original was replaced, the path is returned although the
    file is gone, so a loader with ``allow_crop=True`` can verify the crop.
    """

    return resolve_managed_source_path(
        artifact_root,
        item.source_relative_path,
        item.source_checksum_sha256,
        asset_kind="grid-review-source",
    )


def resolve_managed_source_path(
    artifact_root: Path,
    relative_path: str,
    expected_sha256: str,
    *,
    asset_kind: str,
) -> Path:
    managed_root, candidate = _safe_candidate(artifact_root, relative_path, asset_kind=asset_kind)
    if candidate.is_file() and not candidate.is_symlink():
        return candidate
    if not candidate.exists() and _managed_original_is_cropped(candidate, expected_sha256):
        return candidate
    _log_not_found(asset_kind, relative_path)
    raise ImageReviewNotFoundError(
        "IMAGE_REVIEW_ASSET_NOT_FOUND",
        "The local operational review image is unavailable.",
        details={"assetKind": asset_kind},
    )


def _safe_candidate(
    artifact_root: Path, relative_path: str, *, asset_kind: str
) -> tuple[Path, Path]:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        LOGGER.warning(
            "Operational review asset path unsafe: assetKind=%s code=%s relativePath=%s",
            asset_kind,
            "IMAGE_REVIEW_ASSET_PATH_UNSAFE",
            relative_path,
        )
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_PATH_UNSAFE",
            "The stored operational review asset path is unsafe.",
            details={"assetKind": asset_kind},
        )
    managed_root = artifact_root.resolve() / "data"
    candidate = managed_root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(managed_root):
        _log_not_found(asset_kind, relative_path)
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_NOT_FOUND",
            "The local operational review image is unavailable.",
            details={"assetKind": asset_kind},
        )
    return managed_root, candidate


def _log_not_found(asset_kind: str, relative_path: str) -> None:
    LOGGER.warning(
        "Operational review asset not found: assetKind=%s code=%s relativePath=%s",
        asset_kind,
        "IMAGE_REVIEW_ASSET_NOT_FOUND",
        relative_path,
    )


def _managed_original_is_cropped(path: Path, checksum: str) -> bool:
    from game_predictor_worker.images.normalization import managed_original_is_cropped

    return managed_original_is_cropped(path, checksum)


def _source_frame_preview(
    managed_root: Path, original: Path, expected_sha256: str, *, asset_kind: str
) -> OperationalReviewAsset:
    """Full-frame JPEG of a replaced original: its crop on the fill canvas (D-562).

    Browsers keep drawing overlays in the original's natural size, so the
    served image has the original's oriented dimensions and no EXIF. It is a
    regenerable working file keyed by the crop checksum.
    """

    from game_predictor_worker.images.normalization import (
        CanonicalSourceLoader,
        CanonicalSourceLoadError,
    )
    from PIL import Image

    loader = CanonicalSourceLoader(allow_crop=True)
    try:
        frame = loader.load(original, expected_source_checksum_sha256=expected_sha256)
    except CanonicalSourceLoadError as error:
        LOGGER.warning(
            "Operational review crop unusable: assetKind=%s code=%s",
            asset_kind,
            error.code,
        )
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_NOT_FOUND",
            "The local operational review image is unavailable.",
            details={"assetKind": asset_kind, "reason": error.code},
        ) from error
    finally:
        loader.clear()
    if frame.crop is None:  # the original reappeared between the checks
        return OperationalReviewAsset(original, "image/jpeg")
    directory = managed_root / SOURCE_FRAME_PREVIEW_DIRECTORY
    # Equal crop bytes may sit in different originals or places: the canvas is
    # named by the attestation, which binds original, geometry and crop.
    preview = directory / f"{attestation_sha256(encode_attestation(frame.crop.attestation))}.jpg"
    if not preview.is_file():
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".{uuid4().hex}.part"
        Image.fromarray(frame.rgb).save(temporary, format="JPEG", quality=92)
        os.replace(temporary, preview)
    return OperationalReviewAsset(preview, "image/jpeg")


def _resolve(
    artifact_root: Path,
    relative_path: str,
    expected_sha256: str,
    *,
    asset_kind: str,
) -> OperationalReviewAsset:
    if asset_kind in _SOURCE_ASSET_KINDS:
        managed_root, original = _safe_candidate(
            artifact_root, relative_path, asset_kind=asset_kind
        )
        if not original.exists() and _managed_original_is_cropped(original, expected_sha256):
            return _source_frame_preview(
                managed_root, original, expected_sha256, asset_kind=asset_kind
            )
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        LOGGER.warning(
            "Operational review asset path unsafe: assetKind=%s code=%s relativePath=%s",
            asset_kind,
            "IMAGE_REVIEW_ASSET_PATH_UNSAFE",
            relative_path,
        )
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
        LOGGER.warning(
            "Operational review asset not found: assetKind=%s code=%s relativePath=%s",
            asset_kind,
            "IMAGE_REVIEW_ASSET_NOT_FOUND",
            relative_path,
        )
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_NOT_FOUND",
            "The local operational review image is unavailable.",
            details={"assetKind": asset_kind},
        )
    media_type, _encoding = mimetypes.guess_type(candidate.name)
    if media_type not in _IMAGE_MEDIA_TYPES:
        LOGGER.warning(
            "Operational review asset media type unsupported: "
            "assetKind=%s code=%s relativePath=%s mediaType=%s",
            asset_kind,
            "IMAGE_REVIEW_ASSET_MEDIA_TYPE_UNSUPPORTED",
            relative_path,
            media_type,
        )
        raise ImageReviewNotFoundError(
            "IMAGE_REVIEW_ASSET_MEDIA_TYPE_UNSUPPORTED",
            "The operational review asset is not a supported image.",
            details={"assetKind": asset_kind},
        )
    if _sha256(candidate) != expected_sha256:
        LOGGER.warning(
            "Operational review asset checksum drift: assetKind=%s code=%s relativePath=%s",
            asset_kind,
            "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT",
            relative_path,
        )
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
    "resolve_geometry_completeness_source_asset",
    "resolve_grid_review_source_asset",
    "resolve_grid_review_source_path",
    "resolve_managed_source_path",
    "resolve_operational_board_asset",
    "resolve_operational_cell_asset",
    "resolve_operational_source_asset",
    "resolve_pending_board_cell_source_asset",
]
