"""Run or replay-check a bounded, read-only v1.1 geometry baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.shape_geometry_v2.corpus import (  # noqa: E402
    CorpusVisibility,
    ShapeGeometryCorpusError,
    canonical_json_bytes,
    load_inventory_report,
    load_shape_geometry_corpus_manifest,
    require_current_inventory,
    require_matching_baseline,
    run_v11_baseline,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--max-sources-per-game", type=int, default=10)
    return parser.parse_args()


def _write_canonical(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
    temporary.replace(path)


def _load_baseline(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_V11_BASELINE_UNREADABLE",
            "Baseline report cannot be read for --check.",
        ) from error
    if not isinstance(raw, dict):
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_V11_BASELINE_UNREADABLE",
            "Baseline report must be an object.",
        )
    return raw


def main() -> int:
    args = _arguments()
    try:
        manifest = load_shape_geometry_corpus_manifest(args.manifest)
        if manifest.visibility is not CorpusVisibility.EXECUTOR:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
                "Baseline cannot read an acceptance corpus.",
            )
        inventory = require_current_inventory(manifest, load_inventory_report(args.inventory))
        baseline = run_v11_baseline(
            manifest,
            inventory,
            max_sources_per_game=args.max_sources_per_game,
        )
        if args.check:
            require_matching_baseline(_load_baseline(args.output), baseline)
        else:
            _write_canonical(args.output, baseline)
    except ShapeGeometryCorpusError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
