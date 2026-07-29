"""Checksum-bound M7 queue and pipeline architecture decision."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from .load_benchmark import validate_load_report
from .operations_benchmark import validate_operations_report

QUEUE_DECISION_SCHEMA = "m7-queue-architecture-decision-v1"
SOURCE_REPORTS = {
    "databaseStorage": "ai_docs/quality/m7-storage-database-load-report.json",
    "operationsQuality": ("ai_docs/quality/m7-import-operations-benchmark-report.json"),
}


class QueueArchitectureDecisionError(RuntimeError):
    """Stable validation failure for the local architecture decision."""


def build_queue_decision(repository_root: Path) -> dict[str, object]:
    load_report, load_sha = _read_source_report(
        repository_root,
        SOURCE_REPORTS["databaseStorage"],
    )
    operations_report, operations_sha = _read_source_report(
        repository_root,
        SOURCE_REPORTS["operationsQuality"],
    )
    validate_load_report(load_report)
    validate_operations_report(operations_report)

    profile = _mapping(load_report.get("profile"), "load.profile")
    database = _mapping(load_report.get("database"), "load.database")
    registration = _mapping(
        database.get("registration"),
        "load.database.registration",
    )
    storage = _mapping(load_report.get("storage"), "load.storage")
    materialization = _mapping(
        storage.get("materialization"),
        "load.storage.materialization",
    )
    operations = _mapping(
        operations_report.get("operations"),
        "operations.operations",
    )
    quality = _mapping(
        operations_report.get("qualityEvidence"),
        "operations.qualityEvidence",
    )
    source_reports = [
        {
            "name": "databaseStorage",
            "relativePath": SOURCE_REPORTS["databaseStorage"],
            "schemaVersion": load_report["schemaVersion"],
            "sha256": load_sha,
        },
        {
            "name": "operationsQuality",
            "relativePath": SOURCE_REPORTS["operationsQuality"],
            "schemaVersion": operations_report["schemaVersion"],
            "sha256": operations_sha,
        },
    ]
    decision: dict[str, object] = {
        "adoptCelery": False,
        "adoptMicroservices": False,
        "adoptRedis": False,
        "executionSlotCount": 1,
        "pipelineExecutionModel": "single_local_worker",
        "schedulingSource": "postgresql_jobs_with_fenced_lease",
        "status": "retain_current_architecture",
    }
    report: dict[str, object] = {
        "constraints": {
            "deployment": "single_local_windows_workstation",
            "heavyJobConcurrency": 1,
            "internetRuntime": False,
            "massImportAllowed": quality.get("massImportAllowed"),
            "operatorModel": "private_local_admin",
        },
        "decision": decision,
        "evidence": {
            "databaseRegistrationThroughputPerSecond": registration.get("throughputPerSecond"),
            "fullProfileFileCount": profile.get("fileCount"),
            "fullProfileLayoutCapacity": profile.get("representedLayoutCapacity"),
            "operationsRecoveryPassed": operations.get("allChecksPassed"),
            "reviewPersistenceThroughputPerSecond": _mapping(
                operations.get("reviewPersistence"),
                "operations.reviewPersistence",
            ).get("throughputPerSecond"),
            "storageMaterializationThroughputPerSecond": materialization.get("throughputPerSecond"),
        },
        "nonGoals": [
            "This decision does not enable mass import or publication.",
            "This decision does not weaken OCR or classifier quality gates.",
            "This decision does not treat synthetic operations timing as ML accuracy.",
        ],
        "rationale": [
            {
                "code": "DATABASE_STORAGE_CAPACITY_PASSED",
                "detail": (
                    "The physical 500004-layout capacity profile completed within "
                    "its controlled deadline using bounded memory."
                ),
            },
            {
                "code": "RECOVERY_AND_FENCING_PASSED",
                "detail": (
                    "Checkpoint restart, six isolated stage failures and exact "
                    "retry completed without another coordinator."
                ),
            },
            {
                "code": "QUALITY_IS_CURRENT_BOTTLENECK",
                "detail": (
                    "Mass import remains disabled and manual review share is 1.0; "
                    "a broker cannot improve prediction quality."
                ),
            },
            {
                "code": "LOCAL_SINGLE_OPERATOR_SCOPE",
                "detail": (
                    "The product runs on one private Windows workstation and does "
                    "not require distributed scheduling."
                ),
            },
        ],
        "reopenConditions": [
            {
                "code": "SUSTAINED_HEAVY_JOB_BACKLOG",
                "measurement": "created heavy jobs waiting while one healthy job runs",
                "threshold": "at least 3 jobs continuously for at least 30 minutes",
            },
            {
                "code": "ACCEPTED_IMPORT_SLA_MISSED",
                "measurement": "real-image end-to-end import elapsed time",
                "threshold": ("two repeatable runs exceed the explicitly accepted TASK-0076 SLA"),
            },
            {
                "code": "MULTI_ADMIN_CONCURRENCY_REQUIRED",
                "measurement": "simultaneous administrators requiring heavy jobs",
                "threshold": "at least 2 concurrent operators after Q-019 is resolved",
            },
            {
                "code": "SINGLE_PROCESS_RECOVERY_REGRESSION",
                "measurement": "controlled restart/fencing benchmark",
                "threshold": "any lost checkpoint, duplicate side effect or stale write",
            },
            {
                "code": "DEPLOYMENT_BOUNDARY_CHANGED",
                "measurement": "runtime topology",
                "threshold": ("worker moves beyond one local workstation or requires remote nodes"),
            },
        ],
        "requiredActionOnReopen": (
            "Create a new measured architecture task and Decision Log entry; "
            "do not install or migrate queue infrastructure automatically."
        ),
        "schemaVersion": QUEUE_DECISION_SCHEMA,
        "sourceReports": source_reports,
    }
    validate_queue_decision(report, repository_root)
    return report


def queue_decision_bytes(
    report: Mapping[str, object],
    repository_root: Path,
) -> bytes:
    validate_queue_decision(report, repository_root)
    return (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def validate_queue_decision(
    report: Mapping[str, object],
    repository_root: Path,
) -> None:
    if report.get("schemaVersion") != QUEUE_DECISION_SCHEMA:
        raise QueueArchitectureDecisionError("Unexpected queue decision schema.")
    decision = _mapping(report.get("decision"), "decision")
    expected_decision = {
        "adoptCelery": False,
        "adoptMicroservices": False,
        "adoptRedis": False,
        "executionSlotCount": 1,
        "pipelineExecutionModel": "single_local_worker",
        "schedulingSource": "postgresql_jobs_with_fenced_lease",
        "status": "retain_current_architecture",
    }
    if decision != expected_decision:
        raise QueueArchitectureDecisionError("Queue architecture decision drifted.")
    constraints = _mapping(report.get("constraints"), "constraints")
    if constraints.get("massImportAllowed") is not False:
        raise QueueArchitectureDecisionError("Queue decision cannot enable mass import.")
    reopen_conditions = _sequence(report.get("reopenConditions"), "reopenConditions")
    if len(reopen_conditions) < 4:
        raise QueueArchitectureDecisionError("Queue decision needs measurable reopen conditions.")
    source_reports = _sequence(report.get("sourceReports"), "sourceReports")
    if len(source_reports) != len(SOURCE_REPORTS):
        raise QueueArchitectureDecisionError("Queue decision sources are incomplete.")
    seen_names: set[str] = set()
    for source_value in source_reports:
        source = _mapping(source_value, "source report")
        name = source.get("name")
        if not isinstance(name, str) or name not in SOURCE_REPORTS or name in seen_names:
            raise QueueArchitectureDecisionError("Queue decision source name is invalid.")
        seen_names.add(name)
        relative_path = SOURCE_REPORTS[name]
        if source.get("relativePath") != relative_path:
            raise QueueArchitectureDecisionError("Queue decision source path drifted.")
        raw = (repository_root / relative_path).read_bytes()
        if source.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise QueueArchitectureDecisionError("Queue decision source checksum drifted.")
        source_report = json.loads(raw)
        if not isinstance(source_report, dict):
            raise QueueArchitectureDecisionError("Source report must be an object.")
        if name == "databaseStorage":
            validate_load_report(source_report)
        else:
            validate_operations_report(source_report)
        if source.get("schemaVersion") != source_report.get("schemaVersion"):
            raise QueueArchitectureDecisionError("Source report schema drifted.")
    for value in _all_strings(report):
        lowered = value.lower()
        if "postgresql://" in lowered or "postgresql+psycopg://" in lowered:
            raise QueueArchitectureDecisionError("Decision exposes a database URL.")
        if len(value) >= 3 and value[0].isalpha() and value[1:3] in {":\\", ":/"}:
            raise QueueArchitectureDecisionError("Decision exposes an absolute path.")


def _read_source_report(
    repository_root: Path,
    relative_path: str,
) -> tuple[dict[str, object], str]:
    raw = (repository_root / relative_path).read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise QueueArchitectureDecisionError("Source report must be an object.")
    return cast(dict[str, object], value), hashlib.sha256(raw).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise QueueArchitectureDecisionError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise QueueArchitectureDecisionError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_all_strings(key))
            result.extend(_all_strings(item))
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        result = []
        for item in value:
            result.extend(_all_strings(item))
        return result
    return []


__all__ = [
    "QUEUE_DECISION_SCHEMA",
    "QueueArchitectureDecisionError",
    "build_queue_decision",
    "queue_decision_bytes",
    "validate_queue_decision",
]
