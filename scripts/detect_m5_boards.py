"""Run page/3 × 3 board detection on normalized M5 working images."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.geometry import (  # noqa: E402
    GeometryDetectionError,
    detect_normalized_corpus,
    expected_board_counts_from_manifest,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("normalization_report", type=Path)
    parser.add_argument("--normalization-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help="Explicit expected board count per source; enables audited grid recovery.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that --output already contains the deterministic report.",
    )
    parser.add_argument(
        "--require-detected",
        action="store_true",
        help="Return exit code 1 when any image needs review.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _validate_report_path(normalization_root: Path, output: Path) -> Path:
    normalization = normalization_root.resolve(strict=True)
    resolved = output.resolve()
    if resolved == normalization or resolved.is_relative_to(normalization):
        raise GeometryDetectionError(
            "PAGE_DETECTION_REPORT_IN_NORMALIZATION_ROOT",
            "Page detection report must be outside the normalization artifact root.",
        )
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        report = detect_normalized_corpus(
            args.normalization_report,
            args.normalization_root,
            args.artifact_root,
            expected_board_counts=(
                expected_board_counts_from_manifest(args.corpus_manifest)
                if args.corpus_manifest is not None
                else None
            ),
        )
        content = report.to_json_bytes()
        if args.check and args.output is None:
            raise GeometryDetectionError(
                "PAGE_DETECTION_CHECK_OUTPUT_REQUIRED",
                "--check requires --output.",
            )
        if args.output is None:
            sys.stdout.buffer.write(content)
        else:
            output = _validate_report_path(args.normalization_root, args.output)
            if args.check:
                try:
                    existing = output.read_bytes()
                except OSError as error:
                    raise GeometryDetectionError(
                        "PAGE_DETECTION_REPORT_MISSING",
                        "Expected page detection report cannot be read.",
                    ) from error
                if existing != content:
                    raise GeometryDetectionError(
                        "PAGE_DETECTION_REPORT_DRIFT",
                        "Page detection report differs from current artifacts.",
                    )
            else:
                _write_atomic(output, content)
            payload = report.to_dict()
            print(
                json.dumps(
                    {
                        "detectedCount": payload["detectedCount"],
                        "imageCount": payload["imageCount"],
                        "needsReviewCount": payload["needsReviewCount"],
                        "reportSha256": hashlib.sha256(content).hexdigest(),
                        "status": payload["status"],
                    },
                    sort_keys=True,
                )
            )
        if args.require_detected and any(
            detection.result.status != "detected" for detection in report.detections
        ):
            return 1
        return 0
    except GeometryDetectionError as error:
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
