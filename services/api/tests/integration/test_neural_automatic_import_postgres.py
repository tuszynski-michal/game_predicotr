"""Real rendering, projection, cold replay and human protection on a disposable DB."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_POLICY,
    full_neural_prediction_geometry,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    withheld_review_item_ids,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.lateral_reprocess_protection import has_protected_lateral_owner
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageReviewQueueItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)
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
from test_reviewer_operational_geometry_postgres import _add_symbols, _app
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _seed,
)
from test_virtual_deferred_resolution_postgres import database as _database_fixture
from test_virtual_deferred_resolution_postgres import pytestmark as pytestmark

database = _database_fixture


def test_full_neural_cells_are_current_predictions_and_replay_cold(
    database: _Database, tmp_path: Path
):
    game = _provision_game(database.engine, "task0886-neural-auto")
    factory = _factory(database.engine)
    policy_payload = {
        "schema_version": 1,
        "import_kind": "image_directory",
        "neural_grid_execution_policy_version": NEURAL_AUTO_CROP_POLICY,
    }
    with game_storage_scope(game), factory.begin() as session:
        SqlAlchemyJobRepository(session)._initialize_empty_neural_projection(
            create_job(JobType.IMPORT, game_id=game, input_payload=policy_payload)
        )
        state = session.get(ImageSymbolReviewStateModel, game)
        assert state.status == state.count_projection_status == "ready"
    root = tmp_path / "artifacts"
    seed = _seed(factory, game, root, label="neural-auto", slot_count=2)
    now, token = datetime.now(UTC), uuid4()
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        source = session.get(SourceImageModel, seed.source_image_id)
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.source_image_id == source.id
            )
        )
        job.status = "processing"
        job.lease_token, job.lease_owner = token, "task0886"
        job.started_at, job.heartbeat_at, job.lease_expires_at = (
            now,
            now,
            now + timedelta(minutes=5),
        )
        job.input_payload = {**job.input_payload, **policy_payload}
        source_key, source_sha, relative = (
            source.file_execution_key,
            source.checksum_sha256,
            source.relative_path,
        )
        width, height = source.width, source.height
        rules = revision.topology_rules_version_id
        model = SymbolModelJobSnapshot.from_payload(job.input_payload["symbol_model"])
        rollout = GeometryPipelineRolloutSnapshot.from_payload(
            job.input_payload["image_geometry_rollout"]
        )
    nodes = [
        {"x": float(60 + col * 100), "y": float(50 + row * 100)}
        for row in range(4)
        for col in range(6)
    ]
    nodes[8]["x"] += 7.25
    quads = lattice_cell_quads(nodes, width=width, height=height)
    snapshot = NeuralGridSnapshot.for_game(
        500000,
        grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current,
    )
    proposal = build_neural_source_proposal(
        game_id=str(game),
        source_selection_id=str(uuid4()),
        source_checksum_sha256=source_sha,
        source_width=width,
        source_height=height,
        original_range=AttestedSequenceRange(start=100, end=101),
        snapshot=snapshot,
        detections=[
            {
                "detectionId": "a",
                "score": 0.9,
                "latticeNodes": nodes,
                "cellQuads": [q.to_dict() for q in quads],
                "cellVisibility": lattice_visibility(quads, width=width, height=height),
                "structurallyValid": True,
                "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
            }
        ],
    )
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=100, end=101),
        assignments=[{"positionIndex": 0, "detectionId": "a"}],
    )
    suite = ProductionImageStageAdapterSuite(
        root,
        repository_root=tmp_path,
        manual_geometry_import=True,
        neural_execution_policy=NEURAL_AUTO_CROP_POLICY,
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
            context, previous_results={name: result.payload for name, result in stages.items()}
        )
    candidate = ImageBatchCandidate(
        ImageFileExecution(source_key, source_sha, "b" * 64, {}, "processing", False),
        0,
        relative,
        seed.import_job_id,
        token,
        now,
    )
    store = SqlAlchemyImagePipelineStore(factory)
    with game_storage_scope(game):
        store.project_source_geometry(candidate, stage_results=stages)
        store.project_recognition(candidate, stage_results=stages)

    def current():
        with game_storage_scope(game), factory() as session:
            cells = session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(ImageSymbolReviewCellModel.game_id == game)
                .order_by(ImageSymbolReviewCellModel.cell_index)
            ).all()
            boards = session.scalars(select(RecognizedBoardModel)).all()
            assert len(boards) == 1
            board = boards[0]
            assert board.sequence_number == 100
            assert full_neural_prediction_geometry(
                board.board_geometry,
                position=0,
                sequence=board.sequence_number,
                width=width,
                height=height,
                game_id=str(game),
                source_checksum_sha256=source_sha,
            )
            item = session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            )
            assert session.get(ImageReviewQueueItemModel, item.id) is not None
            source = session.get(SourceImageModel, board.source_image_id)
            assert not withheld_review_item_ids(session, game, ((item.id, board, source),))
            assert len(cells) == 15
            assert all(
                c.review_state == "pending" and c.approved_crop_sample_id is None for c in cells
            )
            board = session.get(RecognizedBoardModel, cells[0].recognized_board_id)
            assert board.geometry_engine_name == "neural_grid_v1"
            assert board.approved_geometry_revision is None and board.geometry_revision == 0
            assert board.board_geometry["latticeNodes"] == nodes
            assert (
                session.get(SourceImageModel, seed.source_image_id).geometry_completeness_status
                == "geometry_incomplete"
            )
            assert session.get(ImageSymbolReviewStateModel, game).status == "ready"
            return [(c.id, c.revision, c.crop_sample_id) for c in cells]

    before = current()
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert current() == before
    # Human symbol feedback works on the automatic lattice without approving
    # geometry first; its training identity attests the current rendered crop.
    _add_symbols(factory, game)
    with game_storage_scope(game), factory() as session:
        cell = session.get(ImageSymbolReviewCellModel, before[0][0])
        symbol_id = session.scalar(
            select(SymbolModel.id).where(SymbolModel.game_id == game, SymbolModel.code == "WISNIA")
        )
        command = {
            "action": "reassign",
            "expectedRevision": cell.revision,
            "expectedGeometryRevision": cell.geometry_revision,
            "expectedCropSampleId": cell.crop_sample_id,
            "expectedCropChecksumSha256": cell.crop_checksum_sha256,
            "targetSymbolId": str(symbol_id),
        }
    app = _app(database, root)
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/games/{game}/symbol-cell-reviews/{before[0][0]}/decision",
                json=command,
            )
            assert response.status_code == 200, response.text
    finally:
        app.state.database_engine.dispose()
    with game_storage_scope(game), factory() as session:
        cell = session.get(ImageSymbolReviewCellModel, before[0][0])
        board = session.get(RecognizedBoardModel, cell.recognized_board_id)
        assert cell.review_state == "approved" and cell.assignment_source == "human"
        assert cell.assigned_symbol_id == symbol_id
        assert cell.approved_crop_sample_id == cell.crop_sample_id
        assert cell.approved_rendered_pixel_checksum_sha256 == cell.rendered_pixel_checksum_sha256
        assert board.approved_geometry_revision is None and board.geometry_revision == 0
    # Historical ready crops may still carry unavailable pre-upgrade counts.
    # Each batch uses a fresh session, proving recovery is not process-local.
    with game_storage_scope(game), factory.begin() as session:
        state = session.get(ImageSymbolReviewStateModel, game)
        state.count_projection_status = "unavailable"
        state.count_projection = {}
    for _ in range(5):
        with game_storage_scope(game), factory.begin() as session:
            complete = SqlAlchemyImageSymbolReviewRepository(
                session
            ).ensure_current_count_projection_next_batch(game, batch_size=5)
        if complete:
            break
    assert complete
    with game_storage_scope(game), factory() as session:
        state = session.get(ImageSymbolReviewStateModel, game)
        assert state.status == state.count_projection_status == "ready"
        assert state.count_projection["all"] == {"pending": 14, "approved": 1}
    # A saved human issue must protect this owner on subsequent reprocesses.
    with game_storage_scope(game), factory.begin() as session:
        cell = session.get(ImageSymbolReviewCellModel, before[1][0])
        cell.quality_issue = "grid_issue"
        session.flush()
        assert has_protected_lateral_owner(
            session,
            job=session.get(JobModel, seed.import_job_id),
            sequence_number=100,
            source_checksum_sha256=source_sha,
        )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory() as session:
        assert session.get(ImageSymbolReviewCellModel, before[1][0]).quality_issue == "grid_issue"
        approved = session.get(ImageSymbolReviewCellModel, before[0][0])
        assert approved.assigned_symbol_id == symbol_id and approved.review_state == "approved"


def test_historical_boards_cannot_be_marked_empty_ready(database: _Database, tmp_path: Path):
    game = _provision_game(database.engine, "task0886-history")
    factory = _factory(database.engine)
    _seed(factory, game, tmp_path / "artifacts", label="history", slot_count=2)
    with game_storage_scope(game), factory.begin() as session:
        SqlAlchemyJobRepository(session)._initialize_empty_neural_projection(
            create_job(
                JobType.IMPORT,
                game_id=game,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "neural_grid_execution_policy_version": NEURAL_AUTO_CROP_POLICY,
                },
            )
        )
        assert session.get(ImageSymbolReviewStateModel, game) is None
