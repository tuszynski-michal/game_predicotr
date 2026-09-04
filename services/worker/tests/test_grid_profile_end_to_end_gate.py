from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_worker.images.grid_profile_end_to_end_gate import (
    GridProfileEndToEndGateError,
    GridProfileGateSourceResult,
    build_grid_profile_end_to_end_gate_report,
    run_grid_profile_gate_source,
)
from game_predictor_worker.images.pipeline_execution import (
    FunctionImageStageAdapter,
    ImageStageContext,
)


def _result(index: int) -> GridProfileGateSourceResult:
    return GridProfileGateSourceResult(
        source_checksum_sha256=hashlib.sha256(f"source-{index}".encode()).hexdigest(),
        quality_angle_bucket=f"bucket-{index % 5}",
        active_board_count=9,
        page_registration_ready_board_count=9,
        final_cell_grid_ready_board_count=9,
        baseline_final_cell_grid_ready_board_count=9,
        invariant_violation_counts={
            "checksum": 0,
            "ordering": 0,
            "topology": 0,
            "overlap": 0,
            "sourceSupport": 0,
        },
        deferral_reason_counts={},
        known_regression_case_count=1 if index == 0 else 0,
        covered_regression_case_count=1 if index == 0 else 0,
    )


def test_report_aggregation_is_deterministic_and_preserves_production_counters() -> None:
    results = [_result(index) for index in range(100)]

    first = build_grid_profile_end_to_end_gate_report(
        cohort_checksum_sha256="a" * 64,
        regression_corpus_version="grid-regressions-v1",
        results=reversed(results),
    )
    second = build_grid_profile_end_to_end_gate_report(
        cohort_checksum_sha256="a" * 64,
        regression_corpus_version="grid-regressions-v1",
        results=results,
    )

    assert first == second
    assert first["sourceCount"] == 100
    assert first["activeBoardCount"] == 900
    assert first["finalCellGridReadyBoardCount"] == 900
    assert first["qualityAngleBucketCounts"] == {
        f"bucket-{index}": 20 for index in range(5)
    }
    assert first["knownRegressionCaseCount"] == 1
    assert first["coveredRegressionCaseCount"] == 1


def test_report_rejects_missing_production_invariant_counter() -> None:
    result = _result(0)
    invalid = GridProfileGateSourceResult(
        source_checksum_sha256=result.source_checksum_sha256,
        quality_angle_bucket=result.quality_angle_bucket,
        active_board_count=9,
        page_registration_ready_board_count=9,
        final_cell_grid_ready_board_count=9,
        baseline_final_cell_grid_ready_board_count=9,
        invariant_violation_counts={"checksum": 0},
    )

    with pytest.raises(GridProfileEndToEndGateError, match="production invariant"):
        build_grid_profile_end_to_end_gate_report(
            cohort_checksum_sha256="a" * 64,
            regression_corpus_version="grid-regressions-v1",
            results=[invalid],
        )


def test_source_runner_executes_production_stage_contract_through_final_crops() -> None:
    checksum = "a" * 64
    called: list[str] = []

    def adapter(stage: str, payload: dict[str, object]) -> FunctionImageStageAdapter:
        def run(context: ImageStageContext) -> dict[str, object]:
            called.append(stage)
            if stage != "discovery":
                assert called[-2] in context.previous_results
            return payload

        return FunctionImageStageAdapter(stage, f"{stage}-v1", run)

    boards = [{"positionIndex": position} for position in range(9)]
    crop_boards = [
        {
            "positionIndex": position,
            "cells": [
                {"rowIndex": row, "columnIndex": column}
                for row in range(3)
                for column in range(5)
            ],
        }
        for position in range(9)
    ]
    suite = SimpleNamespace(
        adapters=lambda: (
            adapter("discovery", {"sourceChecksumSha256": checksum}),
            adapter("normalization", {}),
            adapter("board_detection", {"boards": boards}),
            adapter(
                "board_cell_geometry",
                {
                    "boards": [{**board, "status": "verified"} for board in boards],
                    "gridRows": 3,
                    "gridColumns": 5,
                },
            ),
            adapter("board_crops", {"boards": crop_boards, "deferredBoards": []}),
            adapter("sequence_ocr", {}),
        )
    )
    context = ImageStageContext(
        job_id=uuid4(),
        file_execution_key="b" * 64,
        source_checksum_sha256=checksum,
        source_relative_path="seq_1_9.jpg",
        pipeline_fingerprint="c" * 64,
        previous_results={},
        attested_sequence_range=(1, 9),
    )

    result = run_grid_profile_gate_source(
        suite=suite,
        context=context,
        quality_angle_bucket="front-clear",
        baseline_final_cell_grid_ready_board_count=9,
    )

    assert called == [
        "discovery",
        "normalization",
        "board_detection",
        "board_cell_geometry",
        "board_crops",
    ]
    assert result.page_registration_ready_board_count == 9
    assert result.final_cell_grid_ready_board_count == 9
    assert result.invariant_violation_counts == {
        "checksum": 0,
        "ordering": 0,
        "topology": 0,
        "overlap": 0,
        "sourceSupport": 0,
    }
