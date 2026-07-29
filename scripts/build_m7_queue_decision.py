"""Build or verify the checksum-bound M7 queue architecture decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from game_predictor_worker.images.queue_decision import (
    QueueArchitectureDecisionError,
    build_queue_decision,
    queue_decision_bytes,
    validate_queue_decision,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m7-queue-architecture-decision.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        if args.check:
            report = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise QueueArchitectureDecisionError("Decision must be an object.")
            validate_queue_decision(report, REPOSITORY_ROOT)
            payload = queue_decision_bytes(report, REPOSITORY_ROOT)
            if payload != output.read_bytes():
                raise QueueArchitectureDecisionError("Decision is valid but not canonical JSON.")
            print(f"Queue architecture decision is valid: {output}")
        else:
            report = build_queue_decision(REPOSITORY_ROOT)
            payload = queue_decision_bytes(report, REPOSITORY_ROOT)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            print(payload.decode("utf-8").rstrip())
            print(f"Saved queue architecture decision to {output}.")
        print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")
        return 0
    except (QueueArchitectureDecisionError, OSError, ValueError) as error:
        print(f"Queue architecture decision failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
