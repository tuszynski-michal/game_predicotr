"""Exact epoch-boundary continuation, safe v1 reading and import boundaries."""

import ast
import random
from pathlib import Path

import numpy as np
import pytest
import torch
from game_predictor_worker.training_core import checkpoint as module
from game_predictor_worker.training_core.checkpoint import (
    load_checkpoint,
    make_checkpoint,
    restore_checkpoint,
    write_checkpoint,
)
from game_predictor_worker.training_core.runtime import TrainingInterrupted, train_epochs


def components():
    torch.manual_seed(42)
    np.random.seed(42)
    random.seed(42)
    model = torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.Dropout(0.2))
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 1)
    generator = torch.Generator().manual_seed(42)
    return model, optimizer, scheduler, generator


def step(parts):
    model, optimizer, scheduler, generator = parts
    inputs = torch.rand((3, 2), generator=generator) * random.random() + np.random.rand()
    optimizer.zero_grad()
    model(inputs).sum().backward()
    optimizer.step()
    scheduler.step()


def test_v2_restores_entire_epoch_state_and_v1_is_explicit(tmp_path):
    parts = components()
    step(parts)
    binding = {"dataSha256": "a" * 64, "configuration": {"seed": 42}}
    value = make_checkpoint(*parts, binding=binding, epoch=1, global_step=1, history=[])
    path, checksum = write_checkpoint(tmp_path, value)
    step(parts)
    expected = [parameter.clone() for parameter in parts[0].parameters()]
    expected_rng = torch.get_rng_state()
    resumed = components()
    restore_checkpoint(load_checkpoint(path, checksum, expected_binding=binding), *resumed)
    step(resumed)
    assert all(torch.equal(a, b) for a, b in zip(expected, resumed[0].parameters(), strict=True))
    assert torch.equal(expected_rng, torch.get_rng_state())
    assert parts[2].state_dict() == resumed[2].state_dict()
    for key in parts[1].state_dict()["state"]:
        for field, expected_value in parts[1].state_dict()["state"][key].items():
            assert torch.equal(expected_value, resumed[1].state_dict()["state"][key][field])
    with pytest.raises(ValueError, match="BINDING"):
        load_checkpoint(path, checksum, expected_binding={"different": True})
    invalid_path, invalid_sha = write_checkpoint(tmp_path, {**value, "rng": {}})
    with pytest.raises(ValueError, match="RNG_INVALID"):
        load_checkpoint(invalid_path, invalid_sha, expected_binding=binding)
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="CHECKSUM"):
        load_checkpoint(path, checksum)
    old, old_sha = write_checkpoint(
        tmp_path,
        {
            "schemaVersion": 1,
            "modelState": parts[0].state_dict(),
            "optimizerState": parts[1].state_dict(),
            "inputFingerprint": "old",
            "epoch": 1,
            "history": [],
        },
    )
    with pytest.warns(RuntimeWarning, match="not exact"):
        assert load_checkpoint(old, old_sha)["resumeMode"] == "legacy_approximate"


def test_epoch_control_preserves_completed_checkpoint_when_budget_interrupts():
    events = []

    class Control:
        steps = 0

        def checkpoint(self, content, epoch):
            events.append(("checkpoint", epoch))

        def before_batch(self):
            if self.steps == 3:
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            self.steps += 1

        def after_batch(self):
            pass

        def cancellation_requested(self):
            return False

    with pytest.raises(TrainingInterrupted):
        train_epochs(
            start_epoch=0,
            epochs=3,
            batches=lambda epoch: range(2),
            train_batch=lambda batch: None,
            finish_epoch=lambda epoch: None,
            serialize_checkpoint=lambda epoch: b"checkpoint",
            control=Control(),
        )
    assert events == [("checkpoint", 0), ("checkpoint", 1)]


def test_import_boundaries_are_transitive_source_constraints():
    worker = Path(module.__file__).parents[1]
    for path in (worker / "training_core").glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any("game_predictor" in name for name in imports)
    for path in worker.rglob("*.py"):
        if "vision_lab" in path.parts or "training_core" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any("vision_lab" in name for name in imports)
