from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_grid_proposal import build_neural_source_binding
from game_predictor_worker.images.board_cell_geometry_activation import (
    board_cell_processing_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.neural_page_geometry_preflight import (
    NeuralPageGeometryPreflightHandler,
)
from game_predictor_worker.images.neural_pending_geometry import bound_neural_originals
from game_predictor_worker.images.pipeline_execution import (
    ImageStageContext,
    validate_stage_payload,
)
from game_predictor_worker.images.production_workflow import (
    ProductionImageStageAdapterSuite,
    _filter_canonical_originals,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from test_neural_page_geometry_preflight import Context, Models, Runner, job_fixture, result


def test_folder_to_pending_draft_keeps_missing_middle_and_full_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=Runner([4, 5]), model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    entries = result(root, context)["entries"]
    proposal = entries[checksums[0]]["neuralProposal"]
    ids = [item["detectionId"] for item in proposal["detections"]]
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=101, end=105),
        assignments=[
            {"detectionId": identity, "positionIndex": position}
            for identity, position in zip(ids, [0, 1, 3, 4], strict=True)
        ],
    )
    entries[checksums[0]]["neuralProposalBinding"] = binding
    entries[checksums[0]]["status"] = "review_required"
    managed = ManagedOriginalStore(root).load_existing_manifest(job)
    originals = bound_neural_originals(managed.originals, entries)
    assert len(originals) == 2
    assert [(item.sequence_range_start, item.sequence_range_end) for item in originals] == [
        (101, 105),
        (201, 205),
    ]
    deferred = []
    suite = ProductionImageStageAdapterSuite(
        root,
        repository_root=tmp_path,
        manual_geometry_import=True,
        page_geometry_manifest=entries,
        board_cell_processing=board_cell_processing_snapshot(
            cell_output_size=96,
            topology=BoardCellTopology(rows=3, columns=5, rules_version_id=str(uuid4())),
        ),
        board_cell_geometry_deferred_writer=SimpleNamespace(
            defer=lambda _context, **kwargs: deferred.append(kwargs)
        ),
    )
    monkeypatch.setattr(
        suite,
        "_canonical_source",
        lambda _context: SimpleNamespace(
            source=SimpleNamespace(
                source_checksum_sha256=checksums[0],
                normalized_pixel_checksum_sha256="e" * 64,
                width=500,
                height=300,
            )
        ),
    )
    stage = ImageStageContext(
        job_id=job.id,
        file_execution_key="f" * 64,
        source_checksum_sha256=checksums[0],
        source_relative_path="unused.jpg",
        pipeline_fingerprint="d" * 64,
        previous_results={},
        attested_sequence_range=(101, 105),
    )
    detection = suite.board_detection(stage)
    validate_stage_payload("board_detection", detection, stage)
    assert detection["boards"][2]["geometry"]["quad"] is None
    assert detection["boards"][3]["sequenceNumber"] == 104
    assert (
        detection["boards"][3]["geometry"]["latticeNodes"]
        == proposal["detections"][2]["latticeNodes"]
    )
    stage = replace(stage, previous_results={"board_detection": detection})
    geometry = suite.board_cell_geometry(stage)
    validate_stage_payload("board_cell_geometry", geometry, stage)
    suite.persist_board_cell_geometry_deferrals(stage, geometry)
    stage = replace(stage, previous_results={"board_cell_geometry": geometry})
    crops = suite.board_crops(stage)
    assert crops["boards"] == []
    assert [item["sequence_number"] for item in deferred] == [101, 102, 103, 104, 105]
    structured = geometry["structuredGeometry"]
    assert structured["engineKind"] == "neural_grid_v1"
    assert structured["status"] == "needs_review"
    assert all(board["finalQuad"] is None for board in structured["boards"])
    assert (
        structured["boards"][3]["neuralProposalChecksumSha256"]
        == proposal["proposalChecksumSha256"]
    )


def test_unbound_sources_keep_original_inventory_without_assigning_sequence(tmp_path: Path) -> None:
    job, _checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=Runner([4, 6]), model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    managed = ManagedOriginalStore(root).load_existing_manifest(job)
    assert len(managed.originals) == 2
    assert bound_neural_originals(managed.originals, result(root, context)["entries"]) == ()


def test_canonical_filter_uses_explicit_confirmed_range_without_mutating_original(
    tmp_path: Path,
) -> None:
    job, checksums = job_fixture(tmp_path, files=1, maximum=103)
    root = tmp_path / "artifacts"
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=Runner([5]), model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    entries = result(root, context)["entries"]
    proposal = entries[checksums[0]]["neuralProposal"]
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=101, end=103),
        assignments=[
            {"detectionId": item["detectionId"], "positionIndex": position}
            for position, item in enumerate(proposal["detections"][:3])
        ],
    )
    entries[checksums[0]].update(status="review_required", neuralProposalBinding=binding)
    original = ManagedOriginalStore(root).load_existing_manifest(job).originals
    effective = bound_neural_originals(original, entries)
    assert effective[0].sequence_range_end == 103
    assert original[0].sequence_range_end == 105
    assert (
        _filter_canonical_originals(
            effective,
            replace(
                job,
                input_payload={**job.input_payload, "canonical_sequence_numbers": [101, 102, 103]},
            ),
        )
        == ()
    )
