from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.application.virtual_cell_previews import (
    VirtualSymbolCellImageRenderer,
    render_virtual_symbol_cell_png,
)
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    build_symbol_cell_training_manifest,
    select_symbol_cell_training_samples,
)
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
    _image_visual_descriptor,
    _visual_descriptor,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.symbols.protected_sources import ProtectedSources
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


def _virtual_values() -> dict[str, object]:
    source_geometry_revision_id = uuid4()
    crop_checksum = "c" * 64
    sample_id = "a" * 64
    return {
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


def test_candidate_requires_current_approved_crop_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    monkeypatch.setattr(
        module,
        "render_virtual_symbol_cell_png",
        lambda **_kwargs: _png_bytes((30, 90, 150)),
    )
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    values = _virtual_values()

    candidate = repository._candidate(values, allow_cached=False)
    assert candidate.approved_crop_checksum_sha256 == "c" * 64

    values["approved_geometry_revision"] = 0
    with pytest.raises(ImageReviewConflictError) as conflict:
        repository._candidate(values, allow_cached=False)
    assert conflict.value.code == "SYMBOL_CELL_TRAINING_ELIGIBILITY_DRIFT"


def test_candidate_refuses_a_non_virtual_crop(tmp_path: Path) -> None:
    """D-467 S6 (TASK-0796): no training candidate is read from a crop file."""

    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    values = {**_virtual_values(), "asset_mode": "none"}
    with pytest.raises(ImageReviewConflictError) as invalid:
        repository._candidate(values, allow_cached=False)
    assert invalid.value.code == "SYMBOL_CELL_TRAINING_CROP_INVALID"


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
            "asset_mode": "none",
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


def _source_values(tmp_path: Path) -> dict[str, object]:
    from test_virtual_cell_previews import _asset

    asset = _asset(tmp_path)
    values = _virtual_values()
    for name in (
        "geometry_revision",
        "current_geometry_revision",
        "source_geometry_revision_id",
        "current_source_geometry_revision_id",
        "source_checksum_sha256",
        "normalized_pixel_checksum_sha256",
        "geometry_checksum_sha256",
        "logical_cell_key",
        "render_spec",
        "render_spec_checksum_sha256",
        "rendered_pixel_checksum_sha256",
        "extractor_version",
        "crop_checksum_sha256",
    ):
        values[name] = getattr(asset, name)
    values["source_relative_path"] = (
        f"originals/{asset.source_checksum_sha256[:2]}/{asset.source_checksum_sha256}.jpg"
    )
    values["approved_crop_checksum_sha256"] = asset.crop_checksum_sha256
    values["approved_geometry_revision"] = asset.geometry_revision
    return values


def test_grouped_descriptors_decode_once_and_preserve_manifest_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    first = _source_values(tmp_path)
    rows = tuple(
        {**first, "id": uuid4(), "cell_index": index, "sequence_number": 8 - index}
        for index in range(5)
    )
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    legacy = tuple(repository._candidate(row, allow_cached=False) for row in rows)
    source_opens = []
    original_load = CanonicalSourceLoader.load

    def load(loader, path, **kwargs):
        source_opens.append(path)
        return original_load(loader, path, **kwargs)

    monkeypatch.setattr(CanonicalSourceLoader, "load", load)
    monkeypatch.setattr(
        module,
        "render_virtual_symbol_cell_png",
        Mock(side_effect=AssertionError("No PNG descriptors")),
    )
    grouped = repository._grouped_candidates(rows)
    assert len(source_opens) == 1
    assert grouped == legacy
    assert [c.cell_index for c in grouped] == list(range(5))
    game_id = uuid4()
    manifests = [
        build_symbol_cell_training_manifest(
            game_id=game_id,
            selection=select_symbol_cell_training_samples(
                candidates=candidates, active_symbol_codes=("cherry",)
            ),
        )
        for candidates in (legacy, grouped)
    ]
    assert manifests[0] == manifests[1]
    # A fresh execution attests the source again, instead of relying on process cache.
    assert repository._grouped_candidates(rows) == grouped
    assert len(source_opens) == 2


def test_grouped_protection_uses_the_render_frame_and_rejects_forged_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _source_values(tmp_path)
    protected = ProtectedSources(frozenset(), frozenset())
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    calls = []
    original_load = CanonicalSourceLoader.load

    def load(loader, path, **kwargs):
        calls.append(path)
        return original_load(loader, path, **kwargs)

    monkeypatch.setattr(CanonicalSourceLoader, "load", load)
    assert len(repository._grouped_candidates((row, row), protected=protected)) == 2
    assert len(calls) == 1
    with pytest.raises(ImageReviewConflictError) as drift:
        repository._grouped_candidates(
            (row, {**row, "normalized_pixel_checksum_sha256": "0" * 64}), protected=protected
        )
    assert drift.value.code == "PROTECTED_SOURCE_IDENTITY_DRIFT"
    with pytest.raises(ImageReviewConflictError) as alias:
        repository._grouped_candidates(
            (row,),
            protected=ProtectedSources(
                frozenset(), frozenset((row["normalized_pixel_checksum_sha256"],))
            ),
        )
    assert alias.value.code == "PROTECTED_EVALUATION_SOURCE"


def test_grouped_missing_and_changed_assets_keep_exclusion_semantics(tmp_path: Path) -> None:
    row = _source_values(tmp_path)
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    assert (
        repository._grouped_candidates(({**row, "rendered_pixel_checksum_sha256": "0" * 64},)) == ()
    )
    source_path = tmp_path / "data" / str(row["source_relative_path"])
    source_path.unlink()
    assert repository._grouped_candidates((row,)) == ()
    with pytest.raises(ImageReviewConflictError) as missing:
        repository._grouped_candidates((row,), protected=ProtectedSources(frozenset(), frozenset()))
    assert missing.value.code == "PROTECTED_SOURCE_MISSING"


def test_image_and_png_descriptors_are_identical(tmp_path: Path) -> None:
    from test_virtual_cell_previews import _asset

    asset = _asset(tmp_path)
    png = render_virtual_symbol_cell_png(artifact_root=tmp_path, asset=asset)
    with VirtualSymbolCellImageRenderer(tmp_path) as renderer, renderer.render(asset) as image:
        assert _image_visual_descriptor(image) == _visual_descriptor(png)


def test_interleaved_source_groups_return_in_original_row_order(tmp_path: Path) -> None:
    first = _source_values(tmp_path)
    source = tmp_path / "data" / str(first["source_relative_path"])
    content = source.read_bytes() + b"byte-distinct-source"
    checksum = hashlib.sha256(content).hexdigest()
    relative = f"originals/{checksum[:2]}/{checksum}.jpg"
    alias = tmp_path / "data" / relative
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.write_bytes(content)
    spec = {**first["render_spec"], "sourceChecksumSha256": checksum}
    second = {
        **first,
        "id": uuid4(),
        "source_checksum_sha256": checksum,
        "source_relative_path": relative,
        "render_spec": spec,
        "render_spec_checksum_sha256": hashlib.sha256(canonical_json_bytes(spec)).hexdigest(),
    }
    rows = (first, second, {**first, "id": uuid4()}, {**second, "id": uuid4()})
    repository = SqlAlchemySymbolCellTrainingSourceRepository(Mock(), tmp_path)
    grouped = repository._grouped_candidates(rows)
    assert [candidate.cell_review_id for candidate in grouped] == [row["id"] for row in rows]
    assert grouped == tuple(repository._candidate(row, allow_cached=False) for row in rows)


def test_inventory_counts_changed_crop_as_missing_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_api.storage import symbol_cell_training_source_repository as module

    row = _source_values(tmp_path)
    session = Mock()
    session.execute.return_value.mappings.return_value = (
        row,
        {**row, "id": uuid4(), "rendered_pixel_checksum_sha256": "0" * 64},
    )
    repository = SqlAlchemySymbolCellTrainingSourceRepository(session, tmp_path)
    monkeypatch.setattr(
        repository, "_exclusion_counts", lambda _: module.SymbolCellTrainingExclusionCounts()
    )
    monkeypatch.setattr(module, "_with_manifest_render_specs", lambda *_, **kw: kw["rows"])
    result = repository.inventory(game_id=uuid4(), lock_game=False)
    assert len(result.candidates) == 1
    assert result.exclusions.missing_asset == 1
