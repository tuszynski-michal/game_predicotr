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


def test_inventory_rows_get_render_specs_from_one_manifest_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-467 S7 (TASK-0792): the inventory no longer reads the cell column."""

    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    game_id, board_id = uuid4(), uuid4()
    rows = (
        {
            "recognized_board_id": board_id,
            "geometry_revision": 3,
            "cell_index": 4,
            "asset_mode": "virtual_source",
            "render_spec_checksum_sha256": "1" * 64,
        },
        {
            "recognized_board_id": str(board_id),
            "geometry_revision": 3,
            "cell_index": 9,
            "asset_mode": "virtual_source",
            "render_spec_checksum_sha256": "2" * 64,
        },
        {
            "recognized_board_id": uuid4(),
            "geometry_revision": 0,
            "cell_index": 1,
            "asset_mode": "legacy_file",
            "render_spec_checksum_sha256": None,
        },
    )
    calls: list[tuple[object, tuple[object, ...]]] = []

    def load(_session, *, game_id, keys):  # type: ignore[no-untyped-def]
        requested = tuple(keys)
        calls.append((game_id, requested))
        return {key: {"cellIndex": key.cell_index} for key in requested}

    monkeypatch.setattr(module, "load_cell_render_specs", load)
    merged = module._with_manifest_render_specs(Mock(), game_id=game_id, rows=rows)

    assert [row["render_spec"] for row in merged] == [{"cellIndex": 4}, {"cellIndex": 9}, None]
    assert [{**row, "render_spec": None} for row in merged] == [
        {**row, "render_spec": None} for row in rows
    ]
    assert len(calls) == 1 and calls[0][0] == game_id
    assert [
        (key.recognized_board_id, key.geometry_revision, key.cell_index)  # type: ignore[attr-defined]
        for key in calls[0][1]
    ] == [(board_id, 3, 4), (board_id, 3, 9)]


def test_inventory_sql_selects_no_render_spec_column(monkeypatch: pytest.MonkeyPatch) -> None:
    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    session = Mock()
    session.execute.return_value.mappings.return_value.one.return_value = {
        "unknown_count": 0,
        "unreadable_count": 0,
        "grid_issue_count": 0,
        "changed_crop_count": 0,
    }
    session.execute.return_value.mappings.return_value.__iter__ = lambda _self: iter(())
    monkeypatch.setattr(module, "load_cell_render_specs", lambda *_args, **_kwargs: {})
    repository = SqlAlchemySymbolCellTrainingSourceRepository(session, Path("."))

    inventory = repository.inventory(game_id=uuid4(), lock_game=False)

    assert inventory.candidates == ()
    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert len(statements) == 2
    for sql in statements:
        assert "c.*" not in sql
        assert "c.render_spec," not in sql and "c.render_spec\n" not in sql
    assert "c.render_spec_checksum_sha256" in statements[1]
