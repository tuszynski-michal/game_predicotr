"""TF32 threshold regression and all-A raw/decision/export guards."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import torch
from game_predictor_worker.images import grid_correction_consistency as consistency
from game_predictor_worker.images import grid_training_child as child
from game_predictor_worker.training_core.evaluation_precision import evaluation_precision


def nodes() -> np.ndarray:
    return np.array([(x * 10, y * 10) for y in range(4) for x in range(6)], np.float32)


class Engine:
    def __init__(self, screen: Any, board: Any, settings: Any = None) -> None:
        self.screen_runner, self.board_runner, self.settings = screen, board, settings

    def analyse(self, rgb: np.ndarray) -> list[Any]:
        self.screen_runner(rgb)
        found = self.board_runner(rgb)[0]
        return [SimpleNamespace(nodes=found)]


class Network:
    def to(self, _device: str) -> Network:
        return self

    def eval(self) -> Network:
        return self


class Photos:
    role = "VALIDATION"
    snapshot = SimpleNamespace(manifest={"gameId": "g"}, manifest_sha256="a" * 64)

    def __init__(self, size: int = 13) -> None:
        self.rows = [({"sourceId": str(i), "screenEligible": False}, []) for i in range(size)]
        self.loads: list[int] = []

    def rgb(self, index: int) -> np.ndarray:
        self.loads.append(index)
        return np.full((2, 2, 3), index, np.uint8)

    def targets(self, _index: int) -> list[Any]:
        return [(nodes(), 0)]


def setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reference_error: float = 0.0,
    runtime_error: float = 0.0,
) -> tuple[consistency.CorrectionEvaluator, Photos]:
    diagonal = float(np.linalg.norm(nodes()[-1] - nodes()[0]))

    def board(error: float, pixels: np.ndarray) -> tuple[np.ndarray, ...]:
        delta = error * diagonal if int(pixels.flat[0]) == 12 else 0
        return nodes() + [delta, 0], np.ones(24, np.float32), np.ones(15, np.float32)

    reference = Engine(lambda p: (p.astype(np.float32),), lambda p: board(reference_error, p))
    monkeypatch.setattr(consistency, "torch_engine", lambda *_: reference)
    monkeypatch.setattr(consistency, "NeuralGridEngine", Engine)

    class Session:
        def __init__(self, filename: str, **_kwargs: Any) -> None:
            self.stage = Path(filename).stem

        def run(self, _outputs: Any, values: dict[str, Any]) -> Any:
            pixels = next(iter(values.values()))
            return (
                (pixels.astype(np.float32),)
                if self.stage == "screen"
                else board(runtime_error, pixels)
            )

    import onnxruntime

    monkeypatch.setattr(onnxruntime, "InferenceSession", Session)
    for stage in ("screen", "board"):
        (tmp_path / f"{stage}.onnx").write_bytes(stage.encode())
    photos = Photos()
    return consistency.CorrectionEvaluator([photos], None, "cpu"), photos


def test_precision_restores_process_defaults_after_exception_and_disables_autocast() -> None:
    previous = torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cuda.matmul.allow_tf32 = True
        with (
            pytest.raises(RuntimeError),
            torch.autocast("cpu", dtype=torch.bfloat16),
            evaluation_precision(),
        ):
            assert not torch.backends.cudnn.allow_tf32
            assert not torch.backends.cuda.matmul.allow_tf32
            assert not torch.is_autocast_enabled("cpu")
            raise RuntimeError("runner failed")
        assert torch.backends.cudnn.allow_tf32 and torch.backends.cuda.matmul.allow_tf32
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = previous


def test_full_a_includes_last_partial_photo_and_all_actual_graph_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator, photos = setup(tmp_path, monkeypatch)
    metrics = evaluator(Network())
    proof = evaluator.verify_export(Network(), tmp_path, {"step": 600, "metrics": metrics}, [])
    assert proof["passed"]
    assert len(proof["onnx"]["photos"]) == 13
    assert len(proof["inputs"]) == 26
    assert set(photos.loads) == set(range(13))
    assert {r["stage"] for r in proof["inputs"]} == {"screen", "board"}


def test_raw_tolerance_cannot_hide_last_photo_threshold_crossing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator, _ = setup(tmp_path, monkeypatch, reference_error=0.0199999, runtime_error=0.0200001)
    metrics = evaluator(Network())
    with pytest.raises(consistency.CorrectionConsistencyError) as caught:
        evaluator.verify_export(Network(), tmp_path, {"step": 600, "metrics": metrics}, [])
    proof = caught.value.proof
    assert all(record["verdict"]["passed"] for record in proof["inputs"])
    assert proof["mismatchedSources"] == ["12"]
    assert "MATCHING_OR_BOARD_VERDICT_DIFFERENCE" in proof["reasonCodes"]


def test_raw_difference_blocks_even_without_correctness_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator, _ = setup(tmp_path, monkeypatch, runtime_error=0.001)
    metrics = evaluator(Network())
    with pytest.raises(consistency.CorrectionConsistencyError) as caught:
        evaluator.verify_export(Network(), tmp_path, {"step": 600, "metrics": metrics}, [])
    assert "RAW_OUTPUT_DIFFERENCE" in caught.value.proof["reasonCodes"]
    assert not caught.value.proof["mismatchedSources"]


def test_small_error_change_must_not_reverse_checkpoint_preference() -> None:
    selected = {"step": 600, "metrics": {"boardCorrectRate": 1.0, "normalizedError": 0.01}}
    history = [
        {
            "step": 1200,
            "selectionMetrics": {"boardCorrectRate": 1.0, "normalizedError": 0.010000001},
        }
    ]
    assert not consistency.checkpoint_order_preserved(
        selected, history, {"boardCorrectRate": 1.0, "normalizedError": 0.010000002}
    )
    assert consistency.checkpoint_order_preserved(
        selected, history, {"boardCorrectRate": 1.0, "normalizedError": 0.009999999}
    )


def test_numerical_delta_cannot_flip_validation_nonregression_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator, _ = setup(tmp_path, monkeypatch, reference_error=0.0099999, runtime_error=0.0100001)
    metrics = evaluator(Network())
    diagonal = float(np.linalg.norm(nodes()[-1] - nodes()[0]))
    baseline = Engine(
        lambda p: (p,),
        lambda p: (nodes() + ([0.01 * diagonal, 0] if int(p.flat[0]) == 12 else [0, 0]),),
    )
    with pytest.raises(consistency.CorrectionConsistencyError) as caught:
        evaluator.verify_export(
            Network(), tmp_path, {"step": 600, "metrics": metrics}, [], baseline=baseline
        )
    assert all(row["verdict"]["passed"] for row in caught.value.proof["inputs"])
    assert not caught.value.proof["mismatchedSources"]
    assert "VALIDATION_NONREGRESSION_VERDICT_DIFFERENCE" in caught.value.proof["reasonCodes"]


def test_recovery_identity_binds_every_source_and_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator, _ = setup(tmp_path, monkeypatch)
    metrics = evaluator(Network())
    proof = evaluator.verify_export(Network(), tmp_path, {"step": 600, "metrics": metrics}, [])
    original = consistency.proof_binding(proof)
    proof["onnx"]["photos"][-1]["labelsSha256"] = "b" * 64
    assert consistency.proof_binding(proof) != original


def test_partial_or_regression_role_never_enters_checkpoint_controls() -> None:
    photos = Photos()
    photos.role = "REGRESSION"
    with pytest.raises(ValueError, match="VALIDATION_ONLY"):
        consistency.CorrectionEvaluator([photos], None, "cpu")
    assert photos.loads == []


def test_equal_counts_do_not_hide_target_assignment_or_verdict_swap() -> None:
    photo = {
        key: 1
        for key in (
            "expected",
            "predicted",
            "matched",
            "correct",
            "full_geometry",
            "false_boards",
            "duplicates",
            "complete_correct_strict",
        )
    }
    photo["matches"] = [{"prediction": 0, "label": 0, "valid": True, "correct": True}]
    swapped = {**photo, "matches": [{"prediction": 1, "label": 0, "valid": True, "correct": True}]}
    assert consistency.discrete_outcome(photo) != consistency.discrete_outcome(swapped)


def test_consistency_failure_is_durable_and_keeps_export_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game_predictor_worker.geometry_core import inference

    monkeypatch.setattr(inference, "onnx_engine", lambda _path, **_kwargs: None)
    base = tmp_path / "base"
    base.mkdir()
    (base / "bundle.json").write_text(
        json.dumps(
            {
                "files": {"screen.onnx": "a" * 64, "board.onnx": "b" * 64},
            }
        )
    )
    proof = {"passed": False, "reasonCodes": ["CHECKPOINT_PREFERENCE_DIFFERENCE"]}

    class Evaluator:
        def verify_export(self, *args: Any, **kwargs: Any) -> Any:
            raise consistency.CorrectionConsistencyError(proof)

    result = SimpleNamespace(checkpoint_selection={"step": 600}, history=[])
    spec = {"artifactRoot": str(tmp_path), "base": {"managedDirectory": "base"}}
    with pytest.raises(child.ChildError, match="EVALUATION_INCONSISTENT"):
        child._correction_consistency(Evaluator(), Network(), tmp_path, result, tmp_path, spec)
    assert json.loads((tmp_path / "evaluation-consistency-failed.json").read_text()) == proof


@pytest.mark.parametrize("change", [None, "missing", "labels", "baseline", "checksum"])
def test_export_recovery_requires_current_full_a_proof_without_rewriting_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str | None,
) -> None:
    import copy

    from game_predictor_api.domain import grid_visibility_contract

    evaluator, _ = setup(tmp_path, monkeypatch)
    metrics = evaluator(Network())
    proof = evaluator.verify_export(Network(), tmp_path, {"step": 600, "metrics": metrics}, [])
    fresh = copy.deepcopy(proof)
    if change == "labels":
        fresh["onnx"]["photos"][-1]["labelsSha256"] = "c" * 64
    if change == "baseline":
        fresh["baselineIdentity"] = {"bundleSha256": "d" * 64}
    bundle = {"provenance": {"checkpointSha256": "a" * 64}, "evaluationConsistency": proof}
    if change == "missing":
        del bundle["evaluationConsistency"]
    if change == "checksum":
        bundle["evaluationConsistency"]["selectedStep"] = 601
    destination = tmp_path / (child.EXPORT_PREFIX + "a" * 16)
    destination.mkdir()
    document = destination / "bundle.json"
    document.write_text(json.dumps(bundle))
    before = document.read_bytes()
    monkeypatch.setattr(child, "_verify_recovered", lambda *_: None)
    monkeypatch.setattr(child, "_correction_consistency", lambda *_: fresh)
    monkeypatch.setattr(child, "_export_view", lambda *_: {"recovered": True})
    monkeypatch.setattr(grid_visibility_contract, "require_output_contract", lambda *a, **k: None)
    result = SimpleNamespace(checkpoint_sha256="a" * 64, checkpoint_path=tmp_path / "ckpt.pt")

    def recover() -> Any:
        return child._export(
            {},
            tmp_path,
            Network(),
            None,
            {},
            b"",
            result,
            (None, None),
            correction_evaluator=evaluator,
        )

    if change is None:
        assert recover() == recover() == {"recovered": True}
    else:
        with pytest.raises(child.ChildError, match="EVALUATION_PROOF_"):
            recover()
    assert document.read_bytes() == before
