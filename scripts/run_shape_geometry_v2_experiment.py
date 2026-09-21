"""Run or replay-check a read-only shape-geometry v2 G01 experiment."""

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
    load_manual_annotations,
    load_shape_geometry_corpus_manifest,
    require_current_inventory,
)
from game_predictor_worker.images.shape_geometry_v2.experiment import (  # noqa: E402
    load_shape_geometry_experiment_observations,
    require_matching_experiment,
    run_shape_geometry_experiment,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
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
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_UNREADABLE",
            "Experiment report cannot be read for --check.",
        ) from error
    if not isinstance(raw, dict):
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_UNREADABLE",
            "Experiment report must be an object.",
        )
    return raw


def main() -> int:
    args = _arguments()
    try:
        manifest = load_shape_geometry_corpus_manifest(args.manifest)
        if manifest.visibility is not CorpusVisibility.EXECUTOR:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
                "Experiment cannot read an acceptance corpus.",
            )
        inventory = require_current_inventory(manifest, load_inventory_report(args.inventory))
        annotations = load_manual_annotations(args.annotations, manifest)
        observations = load_shape_geometry_experiment_observations(args.observations)
        report = run_shape_geometry_experiment(manifest, inventory, annotations, observations)
        if args.check:
            require_matching_experiment(_load_report(args.output), report)
        else:
            _write_canonical(args.output, report)
    except ShapeGeometryCorpusError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
