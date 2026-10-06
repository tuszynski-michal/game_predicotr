from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
import torch
from game_predictor_api.domain.symbol_model_snapshots import (
    LAB_RGB_SYMBOL_MODEL_VERSION,
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
    bootstrap_symbol_model_snapshot,
)
from game_predictor_worker.images.lab_rgb_preprocessing import preprocess_lab_rgb96
from game_predictor_worker.images.symbol_onnx import (
    SymbolOnnxError,
    preprocess_rgb_batch,
    symbol_onnx_variant_arguments,
)
from torchvision.transforms import functional


def test_float_antialias_matches_training_transform_and_preserves_boundaries() -> None:
    pixels = np.random.default_rng(881).integers(0, 256, (3, 96, 96, 3), dtype=np.uint8)
    pixels[0, :, 0, :] = 0
    pixels[0, :, -1, :] = 255
    tensor = torch.from_numpy(pixels.transpose(0, 3, 1, 2).copy()).float()
    expected = (
        functional.resize(tensor, [64, 64], antialias=True).div(255).sub(0.5).div(0.5).numpy()
    )
    actual = preprocess_lab_rgb96(list(pixels))
    assert actual.dtype == np.float32
    assert np.max(np.abs(actual - expected)) <= 1e-6
    assert np.array_equal(
        actual,
        preprocess_rgb_batch(
            list(pixels), input_size=64, model_version=LAB_RGB_SYMBOL_MODEL_VERSION
        ),
    )


@pytest.mark.parametrize("shape", [(64, 64, 3), (96, 96, 1), (96, 95, 3)])
def test_lab_rejects_altered_render_shape(shape: tuple[int, int, int]) -> None:
    with pytest.raises(SymbolOnnxError):
        preprocess_rgb_batch(
            [np.zeros(shape, dtype=np.uint8)],
            input_size=64,
            model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
        )


def test_bounded_batch_and_dtype_are_strict() -> None:
    for images in (
        [],
        [np.zeros((96, 96, 3), dtype=np.float32)],
        [np.zeros((96, 96, 3), dtype=np.uint8)] * 257,
    ):
        with pytest.raises(ValueError):
            preprocess_lab_rgb96(images)  # type: ignore[arg-type]


def test_legacy_dispatch_and_snapshot_fingerprint_are_unchanged() -> None:
    pixels = [np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)]
    old = preprocess_rgb_batch(pixels, input_size=64)
    assert np.array_equal(old, preprocess_rgb_batch(pixels, input_size=64, model_version="old-v1"))
    assert symbol_onnx_variant_arguments("old-v1") == {}
    snapshot = bootstrap_symbol_model_snapshot()
    payload = snapshot.to_payload()
    assert "cropSize" not in payload
    identity = {key: value for key, value in payload.items() if key != "inferenceFingerprint"}
    expected = hashlib.sha256(
        json.dumps(identity, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert snapshot.inference_fingerprint == expected
    assert snapshot.crop_output_size == snapshot.input_size
    assert SymbolModelJobSnapshot.from_payload(payload) == snapshot


def _snapshot() -> SymbolModelJobSnapshot:
    return SymbolModelJobSnapshot(
        iteration_id=uuid4(),
        model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
        manifest_checksum_sha256="a" * 64,
        onnx_checksum_sha256="b" * 64,
        onnx_relative_path="models/model.onnx",
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=("a", "b"),
        input_size=64,
        temperature=1.05,
        crop_size=96,
    )


def test_lab_crop_size_is_required_and_part_of_pinned_identity() -> None:
    snapshot = _snapshot()
    payload = snapshot.to_payload()
    assert payload["cropSize"] == 96
    assert snapshot.crop_output_size == 96
    assert snapshot.crop_padding_fraction == 0.0
    assert bootstrap_symbol_model_snapshot().crop_padding_fraction == 0.08
    assert SymbolModelJobSnapshot.from_payload(payload) == snapshot
    for value in (None, 64, 96.0, True, "96"):
        changed = {**payload, "cropSize": value}
        with pytest.raises(ValueError):
            SymbolModelJobSnapshot.from_payload(changed)


def test_pending_reinference_keeps_lab_crop_size_and_checks_fingerprint() -> None:
    from game_predictor_worker.images.pending_symbol_reinference import _snapshot_from_payload
    from game_predictor_worker.jobs.runtime import JobHandlerError

    snapshot = _snapshot()
    job = SimpleNamespace(input_payload={"symbol_model": snapshot.to_payload()})
    assert _snapshot_from_payload(job) == snapshot
    job.input_payload["symbol_model"]["cropSize"] = 64
    with pytest.raises(JobHandlerError):
        _snapshot_from_payload(job)


def test_manual_lab_prediction_uses_rgb96_instead_of_legacy_resizing(tmp_path: Path) -> None:
    from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
        ManualBoardCellSymbolPredictor,
        RenderedBoardCell,
    )
    from test_manual_board_cell_symbol_prediction import _SizedCapturingAdapter

    snapshot = _snapshot()
    predictor = ManualBoardCellSymbolPredictor(tmp_path, tmp_path)
    adapter = _SizedCapturingAdapter()
    predictor._cache[snapshot.inference_fingerprint] = adapter
    rgb = np.random.default_rng(80).integers(0, 256, (96, 96, 3), dtype=np.uint8)
    predictor.predict_rendered_cells([RenderedBoardCell(0, 0, rgb)], snapshot)
    assert np.array_equal(adapter.inputs[0], preprocess_lab_rgb96([rgb]))


def test_full_quad_virtual_renderer_preserves_exact_cell_footprint() -> None:
    from game_predictor_worker.images.virtual_cell_extraction import (
        VirtualCellRenderer,
        source_direct_warp_rgb,
    )
    from test_virtual_cell_extraction import _frame_and_geometries

    frame, _, old_cells = _frame_and_geometries()
    configuration = replace(
        old_cells[0].configuration, output_width=96, output_height=96, padding_fraction=0.0
    )
    cells = tuple(replace(cell, configuration=configuration) for cell in old_cells)
    renders = VirtualCellRenderer().render(frame, cells)
    for cell, render in zip(cells, renders, strict=True):
        assert render.padded_source_quad == cell.source_quad
        assert np.array_equal(
            render.rgb,
            source_direct_warp_rgb(
                frame.rgb, source_quad=cell.source_quad, output_width=96, output_height=96
            ),
        )


def test_pending_lab_inference_preserves_rgb96_transform(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from game_predictor_worker.images.normalization import CanonicalSourceLoader
    from game_predictor_worker.images.pending_symbol_reinference import (
        PendingSymbolReinferenceHandler,
        _ReinferenceCrop,
    )
    from test_manual_board_cell_symbol_prediction import _SizedCapturingAdapter

    snapshot = _snapshot()
    factory = MagicMock()
    factory.return_value.__enter__.return_value.get.return_value = None
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    rgb = np.random.default_rng(83).integers(0, 256, (96, 96, 3), dtype=np.uint8)
    crops = [_ReinferenceCrop(i // 5, i % 5, "a" * 64, rgb) for i in range(15)]
    handler._render_virtual_crops = MagicMock(return_value=crops)
    adapter = _SizedCapturingAdapter()
    output, _ = handler._infer_board(
        uuid4(),
        0,
        source=SimpleNamespace(),
        snapshot=snapshot,
        adapter=adapter,
        source_loader=CanonicalSourceLoader(),
        asset_mode="virtual_source",
        game_id=uuid4(),
    )
    assert len(output) == 15
    assert np.array_equal(adapter.inputs[0], preprocess_lab_rgb96([rgb] * 15))


def test_lab_opset_variant_does_not_weaken_legacy_contract(tmp_path: Path) -> None:
    from game_predictor_worker.images.symbol_onnx import validate_onnx_contract
    from onnx import TensorProto, helper

    graph = helper.make_graph(
        [
            helper.make_node("Flatten", ["images"], ["flat"], axis=1),
            helper.make_node("MatMul", ["flat", "weight"], ["logits"]),
        ],
        "variant",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, ["batch", 3, 64, 64])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 2])],
        [
            helper.make_tensor(
                "weight",
                TensorProto.FLOAT,
                [3 * 64 * 64, 2],
                np.zeros(3 * 64 * 64 * 2, dtype=np.float32),
            )
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=8)
    with pytest.raises(SymbolOnnxError, match="unexpected default opset"):
        validate_onnx_contract(model, input_size=64, class_count=2)
    validate_onnx_contract(
        model,
        input_size=64,
        class_count=2,
        model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
    )
    model.opset_import[0].version = 18
    validate_onnx_contract(model, input_size=64, class_count=2)
    with pytest.raises(SymbolOnnxError):
        validate_onnx_contract(
            model,
            input_size=64,
            class_count=2,
            model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
        )
