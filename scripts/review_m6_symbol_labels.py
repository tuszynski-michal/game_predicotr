"""Run the loopback-only M6 bootstrap symbol label review tool."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from game_predictor_worker.images.symbol_review import (
    BootstrapSymbolReview,
    SymbolReviewError,
)
from game_predictor_worker.images.symbol_review_http import (
    SymbolReviewHttpError,
    create_review_server,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "ai_docs" / "quality" / "m6-symbol-crop-inventory-v2.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_LABEL_OUTPUT = ROOT / "artifacts" / "m6-symbol-review" / "reviewed-labels.json"
STATIC_ROOT = ROOT / "scripts" / "m6_symbol_review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review M5 cell crops and create reviewed-cell-labels-v1.",
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_LABEL_OUTPUT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the default browser automatically.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        review = BootstrapSymbolReview(
            args.inventory,
            args.crop_root,
            args.output,
            require_calibrated=True,
        )
        server = create_review_server(
            review,
            STATIC_ROOT,
            host=args.host,
            port=args.port,
        )
    except (OSError, SymbolReviewError, SymbolReviewHttpError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    bound_host, port = server.server_address[:2]
    host = bound_host.decode() if isinstance(bound_host, bytes) else bound_host
    url = f"http://{host}:{port}/"
    print("M6 symbol review is ready.")
    print(f"Open: {url}")
    print(f"Labels: {review.label_output_path}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping M6 symbol review.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
