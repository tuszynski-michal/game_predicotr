"""Train or reproduce one validation-only M6 symbol benchmark candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch
import torchvision  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    SymbolClassifierError,
    TrainingConfig,
    logical_state_sha256,
    parameter_count,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_model_benchmark import (  # noqa: E402
    BENCHMARK_VERSION,
    SPATIAL_ARCHITECTURE_VERSION,
    SUPPORTED_VARIANTS,
    augmentation_version,
    train_validation_candidate,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report-v3.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report-v3.json"
DEFAULT_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v3"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=SUPPORTED_VARIANTS, required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_PATH_INVALID",
            "Benchmark artifacts must remain inside the repository.",
        ) from error


def _artifact_payload(
    *,
    variant: str,
    state_dict: dict[str, torch.Tensor],
    class_codes: tuple[str, ...],
    config: TrainingConfig,
    dataset_sha256: str,
    split_sha256: str,
) -> dict[str, object]:
    return {
        "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
        "augmentationVersion": augmentation_version(variant),
        "benchmarkVersion": BENCHMARK_VERSION,
        "candidateVariant": variant,
        "classCodes": list(class_codes),
        "config": {
            "inputSize": config.input_size,
            "seed": config.seed,
        },
        "datasetSha256": dataset_sha256,
        "splitSha256": split_sha256,
        "stateDict": state_dict,
    }


def _save_artifact(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        torch.save(payload, temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_artifact(path: Path) -> dict[str, Any]:
    try:
        payload: Any = torch.load(path, map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_INVALID",
            "The benchmark artifact cannot be read.",
        ) from error
    if not isinstance(payload, dict):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_INVALID",
            "The benchmark artifact must contain an object.",
        )
    return payload


def main() -> int:
    args = _args()
    try:
        config = TrainingConfig(epochs=args.epochs)
        data = prepare_training_data(args.dataset, args.split, args.asset_root)
        outcome = train_validation_candidate(data, config, args.variant)
        state = dict(outcome.state_dict)
        payload = _artifact_payload(
            variant=args.variant,
            state_dict=state,
            class_codes=data.class_codes,
            config=config,
            dataset_sha256=data.dataset_sha256,
            split_sha256=data.split_sha256,
        )
        if args.check:
            existing_payload = _load_artifact(args.artifact)
            existing_state = existing_payload.get("stateDict")
            if (
                not isinstance(existing_state, dict)
                or not all(
                    isinstance(name, str) and isinstance(value, torch.Tensor)
                    for name, value in existing_state.items()
                )
                or logical_state_sha256(existing_state)
                != logical_state_sha256(state)
                or {
                    key: existing_payload.get(key)
                    for key in payload
                    if key != "stateDict"
                }
                != {key: value for key, value in payload.items() if key != "stateDict"}
            ):
                raise SymbolClassifierError(
                    "SYMBOL_MODEL_BENCHMARK_ARTIFACT_DRIFT",
                    "The benchmark candidate differs from the reproduced checkpoint.",
                )
        else:
            _save_artifact(args.artifact, payload)
        artifact_content = args.artifact.read_bytes()
        artifact_sha256 = hashlib.sha256(artifact_content).hexdigest()
        report = {
            "architectureVersion": SPATIAL_ARCHITECTURE_VERSION,
            "artifact": {
                "logicalStateSha256": logical_state_sha256(state),
                "parameterCount": parameter_count(state),
                "relativePath": _relative(args.artifact),
                "sha256": artifact_sha256,
            },
            "augmentationVersion": augmentation_version(args.variant),
            "benchmarkVersion": BENCHMARK_VERSION,
            "bestEpoch": outcome.best_epoch,
            "candidateId": args.variant,
            "classes": list(data.class_codes),
            "config": asdict(config),
            "datasetSha256": data.dataset_sha256,
            "history": [dict(row) for row in outcome.history],
            "runtime": {
                "device": "cpu",
                "torchVersion": torch.__version__,
                "torchvisionVersion": torchvision.__version__,
            },
            "schemaVersion": 1,
            "splitSha256": data.split_sha256,
            "splitSeed": data.split_seed,
            "status": "validation_candidate",
            "trainingSampleCount": len(data.train),
            "validationMetrics": outcome.validation_metrics.to_dict(),
            "validationSampleCount": len(data.validation),
        }
        report_content = _json_bytes(report)
        if args.check:
            try:
                existing_report = args.report.read_bytes()
            except OSError as error:
                raise SymbolClassifierError(
                    "SYMBOL_MODEL_BENCHMARK_REPORT_MISSING",
                    "The expected benchmark report cannot be read.",
                ) from error
            if existing_report != report_content:
                raise SymbolClassifierError(
                    "SYMBOL_MODEL_BENCHMARK_REPORT_DRIFT",
                    "The validation-only report differs from the reproduced run.",
                )
        else:
            _write_atomic(args.report, report_content)
        print(
            json.dumps(
                {
                    "artifactSha256": artifact_sha256,
                    "bestEpoch": outcome.best_epoch,
                    "candidateId": args.variant,
                    "reportSha256": hashlib.sha256(report_content).hexdigest(),
                    "status": "validation_candidate",
                    "validationAccuracy": outcome.validation_metrics.accuracy,
                    "validationMacroRecall": outcome.validation_metrics.macro_recall,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, SymbolClassifierError) as error:
        code = (
            error.code
            if isinstance(error, SymbolClassifierError)
            else "SYMBOL_MODEL_BENCHMARK_IO_ERROR"
        )
        print(
            json.dumps(
                {"code": code, "message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
