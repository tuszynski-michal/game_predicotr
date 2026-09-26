"""Test-only initialization probe around the unchanged production entry points."""

from __future__ import annotations

import importlib
import json
import os
import runpy
import sys
import time
from pathlib import Path


def main() -> None:
    role, marker, *arguments = sys.argv[1:]
    module = {
        "api": "game_predictor_api.main",
        "worker": "game_predictor_worker.cli",
    }[role]
    started = time.monotonic()
    imported = importlib.import_module(module)
    Path(marker).write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "module": module,
                "modulePath": imported.__file__,
                "pythonExecutable": sys.executable,
                "initializationSeconds": time.monotonic() - started,
            }
        ),
        encoding="utf-8",
    )
    sys.argv = [f"game_predictor_{role}", *arguments]
    runpy.run_module(f"game_predictor_{role}", run_name="__main__")


if __name__ == "__main__":
    main()
