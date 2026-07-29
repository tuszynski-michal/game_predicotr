"""Build the complete exact-image profile set from two accepted reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_grid_golden import (  # noqa: E402
    CellGridGoldenError,
    CellGridGoldenReview,
)
from game_predictor_worker.images.local_grid_calibration import (  # noqa: E402
    COMPLETE_PROFILE_SET_VERSION,
    LocalGridCalibrationError,
    build_local_profile_document,
    local_profile_document_bytes,
)
from game_predictor_worker.images.local_grid_review import (  # noqa: E402
    LocalGridCalibrationReview,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_V1_CROP_REPORT = ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_BASE_GOLDEN = ROOT / "ai_docs" / "quality" / "m5-cell-grid-golden.json"
DEFAULT_LOCAL_PROFILES = ROOT / "ai_docs" / "quality" / "m5-local-grid-calibration-profiles.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_CORRECTIVE_REVIEW = ROOT / "artifacts" / "m5-local-grid-review" / "reviewed-geometry.json"
DEFAULT_OUTPUT = ROOT / "ai_docs" / "quality" / "m5-complete-local-grid-profiles.json"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--v1-crop-report", type=Path, default=DEFAULT_V1_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--base-golden", type=Path, default=DEFAULT_BASE_GOLDEN)
    parser.add_argument("--local-profiles", type=Path, default=DEFAULT_LOCAL_PROFILES)
    parser.add_argument(
        "--detection-report",
        type=Path,
        default=DEFAULT_DETECTION_REPORT,
    )
    parser.add_argument(
        "--corrective-review",
        type=Path,
        default=DEFAULT_CORRECTIVE_REVIEW,
    )
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
        base_review = CellGridGoldenReview(
            repository_root=ROOT,
            manifest_path=args.manifest,
            annotations_path=args.annotations,
            crop_report_path=args.v1_crop_report,
            crop_root=args.crop_root,
            output_path=args.base_golden,
        )
        corrective_review = LocalGridCalibrationReview(
            repository_root=ROOT,
            manifest_path=args.manifest,
            annotations_path=args.annotations,
            crop_report_path=args.v1_crop_report,
            crop_root=args.crop_root,
            profiles_path=args.local_profiles,
            detection_report_path=args.detection_report,
            output_path=args.corrective_review,
        )
        if corrective_review.progress()["accepted"] != 25:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CORRECTIVE_REVIEW_INCOMPLETE",
                "All 25 corrective decisions are required.",
            )
        base_sources = {
            entry.candidate.source_image_checksum_sha256 for entry in base_review.golden.entries
        }
        missing_anchors = tuple(
            entry
            for entry in corrective_review.golden.entries
            if entry.candidate.source_image_checksum_sha256 not in base_sources
        )
        if len(missing_anchors) != 16:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CORRECTIVE_ANCHORS_INVALID",
                "Corrective review must add exactly 16 missing source anchors.",
            )
        combined = replace(
            base_review.golden,
            review_revision=(
                base_review.golden.review_revision + corrective_review.golden.review_revision
            ),
            entries=base_review.golden.entries + missing_anchors,
        )
        base_bytes = args.base_golden.read_bytes()
        corrective_bytes = args.corrective_review.read_bytes()
        detection_bytes = args.detection_report.read_bytes()
        manifest_bytes = args.manifest.read_bytes()
        document = build_local_profile_document(
            combined,
            golden_sha256=hashlib.sha256(base_bytes).hexdigest(),
            detector_report_sha256=hashlib.sha256(detection_bytes).hexdigest(),
            detection_report=json.loads(detection_bytes),
            corpus_manifest=json.loads(manifest_bytes),
            profile_set_version=COMPLETE_PROFILE_SET_VERSION,
        )
        document["correctiveReviewSha256"] = hashlib.sha256(corrective_bytes).hexdigest()
        document["heldoutAnchorCount"] = 0
        content = local_profile_document_bytes(document)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                raise LocalGridCalibrationError(
                    "LOCAL_GRID_COMPLETE_PROFILES_STALE",
                    "Complete local profiles are missing or stale.",
                )
        else:
            _write_atomic(args.output, content)
        missing_sources = document["missingSourceImageChecksums"]
        if not isinstance(missing_sources, list):
            raise LocalGridCalibrationError(
                "LOCAL_GRID_COMPLETE_PROFILE_BUILD_FAILED",
                "Missing-source list has an invalid contract.",
            )
        print(
            json.dumps(
                {
                    "missingSourceImageCount": len(missing_sources),
                    "output": str(args.output.resolve()),
                    "profileCount": document["profileCount"],
                    "profileSetVersion": document["profileSetVersion"],
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "status": document["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        CellGridGoldenError,
        LocalGridCalibrationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        code = getattr(error, "code", "LOCAL_GRID_COMPLETE_PROFILE_BUILD_FAILED")
        print(
            json.dumps({"code": code, "message": str(error), "status": "failed"}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
