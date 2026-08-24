from __future__ import annotations

from copy import deepcopy

import pytest
from game_predictor_api.application.remote_manual_selection_rollout import (
    RemoteSelectionRolloutReportError,
    build_rollout_report,
    canonical_report_bytes,
    report_checksum,
    summarize_latency_milliseconds,
    summarize_throughput_bytes_per_second,
    validate_rollout_report,
)


def _report(stage: str = "stage-1", **changes: object) -> dict[str, object]:
    expected = {
        "stage-1": (10, ("duplicate_replay", "restart_recovery", "stale_generation")),
        "stage-2": (100, ("api_5xx_retry", "offline_host", "offline_operator", "revoke")),
        "stage-3": (1_000, ("api_restart", "worker_restart", "refresh_resume")),
        "stage-4": (8_000, ("controlled_restart", "long_session_resume", "network_fault")),
        "stage-5": (15_000, ("operation_scale", "resume_after_fault", "unique_file_scale")),
    }
    target, faults = expected[stage]
    prior = {
        "stage-2": {"stage-1": "1" * 64},
        "stage-3": {"stage-1": "1" * 64, "stage-2": "2" * 64},
        "stage-4": {
            "stage-1": "1" * 64,
            "stage-2": "2" * 64,
            "stage-3": "3" * 64,
        },
        "stage-5": {
            "stage-1": "1" * 64,
            "stage-2": "2" * 64,
            "stage-3": "3" * 64,
            "stage-4": "4" * 64,
        },
    }.get(stage, {})
    values: dict[str, object] = {
        "stage_id": stage,
        "environment": {"executionMode": "local_fixture", "os": "Windows"},
        "source_manifest_checksum_sha256": "a" * 64,
        "source_file_count": target,
        "source_size_bytes": tuple(100 + index for index in range(target)),
        "operation_count": target,
        "selected_file_count": target,
        "host_output_file_count": target,
        "output_manifest_item_count": target,
        "trace_event_count": target,
        "ui_latency_samples_ms": (1.0, 2.0, 3.0),
        "api_latency_samples_ms": (2.0, 3.0, 4.0),
        "transfer_latency_samples_ms": (3.0, 4.0, 5.0),
        "host_queue_latency_samples_ms": (4.0, 5.0, 6.0),
        "retry_count": 2,
        "conflict_count": 0,
        "fault_outcomes": {fault: True for fault in faults},
        "duration_milliseconds": 125.0,
        "throughput_bytes_per_second_samples": (100.0, 200.0, 300.0),
        "process_cpu_milliseconds": 22.0,
        "peak_process_memory_bytes": 1024 * 1024,
        "environment_gate_passed": True,
        "prior_stage_checksums": prior,
        "explicit_owner_approval": "owner-approved-2026-08-24"
        if stage in {"stage-4", "stage-5"}
        else None,
    }
    values.update(changes)
    return build_rollout_report(**values)  # type: ignore[arg-type]


def test_stage_one_report_is_canonical_content_addressed_and_passes() -> None:
    report = _report()

    payload = canonical_report_bytes(report)

    assert report["decision"] == {"status": "passed"}
    assert report["contentChecksumSha256"] == report_checksum(report)
    assert payload == canonical_report_bytes(report)


def test_legacy_stage_one_report_remains_verifiable() -> None:
    report = _report()
    stage = report["stage"]
    assert isinstance(stage, dict)
    stage.pop("minimumOperations")
    report.pop("environmentGate")
    report["contentChecksumSha256"] = report_checksum(report)

    validate_rollout_report(report)
    assert report["decision"] == {"status": "passed"}


def test_stage_two_requires_every_earlier_stage_checksum_in_order() -> None:
    with pytest.raises(RemoteSelectionRolloutReportError, match="Prior stages"):
        _report("stage-2", prior_stage_checksums={})


def test_large_stage_is_blocked_without_explicit_owner_approval() -> None:
    report = _report("stage-4", explicit_owner_approval=None)

    assert report["decision"] == {"status": "blocked"}


def test_environment_gate_and_stage_operation_range_block_progression() -> None:
    assert _report("stage-2", environment_gate_passed=False)["decision"] == {"status": "blocked"}
    assert _report("stage-2", operation_count=99, trace_event_count=99)["decision"] == {
        "status": "blocked"
    }


@pytest.mark.parametrize("mutation", ("absolute_path", "token", "checksum"))
def test_report_validator_fails_closed_on_unsafe_evidence(mutation: str) -> None:
    report = deepcopy(_report())
    if mutation == "absolute_path":
        report["environment"] = {"diagnostic": r"C:\private\selection"}
    elif mutation == "token":
        report["environment"] = {"nested": {"accessToken": "never-publish"}}
    else:
        report["contentChecksumSha256"] = "0" * 64
        with pytest.raises(RemoteSelectionRolloutReportError, match="checksum"):
            validate_rollout_report(report)
        return
    report["contentChecksumSha256"] = report_checksum(report)

    with pytest.raises(RemoteSelectionRolloutReportError):
        validate_rollout_report(report)


def test_integrity_failure_is_a_valid_failed_report_that_cannot_be_a_pass() -> None:
    report = deepcopy(_report())
    outcomes = report["outcomes"]
    assert isinstance(outcomes, dict)
    outcomes["missingFinalFileCount"] = 1
    report["decision"] = {"status": "failed"}
    report["contentChecksumSha256"] = report_checksum(report)

    validate_rollout_report(report)
    assert report["decision"] == {"status": "failed"}


@pytest.mark.parametrize(
    "field",
    (
        "conflictCount",
        "queueErrorCount",
        "manifestChecksumMismatchCount",
        "jpegChecksumMismatchCount",
        "jsonParityMismatchCount",
    ),
)
def test_operational_integrity_error_blocks_rollout(field: str) -> None:
    report = deepcopy(_report())
    outcomes = report["outcomes"]
    assert isinstance(outcomes, dict)
    outcomes[field] = 1
    report["decision"] = {"status": "failed"}
    report["contentChecksumSha256"] = report_checksum(report)

    validate_rollout_report(report)
    assert report["decision"] == {"status": "failed"}


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    assert summarize_latency_milliseconds((1.0, 2.0, 3.0, 4.0)) == {
        "maxMs": 4.0,
        "p50Ms": 2.0,
        "p95Ms": 4.0,
        "p99Ms": 4.0,
        "sampleCount": 4,
    }


def test_throughput_summary_has_an_explicit_average_and_units() -> None:
    assert summarize_throughput_bytes_per_second((10.0, 20.0, 30.0, 40.0)) == {
        "averageBytesPerSecond": 25.0,
        "maxBytesPerSecond": 40.0,
        "p50BytesPerSecond": 20.0,
        "p95BytesPerSecond": 40.0,
        "p99BytesPerSecond": 40.0,
        "sampleCount": 4,
    }
