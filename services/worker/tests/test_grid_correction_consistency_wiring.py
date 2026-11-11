"""Exercise production precision and fresh export wiring without optimizer steps."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import torch
from game_predictor_worker.images import grid_rescue_evaluation as rescue
from game_predictor_worker.images import grid_training_child as child
from game_predictor_worker.images.grid_correction_consistency import CorrectionConsistencyError


@pytest.mark.parametrize("stage", ["screen", "board"])
@pytest.mark.parametrize("fails", [False, True])
def test_torch_engine_graph_call_disables_precision_flags_and_restores_them(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    fails: bool,
) -> None:
    observed = []

    class Graph:
        def __init__(self, _network: Any) -> None:
            pass

        def eval(self) -> Graph:
            return self

        def __call__(self, pixels: torch.Tensor) -> tuple[torch.Tensor, ...]:
            observed.append(
                (
                    torch.backends.cudnn.allow_tf32,
                    torch.backends.cuda.matmul.allow_tf32,
                    torch.is_autocast_enabled("cpu"),
                    torch.is_autocast_enabled("cuda"),
                )
            )
            if fails:
                raise RuntimeError("graph failed")
            return (pixels, pixels) if stage == "screen" else (pixels, pixels, pixels)

    monkeypatch.setattr(rescue, "ScreenExport", Graph)
    monkeypatch.setattr(rescue, "BoardExport", Graph)
    monkeypatch.setattr(rescue.DecodeSettings, "of", lambda _recipe: None)
    engine = rescue.torch_engine(SimpleNamespace(screen=None, board=None), None, "cpu")
    previous = torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = True
        with torch.autocast("cpu", dtype=torch.bfloat16):
            runner = getattr(engine, stage + "_runner")
            if fails:
                with pytest.raises(RuntimeError, match="graph failed"):
                    runner(np.zeros((1, 3, 32, 32), np.float32))
            else:
                runner(np.zeros((1, 3, 32, 32), np.float32))
            assert torch.is_autocast_enabled("cpu")
            assert torch.backends.cudnn.allow_tf32 and torch.backends.cuda.matmul.allow_tf32
        assert observed == [(False, False, False, False)]
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = previous


@pytest.mark.parametrize("fails", [False, True])
def test_fresh_export_publishes_full_proof_or_retains_failure_without_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fails: bool,
) -> None:
    from game_predictor_worker.geometry_core import inference
    from game_predictor_worker.images import grid_training_data
    from game_predictor_worker.training_core import grid_training

    def graphs(_network: Any, _recipe: Any, directory: Path, **_kwargs: Any) -> None:
        for stage in ("screen", "board"):
            (directory / f"{stage}.onnx").write_bytes(stage.encode())

    monkeypatch.setattr(grid_training, "export_graphs", graphs)
    monkeypatch.setattr(grid_training, "raw_parity", lambda *_: {"passed": True})
    monkeypatch.setattr(grid_training_data, "parity_inputs", lambda *_: (None, None))
    base = tmp_path / "base"
    base.mkdir()
    baseline = {"files": {"screen.onnx": "a" * 64, "board.onnx": "b" * 64}}
    baseline_bytes = json.dumps(baseline).encode()
    (base / "bundle.json").write_bytes(baseline_bytes)
    pinned = []

    def load_base(path: Path, **kwargs: Any) -> object:
        assert path == base
        assert kwargs["bundle_bytes"] == baseline_bytes
        assert kwargs["expected_bundle_sha256"] == child.sha256_bytes(baseline_bytes)
        pinned.append(True)
        return object()

    monkeypatch.setattr(inference, "onnx_engine", load_base)
    proof = {"passed": not fails, "reasonCodes": ["RAW_OUTPUT_DIFFERENCE"] if fails else []}
    invocations = []

    class Evaluator:
        def verify_export(self, _net: Any, directory: Path, *_args: Any, **kwargs: Any) -> Any:
            assert directory.name.startswith(".export-")
            assert (directory / "screen.onnx").is_file()
            assert kwargs["baseline_identity"] == {
                "bundleSha256": child.sha256_bytes(baseline_bytes),
                **baseline["files"],
            }
            invocations.append(True)
            if fails:
                raise CorrectionConsistencyError(proof)
            return proof

    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    result = SimpleNamespace(
        checkpoint_path=checkpoint,
        checkpoint_sha256="c" * 64,
        best_step=600,
        checkpoint_selection={"step": 600},
        history=[],
    )
    spec = {
        "artifactRoot": str(tmp_path),
        "jobId": "11111111-1111-4111-8111-111111111111",
        "base": {"managedDirectory": "base", "versionId": "base"},
        "preset": {"id": "grid-corrections-v1", "fingerprint": "d" * 64},
        "cohort": {"manifestSha256": "e" * 64},
    }
    destination = tmp_path / (child.EXPORT_PREFIX + "c" * 16)

    def export() -> dict[str, Any]:
        return child._export(
            spec,
            tmp_path,
            torch.nn.Linear(1, 1),
            None,
            {},
            b"{}",
            result,
            (None, None),
            correction_evaluator=Evaluator(),
        )

    if fails:
        with pytest.raises(child.ChildError, match="GRID_TRAINING_EVALUATION_INCONSISTENT"):
            export()
        assert not destination.exists()
        assert json.loads((tmp_path / "evaluation-consistency-failed.json").read_text()) == proof
    else:
        exported = export()
        bundle = json.loads((destination / "bundle.json").read_text())
        assert bundle["evaluationConsistency"] == proof
        assert exported["directory"] == destination.name
        assert not (tmp_path / "evaluation-consistency-failed.json").exists()
    assert not list(tmp_path.glob(".export-*"))
    assert pinned == invocations == [True]


@pytest.mark.parametrize("preset_id", ["grid-corrections-v1", "screen-grid-corrections-v1"])
def test_train_routes_correction_evaluator_only_to_grid_only_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preset_id: str,
) -> None:
    from game_predictor_worker.images import grid_cohort_dataset, grid_training_data
    from game_predictor_worker.training_core import (
        grid_rescue_training,
        grid_training,
        neural_grid_network,
    )

    preset = child.PRESETS[preset_id]
    recipe = json.loads(child.RECIPE_FILE.read_bytes())
    monkeypatch.setattr(child, "_base", lambda *_: (tmp_path / "unused.pt", recipe, None))
    monkeypatch.setattr(torch, "load", lambda *a, **k: {})
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    network = SimpleNamespace(load_state_dict=lambda _: None)
    monkeypatch.setattr(neural_grid_network, "NeuralGridNetwork", lambda _: network)
    snapshot = SimpleNamespace(
        manifest={
            "mode": preset.mode,
            "policyVersion": "application-grid-corrections-v3",
            "gameId": "g",
            "photoSplit": {},
        }
    )
    monkeypatch.setattr(grid_cohort_dataset, "GridCohortSnapshot", lambda *_: snapshot)
    monkeypatch.setattr(grid_training_data, "CohortPhotos", lambda *a, **k: object())
    monkeypatch.setattr(grid_training_data, "validation_crops", lambda *_: (None, None))
    batches = SimpleNamespace(close=lambda: None, exposure_members=lambda _: [])
    for name in ("GridOnlyBatches", "ScreenGridBatches"):
        monkeypatch.setattr(grid_training_data, name, lambda *a, **k: batches)
    correction, screen = object(), object()
    monkeypatch.setattr(grid_training_data, "correction_evaluator", lambda *a, **k: correction)
    monkeypatch.setattr(grid_training_data, "photo_evaluator", lambda *a, **k: screen)
    monkeypatch.setattr(grid_training_data, "board_evaluator", lambda *a, **k: object())
    monkeypatch.setattr(grid_training_data, "macro_evaluator", lambda *_: object())
    monkeypatch.setattr(grid_rescue_training, "selection_input", lambda *_: {"sha256": "a" * 64})
    monkeypatch.setattr(grid_rescue_training, "rescue_recipe", lambda *_: {})
    monkeypatch.setattr(grid_rescue_training, "require_recipe", lambda *_: None)
    monkeypatch.setattr(grid_rescue_training, "TrainingExposure", lambda *_: object())
    monkeypatch.setattr(grid_training.TrainingPlan, "of", lambda *_: SimpleNamespace(binding={}))
    monkeypatch.setattr(child, "ChildControl", lambda *_: object())
    result = SimpleNamespace(
        checkpoint_path=tmp_path / "checkpoint.pt",
        checkpoint_sha256="b" * 64,
        checkpoint_selection={"step": 600},
        history=[],
        best_step=600,
        best_metric=1.0,
        steps=600,
        stop_reason="completed",
    )
    trained = []

    def train(**kwargs: Any) -> Any:
        trained.append(kwargs["evaluate"])
        return result

    monkeypatch.setattr(grid_training, "train", train)
    monkeypatch.setattr(grid_training, "best_weights", lambda *_: {})
    calls = []
    monkeypatch.setattr(child, "_export", lambda *args, **kwargs: calls.append(kwargs) or {})
    spec = {
        "preset": {"id": preset_id, "fingerprint": preset.fingerprint},
        "seed": 1,
        "plannedSteps": 600,
        "requireCuda": False,
        "jobId": "job",
        "base": {"presetSha256": "c" * 64, "weightsSha256": "d" * 64},
        "cohort": {"manifestPath": "p", "manifestSha256": "e" * 64},
    }
    assert child._train(spec, tmp_path, tmp_path, None, None, {"step": 0})["status"] == "exported"
    if preset_id == "grid-corrections-v1":
        assert calls[0]["correction_evaluator"] is correction
        assert trained == [correction]
        assert "screen_evaluator" not in calls[0]
    else:
        assert calls[0]["correction_evaluator"] is None
        assert calls[0]["screen_evaluator"] is screen
        assert trained == [screen]
