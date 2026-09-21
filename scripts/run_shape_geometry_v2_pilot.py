"""Run or replay-check a local, non-publishing shape-geometry v2 G05 pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "api" / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.shape_geometry_v2.corpus import (  # noqa: E402
    CorpusVisibility,
    ShapeGeometryCorpusError,
    canonical_json_bytes,
    load_inventory_report,
    load_manual_annotations,
    load_shape_geometry_corpus_manifest,
    require_current_inventory,
)
from game_predictor_worker.images.shape_geometry_v2.pilot import (  # noqa: E402
    ShapeGeometryPilotError,
    load_shape_geometry_pilot_input,
    require_matching_shape_geometry_pilot,
    run_shape_geometry_pilot,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _write_canonical(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
    temporary.replace(path)


def _load_report(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryPilotError(
            "SHAPE_GEOMETRY_V2_PILOT_UNREADABLE", "Pilot report cannot be read for --check."
        ) from error
    if not isinstance(raw, dict):
        raise ShapeGeometryPilotError(
            "SHAPE_GEOMETRY_V2_PILOT_UNREADABLE", "Pilot report must be an object."
        )
    return raw


def main() -> int:
    args = _arguments()
    try:
        manifest = load_shape_geometry_corpus_manifest(args.manifest)
        if manifest.visibility is not CorpusVisibility.EXECUTOR:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
                "Pilot cannot read an acceptance corpus.",
            )
        inventory = require_current_inventory(manifest, load_inventory_report(args.inventory))
        annotations = load_manual_annotations(args.annotations, manifest)
        pilot = load_shape_geometry_pilot_input(args.pilot)
        result = run_shape_geometry_pilot(manifest, inventory, annotations, pilot)
        if args.check:
            require_matching_shape_geometry_pilot(_load_report(args.output), result)
        else:
            _write_canonical(args.output, result.as_dict())
    except (ShapeGeometryCorpusError, ShapeGeometryPilotError) as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
