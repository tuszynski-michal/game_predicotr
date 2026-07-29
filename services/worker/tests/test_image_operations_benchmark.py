from __future__ import annotations

import copy
from pathlib import Path

import pytest
from game_predictor_worker.images.operations_benchmark import (
    BOARD_COUNT,
    CELL_COUNT,
    OPERATIONS_BENCHMARK_SCHEMA,
    ImageOperationsBenchmarkError,
    operations_report_bytes,
    validate_operations_report,
)


def _report() -> dict[str, object]:
    return {
        "capturedAt": "2026-07-29T14:00:00+00:00",
        "decision": {
            "additionalQueueRequired": False,
            "autoAcceptEnabled": False,
            "g7_4Status": "passed_manual_review_only",
            "massImportAllowed": False,
            "nextAction": "collect_review_feedback_and_retrain",
        },
        "operationalFixture": {
            "boardsPerSource": 9,
            "cellCount": CELL_COUNT,
            "purpose": "synthetic persistence fixture",
            "sourceFileCount": 43,
            "totalBoardCount": BOARD_COUNT,
        },
        "operations": {
            "allChecksPassed": True,
            "reviewDecisionCount": BOARD_COUNT,
            "stagingCellCount": CELL_COUNT,
            "stagingLayoutCount": BOARD_COUNT,
        },
        "qualityEvidence": {
            "autoAcceptEnabled": False,
            "massImportAllowed": False,
        },
        "schemaVersion": OPERATIONS_BENCHMARK_SCHEMA,
    }


def test_report_is_canonical_and_valid() -> None:
    first = operations_report_bytes(_report())
    second = operations_report_bytes(copy.deepcopy(_report()))

    assert first == second
    assert first.endswith(b"\n")


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("operations", "allChecksPassed", False),
        ("operations", "stagingLayoutCount", BOARD_COUNT - 1),
        ("qualityEvidence", "massImportAllowed", True),
        ("decision", "autoAcceptEnabled", True),
    ],
)
def test_validator_rejects_gate_or_cardinality_drift(
    section: str,
    field: str,
    value: object,
) -> None:
    report = _report()
    nested = report[section]
    assert isinstance(nested, dict)
    nested[field] = value

    with pytest.raises(ImageOperationsBenchmarkError):
        validate_operations_report(report)


def test_validator_rejects_database_url_and_absolute_path() -> None:
    report = _report()
    report["unsafe"] = "postgresql://secret@localhost/db"
    with pytest.raises(ImageOperationsBenchmarkError):
        validate_operations_report(report)

    report = _report()
    report["unsafe"] = str(Path("C:/private/model.onnx"))
    with pytest.raises(ImageOperationsBenchmarkError):
        validate_operations_report(report)
