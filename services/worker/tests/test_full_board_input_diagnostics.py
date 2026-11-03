from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np
import pytest
from game_predictor_worker.geometry_core.input_diagnostics import (
    SUPPORTED_PREPROCESSING_VERSION,
    DiagnosticUse,
    InputDiagnostic,
    ModelPin,
    NodeObservation,
    SourcePin,
    array_sha256,
    decode_record,
    diagnostic_uses,
    digest,
    encode_record,
    input_stages,
    reconstruct_input,
)
from game_predictor_worker.geometry_core.preprocessing import (
    board_rectifier,
    crop_board,
    screen_input,
)
from game_predictor_worker.geometry_core.settings import BoardPreset, ScreenPreset
from pydantic import ValidationError


@pytest.fixture
def sample():
    rgb = np.arange(97 * 153 * 3, dtype=np.uint8).reshape(97, 153, 3)
    source = SourcePin(
        source_id="source",
        source_sha256="a" * 64,
        normalized_pixel_sha256="b" * 64,
        rgb_bytes_sha256=array_sha256(rgb),
        width=153,
        height=97,
        exif_orientation=None,
        decoder_version="test",
        coordinate_space="exif-normalized-rgb-pixels-v1",
    )
    screen = ScreenPreset(
        heat_sigma_fraction=0.1,
        min_heat_sigma=1,
        offset_scale=64,
        positive_radius=0.5,
        offset_loss_weight=5,
        decode_threshold=0.3,
        nms_iou=0.5,
        top_k=64,
    )
    board = BoardPreset(
        margin=0.15,
        corner_jitter=0.015,
        shift_jitter=0.04,
        scale_jitter=0.06,
        rotation_jitter_degrees=2,
        boards_per_image=4,
        coordinate_loss_weight=0.125,
        heatmap_loss_weight=0.05,
        heatmap_sigma=1,
        visibility_loss_weight=0.5,
    )
    quad = ((-4.0, 3.0), (130.0, 10.0), (142.0, 87.0), (5.0, 78.0))
    stages = input_stages(rgb, source, quad, screen, board)
    preset = {
        "screen": screen.model_dump(mode="json"),
        "board": board.model_dump(mode="json"),
        "preprocessing_version": SUPPORTED_PREPROCESSING_VERSION,
        "other_full_preset_metadata": {"seed": 42},
    }
    record = InputDiagnostic(
        opencv_version=cv2.__version__,
        source=source,
        model=ModelPin(
            version_id="model",
            bundle_sha256="c" * 64,
            preset_sha256=digest(preset),
            preprocessing_version=SUPPORTED_PREPROCESSING_VERSION,
        ),
        archived_preset=preset,
        sequence_number=101,
        position_index=0,
        association_basis="exact_saved_nodes_then_unique_equal_detector_quad",
        screen_quad=quad,
        screen_preset=screen,
        board_preset=board,
        screen=stages[0],
        board=stages[1],
        raw_nodes=NodeObservation(nodes=None, unavailable_reason="NOT_ARCHIVED"),
        fitted_nodes=NodeObservation(nodes=[(1.0, 2.0)] * 24, unavailable_reason=None),
        reason_codes=["NEURAL_GRID_FIT_OUTLIERS"],
        historical_disposition="automatic",
        current_policy="neural-auto-crop-v2",
        current_policy_verdict="blocked",
        current_policy_blockers=["NEURAL_GRID_FIT_OUTLIERS"],
        diagnostic_use=DiagnosticUse(
            source_id=source.source_id,
            source_sha256=source.source_sha256,
            normalized_pixel_sha256=source.normalized_pixel_sha256,
        ),
    )
    return rgb, record


def test_replay_matches_production_pixels_and_actual_float32_values(sample):
    rgb, record = sample
    canvas, crop = reconstruct_input(decode_record(encode_record(record)), rgb)
    expected_canvas, _, _ = screen_input(rgb, record.screen_preset)
    expected_crop = crop_board(
        rgb,
        board_rectifier(np.asarray(record.screen_quad, np.float32), record.board_preset),
        record.board_preset,
    )
    np.testing.assert_array_equal(canvas, expected_canvas)
    np.testing.assert_array_equal(crop, expected_crop)
    assert record.screen.tensor_sha256 == array_sha256(
        canvas.transpose(2, 0, 1)[None].astype("<f4")
    )
    assert record.board.tensor_sha256 == array_sha256(crop.transpose(2, 0, 1).astype("<f4"))
    assert record.board.tensor_shape == (3, 192, 320)
    assert record.board.tensor_scope == "single_board_sample_before_stack"
    assert record.screen.tensor_scope == "screen_runner_batch"
    assert record.board.rgb_sha256 != record.board.tensor_sha256
    assert (crop == 114).all(axis=2).any()  # Actual out-of-source padding remains visible.
    assert record.raw_nodes.nodes is None and record.fitted_nodes.nodes is not None
    assert record.fraction_of_gt_outside_input is None


def test_new_process_replays_record(sample, tmp_path):
    rgb, record = sample
    (tmp_path / "record.json").write_text(json.dumps(encode_record(record)))
    np.save(tmp_path / "rgb.npy", rgb)
    root = Path(__file__).resolve().parents[3]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(root / path) for path in ("services/api/src", "services/worker/src")
        ),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import json,numpy as np; from pathlib import Path; "
            "from game_predictor_worker.geometry_core.input_diagnostics import "
            "decode_record,reconstruct_input; "
            "r=decode_record(json.loads(Path('record.json').read_text())); "
            "reconstruct_input(r,np.load('rgb.npy',allow_pickle=False))",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "fault",
    [
        "opencv",
        "matrix",
        "canvas",
        "tensor",
        "source",
        "version",
        "preset_hash",
        "preset_content",
        "preset_contract",
        "preprocessing",
        "unsupported_preprocessing",
    ],
)
def test_replay_rejects_drift_even_with_recomputed_envelope(sample, fault):
    rgb, record = sample
    payload = deepcopy(record.model_dump(mode="json"))
    if fault == "opencv":
        payload["opencv_version"] = "other"
    elif fault == "matrix":
        payload["board"]["source_to_input"][0][0] = 0
    elif fault == "canvas":
        payload["board"]["width"] += 1
    elif fault == "tensor":
        payload["board"]["tensor_sha256"] = "f" * 64
    elif fault == "source":
        rgb = rgb.copy()
        rgb[0, 0, 0] += np.uint8(1)
    elif fault == "preset_hash":
        payload["model"]["preset_sha256"] = "f" * 64
    elif fault == "preset_content":
        payload["archived_preset"]["other_full_preset_metadata"]["seed"] = 43
    elif fault == "preset_contract":
        payload["archived_preset"]["board"]["margin"] = 0.2
        payload["model"]["preset_sha256"] = digest(payload["archived_preset"])
    elif fault == "preprocessing":
        payload["model"]["preprocessing_version"] = "future"
    elif fault == "unsupported_preprocessing":
        payload["archived_preset"]["preprocessing_version"] = "future"
        payload["model"]["preprocessing_version"] = "future"
        payload["model"]["preset_sha256"] = digest(payload["archived_preset"])
    else:
        payload["schema_version"] = "future-version"
    with pytest.raises((ValueError, ValidationError)):
        reconstruct_input(decode_record({"payload": payload, "sha256": digest(payload)}), rgb)


def test_checksum_and_nonfinite_nodes_fail(sample):
    _, record = sample
    document = encode_record(record)
    document["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="CHECKSUM"):
        decode_record(document)
    with pytest.raises(ValidationError):
        NodeObservation(nodes=[(float("nan"), 1)] * 24, unavailable_reason=None)
    with pytest.raises(ValidationError):
        NodeObservation(nodes=None, unavailable_reason=None)


def test_invalid_quad_and_canvas_do_not_allocate(sample):
    rgb, record = sample
    with pytest.raises(ValueError, match="QUAD_INVALID"):
        input_stages(
            rgb, record.source, ((1.0, 1.0),) * 4, record.screen_preset, record.board_preset
        )
    board = record.board_preset.model_copy(update={"canvas": (100000, 100000)})
    with pytest.raises(ValueError, match="CANVAS_LIMIT"):
        input_stages(rgb, record.source, record.screen_quad, record.screen_preset, board)


def test_diagnostic_use_is_stable_deduplicated_and_bound_to_records(sample):
    _, record = sample
    second = record.model_copy(update={"position_index": 1, "sequence_number": 102})
    uses = diagnostic_uses([record, second, record])
    assert uses == diagnostic_uses([second, record, second])
    assert len(uses) == 1 and len(uses[0]["records"]) == 2
    assert uses[0]["deduplicationKey"] == diagnostic_uses([record])[0]["deduplicationKey"]
    bindings = {entry["recordSha256"]: entry for entry in uses[0]["records"]}
    assert bindings[encode_record(record)["sha256"]]["sequenceNumber"] == 101
    assert bindings[encode_record(second)["sha256"]]["positionIndex"] == 1


def test_supported_preprocessing_matches_runtime_protocol():
    from game_predictor_worker.vision_lab.neural_grid_protocol import PREPROCESSING_VERSION

    assert SUPPORTED_PREPROCESSING_VERSION == PREPROCESSING_VERSION
