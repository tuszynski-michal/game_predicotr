"""Run or validate the physical M7 recovery and review benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from game_predictor_worker.images.load_benchmark import default_database_url
from game_predictor_worker.images.operations_benchmark import (
    ImageOperationsBenchmarkError,
    build_operations_report,
    operations_report_bytes,
    validate_operations_report,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m7-import-operations-benchmark-report.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=300.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        if args.check:
            report = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ImageOperationsBenchmarkError("Report must be an object.")
            validate_operations_report(report)
            payload = operations_report_bytes(report)
            if payload != output.read_bytes():
                raise ImageOperationsBenchmarkError("Report is valid but not canonical JSON.")
            print(f"Report is valid: {output}")
        else:
            report = build_operations_report(
                default_database_url(),
                REPOSITORY_ROOT,
                max_seconds=args.max_seconds,
            )
            payload = operations_report_bytes(report)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            print(payload.decode("utf-8").rstrip())
            print(f"Saved M7 operations benchmark to {output}.")
        print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")
        return 0
    except (ImageOperationsBenchmarkError, OSError, ValueError) as error:
        print(f"M7 operations benchmark failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
