"""Run or validate the bounded M7.0 image-selection benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.selection.benchmark import (  # noqa: E402
    ImageSelectionBenchmarkError,
    canonical_pretty_json,
    load_scale_annotations,
    run_scale_benchmark,
    validate_scale_report,
)

ANNOTATIONS_PATH = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "image-selection-scale-annotations-v1.json"
)
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts"
QUALITY_ROOT = REPOSITORY_ROOT / "ai_docs" / "quality"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("smoke", "10000", "30000"), default="smoke")
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _default_output(profile_name: str) -> Path:
    return QUALITY_ROOT / f"image-selection-{profile_name}-report.json"


def _resolve_work_root(requested: Path | None) -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if requested is None:
        temporary = tempfile.mkdtemp(prefix="image-selection-benchmark-", dir=ARTIFACT_ROOT)
        path = Path(temporary)
        path.rmdir()
        return path
    resolved = requested.resolve()
    if ARTIFACT_ROOT.resolve() not in resolved.parents:
        raise ImageSelectionBenchmarkError(
            "Benchmark work root must be a child of repository artifacts."
        )
    if resolved.exists():
        raise ImageSelectionBenchmarkError("Benchmark work root must not already exist.")
    return resolved


def _read_report(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = cast(dict[str, Any], json.loads(content))
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ImageSelectionBenchmarkError(
            "The saved image-selection benchmark report is missing or invalid JSON."
        ) from error
    if content != canonical_pretty_json(value):
        raise ImageSelectionBenchmarkError(
            "The saved image-selection benchmark report is not canonical JSON."
        )
    return value, content


def _write_report_atomic(path: Path, report: dict[str, object]) -> bytes:
    content = canonical_pretty_json(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_bytes(content)
    pending.replace(path)
    return content


def main() -> None:
    args = _parse_args()
    annotations = load_scale_annotations(ANNOTATIONS_PATH)
    profile_name = cast(str, args.profile)
    profile = annotations.profiles[profile_name]
    output = cast(Path | None, args.output) or _default_output(profile_name)
    if args.check:
        report, content = _read_report(output)
        validate_scale_report(
            report,
            expected_profile=profile,
            expected_annotation_fingerprint=annotations.fingerprint,
        )
        if cast(dict[str, Any], report["metrics"])["technicalGatePassed"] is not True:
            raise ImageSelectionBenchmarkError("The saved benchmark did not pass its gate.")
        print(f"Report is valid: {output}")
        print(f"SHA-256: {hashlib.sha256(content).hexdigest()}")
        return

    max_seconds = cast(float, args.max_seconds)
    if max_seconds <= 0:
        raise ImageSelectionBenchmarkError("--max-seconds must be positive.")
    work_root = _resolve_work_root(cast(Path | None, args.work_root))
    try:
        report = run_scale_benchmark(
            work_root=work_root,
            profile=profile,
            annotations=annotations,
            max_seconds=max_seconds,
        )
        report["cleanup"] = {
            "partialManifestPublished": False,
            "workRootPolicy": "always-remove-on-exit",
        }
        content = _write_report_atomic(output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        print(f"Saved image-selection benchmark to {output}.")
        print(f"SHA-256: {hashlib.sha256(content).hexdigest()}")
        if cast(dict[str, Any], report["metrics"])["technicalGatePassed"] is not True:
            raise ImageSelectionBenchmarkError("The image-selection benchmark gate failed.")
    finally:
        if work_root.exists():
            resolved = work_root.resolve()
            if ARTIFACT_ROOT.resolve() not in resolved.parents:
                raise ImageSelectionBenchmarkError(
                    "Refusing to clean a work root outside repository artifacts."
                )
            shutil.rmtree(resolved, ignore_errors=False)


if __name__ == "__main__":
    main()
