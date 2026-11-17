"""Metadata-only operator recovery fixtures; no synthetic human ground truth."""

import json
from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
    digest,
)
from game_predictor_worker.training_core.run_budget_extension import (
    prepare_extension,
    verify_extension,
)

AT = "2026-11-17T00:45:00+00:00"


def stopped_row():
    preset = SCREEN_GRID_CORRECTIONS_V1
    budget = replace(
        RunBudget.for_preset(preset, "train"), used_seconds=7200, reserved_steps=1200, attempts=2
    )
    return {
        "id": str(UUID(int=1237)),
        "game_id": str(UUID(int=10)),
        "job_type": "grid_training",
        "status": "failed",
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "input_payload": {
            "training_kind": "grid-training-run-v1",
            "preset_id": preset.preset_id,
            "preset_fingerprint": preset.fingerprint,
            "planned_steps": 1200,
            "seed": 7,
            "cohort_id": str(UUID(int=20)),
            "base_version_id": str(UUID(int=30)),
            "cohort_manifest_sha256": "a" * 64,
            "mode": "screen+grid",
        },
        "checkpoint_payload": {
            "format": "grid-training-state-v1",
            "schema_version": 1,
            "budget": budget.to_payload(),
            "chargedAt": None,
            "checkpoint": None,
            "export": None,
            "registered": None,
            "attempt": 2,
            "history": [],
            "attemptStart": {"reserved": 400, "step": 0},
            "futureMetadata": {"keep": True},
        },
    }


def pointer():
    return {"path": "b" * 64 + ".pt", "sha256": "b" * 64, "step": 575}


def preview(row):
    return prepare_extension(row, pointer(), at=AT, reason="Approved four-hour run recovery")


def test_grant_preserves_consumption_inputs_and_all_other_state():
    row = stopped_row()
    original = deepcopy(row)
    change = preview(row)
    assert row == original
    after = change["payload"]["afterState"]
    budget = RunBudget.from_payload(after["budget"])
    assert (budget.max_seconds, budget.used_seconds, budget.reserved_steps, budget.attempts) == (
        14400,
        7200,
        1200,
        2,
    )
    assert budget.max_steps == 8000
    assert budget.with_current_limits(SCREEN_GRID_CORRECTIONS_V1) == budget
    for key in row["checkpoint_payload"]:
        if key not in {"budget", "history", "checkpoint"}:
            assert after[key] == row["checkpoint_payload"][key]
    assert after["checkpoint"] == pointer()
    assert after["history"][-1]["status"] == "operator_budget_extension"
    assert verify_extension(row, change, change["sha256"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "processing"),
        ("lease_owner", "worker"),
        ("lease_token", "token"),
        ("lease_expires_at", AT),
        ("job_type", "import"),
    ],
)
def test_active_or_foreign_job_fails_closed(key, value):
    row = stopped_row()
    row[key] = value
    with pytest.raises(ValueError):
        preview(row)


@pytest.mark.parametrize("field,value", [("chargedAt", AT), ("registered", {}), ("export", {})])
def test_unsettled_or_already_exported_state_is_rejected(field, value):
    row = stopped_row()
    row["checkpoint_payload"][field] = value
    with pytest.raises(ValueError):
        preview(row)


def test_foreign_policy_older_checkpoint_and_corrupt_budget_are_rejected():
    row = stopped_row()
    row["input_payload"]["content_experiment"] = {}
    with pytest.raises(ValueError):
        preview(row)
    row = stopped_row()
    row["checkpoint_payload"]["checkpoint"] = {**pointer(), "step": 600}
    with pytest.raises(ValueError, match="CHECKPOINT_REGRESSION"):
        preview(row)
    row = stopped_row()
    row["checkpoint_payload"]["budget"]["payload"]["used_seconds"] = 0
    with pytest.raises(ValueError):
        preview(row)


def test_stale_or_tampered_preview_cannot_write():
    row = stopped_row()
    change = preview(row)
    row["checkpoint_payload"]["futureMetadata"]["keep"] = False
    with pytest.raises(ValueError, match="RUN_STATE_DRIFT"):
        verify_extension(row, change, change["sha256"])
    row = stopped_row()
    change["payload"]["afterState"]["attempt"] = 0
    with pytest.raises(ValueError, match="PREVIEW_CHECKSUM"):
        verify_extension(row, change, change["sha256"])
    change["sha256"] = digest(change["payload"])
    with pytest.raises(ValueError, match="PREVIEW_CHANGE_INVALID"):
        verify_extension(row, change, change["sha256"])


def test_lost_response_replay_after_resume_does_not_grant_again():
    row = stopped_row()
    change = preview(row)
    row["checkpoint_payload"] = deepcopy(change["payload"]["afterState"])
    row["status"] = "processing"
    row["lease_owner"] = "worker"
    budget = RunBudget.from_payload(row["checkpoint_payload"]["budget"])
    row["checkpoint_payload"]["budget"] = replace(
        budget, used_seconds=7300, reserved_steps=1400, attempts=3
    ).to_payload()
    assert not verify_extension(row, change, change["sha256"])
    assert len(row["checkpoint_payload"]["history"]) == 1


def checkpoint_fixture(tmp_path):
    import torch
    from game_predictor_worker.images.grid_training_child import canonical, sha256_bytes
    from game_predictor_worker.training_core.checkpoint import make_checkpoint, write_checkpoint
    from game_predictor_worker.training_core.grid_rescue_training import (
        TrainingExposure,
        rescue_recipe,
        selection_input,
    )
    from game_predictor_worker.training_core.grid_training import (
        PHOTO_CHECKPOINT_RULE,
        EarlyStopping,
        TrainingPlan,
    )

    row = stopped_row()
    inputs = row["input_payload"]
    split = {
        "schemaVersion": "grid-correction-split-v4",
        "sha256": "d" * 64,
        "sources": [
            {
                "role": "VALIDATION",
                "validationPurpose": "A",
                "representative": True,
                "eligibleBoards": 9,
                "sourceId": str(UUID(int=n)),
                "sourceSha256": "a" * 64,
                "pixelSha256": "b" * 64,
                "qualifiedLabelsSha256": "c" * 64,
            }
            for n in range(5)
        ],
    }
    manifest = canonical({"gameId": row["game_id"], "photoSplit": split})
    inputs["cohort_manifest_sha256"] = sha256_bytes(manifest)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/manifest.json").write_bytes(manifest)
    selection = selection_input([(row["game_id"], split)])
    recipe = rescue_recipe("b" * 64, None, selection)
    inputs["rescue_recipe"] = recipe
    spec = {
        "jobId": row["id"],
        "attempt": 2,
        "seed": 7,
        "plannedSteps": 1200,
        "cohort": {
            "gameId": row["game_id"],
            "cohortId": inputs["cohort_id"],
            "manifestPath": "data/manifest.json",
            "manifestSha256": inputs["cohort_manifest_sha256"],
        },
        "base": {
            "versionId": inputs["base_version_id"],
            "weightsSha256": "c" * 64,
            "presetSha256": "b" * 64,
        },
        "preset": {"id": inputs["preset_id"], "fingerprint": inputs["preset_fingerprint"]},
        "rescueRecipe": recipe,
    }
    binding = TrainingPlan.of(
        row["id"],
        7,
        SCREEN_GRID_CORRECTIONS_V1,
        1200,
        {
            "cohortManifestSha256": inputs["cohort_manifest_sha256"],
            "baseWeightsSha256": "c" * 64,
            "basePresetSha256": "b" * 64,
            "mode": "screen+grid",
            "selectionInput": selection,
            "rescueRecipe": recipe,
        },
    ).binding
    model = torch.nn.Linear(1, 1)
    optimizer = torch.optim.AdamW(model.parameters())
    policy = SCREEN_GRID_CORRECTIONS_V1.early_stopping
    stopping = EarlyStopping(
        policy.direction,
        policy.patience,
        policy.min_delta,
        policy.min_evaluations,
        selection_rule=PHOTO_CHECKPOINT_RULE,
    )
    value = make_checkpoint(
        model,
        optimizer,
        None,
        torch.Generator(),
        binding=binding,
        epoch=0,
        global_step=575,
        history=[],
        best_state={
            "model": None,
            "step": None,
            "metric": None,
            "early": stopping.state(),
            "exposureCurrent": TrainingExposure(recipe).state(),
        },
    )
    run_dir = tmp_path / "grid-training/runs" / row["id"]
    path, _ = write_checkpoint(run_dir / "checkpoints", value)
    (run_dir / "spec.json").write_text(
        json.dumps({"payload": spec, "sha256": sha256_bytes(canonical(spec))})
    )
    return row, path


def test_real_checkpoint_binding_and_path_validation(tmp_path):
    from scripts.extend_grid_training_run import checkpoint_pointer

    row, path = checkpoint_fixture(tmp_path)
    result = checkpoint_pointer(row, tmp_path, path.name)
    assert result == {"path": path.name, "sha256": path.stem, "step": 575}
    with pytest.raises(ValueError, match="CHECKPOINT_PATH_INVALID"):
        checkpoint_pointer(row, tmp_path, "../" + path.name)
    row["input_payload"]["seed"] = 8
    with pytest.raises(ValueError, match="SPEC_INPUT_MISMATCH"):
        checkpoint_pointer(row, tmp_path, path.name)
    row["input_payload"]["seed"] = 7
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="CHECKPOINT_CHECKSUM_MISMATCH"):
        checkpoint_pointer(row, tmp_path, path.name)


def test_checkpoint_from_another_run_is_rejected_even_with_a_valid_file_sha(tmp_path):
    from game_predictor_worker.training_core.checkpoint import load_checkpoint, write_checkpoint

    from scripts.extend_grid_training_run import checkpoint_pointer

    row, path = checkpoint_fixture(tmp_path)
    value = load_checkpoint(path, path.stem)
    value["binding"]["runId"] = str(UUID(int=999))
    foreign, _ = write_checkpoint(path.parent, value)
    with pytest.raises(ValueError, match="CHECKPOINT_BINDING_MISMATCH"):
        checkpoint_pointer(row, tmp_path, foreign.name)
