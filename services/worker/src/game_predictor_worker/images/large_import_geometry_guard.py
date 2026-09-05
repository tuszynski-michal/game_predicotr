"""Fail-closed representative geometry guard for large v0.10 imports."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_worker.jobs.runtime import JobHandlerError

from .geometry_guard_resolution import GeometryGuardResolutionSet
from .grid_profile_end_to_end_gate import (
    GridProfileGateBoardResult,
    GridProfileGateSourceResult,
    ProductionGateAdapterSuite,
    run_grid_profile_gate_source,
)
from .pipeline_contract import file_execution_key
from .pipeline_execution import ImageStageContext
from .source_ingestion import ManagedOriginal

LARGE_IMPORT_GEOMETRY_GUARD_VERSION = "image-geometry-systemic-guard-v1"
LARGE_IMPORT_GEOMETRY_GUARD_REPORT_SCHEMA = "image-geometry-systemic-guard-report-v2"
LARGE_IMPORT_MIN_SOURCE_COUNT = 100
LARGE_IMPORT_MIN_BOARD_COUNT = 500
LARGE_IMPORT_GUARD_SAMPLE_LIMIT = 25
LARGE_IMPORT_MIN_READY_RATE = 0.98


@dataclass(frozen=True, slots=True)
class LargeImportGeometryGuardResult:
    required: bool
    passed: bool
    report_checksum_sha256: str | None
    report_relative_path: str | None
    source_count: int
    active_board_count: int
    sample_source_count: int
    sample_board_count: int
    page_registration_ready_rate: float | None
    final_cell_grid_ready_rate: float | None
    invariant_violation_count: int

    def checkpoint_payload(self) -> dict[str, object]:
        return {
            "policyVersion": LARGE_IMPORT_GEOMETRY_GUARD_VERSION,
            "required": self.required,
            "passed": self.passed,
            "reportChecksumSha256": self.report_checksum_sha256,
            "reportRelativePath": self.report_relative_path,
            "sourceCount": self.source_count,
            "activeBoardCount": self.active_board_count,
            "sampleSourceCount": self.sample_source_count,
            "sampleBoardCount": self.sample_board_count,
            "pageRegistrationReadyRate": self.page_registration_ready_rate,
            "finalCellGridReadyRate": self.final_cell_grid_ready_rate,
            "invariantViolationCount": self.invariant_violation_count,
        }


@dataclass(frozen=True, slots=True)
class LargeImportGeometryGuardResolutionResult:
    passed: bool
    corrected_full_count: int
    partial_count: int
    rejected_count: int
    manifest_checksum_sha256: str

    def checkpoint_payload(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "correctedFullCount": self.corrected_full_count,
            "partialCount": self.partial_count,
            "rejectedCount": self.rejected_count,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
        }


def guard_required(originals: Sequence[ManagedOriginal]) -> bool:
    return (
        len(originals) >= LARGE_IMPORT_MIN_SOURCE_COUNT
        or sum(_board_count(original) for original in originals) >= LARGE_IMPORT_MIN_BOARD_COUNT
    )


def select_representative_originals(
    originals: Sequence[ManagedOriginal],
    geometry_entries: Mapping[str, object],
    *,
    limit: int = LARGE_IMPORT_GUARD_SAMPLE_LIMIT,
) -> tuple[ManagedOriginal, ...]:
    if not originals or limit < 1:
        return ()
    ordered = tuple(originals)
    target_count = min(limit, len(ordered))
    indices = {0, len(ordered) // 2, len(ordered) - 1}
    if target_count > 1:
        indices.update(
            round(index * (len(ordered) - 1) / (target_count - 1)) for index in range(target_count)
        )
    first_by_bucket: dict[str, int] = {}
    for index, original in enumerate(ordered):
        entry = geometry_entries.get(original.checksum_sha256)
        bucket = geometry_quality_angle_bucket(entry if isinstance(entry, Mapping) else {})
        first_by_bucket.setdefault(bucket, index)
    indices.update(first_by_bucket.values())
    if len(indices) > max(target_count, len(first_by_bucket), 3):
        required = {0, len(ordered) // 2, len(ordered) - 1, *first_by_bucket.values()}
        optional = [index for index in sorted(indices) if index not in required]
        room = max(target_count, len(required)) - len(required)
        indices = required | set(optional[:room])
    return tuple(ordered[index] for index in sorted(indices))


def geometry_quality_angle_bucket(entry: Mapping[str, object]) -> str:
    registration_version = entry.get("registrationVersion")
    if registration_version == "manual-page-geometry-override-v1":
        return "manual-override"
    if isinstance(entry.get("automaticAnchorPass"), int):
        return "auto-anchor"
    inlier_ratio = _number(entry.get("inlierRatio"))
    reprojection = _number(entry.get("p95ReprojectionError"))
    red_coverage = _number(entry.get("meanRedEdgeCoverage"))
    if inlier_ratio is not None and inlier_ratio < 0.35:
        return "low-inlier"
    if reprojection is not None and reprojection > 1.5:
        return "high-reprojection"
    if red_coverage is not None and red_coverage < 0.8:
        return "low-edge-coverage"
    return "nominal"


def run_large_import_geometry_guard(
    *,
    artifact_root: Path,
    job_id: UUID,
    pipeline_fingerprint_sha256: str,
    source_manifest_checksum_sha256: str,
    page_geometry_manifest_checksum_sha256: str,
    originals: Sequence[ManagedOriginal],
    geometry_entries: Mapping[str, object],
    suite: ProductionGateAdapterSuite,
) -> LargeImportGeometryGuardResult:
    source_count = len(originals)
    active_board_count = sum(_board_count(original) for original in originals)
    if not guard_required(originals):
        return LargeImportGeometryGuardResult(
            required=False,
            passed=True,
            report_checksum_sha256=None,
            report_relative_path=None,
            source_count=source_count,
            active_board_count=active_board_count,
            sample_source_count=0,
            sample_board_count=0,
            page_registration_ready_rate=None,
            final_cell_grid_ready_rate=None,
            invariant_violation_count=0,
        )
    selected = select_representative_originals(originals, geometry_entries)
    input_payload = {
        "jobId": str(job_id),
        "pageGeometryManifestChecksumSha256": page_geometry_manifest_checksum_sha256,
        "pipelineFingerprintSha256": pipeline_fingerprint_sha256,
        "policyVersion": LARGE_IMPORT_GEOMETRY_GUARD_VERSION,
        "selectedSourceChecksums": [item.checksum_sha256 for item in selected],
        "sourceManifestChecksumSha256": source_manifest_checksum_sha256,
    }
    input_fingerprint = _checksum(input_payload)
    relative_path = f"data/image-geometry-guards/{job_id}.json"
    path = artifact_root.resolve().joinpath(*PurePosixPath(relative_path).parts)
    existing = _load_existing(path, input_fingerprint=input_fingerprint)
    if existing is None:
        observations = tuple(
            _evaluate_source(
                original,
                geometry_entries=geometry_entries,
                job_id=job_id,
                pipeline_fingerprint_sha256=pipeline_fingerprint_sha256,
                suite=suite,
            )
            for original in selected
        )
        report = _report(
            input_payload=input_payload,
            input_fingerprint=input_fingerprint,
            source_count=source_count,
            active_board_count=active_board_count,
            observations=observations,
        )
        report_checksum = _checksum(report)
        content = _canonical_bytes(
            {"report": report, "reportChecksumSha256": report_checksum},
            pretty=True,
        )
        _write_immutable(path, content)
    else:
        report, report_checksum = existing
    sample_board_count = _required_int(report, "sampleBoardCount")
    page_ready_count = _required_int(report, "pageRegistrationReadyBoardCount")
    final_ready_count = _required_int(report, "finalCellGridReadyBoardCount")
    invariant_violation_count = _required_int(report, "invariantViolationCount")
    page_rate = page_ready_count / sample_board_count if sample_board_count else 0.0
    final_rate = final_ready_count / sample_board_count if sample_board_count else 0.0
    return LargeImportGeometryGuardResult(
        required=True,
        passed=(final_rate >= LARGE_IMPORT_MIN_READY_RATE and invariant_violation_count == 0),
        report_checksum_sha256=report_checksum,
        report_relative_path=relative_path,
        source_count=source_count,
        active_board_count=active_board_count,
        sample_source_count=_required_int(report, "sampleSourceCount"),
        sample_board_count=sample_board_count,
        page_registration_ready_rate=page_rate,
        final_cell_grid_ready_rate=final_rate,
        invariant_violation_count=invariant_violation_count,
    )


def validate_large_import_geometry_guard_resolutions(
    *,
    artifact_root: Path,
    job_id: UUID,
    pipeline_fingerprint_sha256: str,
    originals: Sequence[ManagedOriginal],
    geometry_entries: Mapping[str, object],
    raw_result: LargeImportGeometryGuardResult,
    resolutions: GeometryGuardResolutionSet,
    suite: ProductionGateAdapterSuite,
) -> LargeImportGeometryGuardResolutionResult:
    if not raw_result.required or raw_result.report_relative_path is None:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "A resolution manifest cannot be applied without a required guard report.",
        )
    path = artifact_root.resolve().joinpath(*PurePosixPath(raw_result.report_relative_path).parts)
    try:
        envelope = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The raw geometry guard report is unavailable.",
        ) from error
    report = envelope.get("report") if isinstance(envelope, Mapping) else None
    if (
        not isinstance(report, Mapping)
        or _checksum(report) != raw_result.report_checksum_sha256
        or _required_int(report, "invariantViolationCount") != 0
    ):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "A resolution manifest cannot override raw invariant violations.",
        )
    deferred_keys = {
        (cast(str, source["sourceChecksumSha256"]), cast(int, board["positionIndex"]))
        for source in cast(Sequence[Mapping[str, object]], report.get("sources", []))
        for board in cast(Sequence[Mapping[str, object]], source.get("boards", []))
        if board.get("status") == "deferred"
    }
    if deferred_keys != resolutions.keys:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "The resolution manifest does not exactly cover the raw board failures.",
        )
    selected_checksums = report.get("selectedSourceChecksums")
    if not isinstance(selected_checksums, list):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The raw geometry guard report has no selected-source list.",
        )
    by_checksum = {item.checksum_sha256: item for item in originals}
    observations = tuple(
        _evaluate_source(
            by_checksum[checksum],
            geometry_entries=geometry_entries,
            job_id=job_id,
            pipeline_fingerprint_sha256=pipeline_fingerprint_sha256,
            suite=suite,
        )
        for checksum in selected_checksums
        if isinstance(checksum, str) and checksum in by_checksum
    )
    if len(observations) != len(selected_checksums):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "The raw guard sample differs from the current source manifest.",
        )
    boards = {
        (source.source_checksum_sha256, board.position_index): board
        for source in observations
        for board in source.board_results
    }
    if any(sum(source.invariant_violation_counts.values()) for source in observations):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "Resolved geometry introduced a production invariant violation.",
        )
    if any(board.status != "ready" for key, board in boards.items() if key not in resolutions.keys):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "Resolved execution introduced a new board-level geometry failure.",
        )
    for decision in resolutions.decisions:
        board = boards.get((decision.source_checksum_sha256, decision.position_index))
        expected = "ready" if decision.disposition == "corrected_full" else "deferred"
        expected_reason = {
            "partial": "operator_partial",
            "rejected": "operator_rejected",
        }.get(decision.disposition)
        if (
            board is None
            or board.status != expected
            or (expected_reason is not None and expected_reason not in board.reason_codes)
        ):
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
                "A resolved board did not reproduce its pinned production disposition.",
            )
    return LargeImportGeometryGuardResolutionResult(
        passed=True,
        corrected_full_count=sum(
            item.disposition == "corrected_full" for item in resolutions.decisions
        ),
        partial_count=sum(item.disposition == "partial" for item in resolutions.decisions),
        rejected_count=sum(item.disposition == "rejected" for item in resolutions.decisions),
        manifest_checksum_sha256=resolutions.manifest_checksum_sha256,
    )


def build_board_level_guard_report_from_legacy(
    *,
    legacy_report: Mapping[str, object],
    legacy_report_checksum_sha256: str,
    observations: Sequence[GridProfileGateSourceResult],
) -> dict[str, object]:
    """Derive v2 diagnostics without changing the immutable v1 report."""

    if _checksum(legacy_report) != legacy_report_checksum_sha256:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
            "The legacy geometry guard report checksum is invalid.",
        )
    selected = legacy_report.get("selectedSourceChecksums")
    if not isinstance(selected, list) or any(not isinstance(value, str) for value in selected):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The legacy geometry guard report has no selected-source snapshot.",
        )
    by_checksum = {item.source_checksum_sha256: item for item in observations}
    if len(by_checksum) != len(observations) or set(by_checksum) != set(selected):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
            "The reconstructed board diagnostics differ from the legacy source sample.",
        )
    ordered = tuple(by_checksum[checksum] for checksum in selected)
    required_keys = (
        "jobId",
        "pageGeometryManifestChecksumSha256",
        "pipelineFingerprintSha256",
        "sourceManifestChecksumSha256",
    )
    input_payload = {key: legacy_report.get(key) for key in required_keys}
    if any(not isinstance(value, str) or not value for value in input_payload.values()):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The legacy geometry guard report is missing pinned inputs.",
        )
    input_payload.update(
        {
            "policyVersion": LARGE_IMPORT_GEOMETRY_GUARD_VERSION,
            "selectedSourceChecksums": list(selected),
            "derivedFromReportChecksumSha256": legacy_report_checksum_sha256,
        }
    )
    input_fingerprint = _checksum(input_payload)
    return _report(
        input_payload=input_payload,
        input_fingerprint=input_fingerprint,
        source_count=_required_int(legacy_report, "sourceCount"),
        active_board_count=_required_int(legacy_report, "activeBoardCount"),
        observations=ordered,
    )


def _evaluate_source(
    original: ManagedOriginal,
    *,
    geometry_entries: Mapping[str, object],
    job_id: UUID,
    pipeline_fingerprint_sha256: str,
    suite: ProductionGateAdapterSuite,
) -> GridProfileGateSourceResult:
    expected = _board_count(original)
    entry = geometry_entries.get(original.checksum_sha256)
    bucket = geometry_quality_angle_bucket(entry if isinstance(entry, Mapping) else {})
    try:
        result = run_grid_profile_gate_source(
            suite=suite,
            context=ImageStageContext(
                job_id=job_id,
                file_execution_key=file_execution_key(
                    original.checksum_sha256,
                    pipeline_fingerprint_sha256,
                ),
                source_checksum_sha256=original.checksum_sha256,
                source_relative_path=_data_relative_path(original.managed_relative_path),
                pipeline_fingerprint=pipeline_fingerprint_sha256,
                previous_results={},
                attested_sequence_range=(
                    cast(int, original.sequence_range_start),
                    cast(int, original.sequence_range_end),
                ),
            ),
            quality_angle_bucket=bucket,
            baseline_final_cell_grid_ready_board_count=expected,
        )
        return replace(result, source_relative_path=original.source_relative_path)
    except JobHandlerError as error:
        return GridProfileGateSourceResult(
            source_checksum_sha256=original.checksum_sha256,
            quality_angle_bucket=bucket,
            active_board_count=expected,
            page_registration_ready_board_count=0,
            final_cell_grid_ready_board_count=0,
            baseline_final_cell_grid_ready_board_count=expected,
            invariant_violation_counts={
                "checksum": 0,
                "ordering": 0,
                "topology": 0,
                "overlap": 0,
                "sourceSupport": 0,
            },
            deferral_reason_counts={error.code: expected},
            source_relative_path=original.source_relative_path,
            sequence_range_start=cast(int, original.sequence_range_start),
            sequence_range_end=cast(int, original.sequence_range_end),
            board_results=tuple(
                GridProfileGateBoardResult(
                    position_index=position,
                    sequence_number=cast(int, original.sequence_range_start) + position,
                    status="deferred",
                    reason_codes=(error.code,),
                )
                for position in range(expected)
            ),
        )


def _report(
    *,
    input_payload: Mapping[str, object],
    input_fingerprint: str,
    source_count: int,
    active_board_count: int,
    observations: Sequence[GridProfileGateSourceResult],
) -> dict[str, object]:
    sample_boards = sum(item.active_board_count for item in observations)
    page_ready = sum(item.page_registration_ready_board_count for item in observations)
    final_ready = sum(item.final_cell_grid_ready_board_count for item in observations)
    invariant_counts = Counter[str]()
    deferral_counts = Counter[str]()
    for item in observations:
        invariant_counts.update(item.invariant_violation_counts)
        deferral_counts.update(item.deferral_reason_counts)
    invariant_violation_count = sum(invariant_counts.values())
    return {
        **input_payload,
        "schemaVersion": LARGE_IMPORT_GEOMETRY_GUARD_REPORT_SCHEMA,
        "inputFingerprintSha256": input_fingerprint,
        "sourceCount": source_count,
        "activeBoardCount": active_board_count,
        "sampleSourceCount": len(observations),
        "sampleBoardCount": sample_boards,
        "pageRegistrationReadyBoardCount": page_ready,
        "finalCellGridReadyBoardCount": final_ready,
        "minimumFinalCellGridReadyRate": LARGE_IMPORT_MIN_READY_RATE,
        "invariantViolationCount": invariant_violation_count,
        "invariantViolationCounts": dict(sorted(invariant_counts.items())),
        "deferralReasonCounts": dict(sorted(deferral_counts.items())),
        "passed": (
            (final_ready / sample_boards if sample_boards else 0.0) >= LARGE_IMPORT_MIN_READY_RATE
            and invariant_violation_count == 0
        ),
        "sources": [
            {
                "sourceChecksumSha256": item.source_checksum_sha256,
                "sourceRelativePath": item.source_relative_path,
                "sequenceRangeStart": item.sequence_range_start,
                "sequenceRangeEnd": item.sequence_range_end,
                "qualityAngleBucket": item.quality_angle_bucket,
                "activeBoardCount": item.active_board_count,
                "pageRegistrationReadyBoardCount": (item.page_registration_ready_board_count),
                "finalCellGridReadyBoardCount": item.final_cell_grid_ready_board_count,
                "invariantViolationCounts": dict(item.invariant_violation_counts),
                "deferralReasonCounts": dict(item.deferral_reason_counts),
                "boards": [
                    {
                        "positionIndex": board.position_index,
                        "sequenceNumber": board.sequence_number,
                        "status": board.status,
                        "reasonCodes": list(board.reason_codes),
                        "pageGeometry": board.page_geometry,
                        "analysisQuad": board.analysis_quad,
                        "symbolGridQuad": board.symbol_grid_quad,
                        "evidence": board.evidence,
                    }
                    for board in item.board_results
                ],
            }
            for item in observations
        ],
    }


def _load_existing(
    path: Path,
    *,
    input_fingerprint: str,
) -> tuple[dict[str, object], str] | None:
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The persisted geometry guard report is invalid.",
        ) from error
    if not isinstance(envelope, Mapping) or not isinstance(envelope.get("report"), Mapping):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            "The persisted geometry guard report has an invalid envelope.",
        )
    report = dict(cast(Mapping[str, object], envelope["report"]))
    checksum = envelope.get("reportChecksumSha256")
    if (
        not isinstance(checksum, str)
        or _checksum(report) != checksum
        or report.get("inputFingerprintSha256") != input_fingerprint
    ):
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT",
            "The persisted geometry guard report differs from the pinned import.",
        )
    return report, checksum


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise JobHandlerError(
                "IMAGE_GEOMETRY_GUARD_REPORT_COLLISION",
                "The immutable geometry guard report already has different content.",
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-guard-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise JobHandlerError(
                    "IMAGE_GEOMETRY_GUARD_REPORT_COLLISION",
                    "The immutable geometry guard report already has different content.",
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


def _board_count(original: ManagedOriginal) -> int:
    start = original.sequence_range_start
    end = original.sequence_range_end
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_RANGE_INVALID",
            "A v0.10 guard source has no valid attested sequence range.",
        )
    return end - start + 1


def _data_relative_path(value: str) -> str:
    parts = PurePosixPath(value).parts
    return PurePosixPath(*parts[1:]).as_posix() if parts and parts[0] == "data" else value


def _required_int(value: Mapping[str, object], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_REPORT_INVALID",
            f"The geometry guard report has an invalid {key}.",
        )
    return raw


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value)


def _canonical_bytes(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
            "ascii"
        )
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


__all__ = [
    "LARGE_IMPORT_GEOMETRY_GUARD_VERSION",
    "LARGE_IMPORT_GEOMETRY_GUARD_REPORT_SCHEMA",
    "LargeImportGeometryGuardResult",
    "LargeImportGeometryGuardResolutionResult",
    "build_board_level_guard_report_from_legacy",
    "geometry_quality_angle_bucket",
    "guard_required",
    "run_large_import_geometry_guard",
    "validate_large_import_geometry_guard_resolutions",
    "select_representative_originals",
]
