"""Build a release APK containing the validated M3.5 benchmark snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.releases import (  # noqa: E402
    AndroidReleaseBuildSpec,
    PowerShellAndroidReleaseBuilder,
)
from game_predictor_worker.snapshots import validate_snapshot_artifact  # noqa: E402

DEFAULT_DATASET_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "m35-benchmark"
DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "m35-benchmark-apk"


def _artifact_directory(dataset_directory: Path) -> Path:
    manifest_value: Any = json.loads(
        (dataset_directory / "benchmark-manifest.json").read_text(encoding="utf-8")
    )
    if not isinstance(manifest_value, dict):
        raise RuntimeError("Benchmark manifest root must be an object.")
    artifact = cast(dict[str, Any], manifest_value).get("artifact")
    if not isinstance(artifact, dict):
        raise RuntimeError("Benchmark artifact metadata is invalid.")
    relative_directory = artifact.get("relativeDirectory")
    if not isinstance(relative_directory, str):
        raise RuntimeError("Benchmark artifact directory is invalid.")
    return dataset_directory / relative_directory


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-directory",
        type=Path,
        default=DEFAULT_DATASET_DIRECTORY,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
    )
    parser.add_argument("--version-code", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    dataset_directory = cast(Path, args.dataset_directory).resolve()
    artifact_root = cast(Path, args.artifact_root).resolve()
    snapshot = validate_snapshot_artifact(_artifact_directory(dataset_directory))
    result = PowerShellAndroidReleaseBuilder(
        REPOSITORY_ROOT,
        artifact_root,
    ).build(
        AndroidReleaseBuildSpec(
            release_version=snapshot.manifest.release_version,
            version_code=cast(int, args.version_code),
            snapshot=snapshot,
        )
    )
    print(f"APK: {result.apk_path}")
    print(f"APK SHA-256: {result.apk_sha256}")
    print(f"Snapshot SHA-256: {result.snapshot_sha256}")


if __name__ == "__main__":
    main()
