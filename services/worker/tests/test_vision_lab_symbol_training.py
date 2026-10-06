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
    FEEDBACK_MODELS,
    MODELS,
    PREPROCESSING,
    calibrate,
    compare,
    evaluate_frozen_fusion,
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


@pytest.mark.parametrize("generation", [1, 2, 3, 4])
def test_exact_resume_keeps_rng_optimizer_best_and_consumed_steps(
    tmp_path, monkeypatch, generation
):
    from game_predictor_worker.vision_lab import symbol_training as module

    store, bundle, qualification = prepared(tmp_path / "data")
    manifest = freeze(store, bundle, qualification, tmp_path / "manifests")
    inputs = SymbolTrainingAdapter(manifest).validate()
    req = request(inputs.manifest_id)
    pair = model_pair(generation)
    if generation != 1:
        req = req.model_copy(
            update={"model_version": pair[0], "preprocessing_version": PREPROCESSING[pair[0]]}
        )
    if generation in (3, 4):
        development = next(
            s
            for s in inputs.preparation["samples"]
            if inputs.payload["assignments"][s["decision"]["binding"]["source_id"]] == "development"
        )
        inputs.payload["purpose"] = (
            "symbol_crop_feedback" if generation == 3 else "symbol_ai_experiment"
        )
        inputs.payload["feedback_sample_ids"] = [development["decision"]["decision_id"]]
        diagnostic = deepcopy(inputs.preparation["samples"][0])
        diagnostic["decision"]["decision_id"] = "diagnostic-only"
        diagnostic["decision"]["binding"]["source_id"] = "diagnostic-source"
        inputs.preparation["samples"].append(diagnostic)
        inputs.payload["assignments"]["diagnostic-source"] = "diagnostic_test"
        if generation == 4:
            audit = deepcopy(diagnostic)
            audit["decision"]["decision_id"] = "ai-withheld"
            audit["decision"]["origin"] = "ai_visual_assessment"
            audit["decision"]["binding"]["source_id"] = "ai-source"
            audit["ai_audit"] = True
            inputs.preparation["samples"].append(audit)
            inputs.payload["assignments"]["ai-source"] = "development"
            ai = deepcopy(development)
            ai["decision"]["decision_id"] = "ai-training"
            ai["decision"]["origin"] = "ai_visual_assessment"
            inputs.preparation["samples"].append(ai)
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
    if generation == 3:
        assert measured["sampling"] == {
            "policy": "feedback-weight4-replacement-v1",
            "feedback_weight": 4,
            "unique_development": 1,
            "feedback_samples": 1,
            "draws_per_epoch": 4,
        }
        assert measured["diagnostic_test"]["evaluated_after_model_selection"]
        assert measured["diagnostic_test"]["predictions"]["sample_ids"] == ["diagnostic-only"]
        assert measured["development"]["samples"] == 1
        assert measured["feedback_regression"]["metrics"]["samples"] == 1
    if generation == 4:
        assert measured["sampling"]["ai_samples"] == 1
        assert measured["sampling"]["ai_weight"] == 1
        assert measured["sampling"]["draws_per_epoch"] == 5
        assert measured["development"]["samples"] == 2
        audit = measured["ai_experiment"]["withheld_ai_agreement"]["predictions"]
        assert audit["sample_ids"] == ["ai-withheld"]
        assert measured["ai_experiment"]["evaluated_after_model_selection"]
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


def test_feedback_registry_and_old_cohort_cannot_be_mixed(tmp_path):
    store, bundle, qualification = prepared(tmp_path / "data")
    manifest = freeze(store, bundle, qualification, tmp_path / "manifests")
    inputs = SymbolTrainingAdapter(manifest).validate()
    req = request(inputs.manifest_id).model_copy(
        update={
            "model_version": FEEDBACK_MODELS[0],
            "preprocessing_version": PREPROCESSING[FEEDBACK_MODELS[0]],
        }
    )
    validate_request(req)
    assert model_pair(3) == FEEDBACK_MODELS
    with pytest.raises(ValueError, match="GENERATION_BINDING_REQUIRED"):
        train(inputs, req, None, device_name="cpu")
    with pytest.raises(ValueError, match="GENERATION_INVALID"):
        model_pair(5)


def test_feedback_sampler_has_exact_weights_and_checkpoint_generator(tmp_path):
    from game_predictor_worker.vision_lab.symbol_training import training_loader

    store, bundle, qualification = prepared(tmp_path / "data")
    manifest = freeze(store, bundle, qualification, tmp_path / "manifests")
    inputs = SymbolTrainingAdapter(manifest).validate()
    data = SymbolDataset(inputs, "development", False, 20261005)
    data.samples.append(deepcopy(data.samples[0]))
    data.samples[1]["decision_id"] = "feedback"
    data.tensors.append(data.tensors[0].clone())
    data.labels.append(data.labels[0])
    data.feedback_ids = {"feedback"}
    generator = torch.Generator().manual_seed(20261005)
    loader = training_loader(data, 32, generator, feedback=True)
    assert loader.sampler.generator is generator and loader.generator is generator
    assert loader.sampler.weights.tolist() == [1, 4]
    assert loader.sampler.num_samples == 5 and loader.sampler.replacement
    state = generator.get_state()
    expected = list(loader.sampler)
    generator.set_state(state)
    replay = training_loader(data, 32, generator, feedback=True)
    assert list(replay.sampler) == expected
    assert len(data) == 2


def test_diagnostic_fusion_uses_only_frozen_validation_parameters(monkeypatch):
    from game_predictor_worker.vision_lab import symbol_models as module

    rgb = {
        "manifest_id": "same",
        "classes": ["A", "B"],
        "labels": [0, 1],
        "sample_ids": ["one", "two"],
        "logits": [[8, 0], [0, 8]],
    }
    calibration = compare(rgb, deepcopy(rgb))
    before = deepcopy(calibration)

    def refit(*_args):
        raise AssertionError("diagnostic labels were used for calibration")

    monkeypatch.setattr(module, "calibrate", refit)
    gray = deepcopy(rgb)
    gray["logits"][0] = [0, 8]
    result = evaluate_frozen_fusion(rgb, gray, calibration)
    assert result["gray"]["correct"] == result["fusion"]["correct"] == 1
    assert result["rows"][0]["disagreement"]
    assert calibration == before
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        evaluate_frozen_fusion(rgb, gray, {**calibration, "manifest_id": "other"})
