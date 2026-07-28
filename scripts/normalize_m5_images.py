"""Normalize discovered M5 JPEG files into immutable local working artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.normalization import (  # noqa: E402
    ImageNormalizationError,
    normalize_images,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("discovery_manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that --output already contains the deterministic report.",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Return exit code 1 when any source image cannot be normalized.",
    )
    return parser.parse_args()


def _validate_report_path(source_root: Path, output: Path) -> Path:
    source = source_root.resolve(strict=True)
    resolved = output.resolve()
    if resolved == source or resolved.is_relative_to(source):
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_REPORT_IN_SOURCE",
            "Normalization report must be stored outside the source root.",
        )
    return resolved


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def main() -> int:
    args = _parse_args()
    try:
        report = normalize_images(
            args.source_root,
            args.discovery_manifest,
            args.artifact_root,
        )
        content = report.to_json_bytes()
        if args.check and args.output is None:
            raise ImageNormalizationError(
                "IMAGE_NORMALIZATION_CHECK_OUTPUT_REQUIRED",
                "--check requires --output.",
            )
        if args.output is None:
            sys.stdout.buffer.write(content)
        else:
            output = _validate_report_path(args.source_root, args.output)
            if args.check:
                try:
                    existing = output.read_bytes()
                except OSError as error:
                    raise ImageNormalizationError(
                        "IMAGE_NORMALIZATION_REPORT_MISSING",
                        "Expected normalization report cannot be read.",
                    ) from error
                if existing != content:
                    raise ImageNormalizationError(
                        "IMAGE_NORMALIZATION_REPORT_DRIFT",
                        "Normalization report differs from current artifacts.",
                    )
            else:
                _write_atomic(output, content)
            print(
                json.dumps(
                    {
                        "issueCount": len(report.issues),
                        "normalizedImageCount": len(report.images),
                        "normalizationReportSha256": hashlib.sha256(content).hexdigest(),
                        "status": "clean" if not report.issues else "issues",
                    },
                    sort_keys=True,
                )
            )
        if args.require_clean and report.issues:
            return 1
        return 0
    except ImageNormalizationError as error:
        print(
            json.dumps(
                {"code": error.code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
