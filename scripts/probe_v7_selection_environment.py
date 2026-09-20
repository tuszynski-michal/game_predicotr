"""Run the v7 selection feasibility gate without changing source JPEGs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source in (
    REPOSITORY_ROOT / "services" / "worker" / "src",
    REPOSITORY_ROOT / "services" / "api" / "src",
):
    sys.path.insert(0, str(source))

from game_predictor_worker.semi_automatic_selection.v7_feasibility import (  # noqa: E402
    prepare_isolated_artifact_root,
    probe_v7_environment,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--prepare-artifact-root", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    report = probe_v7_environment(
        checkout_root=args.checkout_root,
        artifact_root=args.artifact_root,
        corpus_root=args.corpus_root,
        model_root=args.model_root,
        require_gpu=args.require_gpu,
    )
    payload = report.as_dict()
    if args.prepare_artifact_root and report.artifact_root_is_isolated:
        try:
            prepare_isolated_artifact_root(report)
            payload["artifactWriteCheck"] = "passed"
        except OSError as error:
            payload["artifactWriteCheck"] = "failed"
            payload["artifactWriteCheckError"] = f"{type(error).__name__}: {error}"
            payload["blockers"] = [*report.blockers, "ARTIFACT_ROOT_UNWRITABLE"]
            payload["status"] = "blocked"
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if payload["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
