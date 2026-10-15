"""One owned disposable DB: durable preparation, RLS and real automatic writes."""

from __future__ import annotations

import copy
import json
import os
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.jobs import JobType, wait_for_review
from game_predictor_api.domain.neural_grid_proposal import (
    build_neural_source_binding,
    build_neural_source_proposal,
)
from game_predictor_api.storage import game_data_v2_manifest_v11 as v11
from game_predictor_api.storage import game_partition_lifecycle as lifecycle
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_reinference import (
    SqlAlchemyGridReinferenceRepository,
    authorize_generic_retry,
)
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from game_predictor_api.storage.job_repository import apply_job_to_record, job_from_record
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
)
from game_predictor_worker.images.grid_reinference_handler import GridReinferenceHandler
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from game_predictor_worker.jobs.runtime import JobExecutionResult, LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from grid_reinference_schema_support import assert_grid_reinference_schema_postgres
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from test_v3_engine_acceptance_postgres import execution
from test_virtual_deferred_resolution_postgres import _provision_game

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


@pytest.fixture(scope="module")
def database():
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task0999_{token}_test", f"task0999_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    arguments = {"connect_timeout": 5, "options": "-c statement_timeout=30000"}
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args=arguments,
    )
    engine = create_engine(url.set(database=name), connect_args=arguments)
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    receipt = {
        "database": name,
        "role": role,
        "pythonPid": os.getpid(),
        "operatorDatabaseChanged": False,
    }
    evidence_prefix = os.environ.get("GAME_PREDICTOR_GRID_TEST_EVIDENCE_PREFIX", "TASK-0999")
    assert all(character.isalnum() or character in "-_" for character in evidence_prefix)
    destination = Path("artifacts/audits") / f"{evidence_prefix}_PG_RECEIPT.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with maintenance.connect() as connection:
        receipt["owner"] = connection.scalar(text("SELECT current_user"))
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    try:
        command.upgrade(config, "0158_new_game_v3_bootstrap")
        with ExitStack() as stack:
            for field in ("CREATE_TABLES", "DELETE_TABLES", "VERSION"):
                stack.enter_context(patch.object(lifecycle, field, getattr(v11, field)))
            _provision_game(engine, "task0999-existing-v11")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
            )
        assert_grid_reinference_schema_postgres(engine, config, role)
        yield SimpleNamespace(engine=engine, config=config, role=role)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            owner = connection.scalar(
                text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:name"),
                {"name": name},
            )
            pids = list(
                connection.scalars(
                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"), {"name": name}
                )
            )
            receipt.update(ownerBeforeCleanup=owner, pidsBeforeCleanup=pids)
            destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            assert owner == receipt["owner"] and not pids, "Refuse unsafe fixture cleanup"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            receipt.update(
                databaseRemaining=connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
                ),
                roleRemaining=connection.scalar(
                    text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
                ),
                phase="cleaned",
            )
        destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        maintenance.dispose()


@pytest.mark.parametrize(
    "scenario",
    [
        "accepted",
        "target_conflict",
        "manual_sibling",
        "grid_issue",
        "rollback_retry",
        "prepare_restart",
        "cleanup_reset",
        "cleanup_range",
        "source_deleted",
        "unchanged",
        "global_source_conflict",
        "cancel_between_sources",
        "cancel_prepare",
        "late_source",
        "foreign_pending_deferred",
        "deferred_stats",
        "inconsistent_partial_stats",
    ],
)
def test_prepare_wait_freeze_start_real_write_and_lost_reply(database, tmp_path, scenario):
    from test_virtual_deferred_resolution_postgres import _factory

    def role(_session, _transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{database.role}"')

    def application_factory(engine):
        factory = _factory(engine)
        event.listen(factory, "after_begin", role)
        return factory

    with patch("test_v3_engine_acceptance_postgres._factory", application_factory):
        game, factory, seed, candidate, stages = execution(
            database, tmp_path, missing=scenario == "deferred_stats"
        )
    root = tmp_path / "artifacts"
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory.begin() as session:
        record = session.get(JobModel, seed.import_job_id)
        from game_predictor_api.storage.board_search_projection_repository import (
            SqlAlchemyBoardSearchProjectionRepository,
        )

        SqlAlchemyBoardSearchProjectionRepository(session).reconcile_import_job(seed.import_job_id)
        old_job = job_from_record(record)
        snapshot = copy.deepcopy(old_job.input_payload["neural_grid_proposal"])
        apply_job_to_record(
            record,
            wait_for_review(old_job, lease_token=old_job.lease_token, updated_at=datetime.now(UTC)),
        )
        session.flush()
        projection = SqlAlchemyBoardSearchProjectionRepository(session)
        for item_id in session.scalars(select(ImageReviewItemModel.id)):
            projection.sync_review_item(item_id)

    late_seed = None
    if scenario in {"cancel_between_sources", "foreign_pending_deferred"}:
        from test_virtual_deferred_resolution_postgres import _seed

        # A later UUID fixes import ordering; this helper creates only a pending slot.
        original_job_model = JobModel

        def later_job(**kwargs):
            return original_job_model(
                id=UUID(int=(1 << 128) - (1 if scenario == "cancel_between_sources" else 2)),
                **kwargs,
            )

        with patch("test_virtual_deferred_resolution_postgres.JobModel", later_job):
            late_seed = _seed(
                factory,
                game,
                root,
                label="c" * (40 if scenario == "cancel_between_sources" else 41),
                slot_count=1,
                sequence_base=200 if scenario == "cancel_between_sources" else 100,
            )

    class FixtureRepository(SqlAlchemyGridReinferenceRepository):
        def model(self, game_id, version_id):
            assert game_id == game and version_id is None
            return copy.deepcopy(snapshot), 1

    class FixtureHandler(GridReinferenceHandler):
        calls = 0

        def recognize(self, source_document, frozen, pin, operation_id, ordinal, runner, context):
            self.calls += 1
            source, geometry = source_document["source"], source_document["geometryContext"]
            if frozen[0]["board"] is None and scenario != "deferred_stats":
                return self.save_checkpoint(
                    operation_id, ordinal, {"outcome": "unchanged", "byPosition": {}}
                )
            detections = []
            for index, item in enumerate(frozen):
                nodes = (
                    [
                        {
                            "x": float(61 + column * 80),
                            "y": float(25 + item["positionIndex"] * 190 + row * 50),
                        }
                        for row in range(4)
                        for column in range(6)
                    ]
                    if item["board"] is None
                    else [
                        {"x": node["x"] + (0.0 if scenario == "unchanged" else 1.0), "y": node["y"]}
                        for node in item["board"]["board_geometry"]["latticeNodes"]
                    ]
                )
                from game_predictor_api.domain.neural_grid_proposal import (
                    NeuralGridSnapshot,
                    lattice_cell_quads,
                    lattice_visibility,
                )

                quads = lattice_cell_quads(
                    nodes, width=source["oriented_width"], height=source["oriented_height"]
                )
                detections.append(
                    dict(
                        detectionId=str(index),
                        score=0.9,
                        latticeNodes=nodes,
                        cellQuads=[quad.to_dict() for quad in quads],
                        cellVisibility=lattice_visibility(
                            quads, width=source["oriented_width"], height=source["oriented_height"]
                        ),
                        structurallyValid=True,
                        reasonCodes=["NEURAL_GRID_GATE_UNCALIBRATED"],
                    )
                )
            proposal = build_neural_source_proposal(
                game_id=str(game),
                source_selection_id=str(seed.import_job_id),
                source_checksum_sha256=source["checksum_sha256"],
                source_width=source["oriented_width"],
                source_height=source["oriented_height"],
                original_range=AttestedSequenceRange(
                    start=geometry["sequence_range_start"], end=geometry["sequence_range_end"]
                ),
                snapshot=NeuralGridSnapshot.from_payload(pin),
                detections=detections,
            )
            binding = build_neural_source_binding(
                proposal,
                confirmed_range=AttestedSequenceRange(
                    start=geometry["sequence_range_start"], end=geometry["sequence_range_end"]
                ),
                assignments=[
                    dict(positionIndex=item["positionIndex"], detectionId=str(i))
                    for i, item in enumerate(frozen)
                ],
            )
            return self.save_checkpoint(
                operation_id,
                ordinal,
                dict(
                    proposal=proposal,
                    binding=binding,
                    byPosition={
                        str(item["positionIndex"]): detections[i] for i, item in enumerate(frozen)
                    },
                ),
            )

    if scenario == "inconsistent_partial_stats":
        # Deliberately inconsistent current projection: its no-pixels mask
        # differs from the retained render manifest. Production validation must
        # reject it and roll back all source effects, including statistics.
        with game_storage_scope(game), factory.begin() as session:
            cell = session.scalar(
                select(ImageSymbolReviewCellModel)
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .limit(1)
            )
            board = session.get(RecognizedBoardModel, cell.recognized_board_id)
            cell.asset_mode = "none"
            cell.source_visibility = "outside"
            cell.source_available = False
            from game_predictor_api.domain.geometry_qualification import (
                GEOMETRY_QUALIFICATION_VERSION_V3,
                GeometryQualification,
            )

            board.geometry_qualification = GeometryQualification(
                completeness_status="pending_partial",
                unavailable_cell_indices=(cell.cell_index,),
                exclude_from_geometry_training=True,
                exclusion_reason="missing_pixels",
                version=GEOMETRY_QUALIFICATION_VERSION_V3,
                fully_unavailable_cell_indices=(cell.cell_index,),
            ).to_dict()
            board.completeness_status = "pending_partial"
            board.unavailable_cell_indices = [cell.cell_index]
            for attribute in (
                "crop_sample_id",
                "crop_checksum_sha256",
                "crop_relative_path",
                "render_spec_checksum_sha256",
                "rendered_pixel_checksum_sha256",
                "render_identity_v2_sha256",
                "logical_cell_key",
                "logical_cell_key_v2",
                "extractor_version",
                "prediction_symbol_code",
                "prediction_confidence",
                "verification_outcome",
                "verified_symbol_id_v2",
            ):
                setattr(cell, attribute, None)
    if scenario == "grid_issue":
        with game_storage_scope(game), factory.begin() as session:
            cell = session.scalar(
                select(ImageSymbolReviewCellModel)
                .order_by(ImageSymbolReviewCellModel.cell_index)
                .limit(1)
            )
            assert cell is not None
            cell.quality_issue = "grid_issue"
            cell.review_state = "pending"
    prepare = {
        "idempotencyKey": str(uuid4()),
        "selector": {
            "categories": ["deferred"]
            if scenario == "foreign_pending_deferred"
            else ["all_automatic", "deferred"],
            "importJobIds": [],
            "sequenceStart": 100 if scenario == "manual_sibling" else None,
            "sequenceEnd": 100 if scenario == "manual_sibling" else None,
        },
        "modelVersionId": None,
        "executionScope": "pilot",
    }
    with game_storage_scope(game), factory.begin() as session:
        view = FixtureRepository(session, root).prepare(game, prepare, "fixture-operator")
    operation_id = UUID(view["operationId"])
    with game_storage_scope(game), factory.begin() as session:
        assert FixtureRepository(session, root).prepare(game, prepare, "fixture-operator")[
            "operationId"
        ] == str(operation_id)
    runner_closes = []
    handler = FixtureHandler(
        factory, root, runner=SimpleNamespace(close=lambda: runner_closes.append(True))
    )

    class CancellationStore(SqlAlchemyWorkerJobStore):
        requested = False

        def heartbeat(self, job_id, **kwargs):
            current = super().heartbeat(job_id, **kwargs)
            cancel_ready = (
                current.stage == "grid_reinference:prepare" and current.progress_current > 0
                if scenario == "cancel_prepare"
                else current.stage == "grid_reinference:infer" and current.progress_current == 3
                if scenario == "cancel_between_sources"
                else False
            )
            if cancel_ready and not self.requested:
                self.requested = True
                with game_storage_scope(game), factory.begin() as session:
                    repository = FixtureRepository(session, root)
                    view = repository.get(game, operation_id)
                    repository.execute(
                        game,
                        operation_id,
                        "cancel",
                        {"idempotencyKey": str(uuid4()), "expectedRevision": view["revision"]},
                        "fixture-operator",
                    )
                current = super().heartbeat(job_id, **kwargs)
            return current

    store = CancellationStore(factory)
    if scenario == "late_source":
        original_page = SqlAlchemyGridReinferenceRepository.prepare_page

        def page_with_late_source(repository, operation):
            nonlocal late_seed
            if late_seed is None:
                from test_virtual_deferred_resolution_postgres import _seed

                late_seed = _seed(
                    factory, game, root, label="l" * 42, slot_count=1, sequence_base=200
                )
            return original_page(repository, operation)

        page_patch = patch.object(
            SqlAlchemyGridReinferenceRepository, "prepare_page", page_with_late_source
        )
    else:
        from contextlib import nullcontext

        page_patch = nullcontext()

    observed_errors = []

    def debug_handler(context, job):
        try:
            handler(context, job)
        except Exception as error:
            observed_errors.append(error)
            import traceback

            traceback.print_exc()
            raise

    worker = LocalJobWorker(
        store,
        {JobType.IMAGE_GRID_REINFERENCE: debug_handler},
        worker_id="task0999",
        worker_version="fixture",
    )

    def run_cancelled_phase(phase):
        with (
            patch.object(
                store,
                "fail",
                side_effect=AssertionError("Cancellation must use checkpoint, not fail-handler"),
            ) as fail,
            patch(
                "game_predictor_worker.jobs.store._reconcile_board_search",
                side_effect=AssertionError("Cancellation must not reconcile a failed handler"),
            ) as reconcile,
        ):
            assert worker.run_once() is JobExecutionResult.CANCELLED
            fail.assert_not_called()
            reconcile.assert_not_called()
        with game_storage_scope(game), factory() as session:
            current = session.get(JobModel, UUID(view["jobId"]))
            assert current.status.value == "cancelled" and current.error_code is None
            assert current.stage == f"grid_reinference:{phase}"
            assert current.checkpoint_payload == {
                "schema_version": 1,
                "workflow": "grid-reinference-v1",
                "phase": phase,
                "cursor": current.progress_current,
            }

    if scenario == "prepare_restart":
        with patch.object(
            SqlAlchemyGridReinferenceRepository,
            "prepare_page",
            side_effect=RuntimeError("controlled prepare interruption"),
        ):
            assert worker.run_once() is JobExecutionResult.FAILED
        with game_storage_scope(game), factory.begin() as session:
            repository = FixtureRepository(session, root)
            failed_view = repository.get(game, operation_id)
            assert failed_view["state"] == "failed"
            repository.execute(
                game,
                operation_id,
                "resume",
                {
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": failed_view["revision"],
                    "expectedPhase": "prepare",
                },
                "fixture-operator",
            )
    if scenario == "cancel_prepare":
        run_cancelled_phase("prepare")
        with game_storage_scope(game), factory.begin() as session:
            repository = FixtureRepository(session, root)
            paused = repository.get(game, operation_id)
            assert paused["state"] == "cancelled" and paused["phase"] == "prepare"
            repository.execute(
                game,
                operation_id,
                "resume",
                {
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": paused["revision"],
                    "expectedPhase": "prepare",
                },
                "fixture-operator",
            )
    with page_patch:
        assert worker.run_once() is JobExecutionResult.WAITING_FOR_REVIEW
    assert handler.calls == 0
    with game_storage_scope(game), factory.begin() as session:
        repository = FixtureRepository(session, root)
        view = repository.get(game, operation_id)
        assert view["state"] == "prepared"
        baseline_source_revision_id = session.scalar(
            select(ImageSourceGeometryRevisionModel.id)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        assert view["scopeStats"]["sourceOccurrenceCount"] == view["sourceCount"]
        assert view["scopeStats"]["selectedSlotCount"] == view["targetCount"]
        assert view["scopeStats"]["availableCellCount"] <= view["scopeStats"]["existingCellCount"]
        assert view["effectStats"]["notRecordedTargetCount"] == view["targetCount"]
        prepared_effect_stats = copy.deepcopy(view["effectStats"])
        assert view["targetCount"] == (
            1
            if scenario in {"manual_sibling", "foreign_pending_deferred"}
            else 3
            if scenario == "cancel_between_sources"
            else 2
        )
        if scenario == "late_source":
            from game_predictor_api.storage.grid_reinference_models import (
                GridReinferenceSourceModel as Source,
            )

            assert view["sourceCount"] == 1
            assert (
                session.scalar(
                    select(Source).where(
                        Source.operation_id == operation_id,
                        Source.source_image_id == late_seed.source_image_id,
                    )
                )
                is None
            )
        record = session.get(JobModel, UUID(view["jobId"]))
        assert record.lease_token is None
        from game_predictor_api.domain.jobs import JobConflictError

        with pytest.raises(JobConflictError) as failure:
            authorize_generic_retry(session, job_from_record(record))
        assert failure.value.code == "GRID_REINFERENCE_START_REQUIRED"
        command_body = {
            "idempotencyKey": str(uuid4()),
            "expectedRevision": view["revision"],
            "manifestSha256": view["manifestSha256"],
        }
        view = repository.execute(game, operation_id, "freeze", command_body, "fixture-operator")
    protected_sibling = None
    if scenario in {"target_conflict", "manual_sibling", "global_source_conflict"}:
        with game_storage_scope(game), factory.begin() as session:
            if scenario == "target_conflict":
                cell = session.scalar(
                    select(ImageSymbolReviewCellModel)
                    .order_by(ImageSymbolReviewCellModel.cell_index)
                    .limit(1)
                )
                assert cell is not None
                cell.revision += 1
            else:
                sibling = session.scalar(
                    select(RecognizedBoardModel).where(RecognizedBoardModel.sequence_number == 101)
                )
                if scenario == "global_source_conflict":
                    previous = session.scalar(
                        select(ImageSourceGeometryRevisionModel)
                        .order_by(ImageSourceGeometryRevisionModel.revision.desc())
                        .limit(1)
                    )
                    payload = {
                        column.name: copy.deepcopy(getattr(previous, column.name))
                        for column in ImageSourceGeometryRevisionModel.__table__.columns
                        if column.name not in {"id", "revision", "created_at", "updated_at"}
                    }
                    payload.update(
                        id=uuid4(),
                        revision=previous.revision + 1,
                        geometry_source="manual",
                        geometry_checksum_sha256="f" * 64,
                        created_by="fixture-human",
                    )
                    replacement = ImageSourceGeometryRevisionModel(**payload)
                    session.add(replacement)
                    session.flush()
                    sibling.source_geometry_revision_id = replacement.id
                    sibling.geometry_checksum_sha256 = replacement.geometry_checksum_sha256
                sibling.approved_geometry_revision = sibling.geometry_revision
                sibling.geometry_approved_by = "fixture-human"
                sibling.geometry_approved_at = datetime.now(UTC)
                sibling.board_geometry = {
                    **sibling.board_geometry,
                    "manualSiblingMarker": "preserve",
                }
                protected_sibling = (
                    sibling.id,
                    sibling.geometry_revision,
                    sibling.source_geometry_revision_id,
                    copy.deepcopy(sibling.board_geometry),
                )
    start = {
        "idempotencyKey": str(uuid4()),
        "expectedRevision": view["revision"],
        "manifestSha256": view["manifestSha256"],
        "broadScopeConfirmed": False,
    }
    with game_storage_scope(game), factory.begin() as session:
        FixtureRepository(session, root).execute(
            game, operation_id, "start", start, "fixture-operator"
        )
    if scenario == "source_deleted":
        with game_storage_scope(game), factory.begin() as session:
            repository = FixtureRepository(session, root)
            current = repository.get(game, operation_id)
            repository.execute(
                game,
                operation_id,
                "cancel",
                {
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": current["revision"],
                },
                "fixture-operator",
            )
        cleanup_fixture(database, factory, game, "range")
        with game_storage_scope(game), factory.begin() as session:
            repository = FixtureRepository(session, root)
            current = repository.get(game, operation_id)
            repository.execute(
                game,
                operation_id,
                "resume",
                {
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": current["revision"],
                    "expectedPhase": "infer",
                },
                "fixture-operator",
            )
    with patch(
        "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
        return_value=tmp_path / "fixture-bundle.json",
    ):
        if scenario == "rollback_retry":
            from game_predictor_api.storage.virtual_grid_geometry_repository import (
                SqlAlchemyVirtualGridGeometryRepository,
            )

            original_write = (
                SqlAlchemyVirtualGridGeometryRepository.save_automatic_reinference_source
            )

            def fail_after_write(writer, **kwargs):
                original_write(writer, **kwargs)
                raise RuntimeError("controlled receipt rollback")

            with patch.object(
                SqlAlchemyVirtualGridGeometryRepository,
                "save_automatic_reinference_source",
                fail_after_write,
            ):
                assert worker.run_once() is JobExecutionResult.FAILED
            with game_storage_scope(game), factory.begin() as session:
                assert not any(
                    row.result is not None
                    for row in session.scalars(
                        select(Target).where(Target.operation_id == operation_id)
                    )
                )
                assert all(
                    board.geometry_revision == 0
                    for board in session.scalars(select(RecognizedBoardModel))
                )
                repository = FixtureRepository(session, root)
                failed_view = repository.get(game, operation_id)
                assert failed_view["effectStats"]["recordedTargetCount"] == 0
                assert failed_view["effectStats"]["automaticWrittenBoardCount"] == 0
                assert failed_view["effectStats"] == prepared_effect_stats
                repository.execute(
                    game,
                    operation_id,
                    "resume",
                    {
                        "idempotencyKey": str(uuid4()),
                        "expectedRevision": failed_view["revision"],
                        "expectedPhase": "infer",
                    },
                    "fixture-operator",
                )
        if scenario == "cancel_between_sources":
            run_cancelled_phase("infer")
            assert len(runner_closes) == 1
            with game_storage_scope(game), factory.begin() as session:
                repository = FixtureRepository(session, root)
                paused = repository.get(game, operation_id)
                assert paused["state"] == "cancelled" and paused["processedSources"] == 1
                assert paused["effectStats"]["recordedTargetCount"] == 2
                assert paused["effectStats"]["notRecordedTargetCount"] == 1
                rows = list(
                    session.scalars(
                        select(Target)
                        .where(Target.operation_id == operation_id)
                        .order_by(Target.ordinal)
                    )
                )
                receipts = {
                    row.target_result_id: copy.deepcopy(row.result)
                    for row in rows
                    if row.source_ordinal == 1
                }
                assert all(value is not None for value in receipts.values())
                assert all(row.result is None for row in rows if row.source_ordinal == 2)
                assert handler.calls == 1
                repository.execute(
                    game,
                    operation_id,
                    "resume",
                    {
                        "idempotencyKey": str(uuid4()),
                        "expectedRevision": paused["revision"],
                        "expectedPhase": "infer",
                    },
                    "fixture-operator",
                )
        outcome = worker.run_once()
        with factory() as session:
            failed = session.get(JobModel, UUID(view["jobId"]))
            if scenario == "inconsistent_partial_stats":
                assert outcome is JobExecutionResult.FAILED
                assert failed.error_code == "JOB_EXECUTION_FAILED"
                assert observed_errors[-1].code == "SYMBOL_CELL_REVIEW_CROP_INVALID"
                assert "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID" in str(observed_errors[-1])
                with game_storage_scope(game), factory.begin() as checked:
                    current = FixtureRepository(checked, root).get(game, operation_id)
                    assert current["state"] == "failed" and current["processedSources"] == 0
                    assert current["effectStats"]["recordedTargetCount"] == 0
                    assert current["effectStats"]["automaticWrittenBoardCount"] == 0
                    assert (
                        current["effectStats"]["notRecordedTargetCount"] == current["targetCount"]
                    )
                    assert current["outcomes"] == {} and current["sourceStatusCounts"] == {}
                    assert all(
                        row.result is None
                        for row in checked.scalars(
                            select(Target).where(Target.operation_id == operation_id)
                        )
                    )
                    assert all(
                        row.geometry_revision == 0
                        for row in checked.scalars(select(RecognizedBoardModel))
                    )
                    assert (
                        checked.scalar(
                            select(ImageSourceGeometryRevisionModel.id)
                            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
                            .limit(1)
                        )
                        == baseline_source_revision_id
                    )
                return
            assert outcome is JobExecutionResult.COMPLETED, (
                failed.error_code,
                failed.error_message,
            )
    if scenario in {"cancel_between_sources", "foreign_pending_deferred"}:
        with game_storage_scope(game), factory.begin() as session:
            done = FixtureRepository(session, root).get(game, operation_id)
            assert done["effectStats"]["notRecordedTargetCount"] == 0
            rows = list(session.scalars(select(Target).where(Target.operation_id == operation_id)))
            if scenario == "cancel_between_sources":
                assert done["outcomes"] == {"automatic_written": 2, "unchanged": 1}
                assert handler.calls == 2 and len(runner_closes) == 2
                assert all(
                    row.result == receipts[row.target_result_id]
                    for row in rows
                    if row.source_ordinal == 1
                )
            else:
                assert done["outcomes"] == {"protected": 1}
                assert (
                    session.scalar(
                        select(RecognizedBoardModel.id).where(
                            RecognizedBoardModel.source_image_id == late_seed.source_image_id
                        )
                    )
                    is None
                )
                from game_predictor_api.storage.models import ImageBoardGeometryPendingModel

                pending = session.get(
                    ImageBoardGeometryPendingModel, UUID(rows[0].snapshot["pending"]["id"])
                )
                assert pending.status == "pending" and pending.review_item_id is None
                assert rows[0].snapshot["foreignOwner"] is not None
        return
    assert handler.calls == (0 if scenario == "source_deleted" else 1)
    with game_storage_scope(game), factory.begin() as session:
        repository = FixtureRepository(session, root)
        before = repository.get(game, operation_id)
        replay = repository.execute(game, operation_id, "start", start, "fixture-operator")
        assert replay["state"] == "completed"
        expected = (
            {"unchanged": 2}
            if scenario == "unchanged"
            else {"conflict": 2}
            if scenario == "global_source_conflict"
            else {"source_missing": 2}
            if scenario == "source_deleted"
            else {"automatic_written": 1, "conflict": 1}
            if scenario == "target_conflict"
            else {"automatic_written": 1, "proposal_ready": 1}
            if scenario == "grid_issue"
            else {"automatic_written": 1}
            if scenario == "manual_sibling"
            else {"automatic_written": 2}
        )
        assert replay["outcomes"] == expected
        effect = replay["effectStats"]
        assert effect["notRecordedTargetCount"] == 0
        assert effect["recordedTargetCount"] == sum(expected.values())
        assert effect["automaticWrittenBoardCount"] == expected.get("automatic_written", 0)
        assert effect == before["effectStats"]
        assert replay["modelSnapshot"] == snapshot
        assert before["reportSha256"] == replay["reportSha256"]
        rows = list(session.scalars(select(Target).where(Target.operation_id == operation_id)))
        for field in effect:
            if field != "schemaVersion":
                assert effect[field] == sum(row.result["effectStats"][field] for row in rows)
        if scenario == "accepted":
            assert effect["changedExistingPixelCellCount"] > 0
        if scenario == "deferred_stats":
            assert effect["createdBoardCount"] == 1 and effect["createdCellCount"] == 15
        if scenario == "unchanged":
            assert effect["changedExistingPixelCellCount"] == 0
        acceptance = (
            "not_evaluated"
            if scenario in {"source_deleted", "unchanged", "global_source_conflict"}
            else "needs_review"
            if scenario in {"target_conflict", "manual_sibling", "grid_issue"}
            else "accepted"
        )
        assert all(row.result["sourceAcceptance"]["status"] == acceptance for row in rows)
        if protected_sibling is not None:
            sibling = session.get(RecognizedBoardModel, protected_sibling[0])
            assert (
                sibling.id,
                sibling.geometry_revision,
                sibling.source_geometry_revision_id,
                sibling.board_geometry,
            ) == protected_sibling
            assert sibling.geometry_approved_by == "fixture-human"
        if scenario == "grid_issue":
            assert (
                session.scalar(
                    select(ImageSymbolReviewCellModel.id).where(
                        ImageSymbolReviewCellModel.quality_issue == "grid_issue",
                        ImageSymbolReviewCellModel.review_state == "pending",
                    )
                )
                is not None
            )
        if scenario not in {"source_deleted", "unchanged", "global_source_conflict"}:
            from game_predictor_api.application.grid_reinference import (
                ACCEPTANCE_POLICY,
                CONTRACT,
                digest,
            )

            revision = session.scalar(
                select(ImageSourceGeometryRevisionModel)
                .order_by(ImageSourceGeometryRevisionModel.revision.desc())
                .limit(1)
            )
            frozen_previous = rows[0].snapshot["geometryContext"]["id"]
            assert revision.geometry_checksum_sha256 == digest(
                {
                    "policy": CONTRACT,
                    "previous": frozen_previous,
                    "boards": revision.board_geometries,
                }
            )
            assert (
                revision.global_initialization["gridReinference"]["acceptancePolicy"]
                == ACCEPTANCE_POLICY
            )
            assert "gridReinferenceAcceptance" not in revision.global_initialization
        boards = list(session.scalars(select(RecognizedBoardModel)))
        assert [
            board.sequence_number for board in sorted(boards, key=lambda item: item.position_index)
        ] == ([] if scenario == "source_deleted" else [100, 101])
        assert all(
            board.approved_geometry_revision is None and board.geometry_approved_by is None
            for board in boards
            if protected_sibling is None or board.id != protected_sibling[0]
        )
        assert session.scalar(
            select(ImageSourceGeometryRevisionModel.status)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        ) == (
            None
            if scenario == "source_deleted"
            else "accepted"
            if scenario in {"unchanged", "global_source_conflict"}
            else acceptance
        )
    assert worker.run_once() is JobExecutionResult.NO_JOB
    if scenario in {"cleanup_reset", "cleanup_range"}:
        cleanup_fixture(
            database, factory, game, "reset" if scenario == "cleanup_reset" else "range"
        )


def cleanup_fixture(database, factory, game, kind):
    """Production cleanup on owned data, unchanged history, rollback and other games."""
    from game_predictor_api.application.cleanup import CleanupService
    from game_predictor_api.domain.cleanup import BoardSourceCleanupSelection, CleanupCommand
    from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
    from game_predictor_api.storage.database import create_cross_game_owner_session_factory
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceSourceModel as Source,
    )
    from game_predictor_api.storage.models import SourceImageModel

    artifacts = SimpleNamespace(
        delete=lambda _paths: None,
        quarantine=lambda *_args: None,
        restore=lambda *_args: None,
        finalize=lambda *_args: None,
    )
    owner_factory = create_cross_game_owner_session_factory(database.engine)

    def retained(session):
        return [
            (
                row.operation_id,
                row.ordinal,
                row.source_image_id,
                copy.deepcopy(row.document),
                copy.deepcopy(row.checkpoint),
            )
            for row in session.scalars(select(Source).order_by(Source.operation_id, Source.ordinal))
        ]

    with owner_factory() as session:
        before_all = retained(session)
    with game_storage_scope(game), factory() as session:
        service = CleanupService(SqlAlchemyCleanupRepository(session, owner_factory), artifacts)
        selection = BoardSourceCleanupSelection(sequence_numbers=(100, 101))
        preview = (
            service.preview_game_reset(game)
            if kind == "reset"
            else service.preview_board_sources(game, selection)
        )
        assert not preview.snapshot.blockers
        if kind == "reset":
            assert any(
                row.name == "grid_reinference_links_detached" and row.count == 1
                for row in preview.snapshot.counts
            )
        else:
            assert (
                "GRID_REINFERENCE_HISTORY_RETAINED_LIVE_SOURCE_LINKS_DETACHED"
                in preview.snapshot.warnings
            )
        command_body = CleanupCommand(
            preview.preview_token, preview.snapshot.confirmation_target, True
        )
        if kind == "reset":
            service.reset_game(game, command_body)
        else:
            service.delete_board_sources(game, selection, command_body)
        # Rollback must restore both the source and live history link.
        session.rollback()
    with game_storage_scope(game), factory() as session:
        assert session.scalar(select(SourceImageModel.id)) is not None
        assert all(
            row.live_source_image_id == row.source_image_id
            for row in session.scalars(select(Source))
        )
        service = CleanupService(SqlAlchemyCleanupRepository(session, owner_factory), artifacts)
        preview = (
            service.preview_game_reset(game)
            if kind == "reset"
            else service.preview_board_sources(game, selection)
        )
        command_body = CleanupCommand(
            preview.preview_token, preview.snapshot.confirmation_target, True
        )
        if kind == "reset":
            service.reset_game(game, command_body)
        else:
            service.delete_board_sources(game, selection, command_body)
        session.commit()
    with game_storage_scope(game), factory() as session:
        assert session.scalar(select(SourceImageModel.id)) is None
        assert all(row.live_source_image_id is None for row in session.scalars(select(Source)))
        assert session.scalar(select(JobModel.id).where(JobModel.game_id == game)) is not None
    with owner_factory() as session:
        assert retained(session) == before_all


def test_symmetric_admission_all_active_phases_and_mutex(database):
    from datetime import timedelta

    from game_predictor_api.domain.jobs import JobConflictError, JobStatus, create_job
    from game_predictor_api.storage.job_admission import acquire_job_admission, admit_job
    from game_predictor_api.storage.job_repository import job_record_from_domain
    from sqlalchemy.exc import OperationalError
    from test_virtual_deferred_resolution_postgres import _factory

    game = _provision_game(database.engine, "task0999-admission-" + uuid4().hex[:8])
    factory = _factory(database.engine)

    def role(_session, _transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{database.role}"')

    event.listen(factory, "after_begin", role)
    kinds = [
        JobType.IMAGE_GRID_REINFERENCE,
        JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        JobType.SYMBOL_TRAINING,
        JobType.IMAGE_SYMBOL_REINFERENCE,
        JobType.IMAGE_SYMBOL_REVIEW_BULK,
        JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
        JobType.IMPORT,
        JobType.VALIDATE,
    ]
    with game_storage_scope(game), factory.begin() as session:
        for kind in kinds:
            payload = {"schema_version": 1}
            if kind is JobType.IMPORT:
                payload["import_kind"] = "image_directory"
            elif kind is JobType.VALIDATE:
                payload["validation_kind"] = "page_geometry_preflight"
            # Existing queued jobs from every competing workflow must block
            # both geometry and symbol starts through the same production gate.
            active = job_record_from_domain(create_job(kind, game_id=game, input_payload=payload))
            session.add(active)
            session.flush()
            for new_kind in (JobType.IMAGE_GRID_REINFERENCE, JobType.SYMBOL_TRAINING):
                with pytest.raises(JobConflictError) as failure:
                    admit_job(
                        session,
                        create_job(new_kind, game_id=game, input_payload={"schema_version": 1}),
                    )
                assert failure.value.code == "GAME_JOB_ADMISSION_CONFLICT"
            # Existing CREATED candidates passed enqueue admission already.
            admit_job(
                session,
                create_job(
                    JobType.IMAGE_GRID_REINFERENCE,
                    game_id=game,
                    input_payload={"schema_version": 1},
                ),
                worker_execution=True,
            )
            active.status = JobStatus.WAITING_FOR_REVIEW
            session.flush()
            acquire_job_admission(session, game)
            now = datetime.now(UTC)
            active.status = JobStatus.PROCESSING
            active.lease_token, active.lease_owner = uuid4(), "task0999-admission"
            active.started_at, active.heartbeat_at, active.lease_expires_at = (
                now,
                now,
                now + timedelta(minutes=1),
            )
            active.cancel_requested_at = now
            active.execution_slot = 1
            session.flush()
            with pytest.raises(JobConflictError):
                acquire_job_admission(session, game)
            with pytest.raises(JobConflictError):
                admit_job(
                    session,
                    create_job(
                        JobType.SYMBOL_TRAINING,
                        game_id=game,
                        input_payload={"schema_version": 1},
                    ),
                    worker_execution=True,
                )
            session.delete(active)
            session.flush()
    # A competing transaction cannot enter the gate while a first start owns
    # the mutex. The statement is bounded independently of the gate's lock limit.
    with game_storage_scope(game), factory() as first, factory() as second:
        acquire_job_admission(first, game)
        second.execute(text("SET LOCAL statement_timeout='200ms'"))
        with pytest.raises(OperationalError):
            acquire_job_admission(second, game)
        second.rollback()
        first.rollback()
        acquire_job_admission(second, game)
        second.rollback()


def seed_retained_history(session, game, source_id):
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceOperationModel as Operation,
    )
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceSourceModel as Source,
    )

    job = JobModel(
        id=uuid4(),
        game_id=game,
        job_type=JobType.IMAGE_GRID_REINFERENCE,
        status="cancelled",
        input_payload={"schema_version": 1},
        input_key=uuid4().hex * 2,
    )
    session.add(job)
    session.flush()
    operation = Operation(
        game_id=game,
        id=uuid4(),
        idempotency_key=uuid4(),
        command_sha256="a" * 64,
        job_id=job.id,
        document={"fixture": "retained immutable report"},
    )
    session.add(operation)
    session.flush()
    source = Source(
        game_id=game,
        operation_id=operation.id,
        ordinal=1,
        source_image_id=source_id,
        live_source_image_id=source_id,
        document={"frozen": str(source_id)},
        checkpoint={"sha256": "b" * 64},
    )
    session.add(source)
    session.flush()
    return operation.id


def test_browser_staging_detaches_only_live_link_and_keeps_guards(database, tmp_path):
    from game_predictor_api.storage.browser_staging_retention_repository import (
        SqlAlchemyBrowserStagingRetentionRepository,
    )
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceSourceModel as Source,
    )
    from game_predictor_api.storage.models import SourceImageModel
    from test_virtual_deferred_resolution_postgres import _factory, _seed

    game = _provision_game(database.engine, "task0999-retention-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    seed = _seed(factory, game, tmp_path / "retention", label="retention" + "x" * 45, slot_count=1)
    upload = uuid4()
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        job.input_payload = {**job.input_payload, "source_selection_id": str(upload)}
        operation = seed_retained_history(session, game, seed.source_image_id)
        source = session.get(Source, (game, operation, 1))
        before = copy.deepcopy(source.document), copy.deepcopy(source.checkpoint)
    SqlAlchemyBrowserStagingRetentionRepository(factory).discard_unused(
        upload_id=upload, game_id=game
    )
    with game_storage_scope(game), factory() as session:
        assert session.get(SourceImageModel, seed.source_image_id) is None
        source = session.get(Source, (game, operation, 1))
        assert (
            source.source_image_id == seed.source_image_id and source.live_source_image_id is None
        )
        assert (source.document, source.checkpoint) == before


def test_superseded_preview_knows_exact_live_reference_and_other_foreign_keys(database):
    from game_predictor_api.storage import game_data_v2_manifest_v12 as v12
    from game_predictor_api.storage.database import create_cross_game_owner_session_factory
    from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
    from game_predictor_api.storage.superseded_import_image_removal_repository import (
        REFERENCED_BY,
        SupersededImportImageRemovalRepository,
        plan_report,
    )
    from test_superseded_import_image_removal import _build_world

    with (
        patch("test_superseded_import_image_removal.GAME_TABLES", v12.GAME_TABLES),
        patch("test_superseded_import_image_removal.VERSION", v12.VERSION),
    ):
        world = _build_world(database.engine)
    owner_factory = create_cross_game_owner_session_factory(database.engine)
    with owner_factory() as session, session.begin():
        GameStorageRouter().bind(session, world.game_id, intent=GameStorageIntent.WRITE)
        seed_retained_history(session, world.game_id, world.images["dead_a.jpg"])
    plan = SupersededImportImageRemovalRepository(database.engine).preview(
        world.game_id, world.target_job
    )
    assert world.images["dead_a.jpg"] in plan.image_ids
    report = plan_report(plan)
    assert report["gridReinferenceHistory"] == {
        "retainedSourceManifests": 1,
        "detachedLiveSourceLinks": 1,
    }
    linked = next(
        image for image in plan.images if image.source_image_id == world.images["fk_ref.jpg"]
    )
    assert not linked.qualifies and any(
        reason.startswith(REFERENCED_BY) for reason in linked.reasons
    )


def test_worker_queue_skips_locked_row_without_created_deadlock(database, caplog):
    from datetime import timedelta

    from game_predictor_api.domain.jobs import complete_job, create_job
    from game_predictor_api.storage.job_repository import job_record_from_domain
    from test_virtual_deferred_resolution_postgres import _factory

    game_a = _provision_game(database.engine, "queue-a-" + uuid4().hex[:8])
    game_b = _provision_game(database.engine, "queue-b-" + uuid4().hex[:8])
    factory, now = _factory(database.engine), datetime.now(UTC)
    old = [
        create_job(
            JobType.IMPORT,
            game_id=game_a,
            input_payload={"schema_version": 1, "import_kind": "image_directory", "fixture": i},
            created_at=now + timedelta(microseconds=i),
        )
        for i in range(2)
    ]
    other = create_job(
        JobType.IMPORT,
        game_id=game_b,
        input_payload={"schema_version": 1, "import_kind": "image_directory"},
        created_at=now + timedelta(seconds=1),
    )
    with game_storage_scope(game_a), factory.begin() as session:
        session.add_all([job_record_from_domain(job) for job in old])
    with game_storage_scope(game_b), factory.begin() as session:
        session.add(job_record_from_domain(other))
    store = SqlAlchemyWorkerJobStore(factory)

    def claim():
        return store.claim_next(
            worker_id="fixture",
            worker_version="fixture",
            lease_duration=timedelta(minutes=1),
            claimed_at=now,
        )

    def finish(job):
        with factory.begin() as session:
            apply_job_to_record(
                session.get(JobModel, job.id),
                complete_job(job, lease_token=job.lease_token, finished_at=now),
            )

    with factory() as locked:
        locked.scalar(select(JobModel).where(JobModel.id == old[0].id).with_for_update())
        claimed = claim()
        assert claimed.id == old[1].id  # Other CREATED never blocks this old job.
        finish(claimed)
        claimed = claim()
        assert claimed.id == other.id  # Locked first row never hides another game.
        assert any("JOB_ROW_LOCKED" in row.message for row in caplog.records)
        finish(claimed)
        locked.rollback()
    claimed = claim()
    assert claimed.id == old[0].id
    finish(claimed)


def unauthorized_grid_queue(session, game, *, now, processing=False, cancel=False):
    from datetime import timedelta

    from game_predictor_api.domain.jobs import create_job, start_job
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceOperationModel as Operation,
    )
    from game_predictor_api.storage.job_repository import job_record_from_domain

    operation = uuid4()
    job = create_job(
        JobType.IMAGE_GRID_REINFERENCE,
        game_id=game,
        input_payload={
            "schema_version": 3,
            "inference_kind": "grid-reinference-v1",
            "operation_id": str(operation),
        },
        created_at=now - timedelta(minutes=3),
    )
    if processing:
        job = start_job(
            job,
            worker_version="fixture",
            worker_id="fixture",
            lease_token=uuid4(),
            lease_expires_at=now - timedelta(seconds=1),
            started_at=now - timedelta(minutes=2),
        )
        if cancel:
            from dataclasses import replace

            job = replace(job, cancel_requested_at=now - timedelta(seconds=2))
    session.add(job_record_from_domain(job))
    session.flush()
    doc = {
        "state": "frozen",
        "phase": "prepare",
        "revision": 0,
        "manifestSha256": "a" * 64,
        "freezeSha256": "a" * 64,
        "receipts": {},
        "modelSnapshot": {"immutable": "historical"},
    }
    session.add(
        Operation(
            game_id=game,
            id=operation,
            idempotency_key=uuid4(),
            command_sha256="b" * 64,
            job_id=job.id,
            document=doc,
        )
    )
    session.flush()
    return job.id, operation, copy.deepcopy(doc)


def test_expired_unauthorized_quarantine_releases_slot_preserves_evidence_and_cancel_wins(database):
    from game_predictor_api.domain.jobs import JobConflictError, JobStatus
    from game_predictor_api.storage.grid_reinference import require_grid_retry_authorization
    from game_predictor_api.storage.grid_reinference_models import (
        GridReinferenceOperationModel as Operation,
    )
    from test_virtual_deferred_resolution_postgres import _factory

    game = _provision_game(database.engine, "expired-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    now = datetime.now(UTC)
    store = SqlAlchemyWorkerJobStore(factory)
    for cancel in (False, True):
        with game_storage_scope(game), factory.begin() as session:
            job_id, operation, original = unauthorized_grid_queue(
                session, game, now=now, processing=True, cancel=cancel
            )
        recovered = store.recover_expired(recovered_at=now)
        assert (
            recovered.id == job_id
            and recovered.lease_token is None
            and recovered.execution_slot is None
        )
        assert recovered.status is (JobStatus.CANCELLED if cancel else JobStatus.FAILED)
        with game_storage_scope(game), factory.begin() as session:
            doc = session.get(Operation, (game, operation)).document
            assert (
                doc["manifestSha256"] == original["manifestSha256"]
                and doc["modelSnapshot"] == original["modelSnapshot"]
                and doc["receipts"] == original["receipts"]
            )
            assert bool(doc.get("executionQuarantine")) is not cancel
            if not cancel:
                with pytest.raises(JobConflictError) as caught:
                    require_grid_retry_authorization(session, recovered)
                assert caught.value.code == "GRID_REINFERENCE_START_REQUIRED"
                with pytest.raises(JobConflictError) as caught:
                    SqlAlchemyGridReinferenceRepository(session, Path(".")).execute(
                        game,
                        operation,
                        "resume",
                        {
                            "idempotencyKey": str(uuid4()),
                            "expectedRevision": 0,
                            "expectedPhase": "prepare",
                        },
                        "fixture",
                    )
                assert caught.value.code == "GRID_REINFERENCE_START_REQUIRED"


def test_scan100_durably_excludes_101_invalid_jobs_and_reaches_other_game(database):
    from datetime import timedelta

    from game_predictor_api.domain.jobs import JobStatus, create_job
    from game_predictor_api.storage.job_repository import job_record_from_domain
    from test_virtual_deferred_resolution_postgres import _factory

    game = _provision_game(database.engine, "quarantine-" + uuid4().hex[:8])
    other = _provision_game(database.engine, "after-limit-" + uuid4().hex[:8])
    factory = _factory(database.engine)
    now = datetime.now(UTC)
    with game_storage_scope(game), factory.begin() as session:
        ids = [unauthorized_grid_queue(session, game, now=now)[0] for _ in range(101)]
    valid = create_job(
        JobType.PAYOUT, game_id=other, input_payload={"schema_version": 1}, created_at=now
    )
    with game_storage_scope(other), factory.begin() as session:
        session.add(job_record_from_domain(valid))
    store = SqlAlchemyWorkerJobStore(factory)
    assert (
        store.claim_next(
            worker_id="fixture",
            worker_version="fixture",
            lease_duration=timedelta(minutes=1),
            claimed_at=now,
        )
        is None
    )
    with factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(JobModel.id).where(
                            JobModel.id.in_(ids), JobModel.status == JobStatus.FAILED
                        )
                    )
                )
            )
            == 100
        )
    claimed = store.claim_next(
        worker_id="fixture",
        worker_version="fixture",
        lease_duration=timedelta(minutes=1),
        claimed_at=now,
    )
    assert claimed.id == valid.id
    with factory() as session:
        assert all(
            session.get(JobModel, key).error_code == "GRID_REINFERENCE_START_REQUIRED"
            for key in ids
        )
    # Avoid an active fixture lane leaking into another case in this module.
    from game_predictor_api.domain.jobs import complete_job

    with factory.begin() as session:
        apply_job_to_record(
            session.get(JobModel, claimed.id),
            complete_job(claimed, lease_token=claimed.lease_token, finished_at=now),
        )
