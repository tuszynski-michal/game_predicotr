"""Run the local Admin API on its validated loopback address."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from game_predictor_api.config import get_settings


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Admin API.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload after Python source changes (development only).",
    )
    arguments = parser.parse_args(argv)
    settings = get_settings()
    uvicorn.run(
        "game_predictor_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=arguments.reload,
        reload_dirs=([str(Path(__file__).resolve().parents[1])] if arguments.reload else None),
    )


if __name__ == "__main__":
    main()
