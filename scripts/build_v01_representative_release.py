"""Prepare and optionally build the representative 500k-layout 0.1 package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

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
from game_predictor_worker.releases import (  # noqa: E402
    AndroidReleaseBuildSpec,
    PowerShellAndroidReleaseBuilder,
)
from game_predictor_worker.releases.representative_v01 import (  # noqa: E402
    V01_IMPORT_JOB_ID,
    V01_LAYOUT_COUNT,
    V01_MANIFEST_FILE,
    V01_RELEASE_VERSION,
    V01_SEED,
    generate_representative_release,
    load_approved_boards,
    load_representative_snapshot_artifact,
    select_representative_symbol_assets,
    validate_representative_release,
)

DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "v01-representative-release"
DEFAULT_CELL_ROOT = REPOSITORY_ROOT / "artifacts" / "data" / "m65-real-workbench-v1" / "cells"
DEFAULT_MOBILE_SYMBOL_ROOT = REPOSITORY_ROOT / "apps" / "mobile" / "assets" / "symbols" / "v01"
RELEASE_REPORT_FILE = "release-report.json"


def _progress(phase: str, current: int, total: int) -> None:
    if current == total or current % 25_000 == 0:
        print(f"{phase}: {current:,}/{total:,}", flush=True)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--build-apk", action="store_true")
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cell-root", type=Path, default=DEFAULT_CELL_ROOT)
    parser.add_argument("--version-code", type=int, default=6)
    return parser.parse_args()


def main() -> int:
    options = _arguments()
    output_directory = cast(Path, options.output_directory).resolve()
    manifest_path = output_directory / V01_MANIFEST_FILE
    if cast(bool, options.build_apk) and manifest_path.is_file():
        print("Using the existing validated representative snapshot.", flush=True)
        artifact = load_representative_snapshot_artifact(output_directory)
    else:
        package_symbol_root = output_directory / "symbols"
        settings = ApiSettings.from_environment()
        engine = create_database_engine(settings)
        try:
            approved_boards = load_approved_boards(
                engine,
                import_job_id=V01_IMPORT_JOB_ID,
            )
        finally:
            engine.dispose()
        print(f"Approved boards: {len(approved_boards)}", flush=True)
        symbol_assets = select_representative_symbol_assets(
            approved_boards,
            cell_root=cast(Path, options.cell_root),
            package_symbol_root=package_symbol_root,
            mobile_symbol_root=DEFAULT_MOBILE_SYMBOL_ROOT,
        )
        print(f"Representative symbol assets: {len(symbol_assets)}", flush=True)
        artifact = generate_representative_release(
            output_directory,
            approved_boards,
            symbol_assets,
            progress=_progress,
        ).artifact
    validation = validate_representative_release(output_directory, progress=_progress)

    apk_path: str | None = None
    apk_sha256: str | None = None
    if cast(bool, options.build_apk):
        android = PowerShellAndroidReleaseBuilder(
            REPOSITORY_ROOT,
            output_directory,
        ).build(
            AndroidReleaseBuildSpec(
                release_version=V01_RELEASE_VERSION,
                version_code=cast(int, options.version_code),
                snapshot=artifact,
            )
        )
        apk_path = android.apk_path.relative_to(output_directory).as_posix()
        apk_sha256 = android.apk_sha256

    report = {
        "apk": (
            None
            if apk_path is None
            else {
                "relativePath": apk_path,
                "sha256": apk_sha256,
                "versionCode": cast(int, options.version_code),
            }
        ),
        "approvedBoardCount": validation.approved_board_count,
        "duplicateGroupCount": validation.duplicate_group_count,
        "generatorSeed": V01_SEED,
        "layoutCount": V01_LAYOUT_COUNT,
        "logicalContentSha256": validation.logical_content_sha256,
        "manifest": manifest_path.relative_to(output_directory).as_posix(),
        "releaseVersion": V01_RELEASE_VERSION,
        "snapshotFileSha256": validation.snapshot_file_sha256,
        "snapshotSizeBytes": validation.snapshot_size_bytes,
        "symbolCount": validation.symbol_count,
        "uniqueFixtureSequenceNumber": validation.unique_fixture_sequence_number,
    }
    report_path = output_directory / RELEASE_REPORT_FILE
    report_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Package directory: {output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
