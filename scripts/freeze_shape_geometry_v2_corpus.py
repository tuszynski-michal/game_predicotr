"""Freeze a local experimental shape-geometry corpus without touching application data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.shape_geometry_v2.corpus import (  # noqa: E402
    ShapeGeometryCorpusError,
    canonical_json_bytes,
    load_shape_geometry_corpus_manifest,
    verify_split_boundary,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--acceptance-manifest", type=Path)
    parser.add_argument("--boundary-output", type=Path)
    return parser.parse_args()


def _write_canonical(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
    temporary.replace(path)


def _require_identical(path: Path, payload: object) -> None:
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_INVENTORY_UNREADABLE",
            "Frozen inventory report cannot be read for --check.",
        ) from error
    if canonical_json_bytes(existing) != canonical_json_bytes(payload):
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_INVENTORY_DRIFT",
            "Frozen inventory report differs from the current corpus.",
        )


def main() -> int:
    args = _arguments()
    try:
        manifest = load_shape_geometry_corpus_manifest(args.manifest)
        report = manifest.freeze_inventory().as_dict()
        if args.check:
            _require_identical(args.output, report)
        else:
            _write_canonical(args.output, report)
        if args.acceptance_manifest is not None:
            if args.boundary_output is None:
                raise ShapeGeometryCorpusError(
                    "SHAPE_GEOMETRY_V2_BOUNDARY_OUTPUT_REQUIRED",
                    "--boundary-output is required with --acceptance-manifest.",
                )
            boundary = verify_split_boundary(
                manifest,
                load_shape_geometry_corpus_manifest(args.acceptance_manifest),
            )
            if args.check:
                _require_identical(args.boundary_output, boundary)
            else:
                _write_canonical(args.boundary_output, boundary)
    except ShapeGeometryCorpusError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
