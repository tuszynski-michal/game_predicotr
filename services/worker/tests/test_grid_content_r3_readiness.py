"""Isolated R3 boundary with real 1200-step core; earlier-arm receipts are explicit fixtures."""

import pytest
import torch
from game_predictor_api.domain.grid_visibility_contract import (
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_worker.images import grid_content_experiment_run as workflow
from game_predictor_worker.images.grid_training_child import sha256_file, write_json_atomic
from game_predictor_worker.training_core.grid_content_experiment import (
    advance_state,
    selection_record,
    start_arm,
)
from game_predictor_worker.training_core.grid_training_admission import digest
from test_grid_content_experiment import game
from test_grid_content_experiment_workflow import WorkflowFixture


def test_impossible_bundle_blocks_run_before_baseline_or_optimizer(tmp_path, monkeypatch):
    from game_predictor_api.domain import grid_content_bundle

    fixture = WorkflowFixture(tmp_path, monkeypatch)
    monkeypatch.setattr(grid_content_bundle, "CONTENT_BUNDLE_MAX_BYTES", 128)
    with pytest.raises(grid_content_bundle.ContentBundleTooLarge) as stopped:
        fixture.invoke()
    assert stopped.value.code == "CONTENT_EXPERIMENT_BUNDLE_TOO_LARGE"
    assert fixture.network_calls == [] and fixture.train_calls == []
    assert fixture.bank_calls == fixture.graph_exports == fixture.final_exports == 0


def ready_for_r3(tmp_path, monkeypatch):
    fixture = WorkflowFixture(tmp_path, monkeypatch, r2_fail=True)
    body = {"planSha256": fixture.plan["sha256"], "fixture": "measured inference boundary"}
    bank = {**body, "sha256": digest(body)}
    write_json_atomic(fixture.run_dir / "content-bank.json", bank)
    ledger = workflow.ExperimentLedger(
        fixture.run_dir / "content-experiment.json", fixture.plan, bank, fixture.spec
    )
    directory = fixture.run_dir / "checkpoints"
    directory.mkdir(exist_ok=True)
    for index, arm in enumerate(("R0", "R1", "R2")):
        checkpoint = directory / f"fixture-{arm}.pt"
        checkpoint.write_bytes(f"explicit earlier-arm fixture {arm}".encode())
        sha = sha256_file(checkpoint)
        row = game()
        row["gameId"] = fixture.plan["cohorts"][0]["gameId"]
        if arm == "R2":
            row["quality"]["candidate"]["false_boards"] = 1
        selected = selection_record([row], arm, 200)
        state = start_arm(fixture.plan, ledger.state, arm, feasible_seconds=10)
        ledger.value["state"] = advance_state(
            fixture.plan,
            state,
            arm,
            completed_steps=1200,
            charged_seconds=1,
            checkpoint_sha256=sha,
            selection=selected,
            complete=True,
        )
        ledger.value["checkpoints"][arm] = {
            "path": checkpoint.name,
            "sha256": sha,
            "localStep": 1200,
            "globalStep": (index + 1) * 1200,
        }
        ledger.value["results"][arm] = {
            "steps": 1200,
            "best_step": 200,
            "checkpoint_path": checkpoint.name,
            "checkpoint_sha256": sha,
            "checkpoint_selection": selected,
            "content_head_exposure": None,
        }
    ledger.save()
    fixture.spec["budget"]["chargedSeconds"] = 3
    fixture.spec["budget"]["remainingSeconds"] = 7197
    fixture.spec["resume"] = {"path": checkpoint.name, "sha256": sha, "step": 3600}
    return fixture


@pytest.mark.parametrize("reason", ["below_threshold", "missing_train_game"])
def test_approved_visible_quads_without_qualified_contract_block_before_r3_preflight(
    tmp_path, monkeypatch, reason
):
    fixture = ready_for_r3(tmp_path, monkeypatch)
    if reason == "below_threshold":
        fixture.references = fixture.references[:1]
        supervision = visibility_supervision(fixture.references)
    else:
        supervision = visibility_supervision(
            fixture.references,
            game_ids=[str(fixture.references[0].gameId), "22222222-2222-4222-8222-222222222222"],
        )
    assert fixture.references[0].humanApproved and not supervision.qualified
    fixture.spec["gridOutputContract"] = GridOutputContract(supervision=supervision).model_dump(
        mode="json"
    )
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_R3_LABELS_REQUIRED"):
        fixture.invoke()
    assert fixture.train_calls == [] and fixture.graph_exports == fixture.final_exports == 0
    assert fixture.ledger()["state"]["arms"]["R3"]["status"] == "pending"


def test_zero_head_exposure_cannot_complete_required_r3_even_when_r0_would_win(
    tmp_path, monkeypatch
):
    fixture = ready_for_r3(tmp_path, monkeypatch)
    original = workflow.screen_grid_losses

    def zero_head(network, batch, recipe, device):
        values = original(network, batch, recipe, device)
        values.update(
            valid_content_quads=torch.tensor(0.0),
            valid_visibility=torch.tensor(0.0),
            positive_visibility=torch.tensor(0.0),
        )
        return values

    monkeypatch.setattr(workflow, "screen_grid_losses", zero_head)
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_HEAD_EXPOSURE_REQUIRED"):
        fixture.invoke()
    state = fixture.ledger()["state"]
    assert state["arms"]["R3"]["completedSteps"] == 1200
    assert state["arms"]["R3"]["status"] == "running"
    assert state["selectedArm"] is None and fixture.final_exports == 0
    assert [arm for arm, _ in fixture.train_calls] == ["R3"]


@pytest.mark.parametrize(
    "exposure",
    [
        None,
        {"quadTargets": 0, "localVisibilityTargets": 2, "optimizerSteps": 1},
        {"quadTargets": 2, "localVisibilityTargets": 0, "optimizerSteps": 1},
        {"quadTargets": 2, "localVisibilityTargets": 2, "optimizerSteps": 201},
    ],
)
def test_head_exposure_must_describe_positive_targets_at_best(exposure):
    with pytest.raises(ValueError, match="CONTENT_EXPERIMENT_HEAD_EXPOSURE_REQUIRED"):
        workflow.require_head_exposure(exposure, 200)
    workflow.require_head_exposure(
        {"quadTargets": 1, "localVisibilityTargets": 1, "optimizerSteps": 200}, 200
    )
