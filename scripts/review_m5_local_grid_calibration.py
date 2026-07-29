"""Prepare and serve missing-anchor plus held-out local geometry review."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_grid_golden import (  # noqa: E402
    CellGridGoldenError,
)
from game_predictor_worker.images.cell_grid_review_http import (  # noqa: E402
    CellGridReviewHttpError,
    create_cell_grid_review_server,
)
from game_predictor_worker.images.local_grid_review import (  # noqa: E402
    LocalGridCalibrationReview,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_V1_CROP_REPORT = ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_PROFILES = ROOT / "ai_docs" / "quality" / "m5-local-grid-calibration-profiles.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "m5-local-grid-review" / "reviewed-geometry.json"
STATIC_ROOT = ROOT / "scripts" / "m5_cell_grid_review"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--v1-crop-report", type=Path, default=DEFAULT_V1_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--detection-report", type=Path, default=DEFAULT_DETECTION_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8879)
    serve.add_argument("--no-open", action="store_true")
    return parser


def _review(args: argparse.Namespace) -> LocalGridCalibrationReview:
    return LocalGridCalibrationReview(
        repository_root=ROOT,
        manifest_path=args.manifest,
        annotations_path=args.annotations,
        crop_report_path=args.v1_crop_report,
        crop_root=args.crop_root,
        profiles_path=args.profiles,
        detection_report_path=args.detection_report,
        output_path=args.output,
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        review = _review(args)
        if args.command == "prepare":
            state = review.state(status="all", limit=100)
            samples = state["samples"]
            assert isinstance(samples, list)
            missing = sum(sample.get("purpose") == "missing_anchor" for sample in samples)
            heldout = sum(sample.get("purpose") == "heldout" for sample in samples)
            print(
                json.dumps(
                    {
                        "accepted": review.progress()["accepted"],
                        "heldoutCount": heldout,
                        "missingAnchorCount": missing,
                        "output": str(review.output_path),
                        "pending": review.progress()["pending"],
                        "total": review.progress()["total"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "serve":
            profile_document = json.loads(args.profiles.read_bytes())
            server = create_cell_grid_review_server(
                review,
                STATIC_ROOT,
                host=args.host,
                port=args.port,
                calibration_profiles=profile_document,
            )
            bound_host, bound_port = server.server_address[:2]
            host = bound_host.decode() if isinstance(bound_host, bytes) else str(bound_host)
            url = f"http://{host}:{bound_port}/"
            print(f"Local image calibration review is ready: {url}")
            print(f"Review: {review.output_path}")
            print("Press Ctrl+C to stop.")
            if not args.no_open:
                webbrowser.open(url)
            try:
                server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:
                print("\nStopping local image calibration review.")
            finally:
                server.server_close()
            return 0
    except (
        CellGridGoldenError,
        CellGridReviewHttpError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        code = getattr(error, "code", "LOCAL_GRID_REVIEW_FAILED")
        print(
            json.dumps(
                {"code": code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
