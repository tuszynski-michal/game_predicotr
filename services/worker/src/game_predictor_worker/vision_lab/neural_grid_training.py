"""TASK-0802 training under the durable run protocol (RunManager lease, fence, budget).

A run is ``configuration.epochs`` rounds. A round is a slice of training wall time (the
preset's ``round_seconds``, shortened only when the remaining D-481 budget requires it),
followed by the full development evaluation and a schema-v2 checkpoint that carries the
best state so far. Smoke runs use 2 rounds of 20 reserved steps instead (<= 50 steps).
The 4-hour limit is enforced three times: the trainer plans its rounds from the durable
``used_seconds``, the RunManager refuses work past ``max_seconds`` and the worker
watchdog terminates the process at the deadline.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader

from game_predictor_worker.training_core.checkpoint import (
    checkpoint_bytes,
    load_checkpoint,
    make_checkpoint,
    restore_checkpoint,
)
from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import write_atomic
from .neural_grid_data import (
    PhotoSample,
    TrainingDataset,
    load_samples,
    open_snapshot,
    verify_images,
)
from .neural_grid_inference import DecodeSettings, NeuralGridEngine, engine_grids, evaluate_samples
from .neural_grid_metrics import selection_key
from .neural_grid_model import (
    BoardExport,
    NeuralGridNetwork,
    ScreenExport,
    focal_loss,
    node_heatmap_loss,
    offset_loss,
    parameter_count,
)
from .neural_grid_protocol import (
    MODEL_VERSION,
    SMOKE_EVAL_IMAGES,
    SMOKE_STEPS_PER_ROUND,
    NeuralGridRunRequest,
    Preset,
    validate_request,
)
from .run_files import verify_artifact
from .runs import RunManager, Token, checkpoint_binding

HEARTBEAT_SECONDS = 10.0
INITIAL_EVALUATION_ESTIMATE = 180.0
CHECKPOINT_ESTIMATE = 30.0


class Heartbeat:
    """Background lease renewal; the trainer polls the flags between steps."""

    def __init__(self, manager: RunManager, run_id: str, lease: Token) -> None:
        self.manager, self.run_id, self.lease = manager, run_id, lease
        self.used_seconds = 0.0
        self.cancel_requested = False
        self.budget_exhausted = False
        self.fenced: str | None = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def beat(self) -> None:
        with self.lock:
            try:
                run = self.manager.heartbeat(self.run_id, self.lease)
                self.used_seconds = run.used_seconds
                self.cancel_requested = run.cancel_requested
            except TrainingInterrupted:
                self.budget_exhausted = True
            except ValueError as error:
                # Lock contention with a checkpoint publication is transient (lease 60 s).
                if str(error) != "ANNOTATION_STORE_BUSY":
                    self.fenced = str(error)

    def reserve_step(self) -> None:
        with self.lock:
            run = self.manager.heartbeat(self.run_id, self.lease, reserve_step=True)
            self.used_seconds = run.used_seconds
            self.cancel_requested = run.cancel_requested

    def _loop(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_SECONDS):
            self.beat()

    def check(self) -> None:
        if self.fenced is not None:
            raise ValueError(self.fenced)
        if self.budget_exhausted:
            raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")

    def __enter__(self) -> Heartbeat:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=HEARTBEAT_SECONDS + 5)


class _ScalerSlot:
    """GradScaler state stored in the checkpoint's scheduler slot."""

    def __init__(self, scaler: GradScaler) -> None:
        self.scaler = scaler

    def state_dict(self) -> dict[str, Any]:
        return {"scaler": self.scaler.state_dict()}

    def load_state_dict(self, value: dict[str, Any]) -> None:
        self.scaler.load_state_dict(value["scaler"])


def seed_everything(seed: int) -> torch.Generator:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True
    return torch.Generator().manual_seed(seed)


def learning_rate(preset: Preset, progress: float) -> float:
    optimization = preset.optimization
    progress = min(max(progress, 0.0), 1.0)
    if optimization.warmup_fraction > 0 and progress < optimization.warmup_fraction:
        return optimization.learning_rate * max(progress / optimization.warmup_fraction, 0.01)
    span = max(1e-9, 1 - optimization.warmup_fraction)
    cosine = 0.5 * (1 + math.cos(math.pi * (progress - optimization.warmup_fraction) / span))
    floor = optimization.final_learning_rate_fraction
    return optimization.learning_rate * (floor + (1 - floor) * cosine)


class TorchRunners:
    """fp32 torch inference with the same outputs as the ONNX graphs."""

    def __init__(self, network: NeuralGridNetwork, device: str) -> None:
        self.device = device
        self.screen_graph = ScreenExport(network.screen).eval()
        self.board_graph = BoardExport(network.board).eval()

    def screen(self, pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        with torch.no_grad():
            heat, offsets = self.screen_graph(torch.from_numpy(pixels).to(self.device))
        return heat.float().cpu().numpy(), offsets.float().cpu().numpy()

    def board(self, crops: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        with torch.no_grad():
            nodes, peak, visibility = self.board_graph(torch.from_numpy(crops).to(self.device))
        return (
            nodes.float().cpu().numpy(),
            peak.float().cpu().numpy(),
            visibility.float().cpu().numpy(),
        )


def torch_engine(network: NeuralGridNetwork, preset: Preset, device: str) -> NeuralGridEngine:
    runners = TorchRunners(network, device)
    return NeuralGridEngine(runners.screen, runners.board, DecodeSettings.of(preset))


def evaluate_network(
    network: NeuralGridNetwork,
    preset: Preset,
    samples: list[PhotoSample],
    device: str,
    heartbeat: Any = None,
) -> tuple[dict[str, Any], list[Any]]:
    was_training = network.training
    network.eval()
    try:
        return evaluate_samples(
            engine_grids(torch_engine(network, preset, device)), samples, heartbeat=heartbeat
        )
    finally:
        network.train(was_training)


def compute_losses(
    network: NeuralGridNetwork, batch: dict[str, torch.Tensor], preset: Preset, device: str
) -> dict[str, torch.Tensor]:
    images = batch["image"].to(device, non_blocking=True).float()
    heat = batch["heat"].to(device, non_blocking=True)
    offsets = batch["offsets"].to(device, non_blocking=True)
    weight = batch["offset_weight"].to(device, non_blocking=True)
    crops = batch["crops"].to(device, non_blocking=True).flatten(0, 1).float()
    nodes = batch["nodes"].to(device, non_blocking=True).flatten(0, 1)
    visible = batch["visible"].to(device, non_blocking=True).flatten(0, 1)
    with torch.autocast("cuda", dtype=torch.float16, enabled=device.startswith("cuda")):
        heat_logits, predicted_offsets = network.screen(images)
        node_logits, predicted_nodes, visibility = network.board(crops)
    board = preset.board
    losses = {
        "heat": focal_loss(heat_logits, heat),
        "offsets": offset_loss(predicted_offsets, offsets, weight)
        * preset.screen.offset_loss_weight,
        "nodes": torch.nn.functional.smooth_l1_loss(predicted_nodes.float(), nodes, beta=1.0)
        * board.coordinate_loss_weight,
        "node_heatmap": node_heatmap_loss(node_logits, nodes, board.stride, board.heatmap_sigma)
        * board.heatmap_loss_weight,
        "visibility": torch.nn.functional.binary_cross_entropy_with_logits(
            visibility.float(), visible
        )
        * board.visibility_loss_weight,
    }
    losses["total"] = sum(losses.values(), torch.zeros((), device=device))
    return losses


def _batches(loader: DataLoader[Any]) -> Iterator[dict[str, torch.Tensor]]:
    while True:
        yield from loader


def make_loader(
    samples: list[PhotoSample], preset: Preset, seed: int, generator: torch.Generator
) -> DataLoader[Any]:
    workers = preset.optimization.data_workers
    return DataLoader(
        TrainingDataset(samples, preset, seed),  # type: ignore[arg-type]
        batch_size=preset.optimization.batch_images,
        shuffle=True,
        generator=generator,
        num_workers=workers,
        persistent_workers=workers > 0,
        pin_memory=True,
        drop_last=True,
        prefetch_factor=4 if workers > 0 else None,
    )


def train_run(manager: RunManager, run_id: str, lease: Token) -> dict[str, Any]:
    run = manager.detail(run_id)
    request = run.request
    if not isinstance(request, NeuralGridRunRequest):
        raise ValueError("NEURAL_GRID_REQUEST_INVALID")
    preset = validate_request(request)
    if not torch.cuda.is_available():
        raise ValueError("RUN_GPU_UNAVAILABLE")  # no CPU fallback (TASK-0802)
    device = "cuda"
    settings = manager.settings or {}
    snapshot = Path(settings["snapshot"])
    if open_snapshot(snapshot).snapshot_id != request.manifest_id:
        raise ValueError("NEURAL_GRID_SNAPSHOT_MISMATCH")
    attempt_dir = manager.root / run_id / f"attempt-{run.attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    smoke = request.purpose == "smoke"

    with Heartbeat(manager, run_id, lease) as heartbeat:
        started = time.monotonic()
        samples = load_samples(snapshot, ("training", "development"))
        training = [s for s in samples if s.role == "training"]
        development = [s for s in samples if s.role == "development"]
        verify_images(samples, open_snapshot(snapshot).files)
        heartbeat.check()
        evaluation = development[:SMOKE_EVAL_IMAGES] if smoke else development
        data_seconds = time.monotonic() - started

        generator = seed_everything(request.seed)
        network = NeuralGridNetwork(preset.board.stride).to(device)
        optimizer = torch.optim.AdamW(
            network.parameters(),
            lr=preset.optimization.learning_rate,
            weight_decay=preset.optimization.weight_decay,
        )
        scaler = GradScaler("cuda")
        slot = _ScalerSlot(scaler)
        history: list[dict[str, Any]] = []
        best: dict[str, Any] = {}
        step, start_round = 0, 0
        if run.checkpoint is not None:
            value = load_checkpoint(
                verify_artifact(manager.root, run.checkpoint),
                run.checkpoint.sha256,
                expected_binding=checkpoint_binding(request),
            )
            restore_checkpoint(value, network, optimizer, slot, generator)
            start_round, step = value["epoch"], value["globalStep"]
            history, best = value["history"], value["bestState"] or {}

        def serialize(round_index: int) -> bytes:
            return checkpoint_bytes(
                make_checkpoint(
                    network,
                    optimizer,
                    slot,
                    generator,
                    binding=checkpoint_binding(request),
                    epoch=round_index,
                    global_step=step,
                    history=history,
                    best_state=best,
                )
            )

        manager.checkpoint(run_id, lease, serialize(start_round), start_round)
        loader = make_loader(training, preset, request.seed, generator)
        stream = _batches(loader)
        rounds = request.configuration.epochs
        evaluation_estimate = INITIAL_EVALUATION_ESTIMATE
        losses_path = attempt_dir / "losses.jsonl"
        progress_path = attempt_dir / "progress.json"
        last_progress = 0.0
        nonfinite = 0
        cancelled = False
        torch.cuda.reset_peak_memory_stats()

        for round_index in range(start_round + 1, rounds + 1):
            heartbeat.beat()
            heartbeat.check()
            if heartbeat.cancel_requested:
                raise TrainingInterrupted("RUN_CANCELLED")
            if smoke:
                round_seconds = float("inf")
            else:
                remaining = request.configuration.max_seconds - heartbeat.used_seconds
                rounds_left = rounds - round_index + 1
                available = (remaining - preset.schedule.final_reserve_seconds) / rounds_left - (
                    evaluation_estimate + CHECKPOINT_ESTIMATE
                )
                round_seconds = min(preset.schedule.round_seconds, available)
                if round_seconds < preset.schedule.minimum_round_seconds:
                    raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            network.train()
            round_started = time.monotonic()
            round_steps = 0
            sums: dict[str, float] = {}
            window: dict[str, float] = {}
            window_steps, window_started = 0, time.monotonic()
            while True:
                elapsed = time.monotonic() - round_started
                if smoke:
                    if round_steps >= SMOKE_STEPS_PER_ROUND:
                        break
                    heartbeat.reserve_step()
                    progress = ((round_index - 1) + round_steps / SMOKE_STEPS_PER_ROUND) / rounds
                elif elapsed >= round_seconds:
                    break
                else:
                    progress = ((round_index - 1) + elapsed / round_seconds) / rounds
                heartbeat.check()
                if heartbeat.cancel_requested:
                    cancelled = True
                    break
                rate = learning_rate(preset, progress)
                for group in optimizer.param_groups:
                    group["lr"] = rate
                batch = next(stream)
                losses = compute_losses(network, batch, preset, device)
                optimizer.zero_grad(set_to_none=True)
                if not torch.isfinite(losses["total"]):
                    nonfinite += 1
                    if nonfinite > 20:
                        raise ValueError("NEURAL_GRID_LOSS_NONFINITE")
                    continue
                nonfinite = 0
                scaler.scale(losses["total"]).backward()  # type: ignore[no-untyped-call]
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(
                    network.parameters(), preset.optimization.gradient_clip
                )
                scaler.step(optimizer)
                scaler.update()
                step += 1
                round_steps += 1
                window_steps += 1
                for name, tensor in losses.items():
                    number = float(tensor.detach())
                    sums[name] = sums.get(name, 0.0) + number
                    window[name] = window.get(name, 0.0) + number
                if smoke or window_steps >= 50:
                    now = time.monotonic()
                    line = {
                        "step": step,
                        "round": round_index,
                        "lr": rate,
                        "progress": progress,
                        "steps_per_second": window_steps / max(now - window_started, 1e-6),
                        **{k: v / window_steps for k, v in window.items()},
                    }
                    with losses_path.open("a", encoding="utf-8") as stream_out:
                        stream_out.write(json.dumps(line) + "\n")
                    window, window_steps, window_started = {}, 0, now
                if time.monotonic() - last_progress >= 30:
                    last_progress = time.monotonic()
                    write_atomic(
                        progress_path,
                        {
                            "run_id": run_id,
                            "round": round_index,
                            "rounds": rounds,
                            "round_seconds": round_seconds if not smoke else None,
                            "round_elapsed": time.monotonic() - round_started,
                            "step": step,
                            "used_seconds": heartbeat.used_seconds,
                            "max_vram_bytes": torch.cuda.max_memory_allocated(),
                            "best_round": best.get("round"),
                            "best_summary": _compact(best.get("summary")),
                            "updated_at": time.time(),
                        },
                    )
            train_seconds = time.monotonic() - round_started
            evaluation_started = time.monotonic()
            summary, _ = evaluate_network(network, preset, evaluation, device)
            evaluation_estimate = max(time.monotonic() - evaluation_started, 30.0)
            entry = {
                "round": round_index,
                "steps": round_steps,
                "global_step": step,
                "train_seconds": train_seconds,
                "evaluation_seconds": evaluation_estimate,
                "used_seconds": heartbeat.used_seconds,
                "train_loss": {k: v / max(round_steps, 1) for k, v in sums.items()},
                "development": summary,
                "shortened_by_cancel": cancelled,
            }
            history.append(entry)
            if not best or selection_key(summary, round_index) > selection_key(
                best["summary"], best["round"]
            ):
                best = {
                    "round": round_index,
                    "summary": summary,
                    "model": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
                }
            heartbeat.check()
            manager.checkpoint(run_id, lease, serialize(round_index), round_index)
            write_atomic(
                progress_path,
                {
                    "run_id": run_id,
                    "round": round_index,
                    "rounds": rounds,
                    "step": step,
                    "used_seconds": heartbeat.used_seconds,
                    "max_vram_bytes": torch.cuda.max_memory_allocated(),
                    "last_round": _compact(summary),
                    "best_round": best["round"],
                    "best_summary": _compact(best["summary"]),
                    "updated_at": time.time(),
                },
            )
            if cancelled:
                raise TrainingInterrupted("RUN_CANCELLED")

        if not best:
            raise ValueError("NEURAL_GRID_BEST_STATE_MISSING")
        return {
            "model_version": MODEL_VERSION,
            "purpose": request.purpose,
            "preset": request.preset,
            "preset_fingerprint": request.preset_fingerprint,
            "snapshot_id": request.manifest_id,
            "pretrained": preset.pretrained,
            "rounds_completed": rounds,
            "global_steps": step,
            "best_round": best["round"],
            "best_development": best["summary"],
            "history": history,
            "data": {
                "training_photos": len(training),
                "training_boards": sum(len(s.boards) for s in training),
                "development_photos": len(development),
                "development_boards": sum(len(s.boards) for s in development),
                "evaluation_photos": len(evaluation),
                "data_preparation_seconds": data_seconds,
            },
            "parameters": {
                "screen": parameter_count(network.screen),
                "board": parameter_count(network.board),
            },
            "max_vram_bytes": torch.cuda.max_memory_allocated(),
            "selection": "max photo_complete_correct_rate; tie lower image_macro; tie earlier",
        }


def _compact(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    keys = (
        "photos",
        "photo_complete_correct_rate",
        "image_macro",
        "board_recovery_rate",
        "detection_recall",
        "nme_median",
        "nme_p95",
        "false_boards",
        "evaluation_seconds",
    )
    return {key: summary.get(key) for key in keys}


def load_state(
    manager: RunManager, run_id: str, which: str = "best"
) -> tuple[NeuralGridNetwork, Preset, dict[str, Any], str]:
    """Network weights of the run's latest checkpoint (``last``) or its best state."""

    run = manager.detail(run_id)
    if run.checkpoint is None or not isinstance(run.request, NeuralGridRunRequest):
        raise ValueError("NEURAL_GRID_CHECKPOINT_MISSING")
    preset = validate_request(run.request)
    value = load_checkpoint(
        verify_artifact(manager.root, run.checkpoint),
        run.checkpoint.sha256,
        expected_binding=checkpoint_binding(run.request),
    )
    network = NeuralGridNetwork(preset.board.stride)
    if which == "best":
        best = value.get("bestState") or {}
        if "model" not in best:
            raise ValueError("NEURAL_GRID_BEST_STATE_MISSING")
        network.load_state_dict(best["model"])
        info = {"state": "best", "round": best["round"], "summary": best["summary"]}
    elif which == "last":
        network.load_state_dict(value["modelState"])
        info = {"state": "last", "round": value["epoch"]}
    else:
        raise ValueError("NEURAL_GRID_STATE_UNKNOWN")
    info["checkpoint_sha256"] = run.checkpoint.sha256
    info["checkpoint_round"] = value["epoch"]
    info["history"] = value["history"]
    return network, preset, info, run.checkpoint.sha256
