"""R1 regressions: actual supervisor admission/spec, with only DB/process boundaries supplied."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import torch
from game_predictor_worker.images.grid_training_child import (
    ChildControl,
    sha256_file,
    write_json_atomic,
)
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler, RunState
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
)
from game_predictor_worker.training_core.runtime import TrainingInterrupted
from test_grid_content_experiment_export import actual_inputs
from test_grid_training_handler import GPU, NOW, Context, job


@pytest.mark.parametrize("checkpoint_step", [650, 4550, 4800])
def test_real_recovery_admission_spec_uses_checkpoint_not_spent_block(
    tmp_path, monkeypatch, checkpoint_step
):
    fixture, snapshot, inputs, plan = actual_inputs(tmp_path, monkeypatch)
    preset = SCREEN_GRID_CORRECTIONS_V1
    current = job()
    current = replace(
        current,
        game_id=UUID(fixture.game),
        input_payload={
            **current.input_payload,
            "cohort_id": fixture.cohort,
            "cohort_manifest_sha256": snapshot.manifest_sha256,
            "mode": "screen+grid",
            "base_version_id": plan["baseVersionId"],
            "family_id": fixture.base["familyId"],
            "preset_id": preset.preset_id,
            "preset_fingerprint": preset.fingerprint,
            "seed": plan["seed"],
            "planned_steps": 4800,
            "content_experiment": plan,
            "content_experiment_inputs": inputs,
        },
    )
    header = {
        "status": "frozen",
        "manifestSha256": snapshot.manifest_sha256,
        "manifestPath": fixture.manifest_pin["path"],
        "mode": "screen+grid",
        "baseVersionId": plan["baseVersionId"],
        "summary": {
            "roles": [
                {
                    "role": role,
                    "eligibleBoards": c["boards"],
                    "eligiblePhotos": c["photos"],
                    "eligibleFullPhotos": c["fullPhotos"],
                }
                for role, c in snapshot.manifest["counts"].items()
            ]
        },
    }
    base = deepcopy(fixture.base)
    store = SimpleNamespace(
        cohort=lambda *a: header,
        eligibility=lambda *a: {"qualification": "eligible"},
        base_version=lambda *a: base,
    )
    handler = GridTrainingJobHandler(
        store,
        artifact_root=tmp_path,
        python=None,
        pythonpath="",
        repository_root=tmp_path,
        probe=lambda: GPU,
        wall_clock=lambda: NOW + timedelta(seconds=20),
        monotonic=lambda: 20.0,
    )
    monkeypatch.setattr(
        handler, "_wait_for_own_trainer", lambda *a: None
    )  # No live process in this fixture.
    run = tmp_path / "run"
    (run / "checkpoints").mkdir(parents=True)
    checkpoint = run / "checkpoints" / "durable.pt"
    torch.save({"model": {"x": torch.ones(1)}, "step": checkpoint_step % 1200}, checkpoint)
    pointer = {"path": checkpoint.name, "sha256": sha256_file(checkpoint), "step": checkpoint_step}
    write_json_atomic(
        run / "progress.json",
        {"attempt": 1, "step": min(4800, checkpoint_step + 37), "checkpoint": pointer},
    )
    budget = replace(
        RunBudget.for_preset(preset, "train", content_experiment=plan),
        reserved_steps=4800,
        used_seconds=1000.0,
    )
    state = RunState(
        budget,
        attempt=1,
        charged_at=NOW.isoformat(),
        attempt_start={"reserved": 4600, "step": max(0, checkpoint_step - 100)},
    )
    handler._recover_previous_attempt(Context(current), current, state, run)
    assert state.checkpoint == pointer and state.budget.logical_completed_steps == checkpoint_step
    assert state.budget.reserved_steps == 4800 and state.budget.used_seconds == 1020.0
    # Persisted/new-process-shaped state, then the real admission and real frozen-data spec.
    state = RunState.load(json.loads(json.dumps(state.payload())), budget)
    cohort, base, joint = handler._admit(Context(current), current, state)
    spec = handler._spec(current, state, cohort, base, joint)
    assert spec["budget"]["remainingSteps"] == 4800 - checkpoint_step
    assert spec["budget"]["remainingSeconds"] == 6180.0
    assert spec["budget"]["logicalCompletedSteps"] == checkpoint_step
    allowance = handler._reserve(state, checkpoint_step)
    write_json_atomic(run / "allowance.json", {"attempt": state.attempt, "step": allowance})
    control = ChildControl(spec, run, SimpleNamespace(renew=lambda record: record), None)
    monkeypatch.setattr(control, "_supervisor_alive", lambda: True)
    if checkpoint_step == 4550:
        for completed in range(4550, 4800):
            if completed >= allowance:
                allowance = handler._reserve(state, allowance)
                write_json_atomic(
                    run / "allowance.json", {"attempt": state.attempt, "step": allowance}
                )
            control.before_step(completed)
        assert allowance == 4800 and state.budget.reserved_steps == 4800
    control.check()  # Export/validation allowed even with zero optimizer steps left.
    with pytest.raises(TrainingInterrupted, match="RUN_BUDGET_EXHAUSTED"):
        control.before_step(4800)
    state.budget = state.budget.charge(6180)
    with pytest.raises(Exception) as stopped:
        handler._admit(Context(current), current, state)
    assert stopped.value.code == "GRID_RUN_BUDGET_EXHAUSTED"


def test_legacy_budget_serialization_and_physical_replay_are_unchanged():
    from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1

    legacy = replace(RunBudget.for_preset(GRID_ONLY_V1, "train"), reserved_steps=650)
    assert "logical_completed_steps" not in legacy.to_payload()["payload"]
    assert RunBudget.from_payload(legacy.to_payload()) == legacy
    assert legacy.remaining_steps == legacy.max_steps - 650
