"""Controlled subprocess. It claims its own identity and never auto-retries."""

import argparse
import os
import threading
from contextlib import suppress
from pathlib import Path

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import read_checked
from .catalog import Catalog
from .runs import RunManager, Token
from .training_adapter import TRAINERS, RunControl, train_from_manifest
from .training_manifest import ManifestAdapter


def configured_manager(root: Path, settings: dict[str, str]) -> RunManager:
    for name in ("snapshot", "annotations", "manifests"):
        data_root = Path(settings[name]).resolve()
        if root.resolve().is_relative_to(data_root) or data_root.is_relative_to(root.resolve()):
            raise ValueError("RUN_DIRECTORY_OVERLAP")
    adapter = ManifestAdapter(
        Path(settings["manifests"]),
        Catalog(Path(settings["snapshot"])),
        Path(settings["annotations"]),
    )
    return RunManager(root, validate=adapter, models=tuple(TRAINERS), settings=settings)


def validate_runtime() -> None:
    from importlib.metadata import version

    import torch

    if (
        str(torch.__version__) != "2.12.1+cu130"
        or version("torchvision") != "0.27.1+cu130"
        or torch.version.cuda != "13.0"
    ):
        raise ValueError("RUN_CUDA_VERSION_MISMATCH")
    if not torch.cuda.is_available():
        raise ValueError("RUN_GPU_UNAVAILABLE")


def execute(manager: RunManager, run_id: str, lease: Token) -> None:
    stop = threading.Event()
    watchdog: threading.Thread | None = None
    try:
        run = manager.claim(run_id, lease)
        remaining = run.request.configuration.max_seconds - run.used_seconds

        def enforce_deadline() -> None:
            # Monotonic Event timeout covers imports, validation, GPU calls and publication.
            # Only this worker exits; recovery accounts the unconfirmed interval conservatively.
            if not stop.wait(remaining):
                os._exit(124)

        watchdog = threading.Thread(target=enforce_deadline, daemon=True)
        watchdog.start()
        validate_runtime()
        inputs = manager.validate(run.request)
        from .training_manifest import TrainingInputs

        if not isinstance(inputs, TrainingInputs):
            raise ValueError("RUN_TRAINING_INPUT_INVALID")
        metrics = train_from_manifest(inputs, run.request, RunControl(manager, run_id, lease))
        manager.finish(run_id, lease, status="succeeded", metrics=metrics)
    except TrainingInterrupted as error:
        manager.finish(run_id, lease, status="cancelled", error=str(error))
    except Exception as error:
        # Failure is durable and still propagated to the process exit code and operator log.
        with suppress(ValueError):
            manager.finish(run_id, lease, status="failed", error=str(error))
        raise
    finally:
        stop.set()
        if watchdog is not None:
            watchdog.join(timeout=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--fence", type=int, required=True)
    parser.add_argument("--lease", required=True)
    args = parser.parse_args()
    settings = read_checked(args.root / "settings.json")
    execute(
        configured_manager(args.root, settings), args.run, (args.attempt, args.fence, args.lease)
    )


if __name__ == "__main__":
    main()
