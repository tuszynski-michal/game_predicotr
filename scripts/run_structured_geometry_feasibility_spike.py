"""Run the bounded, read-only Structured OpenCV feasibility spike."""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
API_SOURCE = REPOSITORY_ROOT / "services" / "api" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

# The API package root eagerly imports the FastAPI application, which imports
# worker preview adapters in return.  This read-only worker tool needs domain
# contracts only, so expose the package path without starting the HTTP graph.
api_package = types.ModuleType("game_predictor_api")
api_package.__path__ = [str(API_SOURCE / "game_predictor_api")]
sys.modules.setdefault("game_predictor_api", api_package)

from game_predictor_worker.images.structured_geometry.feasibility_spike import (  # noqa: E402
    GeometryFeasibilitySpikeError,
    run_feasibility_spike,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate read-only geometry diagnostics for 30–50 immutable JPEGs."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT
        / "ai_docs"
        / "quality"
        / "structured-geometry-feasibility-input-v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "structured-geometry-feasibility-v1",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        report = run_feasibility_spike(
            manifest_path=args.manifest.resolve(strict=True),
            output_root=args.output,
        )
    except GeometryFeasibilitySpikeError as error:
        print(json.dumps({"code": error.code, "message": str(error), "status": "failed"}))
        return 1
    print(
        json.dumps(
            {
                "corpusReadiness": report["corpusReadiness"],
                "decision": report["decision"],
                "reportChecksumSha256": report["reportChecksumSha256"],
                "reportPath": str((args.output / "report.json").resolve()),
                "status": "completed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
