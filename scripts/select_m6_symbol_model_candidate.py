"""Select on validation only, then test exactly one frozen M6 model candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))

from game_predictor_worker.images.symbol_classifier import (  # noqa: E402
    ARCHITECTURE_VERSION,
    EvaluationMetrics,
    SymbolClassifierError,
    TrainingConfig,
    evaluate_classifier,
    load_classifier_artifact,
    prepare_training_data,
)
from game_predictor_worker.images.symbol_model_benchmark import (  # noqa: E402
    BENCHMARK_VERSION,
    SPATIAL_ARCHITECTURE_VERSION,
    ValidationCandidate,
    build_benchmark_model,
    evaluate_benchmark_model,
    select_validation_candidate,
)

QUALITY = ROOT / "ai_docs" / "quality"
DEFAULT_DATASET = QUALITY / "m6-symbol-dataset-export-report-v3.json"
DEFAULT_SPLIT = QUALITY / "m6-symbol-dataset-split-report-v3.json"
DEFAULT_ASSETS = ROOT / "artifacts" / "m6-symbol-dataset-v3"
CONTROL_CANDIDATE_ID = "control_v3"
SELECTION_VERSION = "symbol-model-validation-selection-v1"
TEST_REPORT_VERSION = "symbol-model-selected-test-v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    select = subparsers.add_parser("select")
    select.add_argument("--control-report", type=Path, required=True)
    select.add_argument("--candidate-report", type=Path, action="append", required=True)
    select.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    select.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--check", action="store_true")

    test = subparsers.add_parser("test")
    test.add_argument("--selection", type=Path, required=True)
    test.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    test.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    test.add_argument("--asset-root", type=Path, default=DEFAULT_ASSETS)
    test.add_argument("--output", type=Path, required=True)
    test.add_argument("--check", action="store_true")
    return parser.parse_args()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _load(path: Path) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"Cannot read {path.name}.",
        ) from error
    if not isinstance(value, Mapping):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{path.name} must contain an object.",
        )
    return content, value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{label} must be an object.",
        )
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{label} must be an array.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{label} must be numeric.",
        )
    return float(value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_REPORT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _metrics(value: object, label: str) -> EvaluationMetrics:
    row = _mapping(value, label)
    matrix = tuple(
        tuple(_integer(cell, f"{label}.confusionMatrix") for cell in _sequence(raw, label))
        for raw in _sequence(row.get("confusionMatrix"), f"{label}.confusionMatrix")
    )
    per_class = tuple(
        dict(_mapping(raw, f"{label}.perClass"))
        for raw in _sequence(row.get("perClass"), f"{label}.perClass")
    )
    return EvaluationMetrics(
        loss=_number(row.get("loss"), f"{label}.loss"),
        accuracy=_number(row.get("accuracy"), f"{label}.accuracy"),
        macro_recall=_number(row.get("macroRecall"), f"{label}.macroRecall"),
        confusion_matrix=matrix,
        per_class=per_class,
    )


def _safe_repository_path(relative_value: object) -> Path:
    relative = PurePosixPath(_text(relative_value, "artifact.relativePath"))
    if relative.is_absolute() or ".." in relative.parts:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_PATH_INVALID",
            "Artifact path must remain below the repository.",
        )
    resolved = ROOT.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as error:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_PATH_INVALID",
            "Artifact path escapes the repository.",
        ) from error
    return resolved


def _candidate_row(
    *,
    candidate_id: str,
    report_path: Path,
    report: Mapping[str, object],
    report_bytes: bytes,
    expected_dataset_sha256: str,
    expected_split_sha256: str,
    control: bool,
) -> tuple[ValidationCandidate, dict[str, object]]:
    if (
        report.get("datasetSha256") != expected_dataset_sha256
        or report.get("splitSha256") != expected_split_sha256
    ):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_PROVENANCE_DRIFT",
            "Candidate dataset or split differs from the frozen benchmark inputs.",
        )
    if not control and ("testMetrics" in report or "testSampleCount" in report):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_TEST_LEAKAGE",
            "Validation candidate reports cannot contain test metrics.",
        )
    if control:
        if report.get("status") != "bootstrap":
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_CONTROL_INVALID",
                "The historical control report is invalid.",
            )
        architecture_version = _text(
            report.get("architectureVersion"),
            "control.architectureVersion",
        )
        augmentation = "none"
    else:
        if (
            report.get("status") != "validation_candidate"
            or report.get("benchmarkVersion") != BENCHMARK_VERSION
            or report.get("candidateId") != candidate_id
        ):
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_CANDIDATE_INVALID",
                "A validation candidate report is invalid.",
            )
        architecture_version = _text(
            report.get("architectureVersion"),
            "candidate.architectureVersion",
        )
        augmentation = _text(
            report.get("augmentationVersion"),
            "candidate.augmentationVersion",
        )
    artifact = _mapping(report.get("artifact"), "artifact")
    artifact_path = _safe_repository_path(artifact.get("relativePath"))
    try:
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError as error:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_MISSING",
            "A candidate artifact cannot be read.",
        ) from error
    if artifact_sha256 != artifact.get("sha256"):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_DRIFT",
            "A candidate artifact checksum differs from its report.",
        )
    metrics = _metrics(report.get("validationMetrics"), "validationMetrics")
    parameter_count = _integer(artifact.get("parameterCount"), "artifact.parameterCount")
    candidate = ValidationCandidate(candidate_id, metrics, parameter_count)
    return candidate, {
        "architectureVersion": architecture_version,
        "artifact": {
            "parameterCount": parameter_count,
            "relativePath": artifact_path.relative_to(ROOT).as_posix(),
            "sha256": artifact_sha256,
        },
        "augmentationVersion": augmentation,
        "candidateId": candidate_id,
        "reportPath": report_path.resolve().relative_to(ROOT.resolve()).as_posix(),
        "reportSha256": hashlib.sha256(report_bytes).hexdigest(),
        "validationMetrics": metrics.to_dict(),
    }


def _persist(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_REPORT_MISSING",
                "The expected report cannot be read.",
            ) from error
        if existing != content:
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_REPORT_DRIFT",
                "The expected report differs from current inputs.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _select(args: argparse.Namespace) -> dict[str, object]:
    dataset_bytes = args.dataset.read_bytes()
    split_bytes = args.split.read_bytes()
    dataset_sha256 = hashlib.sha256(dataset_bytes).hexdigest()
    split_sha256 = hashlib.sha256(split_bytes).hexdigest()
    control_bytes, control_report = _load(args.control_report)
    control, control_row = _candidate_row(
        candidate_id=CONTROL_CANDIDATE_ID,
        report_path=args.control_report,
        report=control_report,
        report_bytes=control_bytes,
        expected_dataset_sha256=dataset_sha256,
        expected_split_sha256=split_sha256,
        control=True,
    )
    candidates = [control]
    rows = [control_row]
    for path in args.candidate_report:
        report_bytes, report = _load(path)
        candidate_id = _text(report.get("candidateId"), "candidateId")
        candidate, row = _candidate_row(
            candidate_id=candidate_id,
            report_path=path,
            report=report,
            report_bytes=report_bytes,
            expected_dataset_sha256=dataset_sha256,
            expected_split_sha256=split_sha256,
            control=False,
        )
        candidates.append(candidate)
        rows.append(row)
    winner = select_validation_candidate(candidates)
    report = {
        "benchmarkVersion": BENCHMARK_VERSION,
        "candidates": sorted(rows, key=lambda row: cast(str, row["candidateId"])),
        "datasetSha256": dataset_sha256,
        "schemaVersion": 1,
        "selectedCandidateId": winner.candidate_id,
        "selectionRule": [
            "maximum_validation_macro_recall",
            "maximum_validation_accuracy",
            "minimum_validation_loss",
            "minimum_parameter_count",
            "stable_candidate_id",
        ],
        "selectionVersion": SELECTION_VERSION,
        "splitSha256": split_sha256,
        "status": "selected_test_still_frozen",
    }
    content = _json_bytes(report)
    _persist(args.output, content, check=args.check)
    return {
        "reportSha256": hashlib.sha256(content).hexdigest(),
        "selectedCandidateId": winner.candidate_id,
        "status": report["status"],
    }


def _selected_row(selection: Mapping[str, object]) -> Mapping[str, object]:
    selected_id = _text(selection.get("selectedCandidateId"), "selectedCandidateId")
    rows = [
        _mapping(raw, "candidate")
        for raw in _sequence(selection.get("candidates"), "candidates")
        if _mapping(raw, "candidate").get("candidateId") == selected_id
    ]
    if len(rows) != 1:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_SELECTION_INVALID",
            "The selected candidate must exist exactly once.",
        )
    return rows[0]


def _test(args: argparse.Namespace) -> dict[str, object]:
    selection_bytes, selection = _load(args.selection)
    if (
        selection.get("selectionVersion") != SELECTION_VERSION
        or selection.get("status") != "selected_test_still_frozen"
    ):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_SELECTION_INVALID",
            "The validation selection report is invalid.",
        )
    data = prepare_training_data(args.dataset, args.split, args.asset_root)
    if (
        selection.get("datasetSha256") != data.dataset_sha256
        or selection.get("splitSha256") != data.split_sha256
    ):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_PROVENANCE_DRIFT",
            "The frozen selection references different test inputs.",
        )
    selected = _selected_row(selection)
    artifact = _mapping(selected.get("artifact"), "selected.artifact")
    artifact_path = _safe_repository_path(artifact.get("relativePath"))
    artifact_content = artifact_path.read_bytes()
    if hashlib.sha256(artifact_content).hexdigest() != artifact.get("sha256"):
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARTIFACT_DRIFT",
            "The selected artifact checksum differs.",
        )
    architecture = _text(
        selected.get("architectureVersion"),
        "selected.architectureVersion",
    )
    if architecture == ARCHITECTURE_VERSION:
        model, class_codes, input_size = load_classifier_artifact(artifact_path)
        if class_codes != data.class_codes:
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_CLASS_DRIFT",
                "The selected control class order differs.",
            )
        metrics = evaluate_classifier(
            model.state_dict(),
            data.test,
            TrainingConfig(input_size=input_size),
            class_codes,
        )
    elif architecture == SPATIAL_ARCHITECTURE_VERSION:
        try:
            payload: Any = torch.load(
                artifact_path,
                map_location="cpu",
                weights_only=True,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_ARTIFACT_INVALID",
                "The selected spatial artifact cannot be loaded.",
            ) from error
        payload_row = _mapping(payload, "artifactPayload")
        variant = _text(payload_row.get("candidateVariant"), "candidateVariant")
        class_codes = tuple(
            _text(value, "classCode")
            for value in _sequence(payload_row.get("classCodes"), "classCodes")
        )
        config_row = _mapping(payload_row.get("config"), "config")
        config = TrainingConfig(
            seed=_integer(config_row.get("seed"), "config.seed"),
            input_size=_integer(config_row.get("inputSize"), "config.inputSize"),
        )
        spatial_model = build_benchmark_model(variant, len(class_codes))
        raw_state = _mapping(payload_row.get("stateDict"), "stateDict")
        state = {
            _text(name, "stateName"): value
            for name, value in raw_state.items()
            if isinstance(value, torch.Tensor)
        }
        if len(state) != len(raw_state) or class_codes != data.class_codes:
            raise SymbolClassifierError(
                "SYMBOL_MODEL_BENCHMARK_ARTIFACT_INVALID",
                "The selected spatial state or class order is invalid.",
            )
        spatial_model.load_state_dict(state, strict=True)
        metrics = evaluate_benchmark_model(
            spatial_model,
            data.test,
            config,
            class_codes,
        )
    else:
        raise SymbolClassifierError(
            "SYMBOL_MODEL_BENCHMARK_ARCHITECTURE_UNSUPPORTED",
            "The selected architecture is unsupported.",
        )
    report = {
        "benchmarkVersion": BENCHMARK_VERSION,
        "datasetSha256": data.dataset_sha256,
        "schemaVersion": 1,
        "selectedCandidateId": selected.get("candidateId"),
        "selectedModel": {
            "architectureVersion": architecture,
            "artifactSha256": artifact.get("sha256"),
            "augmentationVersion": selected.get("augmentationVersion"),
        },
        "selectionReportSha256": hashlib.sha256(selection_bytes).hexdigest(),
        "splitSha256": data.split_sha256,
        "status": "selected_candidate_tested",
        "testMetrics": metrics.to_dict(),
        "testReportVersion": TEST_REPORT_VERSION,
        "testSampleCount": len(data.test),
    }
    content = _json_bytes(report)
    _persist(args.output, content, check=args.check)
    return {
        "reportSha256": hashlib.sha256(content).hexdigest(),
        "selectedCandidateId": selected.get("candidateId"),
        "status": report["status"],
        "testAccuracy": metrics.accuracy,
        "testMacroRecall": metrics.macro_recall,
    }


def main() -> int:
    args = _args()
    try:
        result = _select(args) if args.command == "select" else _test(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, RuntimeError, SymbolClassifierError) as error:
        code = (
            error.code
            if isinstance(error, SymbolClassifierError)
            else "SYMBOL_MODEL_BENCHMARK_EXECUTION_FAILED"
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
