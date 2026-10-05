"""Scoped appearance augmentation does not alter validation or v1 defaults."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from game_predictor_worker.vision_lab.symbol_augmentation import augment
from game_predictor_worker.vision_lab.symbol_batch import reclassify_photo
from game_predictor_worker.vision_lab.symbol_models import (
    MODELS,
    PREPROCESSING,
    ROBUST_MODELS,
    model_pair,
    require_robust_qualification,
)
from game_predictor_worker.vision_lab.symbol_runs import validate_request
from game_predictor_worker.vision_lab.symbol_training import SymbolDataset
from game_predictor_worker.vision_lab.symbol_training_manifest import SymbolTrainingAdapter, freeze
from PIL import Image
from test_vision_lab_symbol_training import request
from test_vision_lab_symbol_training_manifest import prepared


def test_versioned_augmentation_deterministic_without_global_rng_changes():
    tensor = torch.linspace(-1, 1, 3 * 64 * 64).reshape(3, 64, 64)
    state = torch.get_rng_state().clone()
    first = augment(tensor, "sample-a", seed=20261005, epoch=8)
    assert torch.equal(first, augment(tensor, "sample-a", seed=20261005, epoch=8))
    assert not torch.equal(first, augment(tensor, "sample-a", seed=20261005, epoch=9))
    assert torch.equal(torch.get_rng_state(), state)
    assert first.shape == tensor.shape and torch.isfinite(first).all()
    assert -1 <= first.min() <= first.max() <= 1


def test_augmentation_exact_after_new_process():
    tensor = torch.linspace(-1, 1, 3 * 64 * 64).reshape(3, 64, 64)
    expected = hashlib.sha256(
        augment(tensor, "sample-b", seed=17, epoch=4).numpy().tobytes()
    ).hexdigest()
    code = (
        "import hashlib,torch;"
        "from game_predictor_worker.vision_lab.symbol_augmentation import augment;"
        "t=torch.linspace(-1,1,3*64*64).reshape(3,64,64);"
        "print(hashlib.sha256(augment(t,'sample-b',seed=17,epoch=4).numpy().tobytes()).hexdigest())"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    child = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert child.stdout.strip() == expected


def test_unaugmented_validation_and_v1_dataset_are_unchanged(tmp_path):
    store, bundle, qualification = prepared(tmp_path / "data")
    manifest = freeze(store, bundle, qualification, tmp_path / "manifests")
    inputs = SymbolTrainingAdapter(manifest).validate()
    old = SymbolDataset(inputs, "validation", False, 20261005)
    new = SymbolDataset(inputs, "validation", False, 20261005, robust=True)
    for index in range(len(old)):
        assert torch.equal(old[index][0], new[index][0]) and old[index][1] == new[index][1]
    assert not old.robust and new.robust and not old.epoch
    train = SymbolDataset(inputs, "development", False, 20261005, robust=True)
    train.epoch = 3
    assert not torch.equal(train[0][0], train.tensors[0])


def test_generation_registry_and_budget_preserve_v1():
    assert model_pair() == MODELS and model_pair(2) == ROBUST_MODELS
    with pytest.raises(ValueError, match="GENERATION_INVALID"):
        model_pair(3)
    old = request(purpose="train")
    validate_request(old)
    forty = old.configuration.model_copy(update={"epochs": 40})
    with pytest.raises(ValueError, match="PROTOCOL_INVALID"):
        validate_request(old.model_copy(update={"configuration": forty}))
    new = old.model_copy(
        update={
            "model_version": ROBUST_MODELS[0],
            "preprocessing_version": PREPROCESSING[ROBUST_MODELS[0]],
            "configuration": old.configuration,
        }
    )
    validate_request(new)
    with pytest.raises(ValueError, match="TRAIN_CONFIGURATION_INVALID"):
        validate_request(
            new.model_copy(
                update={"configuration": old.configuration.model_copy(update={"epochs": 19})}
            )
        )
    assert type(new).model_validate_json(new.model_dump_json()).configuration.epochs == 20


def test_bad_augmentation_shape_or_epoch_rejected():
    with pytest.raises(ValueError, match="INPUT_INVALID"):
        augment(torch.zeros(3, 64, 64), "a", seed=1, epoch=0)
    with pytest.raises(ValueError, match="INPUT_INVALID"):
        augment(torch.zeros(3, 96, 96), "a", seed=1, epoch=1)


def test_qualification_never_relaxes_original_accuracy_or_parity():
    good = {
        "validation": {"samples": 84, "correct": 83},
        "onnx": {"status": "passed", "samples": 84, "max_absolute_error": 1e-6},
    }
    require_robust_qualification(good)
    for measured in (
        {**good, "validation": {"samples": 84, "correct": 82}},
        {**good, "validation": {"samples": 84, "correct": 85}},
        {**good, "onnx": {"status": "passed", "samples": 84, "max_absolute_error": 0.001}},
        {**good, "onnx": {"status": "passed", "samples": 84, "max_absolute_error": float("nan")}},
        {**good, "onnx": {"status": "passed", "samples": 84, "max_absolute_error": -1e-6}},
        {**good, "onnx": {"status": "unavailable"}},
    ):
        with pytest.raises(ValueError, match="QUALIFICATION_FAILED"):
            require_robust_qualification(measured)


def test_new_model_reuses_exact_old_crop_and_geometry():
    from game_predictor_worker.vision_lab.geometry import crop_cell

    image = Image.new("RGB", (100, 100), "red")
    quad = np.array([[0, 0], [99, 0], [99, 99], [0, 99]], np.float32)
    crop = crop_cell(np.asarray(image), quad)
    old = {
        "cells": [
            {
                "quad": quad.tolist(),
                "crop_pixel_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                "predicted": "Q",
                "reasons": ["SYMBOL_LOW_CONFIDENCE", "BOARD_COUNT_EXCESS"],
                "human_approved": False,
            }
        ],
        "expected": 5,
        "detected": 6,
    }
    changed = reclassify_photo(
        image, old, lambda crops: [{"predicted": "K", "confidence": 0.99, "symbol_reasons": []}]
    )
    assert changed["cells"][0]["predicted"] == "K" and old["cells"][0]["predicted"] == "Q"
    assert changed["cells"][0]["reasons"] == ["BOARD_COUNT_EXCESS"]
    assert changed["cells"][0]["requires_review"] and not changed["cells"][0]["human_approved"]
    assert changed["expected"] == 5 and changed["detected"] == 6
    assert changed["cells"][0]["quad"] == old["cells"][0]["quad"]
    with pytest.raises(ValueError, match="REFERENCE_CROP_MISMATCH"):
        reclassify_photo(Image.new("RGB", (100, 100), "blue"), old, None)
