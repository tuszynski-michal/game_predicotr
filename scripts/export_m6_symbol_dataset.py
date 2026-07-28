"""Build the M6 crop inventory or export reviewed symbol labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.calibrated_symbol_inventory import (  # noqa: E402
    build_calibrated_symbol_crop_inventory,
)
from game_predictor_worker.images.symbol_dataset import (  # noqa: E402
    SymbolDatasetError,
    export_reviewed_symbol_dataset,
)

QUALITY_ROOT = REPOSITORY_ROOT / "ai_docs" / "quality"
DEFAULT_CORPUS = QUALITY_ROOT / "m5-corpus-manifest.json"
DEFAULT_ANNOTATIONS = QUALITY_ROOT / "m5-golden-annotations.json"
DEFAULT_GRID_GOLDEN = QUALITY_ROOT / "m5-cell-grid-golden.json"
DEFAULT_PROFILES = QUALITY_ROOT / "m5-grid-calibration-profiles.json"
DEFAULT_CROP_REPORT = QUALITY_ROOT / "m5-board-cell-crops-v2-calibrated-report.json"
DEFAULT_QUALITY_REPORT = (
    QUALITY_ROOT / "m5-board-cell-crops-v2-calibrated-quality-report.json"
)
DEFAULT_CROP_ROOT = REPOSITORY_ROOT / "artifacts" / "m5-board-crops"
DEFAULT_INVENTORY = QUALITY_ROOT / "m6-symbol-crop-inventory-v2.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser(
        "inventory",
        help="Verify all M5 crops and produce stable sample IDs.",
    )
    inventory.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS)
    inventory.add_argument("--golden-annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    inventory.add_argument("--cell-grid-golden", type=Path, default=DEFAULT_GRID_GOLDEN)
    inventory.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    inventory.add_argument("--crop-report", type=Path, default=DEFAULT_CROP_REPORT)
    inventory.add_argument("--quality-report", type=Path, default=DEFAULT_QUALITY_REPORT)
    inventory.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    inventory.add_argument("--output", type=Path, default=DEFAULT_INVENTORY)
    inventory.add_argument("--check", action="store_true")

    export = subparsers.add_parser(
        "export",
        help="Materialize only explicitly reviewed symbol labels.",
    )
    export.add_argument("inventory", type=Path)
    export.add_argument("label_source", type=Path)
    export.add_argument("--crop-root", type=Path, required=True)
    export.add_argument("--artifact-root", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--check", action="store_true")
    export.add_argument(
        "--require-samples",
        action="store_true",
        help="Return exit code 1 when no accepted label was exported.",
    )
    return parser.parse_args()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _persist(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_REPORT_MISSING",
                "Expected report cannot be read.",
            ) from error
        if existing != content:
            raise SymbolDatasetError(
                "SYMBOL_DATASET_REPORT_DRIFT",
                "Expected report differs from current inputs.",
            )
        return
    _write_atomic(path, content)


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "inventory":
            inventory_report = build_calibrated_symbol_crop_inventory(
                args.corpus_manifest,
                args.golden_annotations,
                args.cell_grid_golden,
                args.profiles,
                args.crop_report,
                args.quality_report,
                args.crop_root,
            )
            content = inventory_report.to_json_bytes()
            _persist(args.output, content, check=args.check)
            print(
                json.dumps(
                    {
                        "inventorySha256": hashlib.sha256(content).hexdigest(),
                        "sampleCount": len(inventory_report.samples),
                        "status": "ready",
                    },
                    sort_keys=True,
                )
            )
            return 0

        export_report = export_reviewed_symbol_dataset(
            args.inventory,
            args.label_source,
            args.crop_root,
            args.artifact_root,
        )
        content = export_report.to_json_bytes()
        _persist(args.output, content, check=args.check)
        payload = export_report.to_dict()
        print(
            json.dumps(
                {
                    "assetCount": payload["assetCount"],
                    "datasetSha256": hashlib.sha256(content).hexdigest(),
                    "pendingCount": payload["pendingCount"],
                    "rejectedCount": payload["rejectedCount"],
                    "sampleCount": payload["sampleCount"],
                    "status": payload["status"],
                },
                sort_keys=True,
            )
        )
        if args.require_samples and not export_report.samples:
            return 1
        return 0
    except SymbolDatasetError as error:
        print(
            json.dumps(
                {"code": error.code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
