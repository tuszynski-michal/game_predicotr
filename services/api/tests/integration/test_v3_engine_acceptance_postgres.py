"""New neural acceptance, cold replay and rollback on disposable PostgreSQL."""

import json
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4

import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_POLICY
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_ACTOR,
    V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY,
    V3_ENGINE_ACCEPTANCE_POLICY,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.v3_engine_acceptance_repository import finalize_v3_engine_acceptance
from game_predictor_worker.images import pipeline_store
from game_predictor_worker.images.board_cell_geometry_activation import (
    board_cell_processing_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.orchestration import ImageBatchCandidate, ImageFileExecution
from game_predictor_worker.images.pipeline_contract import GeometryPipelineRolloutSnapshot
from game_predictor_worker.images.pipeline_execution import (
    ImageStageContext,
    StoredImageStageResult,
    validate_stage_payload,
)
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from game_predictor_worker.images.production_workflow import ProductionImageStageAdapterSuite
from sqlalchemy import select
from test_virtual_deferred_resolution_postgres import _factory, _provision_game, _seed
from test_virtual_deferred_resolution_postgres import database as _database_fixture
from test_virtual_deferred_resolution_postgres import pytestmark as pytestmark

_SEED_COUNTER = count(1)


@pytest.fixture(scope="module")
def database():
    # One schema migration per module; every case owns a fresh game partition.
    # Persist the exact target for safe cleanup if an external timeout kills pytest.
    generator = _database_fixture.__wrapped__()
    value = next(generator)
    from pathlib import Path

    from sqlalchemy.engine import make_url

    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/task1017-postgres-receipt.json").write_text(
        json.dumps({"database": make_url(value.url).database}), encoding="utf-8"
    )
    try:
        yield value
    finally:
        with suppress(StopIteration):
            next(generator)


def execution(database, tmp_path, *, legacy=False, missing=False):
    game = _provision_game(database.engine, "task1017-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    root = tmp_path / "artifacts"
    # The existing source fixture derives pixels from label length; distinct
    # lengths also give distinct global file-execution identities per game.
    seed = _seed(
        factory, game, root, label="v3-acceptance" + "x" * next(_SEED_COUNTER), slot_count=2
    )
    now, token = datetime.now(UTC), uuid4()
    snapshot = NeuralGridSnapshot.for_game(
        500000,
        grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current,
    )
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        assert revision.game_id == game and revision.source_image_id == seed.source_image_id, (
            f"Fixture selected game/source {revision.game_id}/{revision.source_image_id}; "
            f"intended {game}/{seed.source_image_id}"
        )
        job.status = "processing"
        job.lease_token, job.lease_owner = token, "task1017"
        job.started_at, job.heartbeat_at, job.lease_expires_at = (
            now,
            now,
            now + timedelta(minutes=5),
        )
        job.input_payload = {
            **job.input_payload,
            "neural_grid_execution_policy_version": NEURAL_AUTO_CROP_POLICY,
            "neural_grid_proposal": snapshot.to_payload(),
            **({} if legacy else {V3_ENGINE_ACCEPTANCE_PAYLOAD_KEY: V3_ENGINE_ACCEPTANCE_POLICY}),
        }
        for pending in session.scalars(
            select(ImageBoardGeometryPendingModel).where(
                ImageBoardGeometryPendingModel.game_id == game,
                ImageBoardGeometryPendingModel.source_image_id == seed.source_image_id,
            )
        ):
            if not missing or pending.position_index == 0:
                pending.status = "superseded"
                pending.superseded_at = now
        width, height, rules = source.width, source.height, revision.topology_rules_version_id
        source_key, source_sha, relative = (
            source.file_execution_key,
            source.checksum_sha256,
            source.relative_path,
        )
        model = SymbolModelJobSnapshot.from_payload(job.input_payload["symbol_model"])
        rollout = GeometryPipelineRolloutSnapshot.from_payload(
            job.input_payload["image_geometry_rollout"]
        )
    detections = []
    for position in range(1 if missing else 2):
        nodes = [
            {"x": float(60 + column * 80), "y": float(25 + position * 190 + row * 50)}
            for row in range(4)
            for column in range(6)
        ]
        quads = lattice_cell_quads(nodes, width=width, height=height)
        detections.append(
            {
                "detectionId": str(position),
                "score": 0.9,
                "latticeNodes": nodes,
                "cellQuads": [quad.to_dict() for quad in quads],
                "cellVisibility": lattice_visibility(quads, width=width, height=height),
                "structurallyValid": True,
                "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
            }
        )
    proposal = build_neural_source_proposal(
        game_id=str(game),
        source_selection_id=str(uuid4()),
        source_checksum_sha256=source_sha,
        source_width=width,
        source_height=height,
        original_range=AttestedSequenceRange(start=100, end=101),
        snapshot=snapshot,
        detections=detections,
    )
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=100, end=101),
        assignments=[{"positionIndex": i, "detectionId": str(i)} for i in range(len(detections))],
    )
    suite = ProductionImageStageAdapterSuite(
        root,
        repository_root=tmp_path,
        manual_geometry_import=True,
        neural_execution_policy=NEURAL_AUTO_CROP_POLICY,
        engine_acceptance_policy=None if legacy else V3_ENGINE_ACCEPTANCE_POLICY,
        symbol_model=model,
        geometry_rollout=rollout,
        page_geometry_manifest={
            source_sha: {
                "status": "review_required",
                "neuralProposal": proposal,
                "neuralProposalBinding": binding,
            }
        },
        board_cell_processing=board_cell_processing_snapshot(
            cell_output_size=model.crop_output_size,
            topology=BoardCellTopology(rows=3, columns=5, rules_version_id=str(rules)),
        ),
    )
    context = ImageStageContext(
        seed.import_job_id, source_key, source_sha, relative, "b" * 64, {}, (100, 101)
    )
    stages = {}
    for adapter in suite.adapters():
        if adapter.stage == "discovery":
            continue
        payload = adapter.execute(context)
        validate_stage_payload(adapter.stage, payload, context)
        stages[adapter.stage] = StoredImageStageResult(adapter.version, payload)
        context = replace(
            context, previous_results={name: item.payload for name, item in stages.items()}
        )
    candidate = ImageBatchCandidate(
        ImageFileExecution(source_key, source_sha, "b" * 64, {}, "processing", False),
        0,
        relative,
        seed.import_job_id,
        token,
        now,
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_source_geometry(
            candidate, stage_results=stages
        )
    return game, factory, seed, candidate, stages


def snapshot_state(factory, game, seed):
    with game_storage_scope(game), factory() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id,
            )
        ).all()
        assert all(
            board.approved_geometry_revision is None and board.geometry_approved_by is None
            for board in boards
        )
        cells = session.scalars(
            select(ImageSymbolReviewCellModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
            )
            .where(
                ImageSymbolReviewCellModel.game_id == game,
                RecognizedBoardModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSymbolReviewCellModel.id)
        ).all()
        assert all(
            cell.game_id == game and cell.import_job_id == seed.import_job_id for cell in cells
        ), (
            f"Snapshot intended {game}/{seed.import_job_id}; selected "
            f"{sorted({(str(cell.game_id), str(cell.import_job_id)) for cell in cells})}"
        )
        return (
            revision.status,
            revision.created_by,
            revision.geometry_checksum_sha256,
            revision.board_geometries,
            revision.global_initialization,
            session.get(SourceImageModel, seed.source_image_id).geometry_completeness_status,
            [(cell.id, cell.revision, cell.crop_sample_id, cell.quality_issue) for cell in cells],
        )


@pytest.mark.parametrize("legacy,missing", [(False, False), (True, False), (False, True)])
def test_complete_acceptance_and_legacy_or_deferred_cold_replay(
    database, tmp_path, legacy, missing
):
    game, factory, seed, candidate, stages = execution(
        database, tmp_path, legacy=legacy, missing=missing
    )
    before = snapshot_state(factory, game, seed)
    assert before[0] == "needs_review"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == ("needs_review" if legacy or missing else "accepted")
    assert after[1] == ("system:image-pipeline-v0.10" if legacy else V3_ENGINE_ACCEPTANCE_ACTOR)
    assert after[2:5] == before[2:5]
    assert after[5] == ("geometry_incomplete" if legacy or missing else "geometry_complete")
    assert len(after[6]) == (15 if missing else 30)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_source_geometry(
            candidate, stage_results=stages
        )
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == after


@pytest.mark.parametrize(
    "fault", ["model", "owner", "revision", "partial", "grid_issue", "stale_issue"]
)
def test_persisted_conflicts_block_acceptance_without_changing_payload(database, tmp_path, fault):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    before = snapshot_state(factory, game, seed)
    assert before[0] == "accepted"
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(
                ImageSourceGeometryRevisionModel.game_id == game,
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        board = session.scalar(
            select(RecognizedBoardModel)
            .where(RecognizedBoardModel.source_image_id == seed.source_image_id)
            .order_by(RecognizedBoardModel.position_index)
            .limit(1)
        )
        if fault == "model":
            job.input_payload = {**job.input_payload, "neural_grid_proposal": {"drift": True}}
        elif fault == "owner":
            item = session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.game_id == game,
                    ImageReviewItemModel.recognized_board_id == board.id,
                )
            )
            item.sequence_number = 999
        elif fault == "revision":
            board.geometry_revision += 1
        elif fault == "partial":
            board.completeness_status = "pending_partial"
            board.unavailable_cell_indices = [0]
        elif fault in ("grid_issue", "stale_issue"):
            cell = session.scalar(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game,
                    ImageSymbolReviewCellModel.recognized_board_id == board.id,
                )
                .limit(1)
            )
            cell.quality_issue = "grid_issue"
            if fault == "stale_issue":
                cell.source_geometry_revision_id = session.scalar(
                    select(ImageSourceGeometryRevisionModel.id)
                    .where(
                        ImageSourceGeometryRevisionModel.game_id == game,
                        ImageSourceGeometryRevisionModel.source_image_id == source.id,
                    )
                    .order_by(ImageSourceGeometryRevisionModel.revision)
                    .limit(1)
                )
        blockers = finalize_v3_engine_acceptance(
            session,
            job=job,
            source=source,
            revision=revision,
            structured=stages["board_cell_geometry"].payload["structuredGeometry"],
        )
        assert bool(blockers) == (fault != "stale_issue")
    after = snapshot_state(factory, game, seed)
    assert after[0] == ("accepted" if fault == "stale_issue" else "needs_review")
    assert after[2:5] == before[2:5]


def test_current_grid_issue_survives_cold_retry_and_removes_engine_acceptance(database, tmp_path):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory.begin() as session:
        cell = session.scalar(
            select(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game,
                ImageSymbolReviewCellModel.import_job_id == seed.import_job_id,
            )
            .limit(1)
        )
        cell.quality_issue = "grid_issue"
    before = snapshot_state(factory, game, seed)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    after = snapshot_state(factory, game, seed)
    assert after[0] == "needs_review"
    assert after[2:5] == before[2:5]
    assert after[6] == before[6]


def test_failed_gate_rolls_back_engine_acceptance_and_recognition(database, tmp_path, monkeypatch):
    game, factory, seed, candidate, stages = execution(database, tmp_path)
    before = snapshot_state(factory, game, seed)

    def fail(*args, **kwargs):
        raise RuntimeError("TASK1017 forced gate failure")

    monkeypatch.setattr(pipeline_store, "recompute_source_image_geometry_completeness", fail)
    with game_storage_scope(game), pytest.raises(RuntimeError, match="forced gate failure"):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == before
