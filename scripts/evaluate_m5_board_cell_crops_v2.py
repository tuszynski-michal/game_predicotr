"""Evaluate detector-driven board-cell-crops-v2 against the accepted golden."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_grid_golden import (  # noqa: E402
    CellGridGoldenError,
    CellGridGoldenReview,
)
from game_predictor_worker.images.cell_grid_v2_quality import (  # noqa: E402
    CellGridV2QualityError,
    v2_quality_report_bytes,
)

DEFAULT_MANIFEST = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_V1_CROP_REPORT = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = REPOSITORY_ROOT / "artifacts" / "m5-board-crops"
DEFAULT_GOLDEN = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-cell-grid-golden.json"
DEFAULT_V2_CROP_REPORT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v2-report.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v2-quality-report.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--v1-crop-report", type=Path, default=DEFAULT_V1_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--v2-crop-report", type=Path, default=DEFAULT_V2_CROP_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the current deterministic quality report already exists.",
    )
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="Return exit code 1 when v2 remains outside the accepted quality budget.",
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


def main() -> int:
    args = _parse_args()
    try:
        review = CellGridGoldenReview(
            repository_root=REPOSITORY_ROOT,
            manifest_path=args.manifest,
            annotations_path=args.annotations,
            crop_report_path=args.v1_crop_report,
            crop_root=args.crop_root,
            output_path=args.golden,
        )
        content = v2_quality_report_bytes(
            review,
            crop_report_path=args.v2_crop_report,
            crop_root=args.crop_root,
        )
        payload = json.loads(content)
        output = args.output.resolve()
        if output == args.crop_root.resolve() or output.is_relative_to(args.crop_root.resolve()):
            raise CellGridV2QualityError(
                "CELL_GRID_V2_QUALITY_REPORT_IN_ARTIFACT_ROOT",
                "The quality report must stay outside immutable crop artifacts.",
            )
        if args.check:
            try:
                existing = output.read_bytes()
            except OSError as error:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_QUALITY_REPORT_MISSING",
                    "Expected v2 quality report cannot be read.",
                ) from error
            if existing != content:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_QUALITY_REPORT_DRIFT",
                    "The v2 quality report differs from current artifacts.",
                )
        else:
            _write_atomic(output, content)
        print(
            json.dumps(
                {
                    "lineP95Px": payload["summary"]["overall"]["p95AbsoluteErrorPx"],
                    "nextTask": payload["nextTask"],
                    "reportSha256": hashlib.sha256(content).hexdigest(),
                    "status": payload["status"],
                    "trainingAllowed": payload["trainingAllowed"],
                },
                sort_keys=True,
            )
        )
        if args.require_pass and not payload["trainingAllowed"]:
            return 1
        return 0
    except (CellGridGoldenError, CellGridV2QualityError, OSError) as error:
        code = getattr(error, "code", "CELL_GRID_V2_QUALITY_IO_FAILED")
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
