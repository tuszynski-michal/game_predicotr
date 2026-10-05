"""Calibration, durable variant admission and exact epoch-boundary continuation."""

from copy import deepcopy

import numpy as np
import pytest
import torch
from game_predictor_worker.training_core.checkpoint import load_checkpoint
from game_predictor_worker.vision_lab.run_contracts import (
    RunMutation,
    StartRunRequest,
    TrainingConfiguration,
)
from game_predictor_worker.vision_lab.run_files import verify_artifact
from game_predictor_worker.vision_lab.runs import RunManager, checkpoint_binding, token
from game_predictor_worker.vision_lab.symbol_models import (
    MODELS,
    PREPROCESSING,
    calibrate,
    compare,
    metrics,
    model_pair,
    probabilities,
)
from game_predictor_worker.vision_lab.symbol_runs import admit, validate_request
from game_predictor_worker.vision_lab.symbol_training import SymbolDataset, preferred, train
from game_predictor_worker.vision_lab.symbol_training_manifest import SymbolTrainingAdapter, freeze
from game_predictor_worker.vision_lab.training_adapter import RunControl
from test_vision_lab_symbol_training_manifest import prepared


def request(manifest="a" * 64, request_id="symbol-test-start", purpose="smoke"):
    return StartRunRequest(
        request_id=request_id,
        manifest_id=manifest,
        model_version=MODELS[0],
        preprocessing_version=PREPROCESSING[MODELS[0]],
        seed=20261005,
        purpose=purpose,
        configuration=TrainingConfiguration(
            epochs=2 if purpose == "smoke" else 20,
            batch_size=32,
            max_steps=10 if purpose == "smoke" else 10000,
            max_seconds=120,
        ),
    )


def test_metrics_confusion_and_macro_are_per_class():
    measured = metrics(np.array([[0.8, 0.2], [0.3, 0.7], [0.4, 0.6]]), [0, 0, 1], ["A", "B"])
    assert measured["correct"] == 2 and measured["confusion"] == [[1, 1], [0, 1]]
    assert measured["macro_accuracy"] == 0.75


def test_fixed64_pooling_preserves_adaptive_forward_and_gradient():
    source = torch.linspace(-1, 1, 2 * 64 * 16 * 16).reshape(2, 64, 16, 16).requires_grad_()
    adaptive = torch.nn.AdaptiveAvgPool2d((4, 4))(source)
    fixed = torch.nn.AvgPool2d(kernel_size=4, stride=4)(source)
    assert torch.equal(adaptive, fixed)
    adaptive.sum().backward()
    expected = source.grad.clone()
    source.grad.zero_()
    fixed.sum().backward()
    assert torch.equal(source.grad, expected)


def test_calibration_and_fusion_do_not_silence_disagreements():
    logits = np.array([[8, 0], [7, 0], [0, 8], [0, 9]])
    labels = [0, 1, 1, 1]
    result = calibrate(logits, labels, ["A", "B"])
    assert (
        result["metrics"]["log_loss"]
        <= metrics(probabilities(logits), labels, ["A", "B"])["log_loss"]
    )
    rgb = {
        "manifest_id": "a",
        "classes": ["A", "B"],
        "labels": labels,
        "sample_ids": list("abcd"),
        "logits": logits.tolist(),
    }
    gray = deepcopy(rgb)
    gray["logits"][0] = [0, 8]
    measured = compare(rgb, gray)
    assert measured["disagreements"] == 1 and measured["rows"][0]["requires_review"]
    assert measured["limitation"] and measured["accepted"] <= 3
    gray["sample_ids"].reverse()
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        compare(rgb, gray)


def test_epoch_selection_macro_loss_then_earliest():
    best = {"epoch": 3, "metrics": {"macro_accuracy": 0.8, "log_loss": 0.2}}
    assert preferred({"epoch": 2, "metrics": {"macro_accuracy": 0.8, "log_loss": 0.2}}, best)
    assert not preferred({"epoch": 4, "metrics": {"macro_accuracy": 0.8, "log_loss": 0.2}}, best)
    assert not preferred({"epoch": 4, "metrics": {"macro_accuracy": 0.7, "log_loss": 0.1}}, best)


def test_confident_agreement_still_flags_known_reference_conflict():
    values = {
        "manifest_id": "a",
        "classes": ["A", "B"],
        "labels": [1, 0],
        "sample_ids": ["wrong-reference", "correct"],
        "logits": [[10, 0], [10, 0]],
    }
    result = compare(values, deepcopy(values))
    assert result["rows"][0]["reference_conflict"]
    assert result["rows"][0]["requires_review"]
    assert not result["rows"][0]["disagreement"]


def test_admission_replay_and_new_variant_share_existing_run_protocol(tmp_path):
    launches = []
    manager = RunManager(
        tmp_path,
        validate=validate_request,
        models=MODELS,
        admit=admit,
        launcher=lambda r: launches.append(r.id),
        identity=lambda _: None,
    )
    req = request(purpose="train")
    first = manager.create_or_get_run(req)
    restarted = RunManager(
        tmp_path,
        validate=validate_request,
        models=MODELS,
        admit=admit,
        launcher=lambda r: launches.append(r.id),
        identity=lambda _: None,
    )
    assert restarted.create_or_get_run(req).id == first.id and len(launches) == 1
    restarted.cancel_run(first.id, RunMutation(request_id="symbol-stop-first", expected_attempt=1))
    with pytest.raises(ValueError, match="ALREADY_ADMITTED"):
        restarted.create_or_get_run(req.model_copy(update={"request_id": "new-symbol-start"}))
    gray = req.model_copy(
        update={
            "request_id": "symbol-gray-start",
            "model_version": MODELS[1],
            "preprocessing_version": PREPROCESSING[MODELS[1]],
        }
    )
    assert restarted.create_or_get_run(gray).request.model_version == MODELS[1]


@pytest.mark.parametrize(
    "change",
    [
        {"protocol_digest": "a" * 64},
        {"seed": 2},
        {"preprocessing_version": "other"},
        {"model_version": "geometry"},
    ],
)
def test_request_cannot_enter_other_registry(change):
    with pytest.raises(ValueError, match="PROTOCOL_INVALID"):
        validate_request(request().model_copy(update=change))


@pytest.mark.parametrize("generation", [1, 2])
def test_exact_resume_keeps_rng_optimizer_best_and_consumed_steps(
    tmp_path, monkeypatch, generation
):
    from game_predictor_worker.vision_lab import symbol_training as module

    store, bundle, qualification = prepared(tmp_path / "data")
    manifest = freeze(store, bundle, qualification, tmp_path / "manifests")
    inputs = SymbolTrainingAdapter(manifest).validate()
    req = request(inputs.manifest_id)
    pair = model_pair(generation)
    if generation == 2:
        req = req.model_copy(
            update={"model_version": pair[0], "preprocessing_version": PREPROCESSING[pair[0]]}
        )
    # Numerical export is verified separately; this test targets exact durable continuation.
    monkeypatch.setattr(module, "export_onnx", lambda *_: {"status": "test-separated"})

    def manager(root):
        return RunManager(
            root,
            validate=lambda _: inputs,
            models=pair,
            launcher=lambda _: None,
            identity=lambda _: None,
        )

    full = manager(tmp_path / "full")
    run = full.create_or_get_run(req)
    full.claim(run.id, token(run))
    measured = train(inputs, req, RunControl(full, run.id, token(run)), device_name="cpu")
    complete = full.finish(run.id, token(run), status="succeeded", metrics=measured)
    original = load_checkpoint(
        verify_artifact(full.root, complete.checkpoint),
        complete.checkpoint.sha256,
        expected_binding=checkpoint_binding(req),
    )

    interrupted = manager(tmp_path / "interrupted")
    run = interrupted.create_or_get_run(req)
    interrupted.claim(run.id, token(run))
    control = RunControl(interrupted, run.id, token(run))
    real_after = control.after_batch
    calls = 0

    def fail_after_batch():
        nonlocal calls
        calls += 1
        real_after()
        if calls == 2:
            raise OSError("lost process after optimizer step")

    monkeypatch.setattr(control, "after_batch", fail_after_batch)
    with pytest.raises(OSError, match="lost process"):
        train(inputs, req, control, device_name="cpu")
    failed = interrupted.finish(run.id, token(run), status="failed", error="lost process")
    assert failed.checkpoint_epoch == 1 and failed.reserved_steps == 2
    restarted = manager(interrupted.root)
    resumed = restarted.retry_run(
        run.id, RunMutation(request_id="symbol-resume-test", expected_attempt=1)
    )
    assert resumed.reserved_steps == 2 and resumed.used_seconds >= failed.used_seconds
    restarted.claim(resumed.id, token(resumed))
    measured = train(
        inputs, req, RunControl(restarted, resumed.id, token(resumed)), device_name="cpu"
    )
    completed = restarted.finish(resumed.id, token(resumed), status="succeeded", metrics=measured)
    restored = load_checkpoint(
        verify_artifact(restarted.root, completed.checkpoint),
        completed.checkpoint.sha256,
        expected_binding=checkpoint_binding(req),
    )
    assert completed.reserved_steps == 3 and restored["globalStep"] == original["globalStep"] == 2
    assert restored["history"] == original["history"]
    assert restored["bestState"]["epoch"] == original["bestState"]["epoch"]
    assert all(
        torch.equal(value, original["modelState"][key])
        for key, value in restored["modelState"].items()
    )
    assert torch.equal(restored["rng"]["torch"], original["rng"]["torch"])
    gray = SymbolDataset(inputs, "validation", True, req.seed)
    rgb = SymbolDataset(inputs, "validation", False, req.seed)
    assert torch.equal(gray[0][0][0], gray[0][0][1]) and not torch.equal(rgb[0][0][0], rgb[0][0][1])
