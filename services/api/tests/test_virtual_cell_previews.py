from __future__ import annotations

import hashlib
import threading
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.application.virtual_cell_previews import VirtualCellPreviewService
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAsset,
    SymbolCellReviewError,
)
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb
from PIL import Image


def _asset(artifact_root: Path, *, revision: int = 3) -> SymbolCellReviewAsset:
    source = Image.new("RGB", (240, 180), color=(120, 30, 20))
    for x in range(40, 200):
        for y in range(30, 150):
            source.putpixel((x, y), ((x * 7) % 255, (y * 9) % 255, (x + y) % 255))
    buffer = BytesIO()
    source.save(buffer, format="JPEG", quality=95)
    content = buffer.getvalue()
    source_checksum = hashlib.sha256(content).hexdigest()
    path = artifact_root / "data" / "originals" / source_checksum[:2] / f"{source_checksum}.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    loader = CanonicalSourceLoader()
    frame = loader.load(path, expected_source_checksum_sha256=source_checksum)
    padded_quad = [
        {"x": 40.0, "y": 30.0},
        {"x": 199.0, "y": 30.0},
        {"x": 199.0, "y": 149.0},
        {"x": 40.0, "y": 149.0},
    ]
    rgb = source_direct_warp_rgb(
        frame.rgb,
        source_quad=tuple((point["x"], point["y"]) for point in padded_quad),
        output_width=64,
        output_height=64,
    )
    rendered_checksum = rgb_pixel_checksum_sha256(rgb)
    render_spec = {
        "boardSlot": 0,
        "cellIndex": 0,
        "columnIndex": 0,
        "configuration": {
            "extractorVersion": "direct-perspective-cell-v1",
            "interpolation": "opencv-inter-linear-v1",
            "outputHeight": 64,
            "outputWidth": 64,
            "paddingFraction": 0.04,
            "preprocessingVersion": "preview-test-v1",
        },
        "coordinateSpace": "exif-normalized-rgb-pixels-v1",
        "geometryFingerprintSha256": "a" * 64,
        "geometryRevision": 2,
        "logicalCellKeySha256": "b" * 64,
        "paddedSourceQuad": padded_quad,
        "renderIdentitySha256": "c" * 64,
        "rowIndex": 0,
        "schemaVersion": "virtual-cell-render-spec-v1",
        "sourceChecksumSha256": source_checksum,
        "sourceQuad": padded_quad,
    }
    source_geometry_revision_id = uuid4()
    return SymbolCellReviewAsset(
        cell_review_id=uuid4(),
        crop_relative_path=None,
        crop_checksum_sha256=rendered_checksum,
        geometry_revision=2,
        current_geometry_revision=2,
        revision=revision,
        asset_mode="virtual_source",
        source_checksum_sha256=source_checksum,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        source_geometry_revision_id=source_geometry_revision_id,
        current_source_geometry_revision_id=source_geometry_revision_id,
        geometry_checksum_sha256="d" * 64,
        logical_cell_key="b" * 64,
        render_spec=render_spec,
        render_spec_checksum_sha256=hashlib.sha256(canonical_json_bytes(render_spec)).hexdigest(),
        rendered_pixel_checksum_sha256=rendered_checksum,
        extractor_version="direct-perspective-cell-v1",
    )


def _current_asset(artifact_root: Path, *, revision: int = 3) -> SymbolCellReviewAsset:
    return _asset(artifact_root, revision=revision)


def _legacy_asset(artifact_root: Path, *, revision: int = 3) -> SymbolCellReviewAsset:
    path = artifact_root / "data" / "crops" / f"legacy-{revision}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), color=(25, 140, 210)).save(path, format="PNG")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return SymbolCellReviewAsset(
        cell_review_id=uuid4(),
        crop_relative_path=path.relative_to(artifact_root).as_posix(),
        crop_checksum_sha256=checksum,
        geometry_revision=2,
        current_geometry_revision=2,
        revision=revision,
    )


def test_virtual_preview_atlas_is_checksum_bound_and_tiled(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    service = VirtualCellPreviewService(tmp_path)

    batch = service.render_batch(game_id=uuid4(), assets=(asset,), preview_size=100)
    cached = service.read_atlas(game_id=batch.game_id, batch_key=batch.batch_key)

    assert hashlib.sha256(cached.content).hexdigest() == batch.atlas_checksum_sha256
    assert cached.batch.tiles[0].cell_review_id == asset.cell_review_id
    with Image.open(BytesIO(cached.content)) as atlas:
        assert atlas.size == (100, 100)


def test_shared_preview_atlas_contains_legacy_and_virtual_cells(tmp_path: Path) -> None:
    legacy = _legacy_asset(tmp_path)
    virtual = _current_asset(tmp_path)
    service = VirtualCellPreviewService(tmp_path)
    game_id = uuid4()

    first = service.render_batch(
        game_id=game_id,
        assets=(legacy, virtual),
        preview_size=100,
    )
    second = service.render_batch(
        game_id=game_id,
        assets=(legacy, virtual),
        preview_size=100,
    )
    cached = service.read_atlas(game_id=game_id, batch_key=first.batch_key)

    assert first.batch_key == second.batch_key
    assert [tile.cell_review_id for tile in first.tiles] == [
        legacy.cell_review_id,
        virtual.cell_review_id,
    ]
    with Image.open(BytesIO(cached.content)) as atlas:
        assert atlas.size == (200, 100)


def test_structured_v0_10_renderer_has_an_independent_cache_identity(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    service = VirtualCellPreviewService(tmp_path)
    game_id = uuid4()

    current = service.render_batch(game_id=game_id, assets=(asset,))
    experimental = service.render_batch(
        game_id=game_id,
        assets=(asset,),
        renderer_mode="structured_v0_10",
    )

    assert current.batch_key != experimental.batch_key
    assert current.renderer_mode == "current"
    assert experimental.renderer_mode == "structured_v0_10"
    assert current.renderer_fingerprint_sha256 != experimental.renderer_fingerprint_sha256


def test_structured_v0_10_renderer_rejects_legacy_pixels(tmp_path: Path) -> None:
    legacy = _legacy_asset(tmp_path)

    with pytest.raises(SymbolCellReviewError) as unavailable:
        VirtualCellPreviewService(tmp_path).render_batch(
            game_id=uuid4(),
            assets=(legacy,),
            renderer_mode="structured_v0_10",
        )

    assert unavailable.value.code == "SYMBOL_CELL_REVIEW_PREVIEW_PROVENANCE_UNAVAILABLE"


def test_preview_cache_prunes_only_after_crossing_the_size_limit(tmp_path: Path) -> None:
    asset = _legacy_asset(tmp_path)

    class CountingPruneService(VirtualCellPreviewService):
        prune_calls = 0

        def _prune(self, **kwargs: object) -> int:  # type: ignore[no-untyped-def]
            type(self).prune_calls += 1
            return super()._prune(**kwargs)  # type: ignore[arg-type]

    service = CountingPruneService(tmp_path, max_cache_bytes=10_000_000)

    service.render_batch(game_id=uuid4(), assets=(asset,))

    assert CountingPruneService.prune_calls == 0


def test_virtual_preview_keeps_render_spec_and_pixel_checksums_independent(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)

    assert asset.render_spec is not None
    assert "renderedPixelChecksumSha256" not in asset.render_spec
    batch = VirtualCellPreviewService(tmp_path).render_batch(
        game_id=uuid4(), assets=(asset,), preview_size=100
    )

    assert batch.tiles[0].cell_review_id == asset.cell_review_id
    assert len(batch.atlas_checksum_sha256) == 64


def test_virtual_preview_rejects_stale_geometry_before_cache_write(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    stale = SymbolCellReviewAsset(
        cell_review_id=asset.cell_review_id,
        crop_relative_path=None,
        crop_checksum_sha256=asset.crop_checksum_sha256,
        geometry_revision=1,
        current_geometry_revision=2,
        revision=asset.revision,
        asset_mode="virtual_source",
        source_checksum_sha256=asset.source_checksum_sha256,
        normalized_pixel_checksum_sha256=asset.normalized_pixel_checksum_sha256,
        source_geometry_revision_id=asset.source_geometry_revision_id,
        current_source_geometry_revision_id=asset.source_geometry_revision_id,
        geometry_checksum_sha256=asset.geometry_checksum_sha256,
        logical_cell_key=asset.logical_cell_key,
        render_spec=asset.render_spec,
        render_spec_checksum_sha256=asset.render_spec_checksum_sha256,
        rendered_pixel_checksum_sha256=asset.rendered_pixel_checksum_sha256,
        extractor_version=asset.extractor_version,
    )

    with pytest.raises(SymbolCellReviewError, match="current geometry") as error:
        VirtualCellPreviewService(tmp_path).render_batch(game_id=uuid4(), assets=(stale,))

    assert error.value.code == "SYMBOL_CELL_REVIEW_CROP_DRIFT"


def test_virtual_preview_single_flight_renders_one_concurrent_batch(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)

    class CountingPreviewService(VirtualCellPreviewService):
        calls = 0
        calls_lock = threading.Lock()

        def _render_atlas(self, **kwargs: object):  # type: ignore[no-untyped-def]
            with self.calls_lock:
                type(self).calls += 1
            time.sleep(0.05)
            return super()._render_atlas(**kwargs)  # type: ignore[arg-type,no-any-return]

    service = CountingPreviewService(tmp_path)
    game_id = uuid4()
    batches: list[str] = []

    def render() -> None:
        batches.append(service.render_batch(game_id=game_id, assets=(asset,)).batch_key)

    threads = [threading.Thread(target=render) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert CountingPreviewService.calls == 1
    assert len(set(batches)) == 1


def test_virtual_preview_expires_and_evicts_cache_when_over_budget(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    now = datetime(2026, 8, 29, tzinfo=UTC)
    service = VirtualCellPreviewService(
        tmp_path,
        cache_ttl=timedelta(seconds=1),
        max_cache_bytes=1,
        clock=lambda: now,
    )
    game_id = uuid4()
    batch = service.render_batch(game_id=game_id, assets=(asset,))

    with pytest.raises(SymbolCellReviewError) as evicted:
        service.read_atlas(game_id=game_id, batch_key=batch.batch_key)
    assert evicted.value.code == "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_NOT_FOUND"


def test_virtual_preview_ttl_and_lru_cache_eviction(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    game_id = uuid4()
    now = [datetime(2026, 8, 29, tzinfo=UTC)]
    service = VirtualCellPreviewService(
        tmp_path,
        cache_ttl=timedelta(minutes=15),
        max_cache_bytes=10_000_000,
        clock=lambda: now[0],
    )
    older = service.render_batch(game_id=game_id, assets=(asset,), preview_size=100)
    time.sleep(0.01)
    newer = service.render_batch(game_id=game_id, assets=(asset,), preview_size=101)
    cache_root = tmp_path / "data" / "working" / "virtual-cell-preview-cache-v1"
    total = sum(path.stat().st_size for path in cache_root.iterdir())

    service._max_cache_bytes = total - 1  # type: ignore[misc]
    service._prune(now=now[0])  # type: ignore[misc]

    with pytest.raises(SymbolCellReviewError) as oldest:
        service.read_atlas(game_id=game_id, batch_key=older.batch_key)
    assert oldest.value.code == "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_NOT_FOUND"
    retained = service.read_atlas(game_id=game_id, batch_key=newer.batch_key)
    assert retained.batch.batch_key == newer.batch_key

    now[0] += timedelta(minutes=16)
    with pytest.raises(SymbolCellReviewError) as expired:
        service.read_atlas(game_id=game_id, batch_key=newer.batch_key)
    assert expired.value.code == "SYMBOL_CELL_REVIEW_PREVIEW_BATCH_NOT_FOUND"


def test_virtual_preview_fails_closed_when_managed_source_is_missing(tmp_path: Path) -> None:
    asset = _current_asset(tmp_path)
    source = tmp_path / "data" / "originals" / asset.source_checksum_sha256[:2]
    for path in source.iterdir():
        path.unlink()

    with pytest.raises(SymbolCellReviewError) as missing:
        VirtualCellPreviewService(tmp_path).render_batch(game_id=uuid4(), assets=(asset,))

    assert missing.value.code == "SYMBOL_CELL_REVIEW_PREVIEW_SOURCE_UNAVAILABLE"
