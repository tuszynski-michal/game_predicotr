"""Create or verify the deterministic M6 source-aware dataset split."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.dataset_split import (  # noqa: E402
    DEFAULT_SPLIT_SEED,
    SymbolDatasetSplitError,
    build_symbol_dataset_split,
)

QUALITY_ROOT = REPOSITORY_ROOT / "ai_docs" / "quality"
DEFAULT_INPUT = QUALITY_ROOT / "m6-symbol-dataset-export-report.json"
DEFAULT_OUTPUT = QUALITY_ROOT / "m6-symbol-dataset-split-report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", default=DEFAULT_SPLIT_SEED)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Return exit code 1 unless the structural split gate passed.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _persist(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_REPORT_MISSING",
                "The expected split report cannot be read.",
            ) from error
        if existing != content:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_REPORT_DRIFT",
                "The split report differs from the current input and seed.",
            )
        return
    _write_atomic(path, content)


def main() -> int:
    args = _parse_args()
    try:
        report = build_symbol_dataset_split(args.input, seed=args.seed)
        content = report.to_json_bytes()
        _persist(args.output, content, check=args.check)
        value = report.to_dict()
        print(
            json.dumps(
                {
                    "bootstrapTargetMet": value["bootstrapTargetMet"],
                    "reportSha256": hashlib.sha256(content).hexdigest(),
                    "sampleCount": value["sampleCount"],
                    "sourceImageCount": value["sourceImageCount"],
                    "status": report.status,
                },
                sort_keys=True,
            )
        )
        if args.require_pass and report.status != "ready":
            return 1
        return 0
    except SymbolDatasetSplitError as error:
        print(
            json.dumps(
                {"code": error.code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
