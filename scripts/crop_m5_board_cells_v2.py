"""Regenerate deterministic detector-driven M5 board-cell-crops-v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.rectification import (  # noqa: E402
    BoardCropError,
    PerspectiveBoardCellCropperV2,
    crop_detected_corpus,
)

DEFAULT_NORMALIZATION_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-normalization-report.json"
)
DEFAULT_DETECTION_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
)
DEFAULT_NORMALIZATION_ROOT = REPOSITORY_ROOT / "artifacts" / "m5-normalization"
DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v2-report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "normalization_report",
        type=Path,
        nargs="?",
        default=DEFAULT_NORMALIZATION_REPORT,
    )
    parser.add_argument(
        "detection_report",
        type=Path,
        nargs="?",
        default=DEFAULT_DETECTION_REPORT,
    )
    parser.add_argument(
        "--normalization-root",
        type=Path,
        default=DEFAULT_NORMALIZATION_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the output report and immutable artifacts are current.",
    )
    parser.add_argument(
        "--require-cropped",
        action="store_true",
        help="Return exit code 1 when any source image needs review.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _report_path(
    normalization_root: Path,
    artifact_root: Path,
    output: Path,
) -> Path:
    normalization = normalization_root.resolve(strict=True)
    artifacts = artifact_root.resolve()
    resolved = output.resolve()
    if (
        resolved in (normalization, artifacts)
        or resolved.is_relative_to(normalization)
        or resolved.is_relative_to(artifacts)
    ):
        raise BoardCropError(
            "BOARD_CROP_REPORT_IN_ARTIFACT_ROOT",
            "The v2 report must stay outside image artifact roots.",
        )
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        report = crop_detected_corpus(
            args.normalization_report,
            args.detection_report,
            args.normalization_root,
            args.artifact_root,
            cropper=PerspectiveBoardCellCropperV2(),
        )
        content = report.to_json_bytes()
        output = _report_path(
            args.normalization_root,
            args.artifact_root,
            args.output,
        )
        if args.check:
            try:
                existing = output.read_bytes()
            except OSError as error:
                raise BoardCropError(
                    "BOARD_CROP_REPORT_MISSING",
                    "Expected v2 board crop report cannot be read.",
                ) from error
            if existing != content:
                raise BoardCropError(
                    "BOARD_CROP_REPORT_DRIFT",
                    "The v2 board crop report differs from current artifacts.",
                )
        else:
            _write_atomic(output, content)
        payload = report.to_dict()
        print(
            json.dumps(
                {
                    "boardCount": payload["boardCount"],
                    "cellCount": payload["cellCount"],
                    "croppedImageCount": payload["croppedImageCount"],
                    "cropperVersion": payload["cropperVersion"],
                    "imageCount": payload["imageCount"],
                    "needsReviewCount": payload["needsReviewCount"],
                    "reportSha256": hashlib.sha256(content).hexdigest(),
                    "status": payload["status"],
                },
                sort_keys=True,
            )
        )
        if args.require_cropped and report.to_dict()["status"] != "cropped":
            return 1
        return 0
    except (BoardCropError, OSError) as error:
        code = getattr(error, "code", "BOARD_CROP_V2_IO_FAILED")
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
