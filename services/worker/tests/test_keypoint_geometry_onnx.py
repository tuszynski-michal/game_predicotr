from __future__ import annotations

from pathlib import Path

import numpy as np
from game_predictor_worker.images.keypoint_geometry import (
    KEYPOINT_ONNX_MAX_PARITY_ERROR,
    KeypointGeometryHeatmapNetwork,
    KeypointOnnxOutputs,
    LocalKeypointGeometryOnnxAdapter,
    decode_keypoint_outputs,
    export_keypoint_geometry_onnx,
    measure_keypoint_onnx_cpu,
    validate_keypoint_onnx_parity,
)


def _logits_for_two_slots() -> KeypointOnnxOutputs:
    heatmaps = np.full((1, 9, 4, 32, 32), -20.0, dtype=np.float32)
    coordinates = (
        ((4, 3), (4, 12), (12, 12), (12, 3)),
        ((4, 18), (4, 28), (12, 28), (12, 18)),
    )
    for slot, corners in enumerate(coordinates):
        for corner, (y, x) in enumerate(corners):
            heatmaps[0, slot, corner, y, x] = 20.0
    presence = np.full((1, 9), -20.0, dtype=np.float32)
    presence[0, 0:2] = 20.0
    presence[0, 5] = 20.0
    return KeypointOnnxOutputs(
        corner_heatmap_logits=heatmaps,
        slot_presence_logits=presence,
    )


def test_golden_decode_uses_attested_active_mask_and_ordered_quads() -> None:
    result = decode_keypoint_outputs(
        _logits_for_two_slots(),
        source_width=320,
        source_height=160,
        active_board_slots=(0, 1),
        model_checksum_sha256="a" * 64,
    )

    assert result.complete is True
    assert result.active_slot_mask == (True, True, False, False, False, False, False, False, False)
    assert result.inactive_false_positive_count == 1
    assert tuple(slot.position_index for slot in result.slots) == (0, 1)
    first = result.slots[0].quad
    assert first is not None
    np.testing.assert_allclose(first.corners[0].x, 3 / 31 * 319, atol=0.01)


def test_missing_active_presence_fails_closed() -> None:
    outputs = _logits_for_two_slots()
    outputs.slot_presence_logits[0, 1] = -20.0

    result = decode_keypoint_outputs(
        outputs,
        source_width=320,
        source_height=160,
        active_board_slots=(0, 1),
        model_checksum_sha256="a" * 64,
    )

    assert result.complete is False
    assert result.slots[1].quad is None
    assert "keypoint_active_slot_missing" in result.slots[1].reason_codes


def test_onnx_parity_and_bounded_cpu_timing(tmp_path: Path) -> None:
    model = KeypointGeometryHeatmapNetwork()
    artifact = export_keypoint_geometry_onnx(model)
    path = tmp_path / "keypoint.onnx"
    path.write_bytes(artifact.content)
    adapter = LocalKeypointGeometryOnnxAdapter(
        path,
        expected_sha256=artifact.checksum_sha256,
    )
    images = np.random.default_rng(319).random((2, 3, 128, 128), dtype=np.float32)

    parity = validate_keypoint_onnx_parity(model, adapter, images)
    timing = measure_keypoint_onnx_cpu(
        adapter,
        images[:1],
        warmup_count=1,
        measurement_count=3,
    )

    assert parity.maximum_absolute_error <= KEYPOINT_ONNX_MAX_PARITY_ERROR
    assert parity.heatmap_argmax_equal is True
    assert parity.presence_mask_equal is True
    assert timing.measurement_count == 3
    assert 0 < timing.median_milliseconds <= timing.p95_milliseconds
    assert timing.p95_milliseconds < 250
