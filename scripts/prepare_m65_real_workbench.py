"""Prepare the accepted real-image corpus for the local M6.5 review UI."""

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

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.database import create_database_engine  # noqa: E402
from game_predictor_worker.images.real_workbench_fixture import (  # noqa: E402
    prepare_real_workbench_fixture,
)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load the checksum-bound M5/M6 corpus into the M6.5 workbench.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/m65-real-workbench-v1/prepare-report.json"),
        help="Relative or absolute path for the deterministic preparation result.",
    )
    options = parser.parse_args(arguments)
    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    try:
        result = prepare_real_workbench_fixture(engine, REPOSITORY_ROOT)
    finally:
        engine.dispose()
    report_path = (
        options.report
        if options.report.is_absolute()
        else REPOSITORY_ROOT / options.report
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        result.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    report_path.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
