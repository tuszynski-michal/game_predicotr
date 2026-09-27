import argparse
import os
from pathlib import Path

import uvicorn

from .api import create_app
from .catalog import Catalog

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--manifests", type=Path)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--training-python", type=Path)
    arguments = parser.parse_args()
    for field, variable in (
        ("snapshot", "VISION_LAB_SNAPSHOT"),
        ("annotations", "VISION_LAB_ANNOTATIONS"),
        ("manifests", "VISION_LAB_MANIFESTS"),
        ("runs", "VISION_LAB_RUNS"),
        ("training_python", "VISION_LAB_PYTHON"),
    ):
        if getattr(arguments, field) is not None:
            os.environ[variable] = str(getattr(arguments, field).resolve())
    uvicorn.run(
        create_app(Catalog(arguments.snapshot), arguments.annotations), host="127.0.0.1", port=8102
    )
