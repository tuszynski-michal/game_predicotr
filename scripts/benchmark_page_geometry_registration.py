"""Read-only benchmark for verified page registration on a managed import.

Run from the repository root, for example::

    .venv\\Scripts\\python.exe scripts\\benchmark_page_geometry_registration.py \
        --game-id 80f3c7ec-6110-4e20-a263-2675ee5b15d6 \
        --job-id b0575f5f-8ec1-46d6-8262-8ef0309055c7 \
        --source seq_64-72.jpg --source seq_91-99.jpg

It reads the active reviewed geometry profile and managed originals, writes no
database rows or artifacts, and emits a compact JSON report.  It is intended
for the real-photo regression gate before a full browser-staging preflight.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
from uuid import UUID

import numpy as np
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_worker.images.page_geometry_registration import VerifiedPageRegistrar
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument("--job-id", required=True, type=UUID)
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument(
        "--first",
        type=int,
        help="Benchmark the first N managed sources in their attested sequence order.",
    )
    parser.add_argument("--artifact-root", default="artifacts", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def _rgb(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as image:
            image.load()
            return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise RuntimeError(f"Cannot read managed source {path}.") from error


def main() -> int:
    arguments = _arguments()
    if not 1 <= arguments.workers <= 8:
        raise RuntimeError("--workers must be between 1 and 8.")
    if bool(arguments.sources) == (arguments.first is not None):
        raise RuntimeError("Pass exactly one of --source or --first.")
    if arguments.first is not None and arguments.first < 1:
        raise RuntimeError("--first must be positive.")
    root = arguments.artifact_root.resolve()
    database_url = os.environ.get(
        "GAME_PREDICTOR_DATABASE_URL",
        "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor",
    )
    with Session(create_engine(database_url)) as session:
        snapshot = SqlAlchemyGridProfileSnapshotResolver(session).resolve(game_id=arguments.game_id)
    profile = snapshot.get("pageRegistrationProfile")
    if not isinstance(profile, Mapping):
        raise RuntimeError("The active game has no valid reviewed page-registration profile.")
    manifest_path = root / "data" / "originals" / "manifests" / f"{arguments.job_id}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise RuntimeError("Managed originals manifest is not an object.")
    originals = manifest.get("originals")
    if not isinstance(originals, list):
        raise RuntimeError("Managed originals manifest has no originals list.")
    by_name: dict[str, dict[str, object]] = {}
    for raw in originals:
        if not isinstance(raw, dict):
            continue
        path = raw.get("sourceRelativePath")
        if isinstance(path, str):
            by_name[path.rsplit("/", 1)[-1]] = raw

    def load_checksum(checksum: str) -> np.ndarray:
        return _rgb(root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg")

    started = time.perf_counter()
    registrar = VerifiedPageRegistrar(profile, load_anchor_rgb=load_checksum)
    initialization_seconds = time.perf_counter() - started
    print(
        json.dumps(
            {
                "anchorCount": len(profile.get("anchors", [])),
                "initializationSeconds": round(initialization_seconds, 6),
                "phase": "registration",
            },
            sort_keys=True,
        ),
        flush=True,
    )

    if arguments.first is not None:
        selected_names: list[str] = []
        for raw in originals[: arguments.first]:
            if not isinstance(raw, dict):
                continue
            path = raw.get("sourceRelativePath")
            if isinstance(path, str):
                selected_names.append(path.rsplit("/", 1)[-1])
        if len(selected_names) != arguments.first:
            raise RuntimeError("Managed originals manifest contains an invalid source path.")
    else:
        selected_names = cast(list[str], arguments.sources)

    def benchmark_source(name: str) -> dict[str, object]:
        raw = by_name.get(name)
        if raw is None or not isinstance(raw.get("checksumSha256"), str):
            raise RuntimeError(f"The managed manifest has no source named {name}.")
        source_started = time.perf_counter()
        checksum = cast(str, raw["checksumSha256"])
        result = registrar.register(load_checksum(checksum))
        return {
            "inlierCount": None if result is None else result.inlier_count,
            "minimumBoardRedEdgeCoverage": (
                None if result is None else round(min(result.board_red_edge_coverages), 6)
            ),
            "registered": result is not None,
            "seconds": round(time.perf_counter() - source_started, 6),
            "source": name,
        }

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        results = list(executor.map(benchmark_source, selected_names))
    registration_seconds = time.perf_counter() - started
    print(
        json.dumps(
            {
                "anchorCount": len(profile.get("anchors", [])),
                "initializationSeconds": round(initialization_seconds, 6),
                "registrationSeconds": round(registration_seconds, 6),
                "results": results,
                "workers": arguments.workers,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
