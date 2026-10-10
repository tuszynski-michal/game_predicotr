"""TASK-0804: target evaluation, sealed single-use holdout reads and the unchanged role guard."""

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.vision_lab import grid_v3_comparison as comparison
from game_predictor_worker.vision_lab import grid_v3_sealed as sealed
from game_predictor_worker.vision_lab.hybrid_v3_calibration import load_calibration_samples
from game_predictor_worker.vision_lab.neural_grid_data import grid_from_quad, load_samples
from game_predictor_worker.vision_lab.neural_grid_protocol import RoleForbiddenError

VISION_LAB = Path(comparison.__file__).resolve().parent


def _quad(x: float, y: float, w: float = 90.0, h: float = 50.0) -> np.ndarray:
    return np.array([[x, y], [x + w, y + 1], [x + w - 1, y + h], [x + 1, y + h - 1]], np.float32)


def _grid(x: float, y: float) -> np.ndarray:
    return grid_from_quad(_quad(x, y))


def _photo(labels, targets, *, complete=True, photo_metric=None, group="g"):
    return comparison.EvalPhoto(
        image_id="photo",
        group=group,
        load=lambda: np.zeros((10, 10, 3), np.uint8),
        labels=tuple(labels),
        targets=tuple(targets),
        labels_complete=complete,
        photo_metric=complete and len(targets) == len(labels)
        if photo_metric is None
        else photo_metric,
    )


# --- the training / calibration guard is unchanged ---------------------------------------------


@pytest.mark.parametrize("role", ["gold", "final_test", "unseen_game"])
def test_training_and_calibration_loaders_still_refuse_sealed_roles(tmp_path, role):
    with pytest.raises(RoleForbiddenError):
        load_samples(tmp_path / "missing", (role,))
    with pytest.raises(RoleForbiddenError):
        load_calibration_samples(tmp_path / "missing", (role,))


@pytest.mark.parametrize(
    "module",
    [
        "neural_grid_training.py",
        "neural_grid_finetune.py",
        "neural_grid_runs.py",
        "neural_grid_data.py",
        "neural_grid_onnx.py",
        "neural_grid_protocol.py",
        "hybrid_v3_calibration.py",
        "grid_v3_comparison.py",
        "assisted_annotation.py",
    ],
)
def test_training_calibration_and_comparison_code_never_imports_the_sealed_reader(module):
    tree = ast.parse((VISION_LAB / module).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("grid_v3_sealed" in name for name in imported)


# --- the sealed ledger ----------------------------------------------------------------------


def _identity(run1="w1", run2="w2", iter3="w3"):
    return {
        "models": {
            "run1": {"weights_sha256": run1},
            "run2": {"weights_sha256": run2},
            "iter3": {"weights_sha256": iter3},
        },
        "originals_sha256": "originals",
        "hybrid": {"network": "run1", "thresholds": {"a": 1}, "gate_version": "g"},
    }


def test_sealed_read_requires_confirmation_and_is_recorded_before_reading(tmp_path):
    ledger = sealed.SealedLedger(tmp_path)
    with pytest.raises(sealed.SealedReadError, match="NOT_CONFIRMED"):
        ledger.begin("gold", _identity(), confirm=False)
    with pytest.raises(sealed.SealedReadError, match="HOLDOUT_UNKNOWN"):
        ledger.begin("development", _identity(), confirm=True)
    token = ledger.begin("gold", _identity(), confirm=True)
    entry = ledger.read()["reads"][0]
    assert entry["status"] == "started" and entry["holdout"] == "gold"
    assert set(entry["model_keys"]) == {"run1", "run2", "iter3", "production", "hybrid"}
    ledger.complete(token, {"summary.json": "abc"})
    entry = ledger.read()["reads"][0]
    assert entry["status"] == "completed" and entry["outputs"] == {"summary.json": "abc"}


def test_second_read_of_a_holdout_by_a_frozen_model_is_refused(tmp_path):
    ledger = sealed.SealedLedger(tmp_path)
    ledger.begin("final_test", _identity(), confirm=True)  # started, never completed (crash)
    with pytest.raises(sealed.SealedReadError, match="REPEATED:final_test:iter3,run1,run2"):
        ledger.begin("final_test", _identity(), confirm=True)
    with pytest.raises(sealed.SealedReadError, match="REPEATED:final_test:run1"):
        ledger.begin("final_test", _identity(run2="new", iter3="new3"), confirm=True)
    with pytest.raises(sealed.SealedReadError, match="REPEATED"):
        ledger.begin("final_test", _identity(), confirm=True, force_reason="  ")
    # Another holdout, or new models only, are separate reads.
    ledger.begin("unseen_game", _identity(), confirm=True)
    ledger.begin("final_test", _identity("a", "b", "c"), confirm=True)
    forced = ledger.begin("final_test", _identity(), confirm=True, force_reason="crash at decode")
    entry = next(e for e in ledger.read()["reads"] if e["read_id"] == forced.read_id)
    assert entry["forced"] is True and entry["force_reason"] == "crash at decode"


def test_inspection_reopens_only_a_completed_read_and_is_recorded(tmp_path):
    ledger = sealed.SealedLedger(tmp_path)
    token = ledger.begin("gold", _identity(), confirm=True)
    with pytest.raises(sealed.SealedReadError, match="INSPECTION_WITHOUT_READ"):
        ledger.begin_inspection(token.read_id, "taxonomy")
    ledger.complete(token, {})
    with pytest.raises(sealed.SealedReadError, match="PURPOSE_REQUIRED"):
        ledger.begin_inspection(token.read_id, " ")
    inspection = ledger.begin_inspection(token.read_id, "taxonomy")
    assert inspection.holdout == "gold" and inspection.read_id != token.read_id
    with pytest.raises(sealed.SealedReadError, match="INSPECTION_WITHOUT_READ"):
        ledger.begin_inspection(inspection.read_id, "again")
    ledger.complete(inspection, {"overviews": "1"})
    entries = ledger.read()["reads"]
    assert [e["status"] for e in entries] == ["completed", "inspected"]
    assert entries[1]["of"] == token.read_id and entries[1]["model_keys"] == {}
    with pytest.raises(sealed.SealedReadError, match="REPEATED"):
        ledger.begin("gold", _identity(), confirm=True)


def test_sealed_loaders_need_a_ledger_token_for_their_own_holdout(tmp_path):
    forged = sealed.SealedRead("gold", "gold-001", object())
    with pytest.raises(sealed.SealedReadError, match="TOKEN_INVALID"):
        sealed.load_gold(forged, tmp_path)
    token = sealed.SealedLedger(tmp_path / "ledger").begin("unseen_game", _identity(), confirm=True)
    with pytest.raises(sealed.SealedReadError, match="WRONG_HOLDOUT"):
        sealed.load_gold(token, tmp_path)
    with pytest.raises(sealed.SealedReadError, match="WRONG_HOLDOUT"):
        sealed.load_lab_holdout(token, "final_test")
    with pytest.raises(sealed.SealedReadError, match="WRONG_HOLDOUT"):
        sealed.load_mumie_holdout(token, tmp_path / "plan.json")
    # The token-free loader cores used by the rehearsal refuse every held-out part.
    for partition in sealed.LAB_PARTITIONS:
        with pytest.raises(sealed.SealedReadError, match="TOKEN_REQUIRED"):
            sealed._lab_partition(partition, tmp_path / "m.json", tmp_path, tmp_path)
    with pytest.raises(sealed.SealedReadError, match="TOKEN_REQUIRED"):
        sealed._mumie_photos(tmp_path / "plan.json", "development", "holdout_ids")
    with pytest.raises(sealed.SealedReadError, match="TOKEN_INVALID"):
        sealed._lab_partition("unseen_game", tmp_path / "m.json", tmp_path, tmp_path, forged)
    with pytest.raises(sealed.SealedReadError, match="WRONG_HOLDOUT"):
        sealed._lab_partition("final_test", tmp_path / "m.json", tmp_path, tmp_path, token)


def _gold_snapshot(tmp_path):
    g, u = _grid(10, 10).tolist(), _grid(150, 10).tolist()
    rows = {
        "dev": ("development", None),
        "gold-mixed": ("gold", [("G", True, g), ("U", False, u)]),
        "gold-all": ("gold", [("G", True, g), ("G", True, u)]),
        "gold-twin": ("gold", [("S", False, g)]),
    }
    lines, selection, files = [], [], {}
    for image_id, (role, boards) in rows.items():
        checksum = hashlib.sha256(image_id.encode()).hexdigest()
        selection.append([image_id, role, checksum, ".jpg"])
        relative = f"images/{checksum[:2]}/{checksum}.jpg"
        files[relative] = checksum
        row = {
            "imageId": image_id,
            "role": role,
            "imageLevel": "G",
            "coordinateSpace": "exif-normalized-rgb-pixels-v1",
            "imagePath": relative,
            "sourceChecksumSha256": checksum,
            "orientedWidth": 400,
            "orientedHeight": 300,
            "familyId": "family",
            "familySeenInTraining": image_id == "gold-all",
            "goldBasis": "g",
            "expectedBoardsOnImage": len(boards or []),
            "boards": [
                {"nodes": nodes, "level": level, "evaluationTarget": target, "positionIndex": i}
                for i, (level, target, nodes) in enumerate(boards or [])
            ],
        }
        lines.append(json.dumps(row).encode() + b"\n")
    samples = b"".join(lines)
    split = json.dumps(
        {
            "selectionColumns": ["imageId", "role", "sourceChecksumSha256", "suffix"],
            "selection": selection,
        }
    ).encode()
    files["samples.jsonl"] = hashlib.sha256(samples).hexdigest()
    files["split.json"] = hashlib.sha256(split).hexdigest()
    root = tmp_path / ("b" * 64)
    root.mkdir()
    (root / "samples.jsonl").write_bytes(samples)
    (root / "split.json").write_bytes(split)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "format": "production-geometry-snapshot-v1",
                "snapshotId": "b" * 64,
                "policy": {"policyVersion": "production-geometry-split-v2"},
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return root


def test_gold_loader_scores_g_boards_and_knows_u_boards(tmp_path):
    root = _gold_snapshot(tmp_path)
    token = sealed.SealedLedger(tmp_path / "ledger").begin("gold", _identity(), confirm=True)
    photos = {p.image_id: p for p in sealed.load_gold(token, root)}
    assert set(photos) == {"gold-all", "gold-mixed"}  # development and the twin are not returned
    mixed, whole = photos["gold-mixed"], photos["gold-all"]
    assert (len(mixed.labels), mixed.targets, mixed.photo_metric) == (2, (0,), False)
    assert (whole.targets, whole.photo_metric, whole.group) == ((0, 1), True, "seen")
    assert mixed.group == "unseen" and mixed.labels_complete
    (root / "samples.jsonl").write_bytes((root / "samples.jsonl").read_bytes() + b"\n")
    with pytest.raises(sealed.SealedReadError, match="CHECKSUM"):
        sealed.load_gold(token, root)


# --- target evaluation ----------------------------------------------------------------------


def test_prediction_on_a_known_unscored_board_is_neither_scored_nor_false():
    target, unscored = _grid(10, 10), _grid(150, 10)
    photo = _photo([target, unscored], [0], photo_metric=False)
    result = comparison.evaluate_targets(photo, [(target, True), (unscored, True)])
    assert [t["correct"] for t in result["targets"]] == [True]
    assert result["false_boards"] == 0 and result["complete_correct"] is None
    outside = comparison.evaluate_targets(photo, [(target, True), (_grid(300, 200), True)])
    assert outside["false_boards"] == 1


def test_partial_labels_ignore_unmatched_predictions_and_have_no_photo_metric():
    labelled = _grid(10, 10)
    photo = _photo([labelled], [0], complete=False)
    shifted = labelled + np.array([3.0, 0.0], np.float32)
    result = comparison.evaluate_targets(photo, [(shifted, True), (_grid(300, 200), True)])
    assert result["false_boards"] is None and result["complete_correct"] is None
    assert result["targets"][0]["matched"] and not result["targets"][0]["correct"]
    summary = comparison.summarize_results([result])
    assert summary["photo_complete_correct_rate"] is None and summary["false_boards"] is None
    assert summary["boards_correct"] == 0 and summary["detection_recall"] == 1.0


def test_missing_target_costs_one_in_image_macro_and_breaks_the_photo():
    a, b = _grid(10, 10), _grid(150, 10)
    result = comparison.evaluate_targets(_photo([a, b], [0, 1]), [(a, True)])
    assert result["macro_cost"] == pytest.approx(0.5)
    assert result["complete_correct"] is False


def test_hybrid_counts_a_wrong_confident_board_and_confident_false_board():
    a, b = _grid(10, 10), _grid(150, 10)
    shifted = a + np.array([6.0, 0.0], np.float32)
    photo = _photo([a, b], [0, 1])
    result = comparison.evaluate_targets(
        photo,
        [(shifted, True), (b, True), (_grid(300, 200), True)],
        ["confident", "needs_review", "confident"],
    )
    result["photo_state"] = "confident"
    hybrid = comparison.summarize_hybrid([result])
    assert hybrid["confident_boards_wrong"] == 2  # the wrong target and the false board
    assert hybrid["confident_photos_with_wrong_scored_board"] == 1


def test_original_reference_keeps_boards_without_grid_as_explicit_missing():
    row = {
        "status": "present",
        "boards": [
            {"positionIndex": 0, "nodes": _grid(10, 10).tolist()},
            {"positionIndex": 1, "nodes": None},
        ],
    }
    reference = comparison.original_reference(row)
    assert [r.nodes is None for r in reference] == [False, True]
    assert len(comparison.predictions_of_reference(reference)) == 1
    decision = comparison.hybrid_decision(row, [])
    assert decision.state == "needs_review"
    assert comparison.original_reference({"status": "missing"}) == []


def test_wilson_interval():
    assert comparison.wilson(0, 0) is None
    low, high = comparison.wilson(7, 5335)
    assert low == pytest.approx(0.000636, abs=2e-5) and high == pytest.approx(0.00270, abs=5e-5)
