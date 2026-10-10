"""Prevent leakage, stale pixels and false recovery in the offline folder test."""

import argparse
import importlib.util
from pathlib import Path

import pytest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "test_mumie_folder.py"
spec = importlib.util.spec_from_file_location("mumie_folder_cli", SCRIPT)
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_selection_uses_numeric_range_and_spans_entire_folder():
    rows = [{"path": f"seq_{i}-{i + 8}.jpg", "sha256": str(i)} for i in (100, 10, 1000, 19, 28)]
    selected, counts = cli.select_rows(rows, set(), 3)
    assert [r["path"] for r in selected] == ["seq_10-18.jpg", "seq_28-36.jpg", "seq_1000-1008.jpg"]
    assert counts["selected"] == 3


def test_known_training_or_review_pixels_and_duplicates_are_excluded():
    rows = [
        {"path": "seq_1-9.jpg", "sha256": "known"},
        {"path": "seq_10-18.jpg", "sha256": "fresh"},
        {"path": "seq_19-27.jpg", "sha256": "fresh"},
    ]
    selected, counts = cli.select_rows(rows, {"known"}, 10)
    assert len(selected) == 1
    assert counts == {
        "files": 3,
        "duplicates": 1,
        "known_sha_excluded": 1,
        "eligible": 1,
        "selected": 1,
    }


def test_windows_copy_suffix_preserves_range_and_deduplicates_only_identical_pixels():
    rows = [
        {"path": "seq_1-9 — kopia.jpg", "sha256": "same"},
        {"path": "seq_1-9.jpg", "sha256": "same"},
        {"path": "seq_10-18 — kopia.jpg", "sha256": "different"},
    ]
    selected, counts = cli.select_rows(rows, set(), 10)
    assert [row["path"] for row in selected] == ["seq_1-9.jpg", "seq_10-18 — kopia.jpg"]
    assert counts["duplicates"] == 1
    assert cli.range_key(Path(selected[1]["path"]))[:2] == (10, 18)


def test_changed_source_bytes_block_decode_even_when_image_is_valid(tmp_path):
    source = tmp_path / "seq_1-9.jpg"
    Image.new("RGB", (20, 20), "red").save(source)
    row = {"path": str(source), "sha256": cli.sha(source)}
    assert cli.load_image(row).size == (20, 20)
    Image.new("RGB", (20, 20), "blue").save(source)
    with pytest.raises(ValueError, match="SOURCE_CHECKSUM_CHANGED"):
        cli.load_image(row)


def test_recovery_checks_assets_and_manifest_binding(tmp_path):
    asset = tmp_path / "overlay.jpg"
    asset.write_bytes(b"pixels")
    result = tmp_path / "row.json"
    cli.write_new(result, {"binding": "m", "files": {"overlay.jpg": cli.sha(asset)}})
    assert cli.validate_result(tmp_path, result, "m")["binding"] == "m"
    with pytest.raises(ValueError, match="RESULT_FOREIGN_MANIFEST"):
        cli.validate_result(tmp_path, result, "other")
    asset.write_bytes(b"changed")
    with pytest.raises(ValueError, match="RESULT_FILE_CHANGED"):
        cli.validate_result(tmp_path, result, "m")


def test_manifest_is_create_only_and_corruption_fails(tmp_path):
    path = tmp_path / "manifest.json"
    cli.write_new(path, {"value": 1})
    cli.write_new(path, {"value": 1})
    with pytest.raises(ValueError, match="ARTIFACT_ALREADY_EXISTS_DIFFERENT"):
        cli.write_new(path, {"value": 2})
    path.write_text('{"payload":{"value":2},"sha256":"bad"}', encoding="utf-8")
    with pytest.raises(ValueError, match="ARTIFACT_CHECKSUM_MISMATCH"):
        cli.read_bound(path)


def test_unchanged_model_reference_is_disclosed_without_invalidating_approval(
    tmp_path, monkeypatch
):
    annotations = tmp_path / "annotations"
    state_path = annotations / "state.json"
    owner = {
        "annotation_revision": 1,
        "origin": "proposal_unchanged",
        "proposal_set_id": "set3",
        "actor": "operator",
    }
    cli.write_new(state_path, {"state": {"assisted_photos": {"p": {"boards": {"0": owner}}}}})
    ledger = tmp_path / "ledger.json"
    cli.write_new(ledger, {"iterations": {"3": {"proposals": str(tmp_path / "set3")}}})
    manifest = {
        "annotations_path": str(annotations),
        "annotations_sha256": cli.sha(state_path),
        "rows": [
            {
                "kind": "new_approved",
                "source_id": "p",
                "labels": [{"board_index": 0, "revision": 1}],
            }
        ],
    }
    monkeypatch.setattr(cli, "collect", lambda path: (manifest, {}))
    (tmp_path / "index.html").write_text('<div id="stats"></div>', encoding="utf-8")
    original = state_path.read_bytes()
    cli.reference_audit(argparse.Namespace(output=tmp_path, ledger=ledger))
    audit = cli.read_bound(tmp_path / "reference-provenance.json")
    assert audit["proposal_models"] == {"iteration3": 1}
    assert audit["origins"] == {"proposal_unchanged": 1}
    assert "niezależną dokładność" in (tmp_path / "review.html").read_text(encoding="utf-8")
    assert state_path.read_bytes() == original
