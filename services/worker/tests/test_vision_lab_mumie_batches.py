"""Batches must not turn partial geometry or model proposals into training labels."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from game_predictor_worker.vision_lab.mumie_batches import (
    FORMAT,
    chunks,
    eligible_boards,
    match_folder,
    verify,
)
from game_predictor_worker.vision_lab.snapshot import canonical


def test_whole_photo_batches_keep_domain_order():
    photos = [{"queue_index": i, "boards": [0, 4, 8]} for i in range(236)]
    batches = chunks(photos, 50)
    assert [len(batch) for batch in batches] == [50, 50, 50, 50, 36]
    assert [row for batch in batches for row in batch] == photos
    for invalid in (0, 51):
        with pytest.raises(ValueError, match="BATCH_SIZE_OUT_OF_RANGE"):
            chunks(photos, invalid)


def test_partial_photo_never_exports_crops_even_with_approved_boards():
    board = {"board_index": 8, "presence": "present", "full_approved": True, "nodes": [[0, 0]] * 24}
    assert eligible_boards({"complete": False, "boards": [board]}) == []
    assert eligible_boards({"complete": True, "boards": [board]}) == [board]
    with pytest.raises(ValueError, match="COMPLETE_PHOTO_INVALID"):
        eligible_boards({"complete": True, "boards": [{**board, "full_approved": False}]})


def test_complete_photo_excludes_absent_slots_and_preserves_positions():
    def board(index):
        return {
            "board_index": index,
            "presence": "present",
            "full_approved": True,
            "nodes": [[0, 0]] * 24,
        }

    result = eligible_boards(
        {"complete": True, "boards": [board(8), {"board_index": 1, "presence": "absent"}, board(0)]}
    )
    assert [row["board_index"] for row in result] == [0, 8]


def test_folder_match_uses_bytes_and_game_not_filename(tmp_path):
    (tmp_path / "renamed.jpg").write_bytes(b"mumie")
    (tmp_path / "duplicate.jpg").write_bytes(b"mumie")
    (tmp_path / "missing.jpg").write_bytes(b"777")
    sha = hashlib.sha256(b"mumie").hexdigest()
    catalog = SimpleNamespace(
        sources={
            "m": SimpleNamespace(id="m", sha256=sha, game_name="Mumie"),
            "7": SimpleNamespace(
                id="7", sha256=hashlib.sha256(b"777").hexdigest(), game_name="777"
            ),
        }
    )
    result = match_folder(tmp_path, catalog)
    assert result["missing"] == ["missing.jpg"]
    assert result["unique"] == 2
    assert result["files"][0]["source_ids"] == ["m"]


def test_verify_detects_changed_crops_and_cannot_escape_artifact(tmp_path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "crop.png").write_bytes(b"pixels")
    payload = {
        "format": FORMAT,
        "artifact_id": root.name,
        "files": {"crop.png": hashlib.sha256(b"pixels").hexdigest()},
    }

    def publish(value):
        (root / "manifest.json").write_text(
            json.dumps({"payload": value, "sha256": hashlib.sha256(canonical(value)).hexdigest()}),
            encoding="utf-8",
        )

    publish(payload)
    assert verify(root) == payload
    assert verify(root) == payload
    (root / "crop.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="ARTIFACT_CHECKSUM_MISMATCH"):
        verify(root)
    publish({**payload, "files": {"../outside.png": hashlib.sha256(b"pixels").hexdigest()}})
    with pytest.raises(ValueError, match="ARTIFACT_CHECKSUM_MISMATCH"):
        verify(root)
