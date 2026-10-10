"""Export adapters preserve legacy approval boundaries without database access."""

import json

import pytest
from game_predictor_worker.vision_lab.symbol_snapshot import SymbolSnapshot
from test_vision_lab_symbol_labels import symbols


def db_fixture(tmp_path, monkeypatch, **changes):
    store, source = symbols(tmp_path)
    cell = dict(
        game_id=source.game_id,
        source_available=True,
        geometry_revision=2,
        review_state="approved",
        quality_issue=None,
        approved_crop_sample_id="crop",
        crop_sample_id="crop",
        approved_crop_checksum_sha256="a" * 64,
        crop_checksum_sha256="a" * 64,
        approved_geometry_revision=2,
        asset_mode="legacy_file",
        approved_asset_mode="legacy_file",
        crop_relative_path="crop.png",
        assigned_symbol_id="a",
        recognized_board_id="board",
        cell_index=0,
        sequence_number=12,
        review_item_id="review",
        revision=3,
        last_reviewed_at="now",
    )
    cell.update(changes)
    projection = dict(
        gameId=source.game_id,
        sourceImageId=source.id,
        boardId="board",
        cellIndex=0,
        geometryRevision=cell["geometry_revision"],
        cropSampleId=cell["crop_sample_id"],
        cropSha256=cell["crop_checksum_sha256"],
        symbolId="a",
        reviewRevision=3,
        reviewedAt="now",
    )
    tables = {
        "symbols": [dict(id="a", code="A", name="A", game_id=source.game_id, status="active")],
        "rules_version_symbols": [],
        "rules_versions": [],
        "image_symbol_review_cells": [cell],
        "recognized_boards": [dict(id="board", source_image_id=source.id, geometry_revision=2)],
        "image_board_search_fast_documents": [
            dict(sequence_number=12, review_item_id="review", recognized_board_id="board")
        ],
    }
    manifest = json.loads((store.catalog.root / "manifest.json").read_bytes())
    manifest.pop("format")
    manifest["schemaVersion"] = 1
    # Adapter tests operate on the already constructed Catalog, as production does.
    (store.catalog.root / "manifest.json").write_text(json.dumps(manifest))

    def read(self, relative, required=True):
        if relative == "approved_labels.json":
            return [projection]
        game = relative.split("/")[1]
        return tables[relative.split("/")[-1][:-6]] if game == source.game_id else None

    monkeypatch.setattr(SymbolSnapshot, "read_json", read)
    return SymbolSnapshot(store.catalog), source


@pytest.mark.parametrize(
    "changes",
    [
        {"source_available": False},
        {"geometry_revision": 99},
        {"review_state": "pending"},
        {"quality_issue": "unreadable"},
        {"approved_crop_sample_id": "old"},
        {"approved_crop_checksum_sha256": "b" * 64},
        {"approved_geometry_revision": 1},
        {"asset_mode": "virtual_source"},
        {"approved_asset_mode": "virtual_source"},
        {"crop_relative_path": None},
    ],
)
def test_db_exclusions(tmp_path, monkeypatch, changes):
    adapter, _ = db_fixture(tmp_path, monkeypatch, **changes)
    assert next(iter(adapter.labels.values()))["reasons"]


def test_db_positive_projection_and_no_folder_claim(tmp_path, monkeypatch):
    adapter, source = db_fixture(tmp_path, monkeypatch)
    value = next(iter(adapter.labels.values()))
    assert value["reasons"] == []
    assert value["projection"]["sourceImageId"] == source.id
    assert value["dictionary"].origin == "db_snapshot"
