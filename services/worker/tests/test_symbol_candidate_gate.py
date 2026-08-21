from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
from game_predictor_worker.images.symbol_classifier import (
    ClassifierSample,
    PreparedTrainingData,
    TrainingConfig,
)
from game_predictor_worker.images.symbol_model_benchmark import build_benchmark_model
from game_predictor_worker.images.symbol_onnx import LocalSymbolOnnxAdapter
from game_predictor_worker.symbols.candidate_gate import (
    SymbolCandidateGateConfiguration,
    SymbolModelBaseline,
    _regression_reasons,
    build_symbol_candidate,
)
from PIL import Image


def _sample(root: Path, name: str, *, class_index: int) -> ClassifierSample:
    path = root / "samples" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), (240, 40, 40) if class_index == 0 else (40, 40, 240)).save(path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return ClassifierSample(
        sample_id=name,
        asset_path=path,
        asset_checksum=checksum,
        source_image_checksum=hashlib.sha256(f"source-{name}".encode()).hexdigest(),
        symbol_code=("A", "B")[class_index],
        class_index=class_index,
    )


def _fixture(root: Path) -> tuple[Path, str, PreparedTrainingData, TrainingConfig]:
    model = build_benchmark_model("spatial", 2)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    checkpoint = root / "data" / "models" / "fixture" / "checkpoint.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"bestState": model.state_dict(), "modelState": model.state_dict()}, checkpoint)
    checksum = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    validation = (
        _sample(root, "validation-a", class_index=0),
        _sample(root, "validation-b", class_index=1),
    )
    test = (_sample(root, "test-b", class_index=1),)
    regression = (_sample(root, "regression-b", class_index=1),)
    data = PreparedTrainingData(
        dataset_sha256=hashlib.sha256(b"dataset").hexdigest(),
        split_sha256=hashlib.sha256(b"split").hexdigest(),
        split_seed="candidate-gate-test",
        class_codes=("A", "B"),
        class_ids=("symbol-a", "symbol-b"),
        train=(),
        validation=validation,
        test=test,
        regression=regression,
    )
    return checkpoint, checksum, data, TrainingConfig(input_size=16)


def test_candidate_gate_writes_checksum_bound_onnx_manifest_and_cpu_report(
    tmp_path: Path,
) -> None:
    checkpoint, checksum, data, config = _fixture(tmp_path)
    stages: list[str] = []

    result = build_symbol_candidate(
        artifact_root=tmp_path,
        candidate_root=tmp_path / "data" / "models" / "fixture" / "candidate",
        checkpoint_path=checkpoint,
        checkpoint_checksum=checksum,
        data=data,
        training_config=config,
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=0,
            minimum_macro_recall=0,
            performance_repetitions=1,
        ),
        stage=stages.append,
    )

    assert result.passed is True
    assert result.rejection_reasons == ()
    assert stages == ["onnx_export", "calibration", "evaluation", "manifest"]
    assert result.metrics["status"] == "candidate_ready"
    assert result.metrics["performance"]["cpuProvider"] == "CPUExecutionProvider"  # type: ignore[index]
    manifest_path = tmp_path.joinpath(*Path(result.manifest_relative_path).parts)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == result.manifest_checksum_sha256
    for artifact in manifest["artifacts"].values():
        path = tmp_path.joinpath(*Path(artifact["relativePath"]).parts)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    assert not (tmp_path / "data" / "models" / "active.json").exists()

    baseline_adapter = LocalSymbolOnnxAdapter(
        tmp_path.joinpath(*Path(result.onnx_relative_path).parts),
        expected_sha256=result.onnx_checksum_sha256,
        class_codes=data.class_codes,
        input_size=config.input_size,
    )
    compared = build_symbol_candidate(
        artifact_root=tmp_path,
        candidate_root=tmp_path / "data" / "models" / "fixture" / "compared",
        checkpoint_path=checkpoint,
        checkpoint_checksum=checksum,
        data=data,
        training_config=config,
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=0,
            minimum_macro_recall=0,
            performance_repetitions=1,
        ),
        baseline=SymbolModelBaseline(
            iteration_id="baseline-1",
            adapter=baseline_adapter,
            temperature=1.0,
        ),
    )
    assert compared.metrics["baseline"]["iterationId"] == "baseline-1"  # type: ignore[index]


def test_candidate_below_quality_threshold_is_rejected(tmp_path: Path) -> None:
    checkpoint, checksum, data, config = _fixture(tmp_path)

    result = build_symbol_candidate(
        artifact_root=tmp_path,
        candidate_root=tmp_path / "data" / "models" / "fixture" / "rejected",
        checkpoint_path=checkpoint,
        checkpoint_checksum=checksum,
        data=data,
        training_config=config,
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=1,
            minimum_macro_recall=1,
            performance_repetitions=1,
        ),
    )

    assert result.passed is False
    assert "TEST_ACCURACY_BELOW_MINIMUM" in result.rejection_reasons
    assert "REGRESSION_MACRO_RECALL_BELOW_MINIMUM" in result.rejection_reasons
    assert result.metrics["status"] == "rejected"


def test_per_symbol_regression_rejects_candidate_even_when_global_accuracy_improves() -> None:
    candidate = {
        "accuracy": 0.95,
        "macroRecall": 0.90,
        "perClass": [
            {"symbolCode": "A", "recall": 0.99},
            {"symbolCode": "B", "recall": 0.70},
        ],
    }
    baseline = {
        "accuracy": 0.90,
        "macroRecall": 0.90,
        "perClass": [
            {"symbolCode": "A", "recall": 0.90},
            {"symbolCode": "B", "recall": 0.90},
        ],
    }

    reasons = _regression_reasons(
        candidate,
        baseline,
        SymbolCandidateGateConfiguration(
            minimum_accuracy=0,
            minimum_macro_recall=0,
            maximum_per_symbol_recall_regression=0.05,
        ),
        "regression",
    )

    assert reasons == ["REGRESSION_SYMBOL_RECALL_REGRESSION:B"]
