"""One existing child executes the closed experiment with a durable shared ledger."""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import torch
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.grid_visibility_contract import GridOutputContract

from ..geometry_core.rescue import GridRescueVariantV2
from ..training_core.grid_content_experiment import (
    ARM_SECONDS,
    ARMS,
    RANK_VERSION,
    advance_state,
    arm_preset,
    init_state,
    require_plan,
    require_state,
    select_winner,
    start_arm,
)
from ..training_core.grid_rescue_training import ContentTrainingExposure
from ..training_core.grid_training import (
    TrainingPlan,
    best_weights,
    namespace,
    screen_grid_losses,
    train,
)
from ..training_core.neural_grid_network import NeuralGridNetwork
from ..training_core.runtime import TrainingInterrupted
from .grid_cohort_dataset import GridCohortSnapshot
from .grid_content_experiment_data import (
    ContentSelectionEvaluator,
    measure_bank,
    torch_engine,
    verify_inputs,
)
from .grid_training_data import (
    CohortPhotos,
    JointPhotos,
    ScreenGridBatches,
    content_references,
    validation_crops,
)


class ExperimentLedger:
    """Checksummed file state; authoritative global wall-time is still the supervisor budget."""

    def __init__(
        self,
        path: Path,
        plan: Any,
        bank: Any,
        spec: Any,
        clock: Any = time.monotonic,
        *,
        started: float | None = None,
    ) -> None:
        self.path, self.plan, self.clock = path, plan, clock
        self.started = clock() if started is None else started
        self.prior_global = float(spec["budget"].get("chargedSeconds", 0))
        if path.exists():
            value = json.loads(path.read_bytes())
            body = {k: v for k, v in value.items() if k != "sha256"}
            if (
                value.get("sha256") != digest(body)
                or body["planSha256"] != plan["sha256"]
                or body["bankSha256"] != bank["sha256"]
            ):
                raise ValueError("CONTENT_EXPERIMENT_LEDGER_CHANGED")
            self.value = body
            require_state(plan, body["state"])
            self._validate()
        else:
            self.value = {
                "schemaVersion": "content-experiment-child-ledger-v1",
                "planSha256": plan["sha256"],
                "bankSha256": bank["sha256"],
                "state": init_state(plan, bank["sha256"]),
                "checkpoints": {},
                "results": {},
                "preflight": {},
            }
            self.save()

    def _validate(self) -> None:
        if (
            set(self.value)
            != {
                "schemaVersion",
                "planSha256",
                "bankSha256",
                "state",
                "checkpoints",
                "results",
                "preflight",
            }
            or self.value["schemaVersion"] != "content-experiment-child-ledger-v1"
        ):
            raise ValueError("CONTENT_EXPERIMENT_LEDGER_CHANGED")
        if any(set(self.value[key]) - set(ARMS) for key in ("checkpoints", "results", "preflight")):
            raise ValueError("CONTENT_EXPERIMENT_LEDGER_CHANGED")
        for arm, row in self.state["arms"].items():
            pointer = self.value["checkpoints"].get(arm)
            if pointer is not None and (
                set(pointer) != {"path", "sha256", "localStep", "globalStep"}
                or Path(pointer["path"]).name != pointer["path"]
                or pointer["sha256"] != row["checkpointSha256"]
                or pointer["localStep"] != row["completedSteps"]
                or pointer["globalStep"] != ARMS.index(arm) * 1200 + pointer["localStep"]
            ):
                raise ValueError("CONTENT_EXPERIMENT_CHECKPOINT_CHANGED")
            if row["completedSteps"] and pointer is None:
                raise ValueError("CONTENT_EXPERIMENT_CHECKPOINT_REQUIRED")
            if row["status"] == "complete":
                result = self.value["results"].get(arm)
                if (
                    result is None
                    or result["steps"] != 1200
                    or result["checkpoint_sha256"] != row["checkpointSha256"]
                    or result["checkpoint_selection"] != row["selection"]
                ):
                    raise ValueError("CONTENT_EXPERIMENT_RESULT_CHANGED")
                if result["checkpoint_path"] != pointer["path"]:
                    raise ValueError("CONTENT_EXPERIMENT_CHECKPOINT_CHANGED")

    @property
    def state(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.value["state"])

    def save(self) -> None:
        from .grid_training_child import write_json_atomic

        write_json_atomic(self.path, {**self.value, "sha256": digest(self.value)})

    def arm_seconds(self, arm: str) -> float:
        others = sum(row["chargedSeconds"] for key, row in self.state["arms"].items() if key != arm)
        return float(
            max(
                self.state["arms"][arm]["chargedSeconds"],
                self.prior_global + self.clock() - self.started - others,
            )
        )

    def charge(self, arm: str, **kwargs: Any) -> None:
        elapsed = self.arm_seconds(arm)
        limit = ARM_SECONDS[ARMS.index(arm)]
        row = self.state["arms"][arm]
        self.value["state"] = advance_state(
            self.plan,
            self.state,
            arm,
            completed_steps=kwargs.pop("completed_steps", row["completedSteps"]),
            charged_seconds=min(elapsed, limit),
            **kwargs,
        )
        self.save()
        if elapsed >= limit:
            raise TrainingInterrupted("CONTENT_EXPERIMENT_ARM_BUDGET_EXHAUSTED")


class ArmControl:
    def __init__(self, parent: Any, ledger: ExperimentLedger, arm: str) -> None:
        self.parent, self.ledger, self.arm = parent, ledger, arm
        self.offset = ARMS.index(arm) * 1200
        self.local_step = ledger.state["arms"][arm]["completedSteps"]

    def before_step(self, step: int) -> None:
        self.ledger.charge(self.arm)
        self.parent.before_step(self.offset + step)

    def progress(self, step: int, total: int, losses: Any) -> None:
        self.local_step = step
        self.ledger.charge(self.arm)
        self.parent.progress(self.offset + step, 4800, losses)

    def checkpoint_published(self, path: Path, sha256: str, step: int) -> None:
        self.local_step = step
        self.ledger.value["checkpoints"][self.arm] = {
            "path": path.name,
            "sha256": sha256,
            "localStep": step,
            "globalStep": self.offset + step,
        }
        self.ledger.charge(self.arm, completed_steps=step, checkpoint_sha256=sha256)
        self.parent.checkpoint_published(path, sha256, self.offset + step)

    def check(self) -> None:
        # Evaluation consumes time but reserves no extra optimizer step at the 1200 boundary.
        self.ledger.charge(self.arm)
        self.parent.check()


def _network(recipe: Any, weights: Any, device: str, arm: str) -> Any:
    torch.manual_seed(20261108)
    network = NeuralGridNetwork(recipe.board.stride, content_head=arm == "R3")
    missing, unexpected = network.load_state_dict(weights, strict=arm != "R3")
    if unexpected or (arm != "R3" and missing) or any("content" not in key for key in missing):
        raise ValueError("CONTENT_EXPERIMENT_BASE_WEIGHTS_CHANGED")
    return network.to(device)


def _result_json(result: Any) -> dict[str, Any]:
    value = asdict(result)
    value["checkpoint_path"] = result.checkpoint_path.name
    return value


def require_head_exposure(exposure: Any, best_step: int) -> None:
    """An untrained auxiliary head cannot satisfy the required R3 arm."""
    keys = {"quadTargets", "localVisibilityTargets", "optimizerSteps"}
    if (
        not isinstance(exposure, dict)
        or set(exposure) != keys
        or any(type(exposure[k]) is not int or exposure[k] <= 0 for k in keys)
        or exposure["optimizerSteps"] > best_step
    ):
        raise ValueError("CONTENT_EXPERIMENT_HEAD_EXPOSURE_REQUIRED")


def run_experiment(
    spec: Any, run_dir: Path, root: Path, lease: Any, record: Any, counter: Any
) -> dict[str, Any]:
    started = time.monotonic()
    from ..training_core.grid_training import preset_payload_fingerprint
    from .grid_training_child import (
        RECIPE_FILE,
        RECIPE_FINGERPRINT,
        ChildControl,
        _base,
        _export,
        sha256_file,
        write_json_atomic,
    )

    plan = require_plan(spec["contentExperiment"])
    inputs = spec["contentExperimentInputs"]
    weights_path, base_payload, _ = _base(spec, root)
    if (
        plan["baseVersionId"] != spec["base"]["versionId"]
        or plan["baseWeightsSha256"] != spec["base"]["weightsSha256"]
    ):
        raise ValueError("CONTENT_EXPERIMENT_BASE_CHANGED")
    preset_bytes = RECIPE_FILE.read_bytes()
    recipe_payload = json.loads(preset_bytes)
    if preset_payload_fingerprint(recipe_payload) != RECIPE_FINGERPRINT or any(
        base_payload[k] != recipe_payload[k]
        for k in ("board", "screen", "fit", "backbone", "preprocessing_version")
    ):
        raise ValueError("GRID_TRAINING_RECIPE_CHANGED")
    recipe = namespace(recipe_payload)
    contract = GridOutputContract.model_validate(spec.get("gridOutputContract"))
    if contract.trainedVisibility:
        raise ValueError("GRID_VISIBILITY_INPUT_CANNOT_CLAIM_TRAINING")
    pins = spec["joint"]["cohorts"] if spec.get("joint") else [spec["cohort"]]
    snapshots = [GridCohortSnapshot(root, p["manifestPath"], p["manifestSha256"]) for p in pins]
    verify_inputs(plan, inputs, snapshots)
    device = "cuda" if torch.cuda.is_available() else spec.get("device", "cpu")
    if spec.get("requireCuda", True) and device != "cuda":
        raise ValueError("GRID_RUN_GPU_UNAVAILABLE")
    weights = torch.load(weights_path, map_location="cpu", weights_only=True)
    from game_predictor_api.domain.grid_content_bundle import require_content_bundle_inputs
    from game_predictor_api.storage.grid_content_bundle import read_content_bundle

    require_content_bundle_inputs(plan, inputs)
    baseline = _network(recipe, weights, device, "R0").eval()
    base_engine = torch_engine(baseline, recipe, device)
    parent = ChildControl(spec, run_dir, lease, record, counter)
    parent.started = min(started, float(spec["budget"].get("startedMonotonic", started)))
    bank_path = run_dir / "content-bank.json"
    if bank_path.exists():
        bank = read_content_bundle(bank_path)
        if (
            bank.get("sha256") != digest({k: v for k, v in bank.items() if k != "sha256"})
            or bank["planSha256"] != plan["sha256"]
        ):
            raise ValueError("CONTENT_BANK_CHANGED")
    else:
        bank = measure_bank(
            plan, inputs, snapshots, base_engine, lambda: parent.before_step(counter["step"])
        )
        write_json_atomic(bank_path, bank)
    from game_predictor_api.domain.grid_content_experiment_evidence import require_bank

    require_bank(bank, plan, inputs)
    require_content_bundle_inputs(plan, inputs, bank)
    ledger = ExperimentLedger(
        run_dir / "content-experiment.json", plan, bank, spec, started=parent.started
    )
    train_pairs = [
        (snapshot, pin)
        for snapshot, pin in zip(snapshots, pins, strict=True)
        if snapshot.manifest["counts"]["TRAIN"]["photos"] > 0
    ]
    parts = [CohortPhotos(snapshot, "TRAIN", full_only=True) for snapshot, _ in train_pairs]
    if not parts:
        raise ValueError("CONTENT_EXPERIMENT_TRAIN_REQUIRED")
    photos = (
        parts[0]
        if len(parts) == 1
        else JointPhotos(parts, [pin["recordings"] for _, pin in train_pairs])
    )
    strata = getattr(photos, "strata", None)
    labels_ready = contract.supervision.qualified and any(
        ref is not None
        and ref.humanApproved
        and any(c.state == "visible" and c.quad is not None for c in ref.cells)
        for i in range(len(photos))
        for ref in content_references(photos, i)
    )
    from .grid_rescue_strategy import completeness_routing

    routing = completeness_routing(
        {"policy": "validation-purpose-a-v1", "sha256": plan["selectionRosterSha256"]}, recipe.board
    )
    for arm in ARMS:
        row = ledger.state["arms"][arm]
        if row["status"] == "complete":
            if arm == "R3":
                if not labels_ready:
                    raise ValueError("CONTENT_EXPERIMENT_R3_LABELS_REQUIRED")
                result_pin = ledger.value["results"][arm]
                require_head_exposure(
                    result_pin.get("content_head_exposure"), result_pin["best_step"]
                )
            continue
        if arm == "R3":
            if ledger.state["arms"]["R2"]["selection"]["gatePassed"]:
                break
            if not labels_ready:
                raise ValueError("CONTENT_EXPERIMENT_R3_LABELS_REQUIRED")
        network = _network(recipe, weights, device, arm)
        preset = arm_preset(arm)
        batches = ScreenGridBatches(
            photos,
            recipe,
            preset.batch_items,
            plan["seed"],
            int(spec.get("dataWorkers", preset.data_workers)),
            strata,
            variant=GridRescueVariantV2() if arm in ("R2", "R3") else None,
            output_contract=contract,
            content_experiment=True,
            content_auxiliary=arm == "R3",
        )
        control = ArmControl(parent, ledger, arm)
        evaluate = ContentSelectionEvaluator(
            snapshots,
            base_engine,
            recipe,
            device,
            arm,
            lambda control=control: control.local_step,
            control.check,
            routing,
        )
        training_plan = TrainingPlan.of(
            spec["jobId"],
            plan["seed"],
            preset,
            1200,
            {
                "cohortManifestSha256": spec["cohort"]["manifestSha256"],
                "baseWeightsSha256": plan["baseWeightsSha256"],
                "basePresetSha256": spec["base"]["presetSha256"],
                "mode": "screen+grid",
                "gridOutputContract": contract.model_dump(mode="json"),
                "contentExperiment": {
                    "planSha256": plan["sha256"],
                    "bankSha256": bank["sha256"],
                    "arm": arm,
                    "rankVersion": RANK_VERSION,
                },
            },
        )
        try:
            if row["status"] == "pending":
                # Measure an actual backward pass and actual complete A inference before admission.
                # No optimizer runs; reset the network to the identical pinned base afterwards.
                timings = []
                for step in (0, 1) if arm in ("R2", "R3") else (0,):
                    started = time.monotonic()
                    network.train()
                    values = screen_grid_losses(network, batches(step), recipe, device)
                    values["total"].backward()  # type: ignore[no-untyped-call]
                    if device == "cuda":
                        torch.cuda.synchronize()
                    timings.append(time.monotonic() - started)
                    network.zero_grad(set_to_none=True)
                    del values
                step_seconds = max(timings)
                network.eval()
                timed = ContentSelectionEvaluator(
                    snapshots,
                    base_engine,
                    recipe,
                    device,
                    arm,
                    lambda: 200,
                    lambda: parent.before_step(counter["step"]),
                    routing,
                )
                started = time.monotonic()
                with torch.inference_mode():
                    timed(network)
                validation_seconds = time.monotonic() - started
                from ..training_core.grid_training import export_graphs
                from .grid_content_experiment_export import content_parity

                started = time.monotonic()
                with tempfile.TemporaryDirectory(
                    prefix=".content-preflight-", dir=run_dir
                ) as temporary:
                    network.cpu().eval()
                    export_graphs(
                        network,
                        recipe,
                        Path(temporary),
                        dynamic_board=arm in ("R2", "R3"),
                        content_auxiliary=arm == "R3",
                    )
                    content_parity(
                        network,
                        Path(temporary),
                        CohortPhotos(
                            snapshots[0], "VALIDATION", full_only=False, content_selection=True
                        ),
                        recipe,
                        arm,
                    )
                export_seconds = time.monotonic() - started
                estimate = step_seconds * 1200 + validation_seconds * 6 + export_seconds
                ledger.value["preflight"][arm] = {
                    "device": device,
                    "stepSeconds": step_seconds,
                    "validationSeconds": validation_seconds,
                    "exportSeconds": export_seconds,
                    "estimatedSeconds": estimate,
                }
                setup = ledger.arm_seconds(arm)
                if estimate + setup > ARM_SECONDS[ARMS.index(arm)]:
                    ledger.save()
                    raise ValueError("CONTENT_EXPERIMENT_ARM_INFEASIBLE")
                ledger.value["state"] = start_arm(
                    plan,
                    ledger.state,
                    arm,
                    feasible_seconds=estimate + setup,
                    r2_gate_passed=False if arm == "R3" else None,
                    human_labels_ready=labels_ready,
                )
                ledger.charge(arm)
                network = _network(recipe, weights, device, arm)
            pointer = ledger.value["checkpoints"].get(arm)
            result = train(
                network=network,
                preset=preset,
                plan=training_plan,
                batches=batches,
                losses=lambda net, batch: screen_grid_losses(
                    cast(NeuralGridNetwork, net), batch, recipe, device
                ),
                evaluate=evaluate,
                control=control,
                checkpoint_directory=run_dir / "checkpoints",
                device=device,
                resume=None
                if pointer is None
                else (run_dir / "checkpoints" / pointer["path"], pointer["sha256"]),
                content_exposure=ContentTrainingExposure(plan, arm),
                content_exposure_members=batches.content_exposure_members,
            )
            if arm == "R3" and result.steps == 1200:
                require_head_exposure(result.content_head_exposure, result.best_step)
            ledger.value["results"][arm] = {
                **_result_json(result),
                "binding": training_plan.binding,
            }
            ledger.charge(
                arm,
                completed_steps=result.steps,
                checkpoint_sha256=result.checkpoint_sha256,
                selection=result.checkpoint_selection,
                complete=result.steps == 1200,
            )
        finally:
            batches.close()
            del network
        if result.steps != 1200:
            raise ValueError("CONTENT_EXPERIMENT_INCOMPLETE_ARM")
    ledger.value["state"] = select_winner(plan, ledger.state)
    ledger.save()
    selected = ledger.state["selectedArm"]
    stored = dict(ledger.value["results"][selected])
    binding = stored.pop("binding")
    stored["checkpoint_path"] = run_dir / "checkpoints" / stored["checkpoint_path"]
    result = cast(Any, SimpleNamespace(**stored))
    if sha256_file(result.checkpoint_path) != result.checkpoint_sha256:
        raise ValueError("CONTENT_EXPERIMENT_CHECKPOINT_CHANGED")
    network = _network(recipe, weights, "cpu", selected)
    network.load_state_dict(best_weights(result.checkpoint_path, result.checkpoint_sha256, binding))
    validation = CohortPhotos(snapshots[0], "VALIDATION", full_only=False, content_selection=True)
    crops, _ = validation_crops(validation, recipe)
    proof = {
        "plan": plan,
        "state": ledger.state,
        "inputs": inputs,
        "bank": bank,
        "selectedArm": selected,
        "bestStep": result.best_step,
        "exposure": result.exposure,
        "contentHeadExposure": result.content_head_exposure,
        "preflight": ledger.value["preflight"],
    }

    def finalize(proof: Any) -> Any:
        from ..training_core.grid_content_experiment import charge_selected_export

        ledger.value["state"] = charge_selected_export(
            plan, ledger.state, charged_seconds=ledger.arm_seconds(selected)
        )
        ledger.save()
        return {**proof, "state": ledger.state}

    if not (run_dir / f"export-{result.checkpoint_sha256[:16]}" / "bundle.json").exists() and (
        ledger.arm_seconds(selected) + ledger.value["preflight"][selected]["exportSeconds"]
        > ARM_SECONDS[ARMS.index(selected)]
    ):
        raise ValueError("CONTENT_EXPERIMENT_EXPORT_RESERVE_REQUIRED")

    export = _export(
        spec,
        run_dir,
        network,
        recipe,
        recipe_payload,
        preset_bytes,
        result,
        (crops, validation),
        content_experiment=proof,
        content_finalize=finalize,
    )
    return {
        "status": "exported",
        "steps": sum(r["completedSteps"] for r in ledger.state["arms"].values()),
        "bestStep": result.best_step,
        "bestMetric": result.best_metric,
        "metric": RANK_VERSION,
        "stopReason": "completed",
        "checkpointSelection": result.checkpoint_selection,
        "checkpoint": {"path": result.checkpoint_path.name, "sha256": result.checkpoint_sha256},
        "history": result.history,
        "export": export,
    }
