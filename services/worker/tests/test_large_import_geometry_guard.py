import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_worker.images.geometry_guard_resolution import (
    GeometryGuardBoardResolution,
    GeometryGuardResolutionSet,
)
from game_predictor_worker.images.large_import_geometry_guard import (
    LARGE_IMPORT_GEOMETRY_GUARD_REPORT_SCHEMA,
    build_board_level_guard_report_from_legacy,
    guard_required,
    reconstruct_board_level_guard_report_from_legacy,
    run_large_import_geometry_guard,
    select_representative_originals,
    validate_large_import_geometry_guard_resolutions,
)
from game_predictor_worker.images.pipeline_execution import (
    FunctionImageStageAdapter,
    ImageStageContext,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginal
from game_predictor_worker.jobs.runtime import JobHandlerError


def _original(index: int, *, board_count: int = 9) -> ManagedOriginal:
    start = index * board_count + 1
    checksum = f"{index + 1:064x}"
    return ManagedOriginal(
        checksum_sha256=checksum,
        source_relative_path=f"seq_{start}_{start + board_count - 1}.jpg",
        managed_relative_path=f"data/originals/{checksum[:2]}/{checksum}.jpg",
        size_bytes=100,
        sequence_range_start=start,
        sequence_range_end=start + board_count - 1,
        sequence_range_source="filename",
    )


class _Suite:
    def __init__(self, *, final_board_count: int = 9) -> None:
        self.final_board_count = final_board_count
        self.calls = 0

    def adapters(self) -> tuple[FunctionImageStageAdapter, ...]:
        self.calls += 1

        def discovery(context: ImageStageContext) -> dict[str, object]:
            return {"sourceChecksumSha256": context.source_checksum_sha256}

        def normalization(_context: ImageStageContext) -> dict[str, object]:
            return {}

        def board_detection(context: ImageStageContext) -> dict[str, object]:
            return {
                "boards": [
                    {**board, "geometry": {"quad": _quad(board["positionIndex"])}}
                    for board in _boards(context, count=9)
                ]
            }

        def board_cell_geometry(context: ImageStageContext) -> dict[str, object]:
            return {
                "gridRows": 3,
                "gridColumns": 5,
                "boards": [
                    {
                        **board,
                        "status": (
                            "verified"
                            if board["positionIndex"] < self.final_board_count
                            else "deferred"
                        ),
                        "reasonCode": (
                            None
                            if board["positionIndex"] < self.final_board_count
                            else "incomplete_lattice"
                        ),
                    }
                    for board in _boards(context, count=9)
                ],
                "structuredGeometry": {
                    "boards": [
                        {
                            **board,
                            "analysisQuad": _quad(board["positionIndex"]),
                            "symbolGridQuad": (
                                _quad(board["positionIndex"])
                                if board["positionIndex"] < self.final_board_count
                                else None
                            ),
                            "evidence": {"supportedIntersectionCount": 24},
                        }
                        for board in _boards(context, count=9)
                    ]
                },
            }

        def board_crops(context: ImageStageContext) -> dict[str, object]:
            return {
                "boards": [
                    {
                        **board,
                        "cells": [
                            {"rowIndex": row, "columnIndex": column}
                            for row in range(3)
                            for column in range(5)
                        ],
                    }
                    for board in _boards(context, count=self.final_board_count)
                ],
                "deferredBoards": [
                    {"positionIndex": position, "reasonCode": "INCOMPLETE_LATTICE"}
                    for position in range(self.final_board_count, 9)
                ],
            }

        return (
            FunctionImageStageAdapter("discovery", "test-v1", discovery),
            FunctionImageStageAdapter("normalization", "test-v1", normalization),
            FunctionImageStageAdapter("board_detection", "test-v1", board_detection),
            FunctionImageStageAdapter("board_cell_geometry", "test-v1", board_cell_geometry),
            FunctionImageStageAdapter("board_crops", "test-v1", board_crops),
        )


def _boards(context: ImageStageContext, *, count: int) -> list[dict[str, int]]:
    del context
    return [{"positionIndex": position} for position in range(count)]


def _quad(position: int) -> list[dict[str, float]]:
    left = float(position * 10)
    return [
        {"x": left, "y": 0.0},
        {"x": left + 8.0, "y": 0.0},
        {"x": left + 8.0, "y": 6.0},
        {"x": left, "y": 6.0},
    ]


def _entries(originals: tuple[ManagedOriginal, ...]) -> dict[str, object]:
    return {
        original.checksum_sha256: {
            "status": "registered",
            "inlierRatio": 0.9,
            "p95ReprojectionError": 0.4,
            "meanRedEdgeCoverage": 0.95,
        }
        for original in originals
    }


def test_guard_threshold_is_sources_or_active_boards() -> None:
    assert not guard_required(tuple(_original(index, board_count=4) for index in range(99)))
    assert guard_required(tuple(_original(index, board_count=9) for index in range(56)))
    assert guard_required(tuple(_original(index, board_count=4) for index in range(100)))


def test_representative_selection_is_deterministic_and_covers_boundaries_and_buckets() -> None:
    originals = tuple(_original(index) for index in range(120))
    entries = _entries(originals)
    entries[originals[7].checksum_sha256] = {
        "status": "registered",
        "registrationVersion": "manual-page-geometry-override-v1",
    }
    entries[originals[11].checksum_sha256] = {
        "status": "registered",
        "inlierRatio": 0.2,
    }

    first = select_representative_originals(originals, entries)
    second = select_representative_originals(originals, entries)

    assert first == second
    assert originals[0] in first
    assert originals[len(originals) // 2] in first
    assert originals[-1] in first
    assert originals[7] in first
    assert originals[11] in first
    assert len(first) <= 25


def test_guard_persists_and_reuses_exact_success_report(tmp_path: Path) -> None:
    originals = tuple(_original(index) for index in range(56))
    suite = _Suite()
    kwargs = {
        "artifact_root": tmp_path,
        "job_id": UUID("11111111-1111-1111-1111-111111111111"),
        "pipeline_fingerprint_sha256": "a" * 64,
        "source_manifest_checksum_sha256": "b" * 64,
        "page_geometry_manifest_checksum_sha256": "c" * 64,
        "originals": originals,
        "geometry_entries": _entries(originals),
        "suite": suite,
    }

    first = run_large_import_geometry_guard(**kwargs)
    first_call_count = suite.calls
    second = run_large_import_geometry_guard(**kwargs)

    assert first.required and first.passed
    assert first.final_cell_grid_ready_rate == 1.0
    assert first.invariant_violation_count == 0
    assert second == first
    assert suite.calls == first_call_count
    assert first.report_checksum_sha256 is not None


def test_guard_rejects_systemically_incomplete_final_grids(tmp_path: Path) -> None:
    originals = tuple(_original(index) for index in range(56))

    result = run_large_import_geometry_guard(
        artifact_root=tmp_path,
        job_id=UUID("22222222-2222-2222-2222-222222222222"),
        pipeline_fingerprint_sha256="a" * 64,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
        originals=originals,
        geometry_entries=_entries(originals),
        suite=_Suite(final_board_count=8),
    )

    assert result.required and not result.passed
    assert result.page_registration_ready_rate == 1.0
    assert result.final_cell_grid_ready_rate == pytest.approx(8 / 9)
    assert result.report_relative_path is not None
    envelope = json.loads((tmp_path / result.report_relative_path).read_text(encoding="ascii"))
    report = envelope["report"]
    assert report["schemaVersion"] == LARGE_IMPORT_GEOMETRY_GUARD_REPORT_SCHEMA
    failed = [
        board
        for source in report["sources"]
        for board in source["boards"]
        if board["status"] == "deferred"
    ]
    assert len(failed) == report["sampleSourceCount"]
    assert failed[0]["positionIndex"] == 8
    assert failed[0]["sequenceNumber"] == 9
    assert failed[0]["reasonCodes"] == ["incomplete_lattice", "INCOMPLETE_LATTICE"]
    assert failed[0]["pageGeometry"]["quad"] == _quad(8)
    assert failed[0]["analysisQuad"] == _quad(8)
    assert failed[0]["symbolGridQuad"] is None
    assert failed[0]["evidence"] == {"supportedIntersectionCount": 24}


def test_exact_resolution_manifest_allows_only_reproduced_full_corrections(
    tmp_path: Path,
) -> None:
    originals = tuple(_original(index) for index in range(56))
    job_id = UUID("55555555-5555-5555-5555-555555555555")
    raw = run_large_import_geometry_guard(
        artifact_root=tmp_path,
        job_id=job_id,
        pipeline_fingerprint_sha256="a" * 64,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
        originals=originals,
        geometry_entries=_entries(originals),
        suite=_Suite(final_board_count=8),
    )
    selected = select_representative_originals(originals, _entries(originals))
    resolutions = GeometryGuardResolutionSet(
        manifest_id=UUID("66666666-6666-6666-6666-666666666666"),
        manifest_checksum_sha256="d" * 64,
        guard_job_id=UUID("77777777-7777-7777-7777-777777777777"),
        guard_report_checksum_sha256="e" * 64,
        decisions=tuple(
            GeometryGuardBoardResolution(
                source_checksum_sha256=original.checksum_sha256,
                source_relative_path=original.source_relative_path,
                position_index=8,
                sequence_number=original.sequence_range_end or 0,
                disposition="corrected_full",
                symbol_grid_quad=tuple(
                    {"x": int(point["x"]), "y": int(point["y"])} for point in _quad(8)
                ),
                unavailable_cell_indices=(),
                decision_checksum_sha256="f" * 64,
            )
            for original in selected
        ),
    )

    result = validate_large_import_geometry_guard_resolutions(
        artifact_root=tmp_path,
        job_id=job_id,
        pipeline_fingerprint_sha256="a" * 64,
        originals=originals,
        geometry_entries=_entries(originals),
        raw_result=raw,
        resolutions=resolutions,
        suite=_Suite(final_board_count=9),
    )

    assert result.passed
    assert result.corrected_full_count == len(selected)
    assert result.partial_count == result.rejected_count == 0


def test_legacy_report_is_upgraded_without_mutation() -> None:
    source = _original(0)
    suite = _Suite(final_board_count=8)
    from game_predictor_worker.images.grid_profile_end_to_end_gate import (
        run_grid_profile_gate_source,
    )
    from game_predictor_worker.images.pipeline_contract import file_execution_key

    result = run_grid_profile_gate_source(
        suite=suite,
        context=ImageStageContext(
            job_id=UUID("44444444-4444-4444-4444-444444444444"),
            file_execution_key=file_execution_key(source.checksum_sha256, "a" * 64),
            source_checksum_sha256=source.checksum_sha256,
            source_relative_path=source.source_relative_path,
            pipeline_fingerprint="a" * 64,
            previous_results={},
            attested_sequence_range=(1, 9),
        ),
        quality_angle_bucket="nominal",
        baseline_final_cell_grid_ready_board_count=9,
    )
    legacy = {
        "jobId": "44444444-4444-4444-4444-444444444444",
        "pageGeometryManifestChecksumSha256": "b" * 64,
        "pipelineFingerprintSha256": "a" * 64,
        "sourceManifestChecksumSha256": "c" * 64,
        "selectedSourceChecksums": [source.checksum_sha256],
        "sourceCount": 100,
        "activeBoardCount": 900,
    }
    legacy_before = json.dumps(legacy, sort_keys=True)
    legacy_checksum = hashlib.sha256(
        json.dumps(legacy, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()

    upgraded = build_board_level_guard_report_from_legacy(
        legacy_report=legacy,
        legacy_report_checksum_sha256=legacy_checksum,
        observations=(result,),
    )

    assert json.dumps(legacy, sort_keys=True) == legacy_before
    assert upgraded["derivedFromReportChecksumSha256"] == legacy_checksum
    assert upgraded["sources"][0]["boards"][8]["sequenceNumber"] == 9


def test_legacy_reconstruction_persists_a_content_addressed_v2_report(
    tmp_path: Path,
) -> None:
    source = _original(0)
    source_job_id = UUID("44444444-4444-4444-4444-444444444444")
    legacy = {
        "jobId": str(source_job_id),
        "pageGeometryManifestChecksumSha256": "b" * 64,
        "pipelineFingerprintSha256": "a" * 64,
        "sourceManifestChecksumSha256": "c" * 64,
        "selectedSourceChecksums": [source.checksum_sha256],
        "sourceCount": 100,
        "activeBoardCount": 900,
    }
    legacy_checksum = hashlib.sha256(
        json.dumps(
            legacy,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()

    first = reconstruct_board_level_guard_report_from_legacy(
        artifact_root=tmp_path,
        source_job_id=source_job_id,
        pipeline_fingerprint_sha256="a" * 64,
        legacy_report=legacy,
        legacy_report_checksum_sha256=legacy_checksum,
        originals=(source,),
        geometry_entries=_entries((source,)),
        suite=_Suite(final_board_count=8),
    )
    second = reconstruct_board_level_guard_report_from_legacy(
        artifact_root=tmp_path,
        source_job_id=source_job_id,
        pipeline_fingerprint_sha256="a" * 64,
        legacy_report=legacy,
        legacy_report_checksum_sha256=legacy_checksum,
        originals=(source,),
        geometry_entries=_entries((source,)),
        suite=_Suite(final_board_count=8),
    )

    assert second == first
    assert first.report_checksum_sha256 in first.report_relative_path
    envelope = json.loads((tmp_path / first.report_relative_path).read_text(encoding="ascii"))
    assert envelope["reportChecksumSha256"] == first.report_checksum_sha256
    assert envelope["report"]["derivedFromReportChecksumSha256"] == legacy_checksum
    assert envelope["report"]["sources"][0]["boards"][8]["status"] == "deferred"


def test_guard_rejects_a_tampered_persisted_report(tmp_path: Path) -> None:
    originals = tuple(_original(index) for index in range(56))
    job_id = UUID("33333333-3333-3333-3333-333333333333")
    kwargs = {
        "artifact_root": tmp_path,
        "job_id": job_id,
        "pipeline_fingerprint_sha256": "a" * 64,
        "source_manifest_checksum_sha256": "b" * 64,
        "page_geometry_manifest_checksum_sha256": "c" * 64,
        "originals": originals,
        "geometry_entries": _entries(originals),
        "suite": _Suite(),
    }
    run_large_import_geometry_guard(**kwargs)
    path = tmp_path / "data" / "image-geometry-guards" / f"{job_id}.json"
    envelope = json.loads(path.read_text(encoding="ascii"))
    envelope["report"]["finalCellGridReadyBoardCount"] = 0
    path.write_text(json.dumps(envelope), encoding="ascii")

    with pytest.raises(JobHandlerError) as captured:
        run_large_import_geometry_guard(**kwargs)

    assert captured.value.code == "IMAGE_GEOMETRY_GUARD_REPORT_DRIFT"
