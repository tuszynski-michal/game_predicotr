"""Generate the bundled M1.1 SQLite snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.snapshot import generate_snapshot  # noqa: E402


def main() -> None:
    asset_directory = REPOSITORY_ROOT / "apps" / "mobile" / "assets" / "snapshot"
    manifest = generate_snapshot(
        asset_directory / "m1-spike.db",
        asset_directory / "manifest.json",
    )
    print(
        "Generated snapshot "
        f"{manifest['releaseVersion']} "
        f"({manifest['recordCount']} records, "
        f"sha256={manifest['snapshotFileSha256']})."
    )


if __name__ == "__main__":
    main()
