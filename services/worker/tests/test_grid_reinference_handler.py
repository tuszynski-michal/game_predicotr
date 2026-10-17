"""Restart-safe raw inference identity, bounded outcomes and slot protection."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_proposal,
)
from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.images.grid_reinference_handler import GridReinferenceHandler
from game_predictor_worker.jobs.runtime import JobHandlerError


def test_raw_cache_restarts_deduplicates_file_and_model_not_occurrence(tmp_path, monkeypatch):
    calls = []
    nodes = np.array(
        [[10.0 + column * 20, 10.0 + row * 20] for row in range(4) for column in range(6)]
    )

    class Runner:
        def run(self, *_args, **kwargs):
            assert kwargs["max_seconds"] == 30.0
            calls.append(True)
            return [BoardDetection(score=0.9, screen_quad=nodes[[0, 5, 23, 18]], nodes=nodes)]

    monkeypatch.setattr(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
        lambda *_args: tmp_path / "fake-bundle",
    )
    snapshot = SimpleNamespace(
        version=SimpleNamespace(files=[SimpleNamespace(name="bundle.json", sha256="a" * 64)])
    )
    source = dict(
        checksum_sha256="a" * 64,
        normalized_pixel_checksum_sha256="b" * 64,
        exif_orientation=1,
        oriented_width=400,
        oriented_height=200,
        normalization_adapter_version="v1",
        id=str(uuid4()),
        import_job_id=str(uuid4()),
    )
    operation = uuid4()
    context = SimpleNamespace(heartbeat=lambda: None)
    first = GridReinferenceHandler(None, tmp_path).raw_inference(
        source, np.zeros((200, 400, 3)), {"version": "one"}, snapshot, operation, Runner(), context
    )
    second_source = {**source, "id": str(uuid4()), "import_job_id": str(uuid4())}
    second = GridReinferenceHandler(None, tmp_path).raw_inference(
        second_source,
        np.zeros((200, 400, 3)),
        {"version": "one"},
        snapshot,
        operation,
        Runner(),
        context,
    )
    assert first == second and len(calls) == 1
    assert first["detections"][0]["reasonCodes"] == ["NEURAL_GRID_GATE_UNCALIBRATED"]
    GridReinferenceHandler(None, tmp_path).raw_inference(
        source, np.zeros((200, 400, 3)), {"version": "two"}, snapshot, operation, Runner(), context
    )
    assert len(calls) == 2


def test_timeout_is_durable_and_is_not_an_empty_success(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
        lambda *_args: tmp_path / "fake",
    )
    snapshot = SimpleNamespace(
        version=SimpleNamespace(files=[SimpleNamespace(name="bundle.json", sha256="a" * 64)])
    )
    runner = SimpleNamespace(
        run=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            GeometryRuntimeError("NEURAL_GRID_SOURCE_TIME_LIMIT", "source timed out")
        )
    )
    source, operation = {"checksum_sha256": "a" * 64}, uuid4()
    result = GridReinferenceHandler(None, tmp_path).raw_inference(
        source,
        np.zeros((20, 20, 3)),
        {},
        snapshot,
        operation,
        runner,
        SimpleNamespace(heartbeat=lambda: None),
    )
    assert result["outcome"] == "inference_timeout"
    result2 = GridReinferenceHandler(None, tmp_path).raw_inference(
        source, np.zeros((20, 20, 3)), {}, snapshot, operation, None, None
    )
    assert result2 == result


def test_checkpoint_corruption_fails_closed_after_restart(tmp_path):
    operation = uuid4()
    handler = GridReinferenceHandler(None, tmp_path)
    checkpoint = handler.save_checkpoint(operation, 1, {"byPosition": {"3": {"nodes": []}}})
    restored = GridReinferenceHandler(None, tmp_path).load_checkpoint(checkpoint)
    assert list(restored["byPosition"]) == [3]
    (tmp_path / checkpoint["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(JobHandlerError, match="checksum"):
        GridReinferenceHandler(None, tmp_path).load_checkpoint(checkpoint)


def test_missing_middle_detection_never_compacts_sequence():
    from game_predictor_api.domain.neural_grid_proposal import (
        lattice_cell_quads,
        lattice_visibility,
    )

    profile = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1)
    snapshot = NeuralGridSnapshot.for_game(500000, profile.current)
    detections = []
    # Two surviving detections from a three-position occurrence: no safe binding.
    for position in (0, 2):
        nodes = [
            {"x": float(10 + position * 120 + column * 20), "y": float(10 + row * 20)}
            for row in range(4)
            for column in range(6)
        ]
        quads = lattice_cell_quads(nodes, width=500, height=200)
        detections.append(
            dict(
                detectionId=str(position),
                score=0.9,
                latticeNodes=nodes,
                cellQuads=[quad.to_dict() for quad in quads],
                cellVisibility=lattice_visibility(quads, width=500, height=200),
                structurallyValid=True,
                reasonCodes=["NEURAL_GRID_GATE_UNCALIBRATED"],
            )
        )
    proposal = build_neural_source_proposal(
        game_id=str(uuid4()),
        source_selection_id=str(uuid4()),
        source_checksum_sha256="a" * 64,
        source_width=500,
        source_height=200,
        original_range=AttestedSequenceRange(start=100, end=102),
        snapshot=snapshot,
        detections=detections,
    )
    before = copy.deepcopy(proposal)
    assert associate_expected_slots(proposal) is None
    assert proposal == before
    assert proposal["originalRange"] == {"sequenceRangeStart": 100, "sequenceRangeEnd": 102}


def test_recognize_fails_closed_before_inference_on_normalization_drift(tmp_path):
    from game_predictor_worker.images.normalization import CanonicalSourceLoader
    from PIL import Image

    path = tmp_path / "data" / "source.jpg"
    path.parent.mkdir()
    Image.new("RGB", (50, 50), "white").save(path, "JPEG")
    import hashlib

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = CanonicalSourceLoader().load(path, expected_source_checksum_sha256=sha)
    source = dict(
        relative_path="source.jpg",
        checksum_sha256=sha,
        normalized_pixel_checksum_sha256="0" * 64,
        oriented_width=50,
        oriented_height=50,
        raw_width=50,
        raw_height=50,
        exif_orientation=frame.source.exif_orientation,
        normalization_adapter_version=frame.source.normalization_adapter_version,
    )
    handler = GridReinferenceHandler(None, tmp_path)
    checkpoint = handler.recognize({"source": source}, [{}], {}, uuid4(), 1, None, None)
    assert handler.load_checkpoint(checkpoint)["reason"] == "NORMALIZATION_FENCE"


def test_missing_artifact_is_durable_source_missing_without_inference(tmp_path):
    handler = GridReinferenceHandler(None, tmp_path)
    checkpoint = handler.recognize(
        {"source": {"relative_path": "absent.jpg", "checksum_sha256": "a" * 64}},
        [{}],
        {},
        uuid4(),
        1,
        None,
        None,
    )
    assert handler.load_checkpoint(checkpoint)["outcome"] == "source_missing"


@pytest.mark.parametrize(
    "checkpoint",
    [
        None,
        {
            "schema_version": 1,
            "workflow": "grid-reinference-v1",
            "phase": "infer",
            "cursor": 2,
            "opaque": {"preserved": True},
        },
    ],
)
def test_cancel_inside_controlled_runner_checkpoints_and_closes_runner(
    tmp_path, monkeypatch, checkpoint
):
    from contextlib import nullcontext
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from game_predictor_api.domain.jobs import (
        JobType,
        acknowledge_job_cancellation,
        checkpoint_job,
        create_job,
        renew_job_lease,
        request_job_cancellation,
        start_job,
    )
    from game_predictor_api.storage.grid_reinference import SqlAlchemyGridReinferenceRepository
    from game_predictor_worker.jobs.runtime import JobExecutionContext, _ExecutionStopped

    now = datetime.now(UTC)
    job = start_job(
        create_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=uuid4(),
            input_payload={"schema_version": 3, "inference_kind": "grid-reinference-v1"},
        ),
        worker_version="test",
        worker_id="test",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(minutes=1),
        started_at=now,
    )
    job = replace(
        job,
        stage="grid_reinference:infer",
        progress_current=3,
        progress_total=4,
        checkpoint_payload=checkpoint,
    )
    checkpoints, closes = [], []

    class Store:
        current = job

        def heartbeat(self, _job_id, **kwargs):
            self.current = renew_job_lease(
                self.current,
                lease_token=kwargs["lease_token"],
                lease_expires_at=kwargs["heartbeat_at"] + kwargs["lease_duration"],
                heartbeat_at=kwargs["heartbeat_at"],
            )
            self.current = request_job_cancellation(self.current, requested_at=now)
            return self.current

        def checkpoint(self, _job_id, **kwargs):
            checkpoints.append(kwargs)
            self.current = checkpoint_job(
                self.current,
                lease_token=kwargs["lease_token"],
                checkpoint_payload=kwargs["checkpoint_payload"],
                stage=kwargs["stage"],
                current=kwargs["current"],
                total=kwargs["total"],
                success_count=kwargs["success_count"],
                failure_count=kwargs["failure_count"],
                review_count=kwargs["review_count"],
                updated_at=kwargs["checkpointed_at"],
            )
            self.current = acknowledge_job_cancellation(
                self.current, lease_token=kwargs["lease_token"], finished_at=now
            )
            return self.current

    context = JobExecutionContext(
        Store(), job, lease_duration=timedelta(minutes=1), clock=lambda: now
    )
    session = MagicMock()
    monkeypatch.setattr(
        SqlAlchemyGridReinferenceRepository,
        "worker_record",
        lambda *_args: SimpleNamespace(document={"phase": "infer"}),
    )
    monkeypatch.setattr(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
        lambda *_args: tmp_path / "bundle",
    )
    snapshot = SimpleNamespace(
        version=SimpleNamespace(files=[SimpleNamespace(name="bundle.json", sha256="a" * 64)])
    )

    class Runner:
        def run(self, *_args, **kwargs):
            kwargs["heartbeat"]()

        def close(self):
            closes.append(True)

    class Handler(GridReinferenceHandler):
        def infer(self, context, _job, runner):
            self.raw_inference(
                {"checksum_sha256": "a" * 64},
                np.zeros((20, 20, 3)),
                {},
                snapshot,
                uuid4(),
                runner,
                context,
            )

    with pytest.raises(_ExecutionStopped):
        Handler(lambda: nullcontext(session), tmp_path, runner=Runner())(context, job)
    assert len(checkpoints) == 1 and len(closes) == 1
    assert checkpoints[0]["current"] == job.progress_current
    assert context.job.status.value == "cancelled"
    assert context.job.stage == "grid_reinference:infer"
    assert context.job.checkpoint_payload == (
        checkpoint
        if checkpoint is not None
        else {
            "schema_version": 1,
            "workflow": "grid-reinference-v1",
            "phase": "infer",
            "cursor": job.progress_current,
        }
    )


def test_quarantine_never_uses_an_active_or_legacy_lease():
    from datetime import UTC, datetime, timedelta

    from game_predictor_api.domain.jobs import (
        JobConflictError,
        JobType,
        create_job,
        quarantine_unstarted_grid_job,
        start_job,
    )

    now = datetime.now(UTC)
    legacy = create_job(
        JobType.IMAGE_GRID_REINFERENCE,
        game_id=uuid4(),
        input_payload={"schema_version": 2, "inference_kind": "pending_grid_only"},
    )
    with pytest.raises(JobConflictError) as caught:
        quarantine_unstarted_grid_job(legacy, checked_at=now)
    assert caught.value.code == "JOB_QUARANTINE_INVALID"
    active = start_job(
        create_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=uuid4(),
            input_payload={"schema_version": 3, "inference_kind": "grid-reinference-v1"},
        ),
        worker_version="fixture",
        worker_id="fixture",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(minutes=1),
        started_at=now,
    )
    with pytest.raises(JobConflictError) as caught:
        quarantine_unstarted_grid_job(active, checked_at=now)
    assert caught.value.code == "JOB_LEASE_NOT_EXPIRED"
