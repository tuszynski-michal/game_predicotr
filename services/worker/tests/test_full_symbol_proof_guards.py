"""Small default tests for the two T4 audit guards accepted into T5."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from game_predictor_api.domain import grid_content_bundle as contract
from game_predictor_worker.images.full_board_variant_context import resolve_final_stage
from game_predictor_worker.images.grid_rescue_strategy import slots
from game_predictor_worker.images.production_cell_input import manifest_input_context
from test_production_cell_observations import board_preset


def test_input_context_bounds_growth_after_stat_and_keeps_the_legacy_error(tmp_path, monkeypatch):
    path = tmp_path / "bundle.json"
    path.write_bytes(b"x" * 65)  # Invalid JSON; reject the size before parsing or SHA.
    monkeypatch.setattr(contract, "CONTENT_BUNDLE_MAX_BYTES", 64)
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda self, **kwargs: SimpleNamespace(st_size=1)
        if self == path
        else original_stat(self, **kwargs),
    )
    manifest = {"managedDirectory": ".", "files": [{"name": "bundle.json", "sha256": "a" * 64}]}
    with pytest.raises(ValueError, match="^INPUT_CONTENT_BUNDLE_PATH_OR_SIZE$") as caught:
        manifest_input_context(tmp_path, manifest)
    assert isinstance(caught.value.__cause__, contract.ContentBundleTooLarge)
    assert (caught.value.__cause__.actual_bytes, caught.value.__cause__.limit_bytes) == (65, 64)


def test_input_context_valid_legacy_bytes_and_path_hash_errors_are_unchanged(tmp_path):
    board = board_preset().model_dump(mode="json")
    payload = json.dumps({"preset": {"board": board}}).encode()
    (tmp_path / "bundle.json").write_bytes(payload)
    manifest = {
        "managedDirectory": ".",
        "files": [
            {"name": "bundle.json", "sha256": hashlib.sha256(payload).hexdigest()},
        ],
    }
    assert manifest_input_context(tmp_path, manifest) == {
        "boardPreset": board,
        "routing": None,
        "path": None,
        "variant": None,
    }
    manifest["files"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="^INPUT_CONTENT_BUNDLE_CHANGED$"):
        manifest_input_context(tmp_path, manifest)
    manifest["managedDirectory"] = "../outside"
    with pytest.raises(ValueError, match="^INPUT_CONTENT_BUNDLE_PATH_OR_SIZE$"):
        manifest_input_context(tmp_path, manifest)


def detection(left):
    nodes = np.asarray([[left + x * 10.0, 10.0 + y * 10.0] for y in range(4) for x in range(6)])
    return SimpleNamespace(nodes=nodes, screen_quad=nodes[[0, 5, 23, 18]])


def test_real_final_slot_swap_cannot_relabel_a_foreign_base_as_wide():
    p, q = 0, 1
    baseline = [detection(10), detection(110)]
    # Replacing p with a result right of q changes the *actual* final slot binding.
    replacement = detection(210)
    final = [replacement, baseline[q]]
    assert slots(baseline) == {p: 0, q: 1}
    assert slots(final) == {p: 1, q: 0}
    returned_for_p = final[slots(final)[p]]
    assert returned_for_p is baseline[q]
    assert resolve_final_stage(returned_for_p, p, baseline, (p,), combined=True) is None
    # Its own BASE provenance and the uncombined legacy behavior are unchanged.
    assert resolve_final_stage(baseline[q], q, baseline, (p,), combined=True) == "baseline"
    assert resolve_final_stage(returned_for_p, p, baseline, (p,), combined=False) == "baseline"


def test_original_and_distinct_node_identical_successful_wide_keep_their_stages():
    baseline = [detection(10), detection(110)]
    replacement = detection(10)
    assert replacement is not baseline[0]
    assert np.array_equal(replacement.nodes, baseline[0].nodes)
    assert slots([replacement, baseline[1]]) == {0: 0, 1: 1}
    assert resolve_final_stage(baseline[0], 0, baseline, (0,), combined=True) == "baseline"
    assert resolve_final_stage(replacement, 0, baseline, (0,), combined=True) == "wide"
    assert resolve_final_stage(replacement, 0, baseline, (), combined=True) is None
