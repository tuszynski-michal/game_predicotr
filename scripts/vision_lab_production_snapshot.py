"""Training snapshot of production 777 geometry and the label-review sample (TASK-0801).

Reads the candidate manifest of ``vision_lab_geometry_export.py`` (TASK-0800) and
the managed source photos read-only; never touches the database.

    preview       plan the ``production-geometry-split-v1`` split, print the counts and
                  the copy size; copies nothing and writes nothing (files are only
                  checked for existence)
    build         plan with SHA-256 and decode checks, copy, verify and publish the
                  snapshot atomically under ``--output-root/<snapshotId>``; a re-run
                  with the same seed and input verifies and leaves it untouched
    label-review  draw 300 S + 300 B boards from the filtered manifest and publish
                  the review sample (crops + sample.json) into ``--output``; the
                  operator then runs ``python -m game_predictor_worker.vision_lab.label_review``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from game_predictor_worker.vision_lab import production_snapshot
from game_predictor_worker.vision_lab.label_review import prepare_review
from game_predictor_worker.vision_lab.production_split import SplitConfig

DEFAULT_SEED = 801


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "build"):
        command = commands.add_parser(name)
        _common(command)
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--training-per-level", type=int, default=3000)
        command.add_argument("--development-per-level", type=int, default=300)
        command.add_argument("--max-copy-gib", type=float, default=3.0)
    review = commands.add_parser("label-review")
    _common(review)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--per-level", type=int, default=300)
    arguments = parser.parse_args()

    started = time.monotonic()
    if arguments.command == "label-review":
        sample = prepare_review(
            arguments.candidates,
            arguments.artifact_root,
            arguments.output,
            arguments.seed,
            arguments.per_level,
        )
        print(
            json.dumps(
                {
                    "sampleId": sample["sampleId"],
                    "items": len(sample["items"]),
                    "population": sample["population"],
                    "integrityExclusions": sample["integrityExclusions"],
                    "output": str(arguments.output),
                    "seconds": round(time.monotonic() - started, 1),
                },
                indent=2,
            )
        )
        return 0

    config = SplitConfig(
        seed=arguments.seed,
        training_per_level=arguments.training_per_level,
        development_per_level=arguments.development_per_level,
    )
    result = production_snapshot.build_snapshot(
        arguments.candidates,
        arguments.artifact_root,
        arguments.output_root,
        config,
        preview=arguments.command == "preview",
        max_copy_bytes=int(arguments.max_copy_gib * 1024**3),
    )
    result.timings["totalSeconds"] = round(time.monotonic() - started, 1)
    print(
        json.dumps(
            {
                "mode": result.mode,
                "status": result.status,
                "snapshotId": result.snapshot_id,
                "destination": str(result.destination) if result.destination else None,
                "copyBytes": result.selected_bytes,
                "blockers": result.blockers,
                "timings": result.timings,
                "summary": result.summary,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 2 if result.blockers else 0


if __name__ == "__main__":
    sys.exit(main())
