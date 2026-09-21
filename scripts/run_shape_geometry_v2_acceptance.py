"""Run or replay-check a local shared shape-geometry v2 G08 acceptance report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "api" / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.shape_geometry_v2.acceptance import (  # noqa: E402
    ShapeGeometryAcceptanceError,
    load_shape_geometry_v2_acceptance_input,
    require_matching_shape_geometry_v2_acceptance,
    run_shape_geometry_v2_acceptance,
)
from game_predictor_worker.images.shape_geometry_v2.corpus import (  # noqa: E402
    ShapeGeometryCorpusError,
    canonical_json_bytes,
    load_inventory_report,
    load_shape_geometry_corpus_manifest,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-manifest", type=Path)
    parser.add_argument("--executor-inventory", type=Path)
    parser.add_argument("--acceptance-manifest", type=Path)
    parser.add_argument("--acceptance-inventory", type=Path)
    parser.add_argument("--frozen-input", type=Path)
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
        raise ShapeGeometryAcceptanceError(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_UNREADABLE",
            "Acceptance report cannot be read for --check.",
        ) from error
    if not isinstance(raw, dict):
        raise ShapeGeometryAcceptanceError(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_UNREADABLE",
            "Acceptance report must be an object.",
        )
    return raw


def _provided_arguments(args: argparse.Namespace) -> tuple[Path | None, ...]:
    return (
        args.executor_manifest,
        args.executor_inventory,
        args.acceptance_manifest,
        args.acceptance_inventory,
        args.frozen_input,
    )


def main() -> int:
    args = _arguments()
    provided = _provided_arguments(args)
    try:
        if any(value is not None for value in provided):
            if any(value is None for value in provided):
                raise ShapeGeometryAcceptanceError(
                    "SHAPE_GEOMETRY_V2_ACCEPTANCE_ARGUMENTS_INCOMPLETE",
                    "All acceptance artifacts must be supplied together.",
                )
            result = run_shape_geometry_v2_acceptance(
                executor_manifest=load_shape_geometry_corpus_manifest(args.executor_manifest),
                executor_inventory=load_inventory_report(args.executor_inventory),
                acceptance_manifest=load_shape_geometry_corpus_manifest(args.acceptance_manifest),
                acceptance_inventory=load_inventory_report(args.acceptance_inventory),
                frozen_input=load_shape_geometry_v2_acceptance_input(args.frozen_input),
            )
        else:
            result = run_shape_geometry_v2_acceptance()
        if args.check:
            require_matching_shape_geometry_v2_acceptance(_load_report(args.output), result)
        else:
            _write_canonical(args.output, result.as_dict())
    except (ShapeGeometryAcceptanceError, ShapeGeometryCorpusError) as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
