"""Deterministic aggregation of production page-and-cell gate observations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from game_predictor_api.domain.grid_calibration import (
    GRID_END_TO_END_GATE_POLICY_V1,
    GRID_END_TO_END_GATE_REPORT_SCHEMA_V1,
)

from .pipeline_execution import ImageStageContext, VersionedImageStageAdapter

INVARIANT_NAMES = ("checksum", "ordering", "topology", "overlap", "sourceSupport")


class GridProfileEndToEndGateError(ValueError):
    """Stable failure while assembling an immutable gate report."""


class ProductionGateAdapterSuite(Protocol):
    def adapters(self) -> tuple[VersionedImageStageAdapter, ...]: ...


@dataclass(frozen=True, slots=True)
class GridProfileGateSourceResult:
    source_checksum_sha256: str
    quality_angle_bucket: str
    active_board_count: int
    page_registration_ready_board_count: int
    final_cell_grid_ready_board_count: int
    baseline_final_cell_grid_ready_board_count: int
    invariant_violation_counts: Mapping[str, int] = field(default_factory=dict)
    deferral_reason_counts: Mapping[str, int] = field(default_factory=dict)
    known_regression_case_count: int = 0
    covered_regression_case_count: int = 0


def run_grid_profile_gate_source(
    *,
    suite: ProductionGateAdapterSuite,
    context: ImageStageContext,
    quality_angle_bucket: str,
    baseline_final_cell_grid_ready_board_count: int,
    known_regression_case_count: int = 0,
    covered_regression_case_count: int = 0,
) -> GridProfileGateSourceResult:
    """Execute the exact production adapters through final board-cell crops."""

    if context.attested_sequence_range is None:
        raise GridProfileEndToEndGateError("A gate source requires an attested board range.")
    start, end = context.attested_sequence_range
    expected_board_count = end - start + 1
    if expected_board_count < 1:
        raise GridProfileEndToEndGateError("The attested gate range is invalid.")
    outputs: dict[str, Mapping[str, object]] = {}
    for adapter in suite.adapters():
        stage_context = replace(context, previous_results=dict(outputs))
        outputs[adapter.stage] = dict(adapter.execute(stage_context))
        if adapter.stage == "board_crops":
            break
    required = {"discovery", "board_detection", "board_cell_geometry", "board_crops"}
    if not required.issubset(outputs):
        raise GridProfileEndToEndGateError(
            "The production adapter suite did not reach final board-cell crops."
        )
    discovery = outputs["discovery"]
    detection_boards = _mapping_sequence(outputs["board_detection"].get("boards"))
    geometry = outputs["board_cell_geometry"]
    geometry_boards = _mapping_sequence(geometry.get("boards"))
    crops = outputs["board_crops"]
    crop_boards = _mapping_sequence(crops.get("boards"))
    expected_positions = list(range(expected_board_count))
    detection_positions = _positions(detection_boards)
    geometry_positions = _positions(geometry_boards)
    crop_positions = _positions(crop_boards)
    checksum_violations = int(
        discovery.get("sourceChecksumSha256") != context.source_checksum_sha256
    )
    ordering_violations = sum(
        positions != expected_positions
        for positions in (detection_positions, geometry_positions)
    )
    topology_violations = int(
        geometry.get("gridRows") != 3 or geometry.get("gridColumns") != 5
    )
    final_positions: set[int] = set()
    for board in crop_boards:
        position = board.get("positionIndex")
        cells = _mapping_sequence(board.get("cells"))
        identities = {
            (cell.get("rowIndex"), cell.get("columnIndex"))
            for cell in cells
        }
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position not in expected_positions
            or len(cells) != 15
            or identities != {(row, column) for row in range(3) for column in range(5)}
        ):
            topology_violations += 1
            continue
        final_positions.add(position)
    if crop_positions != sorted(crop_positions) or len(crop_positions) != len(set(crop_positions)):
        ordering_violations += 1
    deferrals: Counter[str] = Counter()
    deferred_by_position: dict[int, str] = {}
    for board in geometry_boards:
        if board.get("status") == "verified":
            continue
        position = board.get("positionIndex")
        reason = board.get("reasonCode") or board.get("estimatorFailureReason")
        if isinstance(position, int) and isinstance(reason, str):
            deferred_by_position[position] = reason
    for board in _mapping_sequence(crops.get("deferredBoards")):
        position = board.get("positionIndex")
        reason = board.get("reasonCode") or board.get("estimatorFailureReason")
        if isinstance(position, int) and isinstance(reason, str):
            deferred_by_position[position] = reason
    missing_positions = set(expected_positions) - final_positions
    for position in sorted(missing_positions):
        deferrals[deferred_by_position.get(position, "FINAL_CELL_GRID_OUTPUT_MISSING")] += 1
    all_reasons = tuple(deferred_by_position.values())
    invariant_counts = {
        "checksum": checksum_violations,
        "ordering": ordering_violations,
        "topology": topology_violations,
        "overlap": sum("OVERLAP" in reason for reason in all_reasons),
        "sourceSupport": sum("SOURCE_SUPPORT" in reason for reason in all_reasons),
    }
    page_ready = (
        expected_board_count
        if detection_positions == expected_positions and not checksum_violations
        else 0
    )
    return GridProfileGateSourceResult(
        source_checksum_sha256=context.source_checksum_sha256,
        quality_angle_bucket=quality_angle_bucket,
        active_board_count=expected_board_count,
        page_registration_ready_board_count=page_ready,
        final_cell_grid_ready_board_count=len(final_positions),
        baseline_final_cell_grid_ready_board_count=(
            baseline_final_cell_grid_ready_board_count
        ),
        invariant_violation_counts=invariant_counts,
        deferral_reason_counts=dict(deferrals),
        known_regression_case_count=known_regression_case_count,
        covered_regression_case_count=covered_regression_case_count,
    )


def build_grid_profile_end_to_end_gate_report(
    *,
    cohort_checksum_sha256: str,
    regression_corpus_version: str,
    results: Iterable[GridProfileGateSourceResult],
) -> dict[str, object]:
    ordered = sorted(results, key=lambda item: item.source_checksum_sha256)
    if not ordered:
        raise GridProfileEndToEndGateError("The end-to-end gate corpus is empty.")
    if not regression_corpus_version.strip():
        raise GridProfileEndToEndGateError("The regression corpus version is required.")
    seen: set[str] = set()
    bucket_counts: Counter[str] = Counter()
    invariant_counts: Counter[str] = Counter({name: 0 for name in INVARIANT_NAMES})
    deferral_counts: Counter[str] = Counter()
    sources: list[dict[str, object]] = []
    active_boards = registration_ready = final_ready = baseline_ready = 0
    known_regressions = covered_regressions = 0
    for result in ordered:
        _validate_result(result, seen)
        seen.add(result.source_checksum_sha256)
        bucket_counts[result.quality_angle_bucket] += 1
        invariant_counts.update(result.invariant_violation_counts)
        deferral_counts.update(result.deferral_reason_counts)
        active_boards += result.active_board_count
        registration_ready += result.page_registration_ready_board_count
        final_ready += result.final_cell_grid_ready_board_count
        baseline_ready += result.baseline_final_cell_grid_ready_board_count
        known_regressions += result.known_regression_case_count
        covered_regressions += result.covered_regression_case_count
        sources.append(
            {
                "sourceChecksumSha256": result.source_checksum_sha256,
                "qualityAngleBucket": result.quality_angle_bucket,
                "activeBoardCount": result.active_board_count,
            }
        )
    corpus = {"schemaVersion": 1, "sources": sources}
    return {
        "schemaVersion": GRID_END_TO_END_GATE_REPORT_SCHEMA_V1,
        "policyVersion": GRID_END_TO_END_GATE_POLICY_V1,
        "cohortChecksumSha256": _sha256_text(cohort_checksum_sha256),
        "corpusChecksumSha256": _checksum(corpus),
        "sourceCount": len(sources),
        "activeBoardCount": active_boards,
        "pageRegistrationReadyBoardCount": registration_ready,
        "finalCellGridReadyBoardCount": final_ready,
        "baselineFinalCellGridReadyBoardCount": baseline_ready,
        "qualityAngleBucketCounts": dict(sorted(bucket_counts.items())),
        "invariantViolationCounts": dict(sorted(invariant_counts.items())),
        "deferralReasonCounts": dict(sorted(deferral_counts.items())),
        "knownRegressionCaseCount": known_regressions,
        "coveredRegressionCaseCount": covered_regressions,
        "regressionCorpusVersion": regression_corpus_version,
        "sources": sources,
    }


def _validate_result(result: GridProfileGateSourceResult, seen: set[str]) -> None:
    checksum = _sha256_text(result.source_checksum_sha256)
    if checksum in seen:
        raise GridProfileEndToEndGateError("The gate corpus contains a duplicate source.")
    if not result.quality_angle_bucket.strip():
        raise GridProfileEndToEndGateError("Every source requires a quality/angle bucket.")
    counters = (
        result.active_board_count,
        result.page_registration_ready_board_count,
        result.final_cell_grid_ready_board_count,
        result.baseline_final_cell_grid_ready_board_count,
        result.known_regression_case_count,
        result.covered_regression_case_count,
    )
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counters
    ):
        raise GridProfileEndToEndGateError("Gate counters must be non-negative integers.")
    if (
        result.page_registration_ready_board_count > result.active_board_count
        or result.final_cell_grid_ready_board_count
        > result.page_registration_ready_board_count
        or result.baseline_final_cell_grid_ready_board_count > result.active_board_count
        or result.covered_regression_case_count > result.known_regression_case_count
    ):
        raise GridProfileEndToEndGateError("Gate counters violate the production stage order.")
    if set(result.invariant_violation_counts) != set(INVARIANT_NAMES):
        raise GridProfileEndToEndGateError("Every production invariant requires a counter.")
    _validate_count_mapping(result.invariant_violation_counts)
    _validate_count_mapping(result.deferral_reason_counts)


def _validate_count_mapping(value: Mapping[str, int]) -> None:
    if any(
        not key or not isinstance(count, int) or isinstance(count, bool) or count < 0
        for key, count in value.items()
    ):
        raise GridProfileEndToEndGateError("Gate reason counters are invalid.")


def _mapping_sequence(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _positions(values: Sequence[Mapping[str, object]]) -> list[int]:
    return [
        position
        for value in values
        if isinstance((position := value.get("positionIndex")), int)
        and not isinstance(position, bool)
    ]


def _sha256_text(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise GridProfileEndToEndGateError("A gate checksum is not lowercase SHA-256.")
    return value


def _checksum(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "GridProfileEndToEndGateError",
    "GridProfileGateSourceResult",
    "build_grid_profile_end_to_end_gate_report",
    "run_grid_profile_gate_source",
]
