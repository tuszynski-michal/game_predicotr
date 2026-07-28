"""Generate deterministic JSONL fixtures for the M4 acceptance run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.imports.fixtures import (  # noqa: E402
    DEFAULT_ACCEPTANCE_LAYOUT_COUNT,
    DEFAULT_ACCEPTANCE_SEED,
    write_blocked_layout_import_fixture,
    write_layout_import_fixture,
)

DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "imports" / "m4-acceptance"


def _progress(current: int, total: int) -> None:
    if current == total or current % 25_000 == 0:
        print(f"generated: {current:,}/{total:,}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    parser.add_argument(
        "--layout-count",
        type=int,
        default=DEFAULT_ACCEPTANCE_LAYOUT_COUNT,
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_ACCEPTANCE_SEED)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output_directory = args.output_directory.resolve()
    valid = write_layout_import_fixture(
        output_directory / "layouts-500k.jsonl",
        layout_count=args.layout_count,
        seed=args.seed,
        progress=_progress,
    )
    blocked = write_blocked_layout_import_fixture(
        output_directory / "layouts-blocked.jsonl",
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "blocked": blocked.to_dict(),
                "valid": valid.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
