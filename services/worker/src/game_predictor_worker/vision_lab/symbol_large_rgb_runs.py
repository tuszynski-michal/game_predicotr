"""One local D-506 RGB run with neutral fencing, cumulative budgets and checkpoints."""

import argparse
import logging
import os
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import read_checked
from .run_contracts import RunMutation, RunState
from .run_files import verify_artifact
from .runs import RunManager, Token
from .snapshot import reject_links
from .symbol_large_ai_experiment import LargeAiExperimentAdapter
from .symbol_large_rgb_protocol import (
    MODEL,
    PREPROCESSING,
    SEED,
    LargeRgbConfiguration,
    LargeRgbRequest,
    LargeRgbRunState,
    admit,
    validate_request,
)
from .symbol_runs import SOURCE_ROOT, SymbolRunManager
from .symbol_training_manifest import SymbolTrainingInputs

BOOT = (
    "import sys;sys.path.insert(0,sys.argv.pop(1));import runpy;"
    "runpy.run_module('game_predictor_worker.vision_lab.symbol_large_rgb_runs',run_name='__main__')"
)


class LargeRgbRunManager(SymbolRunManager):
    worker_boot = BOOT

    def heartbeat(self, run_id: str, lease: Token, *, reserve_step: bool = False) -> RunState:
        current = super().heartbeat(run_id, lease, reserve_step=reserve_step)
        if current.cancel_requested:
            raise TrainingInterrupted("RUN_CANCELLED")
        return current

    def finish(
        self,
        run_id: str,
        lease: Token,
        *,
        status: str,
        error: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RunState:
        if status == "succeeded":
            current = self.detail(run_id)
            value = metrics or {}
            onnx = value.get("onnx", {})
            best_epoch = value.get("best_epoch")
            if (
                set(current.artifacts) != {"onnx", "best_weights"}
                or type(best_epoch) is not int
                or not 1 <= best_epoch <= current.checkpoint_epoch
                or value.get("completed_epochs") != current.request.configuration.epochs
                or value.get("model_version") != MODEL
                or value.get("manifest_id") != current.request.manifest_id
                or onnx.get("status") != "passed"
                or onnx.get("samples") != value.get("validation", {}).get("samples")
                or not 0 <= onnx.get("max_absolute_error", float("inf")) <= 1e-4
                or onnx.get("artifact") != current.artifacts["onnx"].model_dump()
            ):
                raise ValueError("LARGE_RGB_SUCCESS_EXPORT_REQUIRED")
            for artifact in current.artifacts.values():
                verify_artifact(self.root, artifact)
        # The neutral finish rechecks the lease under its lock and publishes the
        # report atomically. The actual best epoch is in its immutable metrics.
        return super().finish(run_id, lease, status=status, error=error, metrics=metrics)


def build_manager(root: Path, settings: dict[str, str], launcher: Any = None) -> RunManager:
    for path in [root, *[Path(settings[name]) for name in ("manifest", "python", "pythonpath")]]:
        if not path.is_absolute():
            raise ValueError("LARGE_RGB_ABSOLUTE_PATH_REQUIRED")
        reject_links(path)
    adapter = LargeAiExperimentAdapter(Path(settings["manifest"]))
    metadata = read_checked(adapter.manifest)
    if root.resolve() != Path(metadata["run_root"]).resolve():
        raise ValueError("LARGE_RGB_FROZEN_RUN_ROOT_REQUIRED")
    # Metadata-only construction lets the worker claim before its launch grace
    # expires. Full input validation still occurs on create/claim/checkpoint/finish.
    for name in [str(adapter.manifest), metadata["bundle"], *metadata["live_bindings"]]:
        path = Path(name)
        reject_links(path)
        if path.is_file():
            path = path.parent
        if root.resolve().is_relative_to(path.resolve()) or path.resolve().is_relative_to(
            root.resolve()
        ):
            raise ValueError("RUN_DIRECTORY_OVERLAP")

    def validate(request: Any) -> Any:
        return adapter.validate(validate_request(request))

    return LargeRgbRunManager(
        root,
        validate=validate,
        settings=settings,
        models=(MODEL,),
        state_type=LargeRgbRunState,
        launcher=launcher,
        admit=admit,
    )


def execute(manager: RunManager, run_id: str, lease: Token) -> None:
    stop = threading.Event()
    try:
        run = manager.claim(run_id, lease)
        remaining = run.request.configuration.max_seconds - run.used_seconds

        def deadline() -> None:
            if not stop.wait(remaining):
                os._exit(124)

        threading.Thread(target=deadline, daemon=True).start()
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        from .neural_grid_runs import _keep_system_awake
        from .run_worker import validate_runtime
        from .symbol_training import train
        from .training_adapter import RunControl

        _keep_system_awake()
        validate_runtime()
        inputs = manager.validate(run.request)
        if not isinstance(inputs, SymbolTrainingInputs):
            raise ValueError("RUN_TRAINING_INPUT_INVALID")
        measured = train(inputs, run.request, RunControl(manager, run_id, lease))
        manager.finish(run_id, lease, status="succeeded", metrics=measured)
    except TrainingInterrupted as exc:
        manager.finish(run_id, lease, status="cancelled", error=str(exc))
    except Exception as exc:
        with suppress(ValueError):
            manager.finish(run_id, lease, status="failed", error=str(exc))
        raise
    finally:
        stop.set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start")
    for name in ("root", "manifest", "python"):
        start.add_argument("--" + name, type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("--root", type=Path, required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--root", type=Path, required=True)
    resume.add_argument("--run", required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--root", type=Path, required=True)
    worker.add_argument("--run", required=True)
    for name in ("attempt", "fence"):
        worker.add_argument("--" + name, type=int, required=True)
    worker.add_argument("--lease", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    settings = (
        {"manifest": str(args.manifest), "python": str(args.python), "pythonpath": str(SOURCE_ROOT)}
        if args.action == "start"
        else read_checked(args.root / "settings.json")
    )
    manager = build_manager(args.root, settings)
    if args.action == "worker":
        execute(manager, args.run, (args.attempt, args.fence, args.lease))
    elif args.action == "start":
        request = LargeRgbRequest(
            request_id="mumie-large-rgb-start",
            manifest_id=args.manifest.stem,
            model_version=MODEL,
            preprocessing_version=PREPROCESSING,
            seed=SEED,
            purpose="train",
            configuration=LargeRgbConfiguration(epochs=20, batch_size=32, learning_rate=0.001),
        )
        print(manager.create_or_get_run(request).model_dump_json())
    elif args.action == "resume":
        previous = manager.detail(args.run)
        print(
            manager.retry_run(
                args.run,
                RunMutation(
                    request_id=f"large-retry-{previous.attempt}-{args.run}",
                    expected_attempt=previous.attempt,
                ),
            ).model_dump_json()
        )
    else:
        print(manager.list().model_dump_json())


if __name__ == "__main__":
    main()
