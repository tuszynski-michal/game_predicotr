"""Train or reproduce the local M6 bootstrap symbol classifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPOSITORY_ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    ARCHITECTURE_VERSION,
    CLASSIFIER_VERSION,
    SymbolClassifierError,
    TrainingConfig,
    build_training_report,
    evaluate_classifier,
    logical_state_sha256,
    prepare_training_data,
    train_classifier,
    training_report_json_bytes,
)

QUALITY_ROOT = REPOSITORY_ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY_ROOT / "m6-symbol-dataset-export-report.json"
DEFAULT_SPLIT = QUALITY_ROOT / "m6-symbol-dataset-split-report.json"
DEFAULT_ASSET_ROOT = REPOSITORY_ROOT / "artifacts" / "m6-symbol-dataset-v1"
DEFAULT_ARTIFACT = (
    REPOSITORY_ROOT / "artifacts" / "m6-symbol-classifier-baseline" / "bootstrap-symbol-cnn-v1.pt"
)
DEFAULT_REPORT = QUALITY_ROOT / "m6-symbol-classifier-baseline-report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--check", action="store_true")
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


def _save_artifact(
    path: Path,
    state_dict: dict[str, torch.Tensor],
    class_codes: tuple[str, ...],
    config: TrainingConfig,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        torch.save(
            {
                "architectureVersion": ARCHITECTURE_VERSION,
                "classCodes": list(class_codes),
                "classifierVersion": CLASSIFIER_VERSION,
                "config": {
                    "inputSize": config.input_size,
                },
                "stateDict": state_dict,
            },
            temporary,
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_artifact_state(path: Path) -> dict[str, torch.Tensor]:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The existing model artifact cannot be verified.",
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("stateDict"), dict):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The existing model artifact has an invalid contract.",
        )
    raw_state = payload["stateDict"]
    if not all(
        isinstance(name, str) and isinstance(value, torch.Tensor)
        for name, value in raw_state.items()
    ):
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_INVALID",
            "The existing model state is invalid.",
        )
    state: dict[str, torch.Tensor] = {str(name): value for name, value in raw_state.items()}
    return state


def _relative_artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError as error:
        raise SymbolClassifierError(
            "SYMBOL_CLASSIFIER_ARTIFACT_PATH_INVALID",
            "The model artifact must remain inside the repository artifact root.",
        ) from error


def main() -> int:
    args = _parse_args()
    try:
        config = TrainingConfig(epochs=args.epochs)
        data = prepare_training_data(args.dataset, args.split, args.asset_root)
        outcome = train_classifier(data, config)
        test_metrics = evaluate_classifier(
            outcome.state_dict,
            data.test,
            config,
            data.class_codes,
        )
        state = dict(outcome.state_dict)
        if args.check:
            artifact_state = _load_artifact_state(args.artifact)
            if logical_state_sha256(artifact_state) != logical_state_sha256(state):
                raise SymbolClassifierError(
                    "SYMBOL_CLASSIFIER_ARTIFACT_DRIFT",
                    "The existing model state differs from the reproduced checkpoint.",
                )
        else:
            _save_artifact(args.artifact, state, data.class_codes, config)
        artifact_content = args.artifact.read_bytes()
        report = build_training_report(
            data,
            config,
            outcome,
            test_metrics,
            artifact_relative_path=_relative_artifact_path(args.artifact),
            artifact_sha256=hashlib.sha256(artifact_content).hexdigest(),
        )
        report_content = training_report_json_bytes(report)
        if args.check:
            try:
                existing_report = args.report.read_bytes()
            except OSError as error:
                raise SymbolClassifierError(
                    "SYMBOL_CLASSIFIER_REPORT_MISSING",
                    "The expected training report cannot be read.",
                ) from error
            if existing_report != report_content:
                raise SymbolClassifierError(
                    "SYMBOL_CLASSIFIER_REPORT_DRIFT",
                    "The training report differs from the reproduced run.",
                )
        else:
            _write_atomic(args.report, report_content)
        print(
            json.dumps(
                {
                    "bestEpoch": outcome.best_epoch,
                    "logicalStateSha256": logical_state_sha256(state),
                    "reportSha256": hashlib.sha256(report_content).hexdigest(),
                    "status": "bootstrap",
                    "testAccuracy": test_metrics.accuracy,
                    "testMacroRecall": test_metrics.macro_recall,
                    "validationAccuracy": outcome.validation_metrics.accuracy,
                    "validationMacroRecall": outcome.validation_metrics.macro_recall,
                },
                sort_keys=True,
            )
        )
        return 0
    except SymbolClassifierError as error:
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
