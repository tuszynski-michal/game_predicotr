"""Actual child/orchestrator/control paths with tiny CPU optimization.

Source readers, model inference and ONNX export are explicit fixture boundaries;
these tests prove workflow accounting/replay, not data or model qualification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
import torch
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
    GridOutputContract,
    visibility_supervision,
)
from game_predictor_worker.images import grid_content_experiment_run as workflow
from game_predictor_worker.images import grid_training_child as child
from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler, RunState
from game_predictor_worker.training_core.grid_content_experiment import (
    require_state,
    selection_record,
)
from game_predictor_worker.training_core.grid_training_admission import (
    SCREEN_GRID_CORRECTIONS_V1,
    RunBudget,
    digest,
)
from game_predictor_worker.training_core.runtime import TrainingInterrupted
from test_grid_content_experiment import closed_plan, game
from test_grid_training_handler import NOW


class LostResponse(RuntimeError):
    pass


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TinyBoard(torch.nn.Module):
    def __init__(self, content):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))
        self.content_head = torch.nn.Linear(1, 1, bias=False) if content else None

    def forward(self, x):
        result = x * self.weight
        return result if self.content_head is None else result + self.content_head(x)


class TinyNetwork(torch.nn.Module):
    def __init__(self, content=False):
        super().__init__()
        self.board = TinyBoard(content)
        self.screen = torch.nn.Linear(1, 1, bias=False)


class WorkflowFixture:
    def __init__(self, tmp_path, monkeypatch, *, r2_fail=False, labels=True, stop_at=None):
        import game_predictor_api.domain.grid_content_experiment_evidence as evidence
        import game_predictor_worker.images.grid_content_experiment_export as export_module
        import game_predictor_worker.training_core.grid_training as core

        torch.set_num_threads(1)
        self.root = tmp_path
        self.run_dir = tmp_path / "same-child"
        self.run_dir.mkdir()
        self.clock = Clock()
        self.train_calls, self.network_calls, self.global_before = [], [], []
        self.bank_calls = self.graph_exports = self.final_exports = self.cached_exports = 0
        self.lost_response = False
        self.step_cost = 0.01
        self.stop_at = stop_at
        self.stop_used = False
        self.plan = closed_plan()
        recipe_bytes = child.RECIPE_FILE.read_bytes()
        recipe_payload = json.loads(recipe_bytes)
        base = TinyNetwork()
        base_weights = {k: v.clone() for k, v in base.state_dict().items()}
        weights_path = tmp_path / "base.pt"
        torch.save(base_weights, weights_path)
        self.plan["baseWeightsSha256"] = hashlib.sha256(weights_path.read_bytes()).hexdigest()
        self.plan["cohorts"][0]["gameId"] = "11111111-1111-4111-8111-111111111111"
        self.plan["sha256"] = digest({k: v for k, v in self.plan.items() if k != "sha256"})
        self.references = (
            [
                BoardContentReference(
                    gameId=self.plan["cohorts"][0]["gameId"],
                    sourceRepresentativeSha256=f"{i + 1:064x}",
                    positionIndex=0,
                    revision=1,
                    humanApproved=True,
                    cells=tuple(
                        [
                            CellContentReference(
                                state="visible", quad=((1, 1), (2, 1), (2, 2), (1, 2))
                            )
                        ]
                        * 8
                        + [CellContentReference(state="occluded")] * 7
                    ),
                )
                for i in range(5)
            ]
            if labels
            else []
        )
        self.spec = {
            "jobId": "same-job",
            "attempt": 1,
            "contentExperiment": self.plan,
            "contentExperimentInputs": {"fixture": "trusted reader boundary"},
            "base": {
                "versionId": self.plan["baseVersionId"],
                "weightsSha256": self.plan["baseWeightsSha256"],
                "presetSha256": hashlib.sha256(recipe_bytes).hexdigest(),
            },
            "cohort": {"manifestPath": "fixture.json", "manifestSha256": "c" * 64},
            "budget": {"remainingSeconds": 7200.0, "remainingSteps": 4800, "chargedSeconds": 0.0},
            "resume": None,
            "requireCuda": False,
            "device": "cpu",
            "dataWorkers": 0,
            "gridOutputContract": GridOutputContract(
                supervision=visibility_supervision(self.references)
            ).model_dump(mode="json"),
        }
        fixture = self
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(workflow, "time", SimpleNamespace(monotonic=self.clock))
        monkeypatch.setattr(
            child, "time", SimpleNamespace(monotonic=self.clock, sleep=self.clock.advance)
        )
        original_ledger = workflow.ExperimentLedger

        class Ledger(original_ledger):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, clock=fixture.clock, **kwargs)

        monkeypatch.setattr(workflow, "ExperimentLedger", Ledger)
        monkeypatch.setattr(child, "_base", lambda *a: (weights_path, recipe_payload, recipe_bytes))
        monkeypatch.setattr(
            workflow,
            "GridCohortSnapshot",
            lambda *a: SimpleNamespace(manifest={"counts": {"TRAIN": {"photos": 1}}}),
        )
        monkeypatch.setattr(workflow, "verify_inputs", lambda *a: None)
        monkeypatch.setattr(evidence, "require_bank", lambda *a: None)
        monkeypatch.setattr(workflow, "torch_engine", lambda *a: SimpleNamespace())
        monkeypatch.setattr(workflow, "CohortPhotos", lambda *a, **k: [SimpleNamespace()])
        monkeypatch.setattr(workflow, "content_references", lambda *a: self.references)
        monkeypatch.setattr(workflow, "validation_crops", lambda *a: (torch.zeros(1).numpy(), None))
        monkeypatch.setattr(child, "supervisor_alive", lambda *a: True)

        def network(recipe, weights, device, arm):
            assert device == "cpu"
            assert all(torch.equal(weights[k], v) for k, v in base_weights.items())
            torch.manual_seed(20261108)
            value = TinyNetwork(arm == "R3")
            value.load_state_dict(weights, strict=arm != "R3")
            fixture.network_calls.append(
                (arm, {k: v.clone() for k, v in value.state_dict().items()})
            )
            return value

        monkeypatch.setattr(workflow, "_network", network)

        def bank(plan, inputs, snapshots, engine, check):
            fixture.bank_calls += 1
            check()
            fixture.clock.advance(0.1)
            body = {"planSha256": plan["sha256"], "fixture": "measured inference boundary"}
            return {**body, "sha256": digest(body)}

        monkeypatch.setattr(workflow, "measure_bank", bank)
        member = {
            "gameId": self.plan["cohorts"][0]["gameId"],
            "sourceId": "source",
            "sourceSha256": "a" * 64,
            "cohortSha256": "c" * 64,
        }

        class Batches:
            def __init__(self, *args, variant=None, content_auxiliary=False, **kwargs):
                self.variant, self.aux = variant, content_auxiliary

            def __call__(self, step):
                fixture.clock.advance(fixture.step_cost)
                big = self.variant is not None and step % 2 == 1
                # Shape-only views attest the orchestration branch, not pixel parity.
                return {
                    "x": torch.tensor([[1.0], [2.0]]),
                    "image": torch.zeros(1).expand(1, 3, 960 if big else 576, 1280 if big else 768),
                    "crops": torch.zeros(1).expand(
                        1, 1, 3, 288 if big else 192, 480 if big else 320
                    ),
                }

            def content_exposure_members(self, *args):
                return {"screen": [member], "board": [member]}

            def close(self):
                pass

        monkeypatch.setattr(workflow, "ScreenGridBatches", Batches)

        def losses(network, batch, recipe, device):
            loss = (network.board(batch["x"]) + network.screen(batch["x"])).square().mean()
            return {
                "total": loss,
                "heat": loss,
                "valid_nodes": torch.tensor(1.0),
                "valid_visibility": torch.tensor(float(network.board.content_head is not None)),
                "positive_visibility": torch.tensor(float(network.board.content_head is not None)),
                "negative_visibility": torch.tensor(0.0),
                "valid_content_quads": torch.tensor(float(network.board.content_head is not None)),
            }

        monkeypatch.setattr(workflow, "screen_grid_losses", losses)

        class Evaluator:
            def __init__(self, snapshots, base_engine, recipe, device, arm, step, check, routing):
                self.arm, self.step, self.check = arm, step, check

            def __call__(self, network):
                self.check()
                fixture.clock.advance(0.02)
                row = game()
                row["gameId"] = fixture.plan["cohorts"][0]["gameId"]
                if r2_fail and self.arm == "R2":
                    row["quality"]["candidate"]["false_boards"] = 1
                return selection_record([row], self.arm, self.step())

        monkeypatch.setattr(workflow, "ContentSelectionEvaluator", Evaluator)

        def graphs(*a, **k):
            fixture.graph_exports += 1
            fixture.clock.advance(0.1)

        monkeypatch.setattr(core, "export_graphs", graphs)
        monkeypatch.setattr(export_module, "content_parity", lambda *a: {"passed": True})
        original_train = workflow.train

        def train(**kwargs):
            fixture.train_calls.append(
                (kwargs["plan"].binding["contentExperiment"]["arm"], kwargs["resume"])
            )
            return original_train(**kwargs)

        monkeypatch.setattr(workflow, "train", train)
        original_before = child.ChildControl.before_step

        def before(parent, step):
            fixture.global_before.append((parent.spec["attempt"], step))
            if fixture.stop_at == step and not fixture.stop_used:
                fixture.stop_used = True
                raise TrainingInterrupted("TEST_SUPERVISOR_LOST")
            return original_before(parent, step)

        monkeypatch.setattr(child.ChildControl, "before_step", before)

        def final_export(
            spec,
            run_dir,
            network,
            recipe,
            recipe_payload,
            preset_bytes,
            result,
            validation,
            *,
            content_experiment,
            content_finalize,
        ):
            directory = run_dir / f"export-{result.checkpoint_sha256[:16]}"
            path = directory / "bundle.json"
            if path.exists():
                fixture.cached_exports += 1
                return json.loads(path.read_text())["export"]
            fixture.final_exports += 1
            fixture.clock.advance(0.4)
            proof = content_finalize(content_experiment)
            directory.mkdir()
            exported = {"directory": directory.name, "checkpointSha256": result.checkpoint_sha256}
            path.write_text(json.dumps({"proof": proof, "export": exported}))
            if fixture.lost_response:
                fixture.lost_response = False
                raise LostResponse("export installed, response lost")
            return exported

        monkeypatch.setattr(child, "_export", final_export)

    def invoke(self):
        child.write_json_atomic(
            self.run_dir / "allowance.json", {"attempt": self.spec["attempt"], "step": 4800}
        )
        lease = SimpleNamespace(renew=lambda record: record)
        counter = {"step": 0 if self.spec["resume"] is None else self.spec["resume"]["step"]}
        return child._train(self.spec, self.run_dir, self.root, lease, None, counter)

    def ledger(self):
        return json.loads((self.run_dir / "content-experiment.json").read_text())

    def resume(self, *, gap=0.0):
        stored = self.ledger()
        pointer = json.loads((self.run_dir / "progress.json").read_text())["checkpoint"]
        self.spec["attempt"] += 1
        self.spec["resume"] = pointer
        charged = stored["state"]["chargedSeconds"] + gap
        self.spec["budget"] = {
            "remainingSeconds": 7200 - charged,
            "remainingSteps": 4800 - pointer["step"],
            "chargedSeconds": charged,
        }
        self.clock.advance(gap)


def test_real_child_dispatch_completes_and_replays_lost_export_response_once(tmp_path, monkeypatch):
    fixture = WorkflowFixture(tmp_path, monkeypatch)
    fixture.lost_response = True
    with pytest.raises(LostResponse):
        fixture.invoke()
    first = fixture.ledger()
    assert first["state"]["selectedArm"] == "R0"
    assert [arm for arm, _ in fixture.train_calls] == ["R0", "R1", "R2"]
    assert all(
        row["completedSteps"] == 1200 for arm, row in first["state"]["arms"].items() if arm != "R3"
    )
    assert first["state"]["arms"]["R3"]["status"] == "pending"
    assert fixture.bank_calls == fixture.final_exports == 1 and fixture.graph_exports == 3
    fixture.resume()
    result = fixture.invoke()
    assert result["steps"] == 3600 and result["status"] == "exported"
    assert len(fixture.train_calls) == 3 and fixture.bank_calls == fixture.final_exports == 1
    assert fixture.cached_exports == 1 and fixture.graph_exports == 3
    assert fixture.ledger()["state"] == first["state"]
    assert (
        fixture.spec["jobId"] == "same-job"
        and fixture.spec["contentExperiment"]["sha256"] == first["planSha256"]
    )


def test_real_arm_resume_650_maps_to_global1850_without_new_plan_or_preflight(
    tmp_path, monkeypatch
):
    fixture = WorkflowFixture(tmp_path, monkeypatch, stop_at=1850)
    with pytest.raises(TrainingInterrupted, match="TEST_SUPERVISOR_LOST"):
        fixture.invoke()
    interrupted = fixture.ledger()
    assert interrupted["checkpoints"]["R1"]["localStep"] == 650
    assert interrupted["checkpoints"]["R1"]["globalStep"] == 1850
    assert interrupted["state"]["arms"]["R1"]["status"] == "running"
    assert interrupted["state"]["selectedArm"] is None
    fixture.resume(gap=5)
    result = fixture.invoke()
    assert result["steps"] == 3600
    assert [arm for arm, _ in fixture.train_calls] == ["R0", "R1", "R1", "R2"]
    assert fixture.train_calls[2][1][1] == interrupted["checkpoints"]["R1"]["sha256"]
    assert fixture.graph_exports == 3 and fixture.bank_calls == 1
    assert (2, 1850) in fixture.global_before and (2, 650) not in fixture.global_before
    assert fixture.ledger()["state"]["chargedSeconds"] >= interrupted["state"]["chargedSeconds"] + 5
    assert fixture.spec["budget"]["remainingSteps"] == 2950


@pytest.mark.parametrize("labels", [False, True])
def test_required_r3_is_not_silently_skipped_after_r2_fails(tmp_path, monkeypatch, labels):
    fixture = WorkflowFixture(tmp_path, monkeypatch, r2_fail=True, labels=labels)
    if not labels:
        with pytest.raises(ValueError, match="R3_LABELS_REQUIRED"):
            fixture.invoke()
        assert fixture.final_exports == 0
        state = fixture.ledger()["state"]
        assert state["selectedArm"] is None and state["arms"]["R3"]["status"] == "pending"
    else:
        result = fixture.invoke()
        state = require_state(fixture.plan, fixture.ledger()["state"])
        assert state["chargedSeconds"] == pytest.approx(fixture.clock() - 1000.0)
        assert fixture.ledger()["preflight"]["R0"]["estimatedSeconds"] == pytest.approx(
            0.01 * 1200 + 0.02 * 6 + 0.1
        )
        assert result["steps"] == 4800 and state["arms"]["R3"]["status"] == "complete"
        assert [arm for arm, _ in fixture.train_calls] == ["R0", "R1", "R2", "R3"]
        assert state["selectedArm"] == "R0"  # A_PASS precedes failed R2.


def test_infeasible_preflight_never_reaches_optimizer_or_candidate(tmp_path, monkeypatch):
    fixture = WorkflowFixture(tmp_path, monkeypatch)
    fixture.step_cost = 2.0
    with pytest.raises(ValueError, match="ARM_INFEASIBLE"):
        fixture.invoke()
    assert not fixture.train_calls and fixture.final_exports == 0
    assert fixture.ledger()["state"]["arms"]["R0"]["status"] == "pending"
    assert fixture.ledger()["preflight"]["R0"]["estimatedSeconds"] > 1500


def test_production_network_factory_uses_same_base_and_seed_for_every_arm(monkeypatch):
    monkeypatch.setattr(
        workflow, "NeuralGridNetwork", lambda stride, content_head=False: TinyNetwork(content_head)
    )
    recipe = SimpleNamespace(board=SimpleNamespace(stride=4))
    base = {k: value.clone() for k, value in TinyNetwork().state_dict().items()}
    for arm in ("R0", "R1", "R2", "R3"):
        first = workflow._network(recipe, base, "cpu", arm)
        assert all(torch.equal(first.state_dict()[key], value) for key, value in base.items())
        second = workflow._network(recipe, base, "cpu", arm)
        assert all(
            torch.equal(value, second.state_dict()[key])
            for key, value in first.state_dict().items()
        )
        with torch.no_grad():
            first.board.weight.add_(10)
        assert torch.equal(
            workflow._network(recipe, base, "cpu", arm).board.weight, base["board.weight"]
        )
    with pytest.raises(ValueError, match="BASE_WEIGHTS_CHANGED"):
        workflow._network(recipe, {**base, "foreign": torch.ones(1)}, "cpu", "R3")


def test_supervisor_recovers_orphan_global_pointer_and_settles_only_new_steps(
    tmp_path, monkeypatch
):
    plan = closed_plan()
    budget = RunBudget.for_preset(SCREEN_GRID_CORRECTIONS_V1, "train", content_experiment=plan)
    state = RunState(
        budget=replace(budget, reserved_steps=1400, used_seconds=75, attempts=1),
        attempt=1,
        charged_at=NOW.isoformat(),
        attempt_start={"reserved": 1200, "step": 1200},
    )
    directory = tmp_path / "checkpoints"
    directory.mkdir()
    data = b"immutable arm R1 checkpoint at local650/global1850"
    sha = hashlib.sha256(data).hexdigest()
    (directory / f"{sha}.pt").write_bytes(data)
    pointer = {"path": f"{sha}.pt", "sha256": sha, "step": 1850}
    child.write_json_atomic(
        tmp_path / "progress.json", {"attempt": 1, "step": 1850, "checkpoint": pointer}
    )
    supervisor = object.__new__(GridTrainingJobHandler)
    supervisor.monotonic = lambda: 0.0
    supervisor.wall_clock = lambda: NOW + timedelta(seconds=20)
    waited, persisted = [], []
    monkeypatch.setattr(supervisor, "_wait_for_own_trainer", lambda *a: waited.append(True))
    monkeypatch.setattr(supervisor, "_verified_export_without_result", lambda *a: None)
    monkeypatch.setattr(supervisor, "_persist", lambda *a: persisted.append(state.payload()))
    job = SimpleNamespace(input_payload={"preset_id": SCREEN_GRID_CORRECTIONS_V1.preset_id})
    supervisor._recover_previous_attempt(SimpleNamespace(), job, state, tmp_path)
    assert waited == [True] and state.checkpoint == pointer
    assert state.budget.logical_completed_steps == 1850 and state.budget.used_seconds == 95
    restarted = RunState.load(json.loads(json.dumps(persisted[-1])), budget)
    restarted.attempt_start = {"reserved": restarted.budget.reserved_steps, "step": 1850}
    assert supervisor._reserve(restarted, 1850) == 2050
    next_data = b"next durable logical checkpoint1851"
    next_sha = hashlib.sha256(next_data).hexdigest()
    (directory / f"{next_sha}.pt").write_bytes(next_data)
    supervisor._adopt_pointer(
        restarted,
        tmp_path,
        {
            "path": f"{next_sha}.pt",
            "sha256": next_sha,
            "step": 1851,
        },
    )
    supervisor._settle_steps(restarted, 1851)
    assert restarted.budget.reserved_steps == 2050
    assert restarted.budget.logical_completed_steps == 1851
    assert restarted.budget.remaining_steps == 2949 and restarted.budget.remaining_seconds == 7105
