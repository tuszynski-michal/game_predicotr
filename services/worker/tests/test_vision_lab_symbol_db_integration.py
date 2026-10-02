"""Full on-disk exporter-v1 fixture; no database session or operator images."""

import base64
import hashlib
import io

import pytest
from game_predictor_worker.vision_lab.annotation_contracts import AnnotationState, FrozenSplit
from game_predictor_worker.vision_lab.annotations import digest
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.snapshot import canonical
from game_predictor_worker.vision_lab.symbol_snapshot import SymbolSnapshot
from PIL import Image

GAME = "00000000-0000-0000-0000-000000000001"
SOURCE = "00000000-0000-0000-0000-000000000002"


def exported(tmp_path, *, missing=None, owner=None, symbol=None, role="data"):
    root = tmp_path / "db-snapshot"
    root.mkdir()
    image = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 40, 80)).save(image, "PNG")
    data = image.getvalue()
    checksum = hashlib.sha256(data).hexdigest()
    cell = dict(
        game_id=GAME,
        source_available=True,
        geometry_revision=1,
        review_state="approved",
        quality_issue=None,
        approved_crop_sample_id="sample",
        crop_sample_id="sample",
        approved_crop_checksum_sha256=checksum,
        crop_checksum_sha256=checksum,
        approved_geometry_revision=1,
        asset_mode="legacy_file",
        approved_asset_mode="legacy_file",
        crop_relative_path="crop.png",
        assigned_symbol_id="a",
        recognized_board_id="board",
        cell_index=0,
        sequence_number=7,
        review_item_id="review",
        revision=1,
        last_reviewed_at="2026-09-27",
    )
    projection = dict(
        gameId=GAME,
        sourceImageId=SOURCE,
        boardId="board",
        cellIndex=0,
        geometryRevision=1,
        cropSampleId="sample",
        cropSha256=checksum,
        symbolId="a",
        reviewRevision=1,
        reviewedAt="2026-09-27",
    )
    tables = {
        "symbols": [
            dict(id="a", code="A", name="A", game_id=GAME, status="active", **(symbol or {}))
        ],
        "rules_versions": [],
        "rules_version_symbols": [],
        "image_symbol_review_cells": [cell],
        "recognized_boards": [dict(id="board", source_image_id=SOURCE, geometry_revision=1)],
        "image_board_search_fast_documents": [
            dict(sequence_number=7, review_item_id="review", recognized_board_id="board")
        ],
    }
    if owner:
        tables["image_board_search_fast_documents"][0].update(owner)
    if symbol:
        tables["symbols"][0].update(symbol)
    files = {
        f"images/{checksum[:2]}/{checksum}.jpg": data,
        "assets/crop.png": data,
        "approved_labels.json": canonical([projection]),
    }
    for name, rows in tables.items():
        if name != missing:
            files[f"records/{GAME}/{name}.jsonl"] = b"".join(canonical(r) + b"\n" for r in rows)
    inputs = {
        "schemaVersion": 1,
        "datasetName": "test",
        "entries": [
            dict(
                gameId=GAME,
                sourceImageId=SOURCE,
                expectedSourceSha256=checksum,
                sourceFamilyId="test-family",
                role=role,
            )
        ],
    }
    identity = {"input": inputs, "exporterVersion": "test-v1", "rows": []}
    snapshot_id = digest(identity)
    files["frozen_identity.json"] = canonical({"snapshotId": snapshot_id, "rows": []})
    manifest = dict(
        schemaVersion=1,
        input=inputs,
        exporterVersion="test-v1",
        snapshotId=snapshot_id,
        files={name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    )
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "manifest.json").write_bytes(canonical(manifest))
    catalog = Catalog(root)
    return (
        SymbolSnapshot(catalog),
        AnnotationState(snapshot_id=digest([s.model_dump() for s in catalog.sources.values()])),
        data,
    )


def test_exact_db_crop_is_readonly_and_not_recropped(tmp_path):
    adapter, state, data = exported(tmp_path)
    rows = adapter.rows(state)
    assert len(rows) == 1 and rows[0].label_valid and not rows[0].trainable
    preview = adapter.preview(rows[0].sample_id, state)
    assert preview.read_only and preview.origin == "db_approved"
    assert base64.b64decode(preview.crop_bytes_base64) == data
    assert preview.media_type == "image/png"
    assert preview.dictionary.origin == "db_snapshot" and preview.dictionary.version is None


@pytest.mark.parametrize("table", ["symbols", "rules_versions", "image_symbol_review_cells"])
def test_missing_metadata_is_explicit(tmp_path, table):
    adapter, _, _ = exported(tmp_path, missing=table)
    assert adapter.availability == "DB_METADATA_UNSUPPORTED" and not adapter.labels


@pytest.mark.parametrize(
    "owner",
    [{"review_item_id": "wrong"}, {"recognized_board_id": "wrong"}, {"sequence_number": 99}],
)
def test_owner_exclusions(tmp_path, owner):
    adapter, state, _ = exported(tmp_path, owner=owner)
    assert not adapter.rows(state)[0].label_valid


def test_db_holdout_blocks_crop_read(tmp_path, monkeypatch):
    adapter, state, _ = exported(tmp_path)
    state.split = FrozenSplit(
        fingerprint="test",
        revision=0,
        unseen_game_id=GAME,
        seed=1,
        assignments={},
        measurement={},
        annotation_fingerprints={},
        exclusions={},
    )
    state.split.fingerprint = digest(
        [
            state.snapshot_id,
            state.split.model_dump(
                include={
                    "revision",
                    "unseen_game_id",
                    "seed",
                    "assignments",
                    "measurement",
                    "annotation_fingerprints",
                    "exclusions",
                }
            ),
        ]
    )
    monkeypatch.setattr(adapter, "read_bytes", lambda *_: pytest.fail("holdout crop read"))
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        adapter.preview(next(iter(adapter.labels)), state)
    assert "SYMBOL_PIXEL_CHECK_DEFERRED" in adapter.rows(state)[0].reasons


def test_db_crop_tamper_is_integrity_error(tmp_path):
    adapter, state, _ = exported(tmp_path)
    (adapter.root / "assets/crop.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="INTEGRITY"):
        adapter.preview(next(iter(adapter.labels)), state)


@pytest.mark.parametrize("missing", [False, True])
def test_db_source_drift_after_startup_blocks_metadata_and_preview(tmp_path, missing):
    adapter, state, _ = exported(tmp_path)
    source = adapter.catalog.sources[SOURCE]
    path = adapter.catalog.paths[source.asset_id]
    if missing:
        path.unlink()
    else:
        path.write_bytes(b"corrupt source after startup")
    adapter.validate_metadata()
    with pytest.raises(ValueError, match="SYMBOL_SOURCE_INTEGRITY_ERROR"):
        adapter.rows(state)
    with pytest.raises(ValueError, match="SYMBOL_SOURCE_INTEGRITY_ERROR"):
        adapter.preview(next(iter(adapter.labels)), state)
