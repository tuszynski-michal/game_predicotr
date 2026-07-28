"""Prepare, review and report the independent M5 cell-grid golden set."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from game_predictor_worker.images.cell_grid_golden import (
    CellGridGoldenError,
    CellGridGoldenReview,
    baseline_report_bytes,
)
from game_predictor_worker.images.cell_grid_review_http import (
    CellGridReviewHttpError,
    create_cell_grid_review_server,
)
from game_predictor_worker.images.grid_calibration import (
    GridCalibrationError,
    GridCalibrationProfiles,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = ROOT / "ai_docs" / "quality" / "m5-golden-annotations.json"
DEFAULT_CROP_REPORT = ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-report.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_GOLDEN = ROOT / "ai_docs" / "quality" / "m5-cell-grid-golden.json"
DEFAULT_BASELINE = ROOT / "ai_docs" / "quality" / "m5-cell-grid-v1-baseline-report.json"
DEFAULT_PROFILES = ROOT / "ai_docs" / "quality" / "m5-grid-calibration-profiles.json"
STATIC_ROOT = ROOT / "scripts" / "m5_cell_grid_review"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the independent 5x3 cell-grid golden review.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--crop-report", type=Path, default=DEFAULT_CROP_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "prepare",
        help="Create or revalidate the deterministic 27-board review selection.",
    )
    serve = subparsers.add_parser("serve", help="Run the loopback review UI.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the default browser automatically.",
    )
    report = subparsers.add_parser(
        "report",
        help="Generate the rejected-v1 baseline after all boards are accepted.",
    )
    report.add_argument("--output", type=Path, default=DEFAULT_BASELINE)
    report.add_argument(
        "--check",
        action="store_true",
        help="Verify that the existing report is current without writing it.",
    )
    return parser


def _review(args: argparse.Namespace) -> CellGridGoldenReview:
    return CellGridGoldenReview(
        repository_root=ROOT,
        manifest_path=args.manifest,
        annotations_path=args.annotations,
        crop_report_path=args.crop_report,
        crop_root=args.crop_root,
        output_path=args.golden,
    )


def _write_if_changed(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _prepare(args: argparse.Namespace) -> int:
    review = _review(args)
    progress = review.progress()
    print("Independent cell-grid review selection is valid.")
    print(f"Golden: {review.output_path}")
    print(
        "Progress: "
        f"{progress['accepted']}/{progress['total']} accepted, "
        f"{progress['pending']} pending."
    )
    return 0


def _serve(args: argparse.Namespace) -> int:
    review = _review(args)
    GridCalibrationProfiles.from_files(args.profiles, args.manifest)
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
    print("Independent M5 cell-grid review is ready.")
    print(f"Open: {url}")
    print(f"Golden: {review.output_path}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping M5 cell-grid review.")
    finally:
        server.server_close()
    return 0


def _report(args: argparse.Namespace) -> int:
    review = _review(args)
    content = baseline_report_bytes(review)
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_bytes() != content:
            print("ERROR: cell-grid v1 baseline report is missing or stale.", file=sys.stderr)
            return 1
        print(f"Cell-grid v1 baseline report is current: {output}")
        return 0
    changed = _write_if_changed(output, content)
    print(f"Cell-grid v1 baseline report {'written' if changed else 'unchanged'}: {output}")
    return 0


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "prepare":
            return _prepare(args)
        if args.command == "serve":
            return _serve(args)
        if args.command == "report":
            return _report(args)
    except (
        CellGridGoldenError,
        CellGridReviewHttpError,
        GridCalibrationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        code = getattr(error, "code", "CELL_GRID_COMMAND_FAILED")
        print(f"ERROR [{code}]: {error}", file=sys.stderr)
        return 1
    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
