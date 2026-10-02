"""neural_grid run entry points on the durable lab run protocol (TASK-0802).

``python -m game_predictor_worker.vision_lab.neural_grid_runs <command>``

start      create (or replay) a smoke/train run and launch its detached worker
status     run state, budget, progress and last evaluation
resume     new attempt of a failed/cancelled run from its last checkpoint (same budget)
stop       cooperative cancel (round ends early, is evaluated and checkpointed);
           ``--kill`` additionally terminates the identity-checked worker process
evaluate   development evaluation of the best (or last) state, GPU
export     ONNX bundle of the best state with PyTorch-ONNX parity, CPU
timing     ONNX Runtime CPU time per photo
reference  label-reference metrics (production engine output for level B) and,
           optionally, the lab baseline engine through the same evaluator
worker     internal: the detached training process

Only this module and its run root decide budgets: at most three training runs (one per
preset) and four hours each (D-481), enforced in code through ``admit_run``, the request
contract and the worker watchdog. Torch is imported only by commands that need it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import read_checked
from .neural_grid_protocol import (
    MODEL_VERSION,
    NeuralGridRunRequest,
    NeuralGridRunState,
    admit_run,
    build_request,
    validate_request,
)
from .process_identity import process_created
from .run_contracts import RunMutation, RunState, StartRunRequest
from .runs import ACTIVE, RunManager, Token

DEFAULT_DATA = Path(
    os.environ.get(
        "VISION_LAB_DATA_ROOT", str(Path.home() / "Documents" / "game_predictor_vision_data")
    )
)
DEFAULT_SNAPSHOT_ID = "286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59"
DEFAULT_ROOT = DEFAULT_DATA / "neural-grid-runs"
DEFAULT_SNAPSHOT = DEFAULT_DATA / "production-geometry-snapshots" / DEFAULT_SNAPSHOT_ID
SOURCE_ROOT = Path(__file__).resolve().parents[2]
_BOOT = (
    "import sys;sys.path.insert(0,sys.argv.pop(1));import runpy;"
    "runpy.run_module('game_predictor_worker.vision_lab.neural_grid_runs',run_name='__main__')"
)
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def validator(settings: dict[str, str]) -> Any:
    def validate(request: StartRunRequest) -> Any:
        from .neural_grid_data import open_snapshot

        preset = validate_request(request)
        snapshot = Path(settings["snapshot"])
        if open_snapshot(snapshot).snapshot_id != request.manifest_id:
            raise ValueError("NEURAL_GRID_SNAPSHOT_MISMATCH")
        return preset

    return validate


class NeuralGridRunManager(RunManager):
    def _spawn(self, run: RunState) -> None:
        if self.settings is None:
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        executable = Path(self.settings["python"])
        if not executable.is_file():
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        attempt = self.root / run.id / f"attempt-{run.attempt}"
        attempt.mkdir(parents=True, exist_ok=True)
        command = [
            str(executable),
            "-X",
            "utf8",
            "-c",
            _BOOT,
            self.settings["pythonpath"],
            "worker",
            "--root",
            str(self.root.resolve()),
            "--run",
            run.id,
            "--attempt",
            str(run.attempt),
            "--fence",
            str(run.fence),
            "--lease",
            run.lease,
        ]
        environment = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONPATH": self.settings["pythonpath"],
        }
        with (attempt / "worker.log").open("ab") as log:
            flags = 0
            if os.name == "nt":
                flags = _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP | _CREATE_BREAKAWAY_FROM_JOB
            kwargs: dict[str, Any] = {
                "stdin": subprocess.DEVNULL,
                "stdout": log,
                "stderr": log,
                "env": environment,
                "cwd": str(self.root.resolve()),
            }
            if os.name == "nt":
                try:
                    subprocess.Popen(command, creationflags=flags, **kwargs)
                except OSError:
                    # The parent job may forbid breakaway; the worker still has its own
                    # hidden console and process group and survives this session.
                    subprocess.Popen(
                        command, creationflags=flags & ~_CREATE_BREAKAWAY_FROM_JOB, **kwargs
                    )
            else:
                subprocess.Popen(command, start_new_session=True, **kwargs)


def build_manager(root: Path, settings: dict[str, str], launcher: Any = None) -> RunManager:
    snapshot = Path(settings["snapshot"]).resolve()
    if root.resolve().is_relative_to(snapshot) or snapshot.is_relative_to(root.resolve()):
        raise ValueError("RUN_DIRECTORY_OVERLAP")
    return NeuralGridRunManager(
        root,
        validate=validator(settings),
        models=(MODEL_VERSION,),
        settings=settings,
        launcher=launcher,
        state_type=NeuralGridRunState,
        admit=admit_run,
    )


def runtime_settings(args: argparse.Namespace) -> dict[str, str]:
    stored = args.root / "settings.json"
    if stored.exists() and not getattr(args, "python", None):
        return dict(read_checked(stored))
    return {
        "python": str(Path(getattr(args, "python", None) or sys.executable).resolve()),
        "pythonpath": str(SOURCE_ROOT),
        "snapshot": str(Path(args.snapshot).resolve()),
    }


def _keep_system_awake() -> None:
    """Ask Windows not to idle-sleep while this worker lives (process-scoped, not a setting).

    The budget is wall time from claim, so an idle sleep would silently consume it. The
    request ends with the process; lid close or a manual sleep still suspends the run.
    """

    if os.name != "nt":
        return
    import ctypes

    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required)


def execute(manager: RunManager, run_id: str, lease: Token) -> None:
    """Claim, hard deadline watchdog, runtime check, training, durable finish."""

    stop = threading.Event()
    watchdog: threading.Thread | None = None
    try:
        run = manager.claim(run_id, lease)
        remaining = run.request.configuration.max_seconds - run.used_seconds

        def enforce_deadline() -> None:
            # Hard limit: the process exits at the remaining budget whatever it is doing;
            # reconciliation charges the unconfirmed interval conservatively.
            if not stop.wait(remaining):
                os._exit(124)

        watchdog = threading.Thread(target=enforce_deadline, daemon=True)
        watchdog.start()
        _keep_system_awake()
        from .run_worker import validate_runtime

        validate_runtime()
        from .neural_grid_training import train_run

        metrics = train_run(manager, run_id, lease)
        manager.finish(run_id, lease, status="succeeded", metrics=metrics)
    except TrainingInterrupted as error:
        manager.finish(run_id, lease, status="cancelled", error=str(error))
    except Exception as error:
        with suppress(ValueError):
            manager.finish(run_id, lease, status="failed", error=str(error))
        raise
    finally:
        stop.set()
        if watchdog is not None:
            watchdog.join(timeout=1)


def _progress(root: Path, run: RunState) -> dict[str, Any] | None:
    path = root / run.id / f"attempt-{run.attempt}" / "progress.json"
    try:
        return dict(read_checked(path))
    except (OSError, ValueError, KeyError):
        return None


def _last_loss(root: Path, run: RunState) -> dict[str, Any] | None:
    path = root / run.id / f"attempt-{run.attempt}" / "losses.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1]) if lines else None


def describe(root: Path, run: RunState) -> dict[str, Any]:
    request = run.request
    alive = None
    if run.pid is not None and run.process_created is not None:
        with suppress(ValueError):
            alive = process_created(run.pid) == run.process_created
    now = time.time()
    return {
        "id": run.id,
        "request_id": request.request_id,
        "preset": getattr(request, "preset", None),
        "purpose": request.purpose,
        "status": run.status,
        "error": run.error,
        "attempt": run.attempt,
        "pid": run.pid,
        "process_alive": alive,
        "cancel_requested": run.cancel_requested,
        "rounds_completed": run.checkpoint_epoch,
        "rounds": request.configuration.epochs,
        "used_seconds": round(run.used_seconds, 1),
        "max_seconds": request.configuration.max_seconds,
        "remaining_seconds": round(request.configuration.max_seconds - run.used_seconds, 1),
        "heartbeat_age_seconds": None
        if run.heartbeat_at is None
        else round(now - run.heartbeat_at, 1),
        "reserved_steps": run.reserved_steps,
        "checkpoint": None if run.checkpoint is None else run.checkpoint.relative_path,
        "report": None if run.report is None else run.report.relative_path,
        "diagnostics": run.diagnostics,
        "progress": _progress(root, run),
        "last_loss": _last_loss(root, run),
    }


def _budget(manager: RunManager) -> dict[str, Any]:
    page = manager.list(0, 100)
    trained = [r for r in page.runs if r.request.purpose == "train"]
    return {
        "train_runs_started": len(trained),
        "train_runs_allowed": 3,
        "presets_used": sorted(getattr(r.request, "preset", "?") for r in trained),
    }


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _development(
    args: argparse.Namespace, settings: dict[str, str], limit: int | None
) -> list[Any]:
    from .neural_grid_data import load_samples

    samples = load_samples(Path(settings["snapshot"]), ("development",))
    return samples[:limit] if limit else samples


def _refuse_if_active(manager: RunManager) -> None:
    if any(run.status in ACTIVE for run in manager.list(0, 100).runs):
        raise SystemExit("RUN_BUSY: a run is active; evaluate/export after it ends (one GPU job)")


def command_start(args: argparse.Namespace) -> None:
    settings = runtime_settings(args)
    manager = build_manager(args.root, settings)
    from .neural_grid_data import open_snapshot

    snapshot_id = open_snapshot(Path(settings["snapshot"])).snapshot_id
    request = build_request(
        request_id=args.request_id,
        preset_name=args.preset,
        purpose=args.purpose,
        snapshot_id=snapshot_id,
    )
    run = manager.create_or_get_run(request)
    _print({"run": describe(args.root, run), "budget": _budget(manager)})


def command_status(args: argparse.Namespace) -> None:
    settings = runtime_settings(args)
    manager = build_manager(args.root, settings)
    if args.run:
        _print(describe(args.root, manager.detail(args.run)))
        return
    page = manager.list(0, 100)
    _print({"runs": [describe(args.root, run) for run in page.runs], "budget": _budget(manager)})


def command_resume(args: argparse.Namespace) -> None:
    manager = build_manager(args.root, runtime_settings(args))
    current = manager.detail(args.run)
    request_id = args.request_id or f"resume-{args.run[:8]}-{current.attempt}"
    run = manager.retry_run(
        args.run, RunMutation(request_id=request_id, expected_attempt=current.attempt)
    )
    _print(describe(args.root, run))


def command_stop(args: argparse.Namespace) -> None:
    manager = build_manager(args.root, runtime_settings(args))
    current = manager.detail(args.run)
    request_id = args.request_id or f"stop-{args.run[:8]}-{current.attempt}"
    run = manager.cancel_run(
        args.run, RunMutation(request_id=request_id, expected_attempt=current.attempt)
    )
    if (
        args.kill
        and run.pid is not None
        and run.process_created is not None
        and process_created(run.pid) == run.process_created
    ):
        # Identity-checked: never a reused PID. The run fails on lease expiry (60 s) and
        # stays resumable from its last checkpoint.
        subprocess.run(
            ["taskkill", "/PID", str(run.pid), "/T", "/F"]
            if os.name == "nt"
            else ["kill", "-9", str(run.pid)],
            check=False,
            capture_output=True,
            timeout=30,
        )
    _print(describe(args.root, manager.detail(args.run)))


def command_evaluate(args: argparse.Namespace) -> None:
    import torch

    from .neural_grid_training import evaluate_network, load_state

    settings = runtime_settings(args)
    manager = build_manager(args.root, settings)
    _refuse_if_active(manager)
    if not torch.cuda.is_available():
        raise SystemExit("RUN_GPU_UNAVAILABLE: evaluation runs on the GPU")
    network, preset, info, checkpoint = load_state(manager, args.run, args.state)
    samples = _development(args, settings, args.limit)
    summary, photos = evaluate_network(network.cuda(), preset, samples, "cuda")
    output = (
        args.root / args.run / "evaluations" / f"{checkpoint[:16]}-{args.state}-development.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": args.run,
        "role": "development",
        "state": {k: v for k, v in info.items() if k != "history"},
        "summary": summary,
        "photos": [photo.as_dict() for photo in photos],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), "utf-8")
    _print({"output": str(output), "summary": summary})


def command_export(args: argparse.Namespace) -> None:
    from .neural_grid_onnx import export_bundle
    from .neural_grid_training import load_state

    settings = runtime_settings(args)
    manager = build_manager(args.root, settings)
    _refuse_if_active(manager)
    network, preset, info, checkpoint = load_state(manager, args.run, "best")
    run = manager.detail(args.run)
    assert isinstance(run.request, NeuralGridRunRequest)
    destination = args.root / args.run / "exports" / f"{checkpoint[:16]}-round{info['round']}"
    bundle = export_bundle(
        network,
        preset,
        run.request.preset_fingerprint,
        {
            "run_id": args.run,
            "checkpoint_sha256": checkpoint,
            "best_round": info["round"],
            "snapshot_id": run.request.manifest_id,
        },
        destination,
        _development(args, settings, args.parity_images),
    )
    _print({"bundle": str(destination), "parity": bundle["parity"], "files": bundle["files"]})


def command_timing(args: argparse.Namespace) -> None:
    from .neural_grid_onnx import cpu_timing

    settings = runtime_settings(args)
    result = cpu_timing(args.bundle, _development(args, settings, args.images + 1), args.threads)
    output = args.bundle / f"cpu-timing-{args.images}.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), "utf-8")
    _print(result)


def command_reference(args: argparse.Namespace) -> None:
    from .neural_grid_inference import evaluate_samples, geometry_engine_grids

    settings = runtime_settings(args)
    samples = _development(args, settings, None)
    labels = {sample.image_id: [b.nodes for b in sample.boards] for sample in samples}
    result: dict[str, Any] = {}
    # Production engine on level B = the labels by definition (auto geometry accepted).
    b_samples = [s for s in samples if s.level == "B"]
    from .neural_grid_metrics import evaluate_photo, summarize

    result["production_reference_level_B"] = summarize(
        [
            evaluate_photo(
                s.image_id, s.level, labels[s.image_id], [(n, True) for n in labels[s.image_id]]
            )
            for s in b_samples
        ]
    )
    result["production_reference_level_S"] = (
        "not measurable from the snapshot: level S labels are human/reverification "
        "corrections and the snapshot does not keep the production engine output they replaced"
    )
    if args.screen_layout_limit:
        from .geometry import BaselineEngine

        subset = samples[: args.screen_layout_limit]
        summary, _ = evaluate_samples(geometry_engine_grids(BaselineEngine()), subset)
        result["lab_baseline_screen_layout_v3"] = summary
    output = args.root / "reference" / f"development-reference-{args.screen_layout_limit}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), "utf-8")
    _print({"output": str(output), **result})


def command_worker(args: argparse.Namespace) -> None:
    settings = dict(read_checked(args.root / "settings.json"))
    execute(build_manager(args.root, settings), args.run, (args.attempt, args.fence, args.lease))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="neural_grid_runs")
    commands = root.add_subparsers(dest="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        item = commands.add_parser(name)
        item.add_argument("--root", type=Path, default=DEFAULT_ROOT)
        item.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
        return item

    start = add("start")
    start.add_argument("--preset", choices=("A", "B", "C"), required=True)
    start.add_argument("--purpose", choices=("smoke", "train"), required=True)
    start.add_argument("--request-id", required=True)
    start.add_argument("--python", help="GPU interpreter for the worker (default: this one)")
    status = add("status")
    status.add_argument("--run")
    for name in ("resume", "stop"):
        item = add(name)
        item.add_argument("--run", required=True)
        item.add_argument("--request-id")
        if name == "stop":
            item.add_argument("--kill", action="store_true")
    evaluate = add("evaluate")
    evaluate.add_argument("--run", required=True)
    evaluate.add_argument("--state", choices=("best", "last"), default="best")
    evaluate.add_argument("--limit", type=int)
    export = add("export")
    export.add_argument("--run", required=True)
    export.add_argument("--parity-images", type=int, default=16)
    timing = add("timing")
    timing.add_argument("--bundle", type=Path, required=True)
    timing.add_argument("--images", type=int, default=30)
    timing.add_argument("--threads", type=int)
    reference = add("reference")
    reference.add_argument("--screen-layout-limit", type=int, default=0)
    worker = add("worker")
    worker.add_argument("--run", required=True)
    worker.add_argument("--attempt", type=int, required=True)
    worker.add_argument("--fence", type=int, required=True)
    worker.add_argument("--lease", required=True)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    handlers = {
        "start": command_start,
        "status": command_status,
        "resume": command_resume,
        "stop": command_stop,
        "evaluate": command_evaluate,
        "export": command_export,
        "timing": command_timing,
        "reference": command_reference,
        "worker": command_worker,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
