"""Regression cases for independent symbol inference and durable read-only evidence."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.images.symbol_classifier import load_image_tensor
from game_predictor_worker.vision_lab.annotations import digest
from game_predictor_worker.vision_lab.snapshot import sha
from game_predictor_worker.vision_lab.symbol_batch import (
    analyse_photo,
    bound_boards,
    checked_publish,
    choose_rows,
    classify_logits,
    excluded_sources,
    expected_count,
    load_photo,
    preprocess,
    result_path,
    run,
    sequence_range,
    validate_batch,
    validate_result,
)
from game_predictor_worker.vision_lab.symbol_store import publish_file
from PIL import Image
from torchvision.transforms import functional


def board(x, y, score=1):
    nodes = np.array([[x + c * 10, y + r * 10] for r in range(4) for c in range(6)], np.float32)
    return BoardDetection(score, nodes[[0, 5, 23, 18]], nodes=nodes)


def test_five_boards_do_not_draw_sixth_and_preserve_reading_order():
    boards = [
        board(55, 40),
        board(0, 40),
        board(110, 0),
        board(55, 0),
        board(0, 0),
        board(150, 70, 0.1),
    ]
    chosen, reasons, dropped = bound_boards(boards, 5)
    assert [(b.nodes[0].tolist()) for b in chosen] == [[0, 0], [55, 0], [110, 0], [0, 40], [55, 40]]
    assert reasons == ["BOARD_COUNT_EXCESS"] and len(dropped) == 1
    result, _ = analyse_photo(
        Image.new("RGB", (220, 120)),
        boards,
        5,
        lambda crops: [{"predicted": "Q", "confidence": 1, "symbol_reasons": []} for _ in crops],
    )
    assert result["selected"] == 5 and len(result["cells"]) == 75
    assert all(c["requires_review"] and not c["human_approved"] for c in result["cells"])


def test_missing_boards_never_invent_geometry():
    chosen, reasons, _ = bound_boards([board(0, 0)], 5)
    assert len(chosen) == 1 and reasons == ["BOARD_COUNT_MISSING"]
    result, _ = analyse_photo(Image.new("RGB", (100, 100)), [], 5, None)
    assert result["cells"] == [] and result["selected"] == 0


def test_last_filename_is_limited_by_operator_folder_end():
    assert expected_count({"start": 499996, "end": 500004}, Path("481537- 500000 cut")) == (
        5,
        ["FILENAME_FOLDER_RANGE_CLIPPED"],
    )
    assert expected_count({"start": 499987, "end": 499995}, Path("481537- 500000 cut")) == (9, [])
    with pytest.raises(ValueError, match="OUTSIDE_FOLDER_RANGE"):
        expected_count({"start": 500005, "end": 500013}, Path("481537- 500000 cut"))


def test_outside_cells_are_not_black_fabricated_symbols():
    counts = []
    result, _ = analyse_photo(
        Image.new("RGB", (100, 100)),
        [board(-5, 0)],
        1,
        lambda crops: counts.append(len(crops))
        or [{"predicted": "10", "confidence": 1, "symbol_reasons": []} for _ in crops],
    )
    assert counts == [12]
    unavailable = [c for c in result["cells"] if c["predicted"] is None]
    assert [c["cell_index"] for c in unavailable] == [0, 5, 10]
    assert all(
        c["crop_pixel_sha256"] is None and c["reasons"] == ["CELL_OUTSIDE_IMAGE"]
        for c in unavailable
    )


def test_invalid_grid_does_not_reach_classifier():
    broken = board(0, 0)
    broken.nodes[1] = broken.nodes[0]
    result, _ = analyse_photo(Image.new("RGB", (100, 100)), [broken], 1, None)
    assert len(result["cells"]) == 15
    assert all(
        c["predicted"] is None and "GRID_STRUCTURE_INVALID" in c["reasons"] for c in result["cells"]
    )


def test_full_component_exclusion_includes_unselected_aliases():
    payload = {
        "assignments": {"train": "development", "val": "validation"},
        "protected_source_ids": ["protected"],
        "graph": {
            "a": ["train", "train-alias"],
            "b": ["val", "val-alias"],
            "c": ["protected", "protected-alias"],
            "d": ["new"],
        },
    }
    assert excluded_sources(payload) == {
        "train",
        "train-alias",
        "val",
        "val-alias",
        "protected",
        "protected-alias",
    }
    rows = [{"filename": str(i), "start": i, "end": i, "sha256": str(i)} for i in range(10)]
    rows.append(rows[3].copy())
    chosen, inventory = choose_rows(rows, {"0", "2"}, 3)
    assert [r["start"] for r in chosen] == [1, 5, 9]
    assert inventory == {"files": 11, "duplicates": 1, "excluded": 2, "eligible": 8, "selected": 3}


@pytest.mark.parametrize("gray", [False, True])
def test_preprocessing_equals_frozen_training_transform(tmp_path, gray):
    crop = np.random.default_rng(17).integers(0, 256, (96, 96, 3), dtype=np.uint8)
    path = tmp_path / "crop.png"
    Image.fromarray(crop).save(path)
    reference = load_image_tensor(path, 64)
    if gray:
        reference = functional.rgb_to_grayscale(reference, num_output_channels=3)
    np.testing.assert_array_equal(preprocess([crop], gray)[0], reference.numpy())


def test_disagreement_and_low_confidence_remain_review():
    calibration = {
        "rgb_temperature": 1.05,
        "gray_temperature": 1.25,
        "rgb_weight": 0.3,
        "threshold": 0.9,
    }
    rows = classify_logits(
        np.array([[10.0, 0], [10, 0], [0, 0]]),
        np.array([[10.0, 0], [0, 10], [0, 0]]),
        ["K", "Q"],
        calibration,
    )
    assert rows[0]["symbol_reasons"] == []
    assert "SYMBOL_MODEL_DISAGREEMENT" in rows[1]["symbol_reasons"]
    assert rows[2]["symbol_reasons"] == ["SYMBOL_LOW_CONFIDENCE"]
    with pytest.raises(ValueError, match="LOGITS_INVALID"):
        classify_logits(np.array([[float("nan"), 0]]), np.array([[0, 0]]), ["K", "Q"], calibration)


@pytest.mark.parametrize("name", ["seq_8-7.jpg", "seq_1-11.jpg", "bad.jpg", "seq_0-4.jpg"])
def test_invalid_filename_range_is_rejected(name):
    with pytest.raises(ValueError, match="FILENAME_RANGE_INVALID"):
        sequence_range(Path(name))


def test_source_and_training_pixel_drift(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("RGB", (100, 100), "blue").save(path)
    row = {"path": str(path), "sha256": sha(path)}
    image = load_photo(row, [])
    identity = digest([image.size, hashlib.sha256(image.tobytes()).hexdigest()])
    with pytest.raises(ValueError, match="TRAINING_PIXEL_DUPLICATE"):
        load_photo(row, [identity])
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SOURCE_DRIFT"):
        load_photo(row, [])


def durable_fixture(root):
    row = {"filename": "seq_1-1.jpg", "start": 1, "end": 1}
    payload = {"format": "mumie-symbol-batch-v1", "rows": [row], "live_bindings": {}}
    checked_publish(root / "manifest.json", payload)
    path = result_path(root, 0)
    content = b"visual-evidence"
    publish_file(path.parent / "atlas.jpg", content)
    result = {
        "batch_id": digest(payload),
        "row": row,
        "assets": {"atlas.jpg": hashlib.sha256(content).hexdigest()},
    }
    checked_publish(path, result)
    return payload


def test_lost_response_and_restart_do_not_recompute_or_duplicate(tmp_path):
    payload = durable_fixture(tmp_path)
    before = sha(result_path(tmp_path, 0))
    assert run(tmp_path) == {"complete": 1, "processed": 0, "total": 1}
    script = (
        "from pathlib import Path;"
        "from game_predictor_worker.vision_lab.symbol_batch import run;"
        "import sys,json;print(json.dumps(run(Path(sys.argv[1]))))"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(child.stdout) == {"complete": 1, "processed": 0, "total": 1}
    assert sha(result_path(tmp_path, 0)) == before
    assert validate_result(tmp_path, payload, 0)["row"] == payload["rows"][0]


def test_corrupted_published_visual_is_not_silently_skipped(tmp_path):
    payload = durable_fixture(tmp_path)
    (result_path(tmp_path, 0).parent / "atlas.jpg").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="ASSET_DRIFT"):
        validate_result(tmp_path, payload, 0)
    with pytest.raises(ValueError, match="ASSET_DRIFT"):
        run(tmp_path)


def test_input_and_conflicting_publication_fail_explicitly(tmp_path):
    path = tmp_path / "input.txt"
    path.write_bytes(b"source")
    payload = {"format": "mumie-symbol-batch-v1", "live_bindings": {str(path): sha(path)}}
    checked_publish(tmp_path / "manifest.json", payload)
    assert validate_batch(tmp_path) == payload
    with pytest.raises(ValueError, match="INTEGRITY_ERROR"):
        checked_publish(tmp_path / "manifest.json", {"different": True})
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        validate_batch(tmp_path)
