"""Deterministic validation around the physical M6.5 scale profile."""

from __future__ import annotations

from copy import deepcopy

import pytest
from game_predictor_worker.images.workbench_acceptance import (
    WORKBENCH_ACCEPTANCE_SCHEMA,
    WORKBENCH_BOARD_COUNT,
    WORKBENCH_CELL_COUNT,
    WorkbenchAcceptanceError,
    validate_workbench_acceptance_report,
)


def _passing_report() -> dict[str, object]:
    return {
        "schemaVersion": WORKBENCH_ACCEPTANCE_SCHEMA,
        "fixture": {
            "boardCount": WORKBENCH_BOARD_COUNT,
            "cellCount": WORKBENCH_CELL_COUNT,
            "clientPageLimit": 1,
        },
        "physicalProfile": {
            "allChecksPassed": True,
            "adjacentRead": {"p95Milliseconds": 20.0},
            "resolutionWrite": {"p95Milliseconds": 35.0},
        },
        "decision": {
            "automaticMassImportAllowed": False,
            "g6_5Status": "passed_local_supervised",
            "manualReviewRequired": True,
        },
        "operatorProjection": {
            "backlogBoardCount": WORKBENCH_BOARD_COUNT,
            "measurementKind": "planning_projection",
        },
    }


def test_scale_report_requires_3000_boards_with_one_item_client_page() -> None:
    report = _passing_report()
    validate_workbench_acceptance_report(report)

    unbounded = deepcopy(report)
    fixture = unbounded["fixture"]
    assert isinstance(fixture, dict)
    fixture["clientPageLimit"] = WORKBENCH_BOARD_COUNT
    with pytest.raises(WorkbenchAcceptanceError, match="cardinality"):
        validate_workbench_acceptance_report(unbounded)


@pytest.mark.parametrize("operation", ["adjacentRead", "resolutionWrite"])
def test_scale_report_rejects_p95_above_local_gate(operation: str) -> None:
    report = _passing_report()
    physical = report["physicalProfile"]
    assert isinstance(physical, dict)
    timing = physical[operation]
    assert isinstance(timing, dict)
    timing["p95Milliseconds"] = 500.001
    with pytest.raises(WorkbenchAcceptanceError, match="500 ms"):
        validate_workbench_acceptance_report(report)
