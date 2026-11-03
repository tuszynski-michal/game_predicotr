"""Frozen-policy safety regression, including the recorded 462205 candidate."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_crop_policy import (
    LEGACY_NEURAL_AUTO_CROP_POLICY,
    NEURAL_AUTO_CROP_POLICY,
    full_neural_prediction_geometry,
    neural_auto_crop_blockers,
    neural_auto_crop_evidence,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
    proposal_checksum_sha256,
)
from game_predictor_api.domain.v3_engine_acceptance import (
    LEGACY_V3_ENGINE_ACCEPTANCE_POLICY,
    qualify_v3_engine_acceptance,
)
from game_predictor_api.storage.lateral_reprocess_protection import lock_lateral_sequences
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.images.grid_reinference_handler import GridReinferenceHandler
from game_predictor_worker.images.neural_pending_geometry import neural_pending_payload
from game_predictor_worker.jobs.runtime import JobHandlerError
from test_v3_engine_acceptance import facts


def revised_facts(reason, *, legacy=False):
    value = facts()
    value["proposal"]["detections"][0]["reasonCodes"].append(reason)
    value["proposal"]["proposalChecksumSha256"] = proposal_checksum_sha256(value["proposal"])
    value["binding"] = associate_expected_slots(value["proposal"])
    for item, detection in zip(value["positions"], value["proposal"]["detections"], strict=True):
        item.geometry.update(
            neuralProposalChecksumSha256=value["proposal"]["proposalChecksumSha256"],
            neuralProposalBinding=deepcopy(value["binding"]),
            neuralAcceptanceEvidence=neural_auto_crop_evidence(detection),
        )
        if legacy:
            item.geometry["neuralExecutionPolicy"] = LEGACY_NEURAL_AUTO_CROP_POLICY
            item.geometry.pop("neuralAcceptanceEvidence")
    if legacy:
        value["policy"] = LEGACY_V3_ENGINE_ACCEPTANCE_POLICY
    return value


def pending(value, policy):
    return neural_pending_payload(
        {
            "sourceChecksumSha256": value["proposal"]["sourceChecksumSha256"],
            "canonicalWidth": value["width"],
            "canonicalHeight": value["height"],
            "engineId": "manual_v1",
            "globalInitialization": {},
            "boards": [{"positionIndex": i} for i in range(len(value["positions"]))],
        },
        {"neuralProposal": value["proposal"], "neuralProposalBinding": value["binding"]},
        automatic_crops=True,
        execution_policy=policy,
        engine_acceptance_policy=value["policy"],
    )


@pytest.mark.parametrize("reason", ["NEURAL_GRID_FIT_FAILED", "NEURAL_GRID_FIT_OUTLIERS"])
@pytest.mark.parametrize("legacy", [False, True])
def test_worker_and_api_agree_on_fit_failure_and_legacy_interpretation(reason, legacy):
    value = revised_facts(reason, legacy=legacy)
    policy = LEGACY_NEURAL_AUTO_CROP_POLICY if legacy else NEURAL_AUTO_CROP_POLICY
    before = deepcopy(value)
    result = pending(value, policy)
    board = result["structuredGeometry"]["boards"][0]
    assert (board["disposition"] == "automatic") == legacy
    assert (qualify_v3_engine_acceptance(**value) == ()) == legacy
    assert value == before
    if not legacy:
        assert reason in board["reasonCodes"]
        assert board["finalQuad"] is None


def test_api_rechecks_original_reasons_despite_forged_worker_acceptance():
    value = revised_facts("NEURAL_GRID_FIT_FAILED")
    # A worker claiming clean evidence/automatic cannot erase the immutable proposal reason.
    value["positions"][0].geometry["neuralAcceptanceEvidence"]["reasonCodes"] = []
    value["positions"][0].geometry["structuredDisposition"] = "automatic"
    # Completeness is only a consistency projection; it cannot authenticate evidence.
    assert full_neural_prediction_geometry(
        value["positions"][0].geometry,
        position=0,
        sequence=101,
        width=value["width"],
        height=value["height"],
        game_id=value["game_id"],
        source_checksum_sha256=value["source_checksum_sha256"],
    )
    assert "V3_ACCEPTANCE_EVIDENCE_INVALID" in qualify_v3_engine_acceptance(**value)


@pytest.mark.parametrize("fault", ["fit", "evidence_mismatch"])
def test_api_write_guard_rejects_forged_fit_before_storage(fault):
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    value = revised_facts("NEURAL_GRID_FIT_FAILED") if fault == "fit" else facts()
    if fault == "evidence_mismatch":
        value["positions"][0].geometry["neuralAcceptanceEvidence"]["reasonCodes"] = []
    context = SimpleNamespace(
        game_id=UUID(value["game_id"]),
        source_checksum_sha256=value["source_checksum_sha256"],
        position_index=0,
        sequence_number=101,
        oriented_width=500,
        oriented_height=300,
        topology=SimpleNamespace(rows=3, columns=5),
    )
    session = Mock()
    prepared = SimpleNamespace(
        entries=[SimpleNamespace(context=context, board_geometry=value["positions"][0].geometry)]
    )
    with pytest.raises(ImageGridReviewError) as error:
        SqlAlchemyVirtualGridGeometryRepository(session).save_automatic_reinference_source(
            prepared=prepared,
            idempotency_key=uuid4(),
            created_at=datetime.now(UTC),
            proposal=value["proposal"],
            binding=value["binding"],
            model_snapshot=value["model_snapshot"],
            acceptance_policy=value["policy"],
        )
    assert error.value.code == "NEURAL_GRID_AUTOMATIC_WRITE_BLOCKED"
    assert session.mock_calls == []


@pytest.mark.parametrize("reason", ["NEURAL_GRID_FIT_FAILED", "NEURAL_GRID_FIT_OUTLIERS"])
def test_detection_fit_reasons_survive_raw_checkpoint_and_proposal(reason, tmp_path, monkeypatch):
    value = facts()
    snapshot = NeuralGridSnapshot.from_payload(value["model_snapshot"])
    nodes = np.array(
        [[point["x"], point["y"]] for point in value["proposal"]["detections"][0]["latticeNodes"]]
    )
    if reason == "NEURAL_GRID_FIT_FAILED":
        nodes = grid_from_quad(nodes[[0, 5, 23, 18]])
    detection = BoardDetection(
        score=0.9, screen_quad=nodes[[0, 5, 23, 18]], nodes=nodes, reasons=[reason]
    )
    runner = SimpleNamespace(run=Mock(return_value=[detection]))
    monkeypatch.setattr(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
        lambda *_args: tmp_path / "fixture-bundle",
    )
    source = {"checksum_sha256": value["source_checksum_sha256"]}
    rgb = np.zeros((value["height"], value["width"], 3))
    operation = uuid4()
    handler = GridReinferenceHandler(None, tmp_path)
    raw = handler.raw_inference(source, rgb, {}, snapshot, operation, runner, None)
    # A fresh handler reads the published JSON instead of serializing the object again.
    restored = GridReinferenceHandler(None, tmp_path).raw_inference(
        source, rgb, {}, snapshot, operation, None, None
    )
    assert restored == raw and runner.run.call_count == 1
    proposal = build_neural_source_proposal(
        game_id=value["game_id"],
        source_selection_id=str(uuid4()),
        source_checksum_sha256=value["source_checksum_sha256"],
        source_width=value["width"],
        source_height=value["height"],
        original_range=AttestedSequenceRange(start=101, end=101),
        snapshot=snapshot,
        detections=restored["detections"],
    )
    assert reason in proposal["detections"][0]["reasonCodes"]
    arguments = dict(
        detection=proposal["detections"][0],
        binding=associate_expected_slots(proposal),
        position=0,
        width=value["width"],
        height=value["height"],
    )
    assert neural_auto_crop_blockers(policy=LEGACY_NEURAL_AUTO_CROP_POLICY, **arguments) == ()
    assert neural_auto_crop_blockers(policy=NEURAL_AUTO_CROP_POLICY, **arguments) == (reason,)


@pytest.mark.parametrize(
    "fault", ["partial", "empty", "missing", "duplicate", "layout", "pixels", "nodes", "policy"]
)
def test_shared_v2_qualification_fails_closed(fault):
    value = facts()
    detection = deepcopy(value["proposal"]["detections"][0])
    arguments = dict(
        policy=NEURAL_AUTO_CROP_POLICY,
        detection=detection,
        binding=value["binding"],
        position=0,
        width=500,
        height=300,
    )
    if fault == "partial":
        detection["cellVisibility"][0] = "partial"
    elif fault == "empty":
        detection["cellVisibility"] = []
    elif fault == "missing":
        value["binding"]["assignments"].pop()
    elif fault == "duplicate":
        value["binding"]["assignments"][1]["detectionId"] = detection["detectionId"]
    elif fault == "layout":
        arguments["rows"] = 4
    elif fault == "pixels":
        arguments["valid_pixel_box"] = (30, 30, 500, 300)
    elif fault == "nodes":
        detection["latticeNodes"][8] = detection["latticeNodes"][7]
    elif fault == "policy":
        arguments["policy"] = "unknown-v3"
    assert neural_auto_crop_blockers(**arguments)


def test_recorded_462205_outliers_are_review_not_automatic():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/neural_462205_fit_outliers.json").read_text()
    )
    assert fixture["sequenceNumber"] == 462205
    raw = fixture["detection"]
    assert raw["reasons"] == ["NEURAL_GRID_FIT_OUTLIERS"]
    nodes = [{"x": x, "y": y} for x, y in raw["nodes"]]
    quads = lattice_cell_quads(nodes, width=1498, height=1246)
    detection = dict(
        detectionId="recorded-462205",
        latticeNodes=nodes,
        structurallyValid=raw["structurallyValid"],
        reasonCodes=raw["reasons"],
        cellVisibility=lattice_visibility(quads, width=1498, height=1246),
    )
    binding = dict(
        confirmedRange=dict(sequenceRangeStart=462205, sequenceRangeEnd=462205),
        assignments=[dict(positionIndex=0, detectionId="recorded-462205")],
        missingPositionIndexes=[],
    )
    args = dict(detection=detection, binding=binding, position=0, width=1498, height=1246)
    assert neural_auto_crop_blockers(policy=LEGACY_NEURAL_AUTO_CROP_POLICY, **args) == ()
    assert neural_auto_crop_blockers(policy=NEURAL_AUTO_CROP_POLICY, **args) == (
        "NEURAL_GRID_FIT_OUTLIERS",
    )


@pytest.mark.parametrize("policy", [LEGACY_NEURAL_AUTO_CROP_POLICY, NEURAL_AUTO_CROP_POLICY])
def test_both_policies_keep_sequence_locks(policy, monkeypatch):
    locked = Mock()
    monkeypatch.setattr(
        "game_predictor_api.storage.lateral_reprocess_protection.acquire_image_sequence_locks",
        locked,
    )
    session = object()
    job = SimpleNamespace(
        game_id="game", input_payload={"neural_grid_execution_policy_version": policy}
    )
    lock_lateral_sequences(session, job=job, sequence_numbers=[101, 102, 101])
    locked.assert_called_once_with(session, game_id="game", sequence_numbers={101, 102})


@pytest.mark.parametrize("legacy", [False, True])
def test_checkpoint_restart_keeps_frozen_policy_and_decision(tmp_path, legacy):
    value = revised_facts("NEURAL_GRID_FIT_OUTLIERS", legacy=legacy)
    data = dict(
        proposal=value["proposal"],
        binding=value["binding"],
        byPosition={"0": value["proposal"]["detections"][0]},
    )
    policy = LEGACY_NEURAL_AUTO_CROP_POLICY if legacy else NEURAL_AUTO_CROP_POLICY
    if not legacy:
        data["executionPolicy"] = policy
    from uuid import uuid4

    descriptor = GridReinferenceHandler(None, tmp_path).save_checkpoint(uuid4(), 1, data)
    script = """
import json,sys
from pathlib import Path
from game_predictor_worker.images.grid_reinference_handler import GridReinferenceHandler
h=GridReinferenceHandler(None,Path(sys.argv[1]))
value=h.load_checkpoint(json.loads(sys.argv[2]))
h.require_checkpoint_policy(value,sys.argv[3])
print(json.dumps(h.automatic_blockers(value,0)))
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            str(Path.cwd() / p) for p in ("services/api/src", "services/worker/src")
        ),
    }
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), json.dumps(descriptor), policy],
        env=env,
        timeout=30,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == ([] if legacy else ["NEURAL_GRID_FIT_OUTLIERS"])
    restored = GridReinferenceHandler(None, tmp_path).load_checkpoint(descriptor)
    with pytest.raises(JobHandlerError):
        GridReinferenceHandler.require_checkpoint_policy(
            restored, NEURAL_AUTO_CROP_POLICY if legacy else LEGACY_NEURAL_AUTO_CROP_POLICY
        )
