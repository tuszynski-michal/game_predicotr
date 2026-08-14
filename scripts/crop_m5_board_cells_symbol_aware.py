"""Regenerate the full M5 corpus with guarded symbol-aware refinement."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.local_grid_calibration import (  # noqa: E402
    LocalGridCalibrationError,
    LocalImageGridCalibrationProfiles,
)
from game_predictor_worker.images.rectification import (  # noqa: E402
    BoardCropError,
    crop_detected_corpus,
)
from game_predictor_worker.images.symbol_grid_refinement import (  # noqa: E402
    PerspectiveBoardCellCropperV5SymbolAwareAffine,
)

DEFAULT_NORMALIZATION_REPORT = ROOT / "ai_docs" / "quality" / "m5-normalization-report.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_PROFILES = ROOT / "ai_docs" / "quality" / "m5-complete-local-grid-profiles.json"
DEFAULT_NORMALIZATION_ROOT = ROOT / "artifacts" / "m5-normalization"
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v5-symbol-aware-affine-report.json"
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument(
        "--normalization-report",
        type=Path,
        default=DEFAULT_NORMALIZATION_REPORT,
    )
    parser.add_argument(
        "--detection-report",
        type=Path,
        default=DEFAULT_DETECTION_REPORT,
    )
    parser.add_argument(
        "--normalization-root",
        type=Path,
        default=DEFAULT_NORMALIZATION_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
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
        profiles = LocalImageGridCalibrationProfiles.from_files(
            args.profiles,
            args.manifest,
        )
        report = crop_detected_corpus(
            args.normalization_report,
            args.detection_report,
            args.normalization_root,
            args.artifact_root,
            cropper=PerspectiveBoardCellCropperV5SymbolAwareAffine(),
            calibrator=profiles,
        )
        content = report.to_json_bytes()
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                raise BoardCropError(
                    "SYMBOL_AWARE_CROP_REPORT_STALE",
                    "Symbol-aware crop report is missing or stale.",
                )
        else:
            _write_atomic(args.output, content)
        summary = report.to_dict()
        print(
            json.dumps(
                {
                    "boardCount": summary["boardCount"],
                    "cellCount": summary["cellCount"],
                    "croppedImageCount": summary["croppedImageCount"],
                    "cropperVersion": summary["cropperVersion"],
                    "imageCount": summary["imageCount"],
                    "needsReviewCount": summary["needsReviewCount"],
                    "output": str(args.output.resolve()),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "status": summary["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        BoardCropError,
        LocalGridCalibrationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        code = getattr(error, "code", "SYMBOL_AWARE_CROP_FAILED")
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
