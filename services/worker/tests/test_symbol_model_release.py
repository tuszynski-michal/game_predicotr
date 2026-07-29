from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import onnx
import pytest
import torch
from game_predictor_worker.images.symbol_classifier import PREPROCESSING_VERSION
from game_predictor_worker.images.symbol_model_benchmark import (
    BENCHMARK_VERSION,
    NO_AUGMENTATION_VERSION,
    SPATIAL_ARCHITECTURE_VERSION,
    SPATIAL_VARIANT,
    SpatialSymbolCnn,
)
from game_predictor_worker.images.symbol_model_release import (
    MAX_SYMBOL_ALTERNATIVES,
    SPATIAL_MODEL_VERSION,
    SPATIAL_ONNX_MODEL_VERSION,
    SPATIAL_RELEASE_VERSION,
    SymbolModelReleaseError,
    build_symbol_predictions,
    load_spatial_model_checkpoint,
    validate_release_manifest,
)
from game_predictor_worker.images.symbol_onnx import (
    MAX_PARITY_ABSOLUTE_ERROR,
    LocalSymbolOnnxAdapter,
    export_symbol_classifier_onnx,
)

DATASET_SHA = "1" * 64
SPLIT_SHA = "2" * 64
CLASS_CODES = ("a", "b", "c", "d", "e")


def _checkpoint(tmp_path: Path) -> tuple[Path, str]:
    torch.manual_seed(105)
    path = tmp_path / "spatial.pt"
    torch.save(
        {
            "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
            "augmentationVersion": NO_AUGMENTATION_VERSION,
            "benchmarkVersion": BENCHMARK_VERSION,
            "candidateVariant": SPATIAL_VARIANT,
            "classCodes": list(CLASS_CODES),
            "config": {"inputSize": 64, "seed": 61061},
            "datasetSha256": DATASET_SHA,
            "splitSha256": SPLIT_SHA,
            "stateDict": SpatialSymbolCnn(len(CLASS_CODES)).state_dict(),
        },
        path,
    )
    content = path.read_bytes()
    return path, hashlib.sha256(content).hexdigest()


def test_selected_spatial_checkpoint_loads_with_exact_provenance(tmp_path: Path) -> None:
    path, checksum = _checkpoint(tmp_path)

    loaded = load_spatial_model_checkpoint(
        path,
        expected_sha256=checksum,
        expected_dataset_sha256=DATASET_SHA,
        expected_split_sha256=SPLIT_SHA,
        expected_class_codes=CLASS_CODES,
    )

    assert loaded.class_codes == CLASS_CODES
    assert loaded.input_size == 64
    assert loaded.checkpoint_sha256 == checksum
    assert loaded.logical_state_sha256
    assert loaded.model.training is False


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"expected_sha256": "f" * 64}, "SYMBOL_MODEL_CHECKPOINT_DRIFT"),
        (
            {"expected_dataset_sha256": "f" * 64},
            "SYMBOL_MODEL_CHECKPOINT_PROVENANCE_DRIFT",
        ),
        (
            {"expected_class_codes": ("b", "a", "c", "d", "e")},
            "SYMBOL_MODEL_CHECKPOINT_CLASS_DRIFT",
        ),
    ],
)
def test_selected_checkpoint_drift_fails_closed(
    tmp_path: Path,
    override: dict[str, object],
    code: str,
) -> None:
    path, checksum = _checkpoint(tmp_path)
    values: dict[str, object] = {
        "expected_sha256": checksum,
        "expected_dataset_sha256": DATASET_SHA,
        "expected_split_sha256": SPLIT_SHA,
        "expected_class_codes": CLASS_CODES,
    }
    values.update(override)

    with pytest.raises(SymbolModelReleaseError) as error:
        load_spatial_model_checkpoint(path, **values)  # type: ignore[arg-type]

    assert error.value.code == code


def test_predictions_have_stable_bounded_alternatives() -> None:
    logits = np.asarray(
        [
            [1.0, 1.0, 0.4, 2.0, -1.0],
            [0.0, 0.0, 0.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )

    first = build_symbol_predictions(
        logits,
        temperature=1.0,
        class_codes=CLASS_CODES,
    )
    second = build_symbol_predictions(
        logits,
        temperature=1.0,
        class_codes=CLASS_CODES,
    )

    assert first == second
    assert first[0].symbol_code == "d"
    assert [row.symbol_code for row in first[0].alternatives] == ["d", "a", "b", "c"]
    assert [row.symbol_code for row in first[1].alternatives] == ["a", "b", "c", "d"]
    assert all(len(row.alternatives) == MAX_SYMBOL_ALTERNATIVES for row in first)


def test_spatial_onnx_export_matches_pytorch(tmp_path: Path) -> None:
    path, checksum = _checkpoint(tmp_path)
    loaded = load_spatial_model_checkpoint(
        path,
        expected_sha256=checksum,
        expected_dataset_sha256=DATASET_SHA,
        expected_split_sha256=SPLIT_SHA,
        expected_class_codes=CLASS_CODES,
    )
    content = export_symbol_classifier_onnx(
        loaded.model,
        input_size=64,
        class_count=len(CLASS_CODES),
        model_version=SPATIAL_ONNX_MODEL_VERSION,
    )
    onnx_path = tmp_path / "spatial.onnx"
    onnx_path.write_bytes(content)
    adapter = LocalSymbolOnnxAdapter(
        onnx_path,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        class_codes=CLASS_CODES,
        input_size=64,
    )
    images = np.random.default_rng(105).normal(size=(3, 3, 64, 64)).astype(np.float32)

    actual = adapter.infer(images)
    with torch.inference_mode():
        expected = loaded.model(torch.from_numpy(images)).numpy()

    assert onnx.load_model_from_string(content).producer_version == SPATIAL_ONNX_MODEL_VERSION
    assert np.max(np.abs(actual.logits - expected)) < MAX_PARITY_ABSOLUTE_ERROR
    assert np.array_equal(actual.class_indexes, np.argmax(expected, axis=1))


def test_release_manifest_binds_exact_artifact_set(tmp_path: Path) -> None:
    artifacts: dict[str, dict[str, str]] = {}
    for name in (
        "checkpoint",
        "onnx",
        "onnxReport",
        "calibrationReport",
        "verticalSliceReport",
        "decisionReport",
    ):
        path = tmp_path / f"{name}.bin"
        content = name.encode()
        path.write_bytes(content)
        artifacts[name] = {
            "relativePath": path.name,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    manifest = {
        "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
        "artifacts": artifacts,
        "classes": list(CLASS_CODES),
        "modelVersion": SPATIAL_MODEL_VERSION,
        "onnxModelVersion": SPATIAL_ONNX_MODEL_VERSION,
        "preprocessingVersion": PREPROCESSING_VERSION,
        "releaseVersion": SPATIAL_RELEASE_VERSION,
    }

    resolved = validate_release_manifest(manifest, repository_root=tmp_path)
    (tmp_path / "onnx.bin").write_bytes(b"drift")

    assert set(resolved) == set(artifacts)
    with pytest.raises(SymbolModelReleaseError) as error:
        validate_release_manifest(manifest, repository_root=tmp_path)
    assert error.value.code == "SYMBOL_MODEL_RELEASE_ARTIFACT_DRIFT"
