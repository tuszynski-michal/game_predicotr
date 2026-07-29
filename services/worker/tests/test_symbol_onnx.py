from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch
from game_predictor_worker.images.symbol_classifier import SmallSymbolCnn
from game_predictor_worker.images.symbol_onnx import (
    MAX_PARITY_ABSOLUTE_ERROR,
    LocalSymbolOnnxAdapter,
    SymbolOnnxError,
    export_symbol_classifier_onnx,
)


def _artifact(tmp_path: Path) -> tuple[SmallSymbolCnn, Path, str]:
    torch.manual_seed(62)
    model = SmallSymbolCnn(3)
    content = export_symbol_classifier_onnx(
        model,
        input_size=64,
        class_count=3,
    )
    path = tmp_path / "model.onnx"
    path.write_bytes(content)
    return model, path, hashlib.sha256(content).hexdigest()


def test_export_is_byte_deterministic_and_dynamic_batch_matches_pytorch(
    tmp_path: Path,
) -> None:
    model, path, checksum = _artifact(tmp_path)
    second = export_symbol_classifier_onnx(
        model,
        input_size=64,
        class_count=3,
    )
    adapter = LocalSymbolOnnxAdapter(
        path,
        expected_sha256=checksum,
        class_codes=("a", "b", "c"),
        input_size=64,
    )
    generator = np.random.default_rng(62)
    images = generator.normal(size=(4, 3, 64, 64)).astype(np.float32)

    result = adapter.infer(images)
    single = adapter.infer(images[:1])
    with torch.inference_mode():
        expected_logits = model(torch.from_numpy(images)).numpy()
        expected_probabilities = torch.softmax(
            torch.from_numpy(expected_logits),
            dim=1,
        ).numpy()

    assert second == path.read_bytes()
    assert result.logits.shape == (4, 3)
    assert single.logits.shape == (1, 3)
    assert np.max(np.abs(result.logits - expected_logits)) < MAX_PARITY_ABSOLUTE_ERROR
    assert np.max(np.abs(result.probabilities - expected_probabilities)) < MAX_PARITY_ABSOLUTE_ERROR
    assert np.array_equal(
        result.class_indexes,
        np.argmax(expected_logits, axis=1),
    )


def test_artifact_checksum_drift_is_rejected(tmp_path: Path) -> None:
    _, path, checksum = _artifact(tmp_path)
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)

    with pytest.raises(SymbolOnnxError) as error:
        LocalSymbolOnnxAdapter(
            path,
            expected_sha256=checksum,
            class_codes=("a", "b", "c"),
            input_size=64,
        )

    assert error.value.code == "SYMBOL_ONNX_ARTIFACT_DRIFT"


def test_class_contract_drift_is_rejected_before_session(tmp_path: Path) -> None:
    _, path, checksum = _artifact(tmp_path)

    with pytest.raises(SymbolOnnxError) as error:
        LocalSymbolOnnxAdapter(
            path,
            expected_sha256=checksum,
            class_codes=("a", "b"),
            input_size=64,
        )

    assert error.value.code == "SYMBOL_ONNX_OUTPUT_SHAPE_INVALID"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (np.zeros((1, 3, 32, 32), dtype=np.float32), "SYMBOL_ONNX_INPUT_INVALID"),
        (np.zeros((1, 3, 64, 64), dtype=np.float64), "SYMBOL_ONNX_INPUT_INVALID"),
        (np.zeros((0, 3, 64, 64), dtype=np.float32), "SYMBOL_ONNX_INPUT_INVALID"),
    ],
)
def test_invalid_input_contract_fails_closed(
    tmp_path: Path,
    value: np.ndarray,
    code: str,
) -> None:
    _, path, checksum = _artifact(tmp_path)
    adapter = LocalSymbolOnnxAdapter(
        path,
        expected_sha256=checksum,
        class_codes=("a", "b", "c"),
        input_size=64,
    )

    with pytest.raises(SymbolOnnxError) as error:
        adapter.infer(value)

    assert error.value.code == code


def test_non_finite_input_fails_closed(tmp_path: Path) -> None:
    _, path, checksum = _artifact(tmp_path)
    adapter = LocalSymbolOnnxAdapter(
        path,
        expected_sha256=checksum,
        class_codes=("a", "b", "c"),
        input_size=64,
    )
    images = np.zeros((1, 3, 64, 64), dtype=np.float32)
    images[0, 0, 0, 0] = np.nan

    with pytest.raises(SymbolOnnxError) as error:
        adapter.infer(images)

    assert error.value.code == "SYMBOL_ONNX_INPUT_NON_FINITE"


def test_non_finite_runtime_output_fails_closed(tmp_path: Path) -> None:
    class NonFiniteSession:
        def run(self, output_names, inputs):
            return [np.full((1, 3), np.nan, dtype=np.float32)]

    _, path, checksum = _artifact(tmp_path)
    adapter = LocalSymbolOnnxAdapter(
        path,
        expected_sha256=checksum,
        class_codes=("a", "b", "c"),
        input_size=64,
    )
    adapter._session = NonFiniteSession()  # type: ignore[assignment]

    with pytest.raises(SymbolOnnxError) as error:
        adapter.infer(np.zeros((1, 3, 64, 64), dtype=np.float32))

    assert error.value.code == "SYMBOL_ONNX_OUTPUT_INVALID"
