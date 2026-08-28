from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
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


def test_candidate_requires_current_approved_crop_identity(tmp_path: Path) -> None:
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    content = _png_bytes((30, 90, 150))
    checksum = hashlib.sha256(content).hexdigest()
    relative = f"training-crops/{checksum}.png"
    path = tmp_path / "data" / "training-crops" / f"{checksum}.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    sample_id = "a" * 64
    values = {
        "id": uuid4(),
        "review_item_id": uuid4(),
        "recognized_board_id": uuid4(),
        "source_image_id": uuid4(),
        "import_job_id": uuid4(),
        "assigned_symbol_id": uuid4(),
        "symbol_code": "cherry",
        "sequence_number": 1,
        "cell_index": 0,
        "revision": 2,
        "geometry_revision": 1,
        "crop_sample_id": sample_id,
        "crop_relative_path": relative,
        "crop_checksum_sha256": checksum,
        "approved_crop_sample_id": sample_id,
        "approved_crop_checksum_sha256": checksum,
        "approved_geometry_revision": 1,
        "source_checksum_sha256": "b" * 64,
        "source_relative_path": "originals/source.jpg",
        "cropper_version": "cropper-v19",
        "prediction_symbol_code": "cherry",
    }

    candidate = repository._candidate(values, allow_cached=False)
    assert candidate.approved_crop_checksum_sha256 == checksum

    values["approved_geometry_revision"] = 0
    with pytest.raises(ImageReviewConflictError) as conflict:
        repository._candidate(values, allow_cached=False)
    assert conflict.value.code == "SYMBOL_CELL_TRAINING_ELIGIBILITY_DRIFT"
