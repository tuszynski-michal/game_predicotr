"""Bounded GPU smoke of the grid-training admission (TASK-1005).

Measures the full preset-D training step of the laboratory network on the ``training`` role
of a reference snapshot: no operator data, database, checkpoint, candidate or export. The
run takes the application GPU lease, passes the same admission as an application run with
``purpose=smoke`` and ends after 50 steps or 120 training seconds from the first step,
whichever comes first; start-up may take 300 s and the whole run at most 600 s.

    python -m game_predictor_worker.vision_lab.grid_training_smoke \
        --snapshot <reference snapshot> --artifact-root <artifact root> --report <report.json>
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..training_core.gpu_lease import GpuLease, GpuLeaseError, lease_path
from ..training_core.grid_training_admission import (
    PRESETS,
    SMOKE_MAX_SECONDS,
    SMOKE_STARTUP_SECONDS,
    SMOKE_TRAIN_SECONDS,
    GridRunBudgetError,
    RunBudget,
    evaluate_admission,
    probe_runtime,
)

LAB_PRESET = "D"
SEED = 1005
RENEW_SECONDS = 20.0
WATCHDOG_GRACE_SECONDS = 30.0


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


class SmokeWatchdog:
    """Ends a blocked smoke process past the start-up, training or whole-run limit.

    A data-loader batch or a CUDA call can block the training loop, so the limits are also
    checked from a thread. ``stop`` ends the thread before the run returns; once stopped it
    never writes the report or exits the process.
    """

    def __init__(
        self,
        started: float,
        report: dict[str, Any],
        report_path: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        exit_process: Callable[[int], None] = os._exit,
        poll_seconds: float = 1.0,
        grace_seconds: float = WATCHDOG_GRACE_SECONDS,
    ) -> None:
        self.started = started
        self.report = report
        self.report_path = report_path
        self.clock = clock
        self.exit_process = exit_process
        self.poll_seconds = poll_seconds
        self.grace_seconds = grace_seconds
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def expired(self, now: float) -> str | None:
        elapsed = now - self.started
        first_step = self.report.get("phases", {}).get("first_step_done")
        if first_step is None:
            if elapsed > SMOKE_STARTUP_SECONDS + self.grace_seconds:
                return "startup_timeout"
        elif elapsed > float(first_step) + SMOKE_TRAIN_SECONDS + self.grace_seconds:
            return "train_timeout"
        if elapsed > SMOKE_MAX_SECONDS + self.grace_seconds:
            return "watchdog_timeout"
        return None

    def check(self) -> bool:
        """Write the report and exit when a limit has passed; False while within limits."""
        now = self.clock()
        status = self.expired(now)
        if status is None:
            return False
        with self._lock:
            if self._stopped.is_set():
                return False
            self.report["status"] = status
            self.report["elapsedSeconds"] = now - self.started
            # The training thread may still mutate the report; the exit must not depend on it.
            with contextlib.suppress(Exception):
                _write(self.report_path, json.loads(json.dumps(self.report, default=str)))
            self.exit_process(124)
        return True

    def _run(self) -> None:
        while not self._stopped.wait(self.poll_seconds):
            if self.check():
                return

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stopped.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.poll_seconds + 5.0)


def run_smoke(snapshot: Path, artifact_root: Path, report_path: Path, preset_id: str) -> int:
    started = time.monotonic()
    preset = PRESETS[preset_id]
    runtime = probe_runtime()
    lease = GpuLease(lease_path(artifact_root))
    observation = lease.observe()
    decision = evaluate_admission(
        preset_id=preset.preset_id,
        preset_fingerprint=preset.fingerprint,
        purpose="smoke",
        runtime=runtime,
        lease_state=observation.state,
    )
    report: dict[str, Any] = {
        "format": "grid-training-smoke-v1",
        "presetId": preset.preset_id,
        "presetFingerprint": preset.fingerprint,
        "labPreset": LAB_PRESET,
        "snapshot": snapshot.name,
        "runtime": {
            "cudaAvailable": runtime.cuda_available,
            "torch": runtime.torch_version,
            "torchvision": runtime.torchvision_version,
            "cuda": runtime.cuda_version,
            "device": runtime.device_name,
            "totalVramBytes": runtime.total_vram_bytes,
            "freeVramBytes": runtime.free_vram_bytes,
            "probeError": runtime.probe_error,
        },
        "admission": {"admitted": decision.admitted, "reasons": list(decision.reasons)},
        "status": "blocked",
    }
    if not decision.admitted or decision.budget is None:
        _write(report_path, report)
        return 2
    try:
        record = lease.acquire("smoke", f"smoke-{SEED}")
    except GpuLeaseError as error:
        report["admission"] = {"admitted": False, "reasons": [error.code]}
        _write(report_path, report)
        return 2

    watchdog = SmokeWatchdog(started, report, report_path)
    watchdog.start()
    try:
        return _measure(snapshot, decision.budget, report, report_path, lease, record, started)
    finally:
        watchdog.stop()
        with contextlib.suppress(GpuLeaseError):
            lease.release(record)


def _measure(
    snapshot: Path,
    budget: RunBudget,
    report: dict[str, Any],
    report_path: Path,
    lease: GpuLease,
    record: Any,
    started: float,
) -> int:
    import torch
    from torch.amp.grad_scaler import GradScaler

    from .neural_grid_data import load_samples, open_snapshot, verify_images
    from .neural_grid_model import NeuralGridNetwork
    from .neural_grid_protocol import load_preset
    from .neural_grid_training import _batches, compute_losses, make_loader, seed_everything

    phases: dict[str, float] = {}
    report["phases"] = phases
    report["steps"] = 0

    def mark(name: str) -> None:
        phases[name] = round(time.monotonic() - started, 3)

    mark("imports")
    lab_preset, _ = load_preset(LAB_PRESET)
    info = open_snapshot(snapshot)
    samples = load_samples(snapshot, ("training",))
    mark("samples_loaded")
    verify_images(samples, info.files)
    mark("images_verified")
    generator = seed_everything(SEED)
    network = NeuralGridNetwork(lab_preset.board.stride).to("cuda")
    network.train()
    optimizer = torch.optim.AdamW(
        network.parameters(),
        lr=lab_preset.optimization.learning_rate,
        weight_decay=lab_preset.optimization.weight_decay,
    )
    scaler = GradScaler("cuda")
    torch.cuda.reset_peak_memory_stats()
    stream = _batches(make_loader(samples, lab_preset, SEED, generator))
    mark("model_and_loader_ready")
    data_seconds = time.monotonic() - started
    step_times: list[float] = []
    first_step_at: float | None = None
    last_renew = time.monotonic()
    stop = "steps"
    while True:
        now = time.monotonic()
        if now - started >= budget.max_seconds:
            stop = "run_seconds"
            break
        if first_step_at is not None and now - started - first_step_at >= SMOKE_TRAIN_SECONDS:
            stop = "train_seconds"
            break
        try:
            budget = budget.reserve_step()
        except GridRunBudgetError:
            stop = "steps"
            break
        step_started = time.monotonic()
        batch = next(stream)
        losses = compute_losses(network, batch, lab_preset, "cuda")
        optimizer.zero_grad(set_to_none=True)
        scaler.scale(losses["total"]).backward()  # type: ignore[no-untyped-call]
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(network.parameters(), lab_preset.optimization.gradient_clip)
        scaler.step(optimizer)
        scaler.update()
        torch.cuda.synchronize()
        now = time.monotonic()
        step_times.append(now - step_started)
        report["steps"] = len(step_times)
        if first_step_at is None:
            first_step_at = now - started
            mark("first_step_done")
        if now - last_renew >= RENEW_SECONDS:
            record = lease.renew(record)
            last_renew = now
    total = time.monotonic() - started
    budget = budget.charge(total)
    steady = step_times[1:]
    report.update(
        status="completed",
        stop=stop,
        steps=len(step_times),
        trainingPhotos=len(samples),
        batchImages=lab_preset.optimization.batch_images,
        boardsPerImage=lab_preset.board.boards_per_image,
        dataWorkers=lab_preset.optimization.data_workers,
        dataSeconds=data_seconds,
        firstStepSeconds=first_step_at,
        elapsedSeconds=total,
        steadyStepsPerSecond=(len(steady) / sum(steady)) if steady else None,
        peakAllocatedBytes=int(torch.cuda.max_memory_allocated()),
        peakReservedBytes=int(torch.cuda.max_memory_reserved()),
        budget=budget.to_payload(),
        checkpoint=None,
        candidate=None,
    )
    _write(report_path, report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preset", default="screen-grid-v1", choices=sorted(PRESETS))
    args = parser.parse_args(argv)
    return run_smoke(
        args.snapshot.resolve(), args.artifact_root.resolve(), args.report, args.preset
    )


if __name__ == "__main__":
    raise SystemExit(main())
