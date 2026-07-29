"""Build or verify the source-disjoint TASK-0099 suggestion report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    SymbolClassifierError,
    load_classifier_artifact,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_suggestions import (  # noqa: E402
    DEFAULT_MINIMUM_SIMILARITY,
    SUGGESTION_VERSION,
    SymbolSuggestionError,
    evaluate_validation_suggestions,
    suggestion_report_json_bytes,
    validate_classifier_provenance,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report.json"
DEFAULT_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v1"
DEFAULT_ARTIFACT = (
    ROOT / "artifacts" / "m6-symbol-classifier-baseline" / "bootstrap-symbol-cnn-v1.pt"
)
DEFAULT_CLASSIFIER_REPORT = QUALITY / "m6-symbol-classifier-baseline-report.json"
DEFAULT_REPORT = QUALITY / "m6-symbol-suggestion-validation-report.json"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument(
        "--classifier-report",
        type=Path,
        default=DEFAULT_CLASSIFIER_REPORT,
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
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


def main() -> int:
    args = _args()
    try:
        data = prepare_training_data(args.dataset, args.split, args.asset_root)
        validate_classifier_provenance(
            args.classifier_report,
            args.artifact,
            data,
        )
        model, class_codes, input_size = load_classifier_artifact(args.artifact)
        if class_codes != data.class_codes:
            raise SymbolSuggestionError(
                "SYMBOL_SUGGESTION_CLASS_DRIFT",
                "Classifier classes differ from the approved dataset.",
            )
        metrics = evaluate_validation_suggestions(
            model,
            data,
            input_size,
            minimum_similarity=DEFAULT_MINIMUM_SIMILARITY,
        )
        train_sources = {sample.source_image_checksum for sample in data.train}
        validation_sources = {sample.source_image_checksum for sample in data.validation}
        metrics["sameSourceLeakageCount"] = len(train_sources & validation_sources)
        report: dict[str, object] = {
            "artifactSha256": hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
            "datasetSha256": data.dataset_sha256,
            "minimumCosineSimilarity": DEFAULT_MINIMUM_SIMILARITY,
            "qualityGate": {
                "noAutomaticMutation": True,
                "sourceImageLeakageCount": len(train_sources & validation_sources),
                "status": "passed" if not train_sources & validation_sources else "failed",
            },
            "referencePartition": "train",
            "schemaVersion": 1,
            "splitSha256": data.split_sha256,
            "status": "bootstrap",
            "suggestionVersion": SUGGESTION_VERSION,
            "validationMetrics": metrics,
        }
        content = suggestion_report_json_bytes(report)
        if args.check:
            if args.report.read_bytes() != content:
                raise SymbolSuggestionError(
                    "SYMBOL_SUGGESTION_REPORT_DRIFT",
                    "The committed suggestion report differs from evaluation.",
                )
        else:
            _write_atomic(args.report, content)
        print(
            json.dumps(
                {
                    "coverage": metrics["coverage"],
                    "reportSha256": hashlib.sha256(content).hexdigest(),
                    "status": "passed",
                    "top1AccuracyAtCoverage": metrics["top1AccuracyAtCoverage"],
                    "top3AccuracyAtCoverage": metrics["top3AccuracyAtCoverage"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, SymbolClassifierError, SymbolSuggestionError) as error:
        code = getattr(error, "code", "SYMBOL_SUGGESTION_IO_ERROR")
        print(
            json.dumps({"code": code, "message": str(error), "status": "failed"}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
