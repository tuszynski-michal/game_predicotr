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


def test_virtual_candidate_uses_checksum_bound_renderer_without_crop_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    source_geometry_revision_id = uuid4()
    crop_checksum = "c" * 64
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
        "current_geometry_revision": 1,
        "asset_mode": "virtual_source",
        "source_geometry_revision_id": source_geometry_revision_id,
        "current_source_geometry_revision_id": source_geometry_revision_id,
        "logical_cell_key": "d" * 64,
        "logical_cell_key_v2": "e" * 64,
        "render_identity_v2_sha256": "f" * 64,
        "render_spec": {"schemaVersion": "fixture"},
        "render_spec_checksum_sha256": "1" * 64,
        "rendered_pixel_checksum_sha256": crop_checksum,
        "extractor_version": "virtual-renderer-v1",
        "crop_sample_id": sample_id,
        "crop_relative_path": None,
        "crop_checksum_sha256": crop_checksum,
        "approved_crop_sample_id": sample_id,
        "approved_crop_checksum_sha256": crop_checksum,
        "approved_geometry_revision": 1,
        "source_checksum_sha256": "b" * 64,
        "source_relative_path": "originals/bb/source.jpg",
        "normalized_pixel_checksum_sha256": "2" * 64,
        "geometry_checksum_sha256": "3" * 64,
        "cropper_version": "structured-v0.10",
        "prediction_symbol_code": "cherry",
    }
    monkeypatch.setattr(
        module,
        "render_virtual_symbol_cell_png",
        lambda **_kwargs: _png_bytes((20, 120, 220)),
    )

    candidate = repository._candidate(values, allow_cached=False)

    assert candidate.asset_mode == "virtual_source"
    assert candidate.crop_relative_path is None
    assert candidate.rendered_pixel_checksum_sha256 == crop_checksum
