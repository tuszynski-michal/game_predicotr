"""Small CPU fixtures exercise contracts; they do not qualify an operator model."""

from copy import deepcopy

import pytest
import torch
from game_predictor_worker.training_core.grid_content_experiment import (
    ARMS,
    advance_state,
    arm_preset,
    build_plan,
    charge_selected_export,
    init_state,
    require_plan,
    require_state,
    select_winner,
    selection_record,
    start_arm,
)
from game_predictor_worker.training_core.grid_training import (
    TrainingInterrupted,
    TrainingPlan,
    apply_freeze,
    train,
    train_mode,
)
from game_predictor_worker.training_core.grid_training_admission import (
    CONTENT_LIMIT_POLICY,
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
    digest,
)


def closed_plan():
    return build_plan(
        base_version_id="approved-base",
        base_manifest_sha256="a" * 64,
        base_weights_sha256="b" * 64,
        cohorts=[{"gameId": "game", "cohortId": "cohort", "manifestSha256": "c" * 64}],
        train_eligibility_sha256="d" * 64,
        selection_roster_sha256="e" * 64,
        calibration_roster_sha256="f" * 64,
        regression_roster_sha256="0" * 64,
    )


def game(*, damaged=0, usable=9, photos=1, game_id="game"):
    metrics = {
        "photos": photos,
        "full_photos": photos,
        "partial_photos": 0,
        "boards_expected": photos * 9,
        "boards_matched": photos * 9,
        "boards_correct": photos * 9,
        "board_correct_rate": 1.0,
        "detection_recall": 1.0,
        "normalized_error": 0.01,
        "photo_complete_correct": photos,
        "photo_complete_correct_rate": 1.0,
        "false_boards": 0,
        "duplicate_predictions": 0,
    }
    counts = {
        "preserved": photos * 135 - damaged,
        "borderline": damaged,
        "clipped": 0,
        "missing": 0,
        "wrongCells": 0,
        "ties": 0,
        "foreignSymbols": 0,
        "ambiguousBoards": 0,
        "usableBoards": usable,
    }
    content = {
        "state": "ready",
        "reasonCodes": [],
        "photos": photos,
        "fullPhotos": photos,
        "slots": photos * 135,
        "visible": photos * 135,
        "unknown": 0,
        "occluded": 0,
        "outOfFrame": 0,
        "referenceSha256": "1" * 64,
        "base": dict(counts),
        "candidate": dict(counts),
        "degradedInstances": damaged,
        "newWrongCells": 0,
        "newTies": 0,
        "newForeignSymbols": 0,
        "newMatchAmbiguities": 0,
    }
    return {
        "gameId": game_id,
        "quality": {"photos": photos, "base": dict(metrics), "candidate": dict(metrics)},
        "content": content,
        "u": 0.01,
        "delta": 0.001,
        "measurementSha256": "2" * 64,
        "auxiliary": {
            "baselineUsablePhotos": 0,
            "candidateUsablePhotos": usable // 9,
            "newClipped": 0,
            "newBorderline": damaged,
            "newDamagedInstances": damaged,
        },
    }


def test_closed_plan_hash_and_budget_do_not_inherit_legacy_floor():
    plan = closed_plan()
    assert require_plan(plan) == plan
    assert [a["reservedSeconds"] for a in plan["arms"]] == [1500, 1500, 2100, 2100]
    assert RunBudget.for_preset(SCREEN_GRID_CORRECTIONS_V1, "train").max_steps == 8000
    budget = RunBudget.for_preset(SCREEN_GRID_CORRECTIONS_V1, "train", content_experiment=plan)
    assert (budget.max_steps, budget.max_seconds, budget.limit_policy) == (
        4800,
        7200,
        CONTENT_LIMIT_POLICY,
    )
    spent = budget.start_attempt().reserve_step().charge(35)
    assert (
        RunBudget.from_payload(spent.to_payload()).with_current_limits(SCREEN_GRID_CORRECTIONS_V1)
        == spent
    )
    changed = deepcopy(plan)
    changed["arms"][0]["plannedSteps"] = 1199
    changed["sha256"] = digest({k: v for k, v in changed.items() if k != "sha256"})
    with pytest.raises(ValueError, match="PLAN_CHANGED"):
        require_plan(changed)


def test_experiment_admission_keeps_safety_checks_and_never_renews_budget():
    from game_predictor_worker.training_core.grid_training_admission import (
        CohortCounts,
        evaluate_admission,
    )
    from test_grid_training_resource_admission import GPU

    kwargs = dict(
        preset_id=SCREEN_GRID_CORRECTIONS_V1.preset_id,
        preset_fingerprint=SCREEN_GRID_CORRECTIONS_V1.fingerprint,
        purpose="train",
        runtime=GPU,
        lease_state="free",
        counts=CohortCounts("screen+grid", 90, 10, 10, 45, 5, 45, 5),
        content_experiment=closed_plan(),
    )
    admitted = evaluate_admission(**kwargs)
    assert admitted.admitted and admitted.cost is None
    spent = admitted.budget.reserve_step().charge(100)
    resumed = evaluate_admission(**kwargs, stored_budget=spent)
    assert resumed.budget.used_seconds == 100 and resumed.budget.reserved_steps == 1
    assert resumed.budget.max_steps == 4800
    missing_gpu = evaluate_admission(**{**kwargs, "runtime": None})
    assert not missing_gpu.admitted and "GRID_RUN_GPU_UNAVAILABLE" in missing_gpu.reasons
    legacy = RunBudget.for_preset(SCREEN_GRID_CORRECTIONS_V1, "train")
    assert not evaluate_admission(**kwargs, stored_budget=legacy).admitted


def test_state_restart_replay_reserve_and_r3_gate():
    plan = closed_plan()
    state = init_state(plan, "3" * 64)
    for arm in ARMS[:3]:
        state = start_arm(plan, state, arm, feasible_seconds=1400)
        partial = advance_state(
            plan,
            state,
            arm,
            completed_steps=600,
            charged_seconds=500,
            checkpoint_sha256="4" * 64,
            selection=selection_record([game(damaged=1, usable=8)], arm, 600),
        )
        assert require_state(plan, deepcopy(partial)) == partial
        assert (
            advance_state(plan, partial, arm, completed_steps=600, charged_seconds=500) == partial
        )
        with pytest.raises(ValueError, match="SELECTION_INVALID"):
            advance_state(
                plan,
                partial,
                arm,
                completed_steps=600,
                charged_seconds=500,
                selection=selection_record([game(damaged=2, usable=8)], "R3", 600),
            )
        with pytest.raises(ValueError, match="BUDGET_RESET"):
            advance_state(plan, partial, arm, completed_steps=600, charged_seconds=499)
        with pytest.raises(ValueError, match="RESERVE_REQUIRED"):
            start_arm(plan, partial, arm, feasible_seconds=2101)
        with pytest.raises(ValueError, match="INCOMPLETE_ARM"):
            advance_state(
                plan, partial, arm, completed_steps=600, charged_seconds=501, complete=True
            )
        state = advance_state(
            plan, partial, arm, completed_steps=1200, charged_seconds=1000, complete=True
        )
    with pytest.raises(ValueError, match="R3_NOT_ELIGIBLE"):
        start_arm(plan, state, "R3", feasible_seconds=2000, r2_gate_passed=False)
    running = start_arm(
        plan, state, "R3", feasible_seconds=2000, r2_gate_passed=False, human_labels_ready=True
    )
    assert running["chargedSeconds"] == 3000
    with pytest.raises(ValueError, match="ARM_RUNNING"):
        select_winner(plan, running)
    with pytest.raises(ValueError, match="REQUIRED_ARM_INCOMPLETE"):
        select_winner(plan, state)
    finished = advance_state(
        plan,
        running,
        "R3",
        completed_steps=1200,
        charged_seconds=1000,
        checkpoint_sha256="5" * 64,
        selection=selection_record([game(damaged=1, usable=8)], "R3", 1200),
        complete=True,
    )
    assert select_winner(plan, finished)["selectedArm"] == "R0"


def test_rank_is_union_equal_game_and_gate_cannot_be_compensated():
    few = game(damaged=1, usable=8)
    many = game(damaged=100, usable=8, photos=100, game_id="large")
    result = selection_record([few, many], "R2", 200)
    assert result["rank"][0] == pytest.approx(1 / 135)
    assert not result["gatePassed"]
    # Same cell with two new failure categories stays one damaged instance.
    few["content"]["newWrongCells"] = 1
    assert selection_record([few], "R0", 200)["rank"][0] == pytest.approx(1 / 135)
    assert selection_record([game()], "R0", 200)["gatePassed"]
    few["auxiliary"]["newDamagedInstances"] = 0
    with pytest.raises(ValueError, match="UNION_INVALID"):
        selection_record([few], "R0", 200)


def test_batchnorm_stats_keeps_affine_gradient_after_repeated_mode_changes():
    layer = torch.nn.BatchNorm1d(3)
    before = layer.running_mean.clone()
    for _ in range(2):
        train_mode(layer, ("batchnorm_stats",))
        layer(torch.ones(4, 3)).sum().backward()
        assert layer.weight.requires_grad and layer.weight.grad.abs().sum() > 0
        assert torch.equal(before, layer.running_mean)
        layer.eval()
    legacy = torch.nn.BatchNorm1d(3)
    apply_freeze(legacy, ("batchnorm",))
    assert not legacy.weight.requires_grad and not legacy.bias.requires_grad


def test_winner_requires_all_arms_prefers_gate_pass_and_export_charges_same_reserve():
    plan = closed_plan()
    state = init_state(plan, "3" * 64)
    for arm in ARMS[:3]:
        row = game(usable=9 if arm == "R0" else 8)
        if arm == "R0":
            row["quality"]["candidate"]["detection_recall"] = 0.9
        state = start_arm(plan, state, arm, feasible_seconds=1400)
        state = advance_state(
            plan,
            state,
            arm,
            completed_steps=1200,
            charged_seconds=1200,
            checkpoint_sha256="4" * 64,
            selection=selection_record([row], arm, 1200),
            complete=True,
        )
    selected = select_winner(plan, state)
    assert selected["selectedArm"] == "R1"  # R0 had the numerically better rank but failed A.
    charged = charge_selected_export(plan, selected, charged_seconds=1400)
    assert charged["chargedSeconds"] == 3800
    assert charged["arms"]["R1"]["selection"] == selected["arms"]["R1"]["selection"]
    assert charge_selected_export(plan, charged, charged_seconds=1400) == charged
    with pytest.raises(ValueError, match="BUDGET_RESET"):
        charge_selected_export(plan, charged, charged_seconds=1399)
    with pytest.raises(ValueError):
        charge_selected_export(plan, charged, charged_seconds=1501)


def execution(arm="R1"):
    plan = closed_plan()
    return TrainingPlan.of(
        "run",
        20261108,
        arm_preset(arm),
        1200,
        {
            "contentExperiment": {
                "planSha256": plan["sha256"],
                "bankSha256": "3" * 64,
                "arm": arm,
                "rankVersion": "production-content-a-rank-v1",
            }
        },
    )


def test_actual_core_completes_1200_despite_stale_rank_and_resumes(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from game_predictor_worker.training_core.checkpoint import load_checkpoint
    from test_durable_v3_grid_training import Control, Tiny, batches, losses

    torch.set_num_threads(1)

    class Tracking(Control):
        step = 0

        def progress(self, step, total, values):
            self.step = step

    def run(control, path, resume=None):
        def measured(_):
            row = game(usable=8 if control.step == 200 else 9)
            if control.step != 200:
                row["quality"]["candidate"]["false_boards"] = 1
            return selection_record([row], "R1", control.step)

        return train(
            network=Tiny(),
            preset=arm_preset("R1"),
            plan=execution(),
            batches=batches,
            losses=losses,
            evaluate=measured,
            control=control,
            checkpoint_directory=path,
            resume=resume,
        )

    straight = run(Tracking(), tmp_path / "straight")
    assert straight.steps == 1200 and straight.stop_reason == "completed"
    assert straight.best_step == 200 and len(straight.history) == 6
    interrupted = Tracking(stop_at=650)
    with pytest.raises(TrainingInterrupted):
        run(interrupted, tmp_path / "resume")
    path, sha, step = interrupted.published[-1]
    assert step == 650
    code = """
import json,sys,torch
from pathlib import Path
from game_predictor_worker.training_core.grid_training import train
from test_grid_content_experiment import arm_preset,execution,game,selection_record
from test_durable_v3_grid_training import Control,Tiny,batches,losses
torch.set_num_threads(1)
class Tracking(Control):
 step=0
 def progress(self,step,total,values): self.step=step
control=Tracking()
def measured(_):
 row=game(usable=8 if control.step==200 else 9)
 if control.step!=200: row['quality']['candidate']['false_boards']=1
 return selection_record([row],'R1',control.step)
result=train(network=Tiny(),preset=arm_preset('R1'),plan=execution(),batches=batches,losses=losses,
 evaluate=measured,control=control,checkpoint_directory=Path(sys.argv[3]),resume=(Path(sys.argv[1]),sys.argv[2]))
Path(sys.argv[4]).write_text(json.dumps({'steps':result.steps,'checkpoint_selection':result.checkpoint_selection,
 'history':result.history,'checkpoint_path':str(result.checkpoint_path),'checkpoint_sha256':result.checkpoint_sha256}))
"""
    result_path = tmp_path / "cold-result.json"
    worker = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), sha, str(tmp_path / "resume"), str(result_path)],
        env=dict(os.environ, PYTHONPATH=str(worker / "src") + ";" + str(worker / "tests")),
        timeout=35,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    resumed = SimpleNamespace(**json.loads(result_path.read_text()))
    assert resumed.steps == 1200 and resumed.checkpoint_selection == straight.checkpoint_selection
    assert resumed.history == straight.history
    first = load_checkpoint(
        straight.checkpoint_path, straight.checkpoint_sha256, expected_binding=execution().binding
    )
    cold = load_checkpoint(
        Path(resumed.checkpoint_path),
        resumed.checkpoint_sha256,
        expected_binding=execution().binding,
    )
    assert all(
        torch.equal(value, cold["modelState"][key]) for key, value in first["modelState"].items()
    )
    assert all(
        torch.equal(value, cold["bestState"]["model"][key])
        for key, value in first["bestState"]["model"].items()
    )


def test_nonfinite_new_arm_stops_without_counting_step(tmp_path):
    from test_durable_v3_grid_training import Control, Tiny, batches, losses

    def bad(network, batch):
        result = losses(network, batch)
        return {"total": result["total"] * float("nan")}

    control = Control()
    with pytest.raises(TrainingInterrupted, match="OPTIMIZER_STEP_SKIPPED"):
        train(
            network=Tiny(),
            preset=arm_preset("R1"),
            plan=execution(),
            batches=batches,
            losses=bad,
            evaluate=lambda _: 0.0,
            control=control,
            checkpoint_directory=tmp_path,
        )
    assert control.published[-1][2] == 0


def test_failed_r0_forward_rolls_back_batchnorm_and_rng_at_completed_boundary(tmp_path):
    from game_predictor_worker.training_core.checkpoint import load_checkpoint
    from test_durable_v3_grid_training import Control, Tiny, batches, losses

    network = Tiny()
    buffers = {k: v.clone() for k, v in network.named_buffers()}
    rng = torch.get_rng_state().clone()
    control = Control()

    def bad(model, batch):
        value = losses(model, batch)["total"]
        torch.rand(7)
        return {"total": value * float("nan")}

    with pytest.raises(TrainingInterrupted):
        train(
            network=network,
            preset=arm_preset("R0"),
            plan=execution("R0"),
            batches=batches,
            losses=bad,
            evaluate=lambda _: 0.0,
            control=control,
            checkpoint_directory=tmp_path,
        )
    path, sha, _ = control.published[-1]
    stored = load_checkpoint(path, sha, expected_binding=execution("R0").binding)
    assert all(torch.equal(stored["modelState"][k], v) for k, v in buffers.items())
    assert torch.equal(stored["rng"]["torch"], rng)


def test_screen_optimizer_does_not_claim_or_decay_skipped_board(tmp_path):
    from game_predictor_worker.training_core.grid_rescue_training import ContentTrainingExposure
    from test_durable_v3_grid_training import Control, Tiny, batches

    network = Tiny()
    before = {k: v.clone() for k, v in network.board.state_dict().items()}
    exposure = ContentTrainingExposure(closed_plan(), "R1")
    member = {
        "gameId": "game",
        "sourceId": "source",
        "sourceSha256": "a" * 64,
        "cohortSha256": "c" * 64,
    }

    def batch(step):
        return {
            **batches(step),
            "image": torch.zeros(1, 3, 576, 768),
            "crops": torch.zeros(1, 3, 192, 320),
        }

    def loss(model, data):
        value = model.screen(data["x"]).square().mean() + model.board(data["x"]).sum() * 0
        return {
            "total": value,
            "heat": value,
            "valid_nodes": torch.tensor(0.0),
            "valid_visibility": torch.tensor(0.0),
        }

    with pytest.raises(TrainingInterrupted):
        train(
            network=network,
            preset=arm_preset("R1"),
            plan=execution(),
            batches=batch,
            losses=loss,
            evaluate=lambda _: 0.0,
            control=Control(stop_at=2),
            checkpoint_directory=tmp_path,
            content_exposure=exposure,
            content_exposure_members=lambda *a: {"screen": [member], "board": [member]},
        )
    assert exposure.state()["confirmedSteps"] == 2
    assert set(exposure.state()["games"]["game"]) == {"screen:baseline"}
    assert all(torch.equal(v, before[k]) for k, v in network.board.state_dict().items())


def test_scaler_backoff_is_incomplete_without_any_component_exposure(tmp_path, monkeypatch):
    from game_predictor_worker.training_core.checkpoint import load_checkpoint
    from game_predictor_worker.training_core.grid_rescue_training import ContentTrainingExposure
    from test_durable_v3_grid_training import Control, Tiny, batches, losses

    class Backoff:
        current = 8.0

        def __init__(self, *args, **kwargs):
            pass

        def scale(self, loss):
            return loss

        def unscale_(self, optimizer):
            pass

        def get_scale(self):
            return self.current

        def step(self, optimizer):
            pass

        def update(self):
            self.current /= 2

        def state_dict(self):
            return {"scale": self.current}

    monkeypatch.setattr("torch.amp.grad_scaler.GradScaler", Backoff)
    exposure = ContentTrainingExposure(closed_plan(), "R1")
    control = Control()
    with pytest.raises(TrainingInterrupted, match="OPTIMIZER_STEP_SKIPPED"):
        train(
            network=Tiny(),
            preset=arm_preset("R1"),
            plan=execution(),
            batches=batches,
            losses=losses,
            evaluate=lambda _: 0.0,
            control=control,
            checkpoint_directory=tmp_path,
            content_exposure=exposure,
            content_exposure_members=lambda *a: pytest.fail(
                "Skipped optimizer cannot request members"
            ),
        )
    path, sha, step = control.published[-1]
    assert step == 0 and exposure.state()["confirmedSteps"] == 0
    assert (
        load_checkpoint(path, sha, expected_binding=execution().binding)["bestState"][
            "contentExposureCurrent"
        ]
        == exposure.state()
    )


def test_r3_head_exposure_is_real_optimizer_only_and_pinned_to_best(tmp_path):
    from game_predictor_worker.training_core.checkpoint import load_checkpoint
    from test_durable_v3_grid_training import Control, batches

    class Board(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.content_head = torch.nn.Linear(4, 1)

        def forward(self, value):
            return self.content_head(value)

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.board = Board()

    class Tracking(Control):
        step = 0

        def progress(self, step, total, values):
            self.step = step

    def losses(model, batch):
        value = (model.board(batch["x"]) - batch["y"]).square().mean()
        return {
            "total": value,
            "valid_content_quads": torch.tensor(2.0),
            "valid_visibility": torch.tensor(3.0),
        }

    control = Tracking(stop_at=450)
    with pytest.raises(TrainingInterrupted):
        train(
            network=Model(),
            preset=arm_preset("R3"),
            plan=execution("R3"),
            batches=batches,
            losses=losses,
            evaluate=lambda _: selection_record([game()], "R3", control.step),
            control=control,
            checkpoint_directory=tmp_path,
        )
    path, sha, step = control.published[-1]
    stored = load_checkpoint(path, sha, expected_binding=execution("R3").binding)
    assert step == 450 and stored["bestState"]["step"] == 200
    assert stored["bestState"]["contentHeadExposureCurrent"] == {
        "quadTargets": 900,
        "localVisibilityTargets": 1350,
        "optimizerSteps": 450,
    }
    assert stored["bestState"]["contentHeadExposureAtBest"] == {
        "quadTargets": 400,
        "localVisibilityTargets": 600,
        "optimizerSteps": 200,
    }


def test_legacy_presets_serialize_identically_to_v575_in_fresh_process():
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    code = """
import subprocess,sys,types
from game_predictor_worker.training_core.grid_training_admission import PRESETS
source=subprocess.run(['git','show','ac724d297448785bdcb98b17dc6a3d5e3fc104e5:services/worker/src/game_predictor_worker/training_core/grid_training_admission.py'],check=True,capture_output=True,text=True,timeout=10).stdout
module=types.ModuleType('legacy_admission');sys.modules[module.__name__]=module
exec(compile(source,'<v575-admission>','exec'),module.__dict__)
assert set(PRESETS)==set(module.PRESETS)
for key in PRESETS:
 assert PRESETS[key].parameters()==module.PRESETS[key].parameters(),key
 assert PRESETS[key].fingerprint==module.PRESETS[key].fingerprint,key
print('legacy4 exact parameters/fingerprints PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=dict(os.environ),
        timeout=20,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
