"""Fixed pilot masks, image-only crops, structural gates and protocol compatibility."""

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from game_predictor_worker.vision_lab.annotations import digest
from game_predictor_worker.vision_lab.contracts import DetectRequest, Topology
from game_predictor_worker.vision_lab.hybrid_data import (
    grid_from_quad,
    matches,
    prepare_proposal,
    proposals,
    result_from_deltas,
    score,
)
from game_predictor_worker.vision_lab.hybrid_protocol import protocol_digest, validate_protocol
from game_predictor_worker.vision_lab.run_contracts import StartRunRequest
from game_predictor_worker.vision_lab.runs import canonical_request, checkpoint_binding
from game_predictor_worker.vision_lab.training_manifest import TrainingTarget


def board(index=0):
    return grid_from_quad(
        np.array([[20, 20], [120, 20], [120, 80], [20, 80]], dtype=np.float32), 200, 120, index
    )


def target(index=0, source="source"):
    return TrainingTarget(source, index, 1, tuple((p.x, p.y) for p in board(index).nodes))


def test_image_only_crop_unknown_mask_and_variable_count():
    rgb = np.zeros((120, 200, 3), dtype=np.uint8)
    for count in (0, 1, 3):
        engine = SimpleNamespace(
            detect=lambda *args, count=count: SimpleNamespace(
                boards=[board(i) for i in range(count)], reasons=[]
            )
        )
        values, _ = proposals("source", rgb, engine)
        assert len(values) == count
        result = result_from_deltas(
            "source", 200, 120, values, np.zeros((count, 8), dtype=np.float32)
        )
        assert len(result.boards) == count
        assert all(b.status == "needs_review" for b in result.boards)
    p = prepare_proposal("source", rgb, board())
    np.testing.assert_allclose(p.source(p.normalize(p.quad)), p.quad, atol=0.0001)
    assert matches(p, target()) and not matches(p, target(1))
    altered = TrainingTarget("source", 0, 2, tuple((x + 2, y) for x, y in target().nodes))
    # Labels influence matching/loss only: the image-only function has no label argument.
    assert matches(p, altered)
    np.testing.assert_array_equal(p.pixels, prepare_proposal("source", rgb, board()).pixels)
    metrics = score((target(), target(1)), [p], np.zeros((1, 8), dtype=np.float32))
    assert metrics["missed"] == 1 and metrics["valid"] == 1
    assert metrics["score"] == pytest.approx(0.5, abs=0.00001)


def test_structural_gate_rejects_bounds_crossing_and_no_manual_combination():
    for quad in (
        [[-1, 0], [100, 0], [100, 50], [0, 50]],
        [[0, 0], [100, 50], [100, 0], [0, 50]],
        [[0, 0]] * 4,
    ):
        with pytest.raises(ValueError):
            grid_from_quad(np.array(quad, dtype=np.float32), 200, 120, 0)
    with pytest.raises(ValueError, match="CONFLICT"):
        DetectRequest(source_id="source", run_id="a" * 32, preview_board=board())
    assert len(board().nodes) == 24 and Topology(columns=3).columns == 3


def test_old_canonical_request_and_checkpoint_binding_unchanged(tmp_path):
    payload = {
        "request_id": "old-request",
        "manifest_id": "a" * 64,
        "model_version": "test",
        "preprocessing_version": "rgb",
        "seed": 1,
        "purpose": "smoke",
        "configuration": {"epochs": 1, "max_steps": 5},
    }
    request = StartRunRequest(**payload)
    old = request.model_dump()
    old.pop("protocol_digest")
    assert canonical_request(request) == old
    old.pop("request_id")
    assert checkpoint_binding(request) == {
        "inputFingerprint": digest(old),
        "dataSha256": "a" * 64,
        **old,
    }
    hybrid = request.model_copy(
        update={"model_version": "hybrid-mobilenet-v1", "protocol_digest": protocol_digest()}
    )
    with pytest.raises(ValueError, match="RUN_PROTOCOL_MISMATCH"):
        validate_protocol(hybrid, tmp_path / "missing.pth")


def test_api_and_inference_import_without_torch():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import game_predictor_worker.vision_lab.api; "
            "import game_predictor_worker.vision_lab.hybrid_inference; "
            "from game_predictor_worker.vision_lab.training_adapter import TRAINERS; "
            "assert 'hybrid-mobilenet-v1' in TRAINERS; assert 'torch' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_original_baseline_nodes_are_not_zero_delta_homography():
    rgb = np.zeros((120, 200, 3), dtype=np.uint8)
    original = board()
    original.nodes[7].x += 3
    p = prepare_proposal("source", rgb, original)
    truth = TrainingTarget("source", 0, 1, tuple((n.x, n.y) for n in original.nodes))
    zero = np.zeros((1, 8), dtype=np.float32)
    assert score((truth,), [p], zero, original_baseline=True)["score"] == 0
    assert score((truth,), [p], zero)["score"] > 0


def test_registered_protocol_and_actual_weight_bytes_are_verified(tmp_path, monkeypatch):
    import hashlib

    from game_predictor_worker.vision_lab import hybrid_protocol as preset

    weights = tmp_path / preset.WEIGHTS_FILENAME
    weights.write_bytes(b"small-test-fixture")
    monkeypatch.setattr(preset, "WEIGHTS_SHA256", hashlib.sha256(weights.read_bytes()).hexdigest())
    registration = preset.freeze_protocol(tmp_path)
    request = StartRunRequest(
        request_id="protocol-fixture",
        manifest_id="a" * 64,
        model_version=preset.MODEL_VERSION,
        preprocessing_version=preset.PREPROCESSING_VERSION,
        protocol_digest=preset.protocol_digest(),
        seed=20260927,
        purpose="smoke",
        configuration={"epochs": 1, "max_steps": 50},
    )
    preset.validate_protocol(request, weights)
    assert preset.freeze_protocol(tmp_path) == registration
    weights.write_bytes(b"different-weights")
    with pytest.raises(ValueError, match="PROTOCOL_MISMATCH"):
        preset.validate_protocol(request, weights)
    weights.write_bytes(b"small-test-fixture")
    registration.write_bytes(b"{}")
    with pytest.raises((ValueError, KeyError)):
        preset.validate_protocol(request, weights)


def test_independent_runs_start_fresh_with_same_seed_not_learned_smoke_state():
    import torch
    from game_predictor_worker.vision_lab.hybrid_training import fresh_training

    torch.set_num_threads(1)
    smoke, optimizer, generator = fresh_training(None, 20260927, "cpu")
    original = {key: value.clone() for key, value in smoke.state_dict().items()}
    loader_state = generator.get_state().clone()
    loss = (smoke(torch.ones(2, 3, 224, 224)) - 0.1).square().mean()
    loss.backward()
    optimizer.step()
    torch.rand(3, generator=generator)
    trained, new_optimizer, new_generator = fresh_training(None, 20260927, "cpu")
    assert all(torch.equal(original[key], value) for key, value in trained.state_dict().items())
    assert not new_optimizer.state and optimizer.state
    assert torch.equal(loader_state, new_generator.get_state())


def test_backbone_parameters_and_batchnorm_buffers_frozen_after_steps():
    import torch
    from game_predictor_worker.vision_lab.hybrid_model import HybridNetwork

    torch.set_num_threads(1)
    torch.manual_seed(1)
    model = HybridNetwork(None)
    before = {k: v.clone() for k, v in model.features.state_dict().items()}
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=0.001)
    model.train()
    for _ in range(2):
        optimizer.zero_grad()
        loss = (model(torch.ones(2, 3, 224, 224)) - 0.1).square().mean()
        loss.backward()
        optimizer.step()
    assert not any(p.requires_grad for p in model.features.parameters())
    assert not model.features.training
    assert all(torch.equal(before[k], v) for k, v in model.features.state_dict().items())
    assert torch.count_nonzero(model.head[-1].bias) > 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("side", [0, 1])
def test_parity_nonfinite_is_never_a_pass(bad, side):
    from game_predictor_worker.vision_lab.hybrid_onnx import parity_errors

    p = prepare_proposal("source", np.zeros((120, 200, 3), dtype=np.uint8), board())
    arrays = [np.zeros((1, 8), dtype=np.float32), np.zeros((1, 8), dtype=np.float32)]
    arrays[side][0, 0] = bad
    with pytest.raises(ValueError, match="NONFINITE"):
        parity_errors(*arrays, [p])


def test_holdout_guard_before_image_decode_over_http(tmp_path):
    from fastapi.testclient import TestClient
    from game_predictor_worker.vision_lab.annotations import write_atomic
    from game_predictor_worker.vision_lab.api import create_app
    from game_predictor_worker.vision_lab.training_manifest import TrainingInputs

    request = StartRunRequest(
        request_id="holdout-guard",
        manifest_id="a" * 64,
        model_version="hybrid-mobilenet-v1",
        preprocessing_version="baseline-crop-rgb224-v1",
        protocol_digest=protocol_digest(),
        seed=20260927,
        purpose="smoke",
        configuration={"epochs": 1, "max_steps": 50},
    )
    write_atomic(tmp_path / ("a" * 64 + ".json"), {"game_partitions": {"holdout": "final_test"}})
    catalog = SimpleNamespace(sources={"secret": SimpleNamespace(game_id="holdout")})
    manager = SimpleNamespace(
        detail=lambda run_id: SimpleNamespace(status="succeeded", request=request),
        validate=lambda request: TrainingInputs(request.manifest_id, "b" * 64, (), (), catalog),
        settings={"manifests": str(tmp_path)},
    )
    client = TestClient(
        create_app(catalog=catalog, run_manager=manager), base_url="http://127.0.0.1:8102"
    )
    response = client.post(
        "/geometry",
        json={"source_id": "secret", "run_id": "c" * 32},
        headers={"Origin": "http://127.0.0.1:3102"},
    )
    assert response.status_code == 409 and response.json()["detail"] == "HOLDOUT_NOT_RELEASED"


def test_fenced_artifacts_fresh_validation_deadline_and_restart_checks(tmp_path):
    from game_predictor_worker.training_core.runtime import TrainingInterrupted
    from game_predictor_worker.vision_lab.runs import token
    from test_vision_lab_runs import checkpoint_content, manager_at, request

    now = [1000.0]
    manager = manager_at(tmp_path, clock=lambda: now[0])
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 1), 1)
    artifact = manager.publish_artifact(run.id, token(run), "onnx", b"fixture-model")
    with pytest.raises(ValueError, match="FENCED"):
        manager.publish_artifact(run.id, (99, 99, "stale"), "onnx", b"bad")

    def drift(request):
        raise ValueError("RUN_PROTOCOL_MISMATCH")

    manager.validate = drift
    with pytest.raises(ValueError, match="PROTOCOL_MISMATCH"):
        manager.publish_artifact(run.id, token(run), "onnx", b"bad")
    assert manager.detail(run.id).artifacts["onnx"] == artifact
    manager.validate = lambda request: None
    manager.finish(run.id, token(run), status="succeeded")
    assert manager_at(tmp_path).detail(run.id).artifacts["onnx"] == artifact
    (tmp_path / artifact.relative_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="CHECKSUM"):
        manager_at(tmp_path).list()
    other = manager_at(tmp_path / "deadline", clock=lambda: now[0])
    run = other.create_or_get_run(request())
    other.claim(run.id, token(run))
    now[0] += 121
    with pytest.raises(TrainingInterrupted, match="BUDGET"):
        other.publish_artifact(run.id, token(run), "onnx", b"too-late")
    assert not other.detail(run.id).artifacts
