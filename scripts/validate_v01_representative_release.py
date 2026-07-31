"""Independently validate the local representative 0.1 release package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "services" / "api" / "src",
    REPOSITORY_ROOT / "services" / "worker" / "src",
):
    value = str(source_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from game_predictor_worker.releases.representative_v01 import (  # noqa: E402
    validate_representative_release,
)

DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "v01-representative-release"


def _progress(phase: str, current: int, total: int) -> None:
    if current == total or current % 25_000 == 0:
        print(f"{phase}: {current:,}/{total:,}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    report = validate_representative_release(
        options.output_directory,
        progress=_progress,
    )
    print(
        json.dumps(
            {
                "approvedBoardCount": report.approved_board_count,
                "duplicateGroupCount": report.duplicate_group_count,
                "layoutCount": report.layout_count,
                "logicalContentSha256": report.logical_content_sha256,
                "maximumValidationBatchSize": report.maximum_validation_batch_size,
                "snapshotFileSha256": report.snapshot_file_sha256,
                "snapshotSizeBytes": report.snapshot_size_bytes,
                "symbolCount": report.symbol_count,
                "uniqueFixtureSequenceNumber": report.unique_fixture_sequence_number,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
