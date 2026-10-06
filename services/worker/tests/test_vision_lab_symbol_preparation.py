"""Preparation preserves labels-only scope, crop identity and create-only recovery."""

import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from game_predictor_worker.vision_lab.annotations import digest, read_checked
from game_predictor_worker.vision_lab.symbol_contracts import LabelDecide, LabQueueRequest
from game_predictor_worker.vision_lab.symbol_dataset_version import LabelPreviewGrant
from game_predictor_worker.vision_lab.symbol_preparation import (
    build_bundle,
    check_destination,
    latest_fresh_decisions,
    publish_bundle,
    summarize,
    verify_bundle,
)
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from test_vision_lab_symbol_dataset_version import versioned


def approved(tmp_path):
    store, source, _ = versioned(tmp_path)
    queue = store.preview(LabQueueRequest(kind="lab_queue", game_id=source.game_id))
    dictionary = store.dictionary(source.game_id, 1)
    store.mutate(
        LabelDecide(
            op="label_decide",
            request_id="fresh-label",
            expected_revision=2,
            binding=queue.items[0].binding,
            dictionary_version=1,
            dictionary_digest=dictionary.digest,
            action="approve",
            symbol_id="a",
        )
    )
    return store, source


def test_latest_selection_excludes_old_superseded_and_withdrawn():
    def decision(cell, action="approve", version="fresh", revision=1):
        return {
            "binding": {"source_id": "s", "board_index": 0, "cell_index": cell},
            "dataset_version_id": version,
            "action": action,
            "revision": revision,
        }

    payload = {
        "decisions": [
            decision(0, version="old"),
            decision(1),
            decision(1, revision=2),
            decision(2),
            decision(2, action="withdraw"),
            decision(3, action="unknown"),
        ]
    }
    assert latest_fresh_decisions(payload, "fresh") == [decision(1, revision=2)]
    with pytest.raises(ValueError, match="SYMBOL_PREPARATION_EMPTY"):
        latest_fresh_decisions(payload, "none")


def test_build_verify_restart_retry_and_original_history_unchanged(tmp_path):
    store, _ = approved(tmp_path)
    paths = [store.root / "state.json", store.annotations.root / "state.json"]
    before = [p.read_bytes() for p in paths]
    payload, files = build_bundle(store)
    assert payload["trainable"] is False and "assignments" not in payload
    assert payload["report"]["samples"] == 1
    assert payload["report"]["training_blockers"] == {
        "SYMBOL_SPLIT_NOT_FROZEN": 1,
        "SYMBOL_PROVENANCE_UNRESOLVED": 1,
        "HOLDOUT_POLICY_UNRESOLVED": 1,
    }
    root = publish_bundle(tmp_path / "prepared", payload, files)
    assert verify_bundle(root) == payload
    assert read_checked(root / "symbols-state.json") == store.load()
    restarted = SymbolLabelStore(
        store.root, store.annotations, dataset_version=store.dataset_version
    )
    again, again_files = build_bundle(restarted)
    assert (again, again_files) == (payload, files)
    assert publish_bundle(root.parent, again, again_files) == root
    command = [
        sys.executable,
        "-m",
        "game_predictor_worker.vision_lab.symbol_preparation",
        "verify",
        "--bundle",
        str(root),
    ]
    result = subprocess.run(
        command, env=os.environ.copy(), capture_output=True, text=True, timeout=20, check=True
    )
    assert digest(payload) in result.stdout
    assert [p.read_bytes() for p in paths] == before


def test_protected_source_rejected_before_crop_read(tmp_path, monkeypatch):
    store, source = approved(tmp_path)
    real = store.preview_grant

    def protected(p, a, g):
        grant = real(p, a, g)
        return LabelPreviewGrant(
            grant.version_id, a, store.catalog, grant.sources, frozenset({source.id})
        )

    monkeypatch.setattr(store, "preview_grant", protected)
    monkeypatch.setattr(
        "game_predictor_worker.vision_lab.symbol_preparation.read_crop",
        lambda *_: pytest.fail("protected pixels read"),
    )
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        build_bundle(store)


def test_legacy_store_requires_reference(tmp_path):
    store, _ = approved(tmp_path)
    legacy = SymbolLabelStore(store.root, store.annotations)
    with pytest.raises(ValueError, match="SYMBOL_PREPARATION_REFERENCE_REQUIRED"):
        build_bundle(legacy)


def test_verify_rejects_protected_before_reading_crop_files(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab import symbol_preparation as module

    store, source = approved(tmp_path)
    payload, files = build_bundle(store)
    payload["protected_source_ids"].append(source.id)
    monkeypatch.setattr(module, "sha", lambda *_: pytest.fail("protected crop bytes read"))
    with pytest.raises(ValueError, match="HOLDOUT_NOT_RELEASED"):
        publish_bundle(tmp_path / "prepared", payload, files)


def test_invalid_current_label_is_not_silently_dropped(tmp_path, monkeypatch):
    store, _ = approved(tmp_path)
    original = store.local_row

    def invalid(*args):
        row = original(*args)
        row.label_valid = False
        row.reasons = ["SYMBOL_GEOMETRY_STALE"]
        return row

    monkeypatch.setattr(store, "local_row", invalid)
    with pytest.raises(ValueError, match="SYMBOL_PREPARATION_LABEL_INVALID:SYMBOL_GEOMETRY_STALE"):
        build_bundle(store)


@pytest.mark.parametrize("damage", ["missing", "tampered", "extra", "pixel"])
def test_bundle_damage_is_detected(tmp_path, damage):
    store, _ = approved(tmp_path)
    payload, files = build_bundle(store)
    if damage == "pixel":
        payload["samples"][0]["decision"]["binding"]["pixel_sha256"] = "0" * 64
        with pytest.raises(ValueError, match="SYMBOL_PREPARATION_LINEAGE_MISMATCH"):
            publish_bundle(tmp_path / "prepared", payload, files)
        return
    root = publish_bundle(tmp_path / "prepared", payload, files)
    crop = next((root / "crops").glob("*.png"))
    if damage == "missing":
        crop.unlink()
    elif damage == "tampered":
        crop.write_bytes(b"damaged")
    else:
        (root / "extra.txt").write_text("untracked")
    with pytest.raises(
        ValueError, match="SYMBOL_PREPARATION_(INVENTORY_MISMATCH|FILE_INTEGRITY_ERROR)"
    ):
        verify_bundle(root)
    with pytest.raises(ValueError):
        publish_bundle(root.parent, payload, files)


def test_interrupted_publication_keeps_final_absent_and_retry_works(tmp_path, monkeypatch):
    from game_predictor_worker.vision_lab import symbol_preparation as module

    store, _ = approved(tmp_path)
    payload, files = build_bundle(store)
    original = module.publish_file
    calls = 0

    def interrupted(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publication interrupted")
        original(path, data)

    monkeypatch.setattr(module, "publish_file", interrupted)
    output = tmp_path / "prepared"
    with pytest.raises(OSError, match="interrupted"):
        publish_bundle(output, payload, files)
    assert not (output / digest(payload)).exists()
    monkeypatch.setattr(module, "publish_file", original)
    assert verify_bundle(publish_bundle(output, payload, files)) == payload


def test_output_cannot_overlap_inputs(tmp_path):
    store, _ = approved(tmp_path)
    for path in [
        store.root,
        store.root / "output",
        store.annotations.root,
        store.catalog.root,
        store.dataset_version,
        tmp_path,
    ]:
        with pytest.raises(ValueError, match="SYMBOL_PREPARATION_DIRECTORY_OVERLAP"):
            check_destination(path, store)
    check_destination(tmp_path / "prepared", store)
    with pytest.raises(ValueError, match="ABSOLUTE_PATH_REQUIRED"):
        check_destination(Path("relative"), store)


def test_pixel_duplicates_and_conflicting_classes_are_reported():
    sample = {
        "decision": {
            "symbol_id": "a",
            "decision_id": "first",
            "binding": {"source_id": "s", "pixel_sha256": "same"},
        },
        "component_id": "component",
        "family_id": "unresolved",
        "training_blockers": ["SYMBOL_SPLIT_NOT_FROZEN"],
    }
    second = deepcopy(sample)
    second["decision"].update(symbol_id="b", decision_id="second")
    dictionary = {"entries": [{"id": "a", "display_name": "A"}, {"id": "b", "display_name": "B"}]}
    result = summarize([sample, second], dictionary)
    assert result["samples"] == 2 and result["sources"] == result["components"] == 1
    assert result["conflicting_pixel_groups"][0]["symbol_ids"] == ["a", "b"]
    assert result["classes"][0]["unique_pixels"] == 1
    assert result["super_labels"] == 0
