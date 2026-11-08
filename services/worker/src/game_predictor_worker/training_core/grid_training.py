"""Resumable V3 grid training shared by the application trainer and the laboratory (TASK-0996).

Neutral core: no application, database or laboratory import. Every step is a pure function
of ``(seed, step)``: the sampler draws its photo from a per-epoch permutation and the
augmentation generator is ``default_rng([seed, step, slot])``. A checkpoint after step N
therefore continues with exactly the indices and seeds that an uninterrupted run would use.
The learning-rate schedule and evaluation points are step based for the same reason; the
charged wall time is enforced by the caller's budget, not by the schedule.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Protocol

import numpy as np
import torch
from torch import nn

from .checkpoint import load_checkpoint, make_checkpoint, restore_checkpoint, write_checkpoint
from .grid_rescue_training import TrainingExposure
from .grid_training_admission import GridTrainingPreset, digest
from .neural_grid_network import NeuralGridNetwork
from .runtime import TrainingInterrupted

CHECKPOINT_POLICY = "grid-training-checkpoint-v1"
CORRECTION_CHECKPOINT_RULE = "validation-board-correct-photo-macro-error-earliest-v1"
PHOTO_CHECKPOINT_RULE = "validation-photo-board-correct-photo-macro-error-earliest-v1"
NONFINITE_LIMIT = 20
BOARD_CORRECT_MAX_NME = 0.02
BOARD_CORRECT_MAX_NODE_ERROR = 0.05
MATCH_MIN_IOU = 0.5
CORNERS = (0, 5, 23, 18)


def namespace(value: Any) -> Any:
    """Read-only attribute view of a preset JSON (lists become tuples)."""
    if isinstance(value, Mapping):
        return SimpleNamespace(**{str(k): namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(namespace(item) for item in value)
    return value


def step_rng(seed: int, step: int, slot: int) -> np.random.Generator:
    return np.random.default_rng([seed, 0x4744, step, slot])


@dataclass(frozen=True)
class StepSampler:
    """Index of slot ``slot`` at global ``step``: a fresh permutation per pass over the data."""

    size: int
    batch: int
    seed: int

    def indices(self, step: int) -> list[int]:
        if self.size <= 0:
            raise ValueError("GRID_TRAINING_EMPTY_DATASET")
        result = []
        for slot in range(self.batch):
            position = step * self.batch + slot
            epoch, offset = divmod(position, self.size)
            order = np.random.default_rng([self.seed, 0x5350, epoch]).permutation(self.size)
            result.append(int(order[offset]))
        return result


@dataclass(frozen=True)
class BalancedSampler:
    """Shared-candidate sampler (TASK-1006): equal weight per game, then per recording.

    ``strata[game][recording]`` lists dataset indices. Every round of ``len(strata)``
    positions visits each game once in a per-round permutation; a game visits its
    recordings in per-pass permutations and draws a photo of the recording from
    ``(seed, game, recording, round)``. A pure function of ``(seed, step)``, so a resume
    continues with the indices of an uninterrupted run; game size never changes weight.
    """

    strata: tuple[tuple[tuple[int, ...], ...], ...]
    batch: int
    seed: int

    def __post_init__(self) -> None:
        if not self.strata or any(
            not game or any(not recording for recording in game) for game in self.strata
        ):
            raise ValueError("GRID_TRAINING_EMPTY_DATASET")

    @property
    def size(self) -> int:
        return sum(len(recording) for game in self.strata for recording in game)

    def indices(self, step: int) -> list[int]:
        result = []
        games = len(self.strata)
        for slot in range(self.batch):
            position = step * self.batch + slot
            round_index, offset = divmod(position, games)
            game = int(
                np.random.default_rng([self.seed, 0x4A47, round_index]).permutation(games)[offset]
            )
            recordings = self.strata[game]
            visit, at = divmod(round_index, len(recordings))
            order = np.random.default_rng([self.seed, 0x4A52, game, visit]).permutation(
                len(recordings)
            )
            recording = recordings[int(order[at])]
            pick = np.random.default_rng([self.seed, 0x4A50, game, int(order[at]), round_index])
            result.append(int(recording[int(pick.integers(len(recording)))]))
        return result


def learning_rate(preset: GridTrainingPreset, progress: float) -> float:
    """Warm-up then cosine to ``final_learning_rate_fraction`` (same curve as the lab)."""
    progress = min(max(progress, 0.0), 1.0)
    if progress < preset.warmup_fraction:
        return preset.learning_rate * progress / max(preset.warmup_fraction, 1e-9)
    span = max(1.0 - preset.warmup_fraction, 1e-9)
    cosine = 0.5 * (1 + math.cos(math.pi * (progress - preset.warmup_fraction) / span))
    floor = preset.final_learning_rate_fraction
    return preset.learning_rate * (floor + (1 - floor) * cosine)


def apply_freeze(network: nn.Module, frozen: Sequence[str]) -> None:
    """Freeze the detector and/or every BatchNorm; re-apply after each ``train()``."""
    unknown = set(frozen) - {"detector", "batchnorm"}
    if unknown:
        raise ValueError("GRID_TRAINING_FREEZE_UNKNOWN")
    if "detector" in frozen:
        screen = getattr(network, "screen", None)
        if screen is None:
            raise ValueError("GRID_TRAINING_FREEZE_UNKNOWN")
        screen.eval()
        screen.requires_grad_(False)
    if "batchnorm" in frozen:
        for module in network.modules():
            if isinstance(module, nn.modules.batchnorm._BatchNorm):
                module.eval()
                module.requires_grad_(False)


def train_mode(network: nn.Module, frozen: Sequence[str]) -> None:
    network.train()
    apply_freeze(network, frozen)


def trainable_parameters(network: nn.Module) -> list[nn.Parameter]:
    return [parameter for parameter in network.parameters() if parameter.requires_grad]


def _weighted_mean(values: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    return (values * weights).sum() / weights.sum().clamp(min=1e-6)


def weighted_node_losses(
    node_logits: torch.Tensor,
    predicted: torch.Tensor,
    nodes: torch.Tensor,
    weights: torch.Tensor,
    board: Any,
    node_weights: torch.Tensor | None = None,
) -> dict[str, torch.Tensor]:
    """Lab node losses with a per-crop weight; equal weights give the lab means exactly."""
    if node_weights is not None:
        if (
            node_weights.shape != nodes.shape[:2]
            or not torch.isfinite(node_weights).all()
            or (node_weights < 0).any()
        ):
            raise ValueError("GRID_NODE_WEIGHTS_INVALID")
        effective = weights[:, None] * node_weights
        # Mask before arithmetic, so an unknown NaN target cannot poison valid gradients.
        nodes = torch.where(effective[..., None] > 0, nodes, torch.zeros_like(nodes))
    coordinate = torch.nn.functional.smooth_l1_loss(
        predicted.float(), nodes, beta=1.0, reduction="none"
    ).mean(dim=-1)
    batch, channels, height, width = node_logits.shape
    xs = torch.arange(width, device=node_logits.device, dtype=torch.float32) + 0.5
    ys = torch.arange(height, device=node_logits.device, dtype=torch.float32) + 0.5
    target_x = (nodes[..., 0] / board.stride)[..., None, None]
    target_y = (nodes[..., 1] / board.stride)[..., None, None]
    gaussian = torch.exp(
        -((xs.view(1, 1, 1, width) - target_x) ** 2 + (ys.view(1, 1, height, 1) - target_y) ** 2)
        / (2 * board.heatmap_sigma**2)
    )
    gaussian = gaussian / gaussian.sum(dim=(2, 3), keepdim=True).clamp(min=1e-6)
    log_probability = torch.log_softmax(node_logits.float().reshape(batch, channels, -1), dim=-1)
    heatmap = -(gaussian.reshape(batch, channels, -1) * log_probability).sum(dim=-1)
    if node_weights is None:
        coordinate, heatmap = coordinate.mean(dim=1), heatmap.mean(dim=1)
    else:
        weights = effective
    return {
        "nodes": _weighted_mean(coordinate, weights) * board.coordinate_loss_weight,
        "node_heatmap": _weighted_mean(heatmap, weights) * board.heatmap_loss_weight,
    }


def _supervised_losses(
    logits: torch.Tensor,
    predicted: torch.Tensor,
    visibility: torch.Tensor,
    nodes: torch.Tensor,
    weights: torch.Tensor,
    batch: Mapping[str, torch.Tensor],
    board: Any,
    device: str,
) -> dict[str, torch.Tensor]:
    if "node_weights" not in batch:
        return weighted_node_losses(logits, predicted, nodes, weights, board)
    node_weights = batch["node_weights"].to(device).reshape(-1, 24).float()
    targets = batch["visibility_targets"].to(device).reshape(-1, 15).float()
    mask = batch["visibility_mask"].to(device).reshape(-1, 15).float()
    if visibility.shape != targets.shape or mask.shape != targets.shape:
        raise ValueError("GRID_VISIBILITY_SHAPE_INVALID")
    if not torch.isfinite(mask).all() or ((mask < 0) | (mask > 1)).any():
        raise ValueError("GRID_VISIBILITY_MASK_INVALID")
    effective = mask * weights[:, None]
    targets = torch.where(effective > 0, targets, torch.zeros_like(targets))
    if not torch.isfinite(targets).all() or ((targets < 0) | (targets > 1)).any():
        raise ValueError("GRID_VISIBILITY_TARGET_INVALID")
    losses = weighted_node_losses(logits, predicted, nodes, weights, board, node_weights)
    raw = torch.nn.functional.binary_cross_entropy_with_logits(
        visibility.float(), targets, reduction="none"
    )
    losses["visibility"] = _weighted_mean(raw, effective) * board.visibility_loss_weight
    losses["total"] = sum(losses.values(), torch.zeros((), device=device))
    losses["valid_nodes"] = ((node_weights * weights[:, None]) > 0).sum().float().detach()
    losses["masked_nodes"] = (node_weights.numel() - losses["valid_nodes"]).detach()
    losses["valid_visibility"] = (effective > 0).sum().float().detach()
    losses["masked_visibility"] = (mask.numel() - losses["valid_visibility"]).detach()
    losses["positive_visibility"] = ((effective > 0) & (targets == 1)).sum().float().detach()
    losses["negative_visibility"] = ((effective > 0) & (targets == 0)).sum().float().detach()
    return losses


def board_only_losses(
    network: NeuralGridNetwork, batch: Mapping[str, torch.Tensor], recipe: Any, device: str
) -> dict[str, torch.Tensor]:
    """Grid-only: the board stage alone; padded crops have weight 0; visibility is masked
    because cohort targets carry no unavailable-cell labels."""
    crops = batch["crops"].to(device, non_blocking=True).float()
    nodes = batch["nodes"].to(device, non_blocking=True)
    weights = batch["weights"].to(device, non_blocking=True).float()
    with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
        node_logits, predicted, visibility = network.board(crops)
    losses = _supervised_losses(
        node_logits, predicted, visibility, nodes, weights, batch, recipe.board, device
    )
    if "total" not in losses:
        losses["total"] = losses["nodes"] + losses["node_heatmap"]
    return losses


def screen_grid_losses(
    network: NeuralGridNetwork, batch: Mapping[str, torch.Tensor], recipe: Any, device: str
) -> dict[str, torch.Tensor]:
    """Screen+grid: detector targets of all nine boards plus weighted crop losses."""
    from .neural_grid_network import focal_loss, offset_loss

    images = batch["image"].to(device, non_blocking=True).float()
    heat = batch["heat"].to(device, non_blocking=True)
    offsets = batch["offsets"].to(device, non_blocking=True)
    offset_weight = batch["offset_weight"].to(device, non_blocking=True)
    crops = batch["crops"].to(device, non_blocking=True).flatten(0, 1).float()
    nodes = batch["nodes"].to(device, non_blocking=True).flatten(0, 1)
    weights = batch["weights"].to(device, non_blocking=True).flatten(0, 1).float()
    with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
        heat_logits, predicted_offsets = network.screen(images)
        node_logits, predicted, visibility = network.board(crops)
    losses = {
        "heat": focal_loss(heat_logits, heat),
        "offsets": offset_loss(predicted_offsets, offsets, offset_weight)
        * recipe.screen.offset_loss_weight,
        **_supervised_losses(
            node_logits, predicted, visibility, nodes, weights, batch, recipe.board, device
        ),
    }
    losses["total"] = sum(
        (
            losses[key]
            for key in ("heat", "offsets", "nodes", "node_heatmap", "visibility")
            if key in losses
        ),
        torch.zeros((), device=device),
    )
    return losses


@dataclass
class EarlyStopping:
    direction: Literal["maximize", "minimize"]
    patience: int
    min_delta: float
    min_evaluations: int
    best: float | None = None
    best_step: int | None = None
    stale: int = 0
    evaluations: int = 0
    selection_rule: str | None = None
    best_error: float | None = None
    best_board: float | None = None

    def update(
        self,
        metric: float,
        step: int,
        normalized_error: float | None = None,
        board_correct_rate: float | None = None,
    ) -> bool:
        """Record one evaluation; True when it is the new best."""
        if not math.isfinite(metric):
            raise ValueError("GRID_TRAINING_METRIC_NONFINITE")
        self.evaluations += 1
        sign = 1.0 if self.direction == "maximize" else -1.0
        improved = self.best is None or sign * (metric - self.best) > self.min_delta
        if self.selection_rule is not None:
            if (
                self.selection_rule not in (CORRECTION_CHECKPOINT_RULE, PHOTO_CHECKPOINT_RULE)
                or normalized_error is None
                or not math.isfinite(normalized_error)
                or not 0 <= normalized_error <= 1
                or not 0 <= metric <= 1
            ):
                raise ValueError("GRID_TRAINING_SELECTION_INVALID")
            if self.best is not None and (self.best_error is None or self.best_step is None):
                raise ValueError("GRID_TRAINING_SELECTION_INVALID")
            improved = self.best is None or (metric, -normalized_error, -step) > (
                self.best,
                -(self.best_error or 0.0),
                -(self.best_step or 0),
            )
            if self.selection_rule == PHOTO_CHECKPOINT_RULE:
                if (
                    board_correct_rate is None
                    or not math.isfinite(board_correct_rate)
                    or not 0 <= board_correct_rate <= 1
                    or (self.best is not None and self.best_board is None)
                ):
                    raise ValueError("GRID_TRAINING_SELECTION_INVALID")
                improved = self.best is None or (
                    metric,
                    board_correct_rate,
                    -normalized_error,
                    -step,
                ) > (
                    self.best,
                    self.best_board or 0.0,
                    -(self.best_error or 0.0),
                    -(self.best_step or 0),
                )
        if improved:
            self.best_board = board_correct_rate
            self.best_error = normalized_error
            self.best, self.best_step, self.stale = metric, step, 0
        else:
            self.stale += 1
        return improved

    @property
    def stop(self) -> bool:
        return self.evaluations >= self.min_evaluations and self.stale >= self.patience

    def state(self) -> dict[str, Any]:
        return {
            "best": self.best,
            "bestStep": self.best_step,
            "stale": self.stale,
            "evaluations": self.evaluations,
            **(
                {"selectionRule": self.selection_rule, "bestError": self.best_error}
                if self.selection_rule
                else {}
            ),
            **(
                {
                    "metricStateVersion": "photo-board-checkpoint-state-v1",
                    "bestBoard": self.best_board,
                }
                if self.selection_rule == PHOTO_CHECKPOINT_RULE
                else {}
            ),
        }

    def restore(self, value: Mapping[str, Any]) -> None:
        if value.get("selectionRule") != self.selection_rule:
            raise ValueError("GRID_TRAINING_SELECTION_POLICY_MISMATCH")
        self.best_error = value.get("bestError")
        self.best, self.best_step = value["best"], value["bestStep"]
        self.stale, self.evaluations = int(value["stale"]), int(value["evaluations"])
        if self.selection_rule == PHOTO_CHECKPOINT_RULE:
            if (
                value.get("metricStateVersion") != "photo-board-checkpoint-state-v1"
                or "bestBoard" not in value
            ):
                raise ValueError("GRID_TRAINING_SELECTION_POLICY_MISMATCH")
            self.best_board = value["bestBoard"]
            if self.best is not None:
                from .grid_correction_metrics import photo_selection_key

                if self.best_board is None or self.best_error is None:
                    raise ValueError("GRID_TRAINING_SELECTION_POLICY_MISMATCH")

                photo_selection_key(
                    {
                        "photoCorrectRate": self.best,
                        "boardCorrectRate": self.best_board,
                        "normalizedError": self.best_error,
                    },
                    self.best_step,
                )


class TrainingControl(Protocol):
    def before_step(self, step: int) -> None:
        """Raise ``TrainingInterrupted`` for cancel, lost lease or a spent budget."""

    def checkpoint_published(self, path: Path, sha256: str, step: int) -> None: ...

    def progress(self, step: int, total: int, losses: Mapping[str, float]) -> None: ...


@dataclass(frozen=True)
class TrainingPlan:
    run_id: str
    seed: int
    total_steps: int
    evaluation_steps: int
    frozen_modules: tuple[str, ...]
    binding: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        run_id: str,
        seed: int,
        preset: GridTrainingPreset,
        planned_steps: int,
        binding: Mapping[str, Any],
    ) -> TrainingPlan:
        if planned_steps < 1:
            raise ValueError("GRID_TRAINING_EMPTY_PLAN")
        interval = preset.early_stopping.evaluation_interval_seconds
        evaluation_steps = max(1, round(interval * preset.steps_per_second_estimate))
        return cls(
            run_id=run_id,
            seed=seed,
            total_steps=min(planned_steps, preset.max_steps),
            evaluation_steps=evaluation_steps,
            frozen_modules=tuple(preset.frozen_modules),
            binding={
                "policy": "grid-training-checkpoint-v3"
                if preset.preset_id == "screen-grid-corrections-v1"
                else "grid-training-checkpoint-v2"
                if preset.preset_id == "grid-corrections-v1"
                else CHECKPOINT_POLICY,
                "runId": run_id,
                "seed": seed,
                "presetFingerprint": preset.fingerprint,
                **dict(binding),
            },
        )


@dataclass(frozen=True)
class TrainingResult:
    stop_reason: Literal["completed", "early_stopping"]
    steps: int
    best_step: int
    best_metric: float
    checkpoint_path: Path
    checkpoint_sha256: str
    history: list[dict[str, Any]]
    checkpoint_selection: dict[str, Any] | None = None
    exposure: dict[str, Any] | None = None
    visibility_exposure: dict[str, int] | None = None


class _ScalerSlot:
    """GradScaler stored in the checkpoint ``schedulerState`` slot."""

    def __init__(self, scaler: Any) -> None:
        self.scaler = scaler

    def state_dict(self) -> dict[str, Any]:
        return dict(self.scaler.state_dict())

    def load_state_dict(self, value: dict[str, Any]) -> None:
        self.scaler.load_state_dict(value)


BatchSource = Callable[[int], Mapping[str, torch.Tensor]]
LossFunction = Callable[[nn.Module, Mapping[str, torch.Tensor]], dict[str, torch.Tensor]]
Evaluator = Callable[[nn.Module], float | dict[str, float]]


def train(
    *,
    network: nn.Module,
    preset: GridTrainingPreset,
    plan: TrainingPlan,
    batches: BatchSource,
    losses: LossFunction,
    evaluate: Evaluator,
    control: TrainingControl,
    checkpoint_directory: Path,
    resume: tuple[Path, str] | None = None,
    device: str = "cpu",
    exposure: TrainingExposure | None = None,
    exposure_members: Callable[[int], Sequence[Mapping[str, str]]] | None = None,
) -> TrainingResult:
    """Step-deterministic loop with an evaluation and a checkpoint every ``evaluation_steps``."""
    from torch.amp.grad_scaler import GradScaler

    network.to(device)
    train_mode(network, plan.frozen_modules)
    optimizer = torch.optim.AdamW(
        trainable_parameters(network), lr=preset.learning_rate, weight_decay=preset.weight_decay
    )
    scaler = _ScalerSlot(GradScaler("cuda", enabled=device.startswith("cuda")))
    generator = torch.Generator().manual_seed(plan.seed)
    stopping = EarlyStopping(
        preset.early_stopping.direction,
        preset.early_stopping.patience,
        preset.early_stopping.min_delta,
        preset.early_stopping.min_evaluations,
        selection_rule=PHOTO_CHECKPOINT_RULE
        if preset.preset_id == "screen-grid-corrections-v1"
        else CORRECTION_CHECKPOINT_RULE
        if preset.preset_id == "grid-corrections-v1"
        else None,
    )
    history: list[dict[str, Any]] = []
    best_state: dict[str, Any] | None = None
    step = 0
    last: tuple[Path, str] | None = None
    visibility_exposure = {"positiveTargets": 0, "negativeTargets": 0, "optimizerSteps": 0}
    visibility_enabled = "gridOutputContract" in plan.binding
    if resume is not None:
        value = load_checkpoint(resume[0], resume[1], expected_binding=plan.binding)
        restore_checkpoint(value, network, optimizer, scaler, generator)
        step, history = int(value["globalStep"]), list(value["history"])
        stored = value["bestState"]
        if not isinstance(stored, dict) or "early" not in stored:
            raise ValueError("CHECKPOINT_INVALID")
        stopping.restore(stored["early"])
        if visibility_enabled:
            visibility_exposure = dict(stored["visibilityExposureCurrent"])
        if exposure is not None:
            exposure.restore(stored["exposureCurrent"], step)
        # An interruption before the first evaluation stores no best model yet.
        best_state = stored if stored.get("model") is not None else None
        last = resume
        if best_state is not None and (stopping.stop or step >= plan.total_steps):
            return _result(stopping, best_state, step, last, history)

    def publish() -> tuple[Path, str]:
        state = (
            best_state if best_state is not None else {"model": None, "step": None, "metric": None}
        )
        checkpoint = make_checkpoint(
            network,
            optimizer,
            scaler,
            generator,
            binding=plan.binding,
            epoch=stopping.evaluations,
            global_step=step,
            history=history,
            best_state={
                **state,
                "early": stopping.state(),
                **(
                    {"visibilityExposureCurrent": dict(visibility_exposure)}
                    if visibility_enabled
                    else {}
                ),
                **({"exposureCurrent": exposure.state()} if exposure is not None else {}),
            },
        )
        path, sha = write_checkpoint(checkpoint_directory, checkpoint)
        load_checkpoint(path, sha, expected_binding=plan.binding)  # published bytes re-read
        control.checkpoint_published(path, sha, step)
        return path, sha

    nonfinite = 0
    last_step = step if last is not None else -1
    while step < plan.total_steps:
        try:
            control.before_step(step)
        except TrainingInterrupted:
            # Cancel, spent budget or a lost supervisor: keep the work up to this step.
            if last_step != step:
                publish()
            raise
        rate = learning_rate(preset, step / plan.total_steps)
        for group in optimizer.param_groups:
            group["lr"] = rate
        train_mode(network, plan.frozen_modules)
        batch = batches(step)
        values = losses(network, batch)
        optimizer.zero_grad(set_to_none=True)
        if not torch.isfinite(values["total"]):
            nonfinite += 1
            if nonfinite > NONFINITE_LIMIT:
                raise ValueError("GRID_TRAINING_LOSS_NONFINITE")
        elif (
            "valid_nodes" not in values
            or "heat" in values
            or float(values["valid_nodes"] + values["valid_visibility"]) > 0
        ):
            nonfinite = 0
            scaler.scaler.scale(values["total"]).backward()
            scaler.scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(trainable_parameters(network), preset.gradient_clip)
            scale_before = scaler.scaler.get_scale()
            scaler.scaler.step(optimizer)
            scaler.scaler.update()
            if (
                visibility_enabled
                and scaler.scaler.get_scale() >= scale_before
                and "valid_visibility" in values
            ):
                positive = int(values["positive_visibility"].detach())
                negative = int(values["negative_visibility"].detach())
                if positive + negative:
                    visibility_exposure["positiveTargets"] += positive
                    visibility_exposure["negativeTargets"] += negative
                    visibility_exposure["optimizerSteps"] += 1
            if exposure is not None and scaler.scaler.get_scale() >= scale_before:
                if exposure_members is None:
                    raise ValueError("GRID_RESCUE_EXPOSURE_MEMBERS_REQUIRED")
                exposure.confirm(step + 1, exposure_members(step))
        step += 1
        control.progress(step, plan.total_steps, {k: float(v.detach()) for k, v in values.items()})
        if step % plan.evaluation_steps and step < plan.total_steps:
            continue
        network.eval()
        with torch.no_grad():
            measured = evaluate(network)
        board_rate = None
        if stopping.selection_rule:
            expected = {
                "boardCorrectRate",
                "normalizedError",
            } | (
                {"photoCorrectRate"} if stopping.selection_rule == PHOTO_CHECKPOINT_RULE else set()
            )
            if not isinstance(measured, dict) or set(measured) != expected:
                raise ValueError("GRID_TRAINING_SELECTION_INVALID")
            metric = float(
                measured[
                    "photoCorrectRate"
                    if stopping.selection_rule == PHOTO_CHECKPOINT_RULE
                    else "boardCorrectRate"
                ]
            )
            if stopping.selection_rule == PHOTO_CHECKPOINT_RULE:
                board_rate = float(measured["boardCorrectRate"])
            error = float(measured["normalizedError"])
        else:
            if isinstance(measured, dict):
                raise ValueError("GRID_TRAINING_SELECTION_INVALID")
            metric, error = float(measured), None
        improved = stopping.update(metric, step, error, board_rate)
        history.append(
            {
                "step": step,
                "metric": metric,
                "improved": improved,
                **({"selectionMetrics": measured} if stopping.selection_rule else {}),
            }
        )
        if improved or best_state is None:
            best_state = {
                "model": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
                "step": step,
                "metric": metric,
                **(
                    {"visibilityExposureAtBest": dict(visibility_exposure)}
                    if visibility_enabled
                    else {}
                ),
                **({"exposureAtBest": exposure.state()} if exposure is not None else {}),
            }
        last = publish()
        last_step = step
        if stopping.stop:
            break
    if last is None or best_state is None:
        raise ValueError("GRID_TRAINING_NO_CHECKPOINT")
    return _result(stopping, best_state, step, last, history)


def _result(
    stopping: EarlyStopping,
    best_state: Mapping[str, Any],
    step: int,
    last: tuple[Path, str],
    history: list[dict[str, Any]],
) -> TrainingResult:
    return TrainingResult(
        stop_reason="early_stopping" if stopping.stop else "completed",
        steps=step,
        best_step=int(best_state["step"]),
        best_metric=float(best_state["metric"]),
        checkpoint_path=last[0],
        checkpoint_sha256=last[1],
        history=list(history),
        exposure=best_state.get("exposureAtBest"),
        visibility_exposure=best_state.get("visibilityExposureAtBest"),
        checkpoint_selection={
            "rule": stopping.selection_rule,
            "role": "VALIDATION",
            "step": stopping.best_step,
            "metrics": {
                "boardCorrectRate": stopping.best_board
                if stopping.selection_rule == PHOTO_CHECKPOINT_RULE
                else stopping.best,
                "normalizedError": stopping.best_error,
                **(
                    {"photoCorrectRate": stopping.best}
                    if stopping.selection_rule == PHOTO_CHECKPOINT_RULE
                    else {}
                ),
            },
            "earlyStopping": {
                "patience": stopping.patience,
                "evaluationsWithoutImprovement": stopping.stale,
                "stopped": stopping.stop,
            },
        }
        if stopping.selection_rule
        else None,
    )


def best_weights(path: Path, sha256: str, binding: Mapping[str, Any]) -> dict[str, torch.Tensor]:
    value = load_checkpoint(path, sha256, expected_binding=dict(binding))
    best = value.get("bestState")
    if not isinstance(best, dict) or not isinstance(best.get("model"), dict):
        raise ValueError("CHECKPOINT_INVALID")
    return dict(best["model"])


# --- validation metrics ----------------------------------------------------------------------


def node_errors(predicted: np.ndarray, label: np.ndarray) -> tuple[float, float]:
    """(NME, max node error), both normalised by the node 0-23 diagonal (metrics v1)."""
    diagonal = float(np.linalg.norm(label[23] - label[0]))
    if diagonal <= 0 or not np.isfinite(predicted).all():
        return math.inf, math.inf
    errors = np.linalg.norm(predicted - label, axis=1) / diagonal
    return float(errors.mean()), float(errors.max())


def board_correct(predicted: np.ndarray, label: np.ndarray) -> bool:
    nme, worst = node_errors(predicted, label)
    return nme <= BOARD_CORRECT_MAX_NME and worst <= BOARD_CORRECT_MAX_NODE_ERROR


def quad_iou(left: np.ndarray, right: np.ndarray) -> float:
    import cv2

    a = left[list(CORNERS)].astype(np.float32)
    b = right[list(CORNERS)].astype(np.float32)
    area_a, area_b = abs(cv2.contourArea(a)), abs(cv2.contourArea(b))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    intersection, _ = cv2.intersectConvexConvex(a, b)
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0 else 0.0


def photo_complete_correct(predicted: Sequence[np.ndarray], labels: Sequence[np.ndarray]) -> bool:
    """Every label matched (max quad IoU >= 0.5, one-to-one) and correct, no extra board."""
    if len(predicted) != len(labels):
        return False
    pairs = sorted(
        (
            (quad_iou(p, label), i, j)
            for i, p in enumerate(predicted)
            for j, label in enumerate(labels)
        ),
        reverse=True,
    )
    used_p: set[int] = set()
    used_l: set[int] = set()
    for iou, i, j in pairs:
        if iou < MATCH_MIN_IOU or i in used_p or j in used_l:
            continue
        if not board_correct(predicted[i], labels[j]):
            return False
        used_p.add(i)
        used_l.add(j)
    return len(used_l) == len(labels)


# --- export ------------------------------------------------------------------------------------

OPSET = 18
RAW_TOLERANCE = 1e-4
# D-561 (TASK-1001): raw outputs include source-pixel node coordinates of a few hundred
# pixels, where fp32 rounding alone reaches 1e-4. The tolerance is therefore relative to the
# torch output with a floor of one: unchanged for unit-range outputs, 1e-4 relative above.
PARITY_SCALE = "max(1,|torch|)"


def scaled_delta(expected: np.ndarray, actual: np.ndarray) -> float:
    """Largest torch/ONNX difference relative to max(1, |torch|); NaN stays NaN."""
    if not expected.size:
        return 0.0
    difference = np.abs(expected.astype(np.float64) - actual.astype(np.float64))
    return float(np.max(difference / np.maximum(1.0, np.abs(expected.astype(np.float64)))))


def parity_verdict(
    outputs: Sequence[tuple[str, np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    """Parity document of named (torch, ONNX) output pairs."""
    absolute = {
        name: float(np.max(np.abs(left - right))) if left.size else 0.0
        for name, left, right in outputs
    }
    scaled = {name: scaled_delta(left, right) for name, left, right in outputs}
    passed = all(math.isfinite(v) and v <= RAW_TOLERANCE for v in scaled.values()) and all(
        math.isfinite(v) for v in absolute.values()
    )
    return {
        "tolerance": RAW_TOLERANCE,
        "toleranceScale": PARITY_SCALE,
        "maxDelta": absolute,
        "maxScaledDelta": scaled,
        "passed": passed,
    }


def export_graphs(network: NeuralGridNetwork, preset: Any, directory: Path) -> None:
    """ONNX graphs of both stages (moved unchanged from the laboratory, duck-typed preset)."""
    from .neural_grid_network import BoardExport, ScreenExport

    network = network.cpu().eval()
    canvas_w, canvas_h = preset.screen.train_canvas
    batch = torch.export.Dim("batch", min=1, max=64)
    height = torch.export.Dim("height32", min=2, max=64)
    width = torch.export.Dim("width32", min=2, max=64)
    torch.onnx.export(
        ScreenExport(network.screen).eval(),
        (torch.zeros((1, 3, canvas_h, canvas_w)),),
        str(directory / "screen.onnx"),
        input_names=["pixels"],
        output_names=["heat", "offsets"],
        opset_version=OPSET,
        dynamo=True,
        verbose=False,
        external_data=False,
        dynamic_shapes=({0: batch, 2: 32 * height, 3: 32 * width},),
    )
    board_w, board_h = preset.board.canvas
    torch.onnx.export(
        BoardExport(network.board).eval(),
        (torch.zeros((2, 3, board_h, board_w)),),
        str(directory / "board.onnx"),
        input_names=["crops"],
        output_names=["nodes", "peak", "visibility"],
        opset_version=OPSET,
        dynamo=True,
        verbose=False,
        external_data=False,
        dynamic_shapes=({0: torch.export.Dim("crops", min=1, max=64)},),
    )


def raw_parity(
    network: NeuralGridNetwork,
    directory: Path,
    crops: np.ndarray,
    pixels: np.ndarray | None,
) -> dict[str, Any]:
    """Max raw delta between fp32 torch and ONNX Runtime CPU on the given inputs."""
    import onnxruntime  # type: ignore[import-untyped]

    from .neural_grid_network import BoardExport, ScreenExport

    network = network.cpu().eval()
    outputs: list[tuple[str, np.ndarray, np.ndarray]] = []
    session = onnxruntime.InferenceSession(
        str(directory / "board.onnx"), providers=["CPUExecutionProvider"]
    )
    with torch.no_grad():
        expected = [t.numpy() for t in BoardExport(network.board)(torch.from_numpy(crops))]
    actual = session.run(None, {"crops": crops})
    for name, left, right in zip(("nodes", "peak", "visibility"), expected, actual, strict=True):
        outputs.append((f"board.{name}", left, right))
    if pixels is not None:
        session = onnxruntime.InferenceSession(
            str(directory / "screen.onnx"), providers=["CPUExecutionProvider"]
        )
        with torch.no_grad():
            expected = [t.numpy() for t in ScreenExport(network.screen)(torch.from_numpy(pixels))]
        actual = session.run(None, {"pixels": pixels})
        for name, left, right in zip(("heat", "offsets"), expected, actual, strict=True):
            outputs.append((f"screen.{name}", left, right))
    return parity_verdict(outputs)


def weights_bytes(state: Mapping[str, torch.Tensor]) -> bytes:
    stream = io.BytesIO()
    torch.save(dict(state), stream)
    return stream.getvalue()


def bundle_document(
    *,
    preset_payload: Mapping[str, Any],
    preset_fingerprint: str,
    weights_sha256: str,
    files: Mapping[str, str],
    provenance: Mapping[str, Any],
    parity: Mapping[str, Any],
    model_version: str = "neural-grid-v1",
    output_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if output_contract is not None and model_version == "neural-grid-v1":
        model_version = "neural-grid-v2"
    return {
        "format": "neural-grid-bundle-v1" if output_contract is None else "neural-grid-bundle-v2",
        "model_version": model_version,
        "preset": dict(preset_payload),
        "preset_fingerprint": preset_fingerprint,
        "weights_sha256": weights_sha256,
        "opset": OPSET,
        "files": dict(files),
        "provenance": dict(provenance),
        "parity": dict(parity),
        **({"gridOutputContract": dict(output_contract)} if output_contract is not None else {}),
    }


def preset_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    return digest(dict(payload))


__all__ = [
    "CHECKPOINT_POLICY",
    "EarlyStopping",
    "StepSampler",
    "TrainingControl",
    "TrainingInterrupted",
    "TrainingPlan",
    "TrainingResult",
    "apply_freeze",
    "board_correct",
    "board_only_losses",
    "best_weights",
    "bundle_document",
    "export_graphs",
    "learning_rate",
    "namespace",
    "node_errors",
    "parity_verdict",
    "photo_complete_correct",
    "quad_iou",
    "raw_parity",
    "scaled_delta",
    "screen_grid_losses",
    "step_rng",
    "train",
    "train_mode",
    "weighted_node_losses",
    "weights_bytes",
]
