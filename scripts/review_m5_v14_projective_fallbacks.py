"""Prepare and serve the 14 v14 full-preflight fallback boards."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_grid_golden import CellGridGoldenError  # noqa: E402
from game_predictor_worker.images.cell_grid_review_http import (  # noqa: E402
    CellGridReviewHttpError,
    create_cell_grid_review_server,
)
from game_predictor_worker.images.v14_projective_fallback_review import (  # noqa: E402
    V14ProjectiveFallbackReview,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_V1_CROP_REPORT = ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_PREFLIGHT_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-global-bbox-fallback-v14-full-preflight-report.json"
)
DEFAULT_OUTPUT = ROOT / "artifacts" / "m5-v14-projective-fallback-review" / "reviewed-geometry.json"
STATIC_ROOT = ROOT / "scripts" / "m5_cell_grid_review"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--v1-crop-report", type=Path, default=DEFAULT_V1_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--preflight-report", type=Path, default=DEFAULT_PREFLIGHT_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8891)
    serve.add_argument("--no-open", action="store_true")
    return parser


def _review(args: argparse.Namespace) -> V14ProjectiveFallbackReview:
    return V14ProjectiveFallbackReview(
        repository_root=ROOT,
        manifest_path=args.manifest,
        annotations_path=args.annotations,
        crop_report_path=args.v1_crop_report,
        crop_root=args.crop_root,
        preflight_report_path=args.preflight_report,
        output_path=args.output,
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        review = _review(args)
        if args.command == "prepare":
            print(json.dumps({**review.progress(), "output": str(review.output_path)}))
            return 0
        server = create_cell_grid_review_server(
            review,
            STATIC_ROOT,
            host=args.host,
            port=args.port,
        )
        bound_host, bound_port = server.server_address[:2]
        host = bound_host.decode() if isinstance(bound_host, bytes) else str(bound_host)
        url = f"http://{host}:{bound_port}/"
        print(f"V14 fallback review is ready: {url}")
        print(f"Review: {review.output_path}")
        print("Press Ctrl+C to stop.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            print("\nStopping v14 fallback review.")
        finally:
            server.server_close()
        return 0
    except (CellGridGoldenError, CellGridReviewHttpError, OSError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "V14_FALLBACK_REVIEW_FAILED")
        print(
            json.dumps({"code": code, "message": str(error), "status": "failed"}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
