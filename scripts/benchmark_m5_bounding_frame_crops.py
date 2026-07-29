"""Generate a fail-safe full-bounding-frame crop spike for visual comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.geometry import Point, Quad  # noqa: E402
from game_predictor_worker.images.local_grid_calibration import (  # noqa: E402
    local_bounding_frame,
)
from game_predictor_worker.images.rectification import (  # noqa: E402
    BoardCropError,
    BoardGeometry,
    PageGeometry,
    PerspectiveBoardCellCropperV2,
    crop_detected_corpus,
)

SPIKE_CROPPER_VERSION = "board-cell-crops-bounding-frame-spike-v1"
SPIKE_PROFILE_VERSION = "bounding-frame-per-board-spike-v1"

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_NORMALIZATION_REPORT = ROOT / "ai_docs" / "quality" / "m5-normalization-report.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_NORMALIZATION_ROOT = ROOT / "artifacts" / "m5-normalization"
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT = ROOT / "ai_docs" / "quality" / "m5-bounding-frame-crop-spike-report.json"


class _BoundingFrameCropper(PerspectiveBoardCellCropperV2):
    version = SPIKE_CROPPER_VERSION


class _BoundingFrameCalibrator:
    profile_set_version = SPIKE_PROFILE_VERSION

    def __init__(self, manifest_path: Path, detection_report_path: Path) -> None:
        manifest_bytes = manifest_path.read_bytes()
        detection_bytes = detection_report_path.read_bytes()
        self.profile_set_sha256 = hashlib.sha256(
            SPIKE_PROFILE_VERSION.encode() + b"\0" + detection_bytes
        ).hexdigest()
        self.corpus_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self.detection_report_sha256 = hashlib.sha256(detection_bytes).hexdigest()

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        del source_checksum_sha256
        if geometry.status != "detected":
            return geometry
        boards: list[BoardGeometry] = []
        for board in geometry.boards:
            if board.bounding_box is None:
                return PageGeometry(
                    status="needs_review",
                    image_width=geometry.image_width,
                    image_height=geometry.image_height,
                    boards=(),
                    review_reasons=("BOUNDING_FRAME_MISSING",),
                )
            boards.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=cast(
                        Quad,
                        tuple(
                            Point(round(x), round(y))
                            for x, y in local_bounding_frame(board.bounding_box)
                        ),
                    ),
                    bounding_box=board.bounding_box,
                    source_quad_source="detector-local-bounding-frame-spike",
                )
            )
        return PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(boards),
            review_reasons=(),
        )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--normalization-report", type=Path, default=DEFAULT_NORMALIZATION_REPORT)
    parser.add_argument("--detection-report", type=Path, default=DEFAULT_DETECTION_REPORT)
    parser.add_argument("--normalization-root", type=Path, default=DEFAULT_NORMALIZATION_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
        report = crop_detected_corpus(
            args.normalization_report,
            args.detection_report,
            args.normalization_root,
            args.artifact_root,
            cropper=_BoundingFrameCropper(),
            calibrator=_BoundingFrameCalibrator(args.manifest, args.detection_report),
        )
        content = report.to_json_bytes()
        _write_atomic(args.output, content)
        value = report.to_dict()
        print(
            json.dumps(
                {
                    "boardCount": value["boardCount"],
                    "cellCount": value["cellCount"],
                    "imageCount": value["imageCount"],
                    "needsReviewCount": value["needsReviewCount"],
                    "output": str(args.output.resolve()),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "status": value["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (BoardCropError, OSError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "BOUNDING_FRAME_CROP_SPIKE_FAILED")
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
