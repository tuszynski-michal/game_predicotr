from __future__ import annotations

import copy
from pathlib import Path

import pytest
from game_predictor_worker.images.queue_decision import (
    QueueArchitectureDecisionError,
    build_queue_decision,
    queue_decision_bytes,
    validate_queue_decision,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_decision_is_canonical_and_retains_single_worker() -> None:
    report = build_queue_decision(REPOSITORY_ROOT)
    payload = queue_decision_bytes(report, REPOSITORY_ROOT)

    assert payload == queue_decision_bytes(
        build_queue_decision(REPOSITORY_ROOT),
        REPOSITORY_ROOT,
    )
    assert report["decision"] == {
        "adoptCelery": False,
        "adoptMicroservices": False,
        "adoptRedis": False,
        "executionSlotCount": 1,
        "pipelineExecutionModel": "single_local_worker",
        "schedulingSource": "postgresql_jobs_with_fenced_lease",
        "status": "retain_current_architecture",
    }


def test_decision_rejects_queue_or_quality_gate_drift() -> None:
    report = build_queue_decision(REPOSITORY_ROOT)
    changed = copy.deepcopy(report)
    decision = changed["decision"]
    assert isinstance(decision, dict)
    decision["adoptRedis"] = True
    with pytest.raises(QueueArchitectureDecisionError):
        validate_queue_decision(changed, REPOSITORY_ROOT)

    changed = copy.deepcopy(report)
    constraints = changed["constraints"]
    assert isinstance(constraints, dict)
    constraints["massImportAllowed"] = True
    with pytest.raises(QueueArchitectureDecisionError):
        validate_queue_decision(changed, REPOSITORY_ROOT)


def test_decision_rejects_source_checksum_or_unsafe_value() -> None:
    report = build_queue_decision(REPOSITORY_ROOT)
    sources = report["sourceReports"]
    assert isinstance(sources, list)
    first = sources[0]
    assert isinstance(first, dict)
    first["sha256"] = "0" * 64
    with pytest.raises(QueueArchitectureDecisionError):
        validate_queue_decision(report, REPOSITORY_ROOT)

    report = build_queue_decision(REPOSITORY_ROOT)
    report["unsafe"] = "C:/private/queue.conf"
    with pytest.raises(QueueArchitectureDecisionError):
        validate_queue_decision(report, REPOSITORY_ROOT)
