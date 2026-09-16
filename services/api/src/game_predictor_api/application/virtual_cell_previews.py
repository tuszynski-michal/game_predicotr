"""Bounded, regenerable preview atlases for virtual source-backed symbol cells."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID

import numpy as np
from game_predictor_worker.images.normalization import (
    RGB_PIXEL_CHECKSUM_VERSION,
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_RENDER_SPEC_VERSION,
    VirtualCellExtractionError,
    source_direct_warp_rgb,
)
from PIL import Image

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAsset,
    SymbolCellReviewError,
)

VIRTUAL_CELL_PREVIEW_CACHE_VERSION = "virtual-cell-preview-cache-v1"
VIRTUAL_CELL_PREVIEW_EXTRACTION_MODE = "direct_perspective_cell_v1"
CURRENT_SYMBOL_CELL_PREVIEW_RENDERER_VERSION = "symbol-review-current-crop-renderer-v2-edge-to-edge"
STRUCTURED_V0_10_PREVIEW_RENDERER_VERSION = "symbol-review-structured-v0.10-renderer-v1"
SymbolCellPreviewRendererMode = Literal["current", "structured_v0_10"]
MAX_VIRTUAL_CELL_PREVIEW_BATCH_SIZE = 100
DEFAULT_VIRTUAL_CELL_PREVIEW_SIZE = 100
MAX_VIRTUAL_CELL_PREVIEW_SIZE = 256
MIN_VIRTUAL_CELL_PREVIEW_SIZE = 32
DEFAULT_VIRTUAL_CELL_PREVIEW_TTL = timedelta(hours=24)
DEFAULT_VIRTUAL_CELL_PREVIEW_CACHE_BYTES = 2 * 1024 * 1024 * 1024
_CACHE_KEY_LENGTH = 64


@dataclass(frozen=True, slots=True)
class VirtualCellPreviewTarget:
    """One caller-observed virtual cell identity, without pixel bytes."""

    cell_review_id: UUID
    expected_revision: int
    expected_render_spec_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.expected_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_REVISION_INVALID",
                "A virtual preview requires a non-negative expected cell revision.",
            )
        _require_sha256(
            self.expected_render_spec_checksum_sha256,
            code="SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
            message="A virtual preview requires a lowercase render-spec SHA-256 checksum.",
        )


@dataclass(frozen=True, slots=True)
class SymbolCellPreviewTarget:
    """One current cell identity for a shared legacy/virtual preview atlas."""

    cell_review_id: UUID
    expected_revision: int
    expected_crop_checksum_sha256: str
    expected_render_spec_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.expected_revision < 0:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_REVISION_INVALID",
                "A symbol preview requires a non-negative expected cell revision.",
            )
        _require_sha256(
            self.expected_crop_checksum_sha256,
            code="SYMBOL_CELL_REVIEW_PREVIEW_CROP_INVALID",
            message="A symbol preview requires a lowercase crop SHA-256 checksum.",
        )
        if self.expected_render_spec_checksum_sha256 is not None:
            _require_sha256(
                self.expected_render_spec_checksum_sha256,
                code="SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
                message="A symbol preview render-spec checksum is invalid.",
            )


@dataclass(frozen=True, slots=True)
class VirtualCellPreviewTile:
    cell_review_id: UUID
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class VirtualCellPreviewBatch:
    """Descriptor for a cached atlas; the atlas remains derived cache data."""

    game_id: UUID
    batch_key: str
    atlas_checksum_sha256: str
    tiles: tuple[VirtualCellPreviewTile, ...]
    expires_at: datetime
    renderer_mode: SymbolCellPreviewRendererMode
    renderer_version: str
    renderer_fingerprint_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(
            self.batch_key,
            code="SYMBOL_CELL_REVIEW_PREVIEW_BATCH_INVALID",
            message="A virtual preview batch key is invalid.",
        )
        _require_sha256(
            self.atlas_checksum_sha256,
            code="SYMBOL_CELL_REVIEW_PREVIEW_ATLAS_INVALID",
            message="A virtual preview atlas checksum is invalid.",
        )
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        _require_sha256(
            self.renderer_fingerprint_sha256,
            code="SYMBOL_CELL_REVIEW_PREVIEW_RENDERER_INVALID",
            message="A symbol preview renderer fingerprint is invalid.",
        )


@dataclass(frozen=True, slots=True)
class _CachedAtlas:
    batch: VirtualCellPreviewBatch
    content: bytes


class VirtualCellPreviewService:
    """Render and cache small virtual-cell previews without persistent crop artifacts.

    The filesystem cache is deliberately a disposable implementation detail:
    domain records store only source-space provenance and can reproduce every
    byte after this cache has been removed by storage GC.
    """

    def __init__(
        self,
        artifact_root: Path,
        *,
        cache_ttl: timedelta = DEFAULT_VIRTUAL_CELL_PREVIEW_TTL,
        max_cache_bytes: int = DEFAULT_VIRTUAL_CELL_PREVIEW_CACHE_BYTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if cache_ttl <= timedelta(0):
            raise ValueError("cache_ttl must be positive")
        if max_cache_bytes < 1:
            raise ValueError("max_cache_bytes must be positive")
        self._artifact_root = artifact_root.resolve()
        self._cache_root = (
            self._artifact_root / "data" / "working" / VIRTUAL_CELL_PREVIEW_CACHE_VERSION
        )
        self._cache_ttl = cache_ttl
        self._max_cache_bytes = max_cache_bytes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._flights: dict[str, _PreviewFlight] = {}
        self._cache_bytes = self._measure_cache_bytes()

    def render_batch(
        self,
        *,
        game_id: UUID,
        assets: Sequence[SymbolCellReviewAsset],
        preview_size: int = DEFAULT_VIRTUAL_CELL_PREVIEW_SIZE,
        renderer_mode: SymbolCellPreviewRendererMode = "current",
    ) -> VirtualCellPreviewBatch:
        """Return one checksum-bound atlas after validating current virtual provenance."""

        if not assets or len(assets) > MAX_VIRTUAL_CELL_PREVIEW_BATCH_SIZE:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_LIMIT",
                "A virtual preview batch must contain from one to 100 symbol cells.",
            )
        if not MIN_VIRTUAL_CELL_PREVIEW_SIZE <= preview_size <= MAX_VIRTUAL_CELL_PREVIEW_SIZE:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_SIZE_INVALID",
                "previewSize must be between 32 and 256 pixels.",
            )
        cell_ids = tuple(asset.cell_review_id for asset in assets)
        if len(set(cell_ids)) != len(cell_ids):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_DUPLICATE_CELL",
                "A virtual preview batch cannot contain the same cell more than once.",
            )
        renderer_version = symbol_cell_preview_renderer_version(renderer_mode)
        renderer_fingerprint = symbol_cell_preview_renderer_fingerprint(renderer_mode)
        if renderer_mode == "structured_v0_10" and any(
            asset.asset_mode != "virtual_source" for asset in assets
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_PROVENANCE_UNAVAILABLE",
                "The experimental v0.10 preview requires structured source provenance.",
            )
        key = _batch_key(
            game_id=game_id,
            assets=assets,
            preview_size=preview_size,
            renderer_mode=renderer_mode,
            renderer_version=renderer_version,
        )
        cached = self._read_cached(key=key, game_id=game_id, now=self._clock())
        if cached is not None:
            return cached.batch

        flight, owner = self._acquire_flight(key)
        if not owner:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            cached = self._read_cached(key=key, game_id=game_id, now=self._clock())
            if cached is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_PREVIEW_CACHE_UNAVAILABLE",
                    "The concurrent virtual preview result is unavailable.",
                )
            return cached.batch

        try:
            cached = self._read_cached(key=key, game_id=game_id, now=self._clock())
            if cached is not None:
                flight.result = cached.batch
                return cached.batch
            rendered = self._render_atlas(
                game_id=game_id,
                batch_key=key,
                assets=assets,
                preview_size=preview_size,
                now=self._clock(),
                renderer_mode=renderer_mode,
                renderer_version=renderer_version,
                renderer_fingerprint_sha256=renderer_fingerprint,
            )
            self._write_cached(rendered)
            if self._cache_bytes > self._max_cache_bytes:
                self._cache_bytes = self._prune(now=self._clock())
            flight.result = rendered.batch
            return rendered.batch
        except SymbolCellReviewError as error:
            flight.error = error
            raise
        finally:
            self._release_flight(key, flight)

    def read_atlas(self, *, game_id: UUID, batch_key: str) -> _CachedAtlas:
        """Read a non-expired cached atlas, validating its bytes every time."""

        _require_sha256(
            batch_key,
            code="SYMBOL_CELL_REVIEW_PREVIEW_BATCH_INVALID",
            message="The virtual preview batch key is invalid.",
        )
        cached = self._read_cached(key=batch_key, game_id=game_id, now=self._clock())
        if cached is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_NOT_FOUND",
                "The virtual preview batch expired or is unavailable. Request it again.",
            )
        return cached

    def _render_atlas(
        self,
        *,
        game_id: UUID,
        batch_key: str,
        assets: Sequence[SymbolCellReviewAsset],
        preview_size: int,
        now: datetime,
        renderer_mode: SymbolCellPreviewRendererMode,
        renderer_version: str,
        renderer_fingerprint_sha256: str,
    ) -> _CachedAtlas:
        loader = CanonicalSourceLoader()
        frames: dict[str, object] = {}
        descriptors: list[VirtualCellPreviewTile] = []
        columns = min(10, len(assets))
        rows = (len(assets) + columns - 1) // columns
        atlas = Image.new("RGB", (columns * preview_size, rows * preview_size), color=(0, 0, 0))
        try:
            for index, asset in enumerate(assets):
                if asset.asset_mode == "virtual_source":
                    frame = frames.get(asset.source_checksum_sha256 or "")
                    if frame is None:
                        source_path = _managed_virtual_source_path(self._artifact_root, asset)
                        frame = loader.load(
                            source_path,
                            expected_source_checksum_sha256=_required(asset.source_checksum_sha256),
                        )
                        frames[_required(asset.source_checksum_sha256)] = frame
                    preview = _render_virtual_preview(
                        asset=asset,
                        frame=frame,
                        preview_size=preview_size,
                    )
                else:
                    preview = self._render_legacy_preview(
                        asset=asset,
                        preview_size=preview_size,
                    )
                x = (index % columns) * preview_size
                y = (index // columns) * preview_size
                atlas.paste(preview, (x, y))
                descriptors.append(
                    VirtualCellPreviewTile(
                        cell_review_id=asset.cell_review_id,
                        x=x,
                        y=y,
                        width=preview.width,
                        height=preview.height,
                    )
                )
        except (CanonicalSourceLoadError, VirtualCellExtractionError) as error:
            raise SymbolCellReviewError(
                getattr(error, "code", "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_FAILED"),
                str(error),
            ) from error
        finally:
            loader.clear()

        output = BytesIO()
        atlas.save(output, format="WEBP", quality=82, method=4)
        content = output.getvalue()
        expires_at = now + self._cache_ttl
        return _CachedAtlas(
            batch=VirtualCellPreviewBatch(
                game_id=game_id,
                batch_key=batch_key,
                atlas_checksum_sha256=hashlib.sha256(content).hexdigest(),
                tiles=tuple(descriptors),
                expires_at=expires_at,
                renderer_mode=renderer_mode,
                renderer_version=renderer_version,
                renderer_fingerprint_sha256=renderer_fingerprint_sha256,
            ),
            content=content,
        )

    def _render_legacy_preview(
        self,
        *,
        asset: SymbolCellReviewAsset,
        preview_size: int,
    ) -> Image.Image:
        relative_value = _required(asset.crop_relative_path)
        relative = Path(relative_value.replace("/", os.sep))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_INVALID",
                "The symbol-cell crop path is unsafe.",
            )
        data_root = (self._artifact_root / "data").resolve()
        candidates = [(self._artifact_root / relative).resolve()]
        if relative.parts[0] != "data":
            candidates.append((data_root / relative).resolve())
        path = next(
            (
                candidate
                for candidate in candidates
                if candidate.is_relative_to(data_root)
                and candidate.is_file()
                and not candidate.is_symlink()
            ),
            None,
        )
        if path is None:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_NOT_FOUND",
                "The current symbol-cell crop is unavailable.",
            )
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != asset.crop_checksum_sha256:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH",
                "The current symbol-cell crop bytes do not match their checksum.",
            )
        try:
            with Image.open(BytesIO(content)) as source:
                image = source.convert("RGB")
                # Atlas tiles have a fixed square viewport.  Resizing the current crop
                # directly keeps the complete symbol visible while avoiding the black
                # letterbox that the legacy ``thumbnail`` canvas added around it.
                return image.resize(
                    (preview_size, preview_size),
                    Image.Resampling.LANCZOS,
                )
        except OSError as error:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_ASSET_INVALID",
                "The current symbol-cell crop cannot be rendered as a thumbnail.",
            ) from error

    def _read_cached(
        self,
        *,
        key: str,
        game_id: UUID,
        now: datetime,
        touch: bool = True,
    ) -> _CachedAtlas | None:
        if self._cache_root.exists() and self._cache_root.is_symlink():
            return None
        descriptor_path, atlas_path = self._cache_paths(key)
        if not descriptor_path.is_file() or not atlas_path.is_file():
            return None
        if descriptor_path.is_symlink() or atlas_path.is_symlink():
            return None
        try:
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            content = atlas_path.read_bytes()
            cached = _cached_atlas_from_descriptor(descriptor, content)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            self._remove_cache_pair(descriptor_path, atlas_path)
            return None
        if cached.batch.game_id != game_id:
            return None
        if cached.batch.expires_at <= now:
            self._remove_cache_pair(descriptor_path, atlas_path)
            return None
        if touch:
            try:
                os.utime(descriptor_path, None)
                os.utime(atlas_path, None)
            except OSError:
                pass
        return cached

    def _write_cached(self, cached: _CachedAtlas) -> None:
        descriptor_path, atlas_path = self._cache_paths(cached.batch.batch_key)
        if self._cache_root.exists() and self._cache_root.is_symlink():
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_CACHE_UNSAFE",
                "The virtual preview cache path must not be a symbolic link.",
            )
        self._cache_root.mkdir(parents=True, exist_ok=True)
        _atomic_write(atlas_path, cached.content)
        descriptor = {
            "atlasChecksumSha256": cached.batch.atlas_checksum_sha256,
            "batchKey": cached.batch.batch_key,
            "expiresAt": cached.batch.expires_at.isoformat(),
            "gameId": str(cached.batch.game_id),
            "rendererFingerprintSha256": cached.batch.renderer_fingerprint_sha256,
            "rendererMode": cached.batch.renderer_mode,
            "rendererVersion": cached.batch.renderer_version,
            "tiles": [
                {
                    "cellReviewId": str(tile.cell_review_id),
                    "height": tile.height,
                    "width": tile.width,
                    "x": tile.x,
                    "y": tile.y,
                }
                for tile in cached.batch.tiles
            ],
        }
        descriptor_content = canonical_json_bytes(descriptor)
        _atomic_write(descriptor_path, descriptor_content)
        self._cache_bytes += len(cached.content) + len(descriptor_content)

    def _prune(self, *, now: datetime) -> int:
        if not self._cache_root.exists() or self._cache_root.is_symlink():
            return 0
        entries: list[tuple[float, int, Path, Path]] = []
        total = 0
        for descriptor_path in self._cache_root.glob("*.json"):
            if descriptor_path.is_symlink() or not descriptor_path.is_file():
                continue
            key = descriptor_path.stem
            if len(key) != _CACHE_KEY_LENGTH or any(char not in "0123456789abcdef" for char in key):
                continue
            atlas_path = self._cache_root / f"{key}.webp"
            try:
                game_id = _descriptor_game_id(descriptor_path)
            except ValueError:
                self._remove_cache_pair(descriptor_path, atlas_path)
                continue
            cached = self._read_cached(
                key=key,
                game_id=game_id,
                now=now,
                touch=False,
            )
            if cached is None:
                continue
            try:
                descriptor_stat = descriptor_path.stat()
                atlas_stat = atlas_path.stat()
                size = descriptor_stat.st_size + atlas_stat.st_size
                entries.append(
                    (
                        max(descriptor_stat.st_mtime, atlas_stat.st_mtime),
                        size,
                        descriptor_path,
                        atlas_path,
                    )
                )
                total += size
            except OSError:
                self._remove_cache_pair(descriptor_path, atlas_path)
        for _accessed, size, descriptor_path, atlas_path in sorted(entries):
            if total <= self._max_cache_bytes:
                break
            self._remove_cache_pair(descriptor_path, atlas_path)
            total -= size
        return total

    def _measure_cache_bytes(self) -> int:
        if not self._cache_root.exists() or self._cache_root.is_symlink():
            return 0
        total = 0
        for path in self._cache_root.iterdir():
            try:
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def _cache_paths(self, key: str) -> tuple[Path, Path]:
        return self._cache_root / f"{key}.json", self._cache_root / f"{key}.webp"

    @staticmethod
    def _remove_cache_pair(descriptor_path: Path, atlas_path: Path) -> None:
        for path in (descriptor_path, atlas_path):
            try:
                if path.exists() and not path.is_symlink():
                    path.unlink()
            except OSError:
                pass

    def _acquire_flight(self, key: str) -> tuple[_PreviewFlight, bool]:
        with self._lock:
            flight = self._flights.get(key)
            if flight is not None:
                return flight, False
            flight = _PreviewFlight(event=threading.Event())
            self._flights[key] = flight
            return flight, True

    def _release_flight(self, key: str, flight: _PreviewFlight) -> None:
        with self._lock:
            self._flights.pop(key, None)
            flight.event.set()


@dataclass(slots=True)
class _PreviewFlight:
    event: threading.Event
    result: VirtualCellPreviewBatch | None = None
    error: SymbolCellReviewError | None = None


def _render_virtual_preview(
    *,
    asset: SymbolCellReviewAsset,
    frame: object,
    preview_size: int,
) -> Image.Image:
    """Verify the persisted render contract before reducing it to preview pixels."""

    from game_predictor_worker.images.normalization import CanonicalSourceFrame

    if not isinstance(frame, CanonicalSourceFrame):
        raise TypeError("frame must be a CanonicalSourceFrame")
    image = _render_virtual_cell_image(asset=asset, frame=frame)
    return image.resize((preview_size, preview_size), Image.Resampling.LANCZOS)


def render_virtual_symbol_cell_png(*, artifact_root: Path, asset: SymbolCellReviewAsset) -> bytes:
    """Render one current virtual crop at its canonical size into durable PNG bytes.

    Preview atlases intentionally downsample and expire.  A selected catalog
    reference must instead freeze the exact source-direct cell pixels once,
    after all persisted source and render-provenance checks have passed.
    """

    if asset.asset_mode != "virtual_source":
        raise SymbolCellReviewError(
            "SYMBOL_REFERENCE_VIRTUAL_ASSET_INVALID",
            "Only a virtual symbol-cell asset can be materialized as a virtual reference.",
        )
    loader = CanonicalSourceLoader()
    try:
        frame = loader.load(
            _managed_virtual_source_path(artifact_root.resolve(), asset),
            expected_source_checksum_sha256=_required(asset.source_checksum_sha256),
        )
        image = _render_virtual_cell_image(asset=asset, frame=frame)
        output = BytesIO()
        image.save(output, format="PNG", optimize=False, compress_level=9)
        return output.getvalue()
    except (CanonicalSourceLoadError, VirtualCellExtractionError) as error:
        raise SymbolCellReviewError(
            getattr(error, "code", "SYMBOL_REFERENCE_VIRTUAL_RENDER_FAILED"),
            str(error),
        ) from error
    finally:
        loader.clear()


def _render_virtual_cell_image(*, asset: SymbolCellReviewAsset, frame: object) -> Image.Image:
    """Return full-resolution source-direct cell pixels after contract validation."""

    from game_predictor_worker.images.normalization import CanonicalSourceFrame

    if not isinstance(frame, CanonicalSourceFrame):
        raise TypeError("frame must be a CanonicalSourceFrame")
    spec = dict(_required(asset.render_spec))
    _require_virtual_asset_contract(asset=asset, frame=frame, render_spec=spec)
    configuration = _mapping(spec.get("configuration"), "configuration")
    width = _positive_int(configuration.get("outputWidth"), "outputWidth")
    height = _positive_int(configuration.get("outputHeight"), "outputHeight")
    rgb = source_direct_warp_rgb(
        frame.rgb,
        source_quad=_quad(spec.get("paddedSourceQuad")),
        output_width=width,
        output_height=height,
    )
    if rgb_pixel_checksum_sha256(rgb) != _required(asset.rendered_pixel_checksum_sha256):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_PIXEL_CHECKSUM_MISMATCH",
            "The virtual preview pixels differ from the current rendered-cell checksum.",
        )
    return Image.fromarray(np.asarray(rgb), mode="RGB")


def _managed_virtual_source_path(artifact_root: Path, asset: SymbolCellReviewAsset) -> Path:
    checksum = _required(asset.source_checksum_sha256)
    relative = Path("data") / "originals" / checksum[:2] / f"{checksum}.jpg"
    candidate = (artifact_root / relative).resolve()
    data_root = (artifact_root / "data").resolve()
    if not candidate.is_relative_to(data_root) or not candidate.is_file() or candidate.is_symlink():
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_SOURCE_UNAVAILABLE",
            "The managed source image for this virtual symbol-cell preview is unavailable.",
        )
    return candidate


def _require_virtual_asset_contract(
    *,
    asset: SymbolCellReviewAsset,
    frame: object,
    render_spec: Mapping[str, object],
) -> None:
    from game_predictor_worker.images.normalization import CanonicalSourceFrame

    if not isinstance(frame, CanonicalSourceFrame):
        raise TypeError("frame must be a CanonicalSourceFrame")
    if asset.geometry_revision != asset.current_geometry_revision:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CROP_DRIFT",
            "The symbol-cell crop no longer belongs to the current geometry revision.",
        )
    if asset.source_geometry_revision_id != asset.current_source_geometry_revision_id:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_CROP_DRIFT",
            "The virtual cell no longer belongs to the current source geometry revision.",
        )
    if hashlib.sha256(canonical_json_bytes(render_spec)).hexdigest() != _required(
        asset.render_spec_checksum_sha256
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_DRIFT",
            "The stored virtual render specification does not match its checksum.",
        )
    checks = {
        "sourceChecksumSha256": asset.source_checksum_sha256,
        "logicalCellKeySha256": asset.logical_cell_key,
    }
    for field, expected in checks.items():
        if render_spec.get(field) != expected:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_DRIFT",
                "The virtual render specification no longer matches current cell provenance.",
            )
    if render_spec.get("schemaVersion") == VIRTUAL_CELL_RENDER_SPEC_VERSION and (
        render_spec.get("normalizedPixelChecksumSha256") != asset.normalized_pixel_checksum_sha256
        or render_spec.get("pixelChecksumVersion") != RGB_PIXEL_CHECKSUM_VERSION
    ):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_DRIFT",
            "The virtual render specification no longer matches normalized-pixel provenance.",
        )
    if frame.source.source_checksum_sha256 != asset.source_checksum_sha256:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_SOURCE_DRIFT",
            "The managed source checksum changed before the virtual preview was rendered.",
        )
    if frame.source.normalized_pixel_checksum_sha256 != asset.normalized_pixel_checksum_sha256:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_SOURCE_DRIFT",
            "The managed source pixels changed before the virtual preview was rendered.",
        )


def _batch_key(
    *,
    game_id: UUID,
    assets: Sequence[SymbolCellReviewAsset],
    preview_size: int,
    renderer_mode: SymbolCellPreviewRendererMode,
    renderer_version: str,
) -> str:
    payload = {
        "cacheVersion": VIRTUAL_CELL_PREVIEW_CACHE_VERSION,
        "extractionMode": VIRTUAL_CELL_PREVIEW_EXTRACTION_MODE,
        "gameId": str(game_id),
        "previewSize": preview_size,
        "rendererMode": renderer_mode,
        "rendererVersion": renderer_version,
        "cells": [
            {
                "cellReviewId": str(asset.cell_review_id),
                "assetMode": asset.asset_mode,
                "cellRevision": asset.revision,
                "cropChecksumSha256": asset.crop_checksum_sha256,
                "geometryRevision": asset.geometry_revision,
                "geometryChecksumSha256": asset.geometry_checksum_sha256,
                "logicalCellKeySha256": asset.logical_cell_key,
                "renderSpecChecksumSha256": asset.render_spec_checksum_sha256,
                "renderedPixelChecksumSha256": asset.rendered_pixel_checksum_sha256,
                "sourceChecksumSha256": asset.source_checksum_sha256,
                "sourceGeometryRevisionId": str(asset.source_geometry_revision_id),
            }
            for asset in assets
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _cached_atlas_from_descriptor(
    descriptor: object,
    content: bytes,
) -> _CachedAtlas:
    values = _mapping(descriptor, "descriptor")
    checksum = _text(values.get("atlasChecksumSha256"), "atlasChecksumSha256")
    _require_sha256(
        checksum,
        code="SYMBOL_CELL_REVIEW_PREVIEW_ATLAS_INVALID",
        message="The cached virtual preview atlas checksum is invalid.",
    )
    if hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("atlas checksum mismatch")
    expires_at = datetime.fromisoformat(_text(values.get("expiresAt"), "expiresAt"))
    if expires_at.tzinfo is None:
        raise ValueError("expiresAt must include timezone")
    tiles_value = values.get("tiles")
    if not isinstance(tiles_value, list):
        raise ValueError("tiles must be an array")
    return _CachedAtlas(
        batch=VirtualCellPreviewBatch(
            game_id=UUID(_text(values.get("gameId"), "gameId")),
            batch_key=_text(values.get("batchKey"), "batchKey"),
            atlas_checksum_sha256=checksum,
            tiles=tuple(
                VirtualCellPreviewTile(
                    cell_review_id=UUID(
                        _text(_mapping(tile, "tile").get("cellReviewId"), "cellReviewId")
                    ),
                    x=_positive_or_zero(_mapping(tile, "tile").get("x"), "x"),
                    y=_positive_or_zero(_mapping(tile, "tile").get("y"), "y"),
                    width=_positive_int(_mapping(tile, "tile").get("width"), "width"),
                    height=_positive_int(_mapping(tile, "tile").get("height"), "height"),
                )
                for tile in tiles_value
            ),
            expires_at=expires_at,
            renderer_mode=_renderer_mode(values.get("rendererMode")),
            renderer_version=_text(values.get("rendererVersion"), "rendererVersion"),
            renderer_fingerprint_sha256=_text(
                values.get("rendererFingerprintSha256"),
                "rendererFingerprintSha256",
            ),
        ),
        content=content,
    )


def _descriptor_game_id(descriptor_path: Path) -> UUID:
    try:
        value = json.loads(descriptor_path.read_text(encoding="utf-8"))
        return UUID(_text(_mapping(value, "descriptor").get("gameId"), "gameId"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("cached virtual preview descriptor is invalid") from error


def symbol_cell_preview_renderer_version(mode: SymbolCellPreviewRendererMode) -> str:
    if mode == "current":
        return CURRENT_SYMBOL_CELL_PREVIEW_RENDERER_VERSION
    if mode == "structured_v0_10":
        return STRUCTURED_V0_10_PREVIEW_RENDERER_VERSION
    raise SymbolCellReviewError(
        "SYMBOL_CELL_REVIEW_PREVIEW_RENDERER_INVALID",
        "The requested symbol preview renderer is unsupported.",
    )


def symbol_cell_preview_renderer_fingerprint(mode: SymbolCellPreviewRendererMode) -> str:
    payload = {
        "cacheVersion": VIRTUAL_CELL_PREVIEW_CACHE_VERSION,
        "extractionMode": VIRTUAL_CELL_PREVIEW_EXTRACTION_MODE,
        "renderSpecVersion": VIRTUAL_CELL_RENDER_SPEC_VERSION,
        "rendererMode": mode,
        "rendererVersion": symbol_cell_preview_renderer_version(mode),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _renderer_mode(value: object) -> SymbolCellPreviewRendererMode:
    if value == "current":
        return "current"
    if value == "structured_v0_10":
        return "structured_v0_10"
    raise ValueError("rendererMode is invalid")


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _require_sha256(value: str, *, code: str, message: str) -> None:
    if len(value) != _CACHE_KEY_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise SymbolCellReviewError(code, message)


def _required[T](value: T | None) -> T:
    if value is None:
        raise ValueError("required virtual-preview provenance is missing")
    return value


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
            f"The virtual preview {name} must be an object.",
        )
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
            f"The virtual preview {name} must be a positive integer.",
        )
    return value


def _positive_or_zero(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _quad(value: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
            "The virtual preview paddedSourceQuad must contain four points.",
        )
    points: list[tuple[float, float]] = []
    for point in value:
        mapped = _mapping(point, "paddedSourceQuad point")
        x, y = mapped.get("x"), mapped.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int | float)
            or not isinstance(y, int | float)
        ):
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_INVALID",
                "The virtual preview paddedSourceQuad contains an invalid point.",
            )
        points.append((float(x), float(y)))
    return tuple(points)


__all__ = [
    "DEFAULT_VIRTUAL_CELL_PREVIEW_CACHE_BYTES",
    "DEFAULT_VIRTUAL_CELL_PREVIEW_SIZE",
    "DEFAULT_VIRTUAL_CELL_PREVIEW_TTL",
    "MAX_VIRTUAL_CELL_PREVIEW_BATCH_SIZE",
    "SymbolCellPreviewTarget",
    "SymbolCellPreviewRendererMode",
    "render_virtual_symbol_cell_png",
    "symbol_cell_preview_renderer_fingerprint",
    "symbol_cell_preview_renderer_version",
    "VirtualCellPreviewBatch",
    "VirtualCellPreviewService",
    "VirtualCellPreviewTarget",
    "VirtualCellPreviewTile",
]
