"""Run or validate the bounded M7 PostgreSQL and storage load benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.load_benchmark import (  # noqa: E402
    DEFAULT_LOAD_SEED,
    BenchmarkDeadline,
    ImageLoadBenchmarkError,
    build_load_report,
    default_database_url,
    load_profile,
    run_database_load,
    run_storage_load,
    validate_load_report,
)

DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m7-storage-database-load-report.json"
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--seed", type=int, default=DEFAULT_LOAD_SEED)
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _canonical_pretty_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _validate_existing(path: Path, profile_name: str) -> None:
    profile = load_profile(profile_name)
    try:
        content = path.read_bytes()
        report = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise ImageLoadBenchmarkError(
            "The saved M7 load report is missing or invalid JSON."
        ) from error
    validate_load_report(report, expected_profile=profile)
    if content != _canonical_pretty_json(report):
        raise ImageLoadBenchmarkError("The saved M7 load report is not canonical JSON.")
    print(f"Report is valid: {path}")
    print(f"SHA-256: {hashlib.sha256(content).hexdigest()}")


def _resolve_work_root(requested: Path | None) -> tuple[Path, bool]:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if requested is None:
        return (
            Path(tempfile.mkdtemp(prefix="m7-load-", dir=ARTIFACT_ROOT)),
            True,
        )
    resolved = requested.resolve()
    if ARTIFACT_ROOT.resolve() not in resolved.parents:
        raise ImageLoadBenchmarkError(
            "Benchmark work root must be a child of repository artifacts."
        )
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved, False


def main() -> None:
    args = _parse_args()
    output = cast(Path, args.output)
    profile_name = cast(str, args.profile)
    if args.check:
        _validate_existing(output, profile_name)
        return

    profile = load_profile(profile_name)
    max_seconds = cast(float, args.max_seconds)
    seed = cast(int, args.seed)
    deadline = BenchmarkDeadline(max_seconds)
    work_root, cleanup = _resolve_work_root(cast(Path | None, args.work_root))
    try:
        storage = run_storage_load(
            work_root,
            profile,
            seed=seed,
            deadline=deadline,
        )
        database = run_database_load(
            default_database_url(),
            REPOSITORY_ROOT,
            profile,
            seed=seed,
            deadline=deadline,
        )
        report = build_load_report(profile, database, storage)
        content = _canonical_pretty_json(report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        print(json.dumps(report, indent=2, sort_keys=True))
        print(f"Saved M7 load benchmark to {output}.")
        print(f"SHA-256: {hashlib.sha256(content).hexdigest()}")
    finally:
        if cleanup:
            resolved_work_root = work_root.resolve()
            if ARTIFACT_ROOT.resolve() not in resolved_work_root.parents:
                raise ImageLoadBenchmarkError(
                    "Refusing to clean a work root outside repository artifacts."
                )
            shutil.rmtree(resolved_work_root, ignore_errors=False)


if __name__ == "__main__":
    main()
