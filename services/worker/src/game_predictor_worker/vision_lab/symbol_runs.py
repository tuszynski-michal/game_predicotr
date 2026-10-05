"""Local symbol-family CLI on the existing durable, fenced run protocol."""

import argparse
import json
import os
import subprocess
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import read_checked
from .run_contracts import RunMutation, RunState, StartRunRequest, TrainingConfiguration
from .run_files import verify_artifact
from .runs import RunManager, Token
from .snapshot import canonical
from .symbol_models import MODELS, PREPROCESSING, ROBUST_MODELS, compare, model_pair
from .symbol_store import publish_file
from .symbol_training_manifest import SymbolTrainingAdapter, SymbolTrainingInputs

SOURCE_ROOT = Path(__file__).resolve().parents[2]
BOOT = (
    "import sys;sys.path.insert(0,sys.argv.pop(1));import runpy;"
    "runpy.run_module('game_predictor_worker.vision_lab.symbol_runs',run_name='__main__')"
)


def validate_request(request: StartRunRequest) -> None:
    if (
        request.model_version not in (*MODELS, *ROBUST_MODELS)
        or request.protocol_digest is not None
        or request.preprocessing_version != PREPROCESSING.get(request.model_version)
        or request.topology.columns != 5
        or request.topology.rows != 3
        or request.seed != 20261005
        or request.configuration.epochs > 20
        or request.configuration.max_steps > 10000
        or request.configuration.max_seconds > 1800
    ):
        raise ValueError("SYMBOL_RUN_PROTOCOL_INVALID")
    if request.purpose == "train" and (
        request.configuration.epochs != 20
        or request.configuration.batch_size != 32
        or request.configuration.learning_rate != 0.001
    ):
        raise ValueError("SYMBOL_TRAIN_CONFIGURATION_INVALID")


def admit(data: dict[str, Any], request: StartRunRequest) -> None:
    if request.purpose == "train" and any(
        r["request"]["purpose"] == "train"
        and r["request"]["manifest_id"] == request.manifest_id
        and r["request"]["model_version"] == request.model_version
        for r in data["runs"].values()
    ):
        raise ValueError("SYMBOL_VARIANT_TRAIN_ALREADY_ADMITTED")


class SymbolRunManager(RunManager):
    def _spawn(self, run: RunState) -> None:
        if self.settings is None:
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        executable = Path(self.settings["python"])
        if not executable.is_file():
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        directory = self.root / run.id / f"attempt-{run.attempt}"
        directory.mkdir(parents=True, exist_ok=True)
        command = [
            str(executable),
            "-X",
            "utf8",
            "-c",
            BOOT,
            self.settings["pythonpath"],
            "worker",
            "--root",
            str(self.root),
            "--run",
            run.id,
            "--attempt",
            str(run.attempt),
            "--fence",
            str(run.fence),
            "--lease",
            run.lease,
        ]
        with (directory / "worker.log").open("ab") as log:
            kwargs: dict[str, Any] = {
                "stdin": subprocess.DEVNULL,
                "stdout": log,
                "stderr": log,
                "cwd": str(self.root),
                "env": {
                    **os.environ,
                    "PYTHONUTF8": "1",
                    "PYTHONPATH": self.settings["pythonpath"],
                    "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
                },
            }
            if os.name == "nt":
                flags = 0x08000000 | 0x00000200 | 0x01000000
                try:
                    subprocess.Popen(command, creationflags=flags, **kwargs)
                except OSError:
                    subprocess.Popen(command, creationflags=flags & ~0x01000000, **kwargs)
            else:
                subprocess.Popen(command, start_new_session=True, **kwargs)


def build_manager(root: Path, settings: dict[str, str], launcher: Any = None) -> RunManager:
    if not root.is_absolute() or not all(
        Path(settings[n]).is_absolute() for n in ("manifest", "python", "pythonpath")
    ):
        raise ValueError("SYMBOL_RUN_ABSOLUTE_PATH_REQUIRED")
    adapter = SymbolTrainingAdapter(Path(settings["manifest"]))
    # Check output isolation from every pinned live input, including labels and source files.
    inputs = adapter.validate()
    for name in [str(adapter.manifest), str(inputs.bundle), *inputs.payload["live_bindings"]]:
        path = Path(name).resolve()
        if path.is_file():
            path = path.parent
        if root.resolve().is_relative_to(path) or path.is_relative_to(root.resolve()):
            raise ValueError("RUN_DIRECTORY_OVERLAP")

    def validate(request: StartRunRequest) -> Any:
        validate_request(request)
        return adapter.validate(request)

    return SymbolRunManager(
        root,
        validate=validate,
        settings=settings,
        models=model_pair(int(settings.get("generation", "1"))),
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

        _keep_system_awake()
        validate_runtime()
        from .symbol_training import train
        from .training_adapter import RunControl

        inputs = manager.validate(run.request)
        if not isinstance(inputs, SymbolTrainingInputs):
            raise ValueError("RUN_TRAINING_INPUT_INVALID")
        measured = train(inputs, run.request, RunControl(manager, run_id, lease))
        manager.finish(run_id, lease, status="succeeded", metrics=measured)
    except TrainingInterrupted as error:
        manager.finish(run_id, lease, status="cancelled", error=str(error))
    except Exception as error:
        with suppress(ValueError):
            manager.finish(run_id, lease, status="failed", error=str(error))
        raise
    finally:
        stop.set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start")
    for name in ("root", "manifest", "python"):
        start.add_argument("--" + name, type=Path, required=True)
    start.add_argument("--variant", choices=("rgb", "gray"), required=True)
    start.add_argument("--generation", type=int, choices=(1, 2), default=1)
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
    fusion = sub.add_parser("compare")
    fusion.add_argument("--root", type=Path, required=True)
    fusion.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "start":
        settings = {
            "manifest": str(args.manifest),
            "python": str(args.python),
            "pythonpath": str(SOURCE_ROOT),
        }
    else:
        settings = read_checked(args.root / "settings.json")
    if args.action == "start" and args.generation == 2:
        settings["generation"] = "2"
    pair = model_pair(int(settings.get("generation", "1")))
    manager = build_manager(args.root, settings)
    if args.action == "worker":
        execute(manager, args.run, (args.attempt, args.fence, args.lease))
        return
    if args.action == "start":
        model = pair[0 if args.variant == "rgb" else 1]
        request = StartRunRequest(
            request_id=("mumie-first-" if args.generation == 1 else "mumie-robust-") + args.variant,
            manifest_id=args.manifest.stem,
            model_version=model,
            preprocessing_version=PREPROCESSING[model],
            seed=20261005,
            purpose="train",
            configuration=TrainingConfiguration(
                epochs=20,
                batch_size=32,
                learning_rate=0.001,
                max_steps=10000,
                max_seconds=1800,
            ),
        )
        print(manager.create_or_get_run(request).model_dump_json())
    elif args.action == "resume":
        run = manager.detail(args.run)
        print(
            manager.retry_run(
                args.run,
                RunMutation(
                    request_id=f"retry-{run.attempt}-{args.run}", expected_attempt=run.attempt
                ),
            ).model_dump_json()
        )
    elif args.action == "compare":
        if not args.output.is_absolute():
            raise ValueError("SYMBOL_RUN_ABSOLUTE_PATH_REQUIRED")
        runs = {
            r.request.model_version: r
            for r in manager.list().runs
            if r.status == "succeeded" and r.request.purpose == "train"
        }
        if set(runs) != set(pair):
            raise ValueError("SYMBOL_TWO_COMPLETED_MODELS_REQUIRED")
        if any(r.report is None for r in runs.values()):
            raise ValueError("SYMBOL_MODEL_REPORT_MISSING")

        def prediction(model: str) -> dict[str, Any]:
            report = runs[model].report
            assert report is not None
            return dict(
                json.loads(verify_artifact(args.root, report).read_bytes())["metrics"][
                    "predictions"
                ]
            )

        predictions = [prediction(m) for m in pair]
        result = compare(*predictions)
        publish_file(args.output, canonical(result))
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
    else:
        print(manager.list().model_dump_json())


if __name__ == "__main__":
    main()
