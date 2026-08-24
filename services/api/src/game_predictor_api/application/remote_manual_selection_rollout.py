"""Fail-closed, content-addressed evidence for remote-selection rollout stages."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

REMOTE_SELECTION_ROLLOUT_REPORT_SCHEMA = "remote-manual-selection-rollout-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'])(?:[a-zA-Z]:[\\/]|[\\/]{2})[^\s\"']+")

RolloutStageId = Literal["stage-1", "stage-2", "stage-3", "stage-4", "stage-5"]
RolloutStatus = Literal["passed", "failed", "blocked"]


@dataclass(frozen=True, slots=True)
class RemoteSelectionRolloutStage:
    id: RolloutStageId
    operation_target: int
    requires_owner_approval: bool
    required_faults: tuple[str, ...]


ROLL_OUT_STAGES: tuple[RemoteSelectionRolloutStage, ...] = (
    RemoteSelectionRolloutStage(
        id="stage-1",
        operation_target=10,
        requires_owner_approval=False,
        required_faults=("duplicate_replay", "restart_recovery", "stale_generation"),
    ),
    RemoteSelectionRolloutStage(
        id="stage-2",
        operation_target=500,
        requires_owner_approval=False,
        required_faults=("api_5xx_retry", "offline_operator", "revoke"),
    ),
    RemoteSelectionRolloutStage(
        id="stage-3",
        operation_target=1_000,
        requires_owner_approval=False,
        required_faults=("api_restart", "worker_restart", "refresh_resume"),
    ),
    RemoteSelectionRolloutStage(
        id="stage-4",
        operation_target=8_000,
        requires_owner_approval=True,
        required_faults=("network_fault", "controlled_restart", "long_session_resume"),
    ),
    RemoteSelectionRolloutStage(
        id="stage-5",
        operation_target=15_000,
        requires_owner_approval=True,
        required_faults=("unique_file_scale", "operation_scale", "resume_after_fault"),
    ),
)
_STAGES_BY_ID = {stage.id: stage for stage in ROLL_OUT_STAGES}
_FORBIDDEN_KEY_FRAGMENTS = frozenset(
    {"accesscode", "authorization", "cookie", "hostpath", "leasetoken", "secret", "token"}
)


class RemoteSelectionRolloutReportError(ValueError):
    """A rollout report cannot be used as evidence for the next stage."""


def rollout_stage(stage_id: str) -> RemoteSelectionRolloutStage:
    try:
        return _STAGES_BY_ID[stage_id]  # type: ignore[index]
    except KeyError as error:
        raise RemoteSelectionRolloutReportError(
            "Unknown remote-selection rollout stage."
        ) from error


def summarize_latency_milliseconds(samples: Sequence[float]) -> dict[str, float | int]:
    """Return deterministic nearest-rank latency percentiles."""

    if not samples or any(not math.isfinite(value) or value < 0 for value in samples):
        raise RemoteSelectionRolloutReportError(
            "Latency samples must be finite non-negative values."
        )
    ordered = sorted(samples)

    def percentile(percent: float) -> float:
        index = max(0, math.ceil(percent * len(ordered)) - 1)
        return round(ordered[index], 4)

    return {
        "maxMs": round(ordered[-1], 4),
        "p50Ms": percentile(0.50),
        "p95Ms": percentile(0.95),
        "p99Ms": percentile(0.99),
        "sampleCount": len(ordered),
    }


def summarize_throughput_bytes_per_second(
    samples: Sequence[float],
) -> dict[str, float | int]:
    """Return a unit-explicit distribution for transfer throughput."""

    if not samples or any(not math.isfinite(value) or value < 0 for value in samples):
        raise RemoteSelectionRolloutReportError(
            "Throughput samples must be finite non-negative values."
        )
    ordered = sorted(samples)

    def percentile(percent: float) -> float:
        index = max(0, math.ceil(percent * len(ordered)) - 1)
        return round(ordered[index], 4)

    return {
        "averageBytesPerSecond": round(sum(ordered) / len(ordered), 4),
        "maxBytesPerSecond": round(ordered[-1], 4),
        "p50BytesPerSecond": percentile(0.50),
        "p95BytesPerSecond": percentile(0.95),
        "p99BytesPerSecond": percentile(0.99),
        "sampleCount": len(ordered),
    }


def report_checksum(payload: Mapping[str, object]) -> str:
    unsigned = dict(payload)
    unsigned.pop("contentChecksumSha256", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def canonical_report_bytes(payload: Mapping[str, object]) -> bytes:
    report = dict(payload)
    report["contentChecksumSha256"] = report_checksum(report)
    validate_rollout_report(report)
    return _canonical_bytes(report)


def build_rollout_report(
    *,
    stage_id: str,
    environment: Mapping[str, object],
    source_manifest_checksum_sha256: str,
    source_file_count: int,
    source_size_bytes: Sequence[int],
    operation_count: int,
    selected_file_count: int,
    host_output_file_count: int,
    output_manifest_item_count: int,
    trace_event_count: int,
    ui_latency_samples_ms: Sequence[float],
    api_latency_samples_ms: Sequence[float],
    transfer_latency_samples_ms: Sequence[float],
    host_queue_latency_samples_ms: Sequence[float],
    retry_count: int,
    conflict_count: int,
    fault_outcomes: Mapping[str, bool],
    duration_milliseconds: float,
    throughput_bytes_per_second_samples: Sequence[float],
    process_cpu_milliseconds: float,
    peak_process_memory_bytes: int,
    queue_error_count: int = 0,
    manifest_checksum_mismatch_count: int = 0,
    jpeg_checksum_mismatch_count: int = 0,
    json_parity_mismatch_count: int = 0,
    missing_final_file_count: int = 0,
    duplicate_final_file_count: int = 0,
    foreign_file_overwrite_count: int = 0,
    lost_decision_count: int = 0,
    verified_resend_count: int = 0,
    prior_stage_checksums: Mapping[str, str] | None = None,
    explicit_owner_approval: str | None = None,
) -> dict[str, object]:
    """Build evidence from measurements; validation decides whether it may pass."""

    stage = rollout_stage(stage_id)
    if any(size < 1 for size in source_size_bytes):
        raise RemoteSelectionRolloutReportError("Source sizes must be positive.")
    report: dict[str, object] = {
        "schemaVersion": REMOTE_SELECTION_ROLLOUT_REPORT_SCHEMA,
        "stage": {
            "id": stage.id,
            "operationTarget": stage.operation_target,
            "requiresOwnerApproval": stage.requires_owner_approval,
        },
        "environment": dict(environment),
        "approval": {
            "explicitOwnerApproval": explicit_owner_approval,
            "required": stage.requires_owner_approval,
        },
        "priorStages": [
            {"contentChecksumSha256": checksum, "id": previous.id}
            for previous in ROLL_OUT_STAGES
            if previous.id in (prior_stage_checksums or {})
            for checksum in ((prior_stage_checksums or {})[previous.id],)
        ],
        "source": {
            "fileCount": source_file_count,
            "manifestChecksumSha256": source_manifest_checksum_sha256,
            "sizeDistributionBytes": _size_distribution(source_size_bytes),
        },
        "metrics": {
            "apiLatency": summarize_latency_milliseconds(api_latency_samples_ms),
            "hostQueueLatency": summarize_latency_milliseconds(host_queue_latency_samples_ms),
            "transferLatency": summarize_latency_milliseconds(transfer_latency_samples_ms),
            "uiLatency": summarize_latency_milliseconds(ui_latency_samples_ms),
        },
        "performance": {
            "durationMs": _finite_non_negative(duration_milliseconds, "duration_milliseconds"),
            "peakProcessMemoryBytes": _positive_int(
                peak_process_memory_bytes,
                "peak_process_memory_bytes",
            ),
            "processCpuMs": _finite_non_negative(
                process_cpu_milliseconds,
                "process_cpu_milliseconds",
            ),
            "throughputBytesPerSecond": summarize_throughput_bytes_per_second(
                throughput_bytes_per_second_samples
            ),
        },
        "outcomes": {
            "conflictCount": conflict_count,
            "duplicateFinalFileCount": duplicate_final_file_count,
            "foreignFileOverwriteCount": foreign_file_overwrite_count,
            "jpegChecksumMismatchCount": jpeg_checksum_mismatch_count,
            "jsonParityMismatchCount": json_parity_mismatch_count,
            "lostDecisionCount": lost_decision_count,
            "manifestChecksumMismatchCount": manifest_checksum_mismatch_count,
            "missingFinalFileCount": missing_final_file_count,
            "operationCount": operation_count,
            "outputManifestItemCount": output_manifest_item_count,
            "retryCount": retry_count,
            "queueErrorCount": queue_error_count,
            "selectedFileCount": selected_file_count,
            "hostOutputFileCount": host_output_file_count,
            "traceEventCount": trace_event_count,
            "verifiedResendCount": verified_resend_count,
        },
        "faultInjection": [
            {"code": code, "status": "passed" if passed else "failed"}
            for code, passed in sorted(fault_outcomes.items())
        ],
        "decision": {"status": "blocked"},
    }
    report["decision"] = {"status": _decision_status(report)}
    report["contentChecksumSha256"] = report_checksum(report)
    validate_rollout_report(report)
    return report


def validate_rollout_report(payload: Mapping[str, object]) -> None:
    """Validate immutable evidence and reject unsafe or incomplete rollout claims."""

    if payload.get("schemaVersion") != REMOTE_SELECTION_ROLLOUT_REPORT_SCHEMA:
        raise RemoteSelectionRolloutReportError("Unsupported rollout report schema.")
    _reject_sensitive_data(payload)
    stage_payload = _mapping(payload.get("stage"), "stage")
    stage = rollout_stage(_string(stage_payload.get("id"), "stage.id"))
    if stage_payload.get("operationTarget") != stage.operation_target:
        raise RemoteSelectionRolloutReportError("The rollout operation target drifted.")
    if stage_payload.get("requiresOwnerApproval") is not stage.requires_owner_approval:
        raise RemoteSelectionRolloutReportError("The rollout approval policy drifted.")
    source = _mapping(payload.get("source"), "source")
    source_count = _positive_int(source.get("fileCount"), "source.fileCount")
    if not SHA256.fullmatch(_string(source.get("manifestChecksumSha256"), "source.manifest")):
        raise RemoteSelectionRolloutReportError("The source manifest checksum is invalid.")
    _validate_distribution(
        _mapping(source.get("sizeDistributionBytes"), "source.sizeDistributionBytes"),
        source_count,
    )
    _validate_metrics(_mapping(payload.get("metrics"), "metrics"))
    _validate_performance(_mapping(payload.get("performance"), "performance"))
    outcomes = _mapping(payload.get("outcomes"), "outcomes")
    _validate_outcomes(outcomes, source_count)
    _validate_prior_stages(payload.get("priorStages"), stage)
    _validate_faults(payload.get("faultInjection"), stage)
    approval = _mapping(payload.get("approval"), "approval")
    approved = approval.get("explicitOwnerApproval")
    if approval.get("required") is not stage.requires_owner_approval:
        raise RemoteSelectionRolloutReportError("The approval marker does not match the stage.")
    if approved is not None and (not isinstance(approved, str) or not approved.strip()):
        raise RemoteSelectionRolloutReportError("The owner approval marker is invalid.")
    actual_status = _decision_status(payload)
    decision = _mapping(payload.get("decision"), "decision")
    if decision.get("status") != actual_status:
        raise RemoteSelectionRolloutReportError("The rollout decision does not match its evidence.")
    if actual_status == "passed" and stage.requires_owner_approval and approved is None:
        raise RemoteSelectionRolloutReportError("A large stage cannot pass without owner approval.")
    checksum = _string(payload.get("contentChecksumSha256"), "contentChecksumSha256")
    if checksum != report_checksum(payload):
        raise RemoteSelectionRolloutReportError("The rollout report checksum is invalid.")


def _decision_status(payload: Mapping[str, object]) -> RolloutStatus:
    stage = rollout_stage(_string(_mapping(payload.get("stage"), "stage").get("id"), "stage.id"))
    outcomes = _mapping(payload.get("outcomes"), "outcomes")
    errors = sum(
        _non_negative_int(outcomes.get(key), f"outcomes.{key}")
        for key in (
            "conflictCount",
            "duplicateFinalFileCount",
            "foreignFileOverwriteCount",
            "jpegChecksumMismatchCount",
            "jsonParityMismatchCount",
            "lostDecisionCount",
            "manifestChecksumMismatchCount",
            "missingFinalFileCount",
            "queueErrorCount",
            "verifiedResendCount",
        )
    )
    parity_ok = _non_negative_int(
        outcomes.get("hostOutputFileCount"), "outcomes.hostOutputFileCount"
    ) == _non_negative_int(
        outcomes.get("selectedFileCount"), "outcomes.selectedFileCount"
    ) == _non_negative_int(
        outcomes.get("outputManifestItemCount"),
        "outcomes.outputManifestItemCount",
    ) and _non_negative_int(
        outcomes.get("traceEventCount"), "outcomes.traceEventCount"
    ) == _non_negative_int(outcomes.get("operationCount"), "outcomes.operationCount")
    faults = _fault_statuses(payload.get("faultInjection"))
    required_faults_ok = all(faults.get(code) == "passed" for code in stage.required_faults)
    prior_ok = _prior_stages_present(payload.get("priorStages"), stage)
    approval = _mapping(payload.get("approval"), "approval")
    approval_ok = (
        not stage.requires_owner_approval or approval.get("explicitOwnerApproval") is not None
    )
    if errors == 0 and parity_ok and required_faults_ok and prior_ok and approval_ok:
        return "passed"
    if errors > 0 or any(status == "failed" for status in faults.values()):
        return "failed"
    return "blocked"


def _validate_outcomes(outcomes: Mapping[str, object], source_count: int) -> None:
    for key in (
        "conflictCount",
        "duplicateFinalFileCount",
        "foreignFileOverwriteCount",
        "jpegChecksumMismatchCount",
        "jsonParityMismatchCount",
        "lostDecisionCount",
        "manifestChecksumMismatchCount",
        "missingFinalFileCount",
        "operationCount",
        "outputManifestItemCount",
        "retryCount",
        "queueErrorCount",
        "selectedFileCount",
        "hostOutputFileCount",
        "traceEventCount",
        "verifiedResendCount",
    ):
        _non_negative_int(outcomes.get(key), f"outcomes.{key}")
    if (
        _non_negative_int(outcomes.get("selectedFileCount"), "outcomes.selectedFileCount")
        > source_count
    ):
        raise RemoteSelectionRolloutReportError("Selected files exceed the source manifest.")


def _validate_metrics(metrics: Mapping[str, object]) -> None:
    for name in ("apiLatency", "hostQueueLatency", "transferLatency", "uiLatency"):
        latency = _mapping(metrics.get(name), f"metrics.{name}")
        if _positive_int(latency.get("sampleCount"), f"metrics.{name}.sampleCount") < 1:
            raise AssertionError("unreachable")
        values = [
            _finite_non_negative(latency.get(key), f"metrics.{name}.{key}")
            for key in ("p50Ms", "p95Ms", "p99Ms", "maxMs")
        ]
        if values != sorted(values):
            raise RemoteSelectionRolloutReportError("Latency percentiles are not monotonic.")


def _validate_performance(performance: Mapping[str, object]) -> None:
    _finite_non_negative(performance.get("durationMs"), "performance.durationMs")
    _finite_non_negative(performance.get("processCpuMs"), "performance.processCpuMs")
    _positive_int(performance.get("peakProcessMemoryBytes"), "performance.peakProcessMemoryBytes")
    throughput = _mapping(
        performance.get("throughputBytesPerSecond"),
        "performance.throughputBytesPerSecond",
    )
    if (
        _positive_int(
            throughput.get("sampleCount"),
            "performance.throughputBytesPerSecond.sampleCount",
        )
        < 1
    ):
        raise AssertionError("unreachable")
    _finite_non_negative(
        throughput.get("averageBytesPerSecond"),
        "performance.throughputBytesPerSecond.averageBytesPerSecond",
    )
    values = [
        _finite_non_negative(
            throughput.get(key),
            f"performance.throughputBytesPerSecond.{key}",
        )
        for key in (
            "p50BytesPerSecond",
            "p95BytesPerSecond",
            "p99BytesPerSecond",
            "maxBytesPerSecond",
        )
    ]
    if values != sorted(values):
        raise RemoteSelectionRolloutReportError("Throughput percentiles are not monotonic.")


def _validate_distribution(distribution: Mapping[str, object], source_count: int) -> None:
    if (
        _positive_int(
            distribution.get("sampleCount"),
            "source.sizeDistributionBytes.sampleCount",
        )
        != source_count
    ):
        raise RemoteSelectionRolloutReportError(
            "Source size distribution count differs from manifest."
        )
    values = [
        _positive_int(distribution.get(key), f"source.sizeDistributionBytes.{key}")
        for key in ("minBytes", "p50Bytes", "p95Bytes", "maxBytes")
    ]
    if values != sorted(values):
        raise RemoteSelectionRolloutReportError("Source size percentiles are not monotonic.")


def _validate_prior_stages(value: object, stage: RemoteSelectionRolloutStage) -> None:
    if not isinstance(value, list):
        raise RemoteSelectionRolloutReportError("priorStages must be a list.")
    expected = [item.id for item in ROLL_OUT_STAGES[: ROLL_OUT_STAGES.index(stage)]]
    actual: list[str] = []
    for item in value:
        row = _mapping(item, "priorStages[]")
        stage_id = _string(row.get("id"), "priorStages[].id")
        checksum = _string(row.get("contentChecksumSha256"), "priorStages[].contentChecksumSha256")
        if not SHA256.fullmatch(checksum):
            raise RemoteSelectionRolloutReportError("A prior stage checksum is invalid.")
        actual.append(stage_id)
    if actual != expected:
        raise RemoteSelectionRolloutReportError("Prior stages are incomplete or out of order.")


def _prior_stages_present(value: object, stage: RemoteSelectionRolloutStage) -> bool:
    try:
        _validate_prior_stages(value, stage)
    except RemoteSelectionRolloutReportError:
        return False
    return True


def _validate_faults(value: object, stage: RemoteSelectionRolloutStage) -> None:
    statuses = _fault_statuses(value)
    if set(statuses) != set(stage.required_faults):
        raise RemoteSelectionRolloutReportError("Fault evidence is incomplete or unexpected.")
    if any(status not in {"passed", "failed"} for status in statuses.values()):
        raise RemoteSelectionRolloutReportError("Fault evidence has an invalid status.")


def _fault_statuses(value: object) -> dict[str, str]:
    if not isinstance(value, list):
        raise RemoteSelectionRolloutReportError("faultInjection must be a list.")
    statuses: dict[str, str] = {}
    for item in value:
        row = _mapping(item, "faultInjection[]")
        code = _string(row.get("code"), "faultInjection[].code")
        if code in statuses:
            raise RemoteSelectionRolloutReportError("Fault evidence contains a duplicate code.")
        statuses[code] = _string(row.get("status"), "faultInjection[].status")
    return statuses


def _size_distribution(sizes: Sequence[int]) -> dict[str, int]:
    ordered = sorted(sizes)
    if not ordered:
        raise RemoteSelectionRolloutReportError("At least one source size is required.")
    return {
        "maxBytes": ordered[-1],
        "minBytes": ordered[0],
        "p50Bytes": ordered[max(0, math.ceil(0.50 * len(ordered)) - 1)],
        "p95Bytes": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        "sampleCount": len(ordered),
    }


def _reject_sensitive_data(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).replace("_", "").replace("-", "").casefold()
            if any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise RemoteSelectionRolloutReportError(
                    "Rollout report contains a sensitive field."
                )
            _reject_sensitive_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_data(nested)
    elif isinstance(value, str) and WINDOWS_ABSOLUTE_PATH.search(value):
        raise RemoteSelectionRolloutReportError("Rollout report contains an absolute host path.")


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RemoteSelectionRolloutReportError(f"{field} must be an object.")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RemoteSelectionRolloutReportError(f"{field} must be a non-empty string.")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RemoteSelectionRolloutReportError(f"{field} must be a positive integer.")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RemoteSelectionRolloutReportError(f"{field} must be a non-negative integer.")
    return value


def _finite_non_negative(value: object, field: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise RemoteSelectionRolloutReportError(f"{field} must be finite and non-negative.")
    return float(value)


__all__ = [
    "REMOTE_SELECTION_ROLLOUT_REPORT_SCHEMA",
    "ROLL_OUT_STAGES",
    "RemoteSelectionRolloutReportError",
    "RemoteSelectionRolloutStage",
    "build_rollout_report",
    "canonical_report_bytes",
    "report_checksum",
    "rollout_stage",
    "summarize_latency_milliseconds",
    "summarize_throughput_bytes_per_second",
    "validate_rollout_report",
]
