"""Validate the local M5 image corpus without modifying source images."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images import (  # noqa: E402
    CorpusValidationError,
    validate_corpus,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "Return exit code 1 until every image has complete geometry "
            "and the manifest is accepted."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        report = validate_corpus(
            REPOSITORY_ROOT,
            args.manifest.resolve(),
            args.annotations.resolve(),
        )
    except CorpusValidationError as error:
        print(json.dumps({"code": error.code, "message": str(error), "status": "failed"}))
        raise SystemExit(1) from error
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if args.require_complete and not report.ready_for_geometry_benchmark:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
