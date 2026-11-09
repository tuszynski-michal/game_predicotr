"""Production proposal processing writes pending symbols, never human labels."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.domain.jobs import JobType, wait_for_review
from game_predictor_api.domain.neural_crop_policy import SYMBOL_REVIEW_CROP_POLICY
from game_predictor_api.domain.v3_engine_acceptance import SYMBOL_REVIEW_ENGINE_POLICY
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_reinference import SqlAlchemyGridReinferenceRepository
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from game_predictor_api.storage.job_repository import (
    SqlAlchemyJobRepository,
    apply_job_to_record,
    job_from_record,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
)
from game_predictor_worker.images.grid_reinference_handler import GridReinferenceHandler
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from sqlalchemy import select, text
from test_v3_engine_acceptance_postgres import (
    current_partition_budget as current_partition_budget,
)
from test_v3_engine_acceptance_postgres import (
    database as database,
)
from test_v3_engine_acceptance_postgres import (
    execution,
    snapshot_state,
)
from test_v3_engine_acceptance_postgres import (
    pytestmark as pytestmark,
)


def _assert_visible_pending_symbols(session, game, import_job):
    page = SqlAlchemySymbolCellReviewQueryRepository(session).list_items(
        review_filter=SymbolCellReviewListFilter(
            game_id=game,
            symbol_id=None,
            state=SymbolCellReviewFilterState.PENDING,
            include_all_symbols=True,
            import_job_id=import_job,
        ),
        after_key=None,
        before_key=None,
        limit=100,
    )
    assert len(page.items) == 30


def test_new_import_materializes_full_cells_pending_without_geometry_approval(database, tmp_path):  # noqa: F811
    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy=SYMBOL_REVIEW_ENGINE_POLICY,
        crop_policy=SYMBOL_REVIEW_CROP_POLICY,
        fit_reason="NEURAL_GRID_FIT_OUTLIERS",
        workflow_recheck=True,
    )
    with game_storage_scope(game):
        store = SqlAlchemyImagePipelineStore(factory)
        store.project_recognition(candidate, stage_results=stages)
    before = snapshot_state(factory, game, seed)
    assert before[0] == "accepted" and before[5] == "geometry_complete"
    assert len(before[6]) == 30
    with game_storage_scope(game), factory() as session:
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        ).all()
        assert len(boards) == 2
        assert all(b.geometry_approved_at is None for b in boards)
        assert all(b.geometry_approved_by is None for b in boards)
        assert all(b.approved_geometry_revision is None for b in boards)
        cells = session.scalars(
            select(ImageSymbolReviewCellModel).where(ImageSymbolReviewCellModel.game_id == game)
        ).all()
        assert len(cells) == 30 and all(c.review_state == "pending" for c in cells)
        assert all(c.approved_geometry_revision is None for c in cells)
        _assert_visible_pending_symbols(session, game, seed.import_job_id)
        manifests = session.scalars(
            select(BoardRenderManifestModel).where(BoardRenderManifestModel.game_id == game)
        ).all()
        assert len(manifests) == 2
        assert {
            c["renderSpec"]["configuration"]["paddingFraction"]
            for m in manifests
            for c in m.cells["cells"]
        } == {0.0}
        assert session.scalar(select(ImageReviewItemModel.status).limit(1)) == "pending"
        payload = session.get(JobModel, seed.import_job_id).input_payload
        assert (
            payload["neural_grid_operation_pin"]["automaticQualification"]["state"] == "unqualified"
        )
    with game_storage_scope(game), factory.begin() as session:
        # Creation applies the review-purpose policy after the request identity
        # lookup. A lost-response replay must retrieve that exact stored pin.
        request = {**payload, "neural_grid_execution_policy_version": "neural-auto-crop-v2"}
        assert (
            SqlAlchemyJobRepository(session).find_neural_operation_pin(
                game_id=game, job_type=JobType.IMPORT, input_payload=request
            )
            == payload["neural_grid_operation_pin"]
        )
        assert (
            SqlAlchemyJobRepository(session).find_neural_operation_pin(
                game_id=game,
                job_type=JobType.IMPORT,
                input_payload={**request, "source_display_name": "other"},
            )
            is None
        )
    # Fresh writer/session, as when acknowledgement was lost after commit.
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed) == before


def test_existing_deferred_source_reaches_pending_symbols_through_real_worker(database, tmp_path):  # noqa: F811
    game, factory, seed, candidate, stages = execution(
        database, tmp_path, acceptance_policy="v3-engine-acceptance-v3"
    )
    root = tmp_path / "artifacts"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    assert snapshot_state(factory, game, seed)[6] == []
    with game_storage_scope(game), factory.begin() as session:
        # execution() supersedes the seed's deferrals for its automatic-import
        # fixtures. Retain them here to model the pre-existing deferred batch.
        for pending in session.scalars(
            select(ImageBoardGeometryPendingModel).where(
                ImageBoardGeometryPendingModel.game_id == game
            )
        ):
            pending.status, pending.superseded_at = "pending", None
        record = session.get(JobModel, seed.import_job_id)
        old_pin = deepcopy(record.input_payload)
        job = job_from_record(record)
        snapshot = deepcopy(job.input_payload["neural_grid_proposal"])
        apply_job_to_record(
            record, wait_for_review(job, lease_token=job.lease_token, updated_at=datetime.now(UTC))
        )
    evidence = stages["board_cell_geometry"].payload["structuredGeometry"]["globalInitialization"][
        "v3EngineAcceptance"
    ]

    class Repository(SqlAlchemyGridReinferenceRepository):
        def model(self, game_id, version_id):
            assert game_id == game and version_id is None
            return deepcopy(snapshot), 1

    class Handler(GridReinferenceHandler):
        calls = 0

        def recognize(
            self,
            source_document,
            frozen,
            pin,
            operation_id,
            ordinal,
            runner,
            context,
            *,
            execution_policy="neural-auto-crop-v1",
            operation_pin=None,
        ):
            self.calls += 1
            assert execution_policy == SYMBOL_REVIEW_CROP_POLICY
            assert operation_pin["automaticQualification"]["state"] == "unqualified"
            assert all(item["board"] is None for item in frozen)
            proposal = evidence["proposal"]
            return self.save_checkpoint(
                operation_id,
                ordinal,
                {
                    "proposal": proposal,
                    "binding": evidence["binding"],
                    "executionPolicy": execution_policy,
                    "byPosition": {str(i): d for i, d in enumerate(proposal["detections"])},
                },
            )

    body = {
        "idempotencyKey": str(uuid4()),
        "selector": {
            "categories": ["deferred"],
            "importJobIds": [str(seed.import_job_id)],
            "sequenceStart": None,
            "sequenceEnd": None,
        },
        "modelVersionId": None,
        "executionScope": "pilot",
    }
    with game_storage_scope(game), factory.begin() as session:
        view = Repository(session, root).prepare(game, body, "fixture-operator")
    operation_id, job_id = UUID(view["operationId"]), UUID(view["jobId"])
    store = SqlAlchemyWorkerJobStore(factory)
    handler = Handler(factory, root, runner=SimpleNamespace(close=lambda: None))

    worker = LocalJobWorker(
        store,
        {JobType.IMAGE_GRID_REINFERENCE: handler},
        worker_id="task1176",
        worker_version="fixture",
    )
    assert worker.run_once() is JobExecutionResult.WAITING_FOR_REVIEW
    with game_storage_scope(game), factory.begin() as session:
        repo = Repository(session, root)
        view = repo.get(game, operation_id)
        assert view["targetCount"] == 2
        freeze = {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": view["revision"],
            "manifestSha256": view["manifestSha256"],
        }
        view = repo.execute(game, operation_id, "freeze", freeze, "fixture-operator")
        start = {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": view["revision"],
            "manifestSha256": view["manifestSha256"],
            "confirm": True,
        }
        repo.execute(game, operation_id, "start", start, "fixture-operator")
    with patch(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require"
    ):
        outcome = worker.run_once()
    with factory() as session:
        failed = session.get(JobModel, job_id)
        assert outcome is JobExecutionResult.COMPLETED, (failed.error_code, failed.error_message)
    assert handler.calls == 1
    with game_storage_scope(game), factory() as session:
        current = Repository(session, root).get(game, operation_id)
        assert current["effectStats"]["automaticWrittenBoardCount"] == 2, current
        assert session.get(JobModel, job_id).status.value == "completed"
        assert session.get(JobModel, seed.import_job_id).input_payload == old_pin
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        ).all()
        assert len(boards) == 2 and all(b.approved_geometry_revision is None for b in boards)
        assert all(b.geometry_approved_by is None for b in boards)
        cells = session.scalars(
            select(ImageSymbolReviewCellModel).where(ImageSymbolReviewCellModel.game_id == game)
        ).all()
        assert len(cells) == 30 and all(c.review_state == "pending" for c in cells)
        _assert_visible_pending_symbols(session, game, seed.import_job_id)
        manifests = session.scalars(
            select(BoardRenderManifestModel).where(BoardRenderManifestModel.game_id == game)
        ).all()
        assert {
            c["renderSpec"]["configuration"]["paddingFraction"]
            for m in manifests
            for c in m.cells["cells"]
        } == {0.0}
    # Start acknowledgement lost: fresh repository replays the same receipt.
    with game_storage_scope(game), factory.begin() as session:
        replay = Repository(session, root).execute(
            game, operation_id, "start", start, "fixture-operator"
        )
        assert replay["jobId"] == str(job_id) and replay["state"] == "completed"
    assert worker.run_once() is JobExecutionResult.NO_JOB
    command_file, result_file = tmp_path / "replay.json", tmp_path / "result.json"
    command_file.write_text(
        json.dumps(
            {"game": str(game), "operation": str(operation_id), "root": str(root), "command": start}
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("_symbol_review_cold_replay.py")),
            str(command_file),
            str(result_file),
        ],
        env={**os.environ, "GAME_PREDICTOR_DATABASE_URL": database.url},
        capture_output=True,
        check=True,
        timeout=30,
    )
    cold = json.loads(result_file.read_text(encoding="utf-8"))
    assert cold == {
        "pid": cold["pid"],
        "state": "completed",
        "jobId": str(job_id),
        "pendingCount": 30,
    }
    assert cold["pid"] != os.getpid()


def test_qualified_reinference_keeps_calibration_pin_and_result_gates(database, tmp_path):  # noqa: F811
    from test_calibrated_acceptance_postgres import calibrated_report

    game, factory, seed, candidate, stages = execution(
        database,
        tmp_path,
        acceptance_policy="v3-engine-acceptance-v4",
        crop_policy="neural-auto-crop-v2",
        evaluated_game=True,
        calibrated_report=calibrated_report,
        workflow_recheck=True,
        slot_count=9,
    )
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory.begin() as session:
        record = session.get(JobModel, seed.import_job_id)
        original_pin = deepcopy(record.input_payload["neural_grid_operation_pin"])
        snapshot = deepcopy(record.input_payload["neural_grid_proposal"])
        job = job_from_record(record)
        apply_job_to_record(
            record, wait_for_review(job, lease_token=job.lease_token, updated_at=datetime.now(UTC))
        )
    assert original_pin["automaticQualification"]["state"] == "qualified"

    class Repository(SqlAlchemyGridReinferenceRepository):
        def model(self, game_id, version_id):
            assert game_id == game and version_id is None
            return deepcopy(snapshot), 1

    body = {
        "idempotencyKey": str(uuid4()),
        "selector": {
            "categories": ["all_automatic"],
            "importJobIds": [str(seed.import_job_id)],
            "sequenceStart": None,
            "sequenceEnd": None,
        },
        "modelVersionId": None,
        "executionScope": "pilot",
    }
    with game_storage_scope(game), factory.begin() as session:
        repo = Repository(session, tmp_path)
        view = repo.prepare(game, body, "fixture-operator")
        assert view["acceptancePolicy"] == "v3-engine-acceptance-v4"
        payload = session.get(JobModel, UUID(view["jobId"])).input_payload
        pin = payload["neural_grid_operation_pin"]
        assert pin == original_pin and pin["contractVersion"] == "neural-grid-operation-pin-v3"
        assert payload["acceptance_policy"] == "v3-engine-acceptance-v4"
        targets = repo.source_targets(game, seed.source_image_id, body["selector"])
        source_document = {
            "source": session.execute(
                text("SELECT to_jsonb(s) FROM source_images s WHERE game_id=:game AND id=:source"),
                {"game": game, "source": seed.source_image_id},
            ).scalar_one(),
            "geometryContext": session.execute(
                text(
                    "SELECT to_jsonb(g) FROM image_source_geometry_revisions g "
                    "WHERE game_id=:game AND id=:id"
                ),
                {"game": game, "id": UUID(targets[0]["board"]["source_geometry_revision_id"])},
            ).scalar_one(),
        }
    structured = stages["board_cell_geometry"].payload["structuredGeometry"]
    proposal = structured["globalInitialization"]["v3EngineAcceptance"]["proposal"]
    evidence = {
        board["detectionId"]: board["neuralCalibrationEvidence"] for board in structured["boards"]
    }
    handler = GridReinferenceHandler(factory, tmp_path / "artifacts")
    with patch.object(
        handler,
        "raw_inference",
        return_value={"detections": proposal["detections"], "calibrationEvidence": evidence},
    ) as infer:
        saved = handler.recognize(
            source_document,
            targets,
            snapshot,
            UUID(view["operationId"]),
            1,
            None,
            SimpleNamespace(heartbeat=lambda: None),
            execution_policy="neural-auto-crop-v2",
            operation_pin=pin,
        )
    assert infer.call_args.kwargs["calibration_pin"] == pin
    checkpoint = handler.load_checkpoint(saved)
    assert checkpoint["calibrationPin"] == pin
    assert handler.automatic_blockers(checkpoint, 0) == ()
    checkpoint["calibrationEvidence"] = {}
    assert "COMPLETENESS_EVIDENCE_REQUIRED" in handler.automatic_blockers(checkpoint, 0)
