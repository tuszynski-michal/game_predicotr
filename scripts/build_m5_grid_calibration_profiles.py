"""Build deterministic M5 grid calibration profiles from accepted anchors."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_grid_golden import (  # noqa: E402
    CellGridGoldenError,
    CellGridGoldenReview,
)
from game_predictor_worker.images.grid_calibration import (  # noqa: E402
    GridCalibrationError,
    build_profile_document,
    profile_document_bytes,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_V1_CROP_REPORT = ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_GOLDEN = ROOT / "ai_docs" / "quality" / "m5-cell-grid-golden.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_OUTPUT = ROOT / "ai_docs" / "quality" / "m5-grid-calibration-profiles.json"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--v1-crop-report", type=Path, default=DEFAULT_V1_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--detection-report", type=Path, default=DEFAULT_DETECTION_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the published profile document is current.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    args = _args()
    try:
        review = CellGridGoldenReview(
            repository_root=ROOT,
            manifest_path=args.manifest,
            annotations_path=args.annotations,
            crop_report_path=args.v1_crop_report,
            crop_root=args.crop_root,
            output_path=args.golden,
        )
        golden_bytes = args.golden.read_bytes()
        detection_bytes = args.detection_report.read_bytes()
        content = profile_document_bytes(
            build_profile_document(
                review.golden,
                golden_sha256=hashlib.sha256(golden_bytes).hexdigest(),
                detector_report_sha256=hashlib.sha256(detection_bytes).hexdigest(),
            )
        )
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                print(
                    "ERROR: grid calibration profile document is missing or stale.",
                    file=sys.stderr,
                )
                return 1
        else:
            _write_atomic(args.output, content)
        report = json.loads(content)
        print(
            json.dumps(
                {
                    "anchorCount": report["anchorCount"],
                    "profileCount": report["profileCount"],
                    "profileSetVersion": report["profileSetVersion"],
                    "reportSha256": hashlib.sha256(content).hexdigest(),
                    "status": report["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (CellGridGoldenError, GridCalibrationError, OSError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "GRID_CALIBRATION_BUILD_FAILED")
        print(
            json.dumps(
                {"code": code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
