"""Labels-only versions retain old consent/holdouts and exact existing writer receipts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.annotations import digest, read_checked, write_atomic
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.symbol_contracts import (
    LabCropRequest,
    LabelDecide,
    LabQueueRequest,
)
from game_predictor_worker.vision_lab.symbol_dataset_version import (
    load_reference,
    prepare_reference,
    publish_reference,
)
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from test_vision_lab_annotations import approve_full_photo
from test_vision_lab_symbol_labels import dictionary
from test_vision_lab_whole_game_split import pilot_store


def versioned(tmp_path):
    geometry, split = pilot_store(tmp_path)
    geometry.mutate(split)
    source = next(
        s
        for s in geometry.catalog.sources.values()
        if s.game_name == "ordinary" and s.id in split.geometry_source_ids
    )
    approve_full_photo(geometry, source.id)  # real new consent, stale old geometry split
    store = SymbolLabelStore(tmp_path / "symbols", geometry)
    dictionary(store, source)
    original = {
        p: p.read_bytes() for p in (geometry.root / "state.json", store.root / "state.json")
    }
    reference = prepare_reference(
        store,
        [source.id],
        {"accepted": True, "reference": "test explicit consent"},
        {"past_usage": "not a new independent test"},
    )
    target = publish_reference(tmp_path / "versions", reference, store)
    return SymbolLabelStore(store.root, geometry, dataset_version=target), source, original


def test_preview_publish_retry_retains_verbatim_lineage_and_stale(tmp_path):
    store, source, original = versioned(tmp_path)
    assert store.annotations.read().split_stale
    reference = load_reference(store.dataset_version)
    assert reference["counts"] == {"photos": 1, "boards": 1, "cells": 15}
    assert reference["lineage"]["geometry_payload"] == read_checked(
        store.annotations.root / "state.json"
    )
    assert (
        publish_reference(store.dataset_version.parent, reference, store) == store.dataset_version
    )
    assert all(path.read_bytes() == content for path, content in original.items())
    queue = store.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    assert queue.total == len(queue.items) == 15
    assert all(item.status == "unassigned" for item in queue.items)
    assert store.list_labels(source_id=source.id).total == 0
    legacy = SymbolLabelStore(store.root, store.annotations)
    with pytest.raises(ValueError, match="HOLDOUT_POLICY_UNRESOLVED"):
        legacy.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))


def test_exact_writer_lost_response_restart_and_fresh_process(tmp_path):
    store, source, original = versioned(tmp_path)
    queue = store.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    version = store.dictionary(source.game_id, 1)
    request = LabelDecide(
        op="label_decide",
        request_id="lost-response",
        expected_revision=2,
        binding=queue.items[0].binding,
        dictionary_version=1,
        dictionary_digest=version.digest,
        action="approve",
        symbol_id="a",
    )
    result = store.mutate(request)
    assert result.label_valid and not result.trainable
    assert {
        "SYMBOL_SPLIT_NOT_FROZEN",
        "SYMBOL_PROVENANCE_UNRESOLVED",
        "HOLDOUT_POLICY_UNRESOLVED",
    } <= set(result.training_blockers)
    restarted = SymbolLabelStore(
        store.root, store.annotations, dataset_version=store.dataset_version
    )
    written = (store.root / "state.json").read_bytes()
    assert restarted.mutate(request).replayed
    assert (store.root / "state.json").read_bytes() == written
    row = restarted.list_labels(source_id=source.id).items[0]
    assert row.label_valid and row.metadata["dataset_version_id"] == store.dataset_version.name
    assert (store.annotations.root / "state.json").read_bytes() == original[
        store.annotations.root / "state.json"
    ]
    code = """
from pathlib import Path
import sys
from game_predictor_worker.vision_lab.catalog import Catalog
from game_predictor_worker.vision_lab.annotations import AnnotationStore
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from game_predictor_worker.vision_lab.symbol_contracts import LabQueueRequest
store=SymbolLabelStore(Path(sys.argv[1]),AnnotationStore(Path(sys.argv[2]),Catalog(Path(sys.argv[3]))),dataset_version=Path(sys.argv[4]))
print(store.preview(LabQueueRequest(kind='lab_queue',game_id=sys.argv[5])).total)
"""
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(store.root),
            str(store.annotations.root),
            str(store.catalog.root),
            str(store.dataset_version),
            source.game_id,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert check.stdout.strip() == "14"
    approve_full_photo(store.annotations, source.id)
    replay = restarted.mutate(request)
    assert replay.replayed and not replay.label_valid and not replay.trainable
    assert (store.root / "state.json").read_bytes() == written
    with pytest.raises(ValueError, match="SYMBOL_DATASET_VERSION_STALE"):
        restarted.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    assert (
        not SymbolLabelStore(store.root, store.annotations)
        .list_labels(source_id=source.id)
        .items[0]
        .label_valid
    )


def test_inherited_holdout_and_outside_source_guard_before_decode(tmp_path, monkeypatch):
    store, source, _ = versioned(tmp_path)
    protected = next(s for s in store.catalog.sources.values() if s.game_name == "final")
    outside = next(
        s for s in store.catalog.sources.values() if s.game_name == "ordinary" and s.id != source.id
    )
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("protected pixels decoded"))
    for target, reason in (
        (protected, "HOLDOUT_NOT_RELEASED"),
        (outside, "SYMBOL_DATASET_SOURCE_EXCLUDED"),
    ):
        with pytest.raises(ValueError, match=reason):
            store.preview(
                LabCropRequest(
                    kind="lab_cell",
                    source_id=target.id,
                    board_index=0,
                    cell_index=0,
                    expected_geometry_revision=1,
                )
            )


def test_current_and_old_leakage_links_protect_whole_component(tmp_path):
    from game_predictor_worker.vision_lab.symbol_dataset_version import protected_sources
    from test_vision_lab_geometry_cohort import family

    store, source, _ = versioned(tmp_path)
    protected = next(s for s in store.catalog.sources.values() if s.game_name == "final")
    alias = next(
        s for s in store.catalog.sources.values() if s.game_name == "ordinary" and s.id != source.id
    )
    family(store.annotations, [source.id, protected.id], provenance="unresolved")
    # Existing old ordinary family is still linked even if its current declaration changes.
    blocked = protected_sources(store.catalog, store.annotations.read())
    assert source.id in blocked and alias.id in blocked
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        prepare_reference(store, [source.id], {"accepted": True, "reference": "test"}, {})


def test_corrupt_reference_publication_crash_and_retry(tmp_path, monkeypatch):
    store, _, _ = versioned(tmp_path)
    import game_predictor_worker.vision_lab.symbol_store as module

    reference = load_reference(store.dataset_version)
    other = tmp_path / "retry"
    original_link = module.os.link
    monkeypatch.setattr(module.os, "link", lambda *a: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError, match="crash"):
        publish_reference(other, reference, store)
    assert not (other / digest(reference) / "manifest.json").exists()
    monkeypatch.setattr(module.os, "link", original_link)
    assert load_reference(publish_reference(other, reference, store)) == reference
    (store.dataset_version / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="INTEGRITY"):
        store.preview(LabQueueRequest(kind="lab_queue", game_id=reference["game_id"]))


def test_api_uses_existing_contract_with_optional_version(tmp_path):
    store, source, _ = versioned(tmp_path)
    original_app = create_app(store.catalog, store.annotations.root, symbol_root=store.root)
    app = create_app(
        store.catalog,
        store.annotations.root,
        symbol_root=store.root,
        symbol_dataset_version=store.dataset_version,
    )
    assert app.openapi() == original_app.openapi()
    client = TestClient(app, base_url="http://127.0.0.1:8102")
    body = {"kind": "lab_queue", "game_id": source.game_id}
    assert client.post("/symbol-crops", json=body).status_code == 403
    response = client.post("/symbol-crops", json=body, headers={"origin": "http://127.0.0.1:3102"})
    assert response.status_code == 200 and response.json()["total"] == 15


def test_catalog_dictionary_and_frozen_role_drift_fail_closed(tmp_path, monkeypatch):
    store, source, _ = versioned(tmp_path)
    reference = load_reference(store.dataset_version)
    altered = read_checked(store.annotations.root / "state.json")
    altered["state"]["split"]["game_partitions"][source.game_id] = "final_test"
    write_atomic(store.annotations.root / "state.json", altered)
    with pytest.raises(ValueError, match="STALE"):
        store.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    write_atomic(store.annotations.root / "state.json", reference["lineage"]["geometry_payload"])
    dictionary_payload = read_checked(store.root / "state.json")
    dictionary_payload["dictionaries"][0]["digest"] = "0" * 64
    write_atomic(store.root / "state.json", dictionary_payload)
    with pytest.raises(ValueError, match="STALE"):
        store.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    write_atomic(store.root / "state.json", reference["lineage"]["symbols_payload"])
    store.catalog.sources[source.id] = source.model_copy(update={"role": "comparison_only"})
    monkeypatch.setattr(store.catalog, "image", lambda _: pytest.fail("catalog drift decoded"))
    with pytest.raises(ValueError, match="STALE"):
        store.preview(
            LabCropRequest(
                kind="lab_cell",
                source_id=source.id,
                board_index=0,
                cell_index=0,
                expected_geometry_revision=1,
            )
        )
