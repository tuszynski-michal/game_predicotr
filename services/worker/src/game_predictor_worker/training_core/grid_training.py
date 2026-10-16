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
from .grid_training_admission import GridTrainingPreset, digest
from .neural_grid_network import NeuralGridNetwork
from .runtime import TrainingInterrupted

CHECKPOINT_POLICY = "grid-training-checkpoint-v1"
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
) -> dict[str, torch.Tensor]:
    """Lab node losses with a per-crop weight; equal weights give the lab means exactly."""
    coordinate = torch.nn.functional.smooth_l1_loss(
        predicted.float(), nodes, beta=1.0, reduction="none"
    ).mean(dim=(1, 2))
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
    heatmap = -(gaussian.reshape(batch, channels, -1) * log_probability).sum(dim=-1).mean(dim=1)
    return {
        "nodes": _weighted_mean(coordinate, weights) * board.coordinate_loss_weight,
        "node_heatmap": _weighted_mean(heatmap, weights) * board.heatmap_loss_weight,
    }


def board_only_losses(
    network: NeuralGridNetwork, batch: Mapping[str, torch.Tensor], recipe: Any, device: str
) -> dict[str, torch.Tensor]:
    """Grid-only: the board stage alone; padded crops have weight 0; visibility is masked
    because cohort targets carry no unavailable-cell labels."""
    crops = batch["crops"].to(device, non_blocking=True).float()
    nodes = batch["nodes"].to(device, non_blocking=True)
    weights = batch["weights"].to(device, non_blocking=True).float()
    with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
        node_logits, predicted, _ = network.board(crops)
    losses = weighted_node_losses(node_logits, predicted, nodes, weights, recipe.board)
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
        node_logits, predicted, _ = network.board(crops)
    losses = {
        "heat": focal_loss(heat_logits, heat),
        "offsets": offset_loss(predicted_offsets, offsets, offset_weight)
        * recipe.screen.offset_loss_weight,
        **weighted_node_losses(node_logits, predicted, nodes, weights, recipe.board),
    }
    losses["total"] = sum(losses.values(), torch.zeros((), device=device))
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

    def update(self, metric: float, step: int) -> bool:
        """Record one evaluation; True when it is the new best."""
        if not math.isfinite(metric):
            raise ValueError("GRID_TRAINING_METRIC_NONFINITE")
        self.evaluations += 1
        sign = 1.0 if self.direction == "maximize" else -1.0
        improved = self.best is None or sign * (metric - self.best) > self.min_delta
        if improved:
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
        }

    def restore(self, value: Mapping[str, Any]) -> None:
        self.best, self.best_step = value["best"], value["bestStep"]
        self.stale, self.evaluations = int(value["stale"]), int(value["evaluations"])


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
                "policy": CHECKPOINT_POLICY,
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
Evaluator = Callable[[nn.Module], float]


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
    )
    history: list[dict[str, Any]] = []
    best_state: dict[str, Any] | None = None
    step = 0
    last: tuple[Path, str] | None = None
    if resume is not None:
        value = load_checkpoint(resume[0], resume[1], expected_binding=plan.binding)
        restore_checkpoint(value, network, optimizer, scaler, generator)
        step, history = int(value["globalStep"]), list(value["history"])
        stored = value["bestState"]
        if not isinstance(stored, dict) or "early" not in stored:
            raise ValueError("CHECKPOINT_INVALID")
        stopping.restore(stored["early"])
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
            best_state={**state, "early": stopping.state()},
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
        else:
            nonfinite = 0
            scaler.scaler.scale(values["total"]).backward()
            scaler.scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(trainable_parameters(network), preset.gradient_clip)
            scaler.scaler.step(optimizer)
            scaler.scaler.update()
        step += 1
        control.progress(step, plan.total_steps, {k: float(v.detach()) for k, v in values.items()})
        if step % plan.evaluation_steps and step < plan.total_steps:
            continue
        network.eval()
        with torch.no_grad():
            metric = float(evaluate(network))
        improved = stopping.update(metric, step)
        history.append({"step": step, "metric": metric, "improved": improved})
        if improved or best_state is None:
            best_state = {
                "model": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
                "step": step,
                "metric": metric,
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
    deltas: dict[str, float] = {}
    session = onnxruntime.InferenceSession(
        str(directory / "board.onnx"), providers=["CPUExecutionProvider"]
    )
    with torch.no_grad():
        expected = [t.numpy() for t in BoardExport(network.board)(torch.from_numpy(crops))]
    actual = session.run(None, {"crops": crops})
    for name, left, right in zip(("nodes", "peak", "visibility"), expected, actual, strict=True):
        deltas[f"board.{name}"] = float(np.max(np.abs(left - right))) if left.size else 0.0
    if pixels is not None:
        session = onnxruntime.InferenceSession(
            str(directory / "screen.onnx"), providers=["CPUExecutionProvider"]
        )
        with torch.no_grad():
            expected = [t.numpy() for t in ScreenExport(network.screen)(torch.from_numpy(pixels))]
        actual = session.run(None, {"pixels": pixels})
        for name, left, right in zip(("heat", "offsets"), expected, actual, strict=True):
            deltas[f"screen.{name}"] = float(np.max(np.abs(left - right))) if left.size else 0.0
    passed = all(math.isfinite(v) and v <= RAW_TOLERANCE for v in deltas.values())
    return {"tolerance": RAW_TOLERANCE, "maxDelta": deltas, "passed": passed}


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
) -> dict[str, Any]:
    return {
        "format": "neural-grid-bundle-v1",
        "model_version": model_version,
        "preset": dict(preset_payload),
        "preset_fingerprint": preset_fingerprint,
        "weights_sha256": weights_sha256,
        "opset": OPSET,
        "files": dict(files),
        "provenance": dict(provenance),
        "parity": dict(parity),
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
    "photo_complete_correct",
    "quad_iou",
    "raw_parity",
    "screen_grid_losses",
    "step_rng",
    "train",
    "train_mode",
    "weighted_node_losses",
    "weights_bytes",
]
