from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    _cached_verified_visual_descriptor,
    _verified_visual_descriptor,
    _visual_descriptor,
)
from PIL import Image


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), color).save(output, format="PNG")
    return output.getvalue()


def test_visual_descriptor_is_deterministic_and_color_sensitive() -> None:
    red = _png_bytes((200, 10, 10))
    blue = _png_bytes((10, 10, 200))

    assert _visual_descriptor(red) == _visual_descriptor(red)
    assert _visual_descriptor(red)[1] != _visual_descriptor(blue)[1]


def test_preview_cache_is_bounded_but_freeze_rechecks_changed_bytes(tmp_path: Path) -> None:
    _cached_verified_visual_descriptor.cache_clear()
    path = tmp_path / "crop.png"
    original = _png_bytes((20, 100, 180))
    checksum = hashlib.sha256(original).hexdigest()
    path.write_bytes(original)

    cached = _cached_verified_visual_descriptor(str(path), checksum)
    path.write_bytes(_png_bytes((180, 100, 20)))

    assert _cached_verified_visual_descriptor(str(path), checksum) == cached
    assert _cached_verified_visual_descriptor.cache_info().maxsize == 32_768
    with pytest.raises(ImageReviewConflictError) as conflict:
        _verified_visual_descriptor(path, checksum)
    assert conflict.value.code == "SYMBOL_CELL_TRAINING_CROP_CHANGED"
