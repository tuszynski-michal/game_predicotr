import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    SourcePoint,
    SourceQuad,
)
from game_predictor_worker.images.board_cell_geometry_activation import (
    board_cell_processing_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.lateral_partial_artifact import (
    lateral_candidate_from_entry,
)
from game_predictor_worker.images.lateral_partial_contract import (
    LateralPartialContractError,
    LateralPartialGeometrySnapshot,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.images.page_geometry_registration import (
    LateralPageRegistrationCandidate,
    PageRegistrationInitialization,
)
from game_predictor_worker.images.partial_grid_learning import (
    PartialGridPattern,
    PartialGridTrainingProfile,
)
from game_predictor_worker.images.pipeline_execution import (
    ImageStageContext,
    validate_stage_payload,
)
from game_predictor_worker.images.production_workflow import ProductionImageStageAdapterSuite
from PIL import Image
from test_page_geometry_preflight import _cold_start_job, _Context
from test_page_geometry_registration import _page
from test_production_image_workflow import _candidate_snapshot, _structured_active_lattice_rollout
from test_structured_lattice_refinement_v4 import _candidate, _crop

POLICY = LateralPartialGeometrySnapshot(frame_support_review=True)


def _entry(source, quad, *, policy=POLICY):
    candidate = replace(_candidate(quad), policy_checksum_sha256=policy.checksum_sha256)
    return {
        "status": "review_required",
        "imageWidth": source.shape[1],
        "imageHeight": source.shape[0],
        "lateralRegistrationCandidate": candidate.to_payload(),
    }


@pytest.mark.parametrize("side", ["left", "right", "both"])
def test_source_bound_candidate_roundtrip_and_drift(side):
    rgb, quad = _crop(side)
    entry = _entry(rgb, quad)
    restored = lateral_candidate_from_entry(
        entry, width=rgb.shape[1], height=rgb.shape[0], board_count=1, policy=POLICY
    )
    assert restored.to_payload() == _candidate(quad).to_payload()
    with pytest.raises(LateralPartialContractError):
        lateral_candidate_from_entry(
            entry, width=rgb.shape[1] + 1, height=rgb.shape[0], board_count=1, policy=POLICY
        )


def test_preflight_restart_preserves_pinned_extension_without_reprocessing(tmp_path, monkeypatch):
    base, _ = _cold_start_job(tmp_path, image_count=1)
    job = replace(
        base, input_payload={**base.input_payload, "lateral_partial_geometry": POLICY.to_payload()}
    )
    context = _Context()
    handler = PageGeometryPreflightHandler(artifact_root=tmp_path)
    handler(context, job)
    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    path = tmp_path / checkpoint["geometry_manifest_relative_path"]
    manifest = json.loads(path.read_bytes())
    assert manifest["lateralPartialGeometry"] == POLICY.to_payload()
    monkeypatch.setattr(
        handler, "_evaluate_source", lambda *a, **kw: pytest.fail("Repeated detector")
    )
    restarted = _Context()
    handler(restarted, replace(job, checkpoint_payload=checkpoint))
    assert restarted.checkpoints[-1]["checkpoint_payload"] == checkpoint


@pytest.mark.parametrize("tamper", [None, "inventory", "jpeg"])
def test_managed_preflight_uses_verified_originals_after_browser_release(tmp_path, tamper):
    from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
    from game_predictor_worker.jobs.runtime import JobHandlerError

    base, _ = _cold_start_job(tmp_path, image_count=1)
    original_store = ManagedOriginalStore(tmp_path)
    managed = original_store.load_or_create_manifest(
        base, source_directory=Path(base.input_payload["source_directory"])
    )
    for original in managed.originals:
        original_store.ensure_original(managed, original)
    # Delete only this isolated fixture's browser inputs, not managed JPEGs.
    staged = Path(base.input_payload["source_directory"])
    for path in staged.iterdir():
        path.unlink()
    staged.rmdir()
    job = replace(
        base,
        id=uuid4(),
        input_payload={
            **base.input_payload,
            "lateral_partial_geometry": POLICY.to_payload(),
            "managed_source_job_id": str(base.id),
            "managed_source_manifest_checksum_sha256": managed.checksum_sha256,
        },
    )
    if tamper == "inventory":
        (tmp_path / managed.relative_path).write_text("{}")
    elif tamper == "jpeg":
        (tmp_path / managed.originals[0].managed_relative_path).write_bytes(b"changed")
    handler = PageGeometryPreflightHandler(artifact_root=tmp_path)
    context = _Context()
    if tamper:
        with pytest.raises(JobHandlerError):
            handler(context, job)
        assert not any(item["checkpoint_payload"].get("complete") for item in context.checkpoints)
        return
    handler(context, job)
    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    result = json.loads((tmp_path / checkpoint["geometry_manifest_relative_path"]).read_bytes())
    assert result["sourceCount"] == 1
    assert result["lateralPartialGeometry"] == POLICY.to_payload()
    restart = _Context()
    handler(restart, replace(job, checkpoint_payload=checkpoint))
    assert restart.checkpoints[-1]["checkpoint_payload"] == checkpoint


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("learned", [False, True])
def test_real_partial_pass_persists_proposal_without_render_after_restart(tmp_path, side, learned):
    rgb, quad = _crop(side)
    relative = "data/original.jpg"
    path = tmp_path / relative
    path.parent.mkdir()
    Image.fromarray(rgb).save(path, quality=100, subsampling=0)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    snapshot = _candidate_snapshot()
    topology = BoardCellTopology(rows=3, columns=5, rules_version_id=str(uuid4()))
    mask = (0, 5, 10) if side == "left" else (4, 9, 14)
    policy = (
        LateralPartialGeometrySnapshot(
            PartialGridTrainingProfile(
                (PartialGridPattern(mask, sample_count=3, source_count=3),), 3
            ),
            frame_support_review=True,
        )
        if learned
        else POLICY
    )
    options = dict(
        repository_root=Path.cwd(),
        symbol_model=snapshot,
        attested_sequence_ranges={checksum: (1, 1)},
        board_cell_processing=board_cell_processing_snapshot(
            cell_output_size=snapshot.input_size, topology=topology
        ),
        geometry_rollout=replace(
            _structured_active_lattice_rollout(), lateral_partial_geometry=policy
        ),
        page_geometry_manifest={checksum: _entry(rgb, quad, policy=policy)},
        manual_geometry_import=True,
    )
    suite = ProductionImageStageAdapterSuite(tmp_path, **options)
    base = dict(
        job_id=uuid4(),
        file_execution_key="e" * 64,
        source_checksum_sha256=checksum,
        source_relative_path="original.jpg",
        pipeline_fingerprint="d" * 64,
        attested_sequence_range=(1, 1),
    )
    results = {}
    for stage, execute in (
        ("normalization", suite.normalization),
        ("board_detection", suite.board_detection),
        ("board_cell_geometry", suite.board_cell_geometry),
        ("board_crops", suite.board_crops),
    ):
        context = ImageStageContext(**base, previous_results=results)
        results[stage] = dict(execute(context))
        validate_stage_payload(stage, results[stage], context)
    board = results["board_detection"]["structuredGeometry"]["boards"][0]
    assert board["automaticPartialProposal"]["requiresManualConfirmation"] is True
    assert board["automaticPartialProposal"]["version"] == ("automatic-lateral-partial-proposal-v3")
    qualification = board["automaticPartialProposal"]["geometryQualification"]
    assert qualification["includeInPartialGridTraining"] is False
    if learned:
        assert (
            board["automaticPartialProposal"]["trainingProfileChecksumSha256"]
            == policy.training_profile.checksum_sha256
        )
    else:
        assert "trainingProfileChecksumSha256" not in board["automaticPartialProposal"]
    assert board["finalQuad"] is None
    assert board["symbolGridQuad"] is not None
    assert results["board_crops"]["boards"] == []
    assert len(results["board_crops"]["deferredBoards"]) == 1
    restarted = ProductionImageStageAdapterSuite(tmp_path, **options)
    assert (
        restarted.board_crops(ImageStageContext(**base, previous_results=results))
        == results["board_crops"]
    )


def test_historical_v1_candidate_replays_without_new_frame_fields() -> None:
    rgb, quad = _crop("left")
    policy = LateralPartialGeometrySnapshot(frame_support_review=False)
    candidate = replace(
        _candidate(quad),
        policy_checksum_sha256=policy.checksum_sha256,
        version="lateral-page-registration-candidate-v1",
    )
    entry = {
        "status": "review_required",
        "imageWidth": rgb.shape[1],
        "imageHeight": rgb.shape[0],
        "lateralRegistrationCandidate": candidate.to_payload(),
    }
    restored = lateral_candidate_from_entry(
        entry, width=rgb.shape[1], height=rgb.shape[0], board_count=1, policy=policy
    )
    assert restored.to_payload() == candidate.to_payload()
    assert "recoveryKind" not in restored.to_payload()


def test_frame_candidate_roundtrip_preserves_review_slots() -> None:
    image, quads = _page()
    coverages = (0.35, 0.97, 0.87, 0.90, 0.95, 1.0, 1.0, 1.0, 0.93)
    candidate = LateralPageRegistrationCandidate(
        PageRegistrationInitialization(
            anchor_source_checksum_sha256="a" * 64,
            active_board_slots=tuple(range(9)),
            initialization_quads=quads,
            native_homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            inlier_count=100,
            inlier_ratio=0.8,
            p95_reprojection_error=0.5,
            feature_count=1000,
        ),
        policy_checksum_sha256=POLICY.checksum_sha256,
        board_red_edge_coverages=coverages,
        recovery_kind="frame_support_review",
        review_required_slots=(0,),
        version="lateral-page-registration-candidate-v2",
    )
    entry = {
        "status": "review_required",
        "imageWidth": image.shape[1],
        "imageHeight": image.shape[0],
        "lateralRegistrationCandidate": candidate.to_payload(),
    }
    restored = lateral_candidate_from_entry(
        entry,
        width=image.shape[1],
        height=image.shape[0],
        board_count=9,
        policy=POLICY,
    )
    assert restored.to_payload() == candidate.to_payload()
    assert restored.review_required_slots == (0,)


@pytest.mark.parametrize(
    "weak_count,weak_local_full,weak_partial",
    [
        (1, False, False),
        (1, True, False),
        (2, False, False),
        (2, True, False),
        (3, False, False),
        (1, False, True),
    ],
)
def test_selective_workflow_preserves_confident_grids_and_drafts_only_weak_slots(
    tmp_path, monkeypatch, weak_count, weak_local_full, weak_partial
):
    import game_predictor_worker.images.structured_geometry.lattice_refinement_v4 as refinement

    image, quads = _page()
    source_path = tmp_path / "source.jpg"
    Image.fromarray(image).save(source_path, quality=100, subsampling=0)
    checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
    frame = CanonicalSourceLoader().load(source_path, expected_source_checksum_sha256=checksum)
    policy = LateralPartialGeometrySnapshot(frame_support_review=True, selective_frame_review=True)
    candidate = LateralPageRegistrationCandidate(
        PageRegistrationInitialization(
            anchor_source_checksum_sha256="a" * 64,
            active_board_slots=tuple(range(9)),
            initialization_quads=quads,
            native_homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            inlier_count=100,
            inlier_ratio=0.8,
            p95_reprojection_error=0.5,
            feature_count=1000,
        ),
        policy_checksum_sha256=policy.checksum_sha256,
        board_red_edge_coverages=(0.35,) * min(weak_count, 2) + (0.95,) * (9 - min(weak_count, 2)),
        recovery_kind="frame_support_review",
        review_required_slots=tuple(range(min(weak_count, 2))),
        version="lateral-page-registration-candidate-v3",
    )
    entry = {
        "status": "review_required",
        "imageWidth": image.shape[1],
        "imageHeight": image.shape[0],
        "lateralRegistrationCandidate": candidate.to_payload(),
    }

    def fake_refinement(_source, *, analysis_quad, position_index, **_kwargs):
        grid = SourceQuad(
            corners=tuple(
                SourcePoint(
                    point.x + (5 if index in (0, 3) else -5),
                    point.y + (5 if index in (0, 1) else -5),
                )
                for index, point in enumerate(analysis_quad.corners)
            )
        )
        full = position_index >= weak_count or weak_local_full
        payload = {
            "analysisQuad": [point.to_dict() for point in analysis_quad.corners],
            "symbolGridQuad": [point.to_dict() for point in grid.corners] if full else None,
        }
        if weak_partial and position_index == 0:
            payload["automaticPartialProposal"] = {"requiresManualConfirmation": True}
        return SimpleNamespace(
            status=(
                "pending_partial"
                if weak_partial and position_index == 0
                else "full"
                if full
                else "needs_review"
            ),
            baseline=SimpleNamespace(
                analysis_quad=analysis_quad, symbol_grid_quad=grid if full else None
            ),
            proposal=None,
            reason_code=None if full else "local_symbol_grid_unavailable",
            to_payload=lambda: payload,
        )

    monkeypatch.setattr(refinement, "refine_structured_symbol_lattice_v4", fake_refinement)
    model = _candidate_snapshot()
    suite = ProductionImageStageAdapterSuite(
        tmp_path,
        repository_root=Path.cwd(),
        symbol_model=model,
        board_cell_processing=board_cell_processing_snapshot(
            cell_output_size=model.input_size,
            topology=BoardCellTopology(rows=3, columns=5, rules_version_id=str(uuid4())),
        ),
        geometry_rollout=replace(
            _structured_active_lattice_rollout(), lateral_partial_geometry=policy
        ),
        manual_geometry_import=True,
    )
    result = suite._detect_lateral_proposals(frame, AttestedSequenceRange(start=1, end=9), entry)
    boards = result["boards"]
    if weak_count == 3:
        assert all("reviewDraftQuad" not in board for board in boards)
    elif weak_partial:
        assert boards[0]["finalQuad"] is None
        assert boards[0]["automaticPartialProposal"] == {"requiresManualConfirmation": True}
        assert "reviewDraftQuad" not in boards[0]
        assert all(board["finalQuad"] is not None for board in boards[1:])
    else:
        assert [board["finalQuad"] is not None for board in boards] == (
            [False] * weak_count + [True] * (9 - weak_count)
        )
        assert [index for index, board in enumerate(boards) if "reviewDraftQuad" in board] == list(
            range(weak_count)
        )
        assert all(
            board["geometryQualification"]["excludeFromGeometryTraining"] is True
            for board in boards[:weak_count]
        )
        assert all(
            board["reviewDraftOrigin"]
            == (
                "local_symbol_lattice_v1"
                if weak_local_full
                else "page_projection_confident_neighbors_v1"
            )
            for board in boards[:weak_count]
        )
